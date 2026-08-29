import uuid
import json
import logging
from flask import Blueprint, request, Response, g, current_app, stream_with_context, jsonify

from app.extensions import db
from app.middleware.auth import require_tenant_context, load_user_context
from app.models.audit_log import AuditLog
from app.models.chat_thread import ChatThread
from app.models.chat_message import ChatMessage
from app.models.agent_config import AgentConfig

chat_bp = Blueprint("chat", __name__)
logger = logging.getLogger(__name__)


def _save_message(tenant_id, thread_id, user_id, role, content):
    """持久化一条消息到 chat_messages 表"""
    try:
        msg = ChatMessage(tenant_id=tenant_id, thread_id=thread_id,
                          user_id=user_id, role=role, content=content)
        db.session.add(msg)
        db.session.commit()
    except Exception:
        db.session.rollback()


def _load_messages(thread_id: str) -> list[dict]:
    """从 chat_messages 表加载消息历史"""
    msgs = ChatMessage.query.filter_by(thread_id=thread_id)\
        .order_by(ChatMessage.created_at.asc()).all()
    return [m.to_dict() for m in msgs]


def _gen_title(message: str, max_len: int = 30) -> str:
    """从首条消息生成对话标题"""
    t = message.strip().replace("\n", " ")[:max_len]
    return t if t else "新对话"


@chat_bp.route("/chat/stream", methods=["POST"])
@require_tenant_context
def chat_stream():
    """流式对话接口 (SSE) - 支持 agent 和模型选择"""
    data = request.get_json()
    if not data or "message" not in data:
        return Response(
            f"data: {json.dumps({'type': 'error', 'message': 'message is required'})}\n\n",
            mimetype="text/event-stream",
        ), 422

    user_message = data["message"]
    thread_id = data.get("thread_id")
    model_provider_id = data.get("model_provider_id")
    agent_id = data.get("agent_id")
    is_new = not thread_id

    # ===== 安全围栏：输入检查（必须在任何持久化之前执行）=====
    # 拦截（危险内容）→ 直接返回 error 事件，原始内容不落库、不创建线程
    # 脱敏（PII）→ 用脱敏后的文本走后续全部流程（标题/落库/LLM）
    try:
        from app.core.guardrails.chain import GuardrailChain
        _guardrail = GuardrailChain()
        _g_input = _guardrail.check_input(user_message)
        if not _g_input.passed:
            logger.warning(f"Guardrail blocked input (user {g.user_id}): {_g_input.reason[:200]}")
            AuditLog.log(
                tenant_slug=g.tenant_slug, user_id=int(g.user_id),
                action="guardrail:block_input", resource="chat",
                detail={"reason": _g_input.reason[:200]}, status="blocked",
            )
            return Response(
                f"data: {json.dumps({'type': 'error', 'message': f'[安全围栏] {_g_input.reason}'}, ensure_ascii=False)}\n\n",
                mimetype="text/event-stream",
            ), 200
        if _g_input.modified_text and _g_input.modified_text != user_message:
            user_message = _g_input.modified_text
    except Exception as e:
        # 围栏自身异常时 fail-open，不阻塞对话（可用性优先）
        logger.warning(f"Guardrail input check failed (fail-open): {e}")

    if not thread_id:
        thread_id = str(uuid.uuid4())

    tenant_slug = g.tenant_slug
    user_id = g.user_id
    tenant_id = g.tenant_id
    full_thread_id = f"{tenant_slug}:{user_id}:{thread_id}"

    # 新建线程时创建 DB 记录
    if is_new:
        title = _gen_title(user_message)
        t = ChatThread(
            tenant_id=tenant_id, user_id=int(user_id),
            thread_id=thread_id, agent_id=agent_id,
            title=title, model_provider_id=model_provider_id,
        )
        db.session.add(t)
        db.session.commit()

    # 持久化用户消息
    _save_message(tenant_id, thread_id, int(user_id), "user", user_message)

    def generate():
        # 第一条事件：回传 thread_id，让前端知道后端生成的 UUID
        yield f"data: {json.dumps({'type': 'thread_id', 'thread_id': thread_id, 'full_thread_id': full_thread_id})}\n\n"

        ai_content = []
        last_usage = None  # 从 done 事件中提取的 token 用量
        orchestrator = current_app.extensions["agent_orchestrator"]
        try:
            for sse_event in orchestrator.stream_chat(
                user_message=user_message, thread_id=full_thread_id,
                user_id=user_id, tenant_id=tenant_id,
                model_provider_id=model_provider_id,
                agent_id=agent_id,
            ):
                # 收集 AI 回复 token 和用量信息
                line = sse_event.strip()
                if line.startswith("data: "):
                    try:
                        event = json.loads(line[6:])
                        if event.get("type") == "token":
                            ai_content.append(event.get("content", ""))
                        elif event.get("type") == "done" and "usage" in event:
                            last_usage = event["usage"]
                    except json.JSONDecodeError:
                        pass
                yield sse_event
        except Exception as e:
            logger.exception(f"Chat stream error: thread={full_thread_id}")
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)}, ensure_ascii=False)}\n\n"

        # ===== 安全围栏：输出检查（在持久化 AI 回复之前）=====
        # 流式 token 已展示，此检查保证落库内容干净 + 前台收到告警提示
        if ai_content:
            _g_out = _guardrail.check_output("".join(ai_content))
            if not _g_out.passed:
                logger.warning(f"Guardrail blocked output (thread {thread_id}): {_g_out.reason[:200]}")
                AuditLog.log(
                    tenant_slug=tenant_slug, user_id=int(user_id),
                    action="guardrail:block_output", resource="chat",
                    resource_id=thread_id, detail={"reason": _g_out.reason[:200]}, status="blocked",
                )
                yield f"data: {json.dumps({'type': 'guardrail', 'message': f'回复内容触发安全拦截: {_g_out.reason}'}, ensure_ascii=False)}\n\n"
                ai_content = [f"[安全围栏] 该回复因触发安全规则已被拦截: {_g_out.reason}"]
            elif _g_out.modified_text and _g_out.modified_text != "".join(ai_content):
                ai_content = [_g_out.modified_text]

        # 持久化 AI 回复
        if ai_content:
            _save_message(tenant_id, thread_id, int(user_id), "assistant", "".join(ai_content))

        # 记录 Token 用量
        if last_usage:
            try:
                from app.core.monitoring.cost_tracker import CostTracker
                # 解析使用的模型名称
                provider_config = orchestrator._resolve_provider_config(tenant_id, model_provider_id)
                model_name = provider_config.get("model_name", "unknown")
                CostTracker().record(
                    tenant_id=tenant_slug, user_id=str(user_id), model=model_name,
                    input_tokens=last_usage.get("input_tokens", 0),
                    output_tokens=last_usage.get("output_tokens", 0),
                )
            except Exception:
                pass

        # 更新消息计数
        try:
            t = ChatThread.query.filter_by(thread_id=thread_id).first()
            if t:
                t.message_count = (t.message_count or 0) + 2
                db.session.commit()
        except Exception:
            pass

        AuditLog.log(tenant_slug=tenant_slug, user_id=int(user_id),
                     action="agent:execute", resource="chat", resource_id=thread_id,
                     detail={"agent_id": agent_id, "model_provider_id": model_provider_id})

    return Response(
        stream_with_context(generate()), mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"},
    )


@chat_bp.route("/chat/threads", methods=["GET"])
def list_threads():
    """获取当前用户的对话线程列表（供侧边栏）"""
    load_user_context()
    threads = ChatThread.query.filter_by(
        tenant_id=g.tenant_id, user_id=int(g.user_id), is_active=True
    ).order_by(ChatThread.updated_at.desc()).limit(50).all()

    result = []
    for t in threads:
        d = t.to_dict()
        # 补充 agent 名称
        if t.agent_id:
            agent = AgentConfig.query.get(t.agent_id)
            if agent:
                d["agent_name"] = agent.name
        result.append(d)
    return jsonify({"threads": result}), 200


@chat_bp.route("/chat/threads/<thread_id>", methods=["GET"])
def get_thread(thread_id):
    """获取对话历史 + 一致性校验（双重存储对比）"""
    load_user_context()
    messages = _load_messages(thread_id)

    # --- 一致性校验：对比 chat_messages ↔ PostgresSaver ---
    consistency = {"status": "ok"}
    try:
        orchestrator = current_app.extensions.get("agent_orchestrator")
        if orchestrator and orchestrator._checkpointer:
            full_tid = f"{g.tenant_slug}:{g.user_id}:{thread_id}"
            cp_state = orchestrator.get_thread_state(full_tid)
            if cp_state:
                cp_count = cp_state.get("message_count", 0)
                db_count = len(messages)
                if cp_count != db_count:
                    logger.warning(
                        f"Thread {thread_id} consistency mismatch: "
                        f"chat_messages={db_count}, checkpointer={cp_count}"
                    )
                    consistency = {
                        "status": "mismatch",
                        "chat_messages_count": db_count,
                        "checkpointer_count": cp_count,
                    }
    except Exception as e:
        logger.warning(f"Consistency check failed for thread {thread_id}: {e}")
        consistency = {"status": "unavailable", "reason": str(e)[:200]}

    return jsonify({
        "thread_id": thread_id,
        "messages": messages,
        "message_count": len(messages),
        "consistency": consistency,
    }), 200


@chat_bp.route("/chat/threads/<thread_id>", methods=["DELETE"])
def delete_thread(thread_id):
    """清除对话 — 软删除 DB 记录 + 消息 + LangGraph 检查点"""
    load_user_context()

    full_tid = f"{g.tenant_slug}:{g.user_id}:{thread_id}"

    # 1. 软删除线程
    t = ChatThread.query.filter_by(
        thread_id=thread_id, tenant_id=g.tenant_id, user_id=int(g.user_id)
    ).first()
    if t:
        t.is_active = False
        db.session.commit()

    # 2. 删除所有关联消息
    ChatMessage.query.filter_by(thread_id=thread_id).delete()
    db.session.commit()

    # 3. 清理 LangGraph 检查点（PostgresSaver 中的对话状态）
    checkpoint_cleaned = False
    try:
        orchestrator = current_app.extensions.get("agent_orchestrator")
        if orchestrator:
            orchestrator.delete_thread_checkpoint(full_tid)
            checkpoint_cleaned = True
    except Exception as e:
        logger.warning(f"Checkpoint cleanup failed for {full_tid}: {e}")

    AuditLog.log(
        tenant_slug=g.tenant_slug, user_id=int(g.user_id),
        action="chat:delete_thread", resource="chat", resource_id=thread_id,
        detail={"checkpoint_cleaned": checkpoint_cleaned},
    )
    return jsonify({
        "message": "对话已清除",
        "checkpoint_cleaned": checkpoint_cleaned,
    }), 200

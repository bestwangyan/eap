"""Phase 3: 编排 API — 子Agent管理 + 编排测试"""
import json
import logging
from flask import Blueprint, request, jsonify, g

from app.extensions import db
from app.middleware.auth import require_tenant_context, require_permission
from app.models.sub_agent import SubAgentDefinition
from app.core.agent.sub_agent_manager import SubAgentManager
from app.models.audit_log import AuditLog

orch_bp = Blueprint("orchestration", __name__)
logger = logging.getLogger(__name__)


@orch_bp.route("/agents/<int:agent_id>/sub-agents", methods=["GET"])
@require_tenant_context
def list_sub_agents(agent_id):
    subs = SubAgentDefinition.query.filter_by(
        tenant_id=g.tenant_id, parent_agent_id=agent_id
    ).all()
    return jsonify({"sub_agents": [s.to_dict() for s in subs]}), 200


@orch_bp.route("/agents/<int:agent_id>/sub-agents", methods=["POST"])
@require_permission("agent:create")
def create_sub_agent(agent_id):
    data = request.get_json()
    if not data or "name" not in data or "role_prompt" not in data:
        return jsonify({"error": "name and role_prompt are required"}), 422

    sub = SubAgentDefinition(
        tenant_id=g.tenant_id, parent_agent_id=agent_id,
        name=data["name"], role_prompt=data["role_prompt"],
        tools=data.get("tools", []), model=data.get("model"),
        mode=data.get("mode", "inline"),
    )
    db.session.add(sub)
    db.session.commit()

    AuditLog.log(tenant_slug=g.tenant_slug, user_id=int(g.user_id),
                 action="orchestration:create_sub_agent", resource="sub_agent",
                 resource_id=str(sub.id), detail={"name": sub.name, "mode": sub.mode})
    return jsonify({"sub_agent": sub.to_dict()}), 201


@orch_bp.route("/agents/<int:agent_id>/sub-agents/<int:sub_id>", methods=["DELETE"])
@require_permission("agent:delete")
def delete_sub_agent(agent_id, sub_id):
    sub = SubAgentDefinition.query.filter_by(
        id=sub_id, tenant_id=g.tenant_id, parent_agent_id=agent_id
    ).first()
    if not sub:
        return jsonify({"error": "Not found"}), 404
    db.session.delete(sub)
    db.session.commit()
    return jsonify({"message": "deleted"}), 200


@orch_bp.route("/orchestration/test", methods=["POST"])
@require_permission("agent:execute")
def test_orchestration():
    """测试监督者路由 — 分析用户消息并返回 Worker 选择"""
    data = request.get_json()
    message = data.get("message", "")
    agent_id = data.get("agent_id")

    manager = SubAgentManager()
    if agent_id:
        manager.load_from_db(g.tenant_id, agent_id)
    prompt = manager.build_supervisor_prompt(message)

    # 用 DeepSeek 做路由决策
    from app.core.agent.orchestrator import AgentOrchestrator
    orch = AgentOrchestrator()
    provider_config = orch._resolve_provider_config(g.tenant_id)
    llm = orch._build_llm(provider_config)
    response = llm.invoke(prompt)
    content = response.content if hasattr(response, 'content') else str(response)

    # 尝试解析 JSON
    try:
        decision = json.loads(content)
    except json.JSONDecodeError:
        decision = {"worker": None, "reason": content}

    return jsonify({
        "prompt": prompt,
        "decision": decision,
        "available_workers": [w["name"] for w in manager.get_all()],
    }), 200

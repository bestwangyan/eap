from flask import Blueprint, request, jsonify, g

from app.extensions import db
from app.middleware.auth import require_tenant_context, require_permission
from app.models.agent_config import AgentConfig
from app.models.skill_config import SkillConfig
from app.models.mcp_server import MCPServer
from app.models.knowledge import KnowledgeCollection

agent_bp = Blueprint("agent", __name__)


@agent_bp.route("/agents/resources", methods=["GET"])
@require_tenant_context
def list_resources():
    """获取 Agent 可用的资源列表（工具/Skill/MCP/知识库）"""
    tools = [
        {"id": "calculator", "name": "计算器", "description": "安全数学计算"},
        {"id": "datetime", "name": "日期时间", "description": "获取当前日期时间"},
        {"id": "web_search", "name": "网络搜索", "description": "搜索引擎检索"},
        {"id": "code_execution", "name": "代码执行", "description": "沙箱执行代码"},
        {"id": "knowledge_search", "name": "知识库检索", "description": "搜索企业知识库"},
        {"id": "memory_save", "name": "记忆保存", "description": "保存用户全局记忆"},
        {"id": "memory_search", "name": "记忆搜索", "description": "搜索用户历史记忆"},
    ]
    skills = [{"id": s.name, "name": s.name, "description": s.description}
              for s in SkillConfig.query.filter_by(tenant_id=g.tenant_id, is_active=True).all()]
    mcp_servers = [{"id": s.name, "name": s.name, "transport": s.transport, "description": s.description}
                   for s in MCPServer.query.filter_by(tenant_id=g.tenant_id, is_active=True).all()]
    kb_collections = [{"id": c.id, "name": c.name, "description": c.description}
                      for c in KnowledgeCollection.query.filter_by(tenant_id=g.tenant_id).all()]

    # deepagents 默认工具（统一开关：默认全开）
    from app.core.agent.deep_agent_factory import TOOL_DISPLAY_NAMES
    DEEP_DEFAULT_TOOLS = [
        ("write_todos", "任务规划清单"), ("ls", "列出文件"),
        ("read_file", "读取文件"), ("write_file", "写入文件"),
        ("edit_file", "编辑文件"), ("glob", "按模式查找文件"),
        ("grep", "内容搜索"), ("task", "子代理调度"),
    ]
    for tid, tdesc in DEEP_DEFAULT_TOOLS:
        tools.append({
            "id": tid, "name": tid, "description": tdesc,
            "display_name": TOOL_DISPLAY_NAMES.get(tid, tid),
        })

    return jsonify({
        "tools": tools, "skills": skills,
        "mcp_servers": mcp_servers, "knowledge_collections": kb_collections,
    }), 200


@agent_bp.route("/agents", methods=["GET"])
@require_tenant_context
def list_agents():
    """获取 Agent 列表"""
    agents = AgentConfig.query.filter_by(
        tenant_id=g.tenant_id
    ).order_by(AgentConfig.created_at.desc()).all()

    return jsonify({
        "agents": [a.to_dict() for a in agents],
        "total": len(agents),
    }), 200


@agent_bp.route("/agents", methods=["POST"])
@require_permission("agent:create")
def create_agent():
    """创建 Agent"""
    data = request.get_json()
    if not data or "name" not in data:
        return jsonify({"error": "name is required"}), 422

    # 重名检查（租户内唯一），避免 commit 时撞唯一约束返回 500
    if AgentConfig.query.filter_by(
        tenant_id=g.tenant_id, name=data["name"]
    ).first():
        return jsonify({"error": f"Agent '{data['name']}' 已存在"}), 409

    # 执行后端校验（container 为预留值，执行层尚未接入 Docker）
    backend = data.get("backend", "local")
    if backend not in ("local", "container"):
        return jsonify({"error": "backend 必须是 'local' 或 'container'"}), 422

    config = AgentConfig(
        tenant_id=g.tenant_id,
        name=data["name"],
        description=data.get("description", ""),
        model=data.get("model", "claude-sonnet-4-20250514"),
        model_provider_id=data.get("model_provider_id"),
        system_prompt=data.get("system_prompt", ""),
        tools_config=data.get("tools_config", []),
        skills=data.get("skills", []),
        mcp_servers=data.get("mcp_servers", []),
        permission_mode=data.get("permission_mode", "default"),
        backend=backend,
        max_turns=data.get("max_turns", 30),
    )
    db.session.add(config)
    db.session.commit()

    return jsonify({"agent": config.to_dict()}), 201


@agent_bp.route("/agents/<int:agent_id>", methods=["GET"])
@require_permission("agent:read")
def get_agent(agent_id):
    """获取 Agent 详情"""
    config = AgentConfig.query.filter_by(
        id=agent_id, tenant_id=g.tenant_id
    ).first()
    if not config:
        return jsonify({"error": "Agent not found"}), 404
    return jsonify({"agent": config.to_dict()}), 200


@agent_bp.route("/agents/<int:agent_id>", methods=["PUT"])
@require_permission("agent:update")
def update_agent(agent_id):
    """更新 Agent"""
    config = AgentConfig.query.filter_by(
        id=agent_id, tenant_id=g.tenant_id
    ).first()
    if not config:
        return jsonify({"error": "Agent not found"}), 404

    data = request.get_json()
    if "backend" in data and data["backend"] not in ("local", "container"):
        return jsonify({"error": "backend 必须是 'local' 或 'container'"}), 422

    for field in [
        "name", "description", "model", "model_provider_id", "system_prompt",
        "tools_config", "skills", "mcp_servers", "knowledge_collections",
        "permission_mode", "backend", "max_turns", "is_active",
    ]:
        if field in data:
            setattr(config, field, data[field])

    db.session.commit()
    return jsonify({"agent": config.to_dict()}), 200


@agent_bp.route("/agents/<int:agent_id>", methods=["DELETE"])
@require_permission("agent:delete")
def delete_agent(agent_id):
    """删除 Agent"""
    config = AgentConfig.query.filter_by(
        id=agent_id, tenant_id=g.tenant_id
    ).first()
    if not config:
        return jsonify({"error": "Agent not found"}), 404

    # 级联删除该 Agent 下的子 Agent（FK 无 ondelete，需手动清理避免孤儿数据）
    from app.models.sub_agent import SubAgentDefinition
    SubAgentDefinition.query.filter_by(
        tenant_id=g.tenant_id, parent_agent_id=agent_id
    ).delete()

    db.session.delete(config)
    db.session.commit()
    return jsonify({"message": "Agent deleted"}), 200

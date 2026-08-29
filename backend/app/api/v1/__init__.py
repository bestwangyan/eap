from flask import Blueprint

api_v1 = Blueprint("api_v1", __name__)


def register_routes():
    from app.api.v1 import auth, chat, agent, admin, skill, mcp, knowledge, orchestration, workflow, monitor

    api_v1.register_blueprint(auth.auth_bp)
    api_v1.register_blueprint(chat.chat_bp)
    api_v1.register_blueprint(agent.agent_bp)
    api_v1.register_blueprint(admin.admin_bp)
    api_v1.register_blueprint(skill.skill_bp)
    api_v1.register_blueprint(mcp.mcp_bp)
    api_v1.register_blueprint(knowledge.knowledge_bp)
    api_v1.register_blueprint(orchestration.orch_bp)
    api_v1.register_blueprint(workflow.wf_bp)
    api_v1.register_blueprint(monitor.mon_bp)

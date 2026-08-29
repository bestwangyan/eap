from app.extensions import db
from app.models.base import BaseModel


class AgentConfig(BaseModel):
    """Agent 配置"""
    __tablename__ = "agent_configs"

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(
        db.Integer, db.ForeignKey("tenants.id"), nullable=False, index=True
    )
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    # 兼容旧字段（展示用）；真正生效的是 model_provider_id（绑定的模型供应商）
    model = db.Column(db.String(100), default="claude-sonnet-4-20250514")
    model_provider_id = db.Column(
        db.Integer, db.ForeignKey("model_providers.id")
    )  # 绑定的模型供应商，为空时回退聊天页选择/租户默认
    system_prompt = db.Column(db.Text)
    tools_config = db.Column(db.JSON, default=list)
    skills = db.Column(db.JSON, default=list)
    mcp_servers = db.Column(db.JSON, default=list)
    knowledge_collections = db.Column(db.JSON, default=list)
    permission_mode = db.Column(
        db.String(20), default="default"
    )  # default | acceptEdits | dontAsk
    backend = db.Column(
        db.String(20), default="local"
    )  # 执行后端: local | container（容器沙箱，预留）
    max_turns = db.Column(db.Integer, default=30)
    is_active = db.Column(db.Boolean, default=True)

    # 关系
    tenant = db.relationship("Tenant", back_populates="agent_configs")

    __table_args__ = (
        db.UniqueConstraint("tenant_id", "name", name="uq_agent_tenant_name"),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "tenant_id": self.tenant_id,
            "name": self.name,
            "description": self.description,
            "model": self.model,
            "model_provider_id": self.model_provider_id,
            "system_prompt": self.system_prompt,
            "tools_config": self.tools_config,
            "skills": self.skills,
            "mcp_servers": self.mcp_servers,
            "knowledge_collections": self.knowledge_collections,
            "permission_mode": self.permission_mode,
            "backend": self.backend or "local",
            "max_turns": self.max_turns,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

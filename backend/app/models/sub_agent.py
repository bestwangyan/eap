"""Phase 3: 子 Agent 定义模型"""
from app.extensions import db
from app.models.base import BaseModel


class SubAgentDefinition(BaseModel):
    __tablename__ = "sub_agent_definitions"

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey("tenants.id"), nullable=False, index=True)
    parent_agent_id = db.Column(db.Integer, db.ForeignKey("agent_configs.id"), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    role_prompt = db.Column(db.Text, nullable=False)
    tools = db.Column(db.JSON, default=list)
    model = db.Column(db.String(100))
    model_provider_id = db.Column(
        db.Integer, db.ForeignKey("model_providers.id")
    )  # 子代理独立模型后端，为空时继承主代理
    mode = db.Column(db.String(20), default="inline")  # inline | compiled | async
    is_active = db.Column(db.Boolean, default=True)

    __table_args__ = (
        db.UniqueConstraint("parent_agent_id", "name", name="uq_sub_agent_name"),
    )

    def to_dict(self):
        return {
            "id": self.id, "tenant_id": self.tenant_id,
            "parent_agent_id": self.parent_agent_id,
            "name": self.name, "role_prompt": self.role_prompt,
            "tools": self.tools, "model": self.model,
            "model_provider_id": self.model_provider_id,
            "mode": self.mode, "is_active": self.is_active,
        }

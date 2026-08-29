"""Chat thread model - stores thread metadata for sidebar listing"""
from app.extensions import db
from app.models.base import BaseModel


class ChatThread(BaseModel):
    __tablename__ = "chat_threads"

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey("tenants.id"), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    thread_id = db.Column(db.String(255), unique=True, nullable=False, index=True)
    agent_id = db.Column(db.Integer, db.ForeignKey("agent_configs.id"), nullable=True)
    title = db.Column(db.String(500), default="新对话")
    model_provider_id = db.Column(db.Integer, nullable=True)
    message_count = db.Column(db.Integer, default=0)
    is_active = db.Column(db.Boolean, default=True)

    def to_dict(self):
        return {
            "id": self.id,
            "thread_id": self.thread_id,
            "agent_id": self.agent_id,
            "agent_name": None,
            "title": self.title,
            "model_provider_id": self.model_provider_id,
            "message_count": self.message_count,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

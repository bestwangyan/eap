"""Chat message persistence - stores each message in PostgreSQL"""
from app.extensions import db
from app.models.base import BaseModel


class ChatMessage(BaseModel):
    __tablename__ = "chat_messages"

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey("tenants.id"), nullable=False, index=True)
    thread_id = db.Column(db.String(255), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    role = db.Column(db.String(20), nullable=False)
    content = db.Column(db.Text)
    metadata_json = db.Column(db.JSON, default=dict)

    def to_dict(self):
        return {
            "role": self.role,
            "content": self.content,
            "metadata": self.metadata_json,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

"""User global memory — persists across chat threads"""
from app.extensions import db
from app.models.base import BaseModel


class UserMemory(BaseModel):
    """用户级别的记忆条目，跨线程共享"""
    __tablename__ = "user_memories"

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey("tenants.id"), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    key = db.Column(db.String(200), nullable=False)   # 记忆主题（简短标识）
    content = db.Column(db.Text, nullable=False)       # 记忆内容
    category = db.Column(db.String(50), default="fact")  # preference / fact / context / identity
    importance = db.Column(db.Integer, default=5)      # 1-10, 越高越重要
    source_thread_id = db.Column(db.String(255))       # 来源线程（溯源）

    def to_dict(self):
        return {
            "id": self.id,
            "key": self.key,
            "content": self.content,
            "category": self.category,
            "importance": self.importance,
            "source_thread_id": self.source_thread_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

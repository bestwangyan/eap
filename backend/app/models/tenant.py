from app.extensions import db
from app.models.base import BaseModel


class Tenant(BaseModel):
    """租户（企业/组织）"""
    __tablename__ = "tenants"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    slug = db.Column(db.String(50), unique=True, nullable=False, index=True)
    is_active = db.Column(db.Boolean, default=True)

    # 关系
    users = db.relationship("User", back_populates="tenant", lazy="dynamic")
    agent_configs = db.relationship(
        "AgentConfig", back_populates="tenant", lazy="dynamic"
    )

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "slug": self.slug,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

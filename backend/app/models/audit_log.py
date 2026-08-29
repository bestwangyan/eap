from app.extensions import db
from app.models.base import BaseModel


class AuditLog(BaseModel):
    """审计日志"""
    __tablename__ = "audit_logs"

    id = db.Column(db.Integer, primary_key=True)
    tenant_slug = db.Column(
        db.String(50), nullable=False, index=True
    )
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=True
    )
    action = db.Column(db.String(100), nullable=False, index=True)
    resource = db.Column(db.String(200), nullable=False)
    resource_id = db.Column(db.String(100))
    detail = db.Column(db.JSON, default=dict)
    ip_address = db.Column(db.String(45))
    user_agent = db.Column(db.String(500))
    status = db.Column(db.String(20), default="success")

    @classmethod
    def log(
        cls,
        tenant_slug: str,
        user_id: int | None,
        action: str,
        resource: str,
        resource_id: str | None = None,
        detail: dict | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
        status: str = "success",
    ):
        entry = cls(
            tenant_slug=tenant_slug,
            user_id=user_id,
            action=action,
            resource=resource,
            resource_id=resource_id,
            detail=detail or {},
            ip_address=ip_address,
            user_agent=user_agent,
            status=status,
        )
        db.session.add(entry)
        db.session.commit()
        return entry

    def to_dict(self):
        return {
            "id": self.id,
            "tenant_slug": self.tenant_slug,
            "user_id": self.user_id,
            "action": self.action,
            "resource": self.resource,
            "resource_id": self.resource_id,
            "detail": self.detail,
            "ip_address": self.ip_address,
            "status": self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

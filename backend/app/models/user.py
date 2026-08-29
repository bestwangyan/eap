import uuid
from werkzeug.security import generate_password_hash, check_password_hash
from app.extensions import db
from app.models.base import BaseModel
from app.models.role import user_roles


class User(BaseModel):
    """用户"""
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(
        db.Integer, db.ForeignKey("tenants.id"), nullable=False, index=True
    )
    username = db.Column(db.String(80), nullable=False)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    last_login_at = db.Column(db.DateTime)

    # 关系
    tenant = db.relationship("Tenant", back_populates="users")
    roles = db.relationship(
        "Role", secondary=user_roles, back_populates="users", lazy="joined"
    )

    def set_password(self, password: str):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)

    @property
    def all_permissions(self) -> list[str]:
        """汇总所有角色的权限"""
        permissions = set()
        for role in self.roles:
            for perm in role.permissions:
                permissions.add(perm.codename)
        return sorted(permissions)

    @property
    def role_names(self) -> list[str]:
        return [r.name for r in self.roles]

    def has_permission(self, codename: str) -> bool:
        """检查是否拥有指定权限"""
        return (
            "*:*" in self.all_permissions
            or codename in self.all_permissions
        )

    def to_dict(self, include_roles=True):
        result = {
            "id": self.id,
            "tenant_id": self.tenant_id,
            "tenant_slug": self.tenant.slug if self.tenant else None,
            "username": self.username,
            "email": self.email,
            "is_active": self.is_active,
            "last_login_at": (
                self.last_login_at.isoformat() if self.last_login_at else None
            ),
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
        if include_roles:
            result["roles"] = [
                {"id": r.id, "name": r.name, "is_system": r.is_system}
                for r in self.roles
            ]
            result["permissions"] = self.all_permissions
        return result

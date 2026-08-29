from app.extensions import db
from app.models.base import BaseModel


# 关联表
user_roles = db.Table(
    "user_roles",
    db.Column("user_id", db.Integer, db.ForeignKey("users.id"), primary_key=True),
    db.Column("role_id", db.Integer, db.ForeignKey("roles.id"), primary_key=True),
)

role_permissions = db.Table(
    "role_permissions",
    db.Column(
        "role_id", db.Integer, db.ForeignKey("roles.id"), primary_key=True
    ),
    db.Column(
        "permission_id",
        db.Integer,
        db.ForeignKey("permissions.id"),
        primary_key=True,
    ),
)


class Role(BaseModel):
    """角色"""
    __tablename__ = "roles"

    id = db.Column(db.Integer, primary_key=True)
    # 系统级角色 tenant_id 为 NULL，租户级角色绑定 tenant_id
    tenant_id = db.Column(db.Integer, db.ForeignKey("tenants.id"), nullable=True)
    name = db.Column(db.String(80), nullable=False)
    description = db.Column(db.String(255))
    is_system = db.Column(db.Boolean, default=False)

    # 关系
    users = db.relationship(
        "User", secondary=user_roles, back_populates="roles"
    )
    permissions = db.relationship(
        "Permission",
        secondary=role_permissions,
        back_populates="roles",
        lazy="joined",
    )

    __table_args__ = (
        db.UniqueConstraint("tenant_id", "name", name="uq_role_tenant_name"),
    )

    # 预置角色定义 (系统级, tenant_id=NULL)
    PRESET_ROLES = [
        {
            "name": "SuperAdmin",
            "description": "超级管理员",
            "is_system": True,
            "permissions": ["*:*"],
        },
        {
            "name": "TenantAdmin",
            "description": "租户管理员",
            "is_system": True,
            "permissions": [
                "user:*", "agent:*", "knowledge:*",
                "skill:*", "mcp:*", "admin:audit",
                "admin:settings", "approval:approve",
            ],
        },
        {
            "name": "Developer",
            "description": "开发者",
            "is_system": True,
            "permissions": [
                "agent:create", "agent:update", "agent:execute",
                "agent:read", "knowledge:*", "skill:*",
                "mcp:*",
            ],
        },
        {
            "name": "Viewer",
            "description": "查看者",
            "is_system": True,
            "permissions": [
                "agent:read", "agent:execute", "knowledge:read",
                "skill:read", "mcp:read",
            ],
        },
    ]

    @classmethod
    def seed_presets(cls):
        """初始化预置角色"""
        from app.extensions import db
        from app.models.permission import Permission

        for role_def in cls.PRESET_ROLES:
            existing = cls.query.filter_by(
                name=role_def["name"], tenant_id=None
            ).first()
            if existing:
                continue

            role = cls(
                name=role_def["name"],
                description=role_def["description"],
                is_system=role_def["is_system"],
            )
            # 绑定权限
            for perm_codename in role_def["permissions"]:
                if perm_codename.endswith(":*"):
                    # 通配符：匹配所有该 resource 的权限
                    resource = perm_codename.split(":")[0]
                    perms = Permission.query.filter_by(resource=resource).all()
                    role.permissions.extend(perms)
                else:
                    perm = Permission.query.filter_by(
                        codename=perm_codename
                    ).first()
                    if perm:
                        role.permissions.append(perm)

            db.session.add(role)
        db.session.commit()

    def to_dict(self, include_permissions=True):
        result = {
            "id": self.id,
            "tenant_id": self.tenant_id,
            "name": self.name,
            "description": self.description,
            "is_system": self.is_system,
        }
        if include_permissions:
            result["permissions"] = [p.to_dict() for p in self.permissions]
        return result

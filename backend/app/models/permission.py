from app.extensions import db
from app.models.base import BaseModel


class Permission(BaseModel):
    """权限点"""
    __tablename__ = "permissions"

    id = db.Column(db.Integer, primary_key=True)
    resource = db.Column(db.String(100), nullable=False)
    action = db.Column(db.String(50), nullable=False)
    codename = db.Column(
        db.String(200), unique=True, nullable=False, index=True
    )
    description = db.Column(db.String(255))

    # 关系
    roles = db.relationship(
        "Role",
        secondary="role_permissions",
        back_populates="permissions",
    )

    # 预置权限点
    PRESET_PERMISSIONS = [
        # 超级权限
        ("*", "*", "*:*", "超级管理员权限"),
        # 用户管理
        ("user", "create", "user:create", "创建用户"),
        ("user", "read", "user:read", "查看用户"),
        ("user", "update", "user:update", "更新用户"),
        ("user", "delete", "user:delete", "删除用户"),
        # Agent
        ("agent", "create", "agent:create", "创建 Agent"),
        ("agent", "read", "agent:read", "查看 Agent"),
        ("agent", "update", "agent:update", "更新 Agent"),
        ("agent", "delete", "agent:delete", "删除 Agent"),
        ("agent", "execute", "agent:execute", "执行 Agent"),
        # 知识库
        ("knowledge", "create", "knowledge:create", "创建知识库"),
        ("knowledge", "read", "knowledge:read", "查看知识库"),
        ("knowledge", "update", "knowledge:update", "更新知识库"),
        ("knowledge", "delete", "knowledge:delete", "删除知识库"),
        # Skill
        ("skill", "read", "skill:read", "查看 Skill"),
        ("skill", "manage", "skill:manage", "管理 Skill"),
        # MCP
        ("mcp", "read", "mcp:read", "查看 MCP"),
        ("mcp", "manage", "mcp:manage", "管理 MCP"),
        # 管理后台
        ("admin", "access", "admin:access", "访问管理后台"),
        ("admin", "audit", "admin:audit", "查看审计日志"),
        ("admin", "settings", "admin:settings", "系统设置"),
        # 审批
        ("approval", "approve", "approval:approve", "审批操作"),
    ]

    @classmethod
    def seed_presets(cls):
        """初始化预置权限点"""
        from app.extensions import db
        for resource, action, codename, desc in cls.PRESET_PERMISSIONS:
            if not cls.query.filter_by(codename=codename).first():
                db.session.add(cls(
                    resource=resource,
                    action=action,
                    codename=codename,
                    description=desc,
                ))
        db.session.commit()

    def to_dict(self):
        return {
            "id": self.id,
            "resource": self.resource,
            "action": self.action,
            "codename": self.codename,
            "description": self.description,
        }

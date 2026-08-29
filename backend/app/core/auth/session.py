import json
from datetime import datetime
from flask import current_app
from app.extensions import redis_client, db
from app.models.user import User


class SessionManager:
    """Redis 会话生命周期管理

    Key 结构: session:{user_id}:{jti}
    TTL: 与 JWT access_token 过期时间一致
    """

    def __init__(self):
        self.redis = redis_client

    def create_session(self, user: User, jti: str, ttl: int) -> dict:
        """登录时创建 Redis Session"""
        session_data = {
            "user_id": str(user.id),
            "tenant_slug": user.tenant.slug if user.tenant else None,
            "tenant_name": user.tenant.name if user.tenant else None,
            "tenant_id": str(user.tenant_id),
            "username": user.username,
            "email": user.email,
            "roles": user.role_names,
            "permissions": user.all_permissions,
            "login_at": datetime.utcnow().isoformat(),
        }
        key = f"session:{user.id}:{jti}"
        self.redis.setex(key, ttl, json.dumps(session_data, ensure_ascii=False))
        return session_data

    def get_session(self, user_id: str, jti: str) -> dict | None:
        """从 Redis 读取会话"""
        cached = self.redis.get(f"session:{user_id}:{jti}")
        if cached:
            return json.loads(cached)
        return None

    def destroy_session(self, user_id: str, jti: str):
        """登出时销毁单个 Session"""
        self.redis.delete(f"session:{user_id}:{jti}")

    def destroy_all_user_sessions(self, user_id: str):
        """强制下线某用户所有会话"""
        pattern = f"session:{user_id}:*"
        keys = self.redis.keys(pattern)
        if keys:
            self.redis.delete(*keys)

    def refresh_session(
        self, user_id: str, old_jti: str, new_jti: str, ttl: int
    ) -> dict | None:
        """刷新 Token 时迁移 Session"""
        old_key = f"session:{user_id}:{old_jti}"
        cached = self.redis.get(old_key)
        if not cached:
            return None

        session_data = json.loads(cached)
        self.redis.delete(old_key)

        new_key = f"session:{user_id}:{new_jti}"
        self.redis.setex(new_key, ttl, json.dumps(session_data, ensure_ascii=False))
        return session_data

    def update_user_permissions(self, user_id: str):
        """权限变更后刷新该用户所有活跃 Session"""
        user = db.session.get(User, int(user_id))
        if not user:
            return

        new_roles = user.role_names
        new_permissions = user.all_permissions

        pattern = f"session:{user_id}:*"
        for key in self.redis.keys(pattern):
            session_data = json.loads(self.redis.get(key))
            session_data["roles"] = new_roles
            session_data["permissions"] = new_permissions
            ttl = self.redis.ttl(key)
            if ttl > 0:
                self.redis.setex(
                    key, ttl, json.dumps(session_data, ensure_ascii=False)
                )

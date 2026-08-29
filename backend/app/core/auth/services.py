import uuid
from datetime import datetime
from flask import current_app, abort
from flask_jwt_extended import (
    create_access_token,
    create_refresh_token,
    decode_token,
)
from app.extensions import db
from app.models.user import User
from app.models.audit_log import AuditLog
from app.core.auth.session import SessionManager


class AuthService:
    """认证服务"""

    def __init__(self):
        self.session_manager = SessionManager()

    def login(self, email: str, password: str, ip_address: str = None) -> dict:
        """登录"""
        user = User.query.filter_by(email=email).first()
        if not user or not user.check_password(password):
            AuditLog.log(
                tenant_slug="unknown",
                user_id=None,
                action="user:login_failed",
                resource="auth",
                detail={"email": email},
                ip_address=ip_address,
                status="failure",
            )
            abort(401, description="邮箱或密码错误")

        if not user.is_active:
            abort(403, description="账户已被禁用，请联系管理员")

        # 生成唯一 jti
        jti = str(uuid.uuid4())
        access_ttl = current_app.config["JWT_ACCESS_TOKEN_EXPIRES"]

        # 创建 JWT（仅含 sub + jti）
        access_token = create_access_token(
            identity=str(user.id),
            additional_claims={"jti": jti},
        )
        refresh_token = create_refresh_token(
            identity=str(user.id),
            additional_claims={"jti": jti},
        )

        # 写入 Redis Session
        session_data = self.session_manager.create_session(
            user=user, jti=jti, ttl=access_ttl
        )

        # 更新登录时间
        user.last_login_at = datetime.utcnow()
        db.session.commit()

        # 审计日志
        AuditLog.log(
            tenant_slug=user.tenant.slug,
            user_id=user.id,
            action="user:login",
            resource="auth",
            ip_address=ip_address,
        )

        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
            "user": {
                "id": user.id,
                "username": user.username,
                "email": user.email,
                "tenant": session_data["tenant_slug"],
                "tenant_name": session_data.get("tenant_name"),
                "roles": session_data["roles"],
                "permissions": session_data["permissions"],
            },
        }

    def refresh_token(self, refresh_token_value: str) -> dict:
        """刷新 Token"""
        try:
            claims = decode_token(refresh_token_value)
        except Exception:
            abort(401, description="无效的 refresh_token")

        user_id = claims["sub"]
        old_jti = claims["jti"]

        # 生成新 jti，迁移 Redis Session
        new_jti = str(uuid.uuid4())
        access_ttl = current_app.config["JWT_ACCESS_TOKEN_EXPIRES"]

        session_data = self.session_manager.refresh_session(
            user_id, old_jti, new_jti, access_ttl
        )
        if not session_data:
            abort(401, description="会话已过期，请重新登录")

        new_access_token = create_access_token(
            identity=user_id,
            additional_claims={"jti": new_jti},
        )

        return {
            "access_token": new_access_token,
            "token_type": "bearer",
            "user": {
                "id": int(user_id),
                "username": session_data["username"],
                "email": session_data.get("email"),
                "tenant": session_data["tenant_slug"],
                "tenant_name": session_data.get("tenant_name"),
                "roles": session_data["roles"],
                "permissions": session_data["permissions"],
            },
        }

    def logout(self, user_id: str, jti: str):
        """登出"""
        self.session_manager.destroy_session(user_id, jti)
        AuditLog.log(
            tenant_slug="",  # 由调用方通过 g 对象传入
            user_id=int(user_id) if user_id.isdigit() else None,
            action="user:logout",
            resource="auth",
        )

    def get_current_user_info(self, user_id: str, jti: str) -> dict:
        """获取当前用户信息（从 Redis 读取）"""
        session_data = self.session_manager.get_session(user_id, jti)
        if not session_data:
            abort(401, description="会话已过期")

        return {
            "id": int(user_id),
            "username": session_data["username"],
            "email": session_data.get("email"),
            "tenant": session_data["tenant_slug"],
            "tenant_name": session_data.get("tenant_name"),
            "roles": session_data["roles"],
            "permissions": session_data["permissions"],
            "login_at": session_data.get("login_at"),
        }

import json
from functools import wraps
from flask import g, abort, current_app, request
from flask_jwt_extended import verify_jwt_in_request, get_jwt


# ============ JWT 验证 + Redis Session 加载 ============

def load_user_context():
    """从 JWT 验证身份，从 Redis 加载完整用户上下文并注入 Flask g 对象"""
    verify_jwt_in_request()
    claims = get_jwt()
    user_id = claims["sub"]
    jti = claims.get("jti")

    if not jti:
        abort(401, description="Invalid token: missing jti")

    # 从 Redis 读取会话上下文
    redis_client = current_app.extensions["redis_client"]
    session_key = f"session:{user_id}:{jti}"
    cached = redis_client.get(session_key)

    if not cached:
        abort(401, description="会话已过期或已被强制下线，请重新登录")

    session_data = json.loads(cached)

    # 注入 Flask g 对象
    g.user_id = session_data["user_id"]
    g.tenant_slug = session_data["tenant_slug"]
    g.tenant_id = session_data.get("tenant_id")
    g.tenant_name = session_data.get("tenant_name")
    g.username = session_data["username"]
    g.email = session_data.get("email")
    g.roles = session_data.get("roles", [])
    g.permissions = session_data.get("permissions", [])
    g.session_jti = jti

    # 记录审计用的 IP 和 UA
    g.request_ip = request.headers.get(
        "X-Forwarded-For", request.remote_addr
    )
    g.request_ua = request.headers.get("User-Agent", "")


# ============ RBAC 权限拦截 ============

def require_permission(permission_codename: str):
    """检查当前用户是否拥有指定权限（从 Redis Session 读取）"""
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            load_user_context()
            if "*:*" in g.permissions or permission_codename in g.permissions:
                return fn(*args, **kwargs)
            abort(403, description=f"权限不足，需要: {permission_codename}")
        return wrapper
    return decorator


def require_tenant_context(fn=None):
    """加载租户上下文（仅验证身份，不做权限检查），可用作装饰器"""
    if fn is None:
        # 被用作 @require_tenant_context() 带括号调用
        def decorator(fn):
            @wraps(fn)
            def wrapper(*args, **kwargs):
                load_user_context()
                return fn(*args, **kwargs)
            return wrapper
        return decorator

    # 被用作 @require_tenant_context 不带括号
    @wraps(fn)
    def wrapper(*args, **kwargs):
        load_user_context()
        return fn(*args, **kwargs)
    return wrapper

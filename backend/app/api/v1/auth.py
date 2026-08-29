from flask import Blueprint, request, jsonify, g
from pydantic import BaseModel, EmailStr, Field, ValidationError

from app.core.auth.services import AuthService
from app.middleware.auth import load_user_context

auth_bp = Blueprint("auth", __name__)


# ============ 请求模型 ============

class LoginRequest(BaseModel):
    email: str = Field(..., min_length=1, description="邮箱")
    password: str = Field(..., min_length=6, description="密码")


class RegisterRequest(BaseModel):
    email: str
    username: str = Field(..., min_length=2, max_length=80)
    password: str = Field(..., min_length=6)
    tenant_name: str = Field(..., min_length=1, max_length=200)


# ============ 工具函数 ============

def _get_ip() -> str:
    return request.headers.get("X-Forwarded-For", request.remote_addr) or ""


# ============ API 端点 ============

@auth_bp.route("/auth/login", methods=["POST"])
def login():
    """用户登录"""
    try:
        body = LoginRequest(**request.get_json())
    except ValidationError as e:
        return jsonify({"error": "请求参数错误", "details": e.errors()}), 422

    service = AuthService()
    result = service.login(body.email, body.password, ip_address=_get_ip())
    return jsonify(result), 200


@auth_bp.route("/auth/register", methods=["POST"])
def register():
    """用户注册（创建租户 + 管理员用户）"""
    try:
        body = RegisterRequest(**request.get_json())
    except ValidationError as e:
        return jsonify({"error": "请求参数错误", "details": e.errors()}), 422

    from app.extensions import db
    from app.models.tenant import Tenant
    from app.models.user import User
    from app.models.role import Role

    # 检查邮箱是否已存在
    if User.query.filter_by(email=body.email).first():
        return jsonify({"error": "该邮箱已注册"}), 409

    # 创建租户
    import re
    slug = re.sub(r"[^a-z0-9-]", "", body.tenant_name.lower().replace(" ", "-"))
    if Tenant.query.filter_by(slug=slug).first():
        slug = f"{slug}-{body.username}"

    tenant = Tenant(name=body.tenant_name, slug=slug)
    db.session.add(tenant)
    db.session.flush()

    # 创建用户（作为租户管理员）
    user = User(
        tenant_id=tenant.id,
        username=body.username,
        email=body.email,
        is_active=True,
    )
    user.set_password(body.password)
    db.session.add(user)
    db.session.flush()

    # 分配 TenantAdmin 角色
    tenant_admin = Role.query.filter_by(name="TenantAdmin", tenant_id=None).first()
    if tenant_admin:
        # 复制系统角色为租户角色
        custom_role = Role(
            tenant_id=tenant.id,
            name="TenantAdmin",
            description="租户管理员",
            is_system=False,
        )
        custom_role.permissions = tenant_admin.permissions
        db.session.add(custom_role)
        db.session.flush()
        user.roles.append(custom_role)
    else:
        # 如果没有预置角色，创建默认权限
        from app.models.permission import Permission
        for perm in Permission.query.filter_by(resource="*").all():
            user.roles.append(perm)

    db.session.commit()

    return jsonify({
        "message": "注册成功，请登录",
        "tenant": tenant.to_dict(),
        "user": user.to_dict(),
    }), 201


@auth_bp.route("/auth/refresh", methods=["POST"])
def refresh():
    """刷新 Token"""
    data = request.get_json()
    refresh_token = data.get("refresh_token")
    if not refresh_token:
        return jsonify({"error": "refresh_token is required"}), 422

    service = AuthService()
    result = service.refresh_token(refresh_token)
    return jsonify(result), 200


@auth_bp.route("/auth/logout", methods=["POST"])
def logout():
    """登出"""
    from flask_jwt_extended import verify_jwt_in_request, get_jwt
    try:
        verify_jwt_in_request()
        claims = get_jwt()
        service = AuthService()
        service.logout(claims["sub"], claims.get("jti", ""))
    except Exception:
        pass  # Token 已失效也正常返回
    return jsonify({"message": "已登出"}), 200


@auth_bp.route("/auth/me", methods=["GET"])
def me():
    """获取当前用户信息"""
    load_user_context()
    return jsonify({
        "id": int(g.user_id),
        "username": g.username,
        "email": g.email,
        "tenant": g.tenant_slug,
        "tenant_name": g.tenant_name,
        "roles": g.roles,
        "permissions": g.permissions,
    }), 200

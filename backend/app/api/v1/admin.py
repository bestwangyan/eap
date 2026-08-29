from flask import Blueprint, request, jsonify, g

from app.extensions import db
from app.middleware.auth import require_tenant_context, require_permission, load_user_context
from app.models.user import User
from app.models.role import Role
from app.models.audit_log import AuditLog
from app.models.model_provider import ModelProvider
from app.core.auth.session import SessionManager

admin_bp = Blueprint("admin", __name__)


# ============ 用户管理 ============

@admin_bp.route("/admin/users", methods=["GET"])
@require_permission("user:read")
def list_users():
    """用户列表"""
    users = User.query.filter_by(tenant_id=g.tenant_id).all()
    return jsonify({"users": [u.to_dict() for u in users]}), 200


@admin_bp.route("/admin/users", methods=["POST"])
@require_permission("user:create")
def create_user():
    """创建用户"""
    data = request.get_json()
    if not data or "email" not in data or "password" not in data:
        return jsonify({"error": "email and password are required"}), 422

    if User.query.filter_by(email=data["email"]).first():
        return jsonify({"error": "邮箱已存在"}), 409

    user = User(
        tenant_id=g.tenant_id,
        username=data.get("username", data["email"].split("@")[0]),
        email=data["email"],
        is_active=data.get("is_active", True),
    )
    user.set_password(data["password"])

    # 分配角色
    if "role_ids" in data:
        roles = Role.query.filter(
            Role.id.in_(data["role_ids"]),
            (Role.tenant_id == g.tenant_id) | (Role.tenant_id.is_(None)),
        ).all()
        user.roles = roles
    else:
        # 默认分配 Viewer 角色
        viewer = Role.query.filter_by(name="Viewer", tenant_id=None).first()
        if viewer:
            user.roles.append(viewer)

    db.session.add(user)
    db.session.commit()

    AuditLog.log(
        tenant_slug=g.tenant_slug,
        user_id=int(g.user_id),
        action="admin:user_create",
        resource="user",
        resource_id=str(user.id),
        detail={"new_user_email": data["email"]},
    )

    return jsonify({"user": user.to_dict()}), 201


@admin_bp.route("/admin/users/<int:user_id>", methods=["PUT"])
@require_permission("user:update")
def update_user(user_id):
    """更新用户"""
    user = User.query.filter_by(id=user_id, tenant_id=g.tenant_id).first()
    if not user:
        return jsonify({"error": "User not found"}), 404

    data = request.get_json()
    for field in ["username", "email", "is_active"]:
        if field in data:
            setattr(user, field, data[field])

    if "password" in data:
        user.set_password(data["password"])

    if "role_ids" in data:
        roles = Role.query.filter(
            Role.id.in_(data["role_ids"]),
            (Role.tenant_id == g.tenant_id) | (Role.tenant_id.is_(None)),
        ).all()
        user.roles = roles

    db.session.commit()

    # 更新该用户的 Redis Sessions（权限即时生效）
    SessionManager().update_user_permissions(str(user.id))

    return jsonify({"user": user.to_dict()}), 200


@admin_bp.route("/admin/users/<int:user_id>", methods=["DELETE"])
@require_permission("user:delete")
def delete_user(user_id):
    """删除用户"""
    user = User.query.filter_by(id=user_id, tenant_id=g.tenant_id).first()
    if not user:
        return jsonify({"error": "User not found"}), 404

    # 强制下线
    SessionManager().destroy_all_user_sessions(str(user.id))

    db.session.delete(user)
    db.session.commit()
    return jsonify({"message": "User deleted"}), 200


# ============ 角色管理 ============

@admin_bp.route("/admin/roles", methods=["GET"])
@require_permission("user:read")
def list_roles():
    """角色列表（含系统级角色）"""
    roles = Role.query.filter(
        (Role.tenant_id == g.tenant_id) | (Role.tenant_id.is_(None))
    ).all()
    return jsonify({"roles": [r.to_dict() for r in roles]}), 200


@admin_bp.route("/admin/roles", methods=["POST"])
@require_permission("user:update")
def create_role():
    """创建自定义角色"""
    data = request.get_json()
    role = Role(
        tenant_id=g.tenant_id,
        name=data["name"],
        description=data.get("description", ""),
        is_system=False,
    )
    if "permission_ids" in data:
        from app.models.permission import Permission
        perms = Permission.query.filter(
            Permission.id.in_(data["permission_ids"])
        ).all()
        role.permissions = perms

    db.session.add(role)
    db.session.commit()
    return jsonify({"role": role.to_dict()}), 201


# ============ 审计日志 ============

@admin_bp.route("/admin/audit-logs", methods=["GET"])
@require_permission("admin:audit")
def list_audit_logs():
    """审计日志列表（分页）"""
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 50, type=int)

    query = AuditLog.query.filter_by(tenant_slug=g.tenant_slug)
    if action_filter := request.args.get("action"):
        query = query.filter_by(action=action_filter)
    if user_filter := request.args.get("user_id"):
        query = query.filter_by(user_id=int(user_filter))

    pagination = query.order_by(AuditLog.created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )

    return jsonify({
        "logs": [log.to_dict() for log in pagination.items],
        "total": pagination.total,
        "page": page,
        "per_page": per_page,
        "pages": pagination.pages,
    }), 200


# ============ 模型供应商管理 ============

@admin_bp.route("/admin/models", methods=["GET"])
@require_permission("admin:settings")
def list_model_providers():
    """模型供应商列表"""
    models = ModelProvider.query.filter_by(
        tenant_id=g.tenant_id
    ).order_by(ModelProvider.sort_order).all()
    return jsonify({
        "models": [m.to_dict(include_key=True) for m in models],
    }), 200


@admin_bp.route("/admin/models", methods=["POST"])
@require_permission("admin:settings")
def create_model_provider():
    """创建模型供应商配置"""
    data = request.get_json()
    if not data or "name" not in data or "api_key" not in data or "model_name" not in data:
        return jsonify({"error": "name, api_key, model_name are required"}), 422

    # 拒绝脱敏形式的 Key（列表接口展示的是脱敏串，禁止将其当作真实 Key 提交）
    if isinstance(data.get("api_key"), str) and "****" in data["api_key"]:
        return jsonify({"error": "API Key 不能是脱敏形式，请输入完整的真实密钥"}), 422

    # 如果设为默认，先取消其他默认
    if data.get("is_default"):
        ModelProvider.query.filter_by(
            tenant_id=g.tenant_id, is_default=True
        ).update({"is_default": False})

    provider = ModelProvider(
        tenant_id=g.tenant_id,
        name=data["name"],
        provider=data.get("provider", "anthropic"),
        api_key=data["api_key"],
        api_base=data.get("api_base", ""),
        model_name=data["model_name"],
        description=data.get("description", ""),
        is_active=data.get("is_active", True),
        is_default=data.get("is_default", False),
        sort_order=data.get("sort_order", 0),
    )
    db.session.add(provider)
    db.session.commit()

    AuditLog.log(
        tenant_slug=g.tenant_slug,
        user_id=int(g.user_id),
        action="admin:model_create",
        resource="model_provider",
        resource_id=str(provider.id),
        detail={"name": provider.name, "provider": provider.provider, "model_name": provider.model_name},
    )

    return jsonify({"model": provider.to_dict(include_key=True)}), 201


@admin_bp.route("/admin/models/<int:model_id>", methods=["PUT"])
@require_permission("admin:settings")
def update_model_provider(model_id):
    """更新模型供应商配置"""
    provider = ModelProvider.query.filter_by(
        id=model_id, tenant_id=g.tenant_id
    ).first()
    if not provider:
        return jsonify({"error": "Model not found"}), 404

    data = request.get_json()

    # 如果设为默认，先取消其他默认
    if data.get("is_default") and not provider.is_default:
        ModelProvider.query.filter_by(
            tenant_id=g.tenant_id, is_default=True
        ).update({"is_default": False})

    for field in [
        "name", "provider", "api_key", "api_base", "model_name",
        "description", "is_active", "is_default", "sort_order",
    ]:
        if field in data:
            # 防呆：api_key 为脱敏形式（含 ****）或空串时跳过，保留数据库中的真实 Key
            # （前端编辑表单会回传脱敏展示值，直接写入会把真实 Key 覆盖掉，
            #   导致后续对话 401 "api key is invalid"）
            if field == "api_key":
                value = data[field]
                if not isinstance(value, str) or not value.strip() or "****" in value:
                    continue
                setattr(provider, field, value)
                continue
            setattr(provider, field, data[field])

    db.session.commit()
    return jsonify({"model": provider.to_dict(include_key=True)}), 200


@admin_bp.route("/admin/models/<int:model_id>", methods=["DELETE"])
@require_permission("admin:settings")
def delete_model_provider(model_id):
    """删除模型供应商"""
    provider = ModelProvider.query.filter_by(
        id=model_id, tenant_id=g.tenant_id
    ).first()
    if not provider:
        return jsonify({"error": "Model not found"}), 404

    db.session.delete(provider)
    db.session.commit()
    return jsonify({"message": "Model deleted"}), 200


# ============ 公开接口: 可用模型列表（所有登录用户可访问）============

@admin_bp.route("/models/available", methods=["GET"])
def list_available_models():
    """获取当前租户可用的模型列表（用于聊天界面的模型选择器）"""
    load_user_context()
    models = ModelProvider.get_active_providers(int(g.tenant_id))
    return jsonify({
        "models": [
            {
                "id": m.id,
                "name": m.name,
                "provider": m.provider,
                "model_name": m.model_name,
                "description": m.description,
                "is_default": m.is_default,
            }
            for m in models
        ],
        "default_id": next((m.id for m in models if m.is_default), None),
    }), 200


# ============ 系统信息 ============

@admin_bp.route("/admin/health", methods=["GET"])
@require_permission("admin:access")
def health_check():
    """系统健康检查"""
    from app.extensions import redis_client
    checks = {
        "database": _check_db(),
        "redis": _check_redis(redis_client),
        "llm": _check_llm(),
    }
    healthy = all(v["status"] == "ok" for v in checks.values())
    return jsonify({
        "status": "healthy" if healthy else "degraded",
        "checks": checks,
    }), 200 if healthy else 503


def _check_db() -> dict:
    try:
        db.session.execute(db.text("SELECT 1"))
        return {"status": "ok"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def _check_redis(redis_client) -> dict:
    try:
        redis_client.client.ping()
        return {"status": "ok"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def _check_llm() -> dict:
    """检测 LLM 服务连通性"""
    from flask import current_app
    provider = current_app.config["LLM_PROVIDER"]
    if provider == "anthropic":
        key = current_app.config.get("ANTHROPIC_API_KEY")
        if not key:
            return {"status": "warn", "message": "ANTHROPIC_API_KEY not set"}
    elif provider == "openai":
        key = current_app.config.get("OPENAI_API_KEY")
        if not key:
            return {"status": "warn", "message": "OPENAI_API_KEY not set"}
    return {"status": "ok", "provider": provider}

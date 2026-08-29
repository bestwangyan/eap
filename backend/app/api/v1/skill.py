import os
import uuid
import logging
import yaml
from flask import Blueprint, request, jsonify, g, current_app

from app.extensions import db
from app.middleware.auth import require_tenant_context, require_permission
from app.models.skill_config import SkillConfig
from app.models.audit_log import AuditLog

skill_bp = Blueprint("skill", __name__)
logger = logging.getLogger(__name__)

MAX_UPLOAD_SIZE = 50 * 1024 * 1024  # 50MB


@skill_bp.route("/skills", methods=["GET"])
@require_tenant_context
def list_skills():
    """Skill 列表"""
    skills = SkillConfig.query.filter_by(
        tenant_id=g.tenant_id
    ).order_by(SkillConfig.created_at.desc()).all()
    return jsonify({"skills": [s.to_dict() for s in skills]}), 200


@skill_bp.route("/skills/<int:skill_id>", methods=["GET"])
@require_tenant_context
def get_skill(skill_id):
    """Skill 详情（含完整 SKILL.md 内容）"""
    skill = SkillConfig.query.filter_by(
        id=skill_id, tenant_id=g.tenant_id
    ).first()
    if not skill:
        return jsonify({"error": "Skill not found"}), 404

    result = skill.to_dict()
    result["skill_content"] = skill.skill_content
    result["prompt"] = skill.get_prompt()
    return jsonify({"skill": result}), 200


@skill_bp.route("/skills", methods=["POST"])
@require_permission("skill:manage")
def create_skill():
    """通过配置信息创建 Skill（无需上传 ZIP）"""
    data = request.get_json()
    if not data:
        return jsonify({"error": "请求体不能为空"}), 422

    name = data.get("name", "").strip()
    if not name:
        return jsonify({"error": "Skill 名称 (name) 为必填项"}), 422

    # 检查租户内是否重名
    if SkillConfig.query.filter_by(tenant_id=g.tenant_id, name=name).first():
        return jsonify({"error": f"Skill '{name}' 已存在"}), 409

    # 解析运行模式
    mode = data.get("mode", "prompt")
    if mode not in ("prompt", "agent"):
        return jsonify({"error": "mode 必须为 'prompt' 或 'agent'"}), 422

    # 组装 SKILL.md 内容 (frontmatter + prompt)
    frontmatter = {
        "name": name,
        "description": data.get("description", ""),
        "version": data.get("version", "1.0.0"),
        "author": data.get("author", ""),
        "tools": data.get("tools", []),
        "tags": data.get("tags", []),
        "trigger_keywords": data.get("trigger_keywords", []),
    }
    prompt_body = data.get("prompt", data.get("skill_content", "")).strip()
    skill_content = f"---\n{yaml.dump(frontmatter, allow_unicode=True, sort_keys=False)}---\n{prompt_body}"

    try:
        skill = SkillConfig(
            tenant_id=g.tenant_id,
            name=name,
            description=data.get("description", ""),
            version=data.get("version", "1.0.0"),
            author=data.get("author", ""),
            tools=data.get("tools", []),
            tags=data.get("tags", []),
            trigger_keywords=data.get("trigger_keywords", []),
            original_filename="(手动创建)",
            file_hash=f"manual:{uuid.uuid4().hex}",
            is_active=True,
            mode=mode,
            skill_content=skill_content,
        )
        db.session.add(skill)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        logger.exception("Skill creation failed")
        return jsonify({"error": f"创建失败: {str(e)}"}), 500

    AuditLog.log(
        tenant_slug=g.tenant_slug,
        user_id=int(g.user_id),
        action="skill:create",
        resource="skill",
        resource_id=str(skill.id),
        detail={"name": skill.name, "method": "manual"},
    )

    return jsonify({"skill": skill.to_dict(), "message": "Skill 创建成功"}), 201


@skill_bp.route("/skills/upload", methods=["POST"])
@require_permission("skill:manage")
def upload_skill():
    """上传 Skill ZIP 压缩包"""
    if "file" not in request.files:
        return jsonify({"error": "请上传 ZIP 文件"}), 422

    file = request.files["file"]
    if not file.filename.endswith(".zip"):
        return jsonify({"error": "仅支持 .zip 格式"}), 422

    # 检查文件大小
    file.seek(0, os.SEEK_END)
    size = file.tell()
    file.seek(0)
    if size > MAX_UPLOAD_SIZE:
        return jsonify({"error": f"文件大小不能超过 {MAX_UPLOAD_SIZE // 1024 // 1024}MB"}), 413

    zip_data = file.read()
    storage_root = current_app.config.get(
        "SKILLS_STORAGE_ROOT",
        "/home/wangyan/deploy/eap/skills_storage"
    )

    try:
        skill = SkillConfig.from_zip(
            zip_data=zip_data,
            filename=file.filename,
            tenant_id=g.tenant_id,
            storage_root=storage_root,
        )
    except ValueError as e:
        return jsonify({"error": str(e)}), 422
    except Exception as e:
        logger.exception("Skill upload failed")
        return jsonify({"error": f"解析失败: {str(e)}"}), 500

    AuditLog.log(
        tenant_slug=g.tenant_slug,
        user_id=int(g.user_id),
        action="skill:upload",
        resource="skill",
        resource_id=str(skill.id),
        detail={"name": skill.name, "filename": file.filename},
    )

    return jsonify({"skill": skill.to_dict(), "message": "Skill 上传成功"}), 201


@skill_bp.route("/skills/<int:skill_id>", methods=["PUT"])
@require_permission("skill:manage")
def update_skill(skill_id):
    """更新 Skill（启用/禁用/编辑元数据）"""
    skill = SkillConfig.query.filter_by(
        id=skill_id, tenant_id=g.tenant_id
    ).first()
    if not skill:
        return jsonify({"error": "Skill not found"}), 404

    data = request.get_json()
    for field in ["description", "version", "author", "is_active", "tags", "trigger_keywords", "mode"]:
        if field in data:
            setattr(skill, field, data[field])

    db.session.commit()
    return jsonify({"skill": skill.to_dict()}), 200


@skill_bp.route("/skills/<int:skill_id>", methods=["DELETE"])
@require_permission("skill:manage")
def delete_skill(skill_id):
    """删除 Skill"""
    skill = SkillConfig.query.filter_by(
        id=skill_id, tenant_id=g.tenant_id
    ).first()
    if not skill:
        return jsonify({"error": "Skill not found"}), 404

    # 清理文件
    import shutil
    if skill.file_path and os.path.exists(skill.file_path):
        try:
            shutil.rmtree(skill.file_path)
        except Exception as e:
            logger.warning(f"Failed to cleanup skill files: {e}")

    AuditLog.log(
        tenant_slug=g.tenant_slug,
        user_id=int(g.user_id),
        action="skill:delete",
        resource="skill",
        resource_id=str(skill.id),
        detail={"name": skill.name},
    )

    db.session.delete(skill)
    db.session.commit()
    return jsonify({"message": "Skill 已删除"}), 200


@skill_bp.route("/skills/<int:skill_id>/toggle", methods=["POST"])
@require_permission("skill:manage")
def toggle_skill(skill_id):
    """切换 Skill 启用/禁用"""
    skill = SkillConfig.query.filter_by(
        id=skill_id, tenant_id=g.tenant_id
    ).first()
    if not skill:
        return jsonify({"error": "Skill not found"}), 404

    data = request.get_json()
    skill.is_active = data.get("is_active", not skill.is_active)
    db.session.commit()
    return jsonify({"skill": skill.to_dict()}), 200

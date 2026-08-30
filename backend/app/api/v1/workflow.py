"""Phase 4: 人机协同审批 API"""
from flask import Blueprint, request, jsonify, g

from app.extensions import db
from app.middleware.auth import require_tenant_context, require_permission
from app.models.approval import ApprovalRequest
from app.models.audit_log import AuditLog

wf_bp = Blueprint("workflow", __name__)


@wf_bp.route("/workflow/approvals", methods=["GET"])
@require_tenant_context
def list_approvals():
    status = request.args.get("status", "pending")
    approvals = ApprovalRequest.query.filter_by(
        tenant_id=g.tenant_id, status=status
    ).order_by(ApprovalRequest.created_at.desc()).limit(50).all()
    return jsonify({"approvals": [a.to_dict() for a in approvals]}), 200


def _ensure_resolvable(a):
    """仅 pending 审批可被决议（review Minor 2）：已决议/已消费/已放弃的
    行（approved/rejected/resumed/orphaned）不可再次决议 → 409。"""
    if a.status != "pending":
        return jsonify({"error": f"审批已处理（status={a.status}），不可再次决议"}), 409
    return None


@wf_bp.route("/workflow/approvals/<int:approval_id>/approve", methods=["POST"])
@require_permission("approval:approve")
def approve(approval_id):
    a = ApprovalRequest.query.filter_by(id=approval_id, tenant_id=g.tenant_id).first()
    if not a:
        return jsonify({"error": "Not found"}), 404
    guard = _ensure_resolvable(a)
    if guard:
        return guard
    a.status = "approved"
    a.decision = "approve"
    a.resolved_by = int(g.user_id)
    db.session.commit()
    AuditLog.log(tenant_slug=g.tenant_slug, user_id=int(g.user_id),
                 action="approval:approve", resource="approval", resource_id=str(a.id))
    return jsonify({"status": "approved"}), 200


@wf_bp.route("/workflow/approvals/<int:approval_id>/reject", methods=["POST"])
@require_permission("approval:approve")
def reject(approval_id):
    a = ApprovalRequest.query.filter_by(id=approval_id, tenant_id=g.tenant_id).first()
    if not a:
        return jsonify({"error": "Not found"}), 404
    guard = _ensure_resolvable(a)
    if guard:
        return guard
    data = request.get_json() or {}
    a.status = "rejected"
    a.decision = "reject"
    a.comment = data.get("reason", "")
    a.resolved_by = int(g.user_id)
    db.session.commit()
    return jsonify({"status": "rejected"}), 200


@wf_bp.route("/workflow/approvals/<int:approval_id>/edit", methods=["POST"])
@require_permission("approval:approve")
def edit_and_approve(approval_id):
    a = ApprovalRequest.query.filter_by(id=approval_id, tenant_id=g.tenant_id).first()
    if not a:
        return jsonify({"error": "Not found"}), 404
    guard = _ensure_resolvable(a)
    if guard:
        return guard
    data = request.get_json() or {}
    edited_args = data.get("edited_args")
    # review Minor 1: 空 edited_args 会被 orchestrator 静默降级为 approve，
    # 语义不明 —— 编辑路径要求非空对象，否则 422
    if not isinstance(edited_args, dict) or not edited_args:
        return jsonify({"error": "edited_args 必须是非空 JSON 对象（编辑路径不得降级为 approve）"}), 422
    a.status = "approved"
    a.decision = "approve"  # 编辑内容在 edited_args；decision=approve 供 orchestrator 构建 edit 恢复值
    a.edited_args = edited_args
    a.resolved_by = int(g.user_id)
    db.session.commit()
    return jsonify({"status": "approved_with_edits"}), 200

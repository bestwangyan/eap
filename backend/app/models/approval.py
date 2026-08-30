"""Phase 4: 人机协同审批模型"""
from app.extensions import db
from app.models.base import BaseModel


class ApprovalRequest(BaseModel):
    __tablename__ = "approval_requests"

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey("tenants.id"), nullable=False, index=True)
    thread_id = db.Column(db.String(255))
    agent_name = db.Column(db.String(100))
    tool_name = db.Column(db.String(100))
    tool_args = db.Column(db.JSON)
    # pending|approved|rejected|resumed|orphaned
    #   pending   待决议（workflow API 仅允许决议 pending 行）
    #   approved/rejected  已决议未消费（resume 候选；被放弃的批次由
    #                      新消息路径标记为 orphaned）
    #   resumed   已消费（resume 成功，防重复恢复）
    #   orphaned  已放弃（批次 checkpoint 已随新消息清理，不再参与 resume）
    status = db.Column(db.String(20), default="pending")
    requested_by = db.Column(db.Integer, db.ForeignKey("users.id"))
    resolved_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    decision = db.Column(db.String(20))
    edited_args = db.Column(db.JSON)
    comment = db.Column(db.Text)
    required_roles = db.Column(db.JSON, default=list)

    def to_dict(self):
        return {
            "id": self.id, "tenant_id": self.tenant_id,
            "thread_id": self.thread_id, "agent_name": self.agent_name,
            "tool_name": self.tool_name, "tool_args": self.tool_args,
            "status": self.status, "requested_by": self.requested_by,
            "resolved_by": self.resolved_by, "decision": self.decision,
            "edited_args": self.edited_args, "comment": self.comment,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

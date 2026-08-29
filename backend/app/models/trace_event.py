"""Trace event model — stores LangChain/Agent observability traces in PostgreSQL"""
from app.extensions import db
from app.models.base import BaseModel


class TraceEvent(BaseModel):
    """单条 Trace 事件 — LLM 调用 / 工具调用 / Agent 步骤"""
    __tablename__ = "trace_events"

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey("tenants.id"), nullable=False, index=True)
    trace_id = db.Column(db.String(64), nullable=False, index=True)      # 一次对话 = 一个 trace
    parent_run_id = db.Column(db.String(64), index=True)                  # 父事件 run_id
    run_id = db.Column(db.String(64), unique=True, nullable=False)        # 本次事件唯一 ID
    event_type = db.Column(db.String(32), nullable=False)                 # llm / tool / chain / agent
    event_name = db.Column(db.String(255), nullable=False)                # 事件名称
    thread_id = db.Column(db.String(255), index=True)                     # 关联对话线程
    user_id = db.Column(db.Integer, index=True)

    # 事件内容
    input_data = db.Column(db.JSON, default=dict)       # 输入 (prompt / tool args)
    output_data = db.Column(db.JSON, default=dict)      # 输出 (response / tool result)
    metadata_json = db.Column(db.JSON, default=dict)    # 元数据 (model, tokens, latency 等)
    error = db.Column(db.Text)            # 错误信息

    # 时间
    started_at = db.Column(db.DateTime)
    ended_at = db.Column(db.DateTime)
    duration_ms = db.Column(db.Integer)   # 耗时 (毫秒)

    def to_dict(self):
        return {
            "id": self.id,
            "trace_id": self.trace_id,
            "parent_run_id": self.parent_run_id,
            "run_id": self.run_id,
            "event_type": self.event_type,
            "event_name": self.event_name,
            "thread_id": self.thread_id,
            "input_data": self.input_data,
            "output_data": self.output_data,
            "metadata_json": self.metadata_json,
            "error": self.error,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "ended_at": self.ended_at.isoformat() if self.ended_at else None,
            "duration_ms": self.duration_ms,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

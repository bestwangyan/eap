"""LangChain Callback Handler — captures traces into PostgreSQL"""
import time
import uuid
import logging
import json
from datetime import datetime
from typing import Any
from langchain_core.callbacks.base import BaseCallbackHandler

logger = logging.getLogger(__name__)

# contextvar — stores current trace context
from contextvars import ContextVar
_trace_context: ContextVar[dict] = ContextVar("trace_context", default={})


def set_trace_context(tenant_id: int, user_id: int, thread_id: str):
    """在每次对话开始前设置 trace 上下文"""
    _trace_context.set({
        "trace_id": str(uuid.uuid4())[:12],
        "tenant_id": tenant_id,
        "user_id": user_id,
        "thread_id": thread_id,
    })


def get_trace_id() -> str:
    return _trace_context.get().get("trace_id", "")


class DBTraceHandler(BaseCallbackHandler):
    """将 LangChain 事件写入 trace_events 表"""

    def _get_ctx(self) -> dict:
        return _trace_context.get()

    def _save(self, **kwargs):
        from flask import current_app
        try:
            from app.models.trace_event import TraceEvent
            from app.extensions import db

            ctx = self._get_ctx()
            if not ctx:
                return

            event = TraceEvent(
                tenant_id=ctx["tenant_id"],
                user_id=ctx.get("user_id"),
                thread_id=ctx.get("thread_id"),
                trace_id=ctx["trace_id"],
                **kwargs,
            )
            db.session.add(event)
            db.session.commit()
        except Exception as e:
            logger.warning(f"Failed to save trace event: {e}")

    def on_llm_start(
        self, serialized: dict[str, Any], prompts: list[str], *,
        run_id: str, parent_run_id: str | None = None,
        **kwargs: Any,
    ) -> None:
        model = serialized.get("kwargs", {}).get("model", serialized.get("name", "unknown"))
        self._save(
            run_id=str(run_id),
            parent_run_id=str(parent_run_id) if parent_run_id else None,
            event_type="llm",
            event_name=f"LLM: {model}",
            input_data={"prompts": [p[:500] for p in prompts]},
            metadata_json={"model": model, "serialized_name": serialized.get("name", "")},
            started_at=datetime.utcnow(),
        )

    def on_llm_end(self, response, *, run_id: str, **kwargs: Any) -> None:
        from langchain_core.messages import AIMessage
        output = None
        token_usage = None
        if hasattr(response, "generations"):
            for gen_list in response.generations:
                for gen in gen_list:
                    msg = getattr(gen, "message", None)
                    if msg and isinstance(msg, AIMessage):
                        output = {
                            "content": str(msg.content)[:500],
                            "tool_calls": [
                                {"name": tc.get("name"), "args": tc.get("args", {})}
                                if isinstance(tc, dict)
                                else {"name": getattr(tc, "name", ""), "args": getattr(tc, "args", {})}
                                for tc in (msg.tool_calls or [])
                            ] if hasattr(msg, "tool_calls") and msg.tool_calls else None,
                        }
                        if hasattr(msg, "usage_metadata"):
                            token_usage = dict(msg.usage_metadata)

        try:
            from app.models.trace_event import TraceEvent
            from app.extensions import db
            event = TraceEvent.query.filter_by(run_id=str(run_id)).first()
            if event:
                event.output_data = output or {}
                event.metadata_json = {
                    **(event.metadata_json or {}),
                    "token_usage": token_usage or {},
                }
                event.ended_at = datetime.utcnow()
                if event.started_at:
                    event.duration_ms = int(
                        (event.ended_at - event.started_at).total_seconds() * 1000
                    )
                db.session.commit()
        except Exception as e:
            logger.warning(f"Failed to update trace event end: {e}")

    def on_llm_error(self, error, *, run_id: str, **kwargs: Any) -> None:
        try:
            from app.models.trace_event import TraceEvent
            from app.extensions import db
            event = TraceEvent.query.filter_by(run_id=str(run_id)).first()
            if event:
                event.error = str(error)[:1000]
                event.ended_at = datetime.utcnow()
                db.session.commit()
        except Exception:
            pass

    def on_tool_start(
        self, serialized: dict[str, Any], input_str: str, *,
        run_id: str, parent_run_id: str | None = None,
        **kwargs: Any,
    ) -> None:
        tool_name = serialized.get("name", "unknown")
        try:
            tool_input = json.loads(input_str) if input_str else {}
        except (json.JSONDecodeError, TypeError):
            tool_input = {"raw": str(input_str)[:500]}

        self._save(
            run_id=str(run_id),
            parent_run_id=str(parent_run_id) if parent_run_id else None,
            event_type="tool",
            event_name=f"Tool: {tool_name}",
            input_data={"tool_name": tool_name, "input": tool_input},
            started_at=datetime.utcnow(),
        )

    def on_tool_end(self, output: str, *, run_id: str, **kwargs: Any) -> None:
        try:
            from app.models.trace_event import TraceEvent
            from app.extensions import db
            event = TraceEvent.query.filter_by(run_id=str(run_id)).first()
            if event:
                event.output_data = {"output": str(output)[:1000]}
                event.ended_at = datetime.utcnow()
                if event.started_at:
                    event.duration_ms = int(
                        (event.ended_at - event.started_at).total_seconds() * 1000
                    )
                db.session.commit()
        except Exception as e:
            logger.warning(f"Failed to update tool trace end: {e}")

    def on_tool_error(self, error, *, run_id: str, **kwargs: Any) -> None:
        try:
            from app.models.trace_event import TraceEvent
            from app.extensions import db
            event = TraceEvent.query.filter_by(run_id=str(run_id)).first()
            if event:
                event.error = str(error)[:1000]
                event.ended_at = datetime.utcnow()
                db.session.commit()
        except Exception:
            pass

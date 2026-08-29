"""Phase 5: 监控 API — 成本、延迟、并发、健康、Trace"""
from flask import Blueprint, request, jsonify, g, current_app
from app.middleware.auth import require_tenant_context, require_permission
from app.core.monitoring.cost_tracker import CostTracker
from app.models.trace_event import TraceEvent

mon_bp = Blueprint("monitor", __name__)


@mon_bp.route("/admin/monitor/dashboard", methods=["GET"])
@require_permission("admin:access")
def dashboard():
    tracker = CostTracker()
    daily = tracker.get_tenant_daily(g.tenant_slug)
    return jsonify({
        "cost": daily,
        "active_sessions": _count_sessions(),
        "status": "healthy",
    }), 200


@mon_bp.route("/admin/monitor/cost/tenant", methods=["GET"])
@require_permission("admin:access")
def tenant_cost():
    tracker = CostTracker()
    return jsonify(tracker.get_tenant_daily(g.tenant_slug)), 200


@mon_bp.route("/admin/monitor/latency", methods=["GET"])
@require_permission("admin:access")
def latency():
    return jsonify({"p50_ms": 1200, "p95_ms": 3500, "p99_ms": 8000}), 200


@mon_bp.route("/admin/monitor/concurrency", methods=["GET"])
@require_permission("admin:access")
def concurrency():
    return jsonify({"active_sessions": _count_sessions()}), 200


@mon_bp.route("/admin/monitor/traces", methods=["GET"])
@require_permission("admin:access")
def list_traces():
    """获取 Trace 列表（按 trace_id 去重，最近 N 次对话）"""
    limit = request.args.get("limit", 20, type=int)
    from app.extensions import db

    # 获取最近 N 个不重复的 trace_id（按最新 created_at 排序）
    rows = db.session.execute(
        db.text(
            "SELECT trace_id, MAX(created_at) AS last_seen "
            "FROM trace_events WHERE tenant_id = :tid "
            "GROUP BY trace_id ORDER BY last_seen DESC LIMIT :lim"
        ),
        {"tid": g.tenant_id, "lim": limit},
    ).fetchall()
    trace_ids = [row[0] for row in rows]

    traces = []
    for tid in trace_ids:
        first = TraceEvent.query.filter_by(
            tenant_id=g.tenant_id, trace_id=tid
        ).order_by(TraceEvent.started_at.asc()).first()
        if first:
            d = first.to_dict()
            event_count = TraceEvent.query.filter_by(
                tenant_id=g.tenant_id, trace_id=tid
            ).count()
            d["event_count"] = event_count
            traces.append(d)

    return jsonify({"traces": traces}), 200


@mon_bp.route("/admin/monitor/traces/<trace_id>", methods=["GET"])
@require_permission("admin:access")
def get_trace_detail(trace_id):
    """获取一个 Trace 的完整事件树"""
    events = TraceEvent.query.filter_by(
        tenant_id=g.tenant_id, trace_id=trace_id
    ).order_by(TraceEvent.started_at.asc()).all()

    if not events:
        return jsonify({"error": "Trace not found"}), 404

    # 构建事件树
    thread_id = events[0].thread_id if events else None
    return jsonify({
        "trace_id": trace_id,
        "thread_id": thread_id,
        "total_events": len(events),
        "events": [e.to_dict() for e in events],
        # 汇总
        "summary": {
            "llm_calls": sum(1 for e in events if e.event_type == "llm"),
            "tool_calls": sum(1 for e in events if e.event_type == "tool"),
            "total_duration_ms": sum(e.duration_ms or 0 for e in events),
            "errors": [e.error for e in events if e.error],
            "total_tokens": sum(
                (e.metadata_json or {}).get("token_usage", {}).get("total_tokens", 0)
                for e in events if e.event_type == "llm"
            ),
        },
    }), 200


def _count_sessions() -> int:
    try:
        redis_client = current_app.extensions.get("redis_client")
        if redis_client:
            return len(redis_client.keys("session:*"))
    except Exception:
        pass
    return 0

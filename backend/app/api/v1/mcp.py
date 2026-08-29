import logging
from flask import Blueprint, request, jsonify, g

from app.extensions import db
from app.middleware.auth import require_tenant_context, require_permission
from app.models.mcp_server import MCPServer
from app.models.audit_log import AuditLog

mcp_bp = Blueprint("mcp", __name__)
logger = logging.getLogger(__name__)


@mcp_bp.route("/mcp/servers", methods=["GET"])
@require_tenant_context
def list_servers():
    """MCP Server 列表"""
    servers = MCPServer.query.filter_by(
        tenant_id=g.tenant_id
    ).order_by(MCPServer.created_at.desc()).all()
    return jsonify({"servers": [s.to_dict() for s in servers]}), 200


@mcp_bp.route("/mcp/servers/<int:server_id>", methods=["GET"])
@require_tenant_context
def get_server(server_id):
    """MCP Server 详情"""
    server = MCPServer.query.filter_by(
        id=server_id, tenant_id=g.tenant_id
    ).first()
    if not server:
        return jsonify({"error": "MCP Server not found"}), 404
    return jsonify({"server": server.to_dict()}), 200


@mcp_bp.route("/mcp/servers", methods=["POST"])
@require_permission("mcp:manage")
def create_server():
    """创建 MCP Server 配置

    stdio 模式:
    { "name": "filesystem", "transport": "stdio", "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"],
      "env": {} }

    SSE 模式:
    { "name": "remote-server", "transport": "sse",
      "sse_url": "http://host:8080/sse",
      "sse_headers": {"Authorization": "Bearer xxx"} }
    """
    data = request.get_json()
    if not data or "name" not in data:
        return jsonify({"error": "name is required"}), 422

    transport = data.get("transport", "stdio")
    if transport not in ("stdio", "sse"):
        return jsonify({"error": "transport 必须是 stdio 或 sse"}), 422

    if transport == "stdio" and not data.get("command"):
        return jsonify({"error": "stdio 模式需要 command 字段"}), 422
    if transport == "sse" and not data.get("sse_url"):
        return jsonify({"error": "SSE 模式需要 sse_url 字段"}), 422

    server = MCPServer(
        tenant_id=g.tenant_id,
        name=data["name"],
        description=data.get("description", ""),
        transport=transport,
        command=data.get("command", ""),
        args=data.get("args", []),
        env=data.get("env", {}),
        sse_url=data.get("sse_url", ""),
        sse_headers=data.get("sse_headers", {}),
        is_active=data.get("is_active", True),
    )
    db.session.add(server)
    db.session.commit()

    AuditLog.log(
        tenant_slug=g.tenant_slug,
        user_id=int(g.user_id),
        action="mcp:create",
        resource="mcp_server",
        resource_id=str(server.id),
        detail={"name": server.name, "transport": transport},
    )

    return jsonify({"server": server.to_dict()}), 201


@mcp_bp.route("/mcp/servers/<int:server_id>", methods=["PUT"])
@require_permission("mcp:manage")
def update_server(server_id):
    """更新 MCP Server 配置"""
    server = MCPServer.query.filter_by(
        id=server_id, tenant_id=g.tenant_id
    ).first()
    if not server:
        return jsonify({"error": "MCP Server not found"}), 404

    data = request.get_json()
    for field in [
        "name", "description", "transport", "command", "args", "env",
        "sse_url", "sse_headers", "is_active",
    ]:
        if field in data:
            setattr(server, field, data[field])

    db.session.commit()
    return jsonify({"server": server.to_dict()}), 200


@mcp_bp.route("/mcp/servers/<int:server_id>", methods=["DELETE"])
@require_permission("mcp:manage")
def delete_server(server_id):
    """删除 MCP Server 配置"""
    server = MCPServer.query.filter_by(
        id=server_id, tenant_id=g.tenant_id
    ).first()
    if not server:
        return jsonify({"error": "MCP Server not found"}), 404

    AuditLog.log(
        tenant_slug=g.tenant_slug,
        user_id=int(g.user_id),
        action="mcp:delete",
        resource="mcp_server",
        resource_id=str(server.id),
        detail={"name": server.name},
    )

    db.session.delete(server)
    db.session.commit()
    return jsonify({"message": "MCP Server 已删除"}), 200


@mcp_bp.route("/mcp/servers/<int:server_id>/test", methods=["POST"])
@require_permission("mcp:manage")
def test_connection(server_id):
    """测试 MCP Server 连接"""
    server = MCPServer.query.filter_by(
        id=server_id, tenant_id=g.tenant_id
    ).first()
    if not server:
        return jsonify({"error": "MCP Server not found"}), 404

    try:
        config = server.to_mcp_config()

        # 基本连通性检测
        if server.transport == "sse":
            import urllib.request
            req = urllib.request.Request(server.sse_url, method="HEAD")
            for k, v in (server.sse_headers or {}).items():
                req.add_header(k, v)
            urllib.request.urlopen(req, timeout=5)
        else:
            import subprocess
            result = subprocess.run(
                [server.command] + (server.args or []),
                capture_output=True, text=True, timeout=10,
                env={**__import__("os").environ, **(server.env or {})},
            )
            if result.returncode != 0 and "error" in result.stderr.lower():
                return jsonify({
                    "status": "error",
                    "message": result.stderr[:200]
                }), 200

        server.connection_status = "connected"
        from datetime import datetime
        server.last_connected_at = datetime.utcnow()
        db.session.commit()

        return jsonify({"status": "connected", "message": "连接成功"}), 200

    except Exception as e:
        server.connection_status = "error"
        db.session.commit()
        return jsonify({"status": "error", "message": str(e)[:200]}), 200

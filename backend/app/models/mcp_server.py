"""MCP Server 配置 - 用户手动添加的 stdio / SSE 服务"""
from app.extensions import db
from app.models.base import BaseModel


class MCPServer(BaseModel):
    """MCP Server 配置"""
    __tablename__ = "mcp_servers"

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(
        db.Integer, db.ForeignKey("tenants.id"), nullable=False, index=True
    )
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)

    # 连接类型: stdio | sse
    transport = db.Column(db.String(20), nullable=False, default="stdio")

    # ---- stdio 模式 ----
    command = db.Column(db.String(500))          # 启动命令, 如 "python" / "node" / "npx"
    args = db.Column(db.JSON, default=list)       # 命令参数, 如 ["-m", "my_mcp_server"]
    env = db.Column(db.JSON, default=dict)        # 环境变量, 如 {"API_KEY": "xxx"}

    # ---- SSE 模式 ----
    sse_url = db.Column(db.String(500))           # SSE 端点, 如 "http://host:port/sse"
    sse_headers = db.Column(db.JSON, default=dict) # 自定义请求头

    is_active = db.Column(db.Boolean, default=True)
    connection_status = db.Column(db.String(20), default="disconnected")
    # disconnected | connecting | connected | error

    last_connected_at = db.Column(db.DateTime)

    __table_args__ = (
        db.UniqueConstraint("tenant_id", "name", name="uq_mcp_tenant_name"),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "tenant_id": self.tenant_id,
            "name": self.name,
            "description": self.description,
            "transport": self.transport,
            # stdio 字段
            "command": self.command,
            "args": self.args,
            "env": self.env,
            # sse 字段
            "sse_url": self.sse_url,
            "sse_headers": self.sse_headers,
            "is_active": self.is_active,
            "connection_status": self.connection_status,
            "last_connected_at": (
                self.last_connected_at.isoformat()
                if self.last_connected_at else None
            ),
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    def to_mcp_config(self) -> dict:
        """转换为 langchain_mcp_adapters 兼容的配置"""
        if self.transport == "stdio":
            if not self.command:
                raise ValueError(f"MCP Server '{self.name}': stdio 模式需要 command")
            return {
                "command": self.command,
                "args": self.args or [],
                "env": self.env or {},
                "transport": "stdio",
            }
        elif self.transport == "sse":
            if not self.sse_url:
                raise ValueError(f"MCP Server '{self.name}': SSE 模式需要 sse_url")
            return {
                "url": self.sse_url,
                "headers": self.sse_headers or {},
                "transport": "sse",
            }
        else:
            raise ValueError(f"Unknown transport: {self.transport}")

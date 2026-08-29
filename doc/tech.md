# 企业级 Agent 平台 - 全量技术方案

> **版本**: v1.0
> **日期**: 2026-07-25
> **基于选型**: LangChain Deep Agents（详见 [tech_report.md](tech_report.md)）
> **项目代号**: Enterprise Agent Platform (EAP)

---

## 目录

1. [总体架构](#1-总体架构)
2. [项目目录结构](#2-项目目录结构)
3. [Phase 1: 基础设施 + 单 Agent 对话](#3-phase-1-基础设施--单-agent-对话)
4. [Phase 2: 知识库 + RAG](#4-phase-2-知识库--rag)
5. [Phase 3: 多 Agent + 编排 + SkillMCP](#5-phase-3-多-agent--编排--skillmcp)
6. [Phase 4: 企业特性](#6-phase-4-企业特性)
7. [Phase 5: 可观测性 + 运维](#7-phase-5-可观测性--运维)
8. [部署架构](#8-部署架构)
9. [附录](#9-附录)

---

## 1. 总体架构

### 1.1 架构全景图

```
┌──────────────────────────────────────────────────────────────────────────┐
│                          前端层 (Browser)                                  │
│                                                                          │
│  ┌─────────────┐ ┌─────────────┐ ┌───────────┐ ┌──────────────────────┐ │
│  │ Chat UI     │ │ Agent       │ │ Knowledge │ │ Admin Console        │ │
│  │ · 对话界面  │ │ Manager     │ │ Base      │ │ · 用户管理           │ │
│  │ · 流式输出  │ │ · Agent 创建│ │ · 文档上传│ │ · RBAC 配置          │ │
│  │ · 工具结果  │ │ · 编排配置  │ │ · 检索测试│ │ · 审计日志           │ │
│  │ · 审批卡片  │ │ · Skill 管理│ │ · 分块预览│ │ · 系统监控           │ │
│  └─────────────┘ └─────────────┘ └───────────┘ └──────────────────────┘ │
│                                                                          │
│  React 18 + TypeScript + Ant Design 5 + Vite + Zustand                  │
└──────────────────────────────┬───────────────────────────────────────────┘
                               │ HTTP/SSE/WebSocket
                               │ JWT Bearer Token
┌──────────────────────────────▼───────────────────────────────────────────┐
│                        网关层 (Nginx)                                     │
│  · 反向代理  · SSL 终端  · 速率限制  · 静态资源                          │
└──────────────────────────────┬───────────────────────────────────────────┘
                               │
┌──────────────────────────────▼───────────────────────────────────────────┐
│                    Flask Web 服务层 (BFF)                                  │
│                                                                          │
│  ┌───────────┐ ┌───────────┐ ┌───────────┐ ┌──────────────────────────┐ │
│  │ Auth      │ │ RBAC      │ │ Session   │ │ API Router               │ │
│  │ Blueprint │ │ Middleware│ │ Manager   │ │ · /api/v1/chat/*         │ │
│  │ · 登录    │ │ · 角色验证│ │ · Redis   │ │ · /api/v1/agent/*        │ │
│  │ · JWT签发 │ │ · 权限拦截│ │ · 多租户  │ │ · /api/v1/knowledge/*    │ │
│  │ · 刷新    │ │ · 数据隔离│ │           │ │ · /api/v1/admin/*        │ │
│  └───────────┘ └───────────┘ └───────────┘ └──────────────────────────┘ │
│                                                                          │
│  Flask 3.x + Flask-SocketIO + Flask-CORS + Flask-Migrate                │
└──────────────────────────────┬───────────────────────────────────────────┘
                               │ Python API (同进程调用)
┌──────────────────────────────▼───────────────────────────────────────────┐
│                     Agent 执行层 (LangGraph)                               │
│                                                                          │
│  ┌──────────────────────────────────────────────────────────────────────┐│
│  │                    Agent Orchestrator                                 ││
│  │  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌───────────┐ ││
│  │  │ Agent  │  │ Sub-    │  │ Task    │  │ Skill   │  │ MCP       │ ││
│  │  │ Factory │  │ Agent   │  │ Planner │  │ Loader  │  │ Manager   │ ││
│  │  │         │  │ Manager │  │ (DAG)   │  │         │  │           │ ││
│  │  └─────────┘  └─────────┘  └─────────┘  └─────────┘  └───────────┘ ││
│  └──────────────────────────────────────────────────────────────────────┘│
│                                                                          │
│  ┌──────────────────────────────────────────────────────────────────────┐│
│  │                    Middleware Chain                                    ││
│  │  PII Detector → Guardrails → Memory → HITL → Audit Log              ││
│  └──────────────────────────────────────────────────────────────────────┘│
│                                                                          │
│  ┌──────────────────────────────────────────────────────────────────────┐│
│  │                    LangGraph Runtime                                   ││
│  │  Checkpoint (PG) │ Streaming │ Interrupt (HITL) │ State Mgmt        ││
│  └──────────────────────────────────────────────────────────────────────┘│
│                                                                          │
│  LangChain Deep Agents + LangGraph + langgraph-checkpoint-postgres      │
└──────────────────────────────┬───────────────────────────────────────────┘
                               │
┌──────────────────────────────▼───────────────────────────────────────────┐
│                        数据与基础设施层                                    │
│                                                                          │
│  ┌───────────┐ ┌───────────┐ ┌───────────┐ ┌──────────┐ ┌────────────┐ │
│  │ PostgreSQL│ │ Redis     │ │ MinIO/S3  │ │ LLM      │ │ Sandbox    │ │
│  │ · 业务数据│ │ · Session │ │ · 文档    │ │ Gateway  │ │ Runtime    │ │
│  │ · 检查点  │ │ · 缓存    │ │ · 图片    │ │ · Claude │ │ · Docker   │ │
│  │ · pgvector│ │ · 速率限制│ │ · 模型    │ │ · GPT    │ │ · Exec     │ │
│  │ · 记忆存储│ │ · 消息队列│ │           │ │ · 国产   │ │            │ │
│  └───────────┘ └───────────┘ └───────────┘ └──────────┘ └────────────┘ │
└──────────────────────────────────────────────────────────────────────────┘
```

### 1.2 核心数据流

```
用户输入 → Flask API → Auth Middleware → RBAC Check
    → Agent Orchestrator → [Guardrails] → [Memory Injection]
    → LangGraph Agent (with tools/skills/MCP/知识库)
    → Streaming Response (SSE) → 前端流式渲染
    → [HITL 断点] → 等待审批 → 继续执行
    → Checkpoint 持久化 + Audit Log
```

### 1.3 多租户数据隔离模型

```
                    ┌──────────────┐
                    │   Tenant      │
                    │   (企业/组织)  │
                    └──────┬───────┘
                           │ 1:N
           ┌───────────────┼───────────────┐
           │               │               │
     ┌─────▼─────┐  ┌─────▼─────┐  ┌─────▼─────┐
     │ User A    │  │ User B    │  │ Admin     │
     │ Role: dev │  │ Role: ops │  │ Role: SA │
     └─────┬─────┘  └─────┬─────┘  └─────┬─────┘
           │               │               │
           │  Thread Scope │               │
     ┌─────▼──────────────────────────────▼─────┐
     │           LangGraph Threads              │
     │  thread:tenant-1:user-a:session-xyz      │
     │  thread:tenant-1:user-b:session-abc      │
     │  · 每个 Thread 严格隔离                   │
     │  · Memory Store 按 (tenant, user) 命名空间 │
     │  · 知识库按 Tenant 隔离                   │
     └──────────────────────────────────────────┘
```

---

## 2. 项目目录结构

```
enterprise_agent_lang/
├── docker-compose.yml              # 开发环境服务编排
├── docker-compose.prod.yml         # 生产环境编排
├── Makefile                        # 常用命令快捷方式
├── .env.example                    # 环境变量模板
├── .gitignore
│
├── backend/                        # Flask 后端
│   ├── requirements.txt
│   ├── config.py                   # 配置管理（多环境）
│   ├── wsgi.py                     # 应用入口
│   ├── app/
│   │   ├── __init__.py             # 工厂函数 create_app()
│   │   ├── extensions.py           # Flask 扩展初始化
│   │   │
│   │   ├── api/                    # API 蓝图
│   │   │   ├── __init__.py
│   │   │   ├── v1/
│   │   │   │   ├── __init__.py
│   │   │   │   ├── auth.py         # 认证接口
│   │   │   │   ├── chat.py         # 对话接口 (SSE)
│   │   │   │   ├── agent.py        # Agent 管理接口
│   │   │   │   ├── knowledge.py    # 知识库接口
│   │   │   │   ├── skill.py        # Skill 管理接口
│   │   │   │   ├── mcp.py          # MCP Server 管理
│   │   │   │   ├── admin.py        # 管理后台接口
│   │   │   │   └── workflow.py     # 审批工作流接口
│   │   │   └── deps.py             # 依赖注入（get_current_user 等）
│   │   │
│   │   ├── core/                   # 核心业务逻辑
│   │   │   ├── __init__.py
│   │   │   ├── auth/               # 认证模块
│   │   │   │   ├── __init__.py
│   │   │   │   ├── models.py       # User, Role, Permission
│   │   │   │   ├── services.py     # 认证业务逻辑
│   │   │   │   └── jwt.py          # JWT 签发/验证
│   │   │   ├── agent/              # Agent 核心
│   │   │   │   ├── __init__.py
│   │   │   │   ├── orchestrator.py # Agent 编排器
│   │   │   │   ├── factory.py      # Agent 工厂
│   │   │   │   ├── tools/          # 内置工具集
│   │   │   │   │   ├── __init__.py
│   │   │   │   │   ├── search.py   # 搜索工具
│   │   │   │   │   ├── calculator.py
│   │   │   │   │   ├── api_caller.py
│   │   │   │   │   └── sandbox.py  # 沙箱执行
│   │   │   │   ├── skills/         # Skill 系统
│   │   │   │   │   ├── __init__.py
│   │   │   │   │   ├── loader.py   # Skill 加载器
│   │   │   │   │   └── registry.py # Skill 注册表
│   │   │   │   └── prompts/        # 提示词模板
│   │   │   │       └── system.py
│   │   │   ├── knowledge/          # 知识库模块
│   │   │   │   ├── __init__.py
│   │   │   │   ├── models.py       # Document, Chunk, Collection
│   │   │   │   ├── loader.py       # 文档加载器（PDF/Word/MD/TXT）
│   │   │   │   ├── splitter.py     # 文档分块策略
│   │   │   │   ├── embedder.py     # Embedding 服务
│   │   │   │   └── retriever.py    # 检索器（语义+混合）
│   │   │   ├── memory/             # 记忆模块
│   │   │   │   ├── __init__.py
│   │   │   │   ├── store.py        # LangGraph Store 适配
│   │   │   │   └── middleware.py   # Memory Middleware
│   │   │   ├── guardrails/         # 安全围栏
│   │   │   │   ├── __init__.py
│   │   │   │   ├── pii.py          # PII 检测/脱敏
│   │   │   │   ├── content.py      # 内容审核
│   │   │   │   └── chain.py        # 围栏链
│   │   │   └── mcp/                # MCP 管理
│   │   │       ├── __init__.py
│   │   │       ├── manager.py      # MCP Server 生命周期
│   │   │       └── client.py       # MCP Client 适配
│   │   │
│   │   ├── middleware/             # Flask 中间件
│   │   │   ├── __init__.py
│   │   │   ├── auth.py             # JWT 验证
│   │   │   ├── rbac.py             # RBAC 拦截
│   │   │   ├── tenant.py           # 租户上下文注入
│   │   │   └── rate_limit.py       # 速率限制
│   │   │
│   │   └── models/                 # 数据模型 (SQLAlchemy)
│   │       ├── __init__.py
│   │       ├── base.py             # Base Model
│   │       ├── user.py
│   │       ├── role.py
│   │       ├── tenant.py
│   │       ├── agent_config.py
│   │       ├── audit_log.py
│   │       ├── model_provider.py
│   │       ├── skill_config.py
│   │       └── mcp_server.py
│   │
│   ├── migrations/                 # Flask-Migrate 迁移文件
│   └── tests/
│       ├── conftest.py
│       ├── test_auth.py
│       ├── test_chat.py
│       └── test_agent.py
│
├── frontend/                       # React 前端
│   ├── package.json
│   ├── tsconfig.json
│   ├── vite.config.ts
│   ├── index.html
│   ├── src/
│   │   ├── main.tsx
│   │   ├── App.tsx
│   │   ├── router.tsx
│   │   │
│   │   ├── api/                    # API 调用层
│   │   │   ├── client.ts           # Axios 实例 (JWT 拦截)
│   │   │   ├── auth.ts
│   │   │   ├── chat.ts             # SSE 流式客户端
│   │   │   ├── agent.ts
│   │   │   ├── knowledge.ts
│   │   │   └── admin.ts
│   │   │
│   │   ├── stores/                 # 状态管理 (Zustand)
│   │   │   ├── authStore.ts
│   │   │   ├── chatStore.ts
│   │   │   ├── agentStore.ts
│   │   │   └── appStore.ts
│   │   │
│   │   ├── hooks/                  # 自定义 Hooks
│   │   │   ├── useSSE.ts           # SSE 流式 Hook
│   │   │   ├── useAuth.ts
│   │   │   └── usePermission.ts
│   │   │
│   │   ├── pages/                  # 页面组件
│   │   │   ├── Login/
│   │   │   ├── Chat/               # 对话主页
│   │   │   ├── AgentManager/       # Agent 管理
│   │   │   ├── KnowledgeBase/      # 知识库管理
│   │   │   ├── SkillMarket/        # Skill 市场
│   │   │   ├── WorkflowApproval/   # 审批中心
│   │   │   └── Admin/              # 管理后台
│   │   │       ├── UserManagement/
│   │   │       ├── RBACConfig/
│   │   │       ├── AuditLog/
│   │   │       └── SystemMonitor/
│   │   │
│   │   ├── components/             # 通用组件
│   │   │   ├── Layout/
│   │   │   │   ├── MainLayout.tsx
│   │   │   │   ├── Sidebar.tsx
│   │   │   │   └── Header.tsx
│   │   │   ├── Chat/
│   │   │   │   ├── ChatWindow.tsx   # 对话窗口
│   │   │   │   ├── MessageBubble.tsx
│   │   │   │   ├── ToolCallCard.tsx # 工具调用展示
│   │   │   │   ├── ApprovalCard.tsx # 审批操作卡片
│   │   │   │   └── StreamingText.tsx # 流式文本渲染
│   │   │   ├── Agent/
│   │   │   │   ├── AgentCard.tsx
│   │   │   │   ├── AgentConfigForm.tsx
│   │   │   │   └── SubAgentEditor.tsx
│   │   │   ├── Knowledge/
│   │   │   │   ├── DocumentUpload.tsx
│   │   │   │   ├── ChunkPreview.tsx
│   │   │   │   └── SearchTest.tsx
│   │   │   └── Common/
│   │   │       ├── PermissionGate.tsx
│   │   │       ├── LoadingSkeleton.tsx
│   │   │       └── ErrorBoundary.tsx
│   │   │
│   │   ├── types/                  # TypeScript 类型
│   │   │   ├── auth.ts
│   │   │   ├── chat.ts
│   │   │   ├── agent.ts
│   │   │   └── knowledge.ts
│   │   │
│   │   └── utils/
│   │       ├── constants.ts
│   │       └── format.ts
│   │
│   └── public/
│
├── skills/                         # 内置 Skill 定义
│   ├── web_search/
│   │   └── SKILL.md
│   ├── code_execution/
│   │   └── SKILL.md
│   └── data_analysis/
│       └── SKILL.md
│
├── mcp_servers/                    # 内置 MCP Server 配置
│   ├── filesystem.json
│   ├── postgres.json
│   └── web_search.json
│
└── doc/                            # 项目文档
    ├── tech_report.md
    └── tech.md
```

---

## 3. Phase 1: 基础设施 + 单 Agent 对话

> **时间**: 4-6 周 | **目标**: 跑通端到端对话流程
> **验证标准**: 用户可通过前端 UI 登录并与 Agent 进行多轮流式对话

### 3.1 Flask 后端骨架

#### 3.1.1 应用工厂模式

```python
# backend/app/__init__.py
def create_app(config_name: str = "development") -> Flask:
    app = Flask(__name__)
    app.config.from_object(config[config_name])

    # 初始化扩展
    db.init_app(app)
    migrate.init_app(app, db)
    jwt_manager.init_app(app)
    cors.init_app(app)
    redis_client.init_app(app)

    # 注册蓝图
    from app.api.v1 import api_v1
    app.register_blueprint(api_v1, url_prefix="/api/v1")

    # 注册中间件
    from app.middleware import register_middlewares
    register_middlewares(app)

    return app
```

#### 3.1.2 配置管理

```python
# backend/config.py
class BaseConfig:
    SECRET_KEY = os.getenv("SECRET_KEY")
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(hours=2)
    JWT_REFRESH_TOKEN_EXPIRES = timedelta(days=30)

    # 数据库
    SQLALCHEMY_DATABASE_URI = os.getenv(
        "DATABASE_URL",
        "postgresql://eap:eap@localhost:5432/eap"
    )

    # Redis
    REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

    # LLM
    LLM_PROVIDER = os.getenv("LLM_PROVIDER", "anthropic")
    ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
    LLM_MODEL = os.getenv("LLM_MODEL", "claude-sonnet-4-20250514")

    # Agent
    AGENT_MAX_TURNS = int(os.getenv("AGENT_MAX_TURNS", "30"))
    AGENT_MAX_TOKENS = int(os.getenv("AGENT_MAX_TOKENS", "100000"))

    # 文件上传
    UPLOAD_FOLDER = os.getenv("UPLOAD_FOLDER", "/tmp/eap_uploads")
    MAX_CONTENT_LENGTH = 50 * 1024 * 1024  # 50MB


class DevelopmentConfig(BaseConfig):
    DEBUG = True
    SQLALCHEMY_ECHO = True


class ProductionConfig(BaseConfig):
    DEBUG = False


class TestingConfig(BaseConfig):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"


config = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "testing": TestingConfig,
}
```

#### 3.1.3 Flask 扩展初始化

```python
# backend/app/extensions.py
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_jwt_extended import JWTManager
from flask_cors import CORS
import redis

db = SQLAlchemy()
migrate = Migrate()
jwt_manager = JWTManager()
cors = CORS()


class RedisClient:
    def __init__(self):
        self._client = None

    def init_app(self, app):
        self._client = redis.from_url(app.config["REDIS_URL"], decode_responses=True)

    @property
    def client(self):
        return self._client


redis_client = RedisClient()
```

### 3.2 认证与 RBAC 系统

#### 3.2.1 数据模型

```python
# backend/app/core/auth/models.py

class Tenant(db.Model):
    """租户 (企业/组织)"""
    __tablename__ = "tenants"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    slug = db.Column(db.String(50), unique=True, nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    # 关系
    users = db.relationship("User", back_populates="tenant")


class User(db.Model):
    """用户"""
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey("tenants.id"), nullable=False)
    username = db.Column(db.String(80), nullable=False)
    email = db.Column(db.String(255), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login_at = db.Column(db.DateTime)

    # 关系
    tenant = db.relationship("Tenant", back_populates="users")
    roles = db.relationship("Role", secondary="user_roles", back_populates="users")


class Role(db.Model):
    """角色"""
    __tablename__ = "roles"

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey("tenants.id"), nullable=False)
    name = db.Column(db.String(80), nullable=False)          # admin, developer, viewer
    description = db.Column(db.String(255))
    is_system = db.Column(db.Boolean, default=False)          # 系统内置角色不可删

    # 关系
    users = db.relationship("User", secondary="user_roles", back_populates="roles")
    permissions = db.relationship(
        "Permission", secondary="role_permissions", back_populates="roles"
    )
    __table_args__ = (
        db.UniqueConstraint("tenant_id", "name", name="uq_role_tenant_name"),
    )


class Permission(db.Model):
    """权限点"""
    __tablename__ = "permissions"

    id = db.Column(db.Integer, primary_key=True)
    resource = db.Column(db.String(100), nullable=False)     # agent, knowledge, user, admin
    action = db.Column(db.String(50), nullable=False)        # create, read, update, delete, execute
    codename = db.Column(db.String(200), unique=True)        # agent:create, knowledge:read

    roles = db.relationship(
        "Role", secondary="role_permissions", back_populates="permissions"
    )


# 关联表
user_roles = db.Table(
    "user_roles",
    db.Column("user_id", db.Integer, db.ForeignKey("users.id"), primary_key=True),
    db.Column("role_id", db.Integer, db.ForeignKey("roles.id"), primary_key=True),
)

role_permissions = db.Table(
    "role_permissions",
    db.Column("role_id", db.Integer, db.ForeignKey("roles.id"), primary_key=True),
    db.Column("permission_id", db.Integer, db.ForeignKey("permissions.id"), primary_key=True),
)
```

#### 3.2.2 预置角色与权限

| 角色 | 权限 |
|------|------|
| **SuperAdmin** (系统级) | `*:*` — 全部权限 |
| **TenantAdmin** (租户管理员) | `user:*`, `agent:*`, `knowledge:*`, `admin:audit`, `admin:settings` |
| **Developer** (开发者) | `agent:create`, `agent:update`, `agent:execute`, `knowledge:*`, `skill:*`, `mcp:*` |
| **Viewer** (查看者) | `agent:read`, `agent:execute`, `knowledge:read` |

#### 3.2.3 JWT + Redis 会话设计

**设计原则**：JWT 仅携带用户身份标识（`sub`），角色、权限、租户等业务信息存储在 Redis 中。这样做的好处：

- **即时生效**：角色/权限变更后只需清除 Redis 缓存，无需等待 Token 过期
- **Token 瘦身**：JWT 体积小，减少网络传输开销
- **集中管控**：可随时强制下线（删除 Redis Session）
- **灵活扩展**：可在 Redis 中存储任意用户上下文，不受 JWT Claim 限制

```python
# ============ JWT Payload（极简设计）============
{
    "sub": "<user_id>",        # 用户唯一标识
    "jti": "<token_unique_id>", # Token 唯一 ID，用于主动失效
    "exp": 1234567890,
    "iat": 1234567800
}

# ============ Redis 会话缓存 ============
# Key:   session:{user_id}:{jti}
# TTL:   与 JWT access_token 过期时间一致（默认 2 小时）
# Value:
{
    "user_id": "123",
    "tenant_slug": "acme-corp",
    "tenant_name": "ACME 公司",
    "username": "zhangsan",
    "email": "zhangsan@example.com",
    "roles": ["developer", "viewer"],
    "permissions": ["agent:execute", "knowledge:read", "agent:create"],
    "login_at": "2026-07-25T10:00:00Z"
}
```

**Redis Session 生命周期**：

```
登录成功
  → 签发 JWT (仅 sub + jti + exp)
  → 写入 Redis: session:{user_id}:{jti}  (TTL = 2h)
  → 返回 access_token + refresh_token

每次 API 请求
  → 验证 JWT 签名 + 有效期
  → 从 Redis 读取 session:{user_id}:{jti}
  → 注入 Flask g 对象 (g.user_id, g.tenant_slug, g.permissions, ...)
  → 若 Redis 未命中 → 401 (Token 已失效/已被强制下线)

刷新 Token
  → 验证 refresh_token
  → 删除旧 Redis key
  → 签发新 JWT (新 jti) + 写入新 Redis key

登出
  → 删除 Redis session:{user_id}:{jti}
  → JWT 虽未过期，但 Redis 无对应 Session → 401

管理员强制下线某用户
  → 删除该用户所有 Redis session:{user_id}:*
  → 用户下次请求即返回 401
```

#### 3.2.4 认证 API

```python
# backend/app/core/auth/services.py

class AuthService:
    def __init__(self, session_manager: SessionManager):
        self.session_manager = session_manager

    def login(self, email: str, password: str) -> dict:
        """登录 - 签发极简 JWT + 写入 Redis Session"""
        user = User.query.filter_by(email=email).first()
        if not user or not check_password_hash(user.password_hash, password):
            abort(401, message="Invalid credentials")
        if not user.is_active:
            abort(403, message="Account disabled")

        # 生成唯一 jti
        jti = str(uuid.uuid4())

        # 创建 JWT（仅含身份标识）
        access_token = create_access_token(
            identity=str(user.id),
            additional_claims={"jti": jti},
        )
        refresh_token = create_refresh_token(
            identity=str(user.id),
            additional_claims={"jti": jti},
        )

        # 写入 Redis Session
        session_data = self.session_manager.create_session(
            user=user,
            jti=jti,
            ttl=current_app.config["JWT_ACCESS_TOKEN_EXPIRES"],
        )

        # 更新登录时间
        user.last_login_at = datetime.utcnow()
        db.session.commit()

        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
            "user": {
                "id": user.id,
                "username": user.username,
                "email": user.email,
                "tenant": session_data["tenant_slug"],
                "roles": session_data["roles"],
                "permissions": session_data["permissions"],
            },
        }

    def refresh_token(self, refresh_token_value: str) -> dict:
        """刷新 Token - 旧 jti → 新 jti"""
        # 验证 refresh_token
        claims = decode_token(refresh_token_value)
        user_id = claims["sub"]
        old_jti = claims["jti"]

        # 生成新 jti，更新 Redis
        new_jti = str(uuid.uuid4())
        session_data = self.session_manager.refresh_session(
            user_id, old_jti, new_jti
        )
        if not session_data:
            abort(401, message="Session expired")

        new_access_token = create_access_token(
            identity=user_id,
            additional_claims={"jti": new_jti},
        )

        return {
            "access_token": new_access_token,
            "user": {
                "id": user_id,
                "username": session_data["username"],
                "tenant": session_data["tenant_slug"],
                "roles": session_data["roles"],
                "permissions": session_data["permissions"],
            },
        }

    def logout(self, user_id: str, jti: str):
        """登出 - 删除 Redis Session"""
        self.session_manager.destroy_session(user_id, jti)
```


```
POST   /api/v1/auth/login          # 登录 (返回 access_token + refresh_token + 用户信息)
POST   /api/v1/auth/register       # 注册 (需管理员审批)
POST   /api/v1/auth/refresh        # 刷新 Token (旧 jti → 新 jti)
POST   /api/v1/auth/logout         # 登出 (删除 Redis Session)
GET    /api/v1/auth/me             # 获取当前用户信息 (从 Redis 读取)
```

#### 3.2.5 认证与鉴权流程

```python
# backend/app/middleware/auth.py
from functools import wraps
from flask import g, abort, current_app
from flask_jwt_extended import verify_jwt_in_request, get_jwt
import json

# ============ JWT 验证 + Redis Session 加载 ============

def load_user_context():
    """从 JWT 验证身份，从 Redis 加载完整用户上下文"""
    verify_jwt_in_request()
    claims = get_jwt()
    user_id = claims["sub"]
    jti = claims["jti"]

    # 从 Redis 读取会话上下文
    redis_client = current_app.extensions["redis_client"]
    session_key = f"session:{user_id}:{jti}"
    cached = redis_client.get(session_key)

    if not cached:
        abort(401, message="Session expired or invalidated")

    session_data = json.loads(cached)

    # 注入 Flask g 对象（请求级全局变量）
    g.user_id = session_data["user_id"]
    g.tenant_slug = session_data["tenant_slug"]
    g.tenant_name = session_data.get("tenant_name")
    g.username = session_data["username"]
    g.roles = session_data.get("roles", [])
    g.permissions = session_data.get("permissions", [])
    g.session_jti = jti


# ============ RBAC 权限拦截 ============

def require_permission(permission_codename: str):
    """检查当前用户是否拥有指定权限（从 Redis Session 读取）"""
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            load_user_context()
            if "*:*" in g.permissions or permission_codename in g.permissions:
                return fn(*args, **kwargs)
            abort(403, message=f"Missing permission: {permission_codename}")
        return wrapper
    return decorator


def require_tenant_context(fn=None):
    """加载租户上下文（仅验证身份，不做权限检查）"""
    @wraps(fn)
    def wrapper(*args, **kwargs):
        load_user_context()
        return fn(*args, **kwargs)
    return wrapper


# ============ Redis Session 管理 ============

class SessionManager:
    """Redis 会话生命周期管理"""

    def __init__(self, redis_client):
        self.redis = redis_client

    def create_session(self, user: User, jti: str, ttl: int = 7200) -> dict:
        """登录时创建 Redis Session"""
        session_data = {
            "user_id": str(user.id),
            "tenant_slug": user.tenant.slug,
            "tenant_name": user.tenant.name,
            "username": user.username,
            "email": user.email,
            "roles": [r.name for r in user.roles],
            "permissions": self._collect_permissions(user),
            "login_at": datetime.utcnow().isoformat(),
        }
        key = f"session:{user.id}:{jti}"
        self.redis.setex(key, ttl, json.dumps(session_data))
        return session_data

    def destroy_session(self, user_id: str, jti: str):
        """登出时销毁 Session"""
        self.redis.delete(f"session:{user_id}:{jti}")

    def destroy_all_user_sessions(self, user_id: str):
        """强制下线某用户所有会话"""
        pattern = f"session:{user_id}:*"
        keys = self.redis.keys(pattern)
        if keys:
            self.redis.delete(*keys)

    def refresh_session(self, user_id: str, old_jti: str, new_jti: str, ttl: int = 7200):
        """刷新 Token 时更新 Session"""
        old_key = f"session:{user_id}:{old_jti}"
        cached = self.redis.get(old_key)
        if cached:
            session_data = json.loads(cached)
            self.redis.delete(old_key)
            new_key = f"session:{user_id}:{new_jti}"
            self.redis.setex(new_key, ttl, json.dumps(session_data))
            return session_data
        return None

    def update_user_permissions(self, user_id: str):
        """权限变更后刷新该用户所有活跃 Session"""
        # 重建用户权限
        user = db.session.get(User, user_id)
        new_permissions = self._collect_permissions(user)
        # 更新该用户所有 Redis Session
        pattern = f"session:{user_id}:*"
        for key in self.redis.keys(pattern):
            session_data = json.loads(self.redis.get(key))
            session_data["permissions"] = new_permissions
            session_data["roles"] = [r.name for r in user.roles]
            ttl = self.redis.ttl(key)
            self.redis.setex(key, ttl, json.dumps(session_data))

    @staticmethod
    def _collect_permissions(user: User) -> list[str]:
        """从用户角色汇总所有权限"""
        permissions = set()
        for role in user.roles:
            for perm in role.permissions:
                permissions.add(perm.codename)
        return sorted(permissions)
```

### 3.3 Agent 核心集成

#### 3.3.1 Agent 编排器设计

```python
# backend/app/core/agent/orchestrator.py

class AgentOrchestrator:
    """Agent 编排器 - 核心入口"""

    def __init__(self, llm, checkpointer, store, middleware_chain):
        self.llm = llm
        self.checkpointer = checkpointer  # PostgreSQL checkpointer
        self.store = store                 # LangGraph Store (长期记忆)
        self.middleware_chain = middleware_chain
        self._graph = self._build_graph()

    def _build_graph(self):
        """构建 LangGraph StateGraph"""
        from langgraph.graph import StateGraph, MessagesState
        from langgraph.prebuilt import ToolNode

        builder = StateGraph(MessagesState)

        # 节点
        builder.add_node("agent", self._agent_node)
        builder.add_node("tools", ToolNode(self._get_tools()))

        # 边
        builder.add_edge(START, "agent")
        builder.add_conditional_edges("agent", self._should_continue)
        builder.add_edge("tools", "agent")

        return builder.compile(checkpointer=self.checkpointer)

    async def stream_chat(
        self,
        user_message: str,
        thread_id: str,
        user_id: str,
        tenant_id: str,
        config: dict | None = None
    ) -> AsyncGenerator[str, None]:
        """流式对话 - 返回 SSE 事件流"""
        run_config = {
            "configurable": {
                "thread_id": thread_id,
                "user_id": user_id,
                "tenant_id": tenant_id,
            }
        }

        # 注入记忆上下文
        memories = await self.store.search(
            namespace=(tenant_id, user_id, "memories"),
            query=user_message,
        )
        enhanced_message = self._inject_memories(user_message, memories)

        async for event in self._graph.astream_events(
            {"messages": [HumanMessage(content=enhanced_message)]},
            run_config,
            version="v2"
        ):
            yield self._format_sse_event(event)

    def _format_sse_event(self, event: dict) -> str:
        """将 LangGraph 事件格式化为 SSE 消息"""
        kind = event["event"]
        if kind == "on_chat_model_stream":
            chunk = event["data"]["chunk"]
            return f"data: {json.dumps({'type': 'token', 'content': chunk.content})}\n\n"
        elif kind == "on_tool_start":
            return f"data: {json.dumps({'type': 'tool_start', 'tool': event['name']})}\n\n"
        elif kind == "on_tool_end":
            return f"data: {json.dumps({'type': 'tool_end', 'output': str(event['data']['output'])})}\n\n"
        elif kind == "on_chain_end" and event["name"] == "LangGraph":
            return f"data: {json.dumps({'type': 'done'})}\n\n"
        return ""
```

#### 3.3.2 Agent 工厂

```python
# backend/app/core/agent/factory.py
from langchain_deep_agents import create_deep_agent

class AgentFactory:
    """创建不同配置的 Agent 实例"""

    @staticmethod
    def create_default_agent(llm, tools, middleware_chain):
        return create_deep_agent(
            model=llm,
            tools=tools,
            system_prompt=DEFAULT_SYSTEM_PROMPT,
            middleware=middleware_chain,
        )

    @staticmethod
    def create_rag_agent(llm, tools, retriever, middleware_chain):
        return create_deep_agent(
            model=llm,
            tools=[*tools, retriever.as_tool()],
            system_prompt=RAG_SYSTEM_PROMPT,
            middleware=middleware_chain,
        )

    @staticmethod
    def create_sub_agent(llm, tools, role_prompt, tool_allowlist=None):
        """创建编译式子 Agent（受限工具集）"""
        allowed_tools = (
            [t for t in tools if t.name in tool_allowlist]
            if tool_allowlist else tools
        )
        return create_deep_agent(
            model=llm,
            tools=allowed_tools,
            system_prompt=role_prompt,
        )
```

#### 3.3.3 对话 API (SSE 流式)

```python
# backend/app/api/v1/chat.py
from flask import Response, request, stream_with_context
from flask_jwt_extended import get_jwt
import json

@chat_bp.route("/chat/stream", methods=["POST"])
@require_tenant_context()
def chat_stream():
    """流式对话接口 (SSE)"""
    data = request.get_json()
    user_message = data["message"]
    thread_id = data.get("thread_id", str(uuid.uuid4()))

    tenant_slug = g.tenant_slug
    user_id = g.user_id

    def generate():
        orchestrator = current_app.extensions["agent_orchestrator"]
        try:
            for sse_event in orchestrator.stream_chat(
                user_message=user_message,
                thread_id=f"{tenant_slug}:{user_id}:{thread_id}",
                user_id=user_id,
                tenant_id=tenant_slug,
            ):
                yield sse_event
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",    # 禁用 Nginx 缓冲
            "Connection": "keep-alive",
        }
    )


@chat_bp.route("/chat/threads", methods=["GET"])
@require_tenant_context()
def list_threads():
    """获取当前用户的对话线程列表"""
    pass


@chat_bp.route("/chat/threads/<thread_id>/history", methods=["GET"])
@require_tenant_context()
def get_thread_history(thread_id):
    """获取指定线程的历史消息"""
    pass
```

### 3.4 React 前端骨架

#### 3.4.1 路由设计

```typescript
// frontend/src/router.tsx

const router = createBrowserRouter([
  {
    path: "/login",
    element: <LoginPage />,
  },
  {
    path: "/",
    element: <MainLayout />,       // 含 Sidebar + Header
    errorElement: <ErrorBoundary />,
    children: [
      { index: true, element: <Navigate to="/chat" /> },
      { path: "chat", element: <ChatPage /> },
      { path: "chat/:threadId", element: <ChatPage /> },
      {
        path: "agents",
        element: <PermissionGate permission="agent:read"><AgentManagerPage /></PermissionGate>,
      },
      {
        path: "agents/:agentId",
        element: <PermissionGate permission="agent:read"><AgentDetailPage /></PermissionGate>,
      },
      {
        path: "knowledge",
        element: <PermissionGate permission="knowledge:read"><KnowledgeBasePage /></PermissionGate>,
      },
      {
        path: "skills",
        element: <PermissionGate permission="skill:read"><SkillMarketPage /></PermissionGate>,
      },
      {
        path: "approvals",
        element: <WorkflowApprovalPage />,
      },
      {
        path: "admin",
        element: <PermissionGate permission="admin:access"><AdminLayout /></PermissionGate>,
        children: [
          { path: "users", element: <UserManagementPage /> },
          { path: "rbac", element: <RBACConfigPage /> },
          { path: "audit", element: <AuditLogPage /> },
          { path: "monitor", element: <SystemMonitorPage /> },
        ],
      },
    ],
  },
]);
```

#### 3.4.2 状态管理 (Zustand)

```typescript
// frontend/src/stores/authStore.ts
//
// 注意：JWT 仅含 sub + jti，权限/角色信息由登录 API 返回并存储在前端内存中，
// 实际鉴权在后端通过 Redis Session 完成。前端权限判断仅用于 UI 展示控制
// （如隐藏无权限的菜单项），真正的安全边界在后端。

interface AuthState {
  token: string | null;
  refreshToken: string | null;
  user: UserInfo | null;
  permissions: string[];  // 来自登录 API 响应，非 JWT Claim
  login: (email: string, password: string) => Promise<void>;
  logout: () => void;
  hasPermission: (codename: string) => boolean;
}

// frontend/src/stores/chatStore.ts
interface ChatState {
  threads: ChatThread[];
  currentThreadId: string | null;
  messages: Record<string, ChatMessage[]>;  // threadId → messages
  isStreaming: boolean;
  sendMessage: (content: string, threadId: string) => Promise<void>;
  loadThreads: () => Promise<void>;
  loadHistory: (threadId: string) => Promise<void>;
}
```

#### 3.4.3 SSE 流式客户端

```typescript
// frontend/src/api/chat.ts

export function streamChat(
  message: string,
  threadId: string,
  callbacks: {
    onToken: (text: string) => void;
    onToolStart: (toolName: string) => void;
    onToolEnd: (toolName: string, output: string) => void;
    onError: (error: string) => void;
    onDone: () => void;
  }
): AbortController {
  const controller = new AbortController();

  fetch("/api/v1/chat/stream", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${getToken()}`,
    },
    body: JSON.stringify({ message, thread_id: threadId }),
    signal: controller.signal,
  })
    .then(async (response) => {
      const reader = response.body!.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";

        for (const line of lines) {
          if (line.startsWith("data: ")) {
            const event = JSON.parse(line.slice(6));
            switch (event.type) {
              case "token": callbacks.onToken(event.content); break;
              case "tool_start": callbacks.onToolStart(event.tool); break;
              case "tool_end": callbacks.onToolEnd(event.tool, event.output); break;
              case "error": callbacks.onError(event.message); break;
              case "done": callbacks.onDone(); break;
            }
          }
        }
      }
    })
    .catch((err) => {
      if (err.name !== "AbortError") {
        callbacks.onError(err.message);
      }
    });

  return controller;
}
```

#### 3.4.4 对话页面核心组件

```tsx
// frontend/src/pages/Chat/index.tsx
function ChatPage() {
  const { threadId } = useParams();
  const { messages, isStreaming, sendMessage } = useChatStore();
  const [inputValue, setInputValue] = useState("");

  const handleSend = async () => {
    if (!inputValue.trim() || isStreaming) return;
    const content = inputValue;
    setInputValue("");
    await sendMessage(content, threadId || "new");
  };

  return (
    <div className="chat-container">
      <ChatWindow messages={messages[threadId || "new"] || []} isStreaming={isStreaming}>
        {/* 流式文本 */}
        <StreamingText />
        {/* 工具调用卡片 */}
        <ToolCallCard />
        {/* 审批卡片 (Phase 4) */}
        <ApprovalCard />
      </ChatWindow>

      <ChatInput
        value={inputValue}
        onChange={setInputValue}
        onSend={handleSend}
        disabled={isStreaming}
      />
    </div>
  );
}
```

### 3.5 Phase 1 数据库表汇总

| 表名 | 用途 | 关键字段 |
|------|------|---------|
| `tenants` | 租户 | id, name, slug |
| `users` | 用户 | id, tenant_id, email, password_hash |
| `roles` | 角色 | id, tenant_id, name |
| `permissions` | 权限点 | id, codename (如 `agent:execute`) |
| `user_roles` | 用户-角色关联 | user_id, role_id |
| `role_permissions` | 角色-权限关联 | role_id, permission_id |
| `agent_configs` | Agent 配置 | id, tenant_id, name, model, system_prompt, tools_config |
| `chat_threads` | 对话线程 | id, tenant_id, user_id, title, agent_config_id |
| `audit_logs` | 审计日志 | id, tenant_id, user_id, action, resource, detail, ip |

### 3.6 Phase 1 API 接口总览

```
# 认证
POST   /api/v1/auth/login
POST   /api/v1/auth/register
POST   /api/v1/auth/refresh
POST   /api/v1/auth/logout
GET    /api/v1/auth/me

# 用户 (管理后台)
GET    /api/v1/admin/users
POST   /api/v1/admin/users
PUT    /api/v1/admin/users/:id
DELETE /api/v1/admin/users/:id
GET    /api/v1/admin/roles
POST   /api/v1/admin/roles

# 对话
POST   /api/v1/chat/stream           # SSE 流式对话
GET    /api/v1/chat/threads          # 对话线程列表
GET    /api/v1/chat/threads/:id/history
DELETE /api/v1/chat/threads/:id

# Agent 管理
GET    /api/v1/agents                # Agent 列表
POST   /api/v1/agents                # 创建 Agent
GET    /api/v1/agents/:id            # Agent 详情
PUT    /api/v1/agents/:id            # 更新 Agent
DELETE /api/v1/agents/:id
POST   /api/v1/agents/:id/test       # 测试 Agent

# 模型配置
GET    /api/v1/admin/models          # 模型列表
POST   /api/v1/admin/models          # 添加模型
PUT    /api/v1/admin/models/:id      # 更新模型
DELETE /api/v1/admin/models/:id      # 删除模型
GET    /api/v1/models/available      # 公开：可用模型列表

# Skill 管理
GET    /api/v1/skills                # Skill 列表
GET    /api/v1/skills/:id            # Skill 详情
POST   /api/v1/skills/upload         # 上传 Skill ZIP
PUT    /api/v1/skills/:id            # 更新 Skill 元数据
DELETE /api/v1/skills/:id            # 删除 Skill
POST   /api/v1/skills/:id/toggle     # 启用/禁用

# MCP Server 管理
GET    /api/v1/mcp/servers           # MCP Server 列表
GET    /api/v1/mcp/servers/:id       # Server 详情
POST   /api/v1/mcp/servers           # 创建 Server
PUT    /api/v1/mcp/servers/:id       # 更新 Server
DELETE /api/v1/mcp/servers/:id       # 删除 Server
POST   /api/v1/mcp/servers/:id/test  # 连接测试
```

### 3.7 Phase 1 Docker Compose

```yaml
# docker-compose.yml (Phase 1)
version: "3.9"

services:
  postgres:
    image: pgvector/pgvector:pg16
    environment:
      POSTGRES_DB: eap
      POSTGRES_USER: eap
      POSTGRES_PASSWORD: eap_dev
    ports: ["5432:5432"]
    volumes:
      - pg_data:/var/lib/postgresql/data
      - ./init-db.sql:/docker-entrypoint-initdb.d/init.sql
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U eap"]
      interval: 5s

  redis:
    image: redis:7-alpine
    ports: ["6379:6379"]
    volumes: [redis_data:/data]
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s

  backend:
    build: ./backend
    command: flask run --host=0.0.0.0 --port=5000 --debug
    ports: ["5000:5000"]
    environment:
      FLASK_ENV: development
      DATABASE_URL: postgresql://eap:eap_dev@postgres:5432/eap
      REDIS_URL: redis://redis:6379/0
      ANTHROPIC_API_KEY: ${ANTHROPIC_API_KEY}
      OPENAI_API_KEY: ${OPENAI_API_KEY}
    volumes:
      - ./backend:/app
      - /var/run/docker.sock:/var/run/docker.sock  # Sandbox
    depends_on:
      postgres: { condition: service_healthy }
      redis: { condition: service_healthy }

  frontend:
    build: ./frontend
    command: npm run dev
    ports: ["3000:3000"]
    volumes:
      - ./frontend/src:/app/src
    depends_on: [backend]

volumes:
  pg_data:
  redis_data:
```

---

## 4. Phase 2: 知识库 + RAG

> **时间**: 3-4 周 | **目标**: Agent 可基于企业知识库精准回答

### 4.1 知识库数据模型

```python
# backend/app/core/knowledge/models.py

class KnowledgeCollection(db.Model):
    """知识库集合"""
    __tablename__ = "knowledge_collections"

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey("tenants.id"), nullable=False)
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    embedding_model = db.Column(db.String(100), default="text-embedding-3-small")
    chunk_size = db.Column(db.Integer, default=1000)
    chunk_overlap = db.Column(db.Integer, default=200)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    documents = db.relationship("KnowledgeDocument", back_populates="collection")
    __table_args__ = (
        db.UniqueConstraint("tenant_id", "name", name="uq_collection_tenant_name"),
    )


class KnowledgeDocument(db.Model):
    """知识库文档"""
    __tablename__ = "knowledge_documents"

    id = db.Column(db.Integer, primary_key=True)
    collection_id = db.Column(db.Integer, db.ForeignKey("knowledge_collections.id"))
    tenant_id = db.Column(db.Integer, db.ForeignKey("tenants.id"))
    filename = db.Column(db.String(500))
    file_type = db.Column(db.String(20))       # pdf, docx, md, txt
    file_size = db.Column(db.Integer)
    file_path = db.Column(db.String(1000))     # MinIO Object Key
    status = db.Column(db.String(20), default="pending")  # pending → parsing → ready → error
    chunk_count = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    collection = db.relationship("KnowledgeCollection", back_populates="documents")
```

### 4.2 文档处理管道

```python
# backend/app/core/knowledge/loader.py

class DocumentPipeline:
    """文档上传 → 解析 → 分块 → Embedding → 存储"""

    SUPPORTED_TYPES = {
        "pdf": PyPDFLoader,
        "docx": Docx2txtLoader,
        "md": UnstructuredMarkdownLoader,
        "txt": TextLoader,
    }

    def __init__(self, embedding_service, vector_store, object_store):
        self.embedder = embedding_service
        self.vector_store = vector_store  # pgvector
        self.object_store = object_store  # MinIO

    async def process(self, file, collection_id: str, tenant_id: str) -> KnowledgeDocument:
        # 1. 上传到对象存储
        object_key = f"{tenant_id}/{collection_id}/{file.filename}"
        file_path = await self.object_store.upload(object_key, file)

        # 2. 创建文档记录
        doc = KnowledgeDocument(
            collection_id=collection_id,
            tenant_id=tenant_id,
            filename=file.filename,
            file_type=file.filename.split(".")[-1],
            file_size=len(file.read()),
            file_path=file_path,
            status="parsing",
        )
        db.session.add(doc)
        db.session.commit()

        # 3. 解析文档
        loader_class = self.SUPPORTED_TYPES[doc.file_type]
        raw_docs = loader_class(file_path).load()

        # 4. 智能分块
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000,
            chunk_overlap=200,
            separators=["\n\n", "\n", "。", ".", " ", ""],
        )
        chunks = splitter.split_documents(raw_docs)

        # 5. 生成 Embedding 并存储
        texts = [chunk.page_content for chunk in chunks]
        metadatas = [
            {
                "document_id": doc.id,
                "collection_id": collection_id,
                "tenant_id": tenant_id,
                "filename": doc.filename,
                "chunk_index": i,
            }
            for i in range(len(texts))
        ]
        embeddings = await self.embedder.embed_documents(texts)

        await self.vector_store.add_embeddings(
            table_name=f"kb_{collection_id}",
            texts=texts,
            embeddings=embeddings,
            metadatas=metadatas,
            namespace=tenant_id,
        )

        # 6. 更新文档状态
        doc.status = "ready"
        doc.chunk_count = len(chunks)
        db.session.commit()

        return doc
```

### 4.3 混合检索器

```python
# backend/app/core/knowledge/retriever.py

class HybridRetriever:
    """混合检索：语义搜索 + BM25 关键词 + RRF 融合"""

    def __init__(self, vector_store, embedding_service):
        self.vector_store = vector_store
        self.embedder = embedding_service

    async def search(
        self,
        query: str,
        collection_id: str,
        tenant_id: str,
        top_k: int = 5,
        score_threshold: float = 0.7,
    ) -> list[SearchResult]:
        # 1. 查询 Embedding
        query_embedding = await self.embedder.embed_query(query)

        # 2. 语义搜索 (cosine similarity)
        semantic_results = await self.vector_store.similarity_search(
            table_name=f"kb_{collection_id}",
            embedding=query_embedding,
            namespace=tenant_id,
            limit=top_k * 2,
        )

        # 3. 关键词搜索 (PostgreSQL ts_vector + ts_rank)
        keyword_results = await self._bm25_search(
            query=query,
            collection_id=collection_id,
            tenant_id=tenant_id,
            limit=top_k,
        )

        # 4. RRF (Reciprocal Rank Fusion) 融合排序
        fused = self._rrf_fusion(
            semantic=semantic_results,
            keyword=keyword_results,
            k=60,  # RRF 平滑因子
        )

        # 5. 过滤低分结果
        return [r for r in fused[:top_k] if r.score >= score_threshold]

    async def _bm25_search(self, query, collection_id, tenant_id, limit):
        """PostgreSQL 全文搜索"""
        sql = """
        SELECT chunk_index, content, metadata,
               ts_rank(to_tsvector('simple', content), plainto_tsquery('simple', :query)) AS score
        FROM knowledge_chunks
        WHERE collection_id = :collection_id
          AND tenant_id = :tenant_id
          AND to_tsvector('simple', content) @@ plainto_tsquery('simple', :query)
        ORDER BY score DESC
        LIMIT :limit
        """
        # ... 执行查询
```

### 4.4 RAG Agent 集成

```python
# Agent 配置中注入检索工具

def create_rag_tools(retriever: HybridRetriever) -> list:
    """创建 RAG 相关工具"""
    return [
        StructuredTool.from_function(
            name="search_knowledge_base",
            description="搜索企业知识库，查找与查询相关的最新文档。适用于需要公司内部政策、流程、产品文档的场景。",
            func=retriever.search,
            args_schema=SearchInput,
        ),
        StructuredTool.from_function(
            name="list_knowledge_collections",
            description="列出当前用户可访问的知识库集合",
            func=retriever.list_collections,
        ),
    ]


# RAG 系统提示词
RAG_SYSTEM_PROMPT = """你是一个企业知识助手。回答问题时：
1. 优先使用 search_knowledge_base 工具检索公司内部知识
2. 如果知识库没有相关结果，可以结合你的通用知识回答
3. 回答时必须标明信息来源（文档名称、章节）
4. 如果检索到的信息不完整或过时，需要如实告知用户
"""
```

### 4.5 知识库管理前端

```tsx
// frontend/src/pages/KnowledgeBase/index.tsx
function KnowledgeBasePage() {
  const [collections, setCollections] = useState<Collection[]>([]);
  const [selectedCollection, setSelectedCollection] = useState<string | null>(null);

  return (
    <div className="knowledge-page">
      {/* 左侧：知识库列表 */}
      <aside className="collection-sidebar">
        <Button type="primary" onClick={handleCreateCollection}>
          新建知识库
        </Button>
        <CollectionList
          collections={collections}
          selectedId={selectedCollection}
          onSelect={setSelectedCollection}
        />
      </aside>

      {/* 右侧：知识库详情 */}
      <main className="collection-detail">
        {selectedCollection && (
          <>
            {/* 文档上传区域 */}
            <DocumentUpload
              collectionId={selectedCollection}
              onUploadComplete={refreshDocuments}
            />

            {/* 文档列表 */}
            <DocumentList
              collectionId={selectedCollection}
              onDelete={handleDeleteDocument}
            />

            {/* 检索测试面板 */}
            <SearchTest collectionId={selectedCollection} />

            {/* 分块预览 */}
            <ChunkPreview collectionId={selectedCollection} />
          </>
        )}
      </main>
    </div>
  );
}
```

### 4.6 Phase 2 新增 API

```
# 知识库
POST   /api/v1/knowledge/collections
GET    /api/v1/knowledge/collections
GET    /api/v1/knowledge/collections/:id
PUT    /api/v1/knowledge/collections/:id
DELETE /api/v1/knowledge/collections/:id

# 文档
POST   /api/v1/knowledge/collections/:id/documents/upload
GET    /api/v1/knowledge/collections/:id/documents
DELETE /api/v1/knowledge/documents/:id
GET    /api/v1/knowledge/documents/:id/chunks

# 检索
POST   /api/v1/knowledge/search           # 检索测试
POST   /api/v1/knowledge/search/feedback  # 检索反馈 (相关性标注)
```

---

## 5. Phase 3: 多 Agent + 编排 + Skill/MCP

> **时间**: 4-5 周 | **目标**: 支持复杂任务的多 Agent 协作

### 5.1 子 Agent 系统

```python
# backend/app/core/agent/orchestrator.py (扩展)

class MultiAgentOrchestrator:
    """多 Agent 编排器"""

    def __init__(self, llm, checkpointer, store):
        self.llm = llm
        self.checkpointer = checkpointer
        self.store = store
        # 子 Agent 注册表
        self.sub_agents: dict[str, AgentDefinition] = {}

    def register_sub_agent(self, definition: AgentDefinition):
        """注册子 Agent 定义"""
        self.sub_agents[definition.name] = definition

    async def delegate_to_sub_agent(
        self,
        agent_name: str,
        task: str,
        context: dict,
        parent_thread_id: str,
        mode: str = "inline",  # inline | compiled | async
    ) -> AgentResult:
        """委托任务给子 Agent"""
        definition = self.sub_agents[agent_name]

        match mode:
            case "inline":
                # 阻塞式，父 Agent 等待结果
                return await self._run_inline_sub_agent(definition, task, context)
            case "compiled":
                # 编译式，受限工具集
                return await self._run_compiled_sub_agent(definition, task, context)
            case "async":
                # 异步式，非阻塞并行
                task_id = await self._dispatch_async(definition, task, context)
                return AgentResult(status="dispatched", task_id=task_id)

    def build_supervisor_graph(self) -> StateGraph:
        """构建监督者 Agent 图"""
        builder = StateGraph(SupervisorState)

        # 路由节点
        builder.add_node("supervisor", self._supervisor_node)
        builder.add_node("researcher", self._create_sub_agent_node("researcher"))
        builder.add_node("coder", self._create_sub_agent_node("coder"))
        builder.add_node("analyst", self._create_sub_agent_node("analyst"))

        # 监督者路由
        builder.add_conditional_edges(
            "supervisor",
            self._route_to_worker,
            {
                "researcher": "researcher",
                "coder": "coder",
                "analyst": "analyst",
                "FINISH": END,
            },
        )

        # 每个 Worker 完成后回到监督者
        for worker in ["researcher", "coder", "analyst"]:
            builder.add_edge(worker, "supervisor")

        return builder.compile(checkpointer=self.checkpointer)
```

### 5.2 Skill 系统

#### 5.2.1 Skill 定义格式

```markdown
<!-- skills/web_search/SKILL.md -->
---
name: web_search
description: 互联网搜索技能，使用搜索引擎获取最新信息
version: 1.0.0
author: EAP Team
tools:
  - web_search
  - fetch_webpage
tags:
  - search
  - research
---

# Web Search Skill

## 触发条件
当用户提问涉及以下场景时使用：
- 需要最新新闻或实时信息
- 需要查找互联网上的公开资料
- 需要比较不同来源的信息

## 执行步骤
1. 使用 `web_search` 工具执行搜索
2. 对搜索结果进行相关性评估
3. 如有必要，使用 `fetch_webpage` 获取详细内容
4. 综合多源信息，给出有引用的回答

## 约束
- 最多执行 3 次搜索
- 每次搜索返回前 5 条结果
- 必须标明信息来源 URL
```

#### 5.2.2 Skill 管理器

```python
# backend/app/core/agent/skills/registry.py

class SkillRegistry:
    """Skill 注册表"""

    def __init__(self, skills_dir: str = "skills"):
        self.skills_dir = Path(skills_dir)
        self._skills: dict[str, Skill] = {}

    def discover(self):
        """扫描 SKILL.md 文件，发现并注册所有 Skill"""
        for skill_file in self.skills_dir.glob("*/SKILL.md"):
            skill = Skill.from_markdown(skill_file)
            self._skills[skill.name] = skill

    def get_skill(self, name: str) -> Skill | None:
        return self._skills.get(name)

    def list_skills(self, tags: list[str] | None = None) -> list[Skill]:
        if tags:
            return [s for s in self._skills.values() if set(tags) & set(s.tags)]
        return list(self._skills.values())

    def get_skill_prompt(self, name: str) -> str:
        """获取 Skill 的运行时提示词（渐进式披露）"""
        skill = self._skills[name]
        return f"""## Skill: {skill.name}
{skill.description}

触发: {skill.trigger_condition}
步骤: {skill.steps}
约束: {skill.constraints}
"""
```

#### 5.2.3 Skill 管理 API

```
GET    /api/v1/skills                  # Skill 列表
POST   /api/v1/skills                  # 创建 Skill
GET    /api/v1/skills/:name            # Skill 详情
PUT    /api/v1/skills/:name            # 更新 Skill
DELETE /api/v1/skills/:name            # 删除 Skill
POST   /api/v1/skills/:name/test       # 测试 Skill
POST   /api/v1/skills/:name/enable     # 启用/禁用
```

### 5.3 MCP 集成

```python
# backend/app/core/mcp/manager.py
from langchain_mcp_adapters.client import MultiServerMCPClient

class MCPServerManager:
    """MCP Server 生命周期管理"""

    def __init__(self, config_dir: str = "mcp_servers"):
        self.config_dir = Path(config_dir)
        self._clients: dict[str, MultiServerMCPClient] = {}
        self._server_configs: dict[str, dict] = {}

    def load_configs(self):
        """从配置文件加载 MCP Server 定义"""
        for config_file in self.config_dir.glob("*.json"):
            with open(config_file) as f:
                config = json.load(f)
                self._server_configs[config["name"]] = config

    async def connect(self, server_name: str) -> list[BaseTool]:
        """连接 MCP Server 并获取工具列表"""
        config = self._server_configs[server_name]

        client = MultiServerMCPClient({
            server_name: {
                "command": config["command"],
                "args": config.get("args", []),
                "env": config.get("env", {}),
            }
        })

        tools = await client.get_tools()
        self._clients[server_name] = client
        return tools

    async def disconnect(self, server_name: str):
        """断开 MCP Server"""
        if server_name in self._clients:
            await self._clients[server_name].close()
            del self._clients[server_name]

    def get_server_status(self) -> list[dict]:
        """获取所有 MCP Server 状态"""
        return [
            {
                "name": name,
                "connected": name in self._clients,
                "tool_count": len(client.list_tools()) if (client := self._clients.get(name)) else 0,
            }
            for name in self._server_configs
        ]
```

### 5.4 Agent 管理前端

```tsx
// frontend/src/pages/AgentManager/AgentConfigForm.tsx
function AgentConfigForm({ agent, onSave }: Props) {
  const [form] = Form.useForm();

  return (
    <Form form={form} layout="vertical" onFinish={onSave}>
      {/* 基本信息 */}
      <Form.Item name="name" label="Agent 名称" rules={[{ required: true }]}>
        <Input />
      </Form.Item>

      <Form.Item name="model" label="模型">
        <Select options={[
          { label: "Claude Sonnet 4", value: "claude-sonnet-4-20250514" },
          { label: "Claude Opus 4", value: "claude-opus-4-20250514" },
          { label: "GPT-4o", value: "gpt-4o" },
          { label: "DeepSeek V3", value: "deepseek-v3" },
        ]} />
      </Form.Item>

      <Form.Item name="system_prompt" label="系统提示词">
        <TextArea rows={8} />
      </Form.Item>

      {/* 工具选择 */}
      <Form.Item name="tools" label="工具集">
        <Checkbox.Group>
          <Checkbox value="web_search">网络搜索</Checkbox>
          <Checkbox value="code_execution">代码执行</Checkbox>
          <Checkbox value="knowledge_search">知识库检索</Checkbox>
          <Checkbox value="calculator">计算器</Checkbox>
          <Checkbox value="api_caller">API 调用</Checkbox>
        </Checkbox.Group>
      </Form.Item>

      {/* 子 Agent 配置 */}
      <Form.Item label="子 Agent">
        <SubAgentEditor />
      </Form.Item>

      {/* Skill 绑定 */}
      <Form.Item name="skills" label="绑定 Skill">
        <Select mode="multiple" options={skillOptions} />
      </Form.Item>

      {/* MCP Server 绑定 */}
      <Form.Item name="mcp_servers" label="MCP Server">
        <Select mode="multiple" options={mcpOptions} />
      </Form.Item>

      {/* 权限控制 */}
      <Form.Item name="permission_mode" label="权限模式">
        <Radio.Group>
          <Radio value="default">默认 (关键操作需审批)</Radio>
          <Radio value="acceptEdits">自动接受编辑</Radio>
          <Radio value="dontAsk">静默执行</Radio>
        </Radio.Group>
      </Form.Item>

      <Button type="primary" htmlType="submit">保存</Button>
    </Form>
  );
}
```

### 5.5 Phase 3 新增 API

```
# Agent 管理
POST   /api/v1/agents/:id/sub-agents         # 添加子 Agent
DELETE /api/v1/agents/:id/sub-agents/:sub_id # 移除子 Agent
POST   /api/v1/agents/:id/orchestration       # 更新编排配置

# Skill
GET    /api/v1/skills
POST   /api/v1/skills
GET    /api/v1/skills/:name
PUT    /api/v1/skills/:name
DELETE /api/v1/skills/:name

# MCP
GET    /api/v1/mcp/servers
POST   /api/v1/mcp/servers
GET    /api/v1/mcp/servers/:name
PUT    /api/v1/mcp/servers/:name
DELETE /api/v1/mcp/servers/:name
POST   /api/v1/mcp/servers/:name/connect
POST   /api/v1/mcp/servers/:name/disconnect
GET    /api/v1/mcp/servers/:name/tools

# 编排测试
POST   /api/v1/orchestration/test            # 测试编排图
POST   /api/v1/orchestration/deploy          # 部署编排
```

---

## 6. Phase 4: 企业特性

> **时间**: 3-4 周 | **目标**: 满足企业级安全与治理要求

### 6.1 安全围栏系统

```python
# backend/app/core/guardrails/chain.py

class GuardrailChain:
    """安全围栏链 - 多层拦截"""

    def __init__(self):
        self.guardrails: list[BaseGuardrail] = []

    def add(self, guardrail: BaseGuardrail):
        self.guardrails.append(guardrail)

    async def check_input(self, user_input: str, context: dict) -> GuardrailResult:
        """检查用户输入"""
        for guardrail in self.guardrails:
            result = await guardrail.check(user_input, context)
            if not result.passed:
                return result  # 前面拦截即返回
        return GuardrailResult(passed=True)

    async def check_output(self, agent_output: str, context: dict) -> GuardrailResult:
        """检查 Agent 输出"""
        for guardrail in self.guardrails:
            result = await guardrail.check(agent_output, context)
            if not result.passed:
                return result
        return GuardrailResult(passed=True)

    async def check_tool_call(
        self, tool_name: str, tool_args: dict, context: dict
    ) -> GuardrailResult:
        """检查工具调用"""
        for guardrail in self.guardrails:
            if hasattr(guardrail, "check_tool"):
                result = await guardrail.check_tool(tool_name, tool_args, context)
                if not result.passed:
                    return result
        return GuardrailResult(passed=True)
```

#### 6.1.1 PII 检测围栏

```python
# backend/app/core/guardrails/pii.py
import re
from presidio_analyzer import AnalyzerEngine

class PIIGuardrail(BaseGuardrail):
    """检测并脱敏个人身份信息"""

    PII_PATTERNS = {
        "EMAIL": r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b",
        "PHONE_CN": r"1[3-9]\d{9}",
        "ID_CARD_CN": r"\d{17}[\dXx]",
        "CREDIT_CARD": r"\b\d{4}[- ]?\d{4}[- ]?\d{4}[- ]?\d{4}\b",
        "IP_ADDRESS": r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b",
    }

    def __init__(self, mode: str = "redact"):  # redact | mask | hash | block
        self.mode = mode
        self.analyzer = AnalyzerEngine()  # Microsoft Presidio

    async def check(self, text: str, context: dict) -> GuardrailResult:
        findings = []

        # 1. 正则快速扫描
        for pii_type, pattern in self.PII_PATTERNS.items():
            if re.search(pattern, text):
                findings.append({"type": pii_type, "method": "regex"})

        # 2. Presidio 语义分析
        presidio_results = self.analyzer.analyze(text=text, language="zh")
        for r in presidio_results:
            findings.append({"type": r.entity_type, "method": "ml", "score": r.score})

        if findings and self.mode == "block":
            return GuardrailResult(
                passed=False,
                reason=f"检测到敏感信息: {[f['type'] for f in findings]}",
                details={"findings": findings},
            )

        if findings:
            # 脱敏处理
            sanitized = self._sanitize(text, findings)
            return GuardrailResult(
                passed=True,
                modified_text=sanitized,
                details={"findings": findings, "action": f"sanitized ({self.mode})"},
            )

        return GuardrailResult(passed=True)
```

#### 6.1.2 内容审核围栏

```python
class ContentSafetyGuardrail(BaseGuardrail):
    """内容安全审核"""

    BLOCKED_KEYWORDS = [
        "hack", "exploit", "injection",  # 攻击类
        # ... 企业自定义关键词
    ]

    FORBIDDEN_PATTERNS = [
        r"(?i)drop\s+table",           # SQL 注入
        r"(?i)<script.*?>",             # XSS
        r"(?i)rm\s+-rf\s+/",           # 危险命令
        r"(?i)curl.*\|\s*bash",        # 管道执行
    ]

    async def check(self, text: str, context: dict) -> GuardrailResult:
        # 关键词检查
        for keyword in self.BLOCKED_KEYWORDS:
            if keyword.lower() in text.lower():
                return GuardrailResult(
                    passed=False,
                    reason=f"输入包含禁止关键词",
                    details={"matched": keyword},
                )

        # 模式检查
        for pattern in self.FORBIDDEN_PATTERNS:
            if re.search(pattern, text):
                return GuardrailResult(
                    passed=False,
                    reason="检测到潜在危险模式",
                    details={"pattern": pattern},
                )

        return GuardrailResult(passed=True)
```

#### 6.1.3 Middleware Chain 组装

```python
# Deep Agents Middleware 集成
from langchain_deep_agents.middleware import (
    FilesystemMiddleware,
    HumanInTheLoopMiddleware,
    MemoryMiddleware,
)

def build_middleware_chain(guardrail_chain, memory_store):
    return [
        # 1. PII/安全围栏 (前置)
        GuardrailMiddleware(guardrail_chain, stage="input"),
        # 2. 记忆注入
        MemoryMiddleware(store=memory_store),
        # 3. 文件系统权限
        FilesystemMiddleware(
            backend="local",
            permissions=[
                FilesystemPermission(path="/tmp/eap/**", mode="allow", operations=["read", "write"]),
                FilesystemPermission(path="/data/**", mode="allow", operations=["read"]),
                FilesystemPermission(path="~/**", mode="deny"),
            ],
        ),
        # 4. 人机协同
        HumanInTheLoopMiddleware(
            interrupt_on={
                "execute_shell": {"allowed_decisions": ["approve", "reject"]},
                "write_file": {"allowed_decisions": ["approve", "edit", "reject"]},
                "call_api": {"allowed_decisions": ["approve", "reject"]},
            }
        ),
        # 5. 安全围栏 (后置)
        GuardrailMiddleware(guardrail_chain, stage="output"),
    ]
```

### 6.2 人机协同 (HITL)

#### 6.2.1 审批工作流模型

```python
# backend/app/models/workflow.py

class ApprovalRequest(db.Model):
    """审批请求"""
    __tablename__ = "approval_requests"

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey("tenants.id"))
    thread_id = db.Column(db.String(255))                       # LangGraph Thread ID
    checkpoint_id = db.Column(db.String(255))                   # 检查点 ID
    agent_name = db.Column(db.String(100))
    tool_name = db.Column(db.String(100))                       # 待审批的工具
    tool_args = db.Column(db.JSON)                              # 工具参数
    status = db.Column(db.String(20), default="pending")        # pending | approved | rejected | edited
    requested_by = db.Column(db.Integer, db.ForeignKey("users.id"))
    requested_at = db.Column(db.DateTime, default=datetime.utcnow)
    resolved_by = db.Column(db.Integer, db.ForeignKey("users.id"))
    resolved_at = db.Column(db.DateTime)
    decision = db.Column(db.String(20))                         # approve | reject | edit
    edited_args = db.Column(db.JSON)                            # 编辑后的参数
    comment = db.Column(db.Text)                                # 审批意见

    # 审批策略
    required_roles = db.Column(db.ARRAY(db.String))             # ["admin", "security_lead"]
    require_m_of_n = db.Column(db.Integer, default=1)
    current_approvals = db.Column(db.Integer, default=0)
```

#### 6.2.2 审批 API

```python
# backend/app/api/v1/workflow.py

@workflow_bp.route("/approvals", methods=["GET"])
@require_tenant_context()
def list_pending_approvals():
    """获取待审批列表"""
    approvals = ApprovalRequest.query.filter_by(
        tenant_id=g.tenant_slug,
        status="pending",
    ).all()
    return jsonify([a.to_dict() for a in approvals])


@workflow_bp.route("/approvals/<id>/approve", methods=["POST"])
@require_permission("admin:approve")
def approve_request(id):
    """批准 - 通过 LangGraph Command 恢复执行"""
    approval = ApprovalRequest.query.get_or_404(id)

    # 恢复 LangGraph 执行
    orchestrator = current_app.extensions["agent_orchestrator"]
    orchestrator.resume_from_checkpoint(
        thread_id=approval.thread_id,
        checkpoint_id=approval.checkpoint_id,
        command=Command(resume={"decision": "approve"}),
    )

    approval.status = "approved"
    approval.resolved_by = g.user_id
    approval.resolved_at = datetime.utcnow()
    db.session.commit()

    return jsonify({"status": "approved"})


@workflow_bp.route("/approvals/<id>/reject", methods=["POST"])
@require_permission("admin:approve")
def reject_request(id):
    """拒绝 - 返回拒绝信息给 Agent"""
    data = request.get_json()
    approval = ApprovalRequest.query.get_or_404(id)

    orchestrator = current_app.extensions["agent_orchestrator"]
    orchestrator.resume_from_checkpoint(
        thread_id=approval.thread_id,
        checkpoint_id=approval.checkpoint_id,
        command=Command(resume={
            "decision": "reject",
            "reason": data.get("reason", "Rejected by admin"),
        }),
    )

    approval.status = "rejected"
    approval.resolved_by = g.user_id
    approval.comment = data.get("reason")
    approval.resolved_at = datetime.utcnow()
    db.session.commit()

    return jsonify({"status": "rejected"})


@workflow_bp.route("/approvals/<id>/edit", methods=["POST"])
@require_permission("admin:approve")
def edit_and_approve(id):
    """编辑参数后批准"""
    data = request.get_json()
    approval = ApprovalRequest.query.get_or_404(id)

    orchestrator = current_app.extensions["agent_orchestrator"]
    orchestrator.resume_from_checkpoint(
        thread_id=approval.thread_id,
        checkpoint_id=approval.checkpoint_id,
        command=Command(resume={
            "decision": "approve",
            "edited_args": data.get("edited_args"),
        }),
    )

    approval.status = "approved"
    approval.decision = "edit"
    approval.edited_args = data.get("edited_args")
    approval.resolved_by = g.user_id
    approval.resolved_at = datetime.utcnow()
    db.session.commit()

    return jsonify({"status": "approved_with_edits"})
```

### 6.3 长期记忆系统

```python
# backend/app/core/memory/store.py
from langgraph.store.memory import PostgresStore

class LongTermMemoryStore:
    """基于 LangGraph Store 的长期记忆"""

    def __init__(self, conn_string: str):
        self.store = PostgresStore.from_conn_string(conn_string)
        self.store.setup()  # 自动建表

    async def remember(self, tenant_id: str, user_id: str, key: str, value: dict):
        """存储一条记忆"""
        await self.store.put(
            namespace=(tenant_id, user_id, "memories"),
            key=key,
            value={
                **value,
                "created_at": datetime.utcnow().isoformat(),
            },
        )

    async def recall(self, tenant_id: str, user_id: str, query: str, top_k: int = 5):
        """语义搜索相关记忆"""
        results = await self.store.search(
            namespace=(tenant_id, user_id, "memories"),
            query=query,
            limit=top_k,
        )
        return results

    async def forget(self, tenant_id: str, user_id: str, key: str):
        """删除一条记忆"""
        await self.store.delete(
            namespace=(tenant_id, user_id, "memories"),
            key=key,
        )

    async def list_memories(self, tenant_id: str, user_id: str, limit: int = 50):
        """列出最近记忆"""
        return await self.store.list(
            namespace=(tenant_id, user_id, "memories"),
            limit=limit,
        )
```

### 6.4 审计日志

```python
# backend/app/middleware/audit.py

class AuditLogger:
    """全量审计日志记录"""

    ACTION_MAP = {
        "user:login": "用户登录",
        "user:logout": "用户登出",
        "agent:execute": "Agent 执行",
        "agent:tool_call": "工具调用",
        "agent:sub_agent": "子 Agent 委托",
        "knowledge:search": "知识库检索",
        "knowledge:upload": "文档上传",
        "admin:user_create": "创建用户",
        "admin:role_update": "修改角色",
        "approval:approve": "审批通过",
        "approval:reject": "审批拒绝",
    }

    def log(self, tenant_id: str, user_id: str, action: str, resource: str,
            detail: dict | None = None, ip: str | None = None, status: str = "success"):
        entry = AuditLog(
            tenant_id=tenant_id,
            user_id=user_id,
            action=action,
            resource=resource,
            detail=detail or {},
            ip=ip,
            status=status,
        )
        db.session.add(entry)
        db.session.commit()


# 审计日志查询 (管理后台)
GET    /api/v1/admin/audit-logs?action=agent:execute&from=2026-07-01&to=2026-07-25&user_id=123
```

### 6.5 Phase 4 新增数据表

| 表名 | 用途 |
|------|------|
| `approval_requests` | 审批请求（HITL） |
| `audit_logs` | 审计日志（已有，Phase 1 预留） |
| `guardrail_rules` | 自定义围栏规则 |
| `memory_entries` | LangGraph Store 自动管理 |
| `checkpoint_blobs` | LangGraph Checkpoint (自动) |
| `checkpoint_writes` | LangGraph Checkpoint (自动) |

---

## 7. Phase 5: 可观测性 + 运维

> **时间**: 2-3 周 | **目标**: 生产级可观测与运维能力

### 7.1 全链路追踪 (LangSmith + OTel)

```python
# backend/app/extensions.py (扩展)

def init_observability(app: Flask):
    """初始化可观测性"""

    # 1. LangSmith 追踪
    if app.config.get("LANGSMITH_API_KEY"):
        os.environ["LANGSMITH_TRACING"] = "true"
        os.environ["LANGSMITH_PROJECT"] = app.config["LANGSMITH_PROJECT"]

    # 2. OpenTelemetry
    from opentelemetry import trace
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    if app.config.get("OTEL_EXPORTER_ENDPOINT"):
        provider = TracerProvider()
        exporter = OTLPSpanExporter(endpoint=app.config["OTEL_EXPORTER_ENDPOINT"])
        provider.add_span_processor(BatchSpanProcessor(exporter))
        trace.set_tracer_provider(provider)

    # 3. 健康检查端点
    @app.route("/health")
    def health_check():
        checks = {
            "database": check_database(),
            "redis": check_redis(),
            "llm": check_llm_connectivity(),
        }
        status = all(v["status"] == "ok" for v in checks.values())
        return jsonify({"status": "healthy" if status else "degraded", "checks": checks})


# 自定义 Span 装饰器
def trace_agent_call(agent_name: str):
    """为 Agent 调用添加 Trace Span"""
    def decorator(fn):
        @wraps(fn)
        async def wrapper(*args, **kwargs):
            tracer = trace.get_tracer(__name__)
            with tracer.start_as_current_span(
                f"agent.{agent_name}",
                attributes={
                    "agent.name": agent_name,
                    "agent.model": kwargs.get("model", "unknown"),
                    "tenant.id": kwargs.get("tenant_id", ""),
                },
            ) as span:
                try:
                    result = await fn(*args, **kwargs)
                    span.set_attribute("status", "success")
                    return result
                except Exception as e:
                    span.set_attribute("status", "error")
                    span.record_exception(e)
                    raise
        return wrapper
    return decorator
```

### 7.2 成本监控

```python
# backend/app/core/monitoring/cost_tracker.py

class CostTracker:
    """Token 消耗与成本追踪"""

    def __init__(self, redis_client):
        self.redis = redis_client

    # 模型定价 ($/1M tokens)
    PRICING = {
        "claude-opus-4-20250514": {"input": 15.00, "output": 75.00},
        "claude-sonnet-4-20250514": {"input": 3.00, "output": 15.00},
        "claude-haiku-4-5-20251001": {"input": 0.80, "output": 4.00},
        "gpt-4o": {"input": 2.50, "output": 10.00},
        "deepseek-v3": {"input": 0.27, "output": 1.10},
    }

    def record_usage(self, tenant_id: str, user_id: str, model: str,
                     input_tokens: int, output_tokens: int):
        """记录单次使用的 Token 消耗"""
        pricing = self.PRICING.get(model, {"input": 0, "output": 0})
        cost = (
            input_tokens / 1_000_000 * pricing["input"]
            + output_tokens / 1_000_000 * pricing["output"]
        )

        today = datetime.utcnow().strftime("%Y-%m-%d")

        pipe = self.redis.pipeline()
        # 按天聚合
        pipe.hincrby(f"cost:{tenant_id}:{today}", "input_tokens", input_tokens)
        pipe.hincrby(f"cost:{tenant_id}:{today}", "output_tokens", output_tokens)
        pipe.hincrbyfloat(f"cost:{tenant_id}:{today}", "cost_usd", cost)
        # 按用户聚合
        pipe.hincrby(f"cost:{tenant_id}:user:{user_id}:{today}", "input_tokens", input_tokens)
        pipe.hincrby(f"cost:{tenant_id}:user:{user_id}:{today}", "output_tokens", output_tokens)
        pipe.hincrbyfloat(f"cost:{tenant_id}:user:{user_id}:{today}", "cost_usd", cost)
        pipe.execute()

    def get_tenant_daily_cost(self, tenant_id: str, date: str) -> dict:
        return self.redis.hgetall(f"cost:{tenant_id}:{date}")

    def get_tenant_monthly_summary(self, tenant_id: str, month: str) -> dict:
        """汇总月度成本"""
        total_cost = 0
        total_tokens = 0
        # 遍历当月每天，汇总
        # ...
        return {"total_cost_usd": total_cost, "total_tokens": total_tokens}
```

### 7.3 系统监控仪表盘 API

```
GET    /api/v1/admin/monitor/dashboard       # 仪表盘汇总
GET    /api/v1/admin/monitor/cost/tenant     # 租户成本
GET    /api/v1/admin/monitor/cost/user       # 用户成本
GET    /api/v1/admin/monitor/usage/agents    # Agent 使用统计
GET    /api/v1/admin/monitor/usage/models    # 模型使用分布
GET    /api/v1/admin/monitor/latency         # P50/P95/P99 延迟
GET    /api/v1/admin/monitor/errors          # 错误率趋势
GET    /api/v1/admin/monitor/concurrency     # 并发会话数
```

### 7.4 前端监控仪表盘

```tsx
// frontend/src/pages/Admin/SystemMonitor/index.tsx
function SystemMonitorPage() {
  return (
    <div className="monitor-dashboard">
      {/* 顶部指标卡片 */}
      <Row gutter={16}>
        <Col span={6}>
          <StatCard title="今日 Token" value="2.4M" trend="+12%" />
        </Col>
        <Col span={6}>
          <StatCard title="今日成本" value="$12.40" trend="-5%" />
        </Col>
        <Col span={6}>
          <StatCard title="活跃会话" value="48" />
        </Col>
        <Col span={6}>
          <StatCard title="错误率" value="0.3%" trend="stable" />
        </Col>
      </Row>

      {/* 图表区域 */}
      <Row gutter={16}>
        <Col span={12}>
          <Card title="Token 消耗趋势">
            <LineChart data={tokenTrendData} />
          </Card>
        </Col>
        <Col span={12}>
          <Card title="成本趋势 (USD)">
            <AreaChart data={costTrendData} />
          </Card>
        </Col>
      </Row>

      <Row gutter={16}>
        <Col span={8}>
          <Card title="模型使用分布">
            <PieChart data={modelUsageData} />
          </Card>
        </Col>
        <Col span={8}>
          <Card title="响应延迟 (P50/P95/P99)">
            <LineChart data={latencyData} />
          </Card>
        </Col>
        <Col span={8}>
          <Card title="Agent 调用排行">
            <BarChart data={agentUsageData} />
          </Card>
        </Col>
      </Row>

      {/* 实时日志 */}
      <Card title="最近审计日志">
        <AuditLogTable />
      </Card>
    </div>
  );
}
```

---

## 8. 部署架构

### 8.1 开发环境

```yaml
# docker-compose.yml (完整版 - Phase 5)
version: "3.9"

services:
  # 基础设施
  postgres:
    image: pgvector/pgvector:pg16
    environment:
      POSTGRES_DB: eap
      POSTGRES_USER: eap
      POSTGRES_PASSWORD: eap_dev
    ports: ["5432:5432"]
    volumes:
      - pg_data:/var/lib/postgresql/data
      - ./init-db.sql:/docker-entrypoint-initdb.d/init.sql

  redis:
    image: redis:7-alpine
    ports: ["6379:6379"]

  minio:
    image: minio/minio:latest
    command: server /data --console-address ":9001"
    ports: ["9000:9000", "9001:9001"]
    environment:
      MINIO_ROOT_USER: minioadmin
      MINIO_ROOT_PASSWORD: minioadmin

  # 应用服务
  backend:
    build:
      context: ./backend
      dockerfile: Dockerfile.dev
    command: flask run --host=0.0.0.0 --port=5000 --debug
    ports: ["5000:5000"]
    env_file: .env
    volumes:
      - ./backend:/app
      - ./skills:/app/skills
      - ./mcp_servers:/app/mcp_servers
      - /var/run/docker.sock:/var/run/docker.sock
    depends_on: [postgres, redis, minio]

  frontend:
    build:
      context: ./frontend
      dockerfile: Dockerfile.dev
    command: npm run dev
    ports: ["3000:3000"]
    volumes:
      - ./frontend/src:/app/src

  # 反向代理
  nginx:
    image: nginx:alpine
    ports: ["80:80"]
    volumes:
      - ./nginx.dev.conf:/etc/nginx/nginx.conf
    depends_on: [backend, frontend]

volumes:
  pg_data:
  redis_data:
  minio_data:
```

### 8.2 生产环境 (Kubernetes)

```yaml
# deploy/k8s/backend-deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: eap-backend
spec:
  replicas: 3
  selector:
    matchLabels:
      app: eap-backend
  template:
    metadata:
      labels:
        app: eap-backend
    spec:
      containers:
        - name: backend
          image: registry.example.com/eap-backend:latest
          ports:
            - containerPort: 5000
          env:
            - name: FLASK_ENV
              value: "production"
            - name: DATABASE_URL
              valueFrom:
                secretKeyRef:
                  name: eap-secrets
                  key: database-url
            - name: REDIS_URL
              valueFrom:
                secretKeyRef:
                  name: eap-secrets
                  key: redis-url
          resources:
            requests:
              memory: "512Mi"
              cpu: "500m"
            limits:
              memory: "2Gi"
              cpu: "2000m"
          livenessProbe:
            httpGet:
              path: /health
              port: 5000
            initialDelaySeconds: 30
            periodSeconds: 10
          readinessProbe:
            httpGet:
              path: /health
              port: 5000
            initialDelaySeconds: 5
            periodSeconds: 5
---
apiVersion: v1
kind: Service
metadata:
  name: eap-backend
spec:
  selector:
    app: eap-backend
  ports:
    - port: 5000
      targetPort: 5000
  type: ClusterIP
---
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: eap-backend-hpa
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: eap-backend
  minReplicas: 3
  maxReplicas: 20
  metrics:
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: 70
    - type: Resource
      resource:
        name: memory
        target:
          type: Utilization
          averageUtilization: 80
```

### 8.3 生产环境拓扑

```
                    ┌──────────────┐
                    │  CloudFlare   │
                    │  DNS + CDN    │
                    └──────┬───────┘
                           │
                    ┌──────▼───────┐
                    │  Nginx       │
                    │  Ingress     │
                    │  + SSL       │
                    └──────┬───────┘
                           │
              ┌────────────┼────────────┐
              │            │            │
        ┌─────▼─────┐ ┌───▼────┐ ┌────▼─────┐
        │ Frontend  │ │ API GW │ │ WebSocket│
        │ (Static)  │ │ (Kong) │ │ Gateway  │
        └───────────┘ └───┬────┘ └────┬─────┘
                          │           │
              ┌───────────┼───────────┘
              │           │
        ┌─────▼───────────▼──────┐
        │   Backend Service      │
        │   (K8s Deployment      │
        │    HPA: 3-20 pods)     │
        └───────────┬────────────┘
                    │
     ┌──────────────┼──────────────┐
     │              │              │
┌────▼────┐  ┌─────▼──────┐ ┌────▼────┐
│PostgreSQL│ │  Redis     │ │ MinIO   │
│+pgvector │ │  Cluster   │ │ Cluster │
│Primary+  │ │            │ │         │
│Replicas  │ │            │ │         │
└──────────┘ └────────────┘ └─────────┘
```

---

## 9. 附录

### 9.1 环境变量清单

```bash
# .env.example

# ===== 应用 =====
FLASK_ENV=development
SECRET_KEY=your-secret-key-change-in-production

# ===== 数据库 =====
DATABASE_URL=postgresql://eap:eap_dev@localhost:5432/eap
DATABASE_POOL_SIZE=20
DATABASE_POOL_OVERFLOW=10

# ===== Redis =====
REDIS_URL=redis://localhost:6379/0

# ===== LLM =====
LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-xxx
OPENAI_API_KEY=sk-xxx
LLM_MODEL=claude-sonnet-4-20250514

# ===== Embedding =====
EMBEDDING_PROVIDER=openai
EMBEDDING_MODEL=text-embedding-3-small

# ===== LangSmith (可观测性) =====
LANGSMITH_API_KEY=lsv2_xxx
LANGSMITH_PROJECT=eap-platform
LANGSMITH_ENDPOINT=https://api.smith.langchain.com

# ===== OpenTelemetry =====
OTEL_EXPORTER_ENDPOINT=http://jaeger:4317
OTEL_SERVICE_NAME=eap-backend

# ===== 对象存储 (MinIO / S3) =====
S3_ENDPOINT=http://localhost:9000
S3_ACCESS_KEY=minioadmin
S3_SECRET_KEY=minioadmin
S3_BUCKET=eap-knowledge

# ===== Sandbox =====
SANDBOX_PROVIDER=docker
SANDBOX_IMAGE=eap-sandbox:latest

# ===== 安全 =====
PII_DETECTION_MODE=redact
JWT_ACCESS_TOKEN_EXPIRES_MINUTES=120
CORS_ALLOWED_ORIGINS=http://localhost:3000
```

### 9.2 关键技术依赖版本

```
# backend/requirements.txt

# Web 框架
flask==3.1.*
flask-cors==5.*
flask-sqlalchemy==3.1.*
flask-migrate==4.*
flask-jwt-extended==4.7.*
flask-socketio==5.4.*

# Agent 框架
langchain==0.3.*
langgraph==0.3.*
langchain-deep-agents==0.5.*
langgraph-checkpoint-postgres==2.*
langgraph-checkpoint-sqlite==2.*
langchain-community==0.3.*

# LLM
langchain-anthropic==0.3.*
langchain-openai==0.3.*
tiktoken==0.8.*

# 知识库
langchain-text-splitters==0.3.*
pypdf==5.*
python-docx==1.*
unstructured==0.16.*

# 向量存储
pgvector==0.3.*
sqlalchemy==2.0.*

# 安全
presidio-analyzer==2.2.*
presidio-anonymizer==2.2.*

# 基础设施
redis==5.*
boto3==1.35.*        # S3/MinIO
gunicorn==23.*        # WSGI 服务器
gevent==24.*          # 异步 Worker

# 可观测性
opentelemetry-api==1.28.*
opentelemetry-sdk==1.28.*
opentelemetry-exporter-otlp==1.28.*

# 开发工具
pytest==8.*
pytest-asyncio==0.24.*
factory-boy==3.*
```

### 9.3 前端关键依赖

```json
// frontend/package.json (关键依赖)
{
  "dependencies": {
    "react": "^18.3.0",
    "react-dom": "^18.3.0",
    "react-router-dom": "^6.26.0",
    "antd": "^5.22.0",
    "@ant-design/icons": "^5.5.0",
    "zustand": "^5.0.0",
    "axios": "^1.7.0",
    "@ant-design/charts": "^2.2.0",
    "react-markdown": "^9.0.0",
    "react-syntax-highlighter": "^15.6.0",
    "dayjs": "^1.11.0"
  },
  "devDependencies": {
    "typescript": "^5.6.0",
    "vite": "^6.0.0",
    "@vitejs/plugin-react": "^4.3.0",
    "@types/react": "^18.3.0",
    "vitest": "^2.1.0",
    "@testing-library/react": "^16.1.0",
    "eslint": "^9.0.0"
  }
}
```

### 9.4 Phase 里程碑与验收标准

| Phase | 周数 | 核心交付物 | 验收标准 |
|-------|------|-----------|---------|
| **P1** | 4-6 | Flask 骨架 + Auth + 单 Agent 流式对话 | 前端登录后可流式对话，多轮上下文保持 |
| **P2** | 3-4 | 知识库管道 + RAG Agent | 上传 PDF 后可基于内容精准问答 |
| **P3** | 4-5 | 多 Agent 编排 + Skill + MCP | 监督者 Agent 可将任务自动分发给子 Agent |
| **P4** | 3-4 | 安全围栏 + HITL + 长期记忆 | 敏感操作触发审批、PII 自动脱敏 |
| **P5** | 2-3 | 可观测性 + 监控仪表盘 | 全链路 Trace 可查、成本按租户可算 |
| **总计** | **16-22 周** | 完整企业 Agent 平台 | 全部验收标准通过 + 压测达标 |

### 9.5 风险矩阵

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|---------|
| LangGraph API 变动 | 中 | 高 | 锁定 minor 版本，集成测试覆盖核心路径 |
| LLM API 延迟/限流 | 高 | 中 | 多模型路由 + 退避重试 + 缓存策略 |
| 向量检索精度不足 | 中 | 中 | 混合检索 + RRF 融合 + 用户反馈调优 |
| 多 Agent 编排失控 | 低 | 高 | Max Turns + Token 预算硬限制 + 监督者路由 |
| 安全围栏误拦截 | 中 | 低 | 分环境差异化策略 + 用户申诉通道 |
| pgvector 大规模扩展瓶颈 | 低 | 中 | 预留 PGVector 分层/分片扩展方案 |

---

> **文档维护**: 本文档随项目演进持续更新。每个 Phase 完成后需更新对应章节的实际实现细节。
>
> **相关文档**: [技术选型报告](tech_report.md)

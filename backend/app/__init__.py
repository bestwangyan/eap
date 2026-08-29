import os
import logging
from flask import Flask

from config import config
from app.extensions import db, migrate, jwt_manager, cors, redis_client

logger = logging.getLogger(__name__)


def create_app(config_name: str = "development") -> Flask:
    """应用工厂函数"""
    app = Flask(__name__)
    app.config.from_object(config[config_name])

    # ===== LangSmith 全链路追踪（需在创建 Agent 之前初始化）=====
    if app.config.get("LANGSMITH_API_KEY"):
        import os
        os.environ["LANGCHAIN_TRACING_V2"] = "true" if app.config["LANGSMITH_TRACING"] else "false"
        os.environ["LANGCHAIN_API_KEY"] = app.config["LANGSMITH_API_KEY"]
        os.environ["LANGCHAIN_PROJECT"] = app.config["LANGSMITH_PROJECT"]
        os.environ["LANGCHAIN_ENDPOINT"] = app.config["LANGSMITH_ENDPOINT"]
        logger.info(
            f"LangSmith tracing enabled: project={app.config['LANGSMITH_PROJECT']}, "
            f"endpoint={app.config['LANGSMITH_ENDPOINT']}"
        )
    else:
        logger.info("LangSmith tracing disabled (no LANGSMITH_API_KEY configured)")

    # 初始化扩展
    db.init_app(app)
    migrate.init_app(app, db)
    jwt_manager.init_app(app)
    cors.init_app(app, resources={r"/api/*": {"origins": "*"}})
    redis_client.init_app(app)

    # 注册 Agent 编排器到扩展（带 PostgreSQL checkpointer）
    from app.core.agent.orchestrator import AgentOrchestrator
    from langgraph.checkpoint.postgres import PostgresSaver
    import psycopg_pool
    checkpointer = None
    try:
        from urllib.parse import urlparse
        db_url = app.config["SQLALCHEMY_DATABASE_URI"]
        # 将 SQLAlchemy URL 解析为 libpq connection string
        # 支持 postgresql:// 和 postgresql+psycopg2:// 两种格式
        if db_url.startswith("postgresql://") or db_url.startswith("postgres://"):
            # 已经是标准 URI — 去掉可能的 +driver 部分
            conninfo = db_url
            if "+" in conninfo.split("://")[0]:
                conninfo = conninfo.replace(
                    conninfo.split("://")[0] + "://",
                    conninfo.split("://")[0].split("+")[0] + "://",
                    1,
                )
        else:
            # keyword=value 格式，直接使用
            conninfo = db_url

        import psycopg

        pool = psycopg_pool.ConnectionPool(
            conninfo,
            min_size=2, max_size=10, open=True, timeout=30,
        )
        checkpointer = PostgresSaver(pool)
        # PostgresSaver.setup() 使用 CREATE INDEX CONCURRENTLY，必须在
        # autocommit 模式下执行。从连接池获取一个连接并临时开启 autocommit。
        try:
            with pool.connection() as conn:
                conn.autocommit = True
                with conn.cursor() as cur:
                    # 手动执行与 PostgresSaver.setup() 相同的迁移
                    cur.execute("""
                        CREATE TABLE IF NOT EXISTS checkpoints (
                            thread_id TEXT NOT NULL,
                            checkpoint_ns TEXT NOT NULL DEFAULT '',
                            checkpoint_id TEXT NOT NULL,
                            parent_checkpoint_id TEXT,
                            type TEXT,
                            checkpoint JSONB NOT NULL,
                            metadata JSONB NOT NULL DEFAULT '{}',
                            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                            PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id)
                        )
                    """)
                    cur.execute("""
                        CREATE TABLE IF NOT EXISTS checkpoint_blobs (
                            thread_id TEXT NOT NULL,
                            checkpoint_ns TEXT NOT NULL DEFAULT '',
                            channel TEXT NOT NULL,
                            version TEXT NOT NULL,
                            type TEXT NOT NULL,
                            blob BYTEA,
                            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                            PRIMARY KEY (thread_id, checkpoint_ns, channel, version)
                        )
                    """)
                    cur.execute("""
                        CREATE TABLE IF NOT EXISTS checkpoint_writes (
                            thread_id TEXT NOT NULL,
                            checkpoint_ns TEXT NOT NULL DEFAULT '',
                            checkpoint_id TEXT NOT NULL,
                            task_id TEXT NOT NULL,
                            idx INTEGER NOT NULL,
                            channel TEXT NOT NULL,
                            type TEXT,
                            blob BYTEA NOT NULL,
                            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                            task_path TEXT NOT NULL DEFAULT '',
                            PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id, task_id, idx)
                        )
                    """)
                # 索引在 autocommit 模式下单独执行（支持 CONCURRENTLY）
                with conn.cursor() as cur:
                    for idx_sql in [
                        "CREATE INDEX IF NOT EXISTS idx_checkpoints_thread ON checkpoints(thread_id)",
                        "CREATE INDEX IF NOT EXISTS idx_checkpoints_thread_ns ON checkpoints(thread_id, checkpoint_ns)",
                        "CREATE INDEX IF NOT EXISTS idx_checkpoint_blobs_thread ON checkpoint_blobs(thread_id)",
                        "CREATE INDEX IF NOT EXISTS idx_checkpoint_blobs_thread_ns ON checkpoint_blobs(thread_id, checkpoint_ns)",
                        "CREATE INDEX IF NOT EXISTS idx_checkpoint_writes_thread ON checkpoint_writes(thread_id)",
                        "CREATE INDEX IF NOT EXISTS idx_checkpoint_writes_thread_ns ON checkpoint_writes(thread_id, checkpoint_ns)",
                    ]:
                        try:
                            cur.execute(idx_sql)
                        except psycopg.errors.DuplicateTable:
                            pass
            logger.info("PostgresSaver checkpointer initialized with connection pool")
        except Exception as setup_err:
            logger.warning(f"PostgresSaver setup error (may already exist): {setup_err}")
    except Exception as e:
        logger.warning(f"PostgresSaver not available: {e}")
    agent_orchestrator = AgentOrchestrator(checkpointer=checkpointer)
    app.extensions["agent_orchestrator"] = agent_orchestrator
    app.extensions["redis_client"] = redis_client

    # 注册路由
    from app.api.v1 import api_v1, register_routes
    register_routes()
    app.register_blueprint(api_v1, url_prefix="/eap/api/v1")

    # 健康检查端点（无需认证）
    @app.route("/health")
    def health():
        return {"status": "ok"}, 200

    # ===== 统一 JSON 错误响应 =====
    # abort(401/403/...) 与未捕获异常均返回 JSON，避免前端拿到 HTML 错误页或裸 500
    from flask import jsonify
    from werkzeug.exceptions import HTTPException

    @app.errorhandler(HTTPException)
    def handle_http_exception(e):
        return jsonify({
            "error": getattr(e, "description", None) or e.name,
            "status_code": e.code,
        }), e.code

    @app.errorhandler(Exception)
    def handle_unexpected_error(e):
        logger.exception("Unhandled error")
        return jsonify({"error": "服务器内部错误", "status_code": 500}), 500

    # 初始化数据库
    with app.app_context():
        _init_db(app)

    logger.info(f"App created with config: {config_name}")
    return app


def _init_db(app: Flask):
    """初始化数据库表与种子数据"""
    from app.models.tenant import Tenant
    from app.models.permission import Permission
    from app.models.role import Role
    from app.models.model_provider import ModelProvider

    # 建表 (跳过已存在的表)
    try:
        db.create_all()
    except Exception as e:
        logger.warning(f"db.create_all() had issue (may be OK if tables exist): {e}")
        db.session.rollback()

    # 种子数据（仅当表为空时）
    if not Permission.query.first():
        logger.info("Seeding permissions...")
        Permission.seed_presets()

    if not Role.query.filter_by(tenant_id=None).first():
        logger.info("Seeding roles...")
        Role.seed_presets()

    # 创建默认租户（开发环境）
    if not Tenant.query.first():
        default_tenant = Tenant(name="默认组织", slug="default")
        db.session.add(default_tenant)
        db.session.flush()

        from app.models.user import User
        admin_user = User(
            tenant_id=default_tenant.id,
            username="admin",
            email="admin@example.com",
            is_active=True,
        )
        admin_user.set_password(
            os.getenv("EAP_SEED_ADMIN_PW", "CHANGE_ME")
        )  # 种子密码来自环境变量，禁止硬编码真实密码
        db.session.add(admin_user)
        db.session.flush()

        # 分配 SuperAdmin 角色
        super_admin = Role.query.filter_by(name="SuperAdmin", tenant_id=None).first()
        if super_admin:
            admin_user.roles.append(super_admin)

        # 同时创建 Viewer 测试用户
        test_user = User(
            tenant_id=default_tenant.id,
            username="viewer",
            email="viewer@example.com",
            is_active=True,
        )
        test_user.set_password(
            os.getenv("EAP_SEED_VIEWER_PW", "CHANGE_ME")
        )
        db.session.add(test_user)
        viewer_role = Role.query.filter_by(name="Viewer", tenant_id=None).first()
        if viewer_role:
            test_user.roles.append(viewer_role)

        db.session.commit()
        logger.info("Created default tenant and admin user (admin@example.com, 密码见 EAP_SEED_ADMIN_PW)")

    # 为每个租户创建默认模型配置（如果尚未配置）
    for tenant in Tenant.query.all():
        if not ModelProvider.query.filter_by(tenant_id=tenant.id).first():
            logger.info(f"Seeding model providers for tenant {tenant.slug}...")
            ModelProvider.seed_defaults(tenant.id)

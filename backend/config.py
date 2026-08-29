import os
from datetime import timedelta


class BaseConfig:
    """基础配置"""
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-change-in-production")

    # JWT
    JWT_ACCESS_TOKEN_EXPIRES = int(
        timedelta(hours=2).total_seconds()
    )
    JWT_REFRESH_TOKEN_EXPIRES = int(
        timedelta(days=30).total_seconds()
    )

    # ===== 数据库 (服务器 192.168.1.51) =====
    # 真实连接串在服务器 .env 中提供（含密码，禁止提交仓库）
    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL", "")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_size": int(os.getenv("DATABASE_POOL_SIZE", "20")),
        "max_overflow": int(os.getenv("DATABASE_POOL_OVERFLOW", "10")),
        "pool_pre_ping": True,
    }

    # ===== Redis (服务器 192.168.1.51) =====
    # 真实连接串在服务器 .env 中提供（含密码，禁止提交仓库）
    REDIS_URL = os.getenv("REDIS_URL", "")
    REDIS_SESSION_PREFIX = "session"

    # ===== LLM 默认配置（管理员可在 Admin UI 中覆盖）=====
    # 默认使用 DeepSeek，通过环境变量 DEEPSEEK_API_KEY 配置
    DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
    LLM_PROVIDER = os.getenv("LLM_PROVIDER", "deepseek")
    LLM_MODEL = os.getenv("LLM_MODEL", "deepseek-v4-pro")

    # 可选的其他供应商 Key
    ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

    # Agent
    AGENT_MAX_TURNS = int(os.getenv("AGENT_MAX_TURNS", "30"))
    AGENT_MAX_TOKENS = int(os.getenv("AGENT_MAX_TOKENS", "100000"))

    # ===== LangSmith 可观测性 =====
    LANGSMITH_API_KEY = os.getenv("LANGSMITH_API_KEY", "")
    LANGSMITH_PROJECT = os.getenv("LANGSMITH_PROJECT", "eap-platform")
    LANGSMITH_ENDPOINT = os.getenv("LANGSMITH_ENDPOINT", "https://api.smith.langchain.com")
    LANGSMITH_TRACING = os.getenv("LANGSMITH_TRACING", "false").lower() == "true"

    # 文件上传
    SKILLS_STORAGE_ROOT = os.getenv("SKILLS_STORAGE_ROOT", "/home/wangyan/deploy/eap/skills_storage")
    UPLOAD_FOLDER = os.getenv("UPLOAD_FOLDER", "/tmp/eap_uploads")
    MAX_CONTENT_LENGTH = 50 * 1024 * 1024  # 50MB

    # CORS
    CORS_ALLOWED_ORIGINS = os.getenv(
        "CORS_ALLOWED_ORIGINS",
        "http://localhost:3000,http://localhost:5173,http://192.168.1.51:3000",
    )


class DevelopmentConfig(BaseConfig):
    DEBUG = True
    SQLALCHEMY_ECHO = False


class ProductionConfig(BaseConfig):
    DEBUG = False


class TestingConfig(BaseConfig):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    REDIS_URL = "redis://localhost:6379/1"


config = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "testing": TestingConfig,
}

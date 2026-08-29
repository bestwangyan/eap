"""模型供应商配置 - 管理员可配置的 LLM 接入信息"""
from app.extensions import db
from app.models.base import BaseModel


class ModelProvider(BaseModel):
    """管理员配置的模型接入"""
    __tablename__ = "model_providers"

    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(
        db.Integer, db.ForeignKey("tenants.id"), nullable=False, index=True
    )
    name = db.Column(db.String(100), nullable=False)          # 显示名称 "Claude Sonnet"
    provider = db.Column(db.String(50), nullable=False)       # anthropic / openai / deepseek / ...
    api_key = db.Column(db.String(500), nullable=False)       # API Key (加密存储)
    api_base = db.Column(db.String(500))                      # 自定义 API 地址 (可选)
    model_name = db.Column(db.String(200), nullable=False)     # 实际模型名 "claude-sonnet-4-20250514"
    description = db.Column(db.Text)
    is_active = db.Column(db.Boolean, default=True)
    is_default = db.Column(db.Boolean, default=False)          # 是否默认模型
    sort_order = db.Column(db.Integer, default=0)

    __table_args__ = (
        db.UniqueConstraint("tenant_id", "name", name="uq_model_tenant_name"),
    )

    def to_dict(self, include_key: bool = False):
        result = {
            "id": self.id,
            "tenant_id": self.tenant_id,
            "name": self.name,
            "provider": self.provider,
            "api_base": self.api_base,
            "model_name": self.model_name,
            "description": self.description,
            "is_active": self.is_active,
            "is_default": self.is_default,
            "sort_order": self.sort_order,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
        if include_key:
            # 仅在管理后台展示脱敏后的 Key
            result["api_key"] = self._mask_key(self.api_key)
        return result

    @staticmethod
    def _mask_key(key: str) -> str:
        if not key or len(key) < 12:
            return "****"
        return key[:6] + "****" + key[-4:]

    @classmethod
    def get_active_providers(cls, tenant_id: int) -> list["ModelProvider"]:
        return cls.query.filter_by(
            tenant_id=tenant_id, is_active=True
        ).order_by(cls.sort_order).all()

    @classmethod
    def get_default(cls, tenant_id: int) -> "ModelProvider | None":
        return cls.query.filter_by(
            tenant_id=tenant_id, is_active=True, is_default=True
        ).first()

    @classmethod
    def seed_defaults(cls, tenant_id: int):
        """为租户创建预置模型配置（使用环境变量中的 Key）

        优先级: DEEPSEEK_API_KEY > ANTHROPIC_API_KEY > OPENAI_API_KEY
        第一个有值的供应商会自动设为默认模型
        """
        import os
        from flask import current_app

        existing = cls.query.filter_by(tenant_id=tenant_id).first()
        if existing:
            return

        defaults = []
        has_default = False

        # ---- DeepSeek (优先默认) ----
        deepseek_key = (
            current_app.config.get("DEEPSEEK_API_KEY", "")
            if current_app else os.getenv("DEEPSEEK_API_KEY", "")
        )
        if deepseek_key:
            defaults.append(cls(
                tenant_id=tenant_id,
                name="DeepSeek V3",
                provider="deepseek",
                api_key=deepseek_key,
                api_base="https://api.deepseek.com/v1",
                model_name="deepseek-v4-pro",
                description="DeepSeek V3 - 高性价比国产模型",
                is_default=not has_default,
                sort_order=0,
            ))
            has_default = True

        # ---- Anthropic Claude ----
        anthropic_key = current_app.config.get("ANTHROPIC_API_KEY", "") if current_app else os.getenv("ANTHROPIC_API_KEY", "")
        if anthropic_key:
            defaults.append(cls(
                tenant_id=tenant_id,
                name="Claude Sonnet 4",
                provider="anthropic",
                api_key=anthropic_key,
                model_name="claude-sonnet-4-20250514",
                description="Anthropic Claude Sonnet 4 - 平衡性能与成本",
                is_default=not has_default,
                sort_order=1 if has_default else 0,
            ))
            if not has_default:
                has_default = True

        # ---- OpenAI GPT ----
        openai_key = current_app.config.get("OPENAI_API_KEY", "") if current_app else os.getenv("OPENAI_API_KEY", "")
        if openai_key:
            defaults.append(cls(
                tenant_id=tenant_id,
                name="GPT-4o",
                provider="openai",
                api_key=openai_key,
                model_name="gpt-4o",
                description="OpenAI GPT-4o - 多模态高性能模型",
                is_default=not has_default,
                sort_order=2 if has_default else 0,
            ))
            if not has_default:
                has_default = True

        # ---- LM Studio（本地模型服务器，OpenAI 兼容，无需云端 Key）----
        # api_base 默认 127.0.0.1:1234/v1（LM Studio 默认端口），
        # 如 LM Studio 运行在其他机器，管理员在"模型配置"页修改地址即可
        defaults.append(cls(
            tenant_id=tenant_id,
            name="LM Studio 本地模型",
            provider="lmstudio",
            api_key="lm-studio",  # 本地服务不校验，占位即可
            api_base="http://127.0.0.1:1234/v1",
            model_name="openai/gpt-oss-20b",  # 按 LM Studio 中实际加载的模型修改
            description="LM Studio 本地模型 - 数据不出内网",
            is_default=False,
            sort_order=3,
        ))

        for m in defaults:
            db.session.add(m)
        db.session.commit()

"""Global memory tools — cross-thread user memory persistence"""
import logging
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class MemorySaveInput(BaseModel):
    key: str = Field(description="记忆主题（简短标识，如 'user_name', 'preferred_language'）")
    content: str = Field(description="记忆内容")
    category: str = Field(
        default="fact",
        description="分类: preference（偏好）, fact（事实）, context（上下文）, identity（身份）",
    )
    importance: int = Field(default=5, description="重要性 1-10，越高越重要")


class MemorySearchInput(BaseModel):
    query: str = Field(description="搜索关键词或自然语言查询")
    top_k: int = Field(default=5, description="返回数量")


def _memory_save(key: str, content: str, category: str = "fact", importance: int = 5) -> str:
    """保存一条用户记忆，如果 key 已存在则更新内容"""
    try:
        from app.models.user_memory import UserMemory
        from app.extensions import db
        from app.core.agent.runtime_context import get_tenant_id, get_user_id

        tenant_id = int(get_tenant_id())
        user_id = int(get_user_id())

        existing = UserMemory.query.filter_by(
            tenant_id=tenant_id, user_id=user_id, key=key
        ).first()

        if existing:
            existing.content = content
            existing.category = category
            existing.importance = max(1, min(importance, 10))
            db.session.commit()
            return f"已更新记忆: {key}"
        else:
            mem = UserMemory(
                tenant_id=tenant_id, user_id=user_id,
                key=key, content=content,
                category=category,
                importance=max(1, min(importance, 10)),
            )
            db.session.add(mem)
            db.session.commit()
            return f"已保存记忆: {key}"
    except Exception as e:
        db.session.rollback()
        return f"保存记忆失败: {str(e)}"


def _memory_search(query: str, top_k: int = 5) -> str:
    """搜索用户的全局记忆"""
    try:
        from app.models.user_memory import UserMemory
        from app.core.agent.runtime_context import get_tenant_id, get_user_id

        tenant_id = int(get_tenant_id())
        user_id = int(get_user_id())

        # 模糊匹配 key + content
        results = UserMemory.query.filter(
            UserMemory.tenant_id == tenant_id,
            UserMemory.user_id == user_id,
            (UserMemory.key.ilike(f"%{query}%"))
            | (UserMemory.content.ilike(f"%{query}%")),
        ).order_by(
            UserMemory.importance.desc(), UserMemory.updated_at.desc()
        ).limit(top_k).all()

        if not results:
            # 宽松搜索：无关键词时返回最近的重要记忆
            results = UserMemory.query.filter_by(
                tenant_id=tenant_id, user_id=user_id,
            ).filter(
                UserMemory.importance >= 5,
            ).order_by(
                UserMemory.importance.desc(), UserMemory.updated_at.desc()
            ).limit(top_k).all()

        if not results:
            return "未找到相关记忆。"

        parts = [f"找到 {len(results)} 条相关记忆:\n"]
        for m in results:
            parts.append(
                f"- [{m.category}] {m.key}: {m.content[:300]}"
            )
        return "\n".join(parts)

    except Exception as e:
        return f"搜索记忆失败: {str(e)}"


memory_save_tool = StructuredTool.from_function(
    name="memory_save",
    description="保存用户的全局记忆（跨线程持久化）。当用户明确告知重要信息时使用此工具记录。",
    func=_memory_save,
    args_schema=MemorySaveInput,
)

memory_search_tool = StructuredTool.from_function(
    name="memory_search",
    description="搜索当前用户的全局记忆。当需要了解用户背景、偏好或历史时使用。",
    func=_memory_search,
    args_schema=MemorySearchInput,
)

"""Knowledge base search tool"""
import logging
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class KnowledgeSearchInput(BaseModel):
    query: str = Field(description="搜索查询，使用自然语言描述要查找的内容")
    top_k: int = Field(default=5, description="返回结果数量 (1-10)")


def _knowledge_search(query: str, top_k: int = 5) -> str:
    """搜索企业知识库"""
    top_k = max(1, min(top_k, 10))

    try:
        from app.models.knowledge import KnowledgeCollection
        from app.core.knowledge.retriever import HybridRetriever
        from app.core.agent.runtime_context import (
            get_tenant_id, get_knowledge_collection_ids,
        )

        tenant_id = get_tenant_id()
        if not tenant_id:
            return "错误: 无法确定租户上下文"

        # 查询该租户的知识库集合
        q = KnowledgeCollection.query.filter_by(tenant_id=int(tenant_id))

        # 如果 Agent 配置了 knowledge_collections，只搜索指定的集合
        collection_ids = get_knowledge_collection_ids()
        if collection_ids:
            q = q.filter(KnowledgeCollection.id.in_(collection_ids))

        collections = q.all()

        if not collections:
            if collection_ids:
                return (
                    f"当前 Agent 配置的知识库集合（ID: {collection_ids}）中暂无可用集合。"
                    f"请检查知识库配置。"
                )
            return "当前租户下没有知识库集合。请在知识库管理页面上传文档。"

        retriever = HybridRetriever()
        all_results: list[dict] = []

        for col in collections:
            try:
                results = retriever.search(
                    query=query,
                    collection_id=col.id,
                    tenant_id=int(tenant_id),
                    top_k=top_k,
                )
                for r in results:
                    r["collection_name"] = col.name
                all_results.extend(results)
            except Exception as e:
                logger.warning(f"Search collection {col.id} failed: {e}")
                continue

        if not all_results:
            return f"在知识库中未找到与 \"{query}\" 相关的内容。"

        # 按分数排序并截取
        all_results.sort(key=lambda x: x.get("score", 0), reverse=True)
        all_results = all_results[:top_k]

        if not all_results:
            return f"在知识库中未找到与 \"{query}\" 相关的内容。"

        # 返回结构化上下文素材，不包含展示格式。
        # LLM 用这些素材合成回答，并在末尾附上引用来源。
        parts = []
        for i, r in enumerate(all_results):
            content = r["content"][:800]
            col_name = r.get("collection_name", "未知")
            parts.append(
                f"--- 知识库片段 {i + 1} ---\n"
                f"来源: {col_name}\n"
                f"内容: {content}\n"
            )

        parts.append(
            "请基于以上知识库片段回答用户问题。"
            "如果片段中找不到相关信息，请如实告知，不要编造。"
            "回答时用你自己的语言组织，引用来源时注明来源集合名称。"
        )

        return "\n".join(parts)

    except Exception as e:
        return f"知识库搜索失败: {str(e)}"


knowledge_search_tool = StructuredTool.from_function(
    name="knowledge_search",
    description="搜索企业知识库中的文档内容。输入自然语言查询，返回相关文档片段。",
    func=_knowledge_search,
    args_schema=KnowledgeSearchInput,
)

"""Phase 2: 混合检索器 — 语义搜索 + BM25 关键词 + RRF 融合"""
import logging
from app.extensions import db
from app.core.knowledge.embedder import EmbeddingService

logger = logging.getLogger(__name__)


class HybridRetriever:
    def __init__(self, embedding_service: EmbeddingService = None):
        self.embedder = embedding_service or EmbeddingService()

    def search(self, query: str, collection_id: int, tenant_id: int = None,
               top_k: int = 5) -> list[dict]:
        """混合检索入口 — 优先语义搜索，不可用时降级为关键词搜索"""
        self._tenant_id = tenant_id
        table = f"kb_chunks_{collection_id}"
        results = []
        from sqlalchemy import text

        if self.embedder.available:
            try:
                query_embedding = self.embedder.embed_query(query)
                emb_str = str(query_embedding)
                rows = db.session.execute(text(
                    f"SELECT id, document_id, chunk_index, content, metadata, "
                    f"1 - (embedding <=> :emb::vector) AS score "
                    f"FROM {table} "
                    f"ORDER BY embedding <=> :emb::vector "
                    f"LIMIT :limit"
                ), {"emb": emb_str, "limit": top_k * 2}).fetchall()
                for row in rows:
                    meta = row.metadata or {}
                    if not tenant_id or str(meta.get("tenant_id", "")) == str(tenant_id):
                        results.append({
                            "id": row.id, "document_id": row.document_id,
                            "chunk_index": row.chunk_index, "content": row.content,
                            "score": round(float(row.score), 4),
                            "metadata": meta,
                        })
            except Exception as e:
                logger.warning(f"Vector search failed: {e}")

        if not results:
            results = self._keyword_search(query, collection_id, top_k)

        return results[:top_k]

    def _keyword_search(self, query: str, collection_id: int, top_k: int) -> list[dict]:
        """
        关键词降级检索。

        将查询切分为可匹配的 token：
          - 英文/数字词（长度 >= 2）
          - 中文连续串的字符二元组（如 "在哪里成立" → 在哪/哪里/里成/成立）
        所有 token 做 OR 匹配，按命中 token 数排序。

        同时按 metadata 中的 tenant_id 过滤，防止跨租户读取。
        """
        import re
        from sqlalchemy import text
        table = f"kb_chunks_{collection_id}"

        tokens = set()
        for word in re.findall(r"[a-zA-Z0-9_]+", query):
            if len(word) >= 2:
                tokens.add(word)
        for han in re.findall(r"[一-鿿]+", query):
            if len(han) <= 2:
                tokens.add(han)
            else:
                for i in range(len(han) - 1):
                    tokens.add(han[i:i + 2])
        if not tokens:
            tokens.add(query)
        tokens = sorted(tokens)

        or_conds = " OR ".join(f"content ILIKE :t{i}" for i in range(len(tokens)))
        hit_sum = " + ".join(f"(content ILIKE :t{i})::int" for i in range(len(tokens)))
        params = {f"t{i}": f"%{t}%" for i, t in enumerate(tokens)}
        params["limit"] = top_k

        try:
            rows = db.session.execute(text(
                f"SELECT id, document_id, chunk_index, content, metadata, "
                f"({hit_sum}) AS hits "
                f"FROM {table} "
                f"WHERE ({or_conds}) AND metadata->>'tenant_id' = :tid "
                f"ORDER BY hits DESC LIMIT :limit"
            ), {"tid": str(self._tenant_id), **params}).fetchall()
            return [{
                "id": r.id, "document_id": r.document_id,
                "chunk_index": r.chunk_index, "content": r.content,
                "score": round(0.5 + min(r.hits, 5) * 0.1, 4),
                "metadata": r.metadata or {},
            } for r in rows]
        except Exception as e:
            logger.warning(f"Keyword search failed: {e}")
            return []

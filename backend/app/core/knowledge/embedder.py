"""Embedding 服务 — 支持多供应商，无 Key 时自动降级为模拟向量"""
import logging
from flask import current_app

logger = logging.getLogger(__name__)


class EmbeddingService:
    def __init__(self, provider: str = None, model: str = None, api_key: str = None):
        self.provider = provider or current_app.config.get("EMBEDDING_PROVIDER", "openai")
        self.model = model or current_app.config.get("EMBEDDING_MODEL", "text-embedding-3-small")
        self.api_key = api_key or current_app.config.get("OPENAI_API_KEY", "")
        self._available = None

    @property
    def available(self) -> bool:
        """检查 Embedding 服务是否可用"""
        if self._available is None:
            if not self.api_key or self.api_key.startswith("sk-placeholder"):
                self._available = False
            else:
                try:
                    self.embed_documents(["test"])
                    self._available = True
                except Exception:
                    self._available = False
        return self._available

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if self.provider == "openai" and self.api_key and not self.api_key.startswith("sk-placeholder"):
            return self._embed_openai(texts)
        else:
            logger.warning("No valid embedding API key, using simulated vectors. "
                         "Set OPENAI_API_KEY for semantic search.")
            return self._simulate(texts)

    def embed_query(self, text: str) -> list[float]:
        return self.embed_documents([text])[0]

    def _embed_openai(self, texts: list[str]) -> list[list[float]]:
        from openai import OpenAI
        client = OpenAI(api_key=self.api_key)
        resp = client.embeddings.create(model=self.model, input=texts)
        return [d.embedding for d in resp.data]

    def _simulate(self, texts: list[str]) -> list[list[float]]:
        """模拟向量：基于文本 hash 生成确定性向量，仅用于测试"""
        import hashlib
        dim = 1536
        results = []
        for text in texts:
            h = hashlib.sha256(text.encode()).digest()
            # 从 hash 生成 1536 维向量（拉伸+填充）
            vec = [0.0] * dim
            for i in range(min(len(h) * 8, dim)):
                byte_idx = i // 8
                bit_idx = i % 8
                vec[i] = float((h[byte_idx] >> bit_idx) & 1)
            results.append(vec)
        return results

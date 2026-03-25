import asyncio
import logging
from functools import lru_cache

from sentence_transformers import SentenceTransformer

from total_llm.core.config import get_settings

logger = logging.getLogger(__name__)


class EmbeddingService:
    def __init__(self) -> None:
        settings = get_settings()
        self._model = SentenceTransformer(
            settings.embedding.model_name,
            device=settings.embedding.device,
        )
        self.dimension = 1024

    async def embed_query(self, text: str) -> list[float]:
        if not text or not text.strip():
            raise ValueError("Query text cannot be empty")

        logger.debug("Embedding single query text")
        embedding = await asyncio.to_thread(
            self._model.encode,
            text,
            normalize_embeddings=True,
        )
        return embedding.tolist()

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        if any(not text or not text.strip() for text in texts):
            raise ValueError("All document texts must be non-empty")

        logger.debug("Embedding %d documents", len(texts))
        embeddings = await asyncio.to_thread(
            self._model.encode,
            texts,
            normalize_embeddings=True,
            batch_size=32,
        )
        return embeddings.tolist()


@lru_cache
def get_embedding_service() -> EmbeddingService:
    return EmbeddingService()

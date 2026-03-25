import logging
from typing import Any, cast
from uuid import uuid4

from qdrant_client import AsyncQdrantClient
from qdrant_client import models

from total_llm.core.config import get_settings

logger = logging.getLogger(__name__)


class QdrantService:
    def __init__(self, host: str | None = None, port: int | None = None) -> None:
        settings = get_settings()
        self._collection_name = settings.qdrant.collection_name
        self._vector_size = settings.qdrant.vector_size
        self._host = host or settings.qdrant.host
        self._port = port or settings.qdrant.port
        self._client = AsyncQdrantClient(host=self._host, port=self._port)

    async def ensure_collection(self) -> None:
        import aiohttp
        base = f"http://{self._host}:{self._port}"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{base}/collections/{self._collection_name}") as resp:
                    if resp.status == 200:
                        logger.info("Qdrant collection exists: %s", self._collection_name)
                        return
                async with session.put(
                    f"{base}/collections/{self._collection_name}",
                    json={"vectors": {"size": self._vector_size, "distance": "Cosine"}},
                ) as resp:
                    if resp.status == 200:
                        logger.info("Created Qdrant collection: %s", self._collection_name)
                    else:
                        body = await resp.text()
                        logger.error("Failed to create collection: %s %s", resp.status, body)
        except Exception:
            logger.exception("Failed to ensure Qdrant collection")
            raise

    async def search(
        self,
        query_vector: list[float],
        limit: int = 10,
        filter: models.Filter | dict[str, Any] | None = None,
    ) -> list[models.ScoredPoint]:
        if not query_vector:
            return []
        if limit <= 0:
            return []

        search_filter = self._to_filter(filter)

        try:
            result = await self._client.query_points(
                collection_name=self._collection_name,
                query=query_vector,
                limit=limit,
                query_filter=search_filter,
                with_payload=True,
            )
            return result.points
        except Exception:
            logger.exception("Qdrant search failed")
            raise

    async def upsert(
        self,
        texts: list[str],
        vectors: list[list[float]],
        metadatas: list[dict[str, Any]] | None = None,
    ) -> list[str]:
        if len(texts) != len(vectors):
            raise ValueError("texts and vectors length must match")
        if metadatas is not None and len(metadatas) != len(texts):
            raise ValueError("metadatas length must match texts length")
        if not texts:
            return []

        point_ids: list[str] = []
        points: list[models.PointStruct] = []

        for idx, text in enumerate(texts):
            point_id = str(uuid4())
            point_ids.append(point_id)

            payload = {"text": text}
            if metadatas is not None:
                payload.update(metadatas[idx])

            points.append(
                models.PointStruct(
                    id=point_id,
                    vector=vectors[idx],
                    payload=payload,
                )
            )

        try:
            await self._client.upsert(
                collection_name=self._collection_name,
                points=points,
                wait=True,
            )
            return point_ids
        except Exception:
            logger.exception("Qdrant upsert failed")
            raise

    async def delete_by_id(self, point_ids: list[str]) -> None:
        if not point_ids:
            return

        try:
            await self._client.delete(
                collection_name=self._collection_name,
                points_selector=models.PointIdsList(
                    points=cast(list[models.ExtendedPointId], point_ids)
                ),
                wait=True,
            )
        except Exception:
            logger.exception("Failed deleting points by ids")
            raise

    async def delete_by_filter(self, key: str, value: Any) -> None:
        if not key:
            raise ValueError("key cannot be empty")

        try:
            await self._client.delete(
                collection_name=self._collection_name,
                points_selector=models.FilterSelector(
                    filter=models.Filter(
                        must=[
                            models.FieldCondition(
                                key=key,
                                match=models.MatchValue(value=value),
                            )
                        ]
                    )
                ),
                wait=True,
            )
        except Exception:
            logger.exception("Failed deleting points by filter")
            raise

    async def scroll_all(self, limit: int = 256) -> list[models.Record]:
        if limit <= 0:
            return []

        all_points: list[models.Record] = []
        offset: Any = None

        try:
            while True:
                points, offset = await self._client.scroll(
                    collection_name=self._collection_name,
                    limit=limit,
                    offset=offset,
                    with_payload=True,
                    with_vectors=False,
                )
                all_points.extend(points)
                if offset is None:
                    break

            return all_points
        except Exception:
            logger.exception("Failed scrolling Qdrant collection")
            raise

    async def count(self) -> int:
        try:
            result = await self._client.count(
                collection_name=self._collection_name,
                exact=True,
            )
            return int(result.count)
        except Exception:
            logger.exception("Failed counting Qdrant points")
            raise

    def _to_filter(
        self,
        filter_value: models.Filter | dict[str, Any] | None,
    ) -> models.Filter | None:
        if filter_value is None:
            return None
        if isinstance(filter_value, models.Filter):
            return filter_value

        must_conditions: list[models.Condition] = []
        for key, value in filter_value.items():
            if isinstance(value, list):
                must_conditions.append(
                    models.FieldCondition(
                        key=key,
                        match=models.MatchAny(any=value),
                    )
                )
            else:
                must_conditions.append(
                    models.FieldCondition(
                        key=key,
                        match=models.MatchValue(value=value),
                    )
                )

        return models.Filter(must=must_conditions)

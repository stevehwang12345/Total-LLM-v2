import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI

logger = logging.getLogger(__name__)
from fastapi.middleware.cors import CORSMiddleware
from openai import AsyncOpenAI
from total_llm.services.qdrant import QdrantService
from redis.asyncio import Redis

from total_llm.api.alarms import router as alarms_router
from total_llm.api.analysis import router as analysis_router
from total_llm.api.chat import router as chat_router
from total_llm.api.discovery import router as discovery_router
from total_llm.api.devices import router as devices_router
from total_llm.api.documents import router as documents_router
from total_llm.api.reports import router as reports_router
from total_llm.api.system import router as system_router
from total_llm.core.config import get_settings
from total_llm.core.exceptions import register_exception_handlers
from total_llm.database.init import create_pool, init_db
from total_llm.services.health_scheduler import get_scheduler  # pyright: ignore[reportMissingImports]
from total_llm.services.report_scheduler import get_report_scheduler  # pyright: ignore[reportMissingImports]


@asynccontextmanager
async def lifespan(app: FastAPI):
    s = get_settings()
    statuses = {"database": "down", "redis": "down", "embedding": "down", "qdrant": "down", "llm": "down", "vlm": "down"}

    app.state.settings = s
    app.state.db_pool = await create_pool()
    await init_db(app.state.db_pool)
    statuses["database"] = "up"

    redis_host = os.environ.get("REDIS_HOST", s.redis.host)
    redis_port = int(os.environ.get("REDIS_PORT", s.redis.port))
    app.state.redis = Redis(host=redis_host, port=redis_port, password=s.redis.password or None, decode_responses=True)
    try:
        await app.state.redis.ping()  # pyright: ignore[reportGeneralTypeIssues]
        statuses["redis"] = "up"
    except Exception:
        pass

    try:
        from total_llm.services.embedding import EmbeddingService
        app.state.embedding_service = EmbeddingService()
        statuses["embedding"] = "up"
    except Exception:
        logger.exception("Failed to load embedding model")
        app.state.embedding_service = None

    qdrant_host = os.environ.get("QDRANT_HOST", s.qdrant.host)
    qdrant_port = int(os.environ.get("QDRANT_PORT", s.qdrant.port))
    qdrant_svc = QdrantService(host=qdrant_host, port=qdrant_port)
    await qdrant_svc.ensure_collection()
    app.state.qdrant_service = qdrant_svc
    statuses["qdrant"] = "up"

    if app.state.embedding_service is not None:
        from total_llm.database.seed import seed_documents
        try:
            await seed_documents(
                db_pool=app.state.db_pool,
                qdrant_service=app.state.qdrant_service,
                embedding_service=app.state.embedding_service,
                settings=s,
            )
        except Exception:
            logger.exception("Document auto-seed failed (non-fatal)")

    llm_base = os.environ.get("VLLM_BASE_URL", s.llm.base_url)
    vlm_base = os.environ.get("VLM_BASE_URL", s.vlm.base_url)
    llm = AsyncOpenAI(base_url=llm_base, api_key="dummy")
    app.state.llm_client = llm
    app.state.vlm_client = llm if vlm_base == llm_base else AsyncOpenAI(base_url=vlm_base, api_key="dummy")
    statuses["llm"] = "up"
    statuses["vlm"] = "up"
    app.state.service_status = statuses

    scheduler = get_scheduler(interval_seconds=30)
    await scheduler.start(app.state.db_pool)
    report_scheduler = get_report_scheduler()
    await report_scheduler.start(app.state.db_pool)

    yield

    await report_scheduler.stop()
    await scheduler.stop()
    await app.state.redis.aclose()
    await app.state.db_pool.close()


app = FastAPI(title="Total-LLM v2", version="2.0.0", lifespan=lifespan)
settings = get_settings()

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.api.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

register_exception_handlers(app)
for router in (chat_router, analysis_router, devices_router, discovery_router, alarms_router, documents_router, reports_router, system_router):
    app.include_router(router)


@app.get("/health")
async def health() -> dict:
    return {
        "status": "ok",
        "services": app.state.service_status,
        "model": {"llm": settings.llm.model_name, "vlm": settings.vlm.model_name},
    }

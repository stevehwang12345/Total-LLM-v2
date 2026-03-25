from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from openai import AsyncOpenAI
from qdrant_client import QdrantClient
from redis.asyncio import Redis

from total_llm.api.alarms import router as alarms_router
from total_llm.api.analysis import router as analysis_router
from total_llm.api.chat import router as chat_router
from total_llm.api.devices import router as devices_router
from total_llm.api.documents import router as documents_router
from total_llm.api.reports import router as reports_router
from total_llm.api.system import router as system_router
from total_llm.core.config import get_settings
from total_llm.core.exceptions import register_exception_handlers
from total_llm.database.init import create_pool, init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    s = get_settings()
    statuses = {"database": "down", "redis": "down", "embedding": "down", "qdrant": "down", "llm": "down", "vlm": "down"}

    app.state.settings = s
    app.state.db_pool = await create_pool()
    await init_db(app.state.db_pool)
    statuses["database"] = "up"

    app.state.redis = Redis(host=s.redis.host, port=s.redis.port, password=s.redis.password, decode_responses=True)
    try:
        await app.state.redis.ping()
        statuses["redis"] = "up"
    except Exception:
        pass

    app.state.embedding_service = {"model_name": s.embedding.model_name, "device": s.embedding.device}
    statuses["embedding"] = "up"

    app.state.qdrant_service = QdrantClient(host=s.qdrant.host, port=s.qdrant.port)
    statuses["qdrant"] = "up"

    llm = AsyncOpenAI(base_url=s.llm.base_url, api_key="dummy")
    app.state.llm_client = llm
    app.state.vlm_client = llm if s.vlm.base_url == s.llm.base_url else AsyncOpenAI(base_url=s.vlm.base_url, api_key="dummy")
    statuses["llm"] = "up"
    statuses["vlm"] = "up"
    app.state.service_status = statuses

    yield

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
for router in (chat_router, analysis_router, devices_router, alarms_router, documents_router, reports_router, system_router):
    app.include_router(router)


@app.get("/health")
async def health() -> dict:
    return {
        "status": "ok",
        "services": app.state.service_status,
        "model": {"llm": settings.llm.model_name, "vlm": settings.vlm.model_name},
    }

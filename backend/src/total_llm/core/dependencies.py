from fastapi import Request

from total_llm.core.config import Settings, get_settings as _get_settings


def get_db_pool(request: Request):
    return request.app.state.db_pool


def get_redis(request: Request):
    return request.app.state.redis


def get_llm_client(request: Request):
    return request.app.state.llm_client


def get_vlm_client(request: Request):
    return request.app.state.vlm_client


def get_embedding_service(request: Request):
    return request.app.state.embedding_service


def get_qdrant_service(request: Request):
    return request.app.state.qdrant_service


def get_settings() -> Settings:
    return _get_settings()

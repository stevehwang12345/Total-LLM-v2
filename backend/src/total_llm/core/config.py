from functools import lru_cache
import json
import os

from pydantic import AliasChoices, BaseModel, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class LLMSettings(BaseModel):
    base_url: str = "http://localhost:9000/v1"
    model_name: str = "Qwen/Qwen3.5-9B"


class VLMSettings(BaseModel):
    base_url: str = "http://localhost:9000/v1"
    model_name: str = "Qwen/Qwen3.5-9B"


class EmbeddingSettings(BaseModel):
    model_name: str = "Qwen/Qwen3-Embedding-0.6B"
    device: str = "cpu"


class QdrantSettings(BaseModel):
    host: str = "localhost"
    port: int = 6333
    collection_name: str = "documents"
    vector_size: int = 1024


class DatabaseSettings(BaseModel):
    host: str = Field("localhost", validation_alias=AliasChoices("POSTGRES_HOST", "DB_HOST"))
    port: int = Field(5432, validation_alias=AliasChoices("POSTGRES_PORT", "DB_PORT"))
    database: str = Field("total_llm", validation_alias=AliasChoices("POSTGRES_DB", "DB_NAME"))
    username: str = Field("total_llm", validation_alias=AliasChoices("POSTGRES_USER", "DB_USER"))
    password: str = Field("total_llm_dev", validation_alias=AliasChoices("POSTGRES_PASSWORD", "DB_PASSWORD"))


class RedisSettings(BaseModel):
    host: str = "localhost"
    port: int = 6379
    password: str | None = None


class APISettings(BaseModel):
    host: str = "0.0.0.0"
    port: int = 9002
    cors_origins: list[str] = ["http://localhost:9004"]

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, value: object) -> list[str]:
        if isinstance(value, list):
            return [str(v).strip() for v in value if str(v).strip()]
        if isinstance(value, str):
            raw = value.strip()
            if not raw:
                return []
            if raw.startswith("["):
                parsed = json.loads(raw)
                if not isinstance(parsed, list):
                    raise ValueError("CORS_ORIGINS JSON must be an array")
                return [str(v).strip() for v in parsed if str(v).strip()]
            return [item.strip() for item in raw.split(",") if item.strip()]
        return ["http://localhost:9004"]


class AuthSettings(BaseModel):
    jwt_secret: str = "change-me-in-production"
    algorithm: str = "HS256"
    expire_minutes: int = 60


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    llm: LLMSettings = Field(default_factory=LLMSettings)
    vlm: VLMSettings = Field(default_factory=VLMSettings)
    embedding: EmbeddingSettings = Field(default_factory=EmbeddingSettings)
    qdrant: QdrantSettings = Field(default_factory=QdrantSettings)
    database: DatabaseSettings = Field(default_factory=lambda: DatabaseSettings(host="localhost", port=5432, database="total_llm", username="total_llm", password="total_llm_dev"))
    redis: RedisSettings = Field(default_factory=RedisSettings)
    api: APISettings = Field(default_factory=APISettings)
    auth: AuthSettings = Field(default_factory=AuthSettings)

    @model_validator(mode="before")
    @classmethod
    def inject_nested_from_env(cls, data: object) -> dict:
        src = dict(data) if isinstance(data, dict) else {}
        src.setdefault("llm", {"base_url": os.getenv("VLLM_BASE_URL", "http://localhost:9000/v1"), "model_name": os.getenv("LLM_MODEL_NAME", "Qwen/Qwen3.5-9B")})
        src.setdefault("vlm", {"base_url": os.getenv("VLM_BASE_URL", os.getenv("VLLM_BASE_URL", "http://localhost:9000/v1")), "model_name": os.getenv("VLM_MODEL_NAME", os.getenv("LLM_MODEL_NAME", "Qwen/Qwen3.5-9B"))})
        src.setdefault("embedding", {"model_name": os.getenv("EMBEDDING_MODEL_NAME", "Qwen/Qwen3-Embedding-0.6B"), "device": os.getenv("EMBEDDING_DEVICE", "cpu")})
        src.setdefault("qdrant", {"host": os.getenv("QDRANT_HOST", "localhost"), "port": int(os.getenv("QDRANT_PORT", "6333")), "collection_name": os.getenv("QDRANT_COLLECTION_NAME", "documents"), "vector_size": int(os.getenv("QDRANT_VECTOR_SIZE", "1024"))})
        src.setdefault("database", {"host": os.getenv("POSTGRES_HOST", os.getenv("DB_HOST", "localhost")), "port": int(os.getenv("POSTGRES_PORT", os.getenv("DB_PORT", "5432"))), "database": os.getenv("POSTGRES_DB", os.getenv("DB_NAME", "total_llm")), "username": os.getenv("POSTGRES_USER", os.getenv("DB_USER", "total_llm")), "password": os.getenv("POSTGRES_PASSWORD", os.getenv("DB_PASSWORD", "total_llm_dev"))})
        src.setdefault("redis", {"host": os.getenv("REDIS_HOST", "localhost"), "port": int(os.getenv("REDIS_PORT", "6379")), "password": os.getenv("REDIS_PASSWORD") or None})
        src.setdefault("api", {"host": os.getenv("API_HOST", "0.0.0.0"), "port": int(os.getenv("API_PORT", "9002")), "cors_origins": os.getenv("CORS_ORIGINS", "[\"http://localhost:9004\"]")})
        src.setdefault("auth", {"jwt_secret": os.getenv("JWT_SECRET", "change-me-in-production"), "algorithm": os.getenv("JWT_ALGORITHM", "HS256"), "expire_minutes": int(os.getenv("JWT_EXPIRE_MINUTES", "60"))})
        return src


@lru_cache
def get_settings() -> Settings:
    return Settings()

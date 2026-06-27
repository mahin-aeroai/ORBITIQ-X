"""
ORBITIQ-X Backend — Application Configuration
==============================================
Centralised settings loaded from environment variables with full
validation. Uses Pydantic Settings for type-safe configuration.

All settings are read-once at startup via the cached `get_settings()`
dependency. Never import settings directly — always use the function.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import AnyHttpUrl, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    ORBITIQ-X platform configuration.

    All values are loaded from environment variables or the .env file.
    Refer to .env.example for documentation on each variable.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # ─── Application ──────────────────────────────────────────────────────────
    ORBITIQ_ENV: Literal["development", "staging", "production"] = "development"
    ORBITIQ_VERSION: str = "0.1.0"
    ORBITIQ_LOG_LEVEL: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    ORBITIQ_SECRET_KEY: SecretStr = Field(..., min_length=32)

    # ─── Backend ──────────────────────────────────────────────────────────────
    BACKEND_HOST: str = "0.0.0.0"
    BACKEND_PORT: int = Field(default=8000, ge=1024, le=65535)
    BACKEND_WORKERS: int = Field(default=4, ge=1)
    BACKEND_RELOAD: bool = True
    BACKEND_API_PREFIX: str = "/api/v1"
    BACKEND_CORS_ORIGINS: list[str] = ["http://localhost:3000", "https://orbitiq-x.vercel.app", "https://*.vercel.app"]
    BACKEND_RATE_LIMIT_REQUESTS: int = Field(default=100, ge=1)
    BACKEND_JWT_ALGORITHM: str = "HS256"
    BACKEND_JWT_EXPIRE_MINUTES: int = Field(default=60, ge=5)
    BACKEND_JWT_REFRESH_EXPIRE_DAYS: int = Field(default=7, ge=1)
    TRUSTED_HOSTS: list[str] = ["localhost", "127.0.0.1", "orbitiq-x-production.up.railway.app", "*.up.railway.app", "orbitiq-x.vercel.app", "orbitiq-x.railway.internal", "*.railway.internal"]

    @field_validator("BACKEND_CORS_ORIGINS", mode="before")
    @classmethod
    def parse_cors_origins(cls, v: str | list[str]) -> list[str]:
        if isinstance(v, str):
            v = v.strip()
            if v.startswith("["):
                import json
                try:
                    return json.loads(v)
                except Exception:
                    pass
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        return v

    # ─── PostgreSQL ───────────────────────────────────────────────────────────
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_DB: str = "orbitiq_db"
    POSTGRES_USER: str = "orbitiq"
    POSTGRES_PASSWORD: SecretStr = Field(...)
    POSTGRES_POOL_SIZE: int = Field(default=20, ge=5)
    POSTGRES_MAX_OVERFLOW: int = Field(default=10, ge=0)

    @property
    def DATABASE_URL(self) -> str:
        # Railway injects DATABASE_URL directly — use it if present
        import os
        railway_url = os.environ.get("DATABASE_URL", "")
        if railway_url:
            url = railway_url.replace("postgres://", "postgresql+asyncpg://", 1)
            url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
            return url
        return (
            f"postgresql+asyncpg://{self.POSTGRES_USER}:"
            f"{self.POSTGRES_PASSWORD.get_secret_value()}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    # ─── Redis ────────────────────────────────────────────────────────────────
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_PASSWORD: SecretStr = Field(...)
    REDIS_DB: int = Field(default=0, ge=0, le=15)
    REDIS_CACHE_TTL_SECONDS: int = Field(default=3600, ge=60)
    REDIS_STREAM_AGENT_BUS: str = "orbitiq:agents:bus"

    @property
    def REDIS_URL(self) -> str:
        # Railway injects REDIS_URL directly — use it if present
        import os
        railway_url = os.environ.get("REDIS_URL", "")
        if railway_url:
            return railway_url
        return (
            f"redis://:{self.REDIS_PASSWORD.get_secret_value()}"
            f"@{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"
        )

    # ─── Neo4j ────────────────────────────────────────────────────────────────
    NEO4J_HOST: str = "localhost"
    NEO4J_BOLT_PORT: int = 7687
    NEO4J_USER: str = "bff8c462"
    NEO4J_PASSWORD: SecretStr = Field(default="not-configured")
    NEO4J_DATABASE: str = "bff8c462"

    @property
    def NEO4J_URI(self) -> str:
        import os as _os
        env_uri = _os.environ.get("NEO4J_URI", "")
        if env_uri:
            return env_uri
        return f"bolt://{self.NEO4J_HOST}:{self.NEO4J_BOLT_PORT}"

    # ─── Qdrant ───────────────────────────────────────────────────────────────
    QDRANT_URL: str = ""          # e.g. https://xxxx.us-east4-0.gcp.cloud.qdrant.io
    QDRANT_API_KEY: SecretStr = SecretStr("")
    QDRANT_COLLECTION: str = "aerospace_docs"

    # ─── Weaviate ─────────────────────────────────────────────────────────────
    WEAVIATE_HOST: str = "localhost"
    WEAVIATE_PORT: int = 8080
    WEAVIATE_API_KEY: SecretStr = Field(default="not-configured")

    @property
    def WEAVIATE_URL(self) -> str:
        return f"http://{self.WEAVIATE_HOST}:{self.WEAVIATE_PORT}"

    # ─── InfluxDB ─────────────────────────────────────────────────────────────
    INFLUXDB_HOST: str = "localhost"
    INFLUXDB_PORT: int = 8086
    INFLUXDB_ORG: str = "orbitiq-x"
    INFLUXDB_BUCKET: str = "space_weather"
    INFLUXDB_TOKEN: SecretStr = Field(default="not-configured")

    # ─── MinIO ────────────────────────────────────────────────────────────────
    MINIO_HOST: str = "localhost"
    MINIO_PORT: int = 9000
    MINIO_ROOT_USER: str = "minioadmin"
    MINIO_ROOT_PASSWORD: SecretStr = Field(default="not-configured")
    MINIO_BUCKET_TLE: str = "orbitiq-tle"
    MINIO_BUCKET_DOCS: str = "orbitiq-docs"
    MINIO_BUCKET_MODELS: str = "orbitiq-models"

    # ─── AI / LLM ─────────────────────────────────────────────────────────────
    ANTHROPIC_API_KEY: SecretStr = Field(...)
    ANTHROPIC_MODEL: str = "claude-sonnet-4-6"
    ANTHROPIC_MAX_TOKENS: int = Field(default=4096, ge=256)

    OPENAI_API_KEY: SecretStr = Field(...)
    OPENAI_EMBEDDING_MODEL: str = "text-embedding-3-large"
    OPENAI_EMBEDDING_DIMENSIONS: int = 3072

    # ─── External Space Data APIs ─────────────────────────────────────────────
    SPACETRACK_IDENTITY: str = ""
    SPACETRACK_PASSWORD: SecretStr = SecretStr("")
    SPACETRACK_BASE_URL: AnyHttpUrl = AnyHttpUrl("https://www.space-track.org")
    SPACETRACK_RATE_LIMIT_PER_HOUR: int = 300

    CELESTRAK_BASE_URL: AnyHttpUrl = AnyHttpUrl("https://celestrak.org")
    NASA_API_KEY: SecretStr = SecretStr("")

    # ─── Orbital Engine ───────────────────────────────────────────────────────
    ORBITAL_PROPAGATION_STEP_SECONDS: int = Field(default=60, ge=1)
    ORBITAL_MAX_PROPAGATION_DAYS: int = Field(default=30, ge=1, le=365)
    ORBITAL_SGP4_WGS: Literal[72, 84] = 72
    ORBITAL_CONJUNCTION_SCREENING_RANGE_KM: float = Field(default=5.0, gt=0.0)
    ORBITAL_CONJUNCTION_PC_THRESHOLD: float = Field(default=0.0001, gt=0.0, lt=1.0)
    ORBITAL_BATCH_PROPAGATION_WORKERS: int = Field(default=8, ge=1)

    # ─── RAG ──────────────────────────────────────────────────────────────────
    RAG_CHUNK_SIZE: int = Field(default=512, ge=128)
    RAG_CHUNK_OVERLAP: int = Field(default=64, ge=0)
    RAG_TOP_K_RETRIEVAL: int = Field(default=10, ge=1)
    RAG_TOP_K_RERANK: int = Field(default=3, ge=1)
    RAG_MIN_RELEVANCE_SCORE: float = Field(default=0.65, ge=0.0, le=1.0)

    # ─── Agent System ─────────────────────────────────────────────────────────
    AGENT_MAX_ITERATIONS: int = Field(default=15, ge=1)
    AGENT_TIMEOUT_SECONDS: int = Field(default=120, ge=10)
    AGENT_TEMPERATURE: float = Field(default=0.1, ge=0.0, le=1.0)

    # ─── Monitoring ───────────────────────────────────────────────────────────
    SENTRY_DSN: str = ""
    OTEL_EXPORTER_OTLP_ENDPOINT: str = "http://localhost:4317"
    OTEL_SERVICE_NAME: str = "orbitiq-x-backend"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """
    Return the cached application settings singleton.

    Usage
    -----
    In FastAPI dependency injection::

        from app.core.config import get_settings
        from fastapi import Depends

        @router.get("/example")
        async def example(settings: Settings = Depends(get_settings)):
            ...

    Or at module level (avoid in hot paths)::

        settings = get_settings()
    """
    return Settings()

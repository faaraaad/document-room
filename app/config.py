import os
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # App Settings
    PROJECT_NAME: str = "CollabStream"
    API_V1_STR: str = "/api"

    # Infrastructure Connection URLs
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/collabstream"
    REDIS_URL: str = "redis://localhost:6379/0"

    # S3 Object Storage Configuration (MinIO / S3)
    S3_ENDPOINT_URL: Optional[str] = "http://localhost:9000"
    S3_ACCESS_KEY: Optional[str] = "miniouser"
    S3_SECRET_KEY: Optional[str] = "miniopassword"
    S3_BUCKET_NAME: str = "document-snapshots"

    # JWT Authentication config
    JWT_SECRET: str = "super-secret-collabstream-jwt-token-key-2026"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 1 day

    # AI Models APIs
    OPENAI_API_KEY: Optional[str] = None
    ANTHROPIC_API_KEY: Optional[str] = None

    # Telemetry and Observability Configuration
    OTEL_EXPORTER_OTLP_ENDPOINT: Optional[str] = "http://localhost:4317"
    OTEL_SERVICE_NAME: str = "collabstream"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )


settings = Settings()

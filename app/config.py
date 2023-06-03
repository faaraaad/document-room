import os
from typing import Optional
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    PROJECT_NAME: str = "CollabStream"
    API_V1_STR: str = "/api"
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/collabstream"
    REDIS_URL: str = "redis://localhost:6379/0"
    JWT_SECRET: str = "super-secret-collabstream-jwt-token-key-2026"
    JWT_ALGORITHM: str = "HS256"


settings = Settings()

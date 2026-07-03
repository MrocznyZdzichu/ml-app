from functools import lru_cache

from pydantic import AliasChoices, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "ML App"
    app_env: str = Field(default="local", alias="APP_ENV")
    app_secret_key: str = Field(default="dev-secret", alias="APP_SECRET_KEY")
    access_token_expire_minutes: int = Field(default=1440, alias="ACCESS_TOKEN_EXPIRE_MINUTES")

    database_url: str = Field(
        default="postgresql+psycopg://mlapp:mlapp@postgres:5432/mlapp",
        alias="DATABASE_URL",
    )
    redis_url: str = Field(default="redis://redis:6379/0", alias="REDIS_URL")
    descriptive_profile_result_expires_seconds: int = Field(
        default=3600,
        ge=60,
        alias="DESCRIPTIVE_PROFILE_RESULT_EXPIRES_SECONDS",
    )
    duckdb_threads: int = Field(
        default=4,
        ge=1,
        validation_alias=AliasChoices("DUCKDB_THREADS", "DESCRIPTIVE_PROFILE_DUCKDB_THREADS"),
    )
    duckdb_memory_limit: str = Field(
        default="1GB",
        pattern=r"(?i)^\d+(\.\d+)?\s*(KB|MB|GB|TB)$",
        alias="DUCKDB_MEMORY_LIMIT",
    )
    visualization_max_concurrency: int = Field(
        default=2,
        ge=1,
        le=32,
        alias="VISUALIZATION_MAX_CONCURRENCY",
    )

    object_storage_endpoint: str = Field(default="minio:9000", alias="OBJECT_STORAGE_ENDPOINT")
    object_storage_access_key: str = Field(default="mlapp", alias="OBJECT_STORAGE_ACCESS_KEY")
    object_storage_secret_key: str = Field(
        default="mlapp-password",
        alias="OBJECT_STORAGE_SECRET_KEY",
    )
    object_storage_bucket: str = Field(default="datasets", alias="OBJECT_STORAGE_BUCKET")

    cors_origins: list[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]

    @model_validator(mode="after")
    def reject_insecure_non_local_secret(self) -> "Settings":
        environment = self.app_env.strip().lower()
        if environment not in {"local", "development", "test"}:
            if self.app_secret_key in {"dev-secret", "change-me-in-development"}:
                raise ValueError("APP_SECRET_KEY must be changed outside local development")
            if len(self.app_secret_key) < 32:
                raise ValueError("APP_SECRET_KEY must contain at least 32 characters outside local development")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()

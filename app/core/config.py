from datetime import timedelta, timezone, tzinfo
from functools import lru_cache
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configurações centralizadas da aplicação carregadas de variáveis de ambiente / .env."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Aplicação
    app_name: str = "CaisMed API"
    app_version: str = "1.0.0"
    app_env: str = "development"
    app_debug: bool = True
    api_prefix: str = "/api"
    app_timezone: str = "America/Recife"

    # Banco de dados (SQLite local por padrão; aceita PostgreSQL em produção)
    database_url: str = "sqlite:///./caismed.db"

    # Segurança / JWT
    jwt_secret_key: str = "caismed-dev-secret-key-troque-em-producao-com-32-chars"
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 1440  # 24 horas

    # CORS
    cors_origins: str = (
        "http://localhost:8081,"
        "http://localhost:19006,"
        "http://localhost:3000,"
        "http://127.0.0.1:8081"
    )

    # Inteligência Artificial (Google Gemini)
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"
    gemini_timeout_seconds: float = 8.0

    @property
    def normalized_database_url(self) -> str:
        """Normaliza URLs de PostgreSQL (Render/Railway/Heroku) para o driver psycopg v3."""
        url = self.database_url.strip()
        if url.startswith("postgres://"):
            return url.replace("postgres://", "postgresql+psycopg://", 1)
        if url.startswith("postgresql://") and "+psycopg" not in url and "+asyncpg" not in url:
            return url.replace("postgresql://", "postgresql+psycopg://", 1)
        return url

    @property
    def is_sqlite(self) -> bool:
        return self.normalized_database_url.startswith("sqlite")

    @property
    def database_backend(self) -> str:
        if self.is_sqlite:
            return "sqlite"
        if self.normalized_database_url.startswith("postgresql"):
            return "postgresql"
        return self.normalized_database_url.split(":", 1)[0]

    @property
    def cors_origins_list(self) -> list[str]:
        raw = self.cors_origins.strip()
        if not raw:
            return []
        if raw == "*":
            return ["*"]
        return [origin.strip() for origin in raw.split(",") if origin.strip()]

    @property
    def gemini_configured(self) -> bool:
        return bool(self.gemini_api_key and self.gemini_api_key.strip())

    @property
    def tz(self) -> tzinfo:
        try:
            return ZoneInfo(self.app_timezone)
        except ZoneInfoNotFoundError:
            # Fallback para UTC-3 (Recife/Brasília) caso tzdata não esteja instalado
            return timezone(timedelta(hours=-3))


@lru_cache
def get_settings() -> Settings:
    return Settings()

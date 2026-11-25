from typing import Any

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class CamelModel(BaseModel):
    """Base Pydantic v2 com serialização automática em camelCase compatível com o app mobile."""

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        from_attributes=True,
        serialize_by_alias=True,
    )


class ErrorResponse(CamelModel):
    message: str
    detail: Any
    code: str | None = None
    errors: list[dict[str, Any]] | None = None


class DatabaseHealth(CamelModel):
    ok: bool
    backend: str
    detail: str


class AIHealth(CamelModel):
    provider: str
    model: str
    configured: bool
    fallback_enabled: bool = True


class HealthResponse(CamelModel):
    status: str
    app: str
    version: str
    environment: str
    api_prefix: str
    timezone: str
    database: DatabaseHealth
    ai: AIHealth
    timestamp: str

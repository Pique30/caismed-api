from datetime import datetime

from fastapi import APIRouter, status
from fastapi.responses import JSONResponse

from app.core.config import get_settings
from app.core.database import check_database_connection
from app.schemas.common import AIHealth, DatabaseHealth, HealthResponse

router = APIRouter(tags=["Sistema"])


def _build_health_response() -> tuple[int, HealthResponse]:
    settings = get_settings()
    db_ok, db_detail = check_database_connection()
    payload = HealthResponse(
        status="ok" if db_ok else "degraded",
        app=settings.app_name,
        version=settings.app_version,
        environment=settings.app_env,
        api_prefix=settings.api_prefix,
        timezone=settings.app_timezone,
        database=DatabaseHealth(
            ok=db_ok,
            backend=settings.database_backend,
            detail=db_detail,
        ),
        ai=AIHealth(
            provider="gemini" if settings.gemini_configured else "fallback",
            model=settings.gemini_model,
            configured=settings.gemini_configured,
            fallback_enabled=True,
        ),
        timestamp=datetime.now(settings.tz).isoformat(),
    )
    http_status = status.HTTP_200_OK if db_ok else status.HTTP_503_SERVICE_UNAVAILABLE
    return http_status, payload


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Verificar saúde da API",
    description="Retorna o status da API, conexão com o banco de dados e estado da integração com IA.",
)
def healthcheck() -> JSONResponse:
    http_status, payload = _build_health_response()
    return JSONResponse(status_code=http_status, content=payload.model_dump(by_alias=True))

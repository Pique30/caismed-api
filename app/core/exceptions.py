import logging
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger("caismed.api")

DEFAULT_STATUS_MESSAGES: dict[int, str] = {
    status.HTTP_400_BAD_REQUEST: "Confira os dados informados e tente novamente.",
    status.HTTP_401_UNAUTHORIZED: "Sua sessão expirou. Entre de novo.",
    status.HTTP_403_FORBIDDEN: "Você não tem permissão para esta ação.",
    status.HTTP_404_NOT_FOUND: "Não encontramos o que você procurou.",
    status.HTTP_405_METHOD_NOT_ALLOWED: "Método não permitido para esta rota.",
    status.HTTP_409_CONFLICT: "Conflito com os dados existentes.",
    status.HTTP_422_UNPROCESSABLE_CONTENT: "Há dados inválidos. Confira e tente de novo.",
    status.HTTP_500_INTERNAL_SERVER_ERROR: "O servidor não conseguiu responder. Tente mais tarde.",
}


class ApiException(Exception):
    """Exceção de domínio/HTTP padronizada para respostas compatíveis com o app mobile."""

    def __init__(
        self,
        status_code: int,
        message: str,
        *,
        code: str | None = None,
        details: Any | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.message = message
        self.code = code
        self.details = details


def build_error_payload(
    message: str,
    *,
    detail: Any | None = None,
    code: str | None = None,
    errors: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Monta o envelope padrão contendo sempre 'message' (mobile) e 'detail' (FastAPI/Swagger)."""
    payload: dict[str, Any] = {
        "message": message,
        "detail": detail if detail is not None else message,
    }
    if code:
        payload["code"] = code
    if errors is not None:
        payload["errors"] = errors
    return payload


def _format_validation_errors(exc: RequestValidationError) -> tuple[str, list[dict[str, Any]]]:
    formatted: list[dict[str, Any]] = []
    for err in exc.errors():
        loc = [str(part) for part in err.get("loc", []) if part not in ("body", "query", "path")]
        field = ".".join(loc) if loc else "dados"
        formatted.append(
            {
                "field": field,
                "message": err.get("msg", "Valor inválido."),
                "type": err.get("type", "validation_error"),
            }
        )
    if formatted:
        first = formatted[0]
        summary = f"Dados inválidos no campo '{first['field']}': {first['message']}"
    else:
        summary = DEFAULT_STATUS_MESSAGES[status.HTTP_422_UNPROCESSABLE_CONTENT]
    return summary, formatted


def register_exception_handlers(app: FastAPI) -> None:
    """Registra tratadores globais de erro na instância FastAPI."""

    @app.exception_handler(ApiException)
    async def _api_exception_handler(_request: Request, exc: ApiException) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=build_error_payload(
                exc.message,
                detail=exc.details if exc.details is not None else exc.message,
                code=exc.code,
            ),
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_exception_handler(
        _request: Request, exc: StarletteHTTPException
    ) -> JSONResponse:
        raw_detail = exc.detail
        fallback = DEFAULT_STATUS_MESSAGES.get(
            exc.status_code,
            DEFAULT_STATUS_MESSAGES[status.HTTP_500_INTERNAL_SERVER_ERROR],
        )
        # Substitui textos padrão em inglês do Starlette/FastAPI por mensagens amigáveis em PT-BR
        english_defaults = {
            "Not Found",
            "Method Not Allowed",
            "Not authenticated",
            "Forbidden",
            "Bad Request",
        }
        if isinstance(raw_detail, str) and raw_detail not in english_defaults:
            message = raw_detail
        else:
            message = fallback
        code = "SESSAO" if exc.status_code == status.HTTP_401_UNAUTHORIZED else None
        return JSONResponse(
            status_code=exc.status_code,
            content=build_error_payload(message, detail=message, code=code),
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_exception_handler(
        _request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        summary, errors = _format_validation_errors(exc)
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            content=build_error_payload(summary, detail=errors, code="VALIDACAO", errors=errors),
        )

    @app.exception_handler(Exception)
    async def _unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Erro não tratado em %s %s: %s", request.method, request.url.path, exc)
        message = DEFAULT_STATUS_MESSAGES[status.HTTP_500_INTERNAL_SERVER_ERROR]
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=build_error_payload(message, detail=message, code="ERRO_INTERNO"),
        )

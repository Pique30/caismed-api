from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from uuid import uuid4

import bcrypt
import jwt
from fastapi import Depends, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.core.exceptions import ApiException
from app.models.token import TokenRevogado


class PerfilEnum(str, Enum):
    PACIENTE = "paciente"
    PROFISSIONAL = "profissional"
    ADMIN = "admin"


@dataclass(frozen=True)
class TokenPayload:
    sub: str
    perfil: PerfilEnum
    jti: str
    exp: int
    iat: int


bearer_scheme = HTTPBearer(
    scheme_name="BearerAuth",
    description="Informe o token JWT recebido em POST /api/auth/login ou POST /api/auth/register.",
    auto_error=False,
)


def hash_password(plain_password: str) -> str:
    """Gera hash bcrypt seguro da senha em texto puro."""
    password_bytes = plain_password.encode("utf-8")
    salt = bcrypt.gensalt(rounds=12)
    return bcrypt.hashpw(password_bytes, salt).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifica senha em texto puro contra hash bcrypt armazenado."""
    if not plain_password or not hashed_password:
        return False
    try:
        return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))
    except ValueError:
        return False


def create_access_token(
    subject: str,
    perfil: PerfilEnum | str,
    *,
    expires_minutes: int | None = None,
) -> str:
    """Cria um token JWT assinado contendo sub (ID em string), perfil, jti, iat e exp."""
    settings = get_settings()
    perfil_enum = PerfilEnum(perfil)
    now = datetime.now(timezone.utc)
    expire_delta = timedelta(
        minutes=expires_minutes
        if expires_minutes is not None
        else settings.jwt_access_token_expire_minutes
    )
    expires_at = now + expire_delta

    claims = {
        "sub": str(subject),
        "perfil": perfil_enum.value,
        "jti": uuid4().hex,
        "iat": int(now.timestamp()),
        "exp": int(expires_at.timestamp()),
    }
    return jwt.encode(claims, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> TokenPayload:
    """Decodifica e valida assinatura, expiração e claims obrigatórias do JWT."""
    settings = get_settings()
    try:
        data = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
            options={"require": ["sub", "perfil", "jti", "exp", "iat"]},
        )
        return TokenPayload(
            sub=str(data["sub"]),
            perfil=PerfilEnum(data["perfil"]),
            jti=str(data["jti"]),
            exp=int(data["exp"]),
            iat=int(data["iat"]),
        )
    except (jwt.PyJWTError, ValueError, KeyError) as exc:
        raise ApiException(
            status.HTTP_401_UNAUTHORIZED,
            "Sua sessão expirou. Entre de novo.",
            code="SESSAO",
        ) from exc


def is_token_revoked(db: Session, jti: str) -> bool:
    """Verifica se o token (via jti) foi revogado em logout."""
    stmt = select(TokenRevogado.jti).where(TokenRevogado.jti == jti)
    return db.execute(stmt).scalar_one_or_none() is not None


def revoke_token(db: Session, payload: TokenPayload) -> None:
    """Registra o token como revogado e limpa entradas já expiradas."""
    now = datetime.now(timezone.utc)
    db.execute(delete(TokenRevogado).where(TokenRevogado.expira_em < now))
    if not is_token_revoked(db, payload.jti):
        db.add(
            TokenRevogado(
                jti=payload.jti,
                expira_em=datetime.fromtimestamp(payload.exp, tz=timezone.utc),
            )
        )
    db.commit()


def get_current_token_payload(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> TokenPayload:
    """Dependência FastAPI que exige Bearer JWT válido e não revogado."""
    if credentials is None or credentials.scheme.lower() != "bearer" or not credentials.credentials:
        raise ApiException(
            status.HTTP_401_UNAUTHORIZED,
            "Sua sessão expirou. Entre de novo.",
            code="SESSAO",
        )
    payload = decode_access_token(credentials.credentials)
    if is_token_revoked(db, payload.jti):
        raise ApiException(
            status.HTTP_401_UNAUTHORIZED,
            "Sua sessão expirou. Entre de novo.",
            code="SESSAO",
        )
    return payload


def require_roles(*allowed_roles: PerfilEnum) -> Callable[..., TokenPayload]:
    """Cria dependência RBAC restringindo a rota aos perfis autorizados."""
    allowed = set(allowed_roles)

    def _checker(payload: TokenPayload = Depends(get_current_token_payload)) -> TokenPayload:
        if payload.perfil not in allowed:
            raise ApiException(
                status.HTTP_403_FORBIDDEN,
                "Você não tem permissão para esta ação.",
            )
        return payload

    return _checker

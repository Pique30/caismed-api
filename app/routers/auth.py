from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import (
    PerfilEnum,
    TokenPayload,
    get_current_token_payload,
    require_roles,
)
from app.schemas.auth import (
    AdminMeOut,
    AuthTokenOut,
    LoginIn,
    LogoutOut,
    PacienteMeOut,
    PacienteUpdateIn,
    ProfissionalMeOut,
    RegisterIn,
)
from app.services import auth_service

router = APIRouter(tags=["Autenticação"])


@router.post(
    "/auth/register",
    response_model=AuthTokenOut,
    status_code=status.HTTP_201_CREATED,
    summary="Cadastrar novo paciente",
)
def register(body: RegisterIn, db: Session = Depends(get_db)) -> AuthTokenOut:
    return auth_service.registrar_paciente(db, body)


@router.post(
    "/auth/login",
    response_model=AuthTokenOut,
    summary="Autenticar usuário (paciente, profissional ou admin)",
)
def login(body: LoginIn, db: Session = Depends(get_db)) -> AuthTokenOut:
    return auth_service.autenticar_usuario(db, body)


@router.post(
    "/auth/logout",
    response_model=LogoutOut,
    summary="Encerrar sessão revogando o token JWT atual",
)
def logout(
    payload: TokenPayload = Depends(get_current_token_payload),
    db: Session = Depends(get_db),
) -> LogoutOut:
    auth_service.encerrar_sessao(db, payload)
    return LogoutOut()


@router.get(
    "/auth/me",
    response_model=PacienteMeOut | ProfissionalMeOut | AdminMeOut,
    summary="Obter dados do usuário autenticado",
)
def me(
    payload: TokenPayload = Depends(get_current_token_payload),
    db: Session = Depends(get_db),
) -> PacienteMeOut | ProfissionalMeOut | AdminMeOut:
    return auth_service.obter_usuario_atual(db, payload)


@router.put(
    "/pacientes/me",
    response_model=PacienteMeOut,
    summary="Atualizar dados cadastrais do paciente logado",
)
def atualizar_paciente_me(
    body: PacienteUpdateIn,
    payload: TokenPayload = Depends(require_roles(PerfilEnum.PACIENTE)),
    db: Session = Depends(get_db),
) -> PacienteMeOut:
    return auth_service.atualizar_perfil_paciente(db, payload, body)

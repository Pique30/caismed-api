from fastapi import APIRouter, Body, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import (
    PerfilEnum,
    TokenPayload,
    get_current_token_payload,
    require_roles,
)
from app.schemas.consulta import (
    ConsultaCancelarIn,
    ConsultaCreateIn,
    ConsultaOut,
    ConsultaReagendarIn,
    ConsultaStatusIn,
)
from app.services import consulta_service

router = APIRouter(prefix="/consultas", tags=["Consultas"])


@router.get(
    "",
    response_model=list[ConsultaOut],
    summary="Listar consultas do usuário logado (próximas e histórico)",
)
def listar_consultas(
    status_filtro: str | None = Query(default=None, alias="status"),
    payload: TokenPayload = Depends(get_current_token_payload),
    db: Session = Depends(get_db),
) -> list[ConsultaOut]:
    return consulta_service.listar_consultas(db, payload, status_filtro=status_filtro)


@router.post(
    "",
    response_model=ConsultaOut,
    status_code=status.HTTP_201_CREATED,
    summary="Agendar nova consulta (com vínculo opcional à pré-triagem)",
)
def agendar_consulta(
    body: ConsultaCreateIn,
    payload: TokenPayload = Depends(require_roles(PerfilEnum.PACIENTE)),
    db: Session = Depends(get_db),
) -> ConsultaOut:
    return consulta_service.criar_consulta(db, payload, body)


@router.patch(
    "/{consulta_id}/cancelar",
    response_model=ConsultaOut,
    summary="Cancelar consulta agendada (regra de 24h para paciente)",
)
def cancelar_consulta(
    consulta_id: str,
    body: ConsultaCancelarIn | None = Body(default=None),
    payload: TokenPayload = Depends(get_current_token_payload),
    db: Session = Depends(get_db),
) -> ConsultaOut:
    return consulta_service.cancelar_consulta(db, payload, consulta_id, body)


@router.patch(
    "/{consulta_id}/reagendar",
    response_model=ConsultaOut,
    summary="Reagendar consulta para nova data/horário",
)
def reagendar_consulta(
    consulta_id: str,
    body: ConsultaReagendarIn,
    payload: TokenPayload = Depends(require_roles(PerfilEnum.PACIENTE, PerfilEnum.ADMIN)),
    db: Session = Depends(get_db),
) -> ConsultaOut:
    return consulta_service.reagendar_consulta(db, payload, consulta_id, body)


@router.patch(
    "/{consulta_id}/status",
    response_model=ConsultaOut,
    summary="Atualizar status da consulta (profissional ou admin)",
)
def atualizar_status_consulta(
    consulta_id: str,
    body: ConsultaStatusIn,
    payload: TokenPayload = Depends(require_roles(PerfilEnum.PROFISSIONAL, PerfilEnum.ADMIN)),
    db: Session = Depends(get_db),
) -> ConsultaOut:
    return consulta_service.atualizar_status_consulta(db, payload, consulta_id, body)

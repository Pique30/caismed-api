from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import PerfilEnum, TokenPayload, require_roles
from app.schemas.catalogo import (
    ClinicaCreateIn,
    ClinicaOut,
    ClinicaUpdateIn,
    DisponibilidadeCreateIn,
    DisponibilidadeOut,
    EspecialidadeCreateIn,
    EspecialidadeOut,
    EspecialidadeUpdateIn,
    ProfissionalCreateIn,
    ProfissionalOut,
    ProfissionalUpdateIn,
)
from app.schemas.notificacao import OkOut
from app.services import admin_service

router = APIRouter(
    prefix="/admin",
    tags=["Administração"],
    dependencies=[Depends(require_roles(PerfilEnum.ADMIN))],
)


@router.post(
    "/especialidades",
    response_model=EspecialidadeOut,
    status_code=status.HTTP_201_CREATED,
    summary="Cadastrar especialidade (admin)",
)
def criar_especialidade(
    body: EspecialidadeCreateIn, db: Session = Depends(get_db)
) -> EspecialidadeOut:
    return admin_service.criar_especialidade(db, body)


@router.put(
    "/especialidades/{especialidade_id}",
    response_model=EspecialidadeOut,
    summary="Atualizar especialidade (admin)",
)
def atualizar_especialidade(
    especialidade_id: str,
    body: EspecialidadeUpdateIn,
    db: Session = Depends(get_db),
) -> EspecialidadeOut:
    return admin_service.atualizar_especialidade(db, especialidade_id, body)


@router.post(
    "/clinicas",
    response_model=ClinicaOut,
    status_code=status.HTTP_201_CREATED,
    summary="Cadastrar clínica (admin)",
)
def criar_clinica(body: ClinicaCreateIn, db: Session = Depends(get_db)) -> ClinicaOut:
    return admin_service.criar_clinica(db, body)


@router.put(
    "/clinicas/{clinica_id}",
    response_model=ClinicaOut,
    summary="Atualizar clínica (admin)",
)
def atualizar_clinica(
    clinica_id: str, body: ClinicaUpdateIn, db: Session = Depends(get_db)
) -> ClinicaOut:
    return admin_service.atualizar_clinica(db, clinica_id, body)


@router.post(
    "/profissionais",
    response_model=ProfissionalOut,
    status_code=status.HTTP_201_CREATED,
    summary="Cadastrar profissional de saúde (admin)",
)
def criar_profissional(
    body: ProfissionalCreateIn, db: Session = Depends(get_db)
) -> ProfissionalOut:
    return admin_service.criar_profissional(db, body)


@router.put(
    "/profissionais/{profissional_id}",
    response_model=ProfissionalOut,
    summary="Atualizar profissional de saúde (admin)",
)
def atualizar_profissional(
    profissional_id: str,
    body: ProfissionalUpdateIn,
    db: Session = Depends(get_db),
) -> ProfissionalOut:
    return admin_service.atualizar_profissional(db, profissional_id, body)


@router.post(
    "/profissionais/{profissional_id}/disponibilidades",
    response_model=DisponibilidadeOut,
    status_code=status.HTTP_201_CREATED,
    summary="Adicionar grade de disponibilidade a um profissional (admin)",
)
def adicionar_disponibilidade(
    profissional_id: str,
    body: DisponibilidadeCreateIn,
    db: Session = Depends(get_db),
) -> DisponibilidadeOut:
    return admin_service.adicionar_disponibilidade(db, profissional_id, body)


@router.delete(
    "/disponibilidades/{disponibilidade_id}",
    response_model=OkOut,
    summary="Remover bloco de disponibilidade (admin)",
)
def remover_disponibilidade(
    disponibilidade_id: str,
    _payload: TokenPayload = Depends(require_roles(PerfilEnum.ADMIN)),
    db: Session = Depends(get_db),
) -> OkOut:
    admin_service.remover_disponibilidade(db, disponibilidade_id)
    return OkOut(ok=True)

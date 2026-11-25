from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import TokenPayload, get_current_token_payload
from app.schemas.catalogo import ClinicaOut, EspecialidadeOut, HorarioSlotOut, ProfissionalOut
from app.services import agenda_service

router = APIRouter(tags=["Catálogo"])


@router.get(
    "/especialidades",
    response_model=list[EspecialidadeOut],
    summary="Listar especialidades médicas",
)
def listar_especialidades(db: Session = Depends(get_db)) -> list[EspecialidadeOut]:
    return agenda_service.listar_especialidades(db)


@router.get(
    "/clinicas",
    response_model=list[ClinicaOut],
    summary="Listar clínicas da rede com busca opcional",
)
def listar_clinicas(
    q: str = Query(default="", description="Filtro por nome, bairro ou cidade"),
    db: Session = Depends(get_db),
) -> list[ClinicaOut]:
    return agenda_service.listar_clinicas(db, q=q)


@router.get(
    "/profissionais",
    response_model=list[ProfissionalOut],
    summary="Listar profissionais com filtros e próximo horário disponível",
)
def listar_profissionais(
    especialidade: str | None = Query(default=None),
    clinica: str | None = Query(default=None),
    q: str = Query(default=""),
    _payload: TokenPayload = Depends(get_current_token_payload),
    db: Session = Depends(get_db),
) -> list[ProfissionalOut]:
    return agenda_service.listar_profissionais(
        db, especialidade=especialidade, clinica=clinica, q=q
    )


@router.get(
    "/profissionais/{profissional_id}/horarios",
    response_model=list[HorarioSlotOut],
    summary="Consultar horários disponíveis de um profissional em uma data",
)
def horarios_profissional(
    profissional_id: str,
    data: str | None = Query(default=None, description="Data no formato AAAA-MM-DD"),
    clinica: str | None = Query(default=None, description="ID da clínica"),
    _payload: TokenPayload = Depends(get_current_token_payload),
    db: Session = Depends(get_db),
) -> list[HorarioSlotOut]:
    return agenda_service.obter_horarios_profissional(
        db, profissional_id=profissional_id, data_str=data, clinica_id=clinica
    )

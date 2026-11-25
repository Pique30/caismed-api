from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import (
    PerfilEnum,
    TokenPayload,
    get_current_token_payload,
    require_roles,
)
from app.schemas.triagem import TriagemCreateIn, TriagemOut
from app.services import triagem_service

router = APIRouter(prefix="/triagens", tags=["Pré-triagem IA"])


@router.post(
    "",
    response_model=TriagemOut,
    status_code=status.HTTP_201_CREATED,
    summary="Executar pré-triagem inteligente com IA (Google Gemini + fallback)",
)
def criar_triagem(
    body: TriagemCreateIn,
    payload: TokenPayload = Depends(require_roles(PerfilEnum.PACIENTE)),
    db: Session = Depends(get_db),
) -> TriagemOut:
    return triagem_service.criar_triagem(db, payload, body)


@router.get(
    "",
    response_model=list[TriagemOut],
    summary="Listar histórico de pré-triagens do paciente",
)
def listar_triagens(
    payload: TokenPayload = Depends(require_roles(PerfilEnum.PACIENTE, PerfilEnum.ADMIN)),
    db: Session = Depends(get_db),
) -> list[TriagemOut]:
    return triagem_service.listar_triagens_paciente(db, payload)


@router.get(
    "/{triagem_id}",
    response_model=TriagemOut,
    summary="Consultar detalhes de uma pré-triagem específica",
)
def obter_triagem(
    triagem_id: str,
    payload: TokenPayload = Depends(get_current_token_payload),
    db: Session = Depends(get_db),
) -> TriagemOut:
    return triagem_service.obter_triagem(db, payload, triagem_id)

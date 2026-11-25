from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import TokenPayload, get_current_token_payload
from app.schemas.notificacao import NotificacaoOut, OkOut
from app.services import notificacao_service

router = APIRouter(prefix="/notificacoes", tags=["Notificações"])


@router.get(
    "",
    response_model=list[NotificacaoOut],
    summary="Listar notificações e lembretes do usuário autenticado",
)
def listar_notificacoes(
    payload: TokenPayload = Depends(get_current_token_payload),
    db: Session = Depends(get_db),
) -> list[NotificacaoOut]:
    return notificacao_service.listar_notificacoes(db, payload.sub)


@router.patch(
    "/ler-todas",
    response_model=OkOut,
    summary="Marcar todas as notificações do usuário como lidas",
)
def ler_todas_notificacoes(
    payload: TokenPayload = Depends(get_current_token_payload),
    db: Session = Depends(get_db),
) -> OkOut:
    notificacao_service.marcar_todas_como_lidas(db, payload.sub)
    return OkOut(ok=True)

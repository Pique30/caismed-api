from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.orm import Session, joinedload

from app.core.utils import format_date_br, hours_until
from app.models.consulta import Consulta
from app.models.notificacao import Notificacao
from app.schemas.notificacao import NotificacaoOut


def criar_notificacao(db: Session, usuario_id: str, titulo: str, texto: str) -> Notificacao:
    notif = Notificacao(
        usuario_id=usuario_id,
        titulo=titulo,
        texto=texto,
        lida=False,
        quando=datetime.now(timezone.utc),
    )
    db.add(notif)
    return notif


def _gerar_lembretes_24h(db: Session, usuario_id: str) -> None:
    """Gera lembrete in-app para consultas agendadas do paciente dentro das próximas 24 horas."""
    stmt = (
        select(Consulta)
        .options(joinedload(Consulta.especialidade), joinedload(Consulta.clinica))
        .where(
            Consulta.paciente_id == usuario_id,
            Consulta.status == "agendada",
            Consulta.lembrete_enviado.is_(False),
        )
    )
    consultas = db.scalars(stmt).all()
    criou = False
    for c in consultas:
        horas = hours_until(c.data, c.hora)
        if 0 < horas <= 24:
            esp_nome = c.especialidade.nome if c.especialidade else "Consulta"
            clinica_nome = c.clinica.nome if c.clinica else "CaisMed"
            criar_notificacao(
                db,
                usuario_id=usuario_id,
                titulo="Lembrete de consulta",
                texto=f"{esp_nome} em {format_date_br(c.data)} às {c.hora}, {clinica_nome}.",
            )
            c.lembrete_enviado = True
            criou = True
    if criou:
        db.commit()


def listar_notificacoes(db: Session, usuario_id: str) -> list[NotificacaoOut]:
    _gerar_lembretes_24h(db, usuario_id)
    stmt = (
        select(Notificacao)
        .where(Notificacao.usuario_id == usuario_id)
        .order_by(Notificacao.quando.desc())
    )
    itens = db.scalars(stmt).all()
    return [
        NotificacaoOut(
            id=n.id,
            titulo=n.titulo,
            texto=n.texto,
            quando=n.quando.isoformat(),
            lida=n.lida,
        )
        for n in itens
    ]


def marcar_todas_como_lidas(db: Session, usuario_id: str) -> None:
    db.execute(
        update(Notificacao)
        .where(Notificacao.usuario_id == usuario_id, Notificacao.lida.is_(False))
        .values(lida=True)
    )
    db.commit()

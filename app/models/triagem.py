from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


def _new_id() -> str:
    return uuid4().hex


class Triagem(Base):
    __tablename__ = "triagens"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_new_id)
    paciente_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("pacientes.usuario_id", ondelete="CASCADE"), nullable=False, index=True
    )
    descricao: Mapped[str] = mapped_column(Text, nullable=False)
    duracao: Mapped[str] = mapped_column(String(60), default="nao_informada", nullable=False)
    intensidade: Mapped[int | None] = mapped_column(Integer, nullable=True)
    detalhes: Mapped[str] = mapped_column(Text, default="", nullable=False)

    resposta: Mapped[str] = mapped_column(Text, default="", nullable=False)
    nivel_atencao: Mapped[str] = mapped_column(String(20), nullable=False)  # rotina | breve | urgente
    orientacao: Mapped[str] = mapped_column(Text, nullable=False)
    aviso: Mapped[str] = mapped_column(Text, nullable=False)
    recomendacoes_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    provedor_ia: Mapped[str] = mapped_column(String(40), default="fallback", nullable=False)
    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    paciente: Mapped["Paciente"] = relationship(back_populates="triagens")
    consultas: Mapped[list["Consulta"]] = relationship(back_populates="triagem")

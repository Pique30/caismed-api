from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


def _new_id() -> str:
    return uuid4().hex


class Notificacao(Base):
    __tablename__ = "notificacoes"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_new_id)
    usuario_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("usuarios.id", ondelete="CASCADE"), nullable=False, index=True
    )
    titulo: Mapped[str] = mapped_column(String(160), nullable=False)
    texto: Mapped[str] = mapped_column(Text, nullable=False)
    lida: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    quando: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True,
    )

    usuario: Mapped["Usuario"] = relationship(back_populates="notificacoes")

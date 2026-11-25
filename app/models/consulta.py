from datetime import date, datetime, timezone
from uuid import uuid4

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Index, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


def _new_id() -> str:
    return uuid4().hex


class Consulta(Base):
    __tablename__ = "consultas"
    __table_args__ = (
        Index(
            "uq_consulta_profissional_slot_ativo",
            "profissional_id",
            "data",
            "hora",
            unique=True,
            sqlite_where=text("status != 'cancelada'"),
            postgresql_where=text("status != 'cancelada'"),
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_new_id)
    paciente_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("pacientes.usuario_id", ondelete="CASCADE"), nullable=False, index=True
    )
    profissional_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("profissionais.usuario_id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    clinica_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("clinicas.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    especialidade_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("especialidades.id", ondelete="RESTRICT"), nullable=False
    )
    triagem_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("triagens.id", ondelete="SET NULL"), nullable=True, index=True
    )

    data: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    hora: Mapped[str] = mapped_column(String(5), nullable=False)  # "HH:MM"
    status: Mapped[str] = mapped_column(String(20), default="agendada", nullable=False, index=True)
    valor: Mapped[float] = mapped_column(Float, nullable=False)
    motivo_cancelamento: Mapped[str | None] = mapped_column(Text, nullable=True)
    cancelada_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    lembrete_enviado: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    paciente: Mapped["Paciente"] = relationship(back_populates="consultas")
    profissional: Mapped["Profissional"] = relationship(back_populates="consultas")
    clinica: Mapped["Clinica"] = relationship()
    especialidade: Mapped["Especialidade"] = relationship()
    triagem: Mapped["Triagem | None"] = relationship(back_populates="consultas")

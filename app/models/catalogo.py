from uuid import uuid4

from sqlalchemy import Boolean, Column, Float, ForeignKey, Integer, String, Table, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


def _new_id() -> str:
    return uuid4().hex


profissional_especialidades = Table(
    "profissional_especialidades",
    Base.metadata,
    Column(
        "profissional_id",
        String(64),
        ForeignKey("profissionais.usuario_id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "especialidade_id",
        String(64),
        ForeignKey("especialidades.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)


class Especialidade(Base):
    __tablename__ = "especialidades"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    nome: Mapped[str] = mapped_column(String(120), nullable=False)
    descricao: Mapped[str] = mapped_column(Text, default="", nullable=False)
    valor: Mapped[float] = mapped_column(Float, nullable=False)
    ativa: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    profissionais: Mapped[list["Profissional"]] = relationship(
        secondary=profissional_especialidades,
        back_populates="especialidades",
    )


class Clinica(Base):
    __tablename__ = "clinicas"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_new_id)
    nome: Mapped[str] = mapped_column(String(160), nullable=False)
    bairro: Mapped[str] = mapped_column(String(120), nullable=False)
    cidade: Mapped[str] = mapped_column(String(120), nullable=False)
    endereco: Mapped[str] = mapped_column(String(255), nullable=False)
    telefone: Mapped[str] = mapped_column(String(40), default="", nullable=False)
    horario: Mapped[str] = mapped_column(String(160), default="", nullable=False)
    ativa: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    disponibilidades: Mapped[list["Disponibilidade"]] = relationship(
        back_populates="clinica", cascade="all, delete-orphan"
    )


class Disponibilidade(Base):
    """Bloco semanal de atendimento do profissional em uma clínica (dia_semana: 0=Dom..6=Sáb)."""

    __tablename__ = "disponibilidades"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_new_id)
    profissional_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("profissionais.usuario_id", ondelete="CASCADE"), nullable=False, index=True
    )
    clinica_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("clinicas.id", ondelete="CASCADE"), nullable=False, index=True
    )
    dia_semana: Mapped[int] = mapped_column(Integer, nullable=False)  # 0=Domingo .. 6=Sábado
    hora_inicio: Mapped[str] = mapped_column(String(5), nullable=False)  # "08:00"
    hora_fim: Mapped[str] = mapped_column(String(5), nullable=False)  # "12:00"
    duracao_minutos: Mapped[int] = mapped_column(Integer, default=30, nullable=False)

    profissional: Mapped["Profissional"] = relationship(back_populates="disponibilidades")
    clinica: Mapped["Clinica"] = relationship(back_populates="disponibilidades")

from datetime import date, datetime, timezone
from uuid import uuid4

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


def _new_id() -> str:
    return uuid4().hex


class Usuario(Base):
    """Conta de acesso unificada para paciente, profissional e admin."""

    __tablename__ = "usuarios"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=_new_id)
    perfil: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    nome: Mapped[str] = mapped_column(String(160), nullable=False)
    email: Mapped[str | None] = mapped_column(String(160), unique=True, nullable=True, index=True)
    senha_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    ativo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    paciente: Mapped["Paciente | None"] = relationship(
        back_populates="usuario", uselist=False, cascade="all, delete-orphan"
    )
    profissional: Mapped["Profissional | None"] = relationship(
        back_populates="usuario", uselist=False, cascade="all, delete-orphan"
    )
    notificacoes: Mapped[list["Notificacao"]] = relationship(
        back_populates="usuario", cascade="all, delete-orphan"
    )


class Paciente(Base):
    """Dados cadastrais específicos do paciente (vinculado 1:1 ao Usuario)."""

    __tablename__ = "pacientes"

    usuario_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("usuarios.id", ondelete="CASCADE"), primary_key=True
    )
    cpf: Mapped[str] = mapped_column(String(11), unique=True, nullable=False, index=True)
    nascimento: Mapped[date | None] = mapped_column(Date, nullable=True)
    telefone: Mapped[str] = mapped_column(String(30), default="", nullable=False)
    aceite_lgpd: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    aceite_lgpd_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    usuario: Mapped["Usuario"] = relationship(back_populates="paciente")
    consultas: Mapped[list["Consulta"]] = relationship(back_populates="paciente")
    triagens: Mapped[list["Triagem"]] = relationship(back_populates="paciente")


class Profissional(Base):
    """Dados profissionais de médicos/especialistas (vinculado 1:1 ao Usuario)."""

    __tablename__ = "profissionais"

    usuario_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("usuarios.id", ondelete="CASCADE"), primary_key=True
    )
    matricula: Mapped[str] = mapped_column(String(40), unique=True, nullable=False, index=True)
    crm: Mapped[str] = mapped_column(String(40), nullable=False)
    nota: Mapped[float] = mapped_column(Float, default=5.0, nullable=False)
    bio: Mapped[str] = mapped_column(Text, default="", nullable=False)

    usuario: Mapped["Usuario"] = relationship(back_populates="profissional")
    especialidades: Mapped[list["Especialidade"]] = relationship(
        secondary="profissional_especialidades",
        back_populates="profissionais",
    )
    disponibilidades: Mapped[list["Disponibilidade"]] = relationship(
        back_populates="profissional", cascade="all, delete-orphan"
    )
    consultas: Mapped[list["Consulta"]] = relationship(back_populates="profissional")

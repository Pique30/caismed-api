from typing import Literal

from app.schemas.catalogo import ClinicaOut
from app.schemas.common import CamelModel


class ConsultaCreateIn(CamelModel):
    profissional_id: str
    clinica_id: str | None = None
    data: str
    hora: str
    especialidade: str | None = None
    triagem_id: str | None = None


class ConsultaCancelarIn(CamelModel):
    motivo: str = ""


class ConsultaReagendarIn(CamelModel):
    data: str
    hora: str
    clinica_id: str | None = None


class ConsultaStatusIn(CamelModel):
    status: Literal["agendada", "concluida", "faltou"]


class ProfissionalResumoOut(CamelModel):
    id: str
    nome: str
    crm: str


class PacienteResumoOut(CamelModel):
    id: str
    nome: str


class ConsultaOut(CamelModel):
    id: str
    paciente_id: str
    profissional_id: str
    clinica_id: str
    especialidade: str
    especialidade_nome: str
    data: str
    hora: str
    status: str
    valor: float
    triagem_id: str | None = None
    motivo: str | None = None
    criado_em: str
    cancelada_em: str | None = None
    profissional: ProfissionalResumoOut | None = None
    clinica: ClinicaOut | None = None
    paciente: PacienteResumoOut | None = None

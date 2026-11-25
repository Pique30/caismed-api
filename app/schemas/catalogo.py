from pydantic import Field

from app.schemas.common import CamelModel


class EspecialidadeOut(CamelModel):
    id: str
    nome: str
    descricao: str
    valor: float


class EspecialidadeCreateIn(CamelModel):
    id: str = Field(..., min_length=2, max_length=64)
    nome: str = Field(..., min_length=2, max_length=120)
    descricao: str = ""
    valor: float = Field(..., ge=0)


class EspecialidadeUpdateIn(CamelModel):
    nome: str | None = None
    descricao: str | None = None
    valor: float | None = Field(default=None, ge=0)
    ativa: bool | None = None


class ClinicaOut(CamelModel):
    id: str
    nome: str
    bairro: str
    cidade: str
    endereco: str
    telefone: str
    horario: str


class ClinicaCreateIn(CamelModel):
    id: str | None = None
    nome: str = Field(..., min_length=2, max_length=160)
    bairro: str
    cidade: str
    endereco: str
    telefone: str = ""
    horario: str = ""


class ClinicaUpdateIn(CamelModel):
    nome: str | None = None
    bairro: str | None = None
    cidade: str | None = None
    endereco: str | None = None
    telefone: str | None = None
    horario: str | None = None
    ativa: bool | None = None


class ProximoHorarioOut(CamelModel):
    data: str
    hora: str
    clinica_id: str


class ProfissionalOut(CamelModel):
    id: str
    nome: str
    crm: str
    especialidades: list[str]
    nota: float
    bio: str
    clinicas: list[str]
    proximo: ProximoHorarioOut | None = None


class HorarioSlotOut(CamelModel):
    hora: str
    clinica_id: str
    disponivel: bool


class ProfissionalCreateIn(CamelModel):
    id: str | None = None
    nome: str = Field(..., min_length=3)
    email: str | None = None
    matricula: str = Field(..., min_length=2)
    senha: str = Field(..., min_length=6)
    crm: str = Field(..., min_length=3)
    especialidades: list[str] = Field(..., min_length=1)
    nota: float = Field(default=5.0, ge=0, le=5)
    bio: str = ""


class ProfissionalUpdateIn(CamelModel):
    nome: str | None = None
    crm: str | None = None
    especialidades: list[str] | None = None
    nota: float | None = Field(default=None, ge=0, le=5)
    bio: str | None = None
    ativo: bool | None = None


class DisponibilidadeCreateIn(CamelModel):
    clinica_id: str
    dia_semana: int = Field(..., ge=0, le=6)
    hora_inicio: str
    hora_fim: str
    duracao_minutos: int = Field(default=30, ge=10, le=180)


class DisponibilidadeOut(CamelModel):
    id: str
    profissional_id: str
    clinica_id: str
    dia_semana: int
    hora_inicio: str
    hora_fim: str
    duracao_minutos: int

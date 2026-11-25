from typing import Literal

from pydantic import Field

from app.schemas.catalogo import ProximoHorarioOut
from app.schemas.common import CamelModel


class MensagemHistoricoIn(CamelModel):
    de: Literal["eu", "bot"]
    texto: str = Field(..., min_length=1, max_length=600)


class TriagemCreateIn(CamelModel):
    descricao: str
    duracao: str | None = None
    intensidade: int | None = Field(default=None, ge=0, le=10)
    detalhes: str = ""
    historico: list[MensagemHistoricoIn] = Field(default_factory=list)


class MedicoSugeridoOut(CamelModel):
    id: str
    nome: str
    crm: str
    nota: float
    clinicas: list[str] = Field(default_factory=list)
    proximo: ProximoHorarioOut | None = None


class RecomendacaoOut(CamelModel):
    especialidade: str
    nome: str
    prioridade: int
    motivo: str
    medicos: list[MedicoSugeridoOut] = Field(default_factory=list)


class TriagemResultadoOut(CamelModel):
    resposta: str
    recomendacoes: list[RecomendacaoOut]
    nivel_atencao: Literal["rotina", "breve", "urgente"]
    orientacao: str
    aviso: str


class TriagemOut(CamelModel):
    id: str
    paciente_id: str
    descricao: str
    duracao: str
    intensidade: int | None = None
    detalhes: str
    consulta_id: str | None = None
    criado_em: str
    provedor_ia: str
    resultado: TriagemResultadoOut

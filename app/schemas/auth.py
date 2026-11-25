from pydantic import Field

from app.core.security import PerfilEnum
from app.schemas.common import CamelModel


class RegisterIn(CamelModel):
    nome: str
    cpf: str
    nascimento: str | None = None
    telefone: str = ""
    email: str
    senha: str
    aceite_lgpd: bool = Field(default=True, alias="aceiteLGPD")


class LoginIn(CamelModel):
    perfil: PerfilEnum = PerfilEnum.PACIENTE
    login: str
    senha: str


class UsuarioResumoOut(CamelModel):
    id: str
    nome: str
    perfil: str


class AuthTokenOut(CamelModel):
    token: str
    usuario: UsuarioResumoOut


class LogoutOut(CamelModel):
    ok: bool = True
    message: str = "Sessão encerrada com sucesso."


class PacienteMeOut(CamelModel):
    id: str
    nome: str
    cpf: str
    nascimento: str | None = None
    telefone: str
    email: str | None = None
    perfil: str = "paciente"
    criado_em: str


class ProfissionalMeOut(CamelModel):
    id: str
    nome: str
    matricula: str
    crm: str
    especialidades: list[str]
    nota: float
    bio: str
    clinicas: list[str]
    email: str | None = None
    perfil: str = "profissional"
    criado_em: str


class AdminMeOut(CamelModel):
    id: str
    nome: str
    email: str | None = None
    perfil: str = "admin"
    criado_em: str


class PacienteUpdateIn(CamelModel):
    nome: str | None = None
    telefone: str | None = None
    email: str | None = None
    nascimento: str | None = None
    senha: str | None = None

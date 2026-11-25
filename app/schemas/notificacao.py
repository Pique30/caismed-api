from app.schemas.common import CamelModel


class NotificacaoOut(CamelModel):
    id: str
    titulo: str
    texto: str
    quando: str
    lida: bool


class OkOut(CamelModel):
    ok: bool = True

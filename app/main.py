from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core import database
from app.core.config import get_settings
from app.core.exceptions import register_exception_handlers
from app.routers import admin, auth, catalogo, consultas, health, notificacoes, triagens
from app.seed import seed_database

OPENAPI_TAGS = [
    {"name": "Sistema", "description": "Verificação de saúde e metadados da API."},
    {"name": "Autenticação", "description": "Cadastro, login, logout e dados do usuário autenticado."},
    {"name": "Catálogo", "description": "Clínicas, especialidades, profissionais e horários disponíveis."},
    {"name": "Consultas", "description": "Agendamento, histórico, cancelamento, reagendamento e status."},
    {"name": "Pré-triagem IA", "description": "Pré-triagem conversacional com Google Gemini e vínculo com agendamento."},
    {"name": "Notificações", "description": "Central de notificações e lembretes de consulta."},
    {"name": "Administração", "description": "Rotas exclusivas do perfil administrador."},
]


@asynccontextmanager
async def lifespan(_app: FastAPI):
    database.init_db()
    with database.SessionLocal() as db:
        seed_database(db)
    yield


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title=f"{settings.app_name} — Saúde na Palma da Mão",
        version=settings.app_version,
        description=(
            "API REST do projeto **CaisMed** em FastAPI + SQLAlchemy, "
            "compatível com o aplicativo mobile React Native/Expo (`caismed-mobile-main`).\n\n"
            "- Autenticação: `Authorization: Bearer <token>` (perfis `paciente`, `profissional`, `admin`).\n"
            "- Envelope de erro padronizado com `message` e `detail`.\n"
            "- Payloads em `camelCase` e IDs em string.\n"
            "- Contas seed: Paciente CPF `390.533.447-05` / `123456`, Profissional matrícula `2001` / `caismed123`, Admin `admin@caismed.com.br` / `admin123`."
        ),
        openapi_tags=OPENAPI_TAGS,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )

    origins = settings.cors_origins_list
    allow_all = origins == ["*"]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"] if allow_all else origins,
        allow_credentials=not allow_all,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    register_exception_handlers(app)

    # Healthcheck na raiz
    app.include_router(health.router)

    # Todas as rotas de negócio sob /api
    api_router = APIRouter(prefix=settings.api_prefix)
    api_router.include_router(health.router)
    api_router.include_router(auth.router)
    api_router.include_router(catalogo.router)
    api_router.include_router(consultas.router)
    api_router.include_router(triagens.router)
    api_router.include_router(notificacoes.router)
    api_router.include_router(admin.router)
    app.include_router(api_router)

    return app


app = create_app()

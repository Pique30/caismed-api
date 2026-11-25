# CaisMed API — Saúde na Palma da Mão

Backend REST em **Python + FastAPI** para o projeto **CaisMed**, 100% compatível com o aplicativo mobile React Native/Expo (`caismed-mobile-main`).

## Stack

- **FastAPI** + **Uvicorn** (Swagger UI em `/docs` e ReDoc em `/redoc`)
- **SQLAlchemy 2.0** (SQLite local por padrão; PostgreSQL em produção via `DATABASE_URL`)
- **Pydantic v2** com serialização automática em `camelCase` e IDs em string
- **JWT (`PyJWT`) + `bcrypt`** com RBAC (`paciente`, `profissional`, `admin`) e revogação de token no logout
- **Google Gemini (`google-genai`)** isolado em `app/services/ia_service.py` com timeout seguro, guardrails clínicos de urgência e fallback determinístico automático

## Contas de Demonstração (Seed Idempotente)

| Perfil | Login | Senha |
|---|---|---|
| `paciente` | CPF `390.533.447-05` | `123456` |
| `profissional` | Matrícula `2001` a `2007` | `caismed123` |
| `admin` | `admin@caismed.com.br` | `admin123` |

## Como rodar localmente

```powershell
# 1. Ativar ambiente virtual
.\.venv\Scripts\Activate.ps1

# 2. Copiar variáveis de ambiente (opcional — SQLite e fallback de IA funcionam sem .env)
Copy-Item .env.example .env

# 3. Subir a API na porta 3000 (mesma porta padrão do mobile)
uvicorn app.main:app --reload --port 3000
```

- Healthcheck: `http://localhost:3000/health`
- Swagger UI: `http://localhost:3000/docs`
- ReDoc: `http://localhost:3000/redoc`

## Principais Endpoints (`/api`)

- **Autenticação:** `POST /api/auth/register`, `POST /api/auth/login`, `POST /api/auth/logout`, `GET /api/auth/me`, `PUT /api/pacientes/me`
- **Catálogo:** `GET /api/especialidades`, `GET /api/clinicas?q=`, `GET /api/profissionais?especialidade=&clinica=&q=`, `GET /api/profissionais/{id}/horarios?data=AAAA-MM-DD&clinica=`
- **Consultas:** `GET /api/consultas`, `POST /api/consultas`, `PATCH /api/consultas/{id}/cancelar`, `PATCH /api/consultas/{id}/reagendar`, `PATCH /api/consultas/{id}/status`
- **Pré-triagem IA:** `POST /api/triagens`, `GET /api/triagens`, `GET /api/triagens/{id}`
- **Notificações:** `GET /api/notificacoes`, `PATCH /api/notificacoes/ler-todas`
- **Administração (`admin`):** `POST/PUT /api/admin/especialidades`, `POST/PUT /api/admin/clinicas`, `POST/PUT /api/admin/profissionais`, `POST /api/admin/profissionais/{id}/disponibilidades`, `DELETE /api/admin/disponibilidades/{id}`

## Testes Automatizados

```powershell
.\.venv\Scripts\pytest.exe -v
```

## Deploy Público (Render / Railway / Fly.io)

1. Defina `DATABASE_URL` com a string PostgreSQL (aceita `postgres://`, `postgresql://` ou `postgresql+psycopg://`).
2. Configure `JWT_SECRET_KEY`, `CORS_ORIGINS`, `APP_ENV=production` e `GEMINI_API_KEY`.
3. O `Dockerfile` na raiz inicia automaticamente o Uvicorn usando `$PORT`.

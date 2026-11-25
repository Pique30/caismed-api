from collections.abc import Generator

from sqlalchemy import Engine, create_engine, event, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import get_settings


class Base(DeclarativeBase):
    """Classe base para todos os modelos ORM SQLAlchemy 2.0."""


def build_engine(database_url: str) -> Engine:
    """Cria a engine SQLAlchemy configurada para SQLite ou PostgreSQL."""
    is_sqlite = database_url.startswith("sqlite")
    kwargs: dict = {
        "future": True,
        "pool_pre_ping": not is_sqlite,
    }
    if is_sqlite:
        kwargs["connect_args"] = {"check_same_thread": False}
    else:
        kwargs["pool_recycle"] = 1800

    db_engine = create_engine(database_url, **kwargs)

    if is_sqlite:
        @event.listens_for(db_engine, "connect")
        def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return db_engine


settings = get_settings()
engine = build_engine(settings.normalized_database_url)
SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
    class_=Session,
)


def get_db() -> Generator[Session, None, None]:
    """Dependência FastAPI que fornece uma sessão de banco por requisição."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db(target_engine: Engine | None = None) -> None:
    """Garante o registro dos modelos ORM e cria tabelas ainda inexistentes."""
    import app.models  # noqa: F401

    Base.metadata.create_all(bind=target_engine or engine)


def check_database_connection(target_engine: Engine | None = None) -> tuple[bool, str]:
    """Executa uma consulta leve para validar a saúde da conexão com o banco."""
    try:
        with (target_engine or engine).connect() as conn:
            conn.execute(text("SELECT 1"))
        return True, "ok"
    except Exception as exc:  # pragma: no cover - proteção de runtime
        return False, str(exc)

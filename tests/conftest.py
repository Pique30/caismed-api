import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app.core import database
from app.core.database import Base, build_engine
from app.main import create_app


@pytest.fixture()
def test_db_engine(tmp_path, monkeypatch):
    """Cria um banco SQLite isolado por teste, sem sujar o caismed.db local."""
    db_file = tmp_path / "test_caismed.db"
    test_engine = build_engine(f"sqlite:///{db_file.as_posix()}")
    testing_session_local = sessionmaker(
        bind=test_engine,
        autocommit=False,
        autoflush=False,
        expire_on_commit=False,
    )

    monkeypatch.setattr(database, "engine", test_engine)
    monkeypatch.setattr(database, "SessionLocal", testing_session_local)

    import app.models  # noqa: F401

    Base.metadata.create_all(bind=test_engine)
    try:
        yield test_engine, testing_session_local
    finally:
        Base.metadata.drop_all(bind=test_engine)
        test_engine.dispose()


@pytest.fixture()
def client(test_db_engine):
    """Cliente HTTP FastAPI com banco isolado e seed inicial carregado via lifespan."""
    app = create_app()
    with TestClient(app) as test_client:
        yield test_client


def login_headers(client: TestClient, perfil: str, login: str, senha: str) -> dict[str, str]:
    res = client.post(
        "/api/auth/login",
        json={"perfil": perfil, "login": login, "senha": senha},
    )
    assert res.status_code == 200, res.text
    token = res.json()["token"]
    return {"Authorization": f"Bearer {token}"}

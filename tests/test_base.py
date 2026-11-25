from fastapi import Depends
from fastapi.testclient import TestClient

from app.core.exceptions import ApiException
from app.core.security import (
    PerfilEnum,
    TokenPayload,
    create_access_token,
    decode_access_token,
    get_current_token_payload,
    hash_password,
    require_roles,
    revoke_token,
    verify_password,
)
from app.main import create_app
from app.schemas.common import CamelModel


class _SampleSchema(CamelModel):
    usuario_id: str
    nivel_atencao: str


def _build_test_client() -> TestClient:
    app = create_app()

    @app.get("/api/_test/protegida")
    def _protegida(payload: TokenPayload = Depends(get_current_token_payload)):
        return {"id": payload.sub, "perfil": payload.perfil.value}

    @app.get("/api/_test/admin")
    def _admin(payload: TokenPayload = Depends(require_roles(PerfilEnum.ADMIN))):
        return {"id": payload.sub, "perfil": payload.perfil.value}

    @app.post("/api/_test/validacao")
    def _validacao(body: _SampleSchema):
        return body

    @app.get("/api/_test/conflito")
    def _conflito():
        raise ApiException(409, "Esse horário não está mais disponível.", code="HORARIO")

    return TestClient(app)


def test_healthcheck_and_swagger_active(test_db_engine):
    with _build_test_client() as client:
        res = client.get("/health")
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "ok"
        assert data["apiPrefix"] == "/api"
        assert data["database"]["ok"] is True
        assert "fallbackEnabled" in data["ai"]

        assert client.get("/api/health").status_code == 200
        assert client.get("/docs").status_code == 200
        assert client.get("/openapi.json").status_code == 200


def test_error_envelope_and_cors(test_db_engine):
    with _build_test_client() as client:
        res_404 = client.get("/api/rota-inexistente", headers={"Origin": "http://localhost:8081"})
        assert res_404.status_code == 404
        body_404 = res_404.json()
        assert "message" in body_404 and "detail" in body_404
        assert res_404.headers.get("access-control-allow-origin") == "http://localhost:8081"

        res_409 = client.get("/api/_test/conflito")
        assert res_409.status_code == 409
        assert res_409.json()["message"] == "Esse horário não está mais disponível."
        assert res_409.json()["code"] == "HORARIO"

        res_422 = client.post("/api/_test/validacao", json={})
        assert res_422.status_code == 422
        body_422 = res_422.json()
        assert "message" in body_422 and "detail" in body_422 and "errors" in body_422


def test_camel_model_serialization():
    obj = _SampleSchema(usuarioId="u1", nivelAtencao="rotina")
    assert obj.model_dump() == {"usuarioId": "u1", "nivelAtencao": "rotina"}


def test_password_hashing():
    hashed = hash_password("caismed123")
    assert hashed != "caismed123"
    assert verify_password("caismed123", hashed) is True
    assert verify_password("errada", hashed) is False


def test_jwt_rbac_and_revocation(test_db_engine):
    _, testing_session_local = test_db_engine
    token_paciente = create_access_token("p-demo", PerfilEnum.PACIENTE)
    token_admin = create_access_token("adm-1", PerfilEnum.ADMIN)

    with _build_test_client() as client:
        res_no_auth = client.get("/api/_test/protegida")
        assert res_no_auth.status_code == 401
        assert "message" in res_no_auth.json()

        res_ok = client.get(
            "/api/_test/protegida",
            headers={"Authorization": f"Bearer {token_paciente}"},
        )
        assert res_ok.status_code == 200
        assert res_ok.json() == {"id": "p-demo", "perfil": "paciente"}

        res_403 = client.get(
            "/api/_test/admin",
            headers={"Authorization": f"Bearer {token_paciente}"},
        )
        assert res_403.status_code == 403
        assert "message" in res_403.json()

        res_admin = client.get(
            "/api/_test/admin",
            headers={"Authorization": f"Bearer {token_admin}"},
        )
        assert res_admin.status_code == 200

        payload = decode_access_token(token_paciente)
        with testing_session_local() as db:
            revoke_token(db, payload)

        res_revoked = client.get(
            "/api/_test/protegida",
            headers={"Authorization": f"Bearer {token_paciente}"},
        )
        assert res_revoked.status_code == 401

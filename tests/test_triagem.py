from concurrent.futures import TimeoutError as FuturesTimeoutError

from app.core.config import get_settings
from app.services import ia_service
from tests.conftest import login_headers


def test_triagem_pergunta_aberta_sem_perguntas_fixas_recomenda_clinico_geral_e_medicos(client):
    h_pac = login_headers(client, "paciente", "390.533.447-05", "123456")

    # Usuário envia apenas uma pergunta/relato aberto, sem precisar preencher duração ou intensidade
    res = client.post(
        "/api/triagens",
        headers=h_pac,
        json={"descricao": "Quero fazer um check-up geral, não sei qual médico marcar"},
    )
    assert res.status_code == 201, res.text
    data = res.json()
    assert data["duracao"] == "nao_informada"
    assert data["intensidade"] is None

    resultado = data["resultado"]
    assert resultado["resposta"]
    assert "há quanto tempo" not in resultado["resposta"].lower()
    assert "não substitui" in resultado["aviso"].lower()
    assert resultado["nivelAtencao"] == "rotina"

    recs = resultado["recomendacoes"]
    assert len(recs) >= 1
    assert recs[0]["especialidade"] == "clinico_geral"
    # Já traz os clínicos gerais cadastrados no sistema, priorizando foco em prevenção (Dra. Helena)
    medicos = recs[0]["medicos"]
    assert len(medicos) >= 2
    assert medicos[0]["id"] == "m1"
    assert medicos[0]["proximo"] is not None


def test_triagem_contexto_variado_dente_vs_gripe_e_acompanhamento(client):
    h_pac = login_headers(client, "paciente", "390.533.447-05", "123456")

    # 1. Dor de dente -> resposta específica mencionando dentista + Clínico Geral focado em urgências leves (m7)
    res_dente = client.post(
        "/api/triagens",
        headers=h_pac,
        json={"descricao": "Estou com dor no dente desde ontem"},
    )
    assert res_dente.status_code == 201
    dente = res_dente.json()["resultado"]
    assert "dentista" in dente["resposta"].lower()
    assert dente["recomendacoes"][0]["especialidade"] == "clinico_geral"
    assert dente["recomendacoes"][0]["medicos"][0]["id"] == "m7"

    # 2. Dor de cabeça seguida de pergunta "pode ser somente gripe?" -> resposta consciente do contexto
    res_cabeca = client.post(
        "/api/triagens",
        headers=h_pac,
        json={"descricao": "Estou com dor de cabeça"},
    )
    assert res_cabeca.status_code == 201
    cabeca = res_cabeca.json()["resultado"]
    assert cabeca["resposta"] != dente["resposta"]

    res_gripe = client.post(
        "/api/triagens",
        headers=h_pac,
        json={
            "descricao": "Pode ser somente gripe?",
            "historico": [
                {"de": "eu", "texto": "Estou com dor de cabeça"},
                {"de": "bot", "texto": cabeca["resposta"]},
            ],
        },
    )
    assert res_gripe.status_code == 201
    gripe = res_gripe.json()["resultado"]
    assert "pode sim" in gripe["resposta"].lower()
    assert "gripe" in gripe["resposta"].lower()
    assert "não substitui" in gripe["aviso"].lower()
    assert gripe["resposta"] != dente["resposta"]

    # 3. Especialidade específica (ortopedia) não repete clínicos gerais desnecessariamente
    res_orto = client.post(
        "/api/triagens",
        headers=h_pac,
        json={"descricao": "Torci o joelho jogando bola e está doendo"},
    )
    assert res_orto.status_code == 201
    orto = res_orto.json()["resultado"]
    assert len(orto["recomendacoes"]) == 1
    assert orto["recomendacoes"][0]["especialidade"] == "ortopedia"
    assert orto["recomendacoes"][0]["medicos"][0]["id"] == "m5"


def test_triagem_fallback_urgente_com_medicos_e_vinculo_agendamento(client):
    h_pac = login_headers(client, "paciente", "390.533.447-05", "123456")
    h_pro_cardio = login_headers(client, "profissional", "2004", "caismed123")
    h_pro_outro = login_headers(client, "profissional", "2001", "caismed123")

    # 1. Paciente envia relato urgente direto (sem precisar de duração/intensidade explícitas)
    res_t = client.post(
        "/api/triagens",
        headers=h_pac,
        json={
            "descricao": "Estou sentindo dor no peito forte e falta de ar desde hoje",
        },
    )
    assert res_t.status_code == 201, res_t.text
    t_data = res_t.json()
    assert t_data["consultaId"] is None
    assert t_data["duracao"] == "hoje"
    assert t_data["intensidade"] == 7
    assert t_data["resultado"]["nivelAtencao"] == "urgente"
    assert "192" in t_data["resultado"]["orientacao"]
    assert "não substitui" in t_data["resultado"]["aviso"].lower()

    recs = t_data["resultado"]["recomendacoes"]
    assert len(recs) >= 1
    assert recs[0]["especialidade"] == "cardiologia"
    assert len(recs[0]["medicos"]) == 1
    medico = recs[0]["medicos"][0]
    assert medico["id"] == "m4"
    assert medico["proximo"] is not None

    # 2. Fluxo direto: usa o médico já retornado na pré-triagem para agendar vinculado
    ag = client.post(
        "/api/consultas",
        headers=h_pac,
        json={
            "profissionalId": medico["id"],
            "clinicaId": medico["proximo"]["clinicaId"],
            "data": medico["proximo"]["data"],
            "hora": medico["proximo"]["hora"],
            "triagemId": t_data["id"],
        },
    )
    assert ag.status_code == 201, ag.text
    consulta = ag.json()
    assert consulta["triagemId"] == t_data["id"]

    # 3. GET /api/triagens reflete o vínculo com a consulta criada e mantém os médicos
    lista_t = client.get("/api/triagens", headers=h_pac).json()
    encontrada = next(item for item in lista_t if item["id"] == t_data["id"])
    assert encontrada["consultaId"] == consulta["id"]
    assert len(encontrada["resultado"]["recomendacoes"][0]["medicos"]) >= 1

    # 4. Controle de acesso em GET /api/triagens/{id}
    assert client.get(f"/api/triagens/{t_data['id']}", headers=h_pac).status_code == 200
    assert client.get(f"/api/triagens/{t_data['id']}", headers=h_pro_cardio).status_code == 200
    assert client.get(f"/api/triagens/{t_data['id']}", headers=h_pro_outro).status_code == 403


def test_triagem_gemini_mockado_e_guardrail_clinico(client, monkeypatch):
    h_pac = login_headers(client, "paciente", "390.533.447-05", "123456")

    settings = get_settings()
    monkeypatch.setattr(settings, "gemini_api_key", "fake-key-for-test")

    def _fake_gemini(*_args, **_kwargs):
        return ia_service._GeminiTriagemPayload(
            resposta="Dor no peito com desmaio precisa de avaliação médica imediata. Separei também a especialidade de Cardiologia abaixo.",
            recomendacoes=[
                ia_service._GeminiRecomendacao(
                    especialidade="cardiologia",
                    prioridade=1,
                    motivo="Sintoma torácico requer avaliação cardiológica dedicada.",
                )
            ],
            # Mesmo se o LLM subestimar como "rotina", o guardrail deve elevar para "urgente"
            nivel_atencao="rotina",
            orientacao="Procure avaliação médica.",
        )

    monkeypatch.setattr(ia_service, "_chamar_gemini_sync", _fake_gemini)

    res = client.post(
        "/api/triagens",
        headers=h_pac,
        json={
            "descricao": "Dor forte no peito com desmaio",
            "intensidade": 9,
        },
    )
    assert res.status_code == 201
    data = res.json()
    assert data["provedorIa"].startswith("gemini:")
    assert data["resultado"]["resposta"].startswith("Dor no peito")
    assert data["resultado"]["nivelAtencao"] == "urgente"
    assert "192" in data["resultado"]["orientacao"]
    assert len(data["resultado"]["recomendacoes"][0]["medicos"]) == 1


def test_triagem_fallback_em_timeout_do_gemini(client, monkeypatch):
    h_pac = login_headers(client, "paciente", "390.533.447-05", "123456")

    settings = get_settings()
    monkeypatch.setattr(settings, "gemini_api_key", "fake-key-for-test")

    def _raise_timeout(*_args, **_kwargs):
        raise FuturesTimeoutError()

    monkeypatch.setattr(ia_service, "_chamar_gemini_sync", _raise_timeout)

    res = client.post(
        "/api/triagens",
        headers=h_pac,
        json={
            "descricao": "Mancha com coceira na pele do braço há 3 dias",
        },
    )
    assert res.status_code == 201
    data = res.json()
    assert data["duracao"] == "dias"
    assert data["provedorIa"] in ("fallback_error", "fallback_timeout")
    assert data["resultado"]["recomendacoes"][0]["especialidade"] == "dermatologia"
    assert data["resultado"]["recomendacoes"][0]["medicos"][0]["id"] == "m3"
    assert data["resultado"]["nivelAtencao"] == "rotina"

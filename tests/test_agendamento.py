from datetime import timedelta

from app.core import database
from app.core.utils import now_app_tz
from app.models.consulta import Consulta
from app.seed import seed_database
from tests.conftest import login_headers


def test_seed_idempotency(client):
    with database.SessionLocal() as db:
        seed_database(db)
        seed_database(db)
    esps = client.get("/api/especialidades").json()
    clinicas = client.get("/api/clinicas").json()
    assert len(esps) == 6
    assert len(clinicas) == 3


def test_catalog_and_full_appointment_lifecycle(client):
    h_pac = login_headers(client, "paciente", "390.533.447-05", "123456")
    h_pro = login_headers(client, "profissional", "2004", "caismed123")  # Dr. Bruno (cardiologia)

    # Catálogo público
    assert len(client.get("/api/especialidades").json()) == 6
    olinda = client.get("/api/clinicas?q=Olinda").json()
    assert len(olinda) == 1
    assert olinda[0]["id"] == "u1"

    # Profissionais filtrados por especialidade
    profs = client.get("/api/profissionais?especialidade=cardiologia", headers=h_pac).json()
    assert len(profs) == 1
    cardio = profs[0]
    assert cardio["id"] == "m4"
    assert isinstance(cardio["nota"], float)
    assert cardio["proximo"] is not None

    # Busca uma data futura com >48h de antecedência para testar reagendamento e cancelamento
    data_slot = None
    slots_livres = []
    hoje = now_app_tz().date()
    for offset in range(3, 21):
        cand = (hoje + timedelta(days=offset)).isoformat()
        res_h = client.get(f"/api/profissionais/m4/horarios?data={cand}&clinica=u2", headers=h_pac)
        assert res_h.status_code == 200
        livres = [s for s in res_h.json() if s["disponivel"]]
        if len(livres) >= 2:
            data_slot = cand
            slots_livres = livres
            break

    assert data_slot is not None
    hora1 = slots_livres[0]["hora"]
    hora2 = slots_livres[1]["hora"]
    assert isinstance(slots_livres[0]["clinicaId"], str)

    # Criar agendamento
    criada = client.post(
        "/api/consultas",
        headers=h_pac,
        json={"profissionalId": "m4", "clinicaId": "u2", "data": data_slot, "hora": hora1},
    )
    assert criada.status_code == 201, criada.text
    c_data = criada.json()
    assert c_data["status"] == "agendada"
    assert c_data["especialidade"] == "cardiologia"
    assert c_data["especialidadeNome"] == "Cardiologia"
    assert c_data["profissional"]["id"] == "m4"
    assert c_data["clinica"]["id"] == "u2"
    consulta_id = c_data["id"]

    # Double-booking -> 409 HORARIO
    conflito = client.post(
        "/api/consultas",
        headers=h_pac,
        json={"profissionalId": "m4", "clinicaId": "u2", "data": data_slot, "hora": hora1},
    )
    assert conflito.status_code == 409
    assert conflito.json()["code"] == "HORARIO"

    # Reagendar para hora2
    reag = client.patch(
        f"/api/consultas/{consulta_id}/reagendar",
        headers=h_pac,
        json={"data": data_slot, "hora": hora2, "clinicaId": "u2"},
    )
    assert reag.status_code == 200
    assert reag.json()["hora"] == hora2

    # Profissional vê a consulta na própria agenda e atualiza status
    agenda_pro = client.get("/api/consultas", headers=h_pro).json()
    assert any(c["id"] == consulta_id for c in agenda_pro)

    # Cancelar consulta (> 24h)
    canc = client.patch(
        f"/api/consultas/{consulta_id}/cancelar",
        headers=h_pac,
        json={"motivo": "Imprevisto pessoal"},
    )
    assert canc.status_code == 200
    assert canc.json()["status"] == "cancelada"
    assert canc.json()["motivo"] == "Imprevisto pessoal"

    # Horário hora2 volta a ficar disponível após cancelamento
    slots_apos = client.get(
        f"/api/profissionais/m4/horarios?data={data_slot}&clinica=u2",
        headers=h_pac,
    ).json()
    slot_hora2 = next(s for s in slots_apos if s["hora"] == hora2)
    assert slot_hora2["disponivel"] is True

    # Profissional consegue marcar status em consulta ativa
    nova = client.post(
        "/api/consultas",
        headers=h_pac,
        json={"profissionalId": "m4", "clinicaId": "u2", "data": data_slot, "hora": hora2},
    ).json()
    st = client.patch(
        f"/api/consultas/{nova['id']}/status",
        headers=h_pro,
        json={"status": "concluida"},
    )
    assert st.status_code == 200
    assert st.json()["status"] == "concluida"

    # Notificações e marcar todas como lidas
    notifs = client.get("/api/notificacoes", headers=h_pac).json()
    assert any(not n["lida"] for n in notifs)
    ler = client.patch("/api/notificacoes/ler-todas", headers=h_pac)
    assert ler.status_code == 200 and ler.json() == {"ok": True}
    notifs_apos = client.get("/api/notificacoes", headers=h_pac).json()
    assert all(n["lida"] for n in notifs_apos)


def test_24h_rule_and_auto_reminder(client):
    h_pac = login_headers(client, "paciente", "390.533.447-05", "123456")

    # Insere consulta daqui a 4 horas (dentro da janela de 24h)
    em_4h = now_app_tz() + timedelta(hours=4)
    with database.SessionLocal() as db:
        c = Consulta(
            id="c-proxima-4h",
            paciente_id="p-demo",
            profissional_id="m1",
            clinica_id="u1",
            especialidade_id="clinico_geral",
            data=em_4h.date(),
            hora=em_4h.strftime("%H:%M"),
            status="agendada",
            valor=180.0,
            lembrete_enviado=False,
        )
        db.add(c)
        db.commit()

    # Cancelamento com menos de 24h -> 400
    res_canc = client.patch(
        "/api/consultas/c-proxima-4h/cancelar",
        headers=h_pac,
        json={"motivo": "Teste 24h"},
    )
    assert res_canc.status_code == 400
    assert "24 horas" in res_canc.json()["message"]

    # Central de notificações gera lembrete automático de 24h
    notifs = client.get("/api/notificacoes", headers=h_pac).json()
    assert any(n["titulo"] == "Lembrete de consulta" for n in notifs)


def test_admin_crud(client):
    h_adm = login_headers(client, "admin", "admin@caismed.com.br", "admin123")

    esp = client.post(
        "/api/admin/especialidades",
        headers=h_adm,
        json={"id": "oftalmologia", "nome": "Oftalmologia", "descricao": "Saúde ocular", "valor": 220},
    )
    assert esp.status_code == 201

    cli = client.post(
        "/api/admin/clinicas",
        headers=h_adm,
        json={
            "id": "u4",
            "nome": "CaisMed Jaboatão",
            "bairro": "Piedade",
            "cidade": "Jaboatão",
            "endereco": "Av. Bernardo Vieira de Melo, 500",
            "telefone": "(81) 3000-1004",
            "horario": "Seg a Sex, 8h às 18h",
        },
    )
    assert cli.status_code == 201

    pro = client.post(
        "/api/admin/profissionais",
        headers=h_adm,
        json={
            "id": "m8",
            "nome": "Dr. Lucas Ferreira",
            "matricula": "2008",
            "senha": "caismed123",
            "crm": "CRM-PE 89012",
            "especialidades": ["oftalmologia"],
            "nota": 4.9,
            "bio": "Oftalmologista.",
        },
    )
    assert pro.status_code == 201

    disp = client.post(
        "/api/admin/profissionais/m8/disponibilidades",
        headers=h_adm,
        json={
            "clinicaId": "u4",
            "diaSemana": 2,
            "horaInicio": "09:00",
            "horaFim": "11:00",
            "duracaoMinutos": 30,
        },
    )
    assert disp.status_code == 201
    assert disp.json()["profissionalId"] == "m8"

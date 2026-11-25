from tests.conftest import login_headers


def test_register_login_me_update_and_logout(client):
    # Cadastro de novo paciente (CPF válido: 52998224725)
    reg = client.post(
        "/api/auth/register",
        json={
            "nome": "João da Silva",
            "cpf": "529.982.247-25",
            "nascimento": "1985-06-15",
            "telefone": "(81) 98888-7777",
            "email": "joao.silva@exemplo.com",
            "senha": "senha123",
            "aceiteLGPD": True,
        },
    )
    assert reg.status_code == 201, reg.text
    reg_data = reg.json()
    assert reg_data["token"]
    assert reg_data["usuario"]["perfil"] == "paciente"
    assert isinstance(reg_data["usuario"]["id"], str)

    headers = {"Authorization": f"Bearer {reg_data['token']}"}

    # CPF duplicado -> 409 com message
    dup = client.post(
        "/api/auth/register",
        json={
            "nome": "Outro João",
            "cpf": "52998224725",
            "nascimento": "1985-06-15",
            "telefone": "(81) 98888-0000",
            "email": "outro@exemplo.com",
            "senha": "senha123",
            "aceiteLGPD": True,
        },
    )
    assert dup.status_code == 409
    assert "CPF" in dup.json()["message"]

    # GET /api/auth/me
    me = client.get("/api/auth/me", headers=headers)
    assert me.status_code == 200
    me_data = me.json()
    assert me_data["cpf"] == "52998224725"
    assert me_data["perfil"] == "paciente"
    assert me_data["nascimento"] == "1985-06-15"

    # Notificação de boas-vindas criada no cadastro
    notifs = client.get("/api/notificacoes", headers=headers)
    assert notifs.status_code == 200
    assert len(notifs.json()) >= 1

    # PUT /api/pacientes/me (inclusive troca de senha)
    upd = client.put(
        "/api/pacientes/me",
        headers=headers,
        json={
            "nome": "João Silva Atualizado",
            "telefone": "(81) 97777-6666",
            "email": "joao.novo@exemplo.com",
            "nascimento": "1985-06-15",
            "senha": "novaSenha123",
        },
    )
    assert upd.status_code == 200
    assert upd.json()["nome"] == "João Silva Atualizado"
    assert upd.json()["email"] == "joao.novo@exemplo.com"

    # Logout revoga o token atual
    out = client.post("/api/auth/logout", headers=headers)
    assert out.status_code == 200
    assert out.json()["ok"] is True

    me_after = client.get("/api/auth/me", headers=headers)
    assert me_after.status_code == 401

    # Novo login funciona com CPF com máscara e nova senha
    relogin = client.post(
        "/api/auth/login",
        json={"perfil": "paciente", "login": "529.982.247-25", "senha": "novaSenha123"},
    )
    assert relogin.status_code == 200


def test_login_all_profiles_and_rbac(client):
    # Paciente demo
    h_pac = login_headers(client, "paciente", "390.533.447-05", "123456")
    # Profissional demo
    h_pro = login_headers(client, "profissional", "2001", "caismed123")
    # Admin demo
    h_adm = login_headers(client, "admin", "admin@caismed.com.br", "admin123")

    me_pro = client.get("/api/auth/me", headers=h_pro)
    assert me_pro.status_code == 200
    assert me_pro.json()["matricula"] == "2001"
    assert me_pro.json()["crm"] == "CRM-PE 12345"
    assert "clinico_geral" in me_pro.json()["especialidades"]

    me_adm = client.get("/api/auth/me", headers=h_adm)
    assert me_adm.status_code == 200
    assert me_adm.json()["perfil"] == "admin"

    # RBAC: paciente não pode chamar rota admin
    res_403_adm = client.post(
        "/api/admin/especialidades",
        headers=h_pac,
        json={"id": "neurologia", "nome": "Neurologia", "descricao": "Sistema nervoso", "valor": 300},
    )
    assert res_403_adm.status_code == 403

    # RBAC: profissional não pode criar triagem de paciente
    res_403_tri = client.post(
        "/api/triagens",
        headers=h_pro,
        json={"descricao": "Dor de cabeça", "duracao": "hoje", "intensidade": 4, "detalhes": ""},
    )
    assert res_403_tri.status_code == 403

    # Credenciais inválidas -> 401 com message
    bad = client.post(
        "/api/auth/login",
        json={"perfil": "profissional", "login": "2001", "senha": "errada"},
    )
    assert bad.status_code == 401
    assert "message" in bad.json()

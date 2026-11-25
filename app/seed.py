from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import PerfilEnum, hash_password
from app.models.catalogo import Clinica, Disponibilidade, Especialidade
from app.models.consulta import Consulta
from app.models.notificacao import Notificacao
from app.models.usuario import Paciente, Profissional, Usuario

ESPECIALIDADES_SEED = [
    {
        "id": "clinico_geral",
        "nome": "Clínico Geral",
        "descricao": "Avaliação geral e porta de entrada para outras especialidades",
        "valor": 180.0,
    },
    {
        "id": "pediatria",
        "nome": "Pediatria",
        "descricao": "Saúde de bebês, crianças e adolescentes",
        "valor": 200.0,
    },
    {
        "id": "cardiologia",
        "nome": "Cardiologia",
        "descricao": "Coração, pressão arterial e circulação",
        "valor": 260.0,
    },
    {
        "id": "dermatologia",
        "nome": "Dermatologia",
        "descricao": "Pele, cabelos e unhas",
        "valor": 240.0,
    },
    {
        "id": "ortopedia",
        "nome": "Ortopedia",
        "descricao": "Ossos, articulações, coluna e músculos",
        "valor": 250.0,
    },
    {
        "id": "ginecologia",
        "nome": "Ginecologia",
        "descricao": "Saúde da mulher e gestação",
        "valor": 230.0,
    },
]

CLINICAS_SEED = [
    {
        "id": "u1",
        "nome": "CaisMed Olinda",
        "bairro": "Casa Caiada",
        "cidade": "Olinda",
        "endereco": "Av. Presidente Kennedy, 1200",
        "telefone": "(81) 3000-1001",
        "horario": "Seg a Sex, 7h às 19h. Sáb, 8h às 12h",
    },
    {
        "id": "u2",
        "nome": "CaisMed Recife",
        "bairro": "Boa Viagem",
        "cidade": "Recife",
        "endereco": "Av. Domingos Ferreira, 850",
        "telefone": "(81) 3000-1002",
        "horario": "Seg a Sex, 7h às 20h. Sáb, 8h às 13h",
    },
    {
        "id": "u3",
        "nome": "CaisMed Paulista",
        "bairro": "Centro",
        "cidade": "Paulista",
        "endereco": "Av. Duque de Caxias, 430",
        "telefone": "(81) 3000-1003",
        "horario": "Seg a Sex, 7h às 18h",
    },
]

PROFISSIONAIS_SEED = [
    {
        "id": "m1",
        "nome": "Dra. Helena Cavalcanti",
        "email": "helena.cavalcanti@caismed.com.br",
        "matricula": "2001",
        "crm": "CRM-PE 12345",
        "especialidades": ["clinico_geral"],
        "nota": 4.9,
        "bio": "Clínica geral com foco em prevenção e doenças crônicas.",
        "disp": [
            ("u1", [1, 3, 5], "08:00", "12:00", 30),
            ("u2", [2, 4], "13:00", "17:00", 30),
        ],
    },
    {
        "id": "m2",
        "nome": "Dr. Rafael Albuquerque",
        "email": "rafael.albuquerque@caismed.com.br",
        "matricula": "2002",
        "crm": "CRM-PE 23456",
        "especialidades": ["pediatria"],
        "nota": 4.8,
        "bio": "Pediatra, atende de recém-nascidos a adolescentes.",
        "disp": [
            ("u1", [1, 2, 3, 4], "08:00", "12:00", 30),
            ("u3", [5], "08:00", "12:00", 30),
        ],
    },
    {
        "id": "m3",
        "nome": "Dra. Camila Torres",
        "email": "camila.torres@caismed.com.br",
        "matricula": "2003",
        "crm": "CRM-PE 34567",
        "especialidades": ["dermatologia"],
        "nota": 4.7,
        "bio": "Dermatologista clínica e estética.",
        "disp": [
            ("u1", [2, 4], "13:00", "17:00", 30),
        ],
    },
    {
        "id": "m4",
        "nome": "Dr. Bruno Teixeira",
        "email": "bruno.teixeira@caismed.com.br",
        "matricula": "2004",
        "crm": "CRM-PE 45678",
        "especialidades": ["cardiologia"],
        "nota": 4.9,
        "bio": "Cardiologista, check-up e risco cardiovascular.",
        "disp": [
            ("u2", [1, 2, 3], "08:00", "12:00", 30),
        ],
    },
    {
        "id": "m5",
        "nome": "Dr. André Lacerda",
        "email": "andre.lacerda@caismed.com.br",
        "matricula": "2005",
        "crm": "CRM-PE 56789",
        "especialidades": ["ortopedia"],
        "nota": 4.6,
        "bio": "Ortopedista, lesões esportivas e coluna.",
        "disp": [
            ("u2", [4, 5], "08:00", "12:00", 30),
        ],
    },
    {
        "id": "m6",
        "nome": "Dra. Luíza Barros",
        "email": "luiza.barros@caismed.com.br",
        "matricula": "2006",
        "crm": "CRM-PE 67890",
        "especialidades": ["ginecologia"],
        "nota": 4.8,
        "bio": "Ginecologista e obstetra.",
        "disp": [
            ("u3", [1, 3], "13:00", "17:00", 30),
        ],
    },
    {
        "id": "m7",
        "nome": "Dr. Tiago Menezes",
        "email": "tiago.menezes@caismed.com.br",
        "matricula": "2007",
        "crm": "CRM-PE 78901",
        "especialidades": ["clinico_geral"],
        "nota": 4.5,
        "bio": "Clínico geral, rotina e urgências leves.",
        "disp": [
            ("u3", [1, 2, 3, 4, 5], "08:00", "12:00", 30),
        ],
    },
]


def _js_weekday(d: date) -> int:
    """Converte date.weekday() (0=Seg..6=Dom) para o padrão JS (0=Dom..6=Sáb)."""
    return (d.weekday() + 1) % 7


def _proximo_dia(dias_js: list[int], a_partir_de: date) -> date:
    for offset in range(21):
        cand = a_partir_de + timedelta(days=offset)
        if _js_weekday(cand) in dias_js:
            return cand
    return a_partir_de


def seed_database(db: Session) -> None:
    """Popula dados iniciais de forma idempotente (seguro para executar em todo startup)."""
    settings = get_settings()
    hoje = datetime.now(settings.tz).date()

    # 1. Especialidades
    esps_map: dict[str, Especialidade] = {}
    for item in ESPECIALIDADES_SEED:
        esp = db.get(Especialidade, item["id"])
        if esp is None:
            esp = Especialidade(**item)
            db.add(esp)
        esps_map[item["id"]] = esp

    # 2. Clínicas
    for item in CLINICAS_SEED:
        if db.get(Clinica, item["id"]) is None:
            db.add(Clinica(**item))

    db.flush()

    # 3. Profissionais + disponibilidades
    senha_pro_hash = hash_password("caismed123")
    for p in PROFISSIONAIS_SEED:
        user = db.get(Usuario, p["id"])
        if user is None:
            user = Usuario(
                id=p["id"],
                perfil=PerfilEnum.PROFISSIONAL.value,
                nome=p["nome"],
                email=p["email"],
                senha_hash=senha_pro_hash,
            )
            prof = Profissional(
                usuario_id=p["id"],
                matricula=p["matricula"],
                crm=p["crm"],
                nota=p["nota"],
                bio=p["bio"],
                especialidades=[esps_map[eid] for eid in p["especialidades"]],
            )
            db.add(user)
            db.add(prof)
            db.flush()

            for clinica_id, dias, inicio, fim, duracao in p["disp"]:
                for dia in dias:
                    db.add(
                        Disponibilidade(
                            profissional_id=p["id"],
                            clinica_id=clinica_id,
                            dia_semana=dia,
                            hora_inicio=inicio,
                            hora_fim=fim,
                            duracao_minutos=duracao,
                        )
                    )

    # 4. Administrador padrão
    if db.get(Usuario, "adm-demo") is None:
        db.add(
            Usuario(
                id="adm-demo",
                perfil=PerfilEnum.ADMIN.value,
                nome="Administrador CaisMed",
                email="admin@caismed.com.br",
                senha_hash=hash_password("admin123"),
            )
        )

    # 5. Paciente de demonstração (compatível com o README do app mobile)
    paciente_demo_criado = False
    if db.get(Usuario, "p-demo") is None:
        paciente_demo_criado = True
        db.add(
            Usuario(
                id="p-demo",
                perfil=PerfilEnum.PACIENTE.value,
                nome="Maria Oliveira",
                email="maria@exemplo.com",
                senha_hash=hash_password("123456"),
            )
        )
        db.add(
            Paciente(
                usuario_id="p-demo",
                cpf="39053344705",
                nascimento=date(1958, 4, 12),
                telefone="(81) 99999-0000",
                aceite_lgpd=True,
                aceite_lgpd_em=datetime.now(timezone.utc),
            )
        )
        db.flush()

    # 6. Consultas e notificação semente apenas se o paciente demo acabou de ser criado
    if paciente_demo_criado:
        tem_consultas = db.execute(
            select(Consulta.id).where(Consulta.paciente_id == "p-demo").limit(1)
        ).first()
        if not tem_consultas:
            db.add(
                Consulta(
                    id="c-demo-futura",
                    paciente_id="p-demo",
                    profissional_id="m1",
                    clinica_id="u1",
                    especialidade_id="clinico_geral",
                    data=_proximo_dia([1, 3, 5], hoje + timedelta(days=2)),
                    hora="09:00",
                    status="agendada",
                    valor=180.0,
                )
            )
            db.add(
                Consulta(
                    id="c-demo-passada",
                    paciente_id="p-demo",
                    profissional_id="m4",
                    clinica_id="u2",
                    especialidade_id="cardiologia",
                    data=hoje - timedelta(days=12),
                    hora="08:30",
                    status="concluida",
                    valor=260.0,
                )
            )
            db.add(
                Notificacao(
                    id="n-demo-boas-vindas",
                    usuario_id="p-demo",
                    titulo="Bem-vinda à CaisMed",
                    texto="Sua conta está pronta. Agende consultas e converse com a pré-triagem.",
                    lida=False,
                )
            )

    db.commit()

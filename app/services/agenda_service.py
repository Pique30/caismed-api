from datetime import date, timedelta

from fastapi import status
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.core.exceptions import ApiException
from app.core.utils import (
    js_weekday,
    minutes_to_hhmm,
    now_app_tz,
    parse_hhmm,
    parse_iso_date,
    sem_acento,
    today_app_tz,
)
from app.models.catalogo import Clinica, Disponibilidade, Especialidade
from app.models.consulta import Consulta
from app.models.usuario import Profissional, Usuario
from app.schemas.catalogo import (
    ClinicaOut,
    EspecialidadeOut,
    HorarioSlotOut,
    ProfissionalOut,
    ProximoHorarioOut,
)


def listar_especialidades(db: Session) -> list[EspecialidadeOut]:
    esps = db.scalars(
        select(Especialidade)
        .where(Especialidade.ativa.is_(True))
        .order_by(Especialidade.nome.asc())
    ).all()
    return [
        EspecialidadeOut(id=e.id, nome=e.nome, descricao=e.descricao, valor=float(e.valor))
        for e in esps
    ]


def listar_clinicas(db: Session, q: str = "") -> list[ClinicaOut]:
    clinicas = db.scalars(
        select(Clinica).where(Clinica.ativa.is_(True)).order_by(Clinica.nome.asc())
    ).all()
    termo = sem_acento(q.strip())
    filtradas = [
        c
        for c in clinicas
        if not termo or termo in sem_acento(f"{c.nome} {c.bairro} {c.cidade} {c.endereco}")
    ]
    return [
        ClinicaOut(
            id=c.id,
            nome=c.nome,
            bairro=c.bairro,
            cidade=c.cidade,
            endereco=c.endereco,
            telefone=c.telefone,
            horario=c.horario,
        )
        for c in filtradas
    ]


def calcular_slots_do_dia(
    prof: Profissional,
    data_alvo: date,
    ocupados: set[str],
    *,
    clinica_id: str | None = None,
) -> list[HorarioSlotOut]:
    dow = js_weekday(data_alvo)
    slots_base: dict[str, str] = {}

    for bloco in prof.disponibilidades:
        if bloco.dia_semana != dow:
            continue
        if clinica_id and bloco.clinica_id != clinica_id:
            continue
        inicio = parse_hhmm(bloco.hora_inicio)
        fim = parse_hhmm(bloco.hora_fim)
        passo = max(10, bloco.duracao_minutos)
        t = inicio
        while t + passo <= fim:
            slots_base[minutes_to_hhmm(t)] = bloco.clinica_id
            t += passo

    agora = now_app_tz()
    hoje = agora.date()
    if data_alvo < hoje:
        limite_passado = 10**6
    elif data_alvo == hoje:
        limite_passado = agora.hour * 60 + agora.minute
    else:
        limite_passado = -1

    resultado: list[HorarioSlotOut] = []
    for hora in sorted(slots_base.keys()):
        cid = slots_base[hora]
        disponivel = (hora not in ocupados) and (parse_hhmm(hora) > limite_passado)
        resultado.append(HorarioSlotOut(hora=hora, clinica_id=cid, disponivel=disponivel))
    return resultado


def obter_horarios_profissional(
    db: Session,
    profissional_id: str,
    data_str: str | None = None,
    clinica_id: str | None = None,
) -> list[HorarioSlotOut]:
    prof = db.scalar(
        select(Profissional)
        .options(joinedload(Profissional.disponibilidades), joinedload(Profissional.usuario))
        .where(Profissional.usuario_id == profissional_id)
    )
    if prof is None or not prof.usuario.ativo:
        raise ApiException(status.HTTP_404_NOT_FOUND, "Profissional não encontrado.")

    data_alvo = parse_iso_date(data_str) if data_str else today_app_tz()
    ocupados = set(
        db.scalars(
            select(Consulta.hora).where(
                Consulta.profissional_id == profissional_id,
                Consulta.data == data_alvo,
                Consulta.status != "cancelada",
            )
        ).all()
    )
    return calcular_slots_do_dia(prof, data_alvo, ocupados, clinica_id=clinica_id or None)


def _encontrar_proximo_slot(
    prof: Profissional,
    ocupados_por_data: dict[date, set[str]],
    *,
    clinica_id: str | None = None,
    dias_horizonte: int = 30,
) -> ProximoHorarioOut | None:
    hoje = today_app_tz()
    for offset in range(dias_horizonte):
        d = hoje + timedelta(days=offset)
        slots = calcular_slots_do_dia(
            prof, d, ocupados_por_data.get(d, set()), clinica_id=clinica_id or None
        )
        livre = next((s for s in slots if s.disponivel), None)
        if livre:
            return ProximoHorarioOut(
                data=d.isoformat(),
                hora=livre.hora,
                clinica_id=livre.clinica_id,
            )
    return None


def listar_profissionais(
    db: Session,
    *,
    especialidade: str | None = None,
    clinica: str | None = None,
    q: str = "",
) -> list[ProfissionalOut]:
    profs = (
        db.scalars(
            select(Profissional)
            .join(Profissional.usuario)
            .options(
                joinedload(Profissional.usuario),
                joinedload(Profissional.especialidades),
                joinedload(Profissional.disponibilidades),
            )
            .where(Usuario.ativo.is_(True))
            .order_by(Usuario.nome.asc())
        )
        .unique()
        .all()
    )

    hoje = today_app_tz()
    limite = hoje + timedelta(days=30)
    consultas_ativas = db.execute(
        select(Consulta.profissional_id, Consulta.data, Consulta.hora).where(
            Consulta.data >= hoje,
            Consulta.data <= limite,
            Consulta.status != "cancelada",
        )
    ).all()

    ocupados_mapa: dict[str, dict[date, set[str]]] = {}
    for pid, dt, hora in consultas_ativas:
        ocupados_mapa.setdefault(pid, {}).setdefault(dt, set()).add(hora)

    termo = sem_acento(q.strip())
    resultado: list[ProfissionalOut] = []

    for prof in profs:
        esp_ids = [e.id for e in prof.especialidades]
        clinica_ids = sorted({d.clinica_id for d in prof.disponibilidades})

        if especialidade and especialidade not in esp_ids:
            continue
        if clinica and clinica not in clinica_ids:
            continue
        if termo:
            nomes_esp = " ".join(e.nome for e in prof.especialidades)
            if termo not in sem_acento(f"{prof.usuario.nome} {prof.crm} {nomes_esp}"):
                continue

        proximo = _encontrar_proximo_slot(
            prof,
            ocupados_mapa.get(prof.usuario_id, {}),
            clinica_id=clinica or None,
        )
        resultado.append(
            ProfissionalOut(
                id=prof.usuario_id,
                nome=prof.usuario.nome,
                crm=prof.crm,
                especialidades=esp_ids,
                nota=float(prof.nota),
                bio=prof.bio,
                clinicas=clinica_ids,
                proximo=proximo,
            )
        )
    return resultado

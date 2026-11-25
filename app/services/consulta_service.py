from datetime import datetime, timezone

from fastapi import status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app.core.exceptions import ApiException
from app.core.security import PerfilEnum, TokenPayload
from app.core.utils import format_date_br, hours_until, parse_hhmm, parse_iso_date
from app.models.catalogo import Clinica, Especialidade
from app.models.consulta import Consulta
from app.models.triagem import Triagem
from app.models.usuario import Paciente, Profissional
from app.schemas.catalogo import ClinicaOut
from app.schemas.consulta import (
    ConsultaCancelarIn,
    ConsultaCreateIn,
    ConsultaOut,
    ConsultaReagendarIn,
    ConsultaStatusIn,
    PacienteResumoOut,
    ProfissionalResumoOut,
)
from app.services.agenda_service import calcular_slots_do_dia
from app.services.notificacao_service import criar_notificacao


def _carregar_consulta(db: Session, consulta_id: str) -> Consulta | None:
    return db.scalar(
        select(Consulta)
        .options(
            joinedload(Consulta.profissional).joinedload(Profissional.usuario),
            joinedload(Consulta.paciente).joinedload(Paciente.usuario),
            joinedload(Consulta.clinica),
            joinedload(Consulta.especialidade),
        )
        .where(Consulta.id == consulta_id)
    )


def serializar_consulta(c: Consulta) -> ConsultaOut:
    prof_out = (
        ProfissionalResumoOut(
            id=c.profissional.usuario_id,
            nome=c.profissional.usuario.nome,
            crm=c.profissional.crm,
        )
        if c.profissional and c.profissional.usuario
        else None
    )
    pac_out = (
        PacienteResumoOut(
            id=c.paciente.usuario_id,
            nome=c.paciente.usuario.nome,
        )
        if c.paciente and c.paciente.usuario
        else None
    )
    clinica_out = (
        ClinicaOut(
            id=c.clinica.id,
            nome=c.clinica.nome,
            bairro=c.clinica.bairro,
            cidade=c.clinica.cidade,
            endereco=c.clinica.endereco,
            telefone=c.clinica.telefone,
            horario=c.clinica.horario,
        )
        if c.clinica
        else None
    )
    return ConsultaOut(
        id=c.id,
        paciente_id=c.paciente_id,
        profissional_id=c.profissional_id,
        clinica_id=c.clinica_id,
        especialidade=c.especialidade_id,
        especialidade_nome=c.especialidade.nome if c.especialidade else c.especialidade_id,
        data=c.data.isoformat(),
        hora=c.hora,
        status=c.status,
        valor=float(c.valor),
        triagem_id=c.triagem_id,
        motivo=c.motivo_cancelamento,
        criado_em=c.criado_em.isoformat(),
        cancelada_em=c.cancelada_em.isoformat() if c.cancelada_em else None,
        profissional=prof_out,
        clinica=clinica_out,
        paciente=pac_out,
    )


def listar_consultas(
    db: Session,
    payload: TokenPayload,
    *,
    status_filtro: str | None = None,
) -> list[ConsultaOut]:
    stmt = (
        select(Consulta)
        .options(
            joinedload(Consulta.profissional).joinedload(Profissional.usuario),
            joinedload(Consulta.paciente).joinedload(Paciente.usuario),
            joinedload(Consulta.clinica),
            joinedload(Consulta.especialidade),
        )
        .order_by(Consulta.data.asc(), Consulta.hora.asc())
    )
    if payload.perfil == PerfilEnum.PACIENTE:
        stmt = stmt.where(Consulta.paciente_id == payload.sub)
    elif payload.perfil == PerfilEnum.PROFISSIONAL:
        stmt = stmt.where(Consulta.profissional_id == payload.sub)

    if status_filtro:
        stmt = stmt.where(Consulta.status == status_filtro)

    itens = db.scalars(stmt).all()
    return [serializar_consulta(c) for c in itens]


def criar_consulta(db: Session, payload: TokenPayload, body: ConsultaCreateIn) -> ConsultaOut:
    data_alvo = parse_iso_date(body.data)
    parse_hhmm(body.hora)

    prof = db.scalar(
        select(Profissional)
        .options(
            joinedload(Profissional.usuario),
            joinedload(Profissional.especialidades),
            joinedload(Profissional.disponibilidades),
        )
        .where(Profissional.usuario_id == body.profissional_id)
    )
    if prof is None or not prof.usuario.ativo:
        raise ApiException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "Escolha um profissional válido, o dia e o horário.",
        )

    paciente = db.scalar(
        select(Paciente)
        .options(joinedload(Paciente.usuario))
        .where(Paciente.usuario_id == payload.sub)
    )
    if paciente is None:
        raise ApiException(status.HTTP_404_NOT_FOUND, "Paciente não encontrado.")

    ocupados = set(
        db.scalars(
            select(Consulta.hora).where(
                Consulta.profissional_id == prof.usuario_id,
                Consulta.data == data_alvo,
                Consulta.status != "cancelada",
            )
        ).all()
    )
    slots = calcular_slots_do_dia(
        prof, data_alvo, ocupados, clinica_id=body.clinica_id or None
    )
    slot = next((s for s in slots if s.hora == body.hora), None)
    if slot is None or not slot.disponivel:
        raise ApiException(
            status.HTTP_409_CONFLICT,
            "Esse horário não está mais disponível. Escolha outro.",
            code="HORARIO",
        )

    # Resolve especialidade (enviada ou principal do profissional)
    esp: Especialidade | None = None
    if body.especialidade:
        esp = next((e for e in prof.especialidades if e.id == body.especialidade), None)
        if esp is None:
            raise ApiException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                "Este profissional não atende a especialidade selecionada.",
            )
    elif prof.especialidades:
        esp = prof.especialidades[0]

    if esp is None:
        raise ApiException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "Profissional sem especialidade configurada.",
        )

    # Valida vínculo opcional com pré-triagem
    triagem_id = body.triagem_id or None
    if triagem_id:
        triagem = db.get(Triagem, triagem_id)
        if triagem is None:
            raise ApiException(status.HTTP_404_NOT_FOUND, "Pré-triagem não encontrada.")
        if triagem.paciente_id != payload.sub:
            raise ApiException(
                status.HTTP_403_FORBIDDEN,
                "Você não tem permissão para vincular esta pré-triagem.",
            )

    consulta = Consulta(
        paciente_id=payload.sub,
        profissional_id=prof.usuario_id,
        clinica_id=slot.clinica_id,
        especialidade_id=esp.id,
        triagem_id=triagem_id,
        data=data_alvo,
        hora=body.hora,
        status="agendada",
        valor=float(esp.valor),
    )
    db.add(consulta)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise ApiException(
            status.HTTP_409_CONFLICT,
            "Esse horário não está mais disponível. Escolha outro.",
            code="HORARIO",
        ) from exc

    criar_notificacao(
        db,
        usuario_id=payload.sub,
        titulo="Consulta agendada",
        texto=f"{esp.nome} com {prof.usuario.nome} em {format_date_br(data_alvo)} às {body.hora}.",
    )
    criar_notificacao(
        db,
        usuario_id=prof.usuario_id,
        titulo="Novo paciente na agenda",
        texto=f"{paciente.usuario.nome}, {format_date_br(data_alvo)} às {body.hora}.",
    )
    db.commit()

    carregada = _carregar_consulta(db, consulta.id)
    assert carregada is not None
    return serializar_consulta(carregada)


def cancelar_consulta(
    db: Session,
    payload: TokenPayload,
    consulta_id: str,
    body: ConsultaCancelarIn | None = None,
) -> ConsultaOut:
    consulta = _carregar_consulta(db, consulta_id)
    if consulta is None:
        raise ApiException(status.HTTP_404_NOT_FOUND, "Consulta não encontrada.")

    if payload.perfil == PerfilEnum.PACIENTE and consulta.paciente_id != payload.sub:
        raise ApiException(status.HTTP_403_FORBIDDEN, "Esta consulta não é sua.")
    if payload.perfil == PerfilEnum.PROFISSIONAL and consulta.profissional_id != payload.sub:
        raise ApiException(status.HTTP_403_FORBIDDEN, "Esta consulta não pertence à sua agenda.")

    if consulta.status != "agendada":
        raise ApiException(
            status.HTTP_400_BAD_REQUEST,
            "Só dá para cancelar consultas agendadas.",
        )

    if payload.perfil == PerfilEnum.PACIENTE and hours_until(consulta.data, consulta.hora) < 24:
        raise ApiException(
            status.HTTP_400_BAD_REQUEST,
            "O cancelamento pelo app só é possível com 24 horas de antecedência. Ligue para a clínica.",
        )

    consulta.status = "cancelada"
    consulta.motivo_cancelamento = (body.motivo.strip() if body and body.motivo else "")
    consulta.cancelada_em = datetime.now(timezone.utc)

    criar_notificacao(
        db,
        usuario_id=consulta.paciente_id,
        titulo="Consulta cancelada",
        texto=f"A consulta de {format_date_br(consulta.data)} às {consulta.hora} foi cancelada.",
    )
    if payload.perfil == PerfilEnum.PACIENTE:
        criar_notificacao(
            db,
            usuario_id=consulta.profissional_id,
            titulo="Consulta cancelada pelo paciente",
            texto=f"{consulta.paciente.usuario.nome} cancelou a consulta de {format_date_br(consulta.data)} às {consulta.hora}.",
        )

    db.commit()
    db.refresh(consulta)
    return serializar_consulta(consulta)


def reagendar_consulta(
    db: Session,
    payload: TokenPayload,
    consulta_id: str,
    body: ConsultaReagendarIn,
) -> ConsultaOut:
    consulta = _carregar_consulta(db, consulta_id)
    if consulta is None:
        raise ApiException(status.HTTP_404_NOT_FOUND, "Consulta não encontrada.")

    if payload.perfil == PerfilEnum.PACIENTE and consulta.paciente_id != payload.sub:
        raise ApiException(status.HTTP_403_FORBIDDEN, "Esta consulta não é sua.")

    if consulta.status != "agendada":
        raise ApiException(
            status.HTTP_400_BAD_REQUEST,
            "Só dá para reagendar consultas agendadas.",
        )

    if payload.perfil == PerfilEnum.PACIENTE and hours_until(consulta.data, consulta.hora) < 24:
        raise ApiException(
            status.HTTP_400_BAD_REQUEST,
            "O reagendamento pelo app só é possível com 24 horas de antecedência. Ligue para a clínica.",
        )

    nova_data = parse_iso_date(body.data)
    parse_hhmm(body.hora)

    prof = db.scalar(
        select(Profissional)
        .options(joinedload(Profissional.disponibilidades))
        .where(Profissional.usuario_id == consulta.profissional_id)
    )
    if prof is None:
        raise ApiException(status.HTTP_404_NOT_FOUND, "Profissional não encontrado.")

    ocupados = set(
        db.scalars(
            select(Consulta.hora).where(
                Consulta.profissional_id == consulta.profissional_id,
                Consulta.data == nova_data,
                Consulta.status != "cancelada",
                Consulta.id != consulta.id,
            )
        ).all()
    )
    clinica_alvo = body.clinica_id or consulta.clinica_id
    slots = calcular_slots_do_dia(prof, nova_data, ocupados, clinica_id=clinica_alvo)
    slot = next((s for s in slots if s.hora == body.hora), None)
    if slot is None or not slot.disponivel:
        raise ApiException(
            status.HTTP_409_CONFLICT,
            "Esse horário não está mais disponível. Escolha outro.",
            code="HORARIO",
        )

    consulta.data = nova_data
    consulta.hora = body.hora
    consulta.clinica_id = slot.clinica_id
    consulta.lembrete_enviado = False

    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise ApiException(
            status.HTTP_409_CONFLICT,
            "Esse horário não está mais disponível. Escolha outro.",
            code="HORARIO",
        ) from exc

    criar_notificacao(
        db,
        usuario_id=consulta.paciente_id,
        titulo="Consulta reagendada",
        texto=f"Nova data: {format_date_br(nova_data)} às {body.hora}.",
    )
    db.commit()

    atualizada = _carregar_consulta(db, consulta.id)
    assert atualizada is not None
    return serializar_consulta(atualizada)


def atualizar_status_consulta(
    db: Session,
    payload: TokenPayload,
    consulta_id: str,
    body: ConsultaStatusIn,
) -> ConsultaOut:
    consulta = _carregar_consulta(db, consulta_id)
    if consulta is None:
        raise ApiException(status.HTTP_404_NOT_FOUND, "Consulta não encontrada.")

    if payload.perfil == PerfilEnum.PROFISSIONAL and consulta.profissional_id != payload.sub:
        raise ApiException(status.HTTP_403_FORBIDDEN, "Esta consulta não pertence à sua agenda.")

    consulta.status = body.status
    db.commit()
    db.refresh(consulta)
    return serializar_consulta(consulta)

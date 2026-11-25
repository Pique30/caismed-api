from uuid import uuid4

from fastapi import status
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.core.exceptions import ApiException
from app.core.security import PerfilEnum, hash_password
from app.core.utils import parse_hhmm
from app.models.catalogo import Clinica, Disponibilidade, Especialidade
from app.models.usuario import Profissional, Usuario
from app.schemas.catalogo import (
    ClinicaCreateIn,
    ClinicaOut,
    ClinicaUpdateIn,
    DisponibilidadeCreateIn,
    DisponibilidadeOut,
    EspecialidadeCreateIn,
    EspecialidadeOut,
    EspecialidadeUpdateIn,
    ProfissionalCreateIn,
    ProfissionalOut,
    ProfissionalUpdateIn,
)


def criar_especialidade(db: Session, body: EspecialidadeCreateIn) -> EspecialidadeOut:
    esp_id = body.id.strip().lower().replace(" ", "_")
    if db.get(Especialidade, esp_id):
        raise ApiException(status.HTTP_409_CONFLICT, "Já existe uma especialidade com este ID.")
    esp = Especialidade(
        id=esp_id,
        nome=body.nome.strip(),
        descricao=body.descricao.strip(),
        valor=float(body.valor),
        ativa=True,
    )
    db.add(esp)
    db.commit()
    return EspecialidadeOut(id=esp.id, nome=esp.nome, descricao=esp.descricao, valor=float(esp.valor))


def atualizar_especialidade(
    db: Session, esp_id: str, body: EspecialidadeUpdateIn
) -> EspecialidadeOut:
    esp = db.get(Especialidade, esp_id)
    if esp is None:
        raise ApiException(status.HTTP_404_NOT_FOUND, "Especialidade não encontrada.")
    if body.nome is not None:
        esp.nome = body.nome.strip()
    if body.descricao is not None:
        esp.descricao = body.descricao.strip()
    if body.valor is not None:
        esp.valor = float(body.valor)
    if body.ativa is not None:
        esp.ativa = body.ativa
    db.commit()
    return EspecialidadeOut(id=esp.id, nome=esp.nome, descricao=esp.descricao, valor=float(esp.valor))


def criar_clinica(db: Session, body: ClinicaCreateIn) -> ClinicaOut:
    cid = (body.id.strip() if body.id else f"u-{uuid4().hex[:8]}")
    if db.get(Clinica, cid):
        raise ApiException(status.HTTP_409_CONFLICT, "Já existe uma clínica com este ID.")
    c = Clinica(
        id=cid,
        nome=body.nome.strip(),
        bairro=body.bairro.strip(),
        cidade=body.cidade.strip(),
        endereco=body.endereco.strip(),
        telefone=body.telefone.strip(),
        horario=body.horario.strip(),
        ativa=True,
    )
    db.add(c)
    db.commit()
    return ClinicaOut(
        id=c.id,
        nome=c.nome,
        bairro=c.bairro,
        cidade=c.cidade,
        endereco=c.endereco,
        telefone=c.telefone,
        horario=c.horario,
    )


def atualizar_clinica(db: Session, clinica_id: str, body: ClinicaUpdateIn) -> ClinicaOut:
    c = db.get(Clinica, clinica_id)
    if c is None:
        raise ApiException(status.HTTP_404_NOT_FOUND, "Clínica não encontrada.")
    for campo in ("nome", "bairro", "cidade", "endereco", "telefone", "horario"):
        val = getattr(body, campo)
        if val is not None:
            setattr(c, campo, val.strip())
    if body.ativa is not None:
        c.ativa = body.ativa
    db.commit()
    return ClinicaOut(
        id=c.id,
        nome=c.nome,
        bairro=c.bairro,
        cidade=c.cidade,
        endereco=c.endereco,
        telefone=c.telefone,
        horario=c.horario,
    )


def criar_profissional(db: Session, body: ProfissionalCreateIn) -> ProfissionalOut:
    matricula = body.matricula.strip()
    if db.scalar(select(Profissional.usuario_id).where(Profissional.matricula == matricula)):
        raise ApiException(status.HTTP_409_CONFLICT, "Já existe um profissional com esta matrícula.")

    email = body.email.strip().lower() if body.email else None
    if email and db.scalar(select(Usuario.id).where(Usuario.email == email)):
        raise ApiException(status.HTTP_409_CONFLICT, "Este e-mail já está em uso.")

    esps = db.scalars(
        select(Especialidade).where(Especialidade.id.in_(body.especialidades))
    ).all()
    if len(esps) != len(set(body.especialidades)):
        raise ApiException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "Uma ou mais especialidades informadas não existem.",
        )

    uid = body.id.strip() if body.id else f"m-{uuid4().hex[:8]}"
    if db.get(Usuario, uid):
        raise ApiException(status.HTTP_409_CONFLICT, "Já existe um usuário com este ID.")

    usuario = Usuario(
        id=uid,
        perfil=PerfilEnum.PROFISSIONAL.value,
        nome=body.nome.strip(),
        email=email,
        senha_hash=hash_password(body.senha),
        ativo=True,
    )
    prof = Profissional(
        usuario_id=uid,
        matricula=matricula,
        crm=body.crm.strip(),
        nota=float(body.nota),
        bio=body.bio.strip(),
        especialidades=list(esps),
    )
    db.add(usuario)
    db.add(prof)
    db.commit()
    return ProfissionalOut(
        id=uid,
        nome=usuario.nome,
        crm=prof.crm,
        especialidades=[e.id for e in esps],
        nota=float(prof.nota),
        bio=prof.bio,
        clinicas=[],
        proximo=None,
    )


def atualizar_profissional(
    db: Session, profissional_id: str, body: ProfissionalUpdateIn
) -> ProfissionalOut:
    prof = db.scalar(
        select(Profissional)
        .options(
            joinedload(Profissional.usuario),
            joinedload(Profissional.especialidades),
            joinedload(Profissional.disponibilidades),
        )
        .where(Profissional.usuario_id == profissional_id)
    )
    if prof is None:
        raise ApiException(status.HTTP_404_NOT_FOUND, "Profissional não encontrado.")

    if body.nome is not None:
        prof.usuario.nome = body.nome.strip()
    if body.crm is not None:
        prof.crm = body.crm.strip()
    if body.nota is not None:
        prof.nota = float(body.nota)
    if body.bio is not None:
        prof.bio = body.bio.strip()
    if body.ativo is not None:
        prof.usuario.ativo = body.ativo
    if body.especialidades is not None:
        esps = db.scalars(
            select(Especialidade).where(Especialidade.id.in_(body.especialidades))
        ).all()
        if not esps or len(esps) != len(set(body.especialidades)):
            raise ApiException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                "Uma ou mais especialidades informadas não existem.",
            )
        prof.especialidades = list(esps)

    db.commit()
    return ProfissionalOut(
        id=prof.usuario_id,
        nome=prof.usuario.nome,
        crm=prof.crm,
        especialidades=[e.id for e in prof.especialidades],
        nota=float(prof.nota),
        bio=prof.bio,
        clinicas=sorted({d.clinica_id for d in prof.disponibilidades}),
        proximo=None,
    )


def adicionar_disponibilidade(
    db: Session, profissional_id: str, body: DisponibilidadeCreateIn
) -> DisponibilidadeOut:
    if db.get(Profissional, profissional_id) is None:
        raise ApiException(status.HTTP_404_NOT_FOUND, "Profissional não encontrado.")
    if db.get(Clinica, body.clinica_id) is None:
        raise ApiException(status.HTTP_404_NOT_FOUND, "Clínica não encontrada.")

    inicio = parse_hhmm(body.hora_inicio)
    fim = parse_hhmm(body.hora_fim)
    if fim <= inicio:
        raise ApiException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "O horário final deve ser maior que o horário inicial.",
        )

    disp = Disponibilidade(
        profissional_id=profissional_id,
        clinica_id=body.clinica_id,
        dia_semana=body.dia_semana,
        hora_inicio=body.hora_inicio,
        hora_fim=body.hora_fim,
        duracao_minutos=body.duracao_minutos,
    )
    db.add(disp)
    db.commit()
    return DisponibilidadeOut(
        id=disp.id,
        profissional_id=disp.profissional_id,
        clinica_id=disp.clinica_id,
        dia_semana=disp.dia_semana,
        hora_inicio=disp.hora_inicio,
        hora_fim=disp.hora_fim,
        duracao_minutos=disp.duracao_minutos,
    )


def remover_disponibilidade(db: Session, disponibilidade_id: str) -> None:
    disp = db.get(Disponibilidade, disponibilidade_id)
    if disp is None:
        raise ApiException(status.HTTP_404_NOT_FOUND, "Disponibilidade não encontrada.")
    db.delete(disp)
    db.commit()

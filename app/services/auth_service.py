from datetime import datetime, timezone

from fastapi import status
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.core.exceptions import ApiException
from app.core.security import (
    PerfilEnum,
    TokenPayload,
    create_access_token,
    hash_password,
    revoke_token,
    verify_password,
)
from app.core.utils import cpf_valido, email_valido, parse_iso_date, so_digitos, today_app_tz
from app.models.usuario import Paciente, Profissional, Usuario
from app.schemas.auth import (
    AdminMeOut,
    AuthTokenOut,
    LoginIn,
    PacienteMeOut,
    PacienteUpdateIn,
    ProfissionalMeOut,
    RegisterIn,
    UsuarioResumoOut,
)
from app.services.notificacao_service import criar_notificacao


def registrar_paciente(db: Session, body: RegisterIn) -> AuthTokenOut:
    nome = body.nome.strip()
    if len(nome) < 3:
        raise ApiException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Informe seu nome completo.")

    cpf_limpo = so_digitos(body.cpf)
    if not cpf_valido(cpf_limpo):
        raise ApiException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "CPF inválido. Confira os 11 números.",
        )

    email = body.email.strip().lower()
    if not email_valido(email):
        raise ApiException(status.HTTP_422_UNPROCESSABLE_CONTENT, "E-mail inválido.")

    if len(body.senha) < 6:
        raise ApiException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "A senha deve ter pelo menos 6 caracteres.",
        )

    if not body.aceite_lgpd:
        raise ApiException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "É necessário aceitar os termos de uso e a LGPD para criar a conta.",
        )

    nascimento = None
    if body.nascimento:
        nascimento = parse_iso_date(body.nascimento, field_label="data de nascimento")
        if nascimento > today_app_tz():
            raise ApiException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                "A data de nascimento não pode estar no futuro.",
            )

    if db.scalar(select(Paciente.usuario_id).where(Paciente.cpf == cpf_limpo)):
        raise ApiException(
            status.HTTP_409_CONFLICT,
            "Já existe uma conta com este CPF. Entre com a sua senha.",
        )

    if db.scalar(select(Usuario.id).where(Usuario.email == email)):
        raise ApiException(
            status.HTTP_409_CONFLICT,
            "Já existe uma conta cadastrada com este e-mail.",
        )

    agora = datetime.now(timezone.utc)
    usuario = Usuario(
        perfil=PerfilEnum.PACIENTE.value,
        nome=nome,
        email=email,
        senha_hash=hash_password(body.senha),
        ativo=True,
        criado_em=agora,
    )
    db.add(usuario)
    db.flush()

    paciente = Paciente(
        usuario_id=usuario.id,
        cpf=cpf_limpo,
        nascimento=nascimento,
        telefone=body.telefone.strip(),
        aceite_lgpd=True,
        aceite_lgpd_em=agora,
    )
    db.add(paciente)
    criar_notificacao(
        db,
        usuario_id=usuario.id,
        titulo="Bem-vindo à CaisMed",
        texto="Conta criada. Já pode agendar consultas e fazer a pré-triagem.",
    )
    db.commit()

    token = create_access_token(usuario.id, PerfilEnum.PACIENTE)
    return AuthTokenOut(
        token=token,
        usuario=UsuarioResumoOut(id=usuario.id, nome=usuario.nome, perfil=usuario.perfil),
    )


def autenticar_usuario(db: Session, body: LoginIn) -> AuthTokenOut:
    usuario: Usuario | None = None
    msg_erro = "Credenciais incorretas."

    if body.perfil == PerfilEnum.PACIENTE:
        msg_erro = "CPF ou senha incorretos."
        cpf_limpo = so_digitos(body.login)
        if cpf_limpo:
            paciente = db.scalar(
                select(Paciente)
                .options(joinedload(Paciente.usuario))
                .where(Paciente.cpf == cpf_limpo)
            )
            usuario = paciente.usuario if paciente else None
    elif body.perfil == PerfilEnum.PROFISSIONAL:
        msg_erro = "Matrícula ou senha incorretas."
        matricula = body.login.strip()
        if matricula:
            prof = db.scalar(
                select(Profissional)
                .options(joinedload(Profissional.usuario))
                .where(Profissional.matricula == matricula)
            )
            usuario = prof.usuario if prof else None
    elif body.perfil == PerfilEnum.ADMIN:
        msg_erro = "E-mail ou senha de administrador incorretos."
        email = body.login.strip().lower()
        if email:
            usuario = db.scalar(
                select(Usuario).where(
                    Usuario.email == email,
                    Usuario.perfil == PerfilEnum.ADMIN.value,
                )
            )

    if usuario is None or not usuario.ativo or not verify_password(body.senha, usuario.senha_hash):
        raise ApiException(status.HTTP_401_UNAUTHORIZED, msg_erro)

    token = create_access_token(usuario.id, PerfilEnum(usuario.perfil))
    return AuthTokenOut(
        token=token,
        usuario=UsuarioResumoOut(id=usuario.id, nome=usuario.nome, perfil=usuario.perfil),
    )


def encerrar_sessao(db: Session, payload: TokenPayload) -> None:
    revoke_token(db, payload)


def obter_usuario_atual(
    db: Session, payload: TokenPayload
) -> PacienteMeOut | ProfissionalMeOut | AdminMeOut:
    usuario = db.scalar(
        select(Usuario)
        .options(
            joinedload(Usuario.paciente),
            joinedload(Usuario.profissional).joinedload(Profissional.especialidades),
            joinedload(Usuario.profissional).joinedload(Profissional.disponibilidades),
        )
        .where(Usuario.id == payload.sub)
    )
    if usuario is None or not usuario.ativo:
        raise ApiException(
            status.HTTP_401_UNAUTHORIZED,
            "Sessão inválida. Entre de novo.",
            code="SESSAO",
        )

    if usuario.perfil == PerfilEnum.PACIENTE.value and usuario.paciente:
        p = usuario.paciente
        return PacienteMeOut(
            id=usuario.id,
            nome=usuario.nome,
            cpf=p.cpf,
            nascimento=p.nascimento.isoformat() if p.nascimento else None,
            telefone=p.telefone,
            email=usuario.email,
            perfil=PerfilEnum.PACIENTE.value,
            criado_em=usuario.criado_em.isoformat(),
        )

    if usuario.perfil == PerfilEnum.PROFISSIONAL.value and usuario.profissional:
        pr = usuario.profissional
        clinicas_ids = sorted({d.clinica_id for d in pr.disponibilidades})
        return ProfissionalMeOut(
            id=usuario.id,
            nome=usuario.nome,
            matricula=pr.matricula,
            crm=pr.crm,
            especialidades=[e.id for e in pr.especialidades],
            nota=float(pr.nota),
            bio=pr.bio,
            clinicas=clinicas_ids,
            email=usuario.email,
            perfil=PerfilEnum.PROFISSIONAL.value,
            criado_em=usuario.criado_em.isoformat(),
        )

    return AdminMeOut(
        id=usuario.id,
        nome=usuario.nome,
        email=usuario.email,
        perfil=usuario.perfil,
        criado_em=usuario.criado_em.isoformat(),
    )


def atualizar_perfil_paciente(
    db: Session, payload: TokenPayload, body: PacienteUpdateIn
) -> PacienteMeOut:
    usuario = db.scalar(
        select(Usuario)
        .options(joinedload(Usuario.paciente))
        .where(Usuario.id == payload.sub)
    )
    if usuario is None or usuario.paciente is None:
        raise ApiException(status.HTTP_404_NOT_FOUND, "Paciente não encontrado.")

    if body.nome is not None:
        nome = body.nome.strip()
        if len(nome) < 3:
            raise ApiException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Informe seu nome completo.")
        usuario.nome = nome

    if body.email is not None:
        email = body.email.strip().lower()
        if not email_valido(email):
            raise ApiException(status.HTTP_422_UNPROCESSABLE_CONTENT, "E-mail inválido.")
        outro = db.scalar(
            select(Usuario.id).where(Usuario.email == email, Usuario.id != usuario.id)
        )
        if outro:
            raise ApiException(status.HTTP_409_CONFLICT, "Este e-mail já está em uso.")
        usuario.email = email

    if body.telefone is not None:
        usuario.paciente.telefone = body.telefone.strip()

    if body.nascimento is not None:
        if body.nascimento.strip():
            nasc = parse_iso_date(body.nascimento, field_label="data de nascimento")
            if nasc > today_app_tz():
                raise ApiException(
                    status.HTTP_422_UNPROCESSABLE_CONTENT,
                    "A data de nascimento não pode estar no futuro.",
                )
            usuario.paciente.nascimento = nasc

    if body.senha is not None and body.senha != "":
        if len(body.senha) < 6:
            raise ApiException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                "A senha deve ter pelo menos 6 caracteres.",
            )
        usuario.senha_hash = hash_password(body.senha)

    db.commit()
    db.refresh(usuario)
    return PacienteMeOut(
        id=usuario.id,
        nome=usuario.nome,
        cpf=usuario.paciente.cpf,
        nascimento=usuario.paciente.nascimento.isoformat() if usuario.paciente.nascimento else None,
        telefone=usuario.paciente.telefone,
        email=usuario.email,
        perfil=PerfilEnum.PACIENTE.value,
        criado_em=usuario.criado_em.isoformat(),
    )

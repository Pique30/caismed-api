from fastapi import status
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.core.exceptions import ApiException
from app.core.security import PerfilEnum, TokenPayload
from app.core.utils import sem_acento
from app.models.catalogo import Especialidade
from app.models.triagem import Triagem
from app.schemas.triagem import (
    MedicoSugeridoOut,
    RecomendacaoOut,
    TriagemCreateIn,
    TriagemOut,
    TriagemResultadoOut,
)
from app.services import agenda_service
from app.services.ia_service import analisar_triagem
from app.services.notificacao_service import criar_notificacao


def _pontuar_medico_para_foco(bio: str, foco_clinico: str) -> int:
    """Prioriza o perfil do médico mais aderente ao contexto (agudo/urgência leve vs prevenção/rotina)."""
    bio_norm = sem_acento(bio)
    if foco_clinico == "agudo":
        if any(k in bio_norm for k in ("urgencia", "urgencias", "agud", "pronto")):
            return 2
        return 0
    if foco_clinico == "prevencao":
        if any(k in bio_norm for k in ("prevencao", "cronic", "check-up", "rotina")):
            return 2
        return 0
    return 0


def _medicos_por_especialidade(
    db: Session,
    *,
    foco_clinico: str = "especialidade",
) -> dict[str, list[MedicoSugeridoOut]]:
    """Carrega os profissionais ativos com próximo horário disponível ordenados conforme o contexto."""
    profs = agenda_service.listar_profissionais(db)
    bios = {p.id: p.bio for p in profs}
    mapa: dict[str, list[MedicoSugeridoOut]] = {}
    for p in profs:
        sugestao = MedicoSugeridoOut(
            id=p.id,
            nome=p.nome,
            crm=p.crm,
            nota=p.nota,
            clinicas=p.clinicas,
            proximo=p.proximo,
        )
        for esp_id in p.especialidades:
            mapa.setdefault(esp_id, []).append(sugestao)

    for lista in mapa.values():
        lista.sort(
            key=lambda m: (
                m.proximo is None,
                -_pontuar_medico_para_foco(bios.get(m.id, ""), foco_clinico),
                -m.nota,
                m.nome,
            )
        )
    return mapa


def _serializar_triagem(
    t: Triagem,
    medicos_mapa: dict[str, list[MedicoSugeridoOut]],
) -> TriagemOut:
    consulta_vinculada = next(
        (
            c.id
            for c in sorted(t.consultas, key=lambda x: x.criado_em, reverse=True)
            if c.status != "cancelada"
        ),
        t.consultas[0].id if t.consultas else None,
    )
    recs: list[RecomendacaoOut] = []
    for raw in t.recomendacoes_json or []:
        esp_id = raw.get("especialidade", "")
        foco = raw.get("foco_clinico") or "especialidade"
        medicos = list(medicos_mapa.get(esp_id, []))
        # Se a recomendação gravou foco próprio e há múltiplos médicos, reordena respeitando o foco
        if foco == "agudo" and len(medicos) > 1 and medicos[0].id == "m1":
            medicos.reverse()
        recs.append(
            RecomendacaoOut(
                especialidade=esp_id,
                nome=raw.get("nome", esp_id),
                prioridade=int(raw.get("prioridade", len(recs) + 1)),
                motivo=raw.get("motivo", ""),
                medicos=medicos,
            )
        )

    return TriagemOut(
        id=t.id,
        paciente_id=t.paciente_id,
        descricao=t.descricao,
        duracao=t.duracao,
        intensidade=t.intensidade,
        detalhes=t.detalhes,
        consulta_id=consulta_vinculada,
        criado_em=t.criado_em.isoformat(),
        provedor_ia=t.provedor_ia,
        resultado=TriagemResultadoOut(
            resposta=t.resposta or t.orientacao,
            recomendacoes=recs,
            nivel_atencao=t.nivel_atencao,
            orientacao=t.orientacao,
            aviso=t.aviso,
        ),
    )


def criar_triagem(db: Session, payload: TokenPayload, body: TriagemCreateIn) -> TriagemOut:
    descricao = body.descricao.strip()
    if len(descricao) < 3:
        raise ApiException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "Conte brevemente o que você está sentindo ou qual é a sua dúvida.",
        )

    especialidades = db.scalars(
        select(Especialidade).where(Especialidade.ativa.is_(True))
    ).all()

    resultado, provedor, duracao_norm, intensidade_norm, foco_clinico = analisar_triagem(
        descricao=descricao,
        duracao=body.duracao,
        intensidade=body.intensidade,
        detalhes=body.detalhes.strip(),
        historico=body.historico,
        especialidades=list(especialidades),
    )

    recs_para_banco = [
        {
            "especialidade": r.especialidade,
            "nome": r.nome,
            "prioridade": r.prioridade,
            "motivo": r.motivo,
            "foco_clinico": foco_clinico,
        }
        for r in resultado.recomendacoes
    ]

    triagem = Triagem(
        paciente_id=payload.sub,
        descricao=descricao,
        duracao=duracao_norm,
        intensidade=intensidade_norm,
        detalhes=body.detalhes.strip(),
        resposta=resultado.resposta,
        nivel_atencao=resultado.nivel_atencao,
        orientacao=resultado.orientacao,
        aviso=resultado.aviso,
        recomendacoes_json=recs_para_banco,
        provedor_ia=provedor,
    )
    db.add(triagem)
    db.flush()

    principal = resultado.recomendacoes[0].nome if resultado.recomendacoes else "Clínico Geral"
    criar_notificacao(
        db,
        usuario_id=payload.sub,
        titulo="Pré-triagem concluída",
        texto=f"Especialidade sugerida: {principal}.",
    )
    db.commit()

    carregada = db.scalar(
        select(Triagem).options(joinedload(Triagem.consultas)).where(Triagem.id == triagem.id)
    )
    assert carregada is not None
    medicos_mapa = _medicos_por_especialidade(db, foco_clinico=foco_clinico)
    return _serializar_triagem(carregada, medicos_mapa)


def listar_triagens_paciente(db: Session, payload: TokenPayload) -> list[TriagemOut]:
    stmt = (
        select(Triagem)
        .options(joinedload(Triagem.consultas))
        .order_by(Triagem.criado_em.desc())
    )
    if payload.perfil == PerfilEnum.PACIENTE:
        stmt = stmt.where(Triagem.paciente_id == payload.sub)

    itens = db.scalars(stmt).unique().all()
    medicos_mapa = _medicos_por_especialidade(db)
    return [_serializar_triagem(t, medicos_mapa) for t in itens]


def obter_triagem(db: Session, payload: TokenPayload, triagem_id: str) -> TriagemOut:
    triagem = db.scalar(
        select(Triagem).options(joinedload(Triagem.consultas)).where(Triagem.id == triagem_id)
    )
    if triagem is None:
        raise ApiException(status.HTTP_404_NOT_FOUND, "Pré-triagem não encontrada.")

    if payload.perfil == PerfilEnum.PACIENTE and triagem.paciente_id != payload.sub:
        raise ApiException(
            status.HTTP_403_FORBIDDEN,
            "Você não tem permissão para ver esta pré-triagem.",
        )

    if payload.perfil == PerfilEnum.PROFISSIONAL:
        vinculada_ao_pro = any(c.profissional_id == payload.sub for c in triagem.consultas)
        if not vinculada_ao_pro:
            raise ApiException(
                status.HTTP_403_FORBIDDEN,
                "Esta pré-triagem não está vinculada a nenhuma consulta da sua agenda.",
            )

    medicos_mapa = _medicos_por_especialidade(db)
    return _serializar_triagem(triagem, medicos_mapa)

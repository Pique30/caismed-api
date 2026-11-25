"""Serviço isolado de Pré-triagem com IA (Google Gemini + guardrails clínicos + fallback contextual)."""

from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
import json
import logging
import re
from typing import Literal

from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.core.utils import sem_acento
from app.models.catalogo import Especialidade
from app.schemas.triagem import MensagemHistoricoIn, RecomendacaoOut, TriagemResultadoOut

logger = logging.getLogger("caismed.ia")

AVISO_OBRIGATORIO = (
    "Esta é uma orientação inicial gerada por inteligência artificial. "
    "Ela não substitui a avaliação de um médico."
)

ORIENTACAO_URGENTE = (
    "Os sinais descritos exigem atenção imediata. Procure um pronto-socorro agora "
    "ou ligue 192 (SAMU), sem esperar por uma consulta agendada."
)

SINAIS_ALERTA = [
    "falta de ar",
    "dor no peito",
    "dor forte no peito",
    "aperto no peito",
    "desmaio",
    "desmaiei",
    "sangramento intenso",
    "sangramento",
    "convulsao",
    "nao consigo respirar",
    "sem ar",
    "perda de forca",
    "fala enrolada",
    "boca torta",
    "visao subita",
]

# Especialidades da rede com explicações próprias (sem frases genéricas repetidas)
REGRAS_ESPECIALIDADES: list[dict] = [
    {
        "esp": "cardiologia",
        "palavras": [
            "peito",
            "coracao",
            "palpita",
            "pressao",
            "hipertens",
            "taquicardia",
            "falta de ar",
            "inchaco nas pernas",
            "arritmia",
            "cardio",
        ],
        "motivo": "Avalia sintomas relacionados ao coração, pressão arterial e circulação com exames direcionados.",
        "resposta": (
            "Alterações ligadas ao coração, palpitações ou pressão arterial merecem uma avaliação focada "
            "com um cardiologista. Já separei a especialidade e o atendimento disponível abaixo."
        ),
    },
    {
        "esp": "dermatologia",
        "palavras": [
            "pele",
            "mancha",
            "coceira",
            "alergia na pele",
            "alergia",
            "espinha",
            "acne",
            "ferida",
            "vermelhidao",
            "cabelo",
            "queda de cabelo",
            "unha",
            "caroco na pele",
            "micose",
            "bolinha",
            "descama",
        ],
        "motivo": "Especialidade dedicada a manchas, coceiras, alergias cutâneas, cabelos e unhas.",
        "resposta": (
            "Sinais na pele, coceiras ou alterações em cabelos e unhas são melhor avaliados por um "
            "dermatologista, que consegue examinar o aspecto de perto e indicar o tratamento certo."
        ),
    },
    {
        "esp": "ortopedia",
        "palavras": [
            "joelho",
            "coluna",
            "costas",
            "osso",
            "fratura",
            "ombro",
            "tornozelo",
            "muscul",
            "articula",
            "perna",
            "braco",
            "quadril",
            "lombar",
            "entorse",
            "torci",
            "pescoco",
            "tendinite",
        ],
        "motivo": "Indicada para dores ou lesões em ossos, coluna, articulações e músculos.",
        "resposta": (
            "Dores musculares, articulares ou na coluna costumam ser investigadas pelo ortopedista, "
            "que avalia a mobilidade e define se há necessidade de exame de imagem ou reabilitação."
        ),
    },
    {
        "esp": "pediatria",
        "palavras": [
            "crianca",
            "filho",
            "filha",
            "bebe",
            "neto",
            "neta",
            "recem",
            "infantil",
            "pediatr",
            "menino",
            "menina",
        ],
        "motivo": "Acompanha bebês, crianças e adolescentes com avaliação adequada à faixa etária.",
        "resposta": (
            "Quando os sintomas envolvem crianças ou bebês, o mais seguro é passar por um pediatra, "
            "que faz a avaliação considerando peso, idade e histórico infantil."
        ),
    },
    {
        "esp": "ginecologia",
        "palavras": [
            "gravidez",
            "gestante",
            "gravida",
            "menstrua",
            "colica",
            "utero",
            "corrimento",
            "mama",
            "ovario",
            "preventivo",
            "gineco",
            "anticoncepcional",
            "menopausa",
        ],
        "motivo": "Cuida da saúde da mulher, ciclo menstrual, exames preventivos e gestação.",
        "resposta": (
            "Para questões ligadas ao ciclo menstrual, saúde íntima, exames preventivos ou gestação, "
            "a ginecologia é a especialidade mais indicada."
        ),
    },
]

# Cenários contextuais específicos (clínica geral / fora da rede / dúvidas de hipótese)
CENARIOS_CONTEXTUAIS: list[dict] = [
    {
        "nome": "odontologia",
        "foco": "agudo",
        "palavras": ["dente", "dentes", "gengiva", "siso", "carie", "odont", "molar", "mastigar", "canal no dente"],
        "resposta": (
            "Para dor de dente ou incômodo na gengiva, o profissional ideal é um dentista. "
            "Como a CaisMed ainda não conta com odontologia na rede, se houver dor forte, inchaço no rosto "
            "ou febre, um Clínico Geral pode fazer uma avaliação inicial e orientar cuidados até você passar pelo dentista."
        ),
        "motivo": "Pode avaliar sinais de inflamação, inchaço ou febre e orientar cuidados iniciais até o atendimento odontológico.",
        "orientacao": "Procure um dentista assim que possível; se a dor estiver intensa ou houver inchaço/febre, agende uma avaliação inicial com o Clínico Geral abaixo.",
    },
    {
        "nome": "oftalmologia",
        "foco": "agudo",
        "palavras": ["olho", "olhos", "visao", "vista", "embacad", "conjuntivite", "lacrimej", "ardencia nos olhos"],
        "resposta": (
            "Sintomas nos olhos ou alterações na visão costumam ser avaliados por um oftalmologista. "
            "Enquanto isso, você pode agendar com um Clínico Geral da CaisMed para uma triagem inicial "
            "e encaminhamento adequado caso haja vermelhidão, secreção ou desconforto."
        ),
        "motivo": "Faz a avaliação inicial de desconfortos oculares comuns (como irritação ou conjuntivite) e encaminha ao oftalmologista se necessário.",
        "orientacao": "Evite coçar os olhos ou usar colírios sem orientação; agende uma avaliação inicial abaixo.",
    },
    {
        "nome": "gripe_respiratorio",
        "foco": "agudo",
        "palavras": [
            "gripe",
            "gripad",
            "resfriado",
            "coriza",
            "nariz entupido",
            "tosse",
            "garganta",
            "espirro",
            "catarro",
            "sinusite",
            "rinite",
            "febre",
        ],
        "resposta": (
            "Esses sinais são bastante comuns em quadros virais, como gripe, resfriado ou inflamações "
            "das vias aéreas, mas também podem aparecer em outras infecções. Vale passar por um Clínico Geral "
            "para avaliar seu estado geral e indicar o cuidado mais adequado."
        ),
        "motivo": "Avalia sintomas respiratórios, febre e mal-estar para diferenciar quadros virais simples de infecções que pedem tratamento específico.",
        "orientacao": "Mantenha boa hidratação e repouso; se a febre persistir ou os sintomas piorarem, agende com o Clínico Geral abaixo.",
    },
    {
        "nome": "cefaleia",
        "foco": "agudo",
        "palavras": ["dor de cabeca", "cabeca doendo", "enxaqueca", "cefaleia", "cabeca pesada", "tontura"],
        "resposta": (
            "Dor de cabeça pode ter várias causas — desde tensão, cansaço, desidratação e sinusite até "
            "um quadro viral inicial (como gripe) ou alteração de pressão. O ideal é consultar um Clínico Geral "
            "para investigar a origem e orientar o tratamento seguro."
        ),
        "motivo": "Investiga a causa da dor de cabeça ou tontura (tensão, pressão, sinusite ou quadro viral) e orienta o manejo adequado.",
        "orientacao": "Observe se a dor vem acompanhada de febre, rigidez no pescoço ou alteração visual; para avaliação completa, agende com o Clínico Geral abaixo.",
    },
    {
        "nome": "gastro",
        "foco": "agudo",
        "palavras": ["estomago", "azia", "refluxo", "gastrite", "barriga", "diarreia", "enjoo", "nausea", "vomito", "indigestao"],
        "resposta": (
            "Desconfortos no estômago, enjoo ou alterações intestinais podem estar ligados a alimentação, "
            "viroses ou gastrite. Um Clínico Geral consegue avaliar seus sintomas, checar sinais de desidratação "
            "e orientar exames ou tratamento."
        ),
        "motivo": "Avalia sintomas digestivos, orienta hidratação e solicita exames se necessário.",
        "orientacao": "Priorize líquidos e alimentação leve, e agende com um Clínico Geral abaixo se o desconforto continuar.",
    },
    {
        "nome": "saude_mental_sono",
        "foco": "prevencao",
        "palavras": ["ansiedade", "estresse", "insonia", "nao consigo dormir", "tristeza", "depressao", "panico", "esgotamento", "cansaco constante"],
        "resposta": (
            "Questões como ansiedade, cansaço persistente ou dificuldade para dormir merecem escuta e "
            "cuidado médico — inclusive para descartar causas físicas como alterações hormonais ou deficiências "
            "de vitaminas. Um Clínico Geral é um ótimo ponto de partida para acolher e encaminhar se preciso."
        ),
        "motivo": "Faz uma avaliação clínica global, checa causas físicas e orienta o acompanhamento ou encaminhamento especializado.",
        "orientacao": "Você não precisa lidar com isso sozinho(a); agende uma consulta tranquila com o Clínico Geral abaixo.",
    },
    {
        "nome": "checkup_rotina",
        "foco": "prevencao",
        "palavras": ["check-up", "checkup", "exame", "exames", "rotina", "prevencao", "qual medico", "acompanhamento"],
        "resposta": (
            "Para check-up, exames de rotina ou quando você quer fazer uma avaliação geral da saúde, "
            "o Clínico Geral é o profissional ideal. Ele revisa seu histórico, solicita os exames certos "
            "e indica outros especialistas apenas se houver necessidade."
        ),
        "motivo": "Conduz check-ups completos, acompanha saúde preventiva e solicita exames de rotina.",
        "orientacao": "Escolha abaixo um horário com o Clínico Geral focado em prevenção para o seu check-up.",
    },
]

HIPOTESES_PERGUNTA: list[tuple[list[str], str]] = [
    (
        ["gripe", "resfriado", "virose", "gripad"],
        "Pode sim ser somente uma gripe ou uma virose leve, mas como sintomas parecidos também podem ter outras causas, vale consultar um médico para avaliar com segurança.",
    ),
    (
        ["dengue", "zika", "chikungunya"],
        "Pode sim lembrar um quadro viral como dengue, especialmente se houver febre ou dor no corpo. É importante passar por avaliação médica para confirmar e acompanhar sinais de alerta, evitando automedicação.",
    ),
    (
        ["sinusite", "rinite"],
        "Pode sim estar relacionado a sinusite ou rinite, principalmente se houver peso no rosto ou nariz congestionado. Uma avaliação com o Clínico Geral ajuda a confirmar e indicar o cuidado adequado.",
    ),
    (
        ["enxaqueca"],
        "Pode sim ser uma crise de enxaqueca, sobretudo se a dor for pulsátil ou vier com sensibilidade à luz. Vale consultar um médico para avaliar o padrão das crises e orientar o tratamento.",
    ),
    (
        ["alergia"],
        "Pode sim ser uma reação alérgica, mas observar a evolução com um médico é a melhor forma de identificar a causa e escolher o tratamento seguro.",
    ),
    (
        ["estresse", "ansiedade", "cansaco"],
        "Pode sim ter relação com estresse ou cansaço acumulado, mas vale conversar com um médico para avaliar o quadro como um todo e descartar outras causas clínicas.",
    ),
    (
        ["gastrite", "refluxo"],
        "Pode sim ser gastrite ou refluxo, mas uma consulta médica ajuda a confirmar a causa do desconforto e evitar que piore.",
    ),
]

DURACAO_LABELS = {
    "hoje": "começou hoje",
    "dias": "há 2 ou 3 dias",
    "semana": "há cerca de 1 semana",
    "mais_semana": "há mais de 1 semana",
    "nao_informada": "não informada",
}


class _GeminiRecomendacao(BaseModel):
    especialidade: str = Field(..., description="ID exato da especialidade da lista fornecida")
    prioridade: int = Field(..., ge=1, le=3)
    motivo: str = Field(..., min_length=8, max_length=220)


class _GeminiTriagemPayload(BaseModel):
    resposta: str = Field(
        ...,
        min_length=15,
        max_length=450,
        description="Resposta direta, natural, específica ao contexto e sem fórmulas repetitivas.",
    )
    recomendacoes: list[_GeminiRecomendacao] = Field(..., min_length=1, max_length=2)
    nivel_atencao: Literal["rotina", "breve", "urgente"]
    foco_clinico: Literal["agudo", "prevencao", "especialidade"] = "especialidade"
    orientacao: str = Field(..., min_length=10, max_length=320)


def inferir_duracao_e_intensidade(
    descricao: str,
    detalhes: str,
    duracao: str | None,
    intensidade: int | None,
) -> tuple[str, int | None]:
    """Extrai pistas opcionais de duração e intensidade do texto livre sem travar o usuário."""
    txt = sem_acento(f"{descricao} {detalhes}")

    duracao_final = (duracao or "").strip()
    if not duracao_final:
        if any(p in txt for p in ["meses", "semanas", "faz tempo", "mais de uma semana", "2 semanas", "ha semanas"]):
            duracao_final = "mais_semana"
        elif any(p in txt for p in ["uma semana", "1 semana", "7 dias"]):
            duracao_final = "semana"
        elif any(p in txt for p in ["ontem", "2 dias", "3 dias", "dois dias", "tres dias", "alguns dias"]):
            duracao_final = "dias"
        elif any(p in txt for p in ["hoje", "agora", "acordei", "ha pouco"]):
            duracao_final = "hoje"
        else:
            duracao_final = "nao_informada"

    intensidade_final = intensidade
    if intensidade_final is None:
        m = re.search(r"\b(10|[0-9])\s*(?:/\s*10|de\s*10)\b", txt)
        if m:
            intensidade_final = int(m.group(1))
        elif any(p in txt for p in ["insuportavel", "muito forte", "intensa", "intenso", "aguda", "muito intensa"]):
            intensidade_final = 9
        elif any(p in txt for p in ["forte", "bastante", "piorando", "incomoda muito"]):
            intensidade_final = 7
        elif any(p in txt for p in ["moderada", "moderado", "mais ou menos"]):
            intensidade_final = 5
        elif any(p in txt for p in ["leve", "fraca", "fraco", "pouco", "de leve"]):
            intensidade_final = 2

    return duracao_final, intensidade_final


def _tem_sinal_alerta(texto: str) -> bool:
    txt = sem_acento(texto)
    return any(sinal in txt for sinal in SINAIS_ALERTA)


def _eh_pergunta_hipotese(texto: str) -> bool:
    txt = sem_acento(texto)
    return (
        "?" in texto
        or any(
            gatilho in txt
            for gatilho in ["pode ser", "sera que", "sera ", "e so ", "e somente", "talvez seja", "parece ser"]
        )
    )


def _texto_historico_usuario(historico: list[MensagemHistoricoIn]) -> str:
    """Extrai as últimas mensagens do próprio paciente para entender perguntas de acompanhamento."""
    ultimas = [m.texto for m in historico if m.de == "eu"][-2:]
    return " ".join(ultimas)


def _analisar_fallback(
    descricao: str,
    duracao: str,
    intensidade: int | None,
    detalhes: str,
    historico: list[MensagemHistoricoIn],
    especialidades: list[Especialidade],
) -> tuple[TriagemResultadoOut, str]:
    esps_por_id = {e.id: e for e in especialidades}
    txt_atual = sem_acento(f"{descricao} {detalhes}")
    ctx_anterior = sem_acento(_texto_historico_usuario(historico))
    txt_combinado = f"{ctx_anterior} {txt_atual}".strip()

    # 1. Verifica se é pergunta de hipótese ("pode ser somente gripe?", "será alergia?", etc.)
    resposta_hipotese: str | None = None
    if _eh_pergunta_hipotese(descricao):
        for palavras_hip, texto_hip in HIPOTESES_PERGUNTA:
            if any(p in txt_atual for p in palavras_hip):
                resposta_hipotese = texto_hip
                break

    # 2. Avalia especialidades específicas da rede (priorizando a mensagem atual, depois contexto)
    pontuadas: list[tuple[dict, int]] = []
    for regra in REGRAS_ESPECIALIDADES:
        if regra["esp"] not in esps_por_id:
            continue
        peso_atual = sum(2 for p in regra["palavras"] if p in txt_atual)
        peso_ctx = sum(1 for p in regra["palavras"] if p in ctx_anterior) if resposta_hipotese else 0
        total = peso_atual + peso_ctx
        if total > 0:
            pontuadas.append((regra, total))

    pontuadas.sort(key=lambda item: item[1], reverse=True)

    # 3. Avalia cenários contextuais específicos (dente, olhos, gripe, dor de cabeça, gastro, mental, checkup)
    cenario_match: dict | None = None
    melhor_score_cen = 0
    for cen in CENARIOS_CONTEXTUAIS:
        score = sum(2 for p in cen["palavras"] if p in txt_atual)
        if score == 0 and resposta_hipotese:
            score = sum(1 for p in cen["palavras"] if p in ctx_anterior)
        if score > melhor_score_cen:
            melhor_score_cen = score
            cenario_match = cen

    alerta = _tem_sinal_alerta(f"{descricao} {detalhes}")
    inten_num = intensidade if intensidade is not None else 0

    # Nível de atenção
    if alerta or inten_num >= 9:
        nivel: Literal["rotina", "breve", "urgente"] = "urgente"
        orientacao = ORIENTACAO_URGENTE
    elif inten_num >= 6 or duracao == "mais_semana":
        nivel = "breve"
        orientacao = (
            "Recomendo agendar uma consulta nos próximos dias. "
            "Se os sintomas piorarem ou surgirem sinais de alerta, procure atendimento antes."
        )
    else:
        nivel = "rotina"
        orientacao = "Escolha abaixo um médico disponível para avaliar seu caso com tranquilidade."

    cg_disponivel = "clinico_geral" in esps_por_id
    escolhidas: list[tuple[str, str]] = []
    foco_clinico = "especialidade"
    resposta = ""

    # Caso A: Especialidade específica clara (ex.: cardiologia, dermatologia, ortopedia, pediatria, ginecologia)
    if pontuadas and (not cenario_match or pontuadas[0][1] >= melhor_score_cen):
        top_regra = pontuadas[0][0]
        escolhidas.append((top_regra["esp"], top_regra["motivo"]))
        # Só adiciona uma segunda especialidade se ela também teve correspondência real no relato
        if len(pontuadas) > 1 and pontuadas[1][1] >= 2:
            segunda = pontuadas[1][0]
            escolhidas.append((segunda["esp"], segunda["motivo"]))

        principal_nome = esps_por_id[top_regra["esp"]].nome
        if nivel == "urgente":
            resposta = (
                f"Atenção: pelo que você relatou, há sinais que merecem avaliação imediata em um "
                f"pronto-socorro (ou pelo SAMU 192). Para acompanhamento ambulatorial após estabilização, "
                f"a especialidade recomendada é {principal_nome}."
            )
        elif resposta_hipotese:
            resposta = (
                f"{resposta_hipotese} Para investigar isso adequadamente, a especialidade indicada "
                f"é {principal_nome}."
            )
        else:
            resposta = top_regra["resposta"]

    # Caso B: Cenário contextual específico (dente, gripe, dor de cabeça, gastro, olhos, mental, check-up)
    elif cenario_match and cg_disponivel:
        foco_clinico = cenario_match["foco"]
        escolhidas.append(("clinico_geral", cenario_match["motivo"]))
        if nivel == "urgente":
            resposta = (
                "Atenção: pela intensidade ou pelos sinais relatados, procure avaliação imediata em um "
                "pronto-socorro (ou ligue 192). Depois, você pode acompanhar o caso com um Clínico Geral."
            )
        elif resposta_hipotese:
            if cenario_match["nome"] == "cefaleia" and "gripe" in txt_atual:
                resposta = (
                    "Pode sim ser somente uma gripe ou um quadro viral leve — dor de cabeça costuma aparecer "
                    "no início desses quadros. Mesmo assim, como também pode envolver sinusite, tensão ou "
                    "outras causas, vale consultar um Clínico Geral para avaliar com calma."
                )
            else:
                resposta = resposta_hipotese
        else:
            resposta = cenario_match["resposta"]
        if nivel != "urgente":
            orientacao = cenario_match["orientacao"]

    # Caso C: Relato aberto / ambíguo / sem correspondência específica -> Clínico Geral
    else:
        foco_clinico = "prevencao" if any(p in txt_combinado for p in ["rotina", "check", "exame"]) else "agudo"
        alvo = esps_por_id.get("clinico_geral") or especialidades[0]
        escolhidas.append(
            (
                alvo.id,
                "Avalia o seu relato de forma ampla, esclarece dúvidas e encaminha para um especialista se precisar.",
            )
        )
        if nivel == "urgente":
            resposta = (
                "Pela gravidade ou intensidade informada, procure um pronto-socorro ou ligue 192 (SAMU) "
                "imediatamente. Para acompanhamento posterior, o Clínico Geral é o primeiro passo."
            )
        elif resposta_hipotese:
            resposta = resposta_hipotese
        else:
            resposta = (
                f"Para avaliar melhor o que você descreveu sem arriscar um palpite impreciso, "
                f"o caminho mais seguro é iniciar com um {alvo.nome}. Ele analisa seu quadro completo "
                f"e direciona o tratamento ou encaminhamento ideal."
            )

    recomendacoes = [
        RecomendacaoOut(
            especialidade=esp_id,
            nome=esps_por_id[esp_id].nome,
            prioridade=idx + 1,
            motivo=motivo,
        )
        for idx, (esp_id, motivo) in enumerate(escolhidas[:2])
    ]

    return (
        TriagemResultadoOut(
            resposta=resposta,
            recomendacoes=recomendacoes,
            nivel_atencao=nivel,
            orientacao=orientacao,
            aviso=AVISO_OBRIGATORIO,
        ),
        foco_clinico,
    )


def _chamar_gemini_sync(
    api_key: str,
    model_name: str,
    descricao: str,
    duracao: str,
    intensidade: int | None,
    detalhes: str,
    historico: list[MensagemHistoricoIn],
    especialidades: list[Especialidade],
) -> _GeminiTriagemPayload:
    from google import genai
    from google.genai import types

    catalogo_texto = "\n".join(
        f'- id: "{e.id}" | nome: "{e.nome}" | descricao: {e.descricao}'
        for e in especialidades
    )
    duracao_legivel = DURACAO_LABELS.get(duracao, duracao)
    intensidade_legivel = f"{intensidade}/10" if intensidade is not None else "não informada"

    historico_texto = "\n".join(
        f"- {'Paciente' if m.de == 'eu' else 'Assistente'}: {m.texto}"
        for m in historico[-6:]
    )

    prompt = (
        "Você é o assistente de pré-triagem prática e humana da clínica CaisMed (Brasil).\n"
        "Entenda o que o paciente relatou ou perguntou (considerando também o histórico recente da conversa) "
        "e responda em português brasileiro claro, natural, direto e variado — NUNCA repita textos genéricos "
        "engessados para assuntos diferentes.\n\n"
        "DIRETRIZES OBRIGATÓRIAS:\n"
        "1. Responda DIRETAMENTE ao ponto específico do paciente (ex.: se ele perguntar 'pode ser somente gripe?', "
        "diga com naturalidade que pode sim ser uma gripe/quadro viral leve, mas que vale consultar um médico para "
        "avaliar e descartar outras causas; se falar de dor de dente, explique que o ideal é um dentista e que, "
        "como a rede não tem odontologia, o Clínico Geral ajuda se houver dor forte, inchaço ou febre).\n"
        "2. NÃO faça interrogatório robótico nem peça formulários ('Entendi, há quanto tempo...?').\n"
        "3. NUNCA dê diagnóstico fechado nem prescreva medicamentos.\n"
        "4. Use EXCLUSIVAMENTE IDs de especialidade da lista abaixo. Quando uma especialidade específica for clara "
        "(ex.: dermatologia, ortopedia, cardiologia, pediatria, ginecologia), recomende apenas ela (não anexe "
        "`clinico_geral` automaticamente em tudo). Quando o relato for genérico, dúvida aberta, sintoma sistêmico "
        "comum (gripe, dor de cabeça, febre, estômago) ou fora da rede (dente, olhos), recomende `clinico_geral`.\n"
        "5. Defina `foco_clinico` como:\n"
        "   - \"agudo\" para sintomas agudos/recentes, febre, gripe, dor de cabeça, dor de dente ou urgências leves;\n"
        "   - \"prevencao\" para check-up, exames de rotina, prevenção ou acompanhamento crônico;\n"
        "   - \"especialidade\" quando a recomendação principal for uma especialidade específica.\n"
        "6. Se houver sinais graves (dor ou aperto no peito, falta de ar, desmaio, sinais de AVC, sangramento "
        "importante ou intensidade >= 9), defina `nivel_atencao` = \"urgente\" e oriente procurar pronto-socorro "
        "ou ligar 192 (SAMU) imediatamente.\n"
        "7. Classifique `nivel_atencao` exatamente como: \"rotina\", \"breve\" ou \"urgente\".\n\n"
        f"ESPECIALIDADES DISPONÍVEIS NA CAISMED:\n{catalogo_texto}\n\n"
        f"HISTÓRICO RECENTE DA CONVERSA:\n{historico_texto or 'Primeira mensagem da conversa'}\n\n"
        "MENSAGEM ATUAL DO PACIENTE:\n"
        f"- Relato/Pergunta: {descricao}\n"
        f"- Duração (se informada): {duracao_legivel}\n"
        f"- Intensidade (se informada): {intensidade_legivel}\n"
        f"- Detalhes adicionais: {detalhes or 'Não informado'}\n"
    )

    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(
        model=model_name,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=_GeminiTriagemPayload,
            temperature=0.35,
        ),
    )

    raw_text = (response.text or "").strip()
    if not raw_text:
        raise ValueError("Resposta vazia do modelo Gemini.")
    return _GeminiTriagemPayload.model_validate(json.loads(raw_text))


def _normalizar_e_aplicar_guardrails(
    ia_payload: _GeminiTriagemPayload,
    descricao: str,
    intensidade: int | None,
    detalhes: str,
    especialidades: list[Especialidade],
) -> tuple[TriagemResultadoOut, str]:
    esps_por_id = {e.id: e for e in especialidades}
    vistas: set[str] = set()
    recomendacoes: list[RecomendacaoOut] = []

    for rec in ia_payload.recomendacoes:
        esp_id = rec.especialidade.strip().lower()
        if esp_id in esps_por_id and esp_id not in vistas:
            vistas.add(esp_id)
            recomendacoes.append(
                RecomendacaoOut(
                    especialidade=esp_id,
                    nome=esps_por_id[esp_id].nome,
                    prioridade=len(recomendacoes) + 1,
                    motivo=rec.motivo.strip(),
                )
            )
        if len(recomendacoes) >= 2:
            break

    if not recomendacoes:
        padrao = esps_por_id.get("clinico_geral") or especialidades[0]
        recomendacoes.append(
            RecomendacaoOut(
                especialidade=padrao.id,
                nome=padrao.nome,
                prioridade=1,
                motivo="Avalia seu quadro de forma completa e encaminha para outro especialista se necessário.",
            )
        )

    nivel = ia_payload.nivel_atencao
    orientacao = ia_payload.orientacao.strip()
    resposta = ia_payload.resposta.strip()

    # Guardrail clínico de segurança: nunca subestimar urgência
    if _tem_sinal_alerta(f"{descricao} {detalhes}") or (intensidade is not None and intensidade >= 9):
        nivel = "urgente"
        if "192" not in orientacao and "pronto-socorro" not in orientacao.lower():
            orientacao = f"{ORIENTACAO_URGENTE} {orientacao}"

    return (
        TriagemResultadoOut(
            resposta=resposta,
            recomendacoes=recomendacoes,
            nivel_atencao=nivel,
            orientacao=orientacao,
            aviso=AVISO_OBRIGATORIO,
        ),
        ia_payload.foco_clinico,
    )


def analisar_triagem(
    *,
    descricao: str,
    duracao: str | None,
    intensidade: int | None,
    detalhes: str,
    historico: list[MensagemHistoricoIn] | None = None,
    especialidades: list[Especialidade],
) -> tuple[TriagemResultadoOut, str, str, int | None, str]:
    """
    Executa a análise de pré-triagem via Google Gemini com timeout rígido e fallback contextual.
    Retorna `(resultado, provedor_utilizado, duracao_normalizada, intensidade_normalizada, foco_clinico)`.
    """
    settings = get_settings()
    hist = list(historico or [])
    duracao_norm, intensidade_norm = inferir_duracao_e_intensidade(
        descricao, detalhes, duracao, intensidade
    )

    if not settings.gemini_configured or not especialidades:
        resultado, foco = _analisar_fallback(
            descricao, duracao_norm, intensidade_norm, detalhes, hist, especialidades
        )
        return resultado, "fallback", duracao_norm, intensidade_norm, foco

    executor = ThreadPoolExecutor(max_workers=1)
    future = executor.submit(
        _chamar_gemini_sync,
        settings.gemini_api_key.strip(),
        settings.gemini_model,
        descricao,
        duracao_norm,
        intensidade_norm,
        detalhes,
        hist,
        especialidades,
    )
    try:
        ia_payload = future.result(timeout=settings.gemini_timeout_seconds)
        resultado, foco = _normalizar_e_aplicar_guardrails(
            ia_payload, descricao, intensidade_norm, detalhes, especialidades
        )
        return resultado, f"gemini:{settings.gemini_model}", duracao_norm, intensidade_norm, foco
    except FuturesTimeoutError:
        logger.warning(
            "Timeout ao chamar Gemini (%.1fs); usando fallback contextual.",
            settings.gemini_timeout_seconds,
        )
        resultado, foco = _analisar_fallback(
            descricao, duracao_norm, intensidade_norm, detalhes, hist, especialidades
        )
        return resultado, "fallback_timeout", duracao_norm, intensidade_norm, foco
    except Exception as exc:
        logger.warning("Erro ao chamar Gemini (%s); usando fallback contextual.", exc)
        resultado, foco = _analisar_fallback(
            descricao, duracao_norm, intensidade_norm, detalhes, hist, especialidades
        )
        return resultado, "fallback_error", duracao_norm, intensidade_norm, foco
    finally:
        executor.shutdown(wait=False, cancel_futures=True)

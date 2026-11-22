"""Comandos que conversam com o arquivo de notícias: /perguntar (RAG) e /semana (ranking de assuntos).

RAG aqui é simples e leve, pensado para uma máquina de 1 GB:
  1. busca de texto (SQLite FTS5) acha as notícias guardadas mais parecidas com a pergunta;
  2. a IA responde usando SÓ essas notícias, citando cada uma pelo número.
"""
from __future__ import annotations

import logging
import re
from collections import Counter
from datetime import datetime
from html import escape

from gamebot import ia
from gamebot.banco import Banco, Registro, buscar, recentes, vetores_recentes
from gamebot.filtros import normalizar
from gamebot.sources import pagina

log = logging.getLogger(__name__)

# Palavras de pergunta que não ajudam a achar notícia
_PERGUNTA = {
    "que", "qual", "quais", "quando", "como", "onde", "quem", "porque", "por", "sobre", "saiu", "sairam",
    "teve", "tem", "tiveram", "algo", "alguma", "algum", "novidade", "novidades", "noticia", "noticias",
    "essa", "esse", "esta", "este", "semana", "hoje", "ontem", "mes", "ultimos", "ultimas", "dias",
    "mim", "me", "fala", "conta", "falar", "jogo", "jogos", "game", "games", "sao", "foi", "vai", "ser",
    "mais", "muito", "pra", "nas", "nos", "uma", "uns", "umas", "boa", "bom", "boas",
}

# Palavras comuns em títulos que não são assunto (para o ranking sem IA)
_GENERICAS = {
    "com", "sem", "mas", "por", "ate", "ano", "anos", "novo", "nova", "novos", "novas", "diz", "faz",
    "the", "and", "for", "new", "now", "out", "get", "gets", "has", "its", "you", "your", "how", "why",
    "anuncia", "anunciado", "recebe", "chega", "ganha", "lancamento", "trailer", "update", "atualizacao",
}

SISTEMA_PERGUNTA = (
    "Você é o assistente do bot Resumo Gamer. Responda em português do Brasil, de forma curta e direta "
    "(no máximo 6 frases), usando SOMENTE as notícias numeradas fornecidas e os trechos das matérias, "
    "quando houver. Não copie frases inteiras das matérias: explique com suas palavras. Cite as notícias pelo número "
    "entre colchetes, por exemplo [1] ou [2][3]. Se as notícias não responderem à pergunta, diga isso "
    "claramente e não invente nada. Não use markdown, só texto simples."
)

SISTEMA_SEMANA = (
    "Você agrupa notícias de games por assunto. Junte notícias que falam do mesmo jogo, empresa ou evento. "
    "Devolva no máximo 6 assuntos, do que mais aparece para o que menos aparece, ignorando assuntos com uma "
    'única notícia se houver outros maiores. Responda SOMENTE com JSON no formato {"assuntos": '
    '[{"assunto": "nome curto", "ids": [0, 3, 5]}]}.'
)


def consulta_fts(pergunta: str) -> str:
    """Transforma a pergunta numa busca FTS5: palavras relevantes, com prefixo, unidas por OR."""
    palavras = [p for p in normalizar(pergunta).split() if p not in _PERGUNTA and (len(p) >= 3 or p.isdigit())]
    vistas = list(dict.fromkeys(palavras))[:8]
    return " OR ".join(f'"{p}"*' for p in vistas)


def _fontes(registros: list[Registro], textos: dict[int, str] | None = None) -> str:
    textos = textos or {}
    linhas = []
    for i, r in enumerate(registros, 1):
        linha = f"[{i}] {r.titulo} — {r.resumo} ({r.fonte}, {r.data[:10]})"
        if textos.get(i):
            linha += f"\nTrecho da matéria [{i}]:\n{textos[i]}"
        linhas.append(linha)
    return "\n\n".join(linhas)


def _links(registros: list[Registro], numeros: list[int] | None = None) -> str:
    usados = numeros or list(range(1, len(registros) + 1))
    return "\n".join(
        f'[{i}] <a href="{escape(registros[i - 1].link, quote=True)}">{escape(registros[i - 1].titulo)}</a> · '
        f"<i>{escape(registros[i - 1].fonte)}</i>"
        for i in usados if 1 <= i <= len(registros)
    )


def busca_hibrida(pergunta: str, banco: Banco, embeddings: list[ia.Provedor] | None,
                  dias: int = 30, limite: int = 8) -> list[Registro]:
    """Junta a busca por palavras (FTS5) com a busca por significado (embeddings), alternando os resultados."""
    por_palavra = buscar(banco, consulta_fts(pergunta), dias=dias, limite=limite)
    por_significado: list[Registro] = []
    gerado = ia.vetorizar([pergunta], embeddings) if embeddings else None
    if gerado:
        modelo, (vetor,) = gerado
        candidatos = vetores_recentes(banco, modelo, dias)
        notas = sorted(((ia.cosseno(vetor, v), r) for r, v in candidatos), key=lambda x: x[0], reverse=True)
        por_significado = [r for nota, r in notas[:limite] if nota >= 0.5]
    juntos, vistos = [], set()
    for par in zip(por_palavra + [None] * limite, por_significado + [None] * limite, strict=False):
        for r in par:
            if r and r.link not in vistos:
                vistos.add(r.link)
                juntos.append(r)
    return juntos[:limite]


def perguntar(pergunta: str, banco: Banco, provedores: list[ia.Provedor], dias: int = 30,
              ler_materia=None, materias: int = 3, embeddings: list[ia.Provedor] | None = None) -> str:
    pergunta = pergunta.strip()
    if not pergunta:
        return "Escreva a pergunta depois do comando. Exemplo:\n/perguntar o que saiu de GTA 6 essa semana?"

    registros = busca_hibrida(pergunta, banco, embeddings, dias=dias)
    if not registros:
        return (f"🔎 Não achei nada sobre isso nas notícias dos últimos {dias} dias.\n"
                "Tente outras palavras, como o nome do jogo ou da empresa.")

    # Lê na hora o texto das matérias mais relevantes (sob demanda: só quando alguém pergunta)
    ler_materia = ler_materia or pagina.ler
    textos = {i: ler_materia(r.link) for i, r in enumerate(registros[:materias], 1)} if materias else {}
    try:
        resposta = ia.completar(provedores, SISTEMA_PERGUNTA,
                                f"Notícias:\n{_fontes(registros, textos)}\n\nPergunta: {pergunta}")
    except ia.FalhaIA as erro:
        log.warning("Sem IA para o /perguntar: %s", erro)
        return f"🔎 A IA não respondeu agora, mas achei estas notícias:\n\n{_links(registros)}"

    citadas = sorted({int(n) for n in re.findall(r"\[(\d+)\]", resposta)})
    citadas = [n for n in citadas if 1 <= n <= len(registros)] or list(range(1, min(len(registros), 3) + 1))
    return f"💬 {escape(resposta)}\n\n<b>Fontes</b>\n{_links(registros, citadas)}"


def _ranking_simples(registros: list[Registro]) -> list[tuple[str, list[int]]]:
    """Sem IA: as palavras que mais se repetem nos títulos viram os 'assuntos'."""
    contagem: Counter[str] = Counter()
    onde: dict[str, list[int]] = {}
    for i, r in enumerate(registros):
        for p in set(normalizar(r.titulo).split()):
            if len(p) >= 3 and not p.isdigit() and p not in _PERGUNTA and p not in _GENERICAS:
                contagem[p] += 1
                onde.setdefault(p, []).append(i)
    return [(p.upper() if len(p) <= 4 else p.capitalize(), onde[p]) for p, n in contagem.most_common(6) if n >= 2]


def semana(banco: Banco, provedores: list[ia.Provedor], dias: int = 7, agora: datetime | None = None) -> str:
    todos = recentes(banco, dias=dias, limite=5000)
    # A IA recebe uma amostra espalhada pela semana inteira (no máximo 150 títulos, para caber no plano grátis)
    passo = max(1, -(-len(todos) // 150))
    registros = todos[::passo][:150]
    if len(registros) < 2:
        return "📊 Ainda tenho poucas notícias guardadas para montar o ranking. Volte depois de alguns resumos."

    assuntos: list[tuple[str, list[int]]] = []
    try:
        titulos = "\n".join(f"{i}: {r.titulo}" for i, r in enumerate(registros))
        dados = ia._extrair_json(ia.completar(provedores, SISTEMA_SEMANA, titulos, temperatura=0.1))
        for a in dados.get("assuntos", [])[:6]:
            ids = [int(i) for i in a.get("ids", []) if 0 <= int(i) < len(registros)]
            if a.get("assunto") and ids:
                assuntos.append((str(a["assunto"]), list(dict.fromkeys(ids))))
    except (ia.FalhaIA, ValueError, TypeError, AttributeError) as erro:
        log.warning("Ranking sem IA: %s", erro)

    if not assuntos:
        assuntos = _ranking_simples(registros)
    if not assuntos:
        return "📊 Nenhum assunto se repetiu o bastante nesta semana para montar um ranking."

    assuntos.sort(key=lambda a: len(a[1]), reverse=True)
    medalhas = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣", "6️⃣"]
    amostra = f", amostra de {len(registros)}" if len(registros) < len(todos) else ""
    partes = [f"<b>📊 Assuntos da semana</b> ({len(todos)} notícias guardadas{amostra})"]
    for pos, (assunto, ids) in enumerate(assuntos):
        fontes = {registros[i].fonte for i in ids}
        destaque = registros[ids[0]]
        partes.append(
            f"{medalhas[pos]} <b>{escape(assunto)}</b> · {len(ids)} notícia(s) em {len(fontes)} site(s)\n"
            f'<a href="{escape(destaque.link, quote=True)}">{escape(destaque.titulo)}</a>'
        )
    partes.append("<i>Dica: os primeiros da lista são bons candidatos para vídeo.</i>")
    return "\n\n".join(partes)


SISTEMA_ROTEIRO = (
    "Você ajuda um criador a preparar um vídeo curto para o YouTube sobre as notícias de games da semana. "
    "Escreva em português do Brasil, em tom de conversa, um RASCUNHO de roteiro de 3 a 5 minutos com: "
    "ABERTURA (1 a 2 frases), de 3 a 5 NOTÍCIAS escolhidas entre os assuntos que mais aparecem na lista "
    "(cada uma com um título curto e 2 a 3 frases de fala), PROMOÇÃO DA SEMANA (se houver promoções na "
    "lista) e ENCERRAMENTO com uma chamada para comentar. Use SOMENTE as informações fornecidas, explique "
    "com suas palavras e cite a notícia usada pelo número entre colchetes, por exemplo [4]. "
    "Não use markdown; separe as partes com linhas em branco e escreva o nome de cada parte em MAIÚSCULAS."
)


def roteiro(banco: Banco, provedores: list[ia.Provedor], promocoes=None, dias: int = 7) -> str:
    """Rascunho de roteiro de vídeo com a semana (1 chamada de IA)."""
    todos = recentes(banco, dias=dias, limite=5000)
    passo = max(1, -(-len(todos) // 120))
    registros = todos[::passo][:120]
    if len(registros) < 3:
        return "🎬 Ainda tenho poucas notícias guardadas para um roteiro. Volte depois de alguns resumos."

    lista = "\n".join(f"[{i}] {r.titulo} ({r.fonte})" for i, r in enumerate(registros, 1))
    ofertas = ""
    if promocoes:
        ofertas = "\n\nPromoções:\n" + "\n".join(
            f"- {p.jogo}: {'grátis' if p.gratis else f'-{p.desconto}% por US$ {p.preco_promocional:.2f}'} na {p.loja}"
            for p in promocoes[:5])
    try:
        texto = ia.completar(provedores, SISTEMA_ROTEIRO, f"Notícias da semana:\n{lista}{ofertas}",
                             temperatura=0.6, timeout=90)
    except ia.FalhaIA as erro:
        log.warning("Sem IA para o /roteiro: %s", erro)
        return "🎬 A IA não respondeu agora. Tente o /roteiro de novo daqui a pouco."

    citadas = sorted({int(n) for n in re.findall(r"\[(\d+)\]", texto) if 1 <= int(n) <= len(registros)})
    rodape = ("\n\n<b>Fontes para citar no vídeo</b>\n" + _links(registros, citadas)) if citadas else ""
    return (f"🎬 <b>Rascunho de roteiro</b> (revise e fale com as suas palavras)\n\n{escape(texto)}{rodape}")

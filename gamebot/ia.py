"""Tradução das notícias para português com IA.

Usa qualquer provedor compatível com a API de chat da OpenAI (/chat/completions).
Tenta os provedores na ordem do config.yaml, pula os que não têm chave e,
se todos falharem, devolve as notícias como vieram (em inglês).
"""
from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, replace

import requests

from gamebot.models import Noticia

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Provedor:
    nome: str
    url: str
    modelo: str
    variavel_chave: str  # nome da variável de ambiente / secret do GitHub

    @property
    def chave(self) -> str:
        return os.getenv(self.variavel_chave, "").strip()


# Valores padrão. Endereço, modelo e ordem podem ser trocados no config.yaml.
PADRAO: dict[str, Provedor] = {
    "openrouter": Provedor("openrouter", "https://openrouter.ai/api/v1/chat/completions",
                           "openrouter/free", "OPENROUTER_API_KEY"),
    "groq": Provedor("groq", "https://api.groq.com/openai/v1/chat/completions",
                     "llama-3.3-70b-versatile", "GROQ_API_KEY"),
    "gemini": Provedor("gemini", "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
                       "gemini-2.5-flash", "GEMINI_API_KEY"),
    "sambanova": Provedor("sambanova", "https://api.sambanova.ai/v1/chat/completions",
                          "Meta-Llama-3.3-70B-Instruct", "SAMBANOVA_API_KEY"),
}

INSTRUCAO = (
    "Você traduz notícias de games do inglês para o português do Brasil. "
    "Para cada item, devolva um título em português natural, como um site brasileiro de games escreveria, "
    "e um resumo de no máximo uma frase curta. Mantenha em inglês nomes de jogos, empresas, consoles e "
    "termos que os jogadores brasileiros usam em inglês (patch, DLC, Game Pass, remake). "
    "Não invente informações que não estejam no título ou no resumo original. "
    'Responda SOMENTE com JSON no formato {"itens": [{"id": 0, "titulo": "...", "resumo": "..."}]}, '
    "com um item para cada id recebido."
)


class FalhaIA(RuntimeError):
    pass


def montar_provedores(config: dict | None) -> list[Provedor]:
    """Lê a seção 'ia' do config.yaml e devolve os provedores na ordem de uso."""
    config = config or {}
    provedores = []
    for nome in config.get("provedores", list(PADRAO)):
        base = PADRAO.get(nome)
        extra = (config.get("modelos") or {}).get(nome) or {}
        if isinstance(extra, str):
            extra = {"modelo": extra}
        if not base and not extra.get("url"):
            log.warning("Provedor de IA desconhecido: %s", nome)
            continue
        provedores.append(Provedor(
            nome=nome,
            url=extra.get("url", base.url if base else ""),
            modelo=extra.get("modelo", base.modelo if base else ""),
            variavel_chave=extra.get("chave", base.variavel_chave if base else f"{nome.upper()}_API_KEY"),
        ))
    return provedores


def _extrair_json(texto: str) -> dict:
    """Aceita JSON puro ou dentro de ```json ... ```, como alguns modelos respondem."""
    texto = texto.strip()
    cerca = re.search(r"```(?:json)?\s*(.*?)```", texto, re.DOTALL)
    if cerca:
        texto = cerca.group(1)
    inicio, fim = texto.find("{"), texto.rfind("}")
    if inicio < 0 or fim < 0:
        raise FalhaIA("resposta sem JSON")
    return json.loads(texto[inicio : fim + 1])


def _chamar(provedor: Provedor, itens: list[dict], sessao: requests.Session, timeout: int) -> dict[int, dict]:
    resp = sessao.post(
        provedor.url,
        timeout=timeout,
        headers={
            "Authorization": f"Bearer {provedor.chave}",
            "Content-Type": "application/json",
            # Identificação recomendada pelo OpenRouter; os outros ignoram
            "HTTP-Referer": "https://github.com/Ericklevy/game-news-bot",
            "X-Title": "game-news-bot",
        },
        json={
            "model": provedor.modelo,
            "temperature": 0.2,
            "messages": [
                {"role": "system", "content": INSTRUCAO},
                {"role": "user", "content": json.dumps({"itens": itens}, ensure_ascii=False)},
            ],
        },
    )
    if resp.status_code != 200:
        # Só o código e o começo da mensagem: nunca a chave
        raise FalhaIA(f"HTTP {resp.status_code}: {resp.text[:160]}")
    try:
        conteudo = resp.json()["choices"][0]["message"]["content"] or ""
        dados = _extrair_json(conteudo)
        traduzidos = {int(i["id"]): i for i in dados["itens"]}
    except (KeyError, IndexError, TypeError, ValueError) as erro:
        raise FalhaIA(f"resposta em formato inesperado ({erro})") from erro
    faltando = {i["id"] for i in itens} - set(traduzidos)
    if faltando:
        raise FalhaIA(f"faltaram {len(faltando)} itens na resposta")
    return traduzidos


def traduzir(noticias: list[Noticia], provedores: list[Provedor],
             sessao: requests.Session | None = None, timeout: int = 60) -> list[Noticia]:
    """Traduz títulos e resumos numa única chamada. Em caso de falha, devolve as originais."""
    if not noticias:
        return noticias
    disponiveis = [p for p in provedores if p.chave]
    if not disponiveis:
        log.info("IA: nenhuma chave configurada, resumo sai em inglês")
        return noticias

    sessao = sessao or requests.Session()
    itens = [{"id": i, "titulo": n.titulo, "resumo": n.resumo[:280]} for i, n in enumerate(noticias)]
    for provedor in disponiveis:
        try:
            traduzidos = _chamar(provedor, itens, sessao, timeout)
        except (FalhaIA, requests.RequestException) as erro:
            log.warning("IA %s falhou: %s", provedor.nome, erro)
            continue
        log.info("IA: %d notícias traduzidas por %s (%s)", len(noticias), provedor.nome, provedor.modelo)
        return [
            replace(n,
                    titulo=(traduzidos[i].get("titulo") or n.titulo).strip(),
                    resumo=(traduzidos[i].get("resumo") or "").strip(),
                    traduzida=True)
            for i, n in enumerate(noticias)
        ]
    log.warning("IA: todos os provedores falharam, resumo sai em inglês")
    return noticias


def _conversar(provedor: Provedor, sistema: str, usuario: str, sessao: requests.Session,
               timeout: int, temperatura: float) -> str:
    resp = sessao.post(
        provedor.url,
        timeout=timeout,
        headers={
            "Authorization": f"Bearer {provedor.chave}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/Ericklevy/game-news-bot",
            "X-Title": "game-news-bot",
        },
        json={
            "model": provedor.modelo,
            "temperature": temperatura,
            "messages": [{"role": "system", "content": sistema}, {"role": "user", "content": usuario}],
        },
    )
    if resp.status_code != 200:
        raise FalhaIA(f"HTTP {resp.status_code}: {resp.text[:160]}")
    try:
        texto = (resp.json()["choices"][0]["message"]["content"] or "").strip()
    except (KeyError, IndexError, TypeError, ValueError) as erro:
        raise FalhaIA(f"resposta em formato inesperado ({erro})") from erro
    if not texto:
        raise FalhaIA("resposta vazia")
    return texto


def completar(provedores: list[Provedor], sistema: str, usuario: str,
              sessao: requests.Session | None = None, timeout: int = 60,
              temperatura: float = 0.3) -> str:
    """Pergunta livre para a IA, com a mesma fila de provedores da tradução.

    Levanta FalhaIA se nenhum provedor responder.
    """
    disponiveis = [p for p in provedores if p.chave]
    if not disponiveis:
        raise FalhaIA("nenhuma chave de IA configurada")
    sessao = sessao or requests.Session()
    for provedor in disponiveis:
        try:
            texto = _conversar(provedor, sistema, usuario, sessao, timeout, temperatura)
        except (FalhaIA, requests.RequestException) as erro:
            log.warning("IA %s falhou: %s", provedor.nome, erro)
            continue
        log.info("IA: resposta de %s (%s)", provedor.nome, provedor.modelo)
        return texto
    raise FalhaIA("todos os provedores falharam")


# ---------- embeddings (busca por significado) ----------

EMBEDDINGS_PADRAO = {"gemini": "gemini-embedding-001"}


def montar_embeddings(config: dict | None) -> list[Provedor]:
    """Provedores de embeddings, da seção ia.embeddings do config.yaml. Vazio = desligado."""
    emb = (config or {}).get("embeddings") or {}
    if not emb.get("ativo", False):
        return []
    provedores = []
    for nome in emb.get("provedores", ["gemini"]):
        base = PADRAO.get(nome)
        modelo = (emb.get("modelos") or {}).get(nome) or EMBEDDINGS_PADRAO.get(nome)
        if not base or not modelo:
            log.warning("Embeddings: provedor %s sem modelo configurado", nome)
            continue
        provedores.append(Provedor(nome, base.url.replace("chat/completions", "embeddings"), modelo, base.variavel_chave))
    return provedores


def vetorizar(textos: list[str], provedores: list[Provedor], sessao: requests.Session | None = None,
              timeout: int = 60) -> tuple[str, list[list[float]]] | None:
    """Gera um vetor por texto (formato /embeddings da OpenAI). Devolve (modelo, vetores) ou None."""
    disponiveis = [p for p in provedores if p.chave]
    if not textos or not disponiveis:
        return None
    sessao = sessao or requests.Session()
    for p in disponiveis:
        try:
            resp = sessao.post(p.url, timeout=timeout,
                               headers={"Authorization": f"Bearer {p.chave}", "Content-Type": "application/json"},
                               json={"model": p.modelo, "input": textos})
            if resp.status_code != 200:
                raise FalhaIA(f"HTTP {resp.status_code}: {resp.text[:160]}")
            dados = sorted(resp.json()["data"], key=lambda d: d.get("index", 0))
            vetores = [d["embedding"] for d in dados]
            if len(vetores) != len(textos):
                raise FalhaIA("quantidade de vetores diferente da de textos")
        except (FalhaIA, requests.RequestException, KeyError, TypeError, ValueError) as erro:
            log.warning("Embeddings %s falharam: %s", p.nome, erro)
            continue
        return f"{p.nome}/{p.modelo}", vetores
    return None


def cosseno(a: list[float], b: list[float]) -> float:
    num = sum(x * y for x, y in zip(a, b, strict=False))
    den = (sum(x * x for x in a) ** 0.5) * (sum(y * y for y in b) ** 0.5)
    return num / den if den else 0.0

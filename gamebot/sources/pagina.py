"""Lê o texto principal de uma matéria (só os parágrafos), para o /perguntar responder com mais detalhe.

O texto é usado apenas como contexto para a IA e não é republicado.
"""
from __future__ import annotations

import logging
import re
from html.parser import HTMLParser

import requests

log = logging.getLogger(__name__)
HEADERS = {"User-Agent": "game-news-bot/1.0 (+https://github.com/Ericklevy/game-news-bot)"}
_IGNORAR = {"script", "style", "nav", "header", "footer", "aside", "form", "figcaption", "noscript"}


class _Paragrafos(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.paragrafos: list[str] = []
        self._dentro_p = 0
        self._ignorando = 0
        self._atual: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag in _IGNORAR:
            self._ignorando += 1
        elif tag == "p" and not self._ignorando:
            self._dentro_p += 1
            self._atual = []

    def handle_endtag(self, tag):
        if tag in _IGNORAR and self._ignorando:
            self._ignorando -= 1
        elif tag == "p" and self._dentro_p:
            self._dentro_p -= 1
            texto = " ".join("".join(self._atual).split())
            if len(texto) >= 60:                 # descarta legendas, créditos e botões
                self.paragrafos.append(texto)

    def handle_data(self, data):
        if self._dentro_p and not self._ignorando:
            self._atual.append(data)


def extrair_texto(html: str, limite: int = 2500) -> str:
    leitor = _Paragrafos()
    leitor.feed(html)
    texto = "\n".join(leitor.paragrafos)
    texto = re.sub(r"\s+\n", "\n", texto).strip()
    return texto if len(texto) <= limite else texto[:limite].rsplit(" ", 1)[0] + "…"


def ler(url: str, sessao: requests.Session | None = None, timeout: int = 10, limite: int = 2500) -> str:
    """Baixa a página e devolve os parágrafos. Qualquer falha vira texto vazio."""
    sessao = sessao or requests.Session()
    try:
        resp = sessao.get(url, headers=HEADERS, timeout=timeout)
        if resp.status_code != 200 or "html" not in resp.headers.get("content-type", ""):
            log.info("Página %s não lida (HTTP %s)", url, resp.status_code)
            return ""
        return extrair_texto(resp.text, limite)
    except requests.RequestException as erro:
        log.info("Página %s não lida: %s", url, erro)
        return ""

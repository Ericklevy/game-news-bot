"""Coleta notícias de feeds RSS/Atom."""
from __future__ import annotations

import html
import logging
import re
from datetime import datetime, timezone

import feedparser

from gamebot.models import Noticia
from gamebot.plataformas import detectar

log = logging.getLogger(__name__)
_TAGS = re.compile(r"<[^>]+>")


def _limpar(texto: str, limite: int = 280) -> str:
    texto = html.unescape(_TAGS.sub(" ", texto or ""))
    texto = " ".join(texto.split())
    return texto if len(texto) <= limite else texto[: limite - 1].rstrip() + "…"


def _data(entrada) -> datetime | None:
    struct = entrada.get("published_parsed") or entrada.get("updated_parsed")
    if not struct:
        return None
    return datetime(*struct[:6], tzinfo=timezone.utc)


def ler_feed(nome: str, url_ou_xml: str) -> list[Noticia]:
    """Lê um feed (URL ou conteúdo XML). Falhas viram lista vazia e um aviso no log."""
    feed = feedparser.parse(url_ou_xml, agent="game-news-bot/1.0 (+https://github.com/Ericklevy/game-news-bot)")
    if feed.bozo and not feed.entries:
        log.warning("Feed %s indisponível: %s", nome, feed.get("bozo_exception"))
        return []

    noticias = []
    for e in feed.entries:
        titulo, link = _limpar(e.get("title", ""), 200), e.get("link", "")
        if not titulo or not link:
            continue
        resumo = _limpar(e.get("summary", ""))
        noticias.append(Noticia(
            titulo=titulo,
            link=link,
            fonte=nome,
            publicada_em=_data(e),
            resumo=resumo,
            plataformas=detectar(f"{titulo} {resumo}"),
        ))
    log.info("Feed %s: %d notícias", nome, len(noticias))
    return noticias

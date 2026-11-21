"""Filtros: plataformas de interesse, palavras bloqueadas e notícias repetidas."""
from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable
from difflib import SequenceMatcher

from gamebot.models import Noticia

_PALAVRAS_VAZIAS = {
    "the", "a", "an", "of", "to", "in", "and", "for", "on", "is", "with", "at", "its", "it's",
    "o", "a", "os", "as", "de", "do", "da", "dos", "das", "e", "em", "no", "na", "para", "com", "um", "uma",
}


def normalizar(titulo: str) -> str:
    """Título em minúsculas, sem acentos, pontuação e palavras vazias."""
    t = unicodedata.normalize("NFKD", titulo.lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    palavras = re.findall(r"[a-z0-9]+", t)
    return " ".join(p for p in palavras if p not in _PALAVRAS_VAZIAS)


def parecidos(a: str, b: str, limiar: float = 0.72) -> bool:
    """Dois títulos falam do mesmo assunto? Compara o texto e as palavras em comum."""
    na, nb = normalizar(a), normalizar(b)
    if not na or not nb:
        return False
    if SequenceMatcher(None, na, nb).ratio() >= limiar:
        return True
    pa, pb = set(na.split()), set(nb.split())
    return len(pa & pb) / min(len(pa), len(pb)) >= 0.8


def sem_repetidas(noticias: Iterable[Noticia]) -> list[Noticia]:
    """Remove links repetidos e o mesmo assunto publicado por sites diferentes (fica o primeiro)."""
    escolhidas: list[Noticia] = []
    links: set[str] = set()
    for n in noticias:
        if n.link in links or any(parecidos(n.titulo, e.titulo) for e in escolhidas):
            continue
        links.add(n.link)
        escolhidas.append(n)
    return escolhidas


def por_plataforma(noticias: Iterable[Noticia], plataformas: set[str], incluir_gerais: bool = True) -> list[Noticia]:
    """Mantém notícias das plataformas escolhidas. Notícias sem plataforma são 'gerais'."""
    resultado = []
    for n in noticias:
        if not n.plataformas:
            if incluir_gerais:
                resultado.append(n)
        elif n.plataformas & plataformas:
            resultado.append(n)
    return resultado


def sem_bloqueadas(noticias: Iterable[Noticia], bloqueadas: Iterable[str]) -> list[Noticia]:
    """Tira notícias com palavras que você não quer ver (ex.: filmes, séries)."""
    termos = [normalizar(b) for b in bloqueadas if b.strip()]
    return [n for n in noticias if not any(t and t in normalizar(n.titulo) for t in termos)]

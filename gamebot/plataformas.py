"""Detecta de quais plataformas uma notícia fala, a partir do texto."""
from __future__ import annotations

import re

# Palavras que indicam cada plataforma. A busca ignora maiúsculas.
PALAVRAS: dict[str, tuple[str, ...]] = {
    "PlayStation": ("playstation", "ps5", "ps4", "ps plus", "psn", "sony interactive", "dualsense"),
    "Xbox": ("xbox", "game pass", "series x", "series s"),
    "Nintendo": ("nintendo", "switch 2", "switch", "zelda", "mario", "pokémon", "pokemon"),
    "PC": ("pc", "steam", "epic games store", "gog", "windows"),
}

_PADROES = {
    plataforma: re.compile(r"\b(" + "|".join(re.escape(p) for p in palavras) + r")\b", re.IGNORECASE)
    for plataforma, palavras in PALAVRAS.items()
}


def detectar(texto: str) -> frozenset[str]:
    """Retorna as plataformas citadas no texto. Vazio significa notícia geral."""
    return frozenset(p for p, padrao in _PADROES.items() if padrao.search(texto or ""))

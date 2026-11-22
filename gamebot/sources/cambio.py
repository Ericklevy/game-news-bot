"""Cotação do dólar em reais pela API pública Frankfurter (sem chave).

Documentação: https://frankfurter.dev/v1/
"""
from __future__ import annotations

import logging

import requests

log = logging.getLogger(__name__)
URL = "https://api.frankfurter.dev/v1/latest"
HEADERS = {"User-Agent": "game-news-bot/1.0 (+https://github.com/Ericklevy/game-news-bot)"}


def dolar_em_reais(sessao: requests.Session | None = None, timeout: int = 15) -> float | None:
    """Quantos reais vale 1 dólar hoje. Devolve None se a API falhar."""
    sessao = sessao or requests.Session()
    resp = sessao.get(URL, params={"base": "USD", "symbols": "BRL"}, headers=HEADERS, timeout=timeout)
    resp.raise_for_status()
    taxa = float(resp.json()["rates"]["BRL"])
    if not 1 < taxa < 20:          # proteção contra resposta estranha
        raise ValueError(f"cotação fora do esperado: {taxa}")
    return taxa

"""Jogos e DLCs grátis por tempo limitado, pela API pública da GamerPower (sem chave).

A GamerPower pede crédito: o resumo mostra "via GamerPower" na seção.
Documentação: https://www.gamerpower.com/api-read
"""
from __future__ import annotations

import logging

import requests

from gamebot.models import Gratis

log = logging.getLogger(__name__)
URL = "https://www.gamerpower.com/api/giveaways"
HEADERS = {"User-Agent": "game-news-bot/1.0 (+https://github.com/Ericklevy/game-news-bot)"}


def buscar(tipo: str = "game", limite: int = 5, sessao: requests.Session | None = None,
           timeout: int = 20) -> list[Gratis]:
    """Sorteios ativos do tipo pedido, dos mais populares para os menos. Sem sorteios = lista vazia."""
    sessao = sessao or requests.Session()
    resp = sessao.get(URL, params={"type": tipo, "sort-by": "popularity"}, headers=HEADERS, timeout=timeout)
    if resp.status_code == 201:      # a API responde 201 com um aviso quando não há nada ativo
        return []
    resp.raise_for_status()
    dados = resp.json()
    if not isinstance(dados, list):
        return []

    gratis = []
    for item in dados:
        if item.get("status", "Active") != "Active":
            continue
        try:
            fim = item.get("end_date") or "N/A"
            gratis.append(Gratis(
                titulo=item["title"],
                link=item.get("open_giveaway_url") or item["gamerpower_url"],
                plataformas=item.get("platforms", ""),
                tipo=item.get("type", ""),
                valor="" if item.get("worth") in (None, "N/A") else item["worth"],
                termina_em=None if fim == "N/A" else fim[:10],
            ))
        except KeyError:
            continue
        if len(gratis) >= limite:
            break
    return gratis

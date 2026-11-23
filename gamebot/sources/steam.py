"""Promoções direto da loja Steam, pelo endpoint público featuredcategories (sem chave).

Os preços vêm em dólar (cc=us), a mesma moeda da CheapShark, para que a conversão
para reais e a formatação do resumo funcionem igual nas duas fontes.

Esse endpoint não é documentado oficialmente pela Valve, então pode mudar sem aviso.
Se falhar, o bot segue só com as promoções da CheapShark.
"""
from __future__ import annotations

import logging
import re

import requests

from gamebot.models import Promocao

log = logging.getLogger(__name__)

API = "https://store.steampowered.com/api/featuredcategories/"
LINK_LOJA = "https://store.steampowered.com/app/{}"
TIMEOUT = 20
HEADERS = {"User-Agent": "game-news-bot/1.0 (+https://github.com/Ericklevy/game-news-bot)"}


def buscar(desconto_minimo: int = 50, sessao: requests.Session | None = None) -> list[Promocao]:
    """Promoções da seção 'specials' da Steam, com desconto mínimo. Falha vira lista vazia."""
    sessao = sessao or requests.Session()
    try:
        resp = sessao.get(API, params={"cc": "us", "l": "english"}, headers=HEADERS, timeout=TIMEOUT)
        resp.raise_for_status()
        itens = (resp.json().get("specials") or {}).get("items") or []
    except (requests.RequestException, ValueError, AttributeError) as erro:
        log.warning("Promoções da Steam indisponíveis: %s", erro)
        return []

    promocoes = []
    for item in itens:
        try:
            if not item.get("discounted"):
                continue
            p = Promocao(
                jogo=item["name"],
                loja="Steam",
                preco_normal=int(item["original_price"]) / 100,      # a Steam informa em centavos
                preco_promocional=int(item["final_price"]) / 100,
                link=LINK_LOJA.format(item["id"]),
            )
        except (KeyError, TypeError, ValueError):
            continue
        if p.desconto >= desconto_minimo:
            promocoes.append(p)
    log.info("Promoções Steam: %d com %d%%+ de desconto", len(promocoes), desconto_minimo)
    return promocoes


def _chave(nome: str) -> str:
    return re.sub(r"[^a-z0-9]", "", nome.lower())


def sem_duplicadas(principais: list[Promocao], extras: list[Promocao]) -> list[Promocao]:
    """Junta as duas listas. Se o mesmo jogo aparecer nas duas, fica o da fonte principal."""
    vistos = {_chave(p.jogo) for p in principais}
    return principais + [p for p in extras if _chave(p.jogo) not in vistos]

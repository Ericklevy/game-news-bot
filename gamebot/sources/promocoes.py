"""Coleta promoções de jogos de PC pela API pública da CheapShark.

Documentação: https://apidocs.cheapshark.com/
"""
from __future__ import annotations

import logging

import requests

from gamebot.models import Promocao

log = logging.getLogger(__name__)

API = "https://www.cheapshark.com/api/1.0"
LINK_OFERTA = "https://www.cheapshark.com/redirect?dealID={}"
TIMEOUT = 20


def lojas(sessao: requests.Session) -> dict[str, str]:
    """Mapa storeID -> nome da loja (Steam, GOG, Epic...)."""
    resp = sessao.get(f"{API}/stores", timeout=TIMEOUT)
    resp.raise_for_status()
    return {s["storeID"]: s["storeName"] for s in resp.json() if s.get("isActive", 1)}


def buscar(desconto_minimo: int = 50, nota_minima: int = 70, limite: int = 30,
           sessao: requests.Session | None = None) -> list[Promocao]:
    """Busca ofertas com desconto alto, ordenadas pela melhor relação preço/qualidade.

    Se a API estiver fora do ar, devolve lista vazia: o resumo sai só com as notícias.
    """
    sessao = sessao or requests.Session()
    try:
        nomes_lojas = lojas(sessao)
        resp = sessao.get(f"{API}/deals", timeout=TIMEOUT, params={
            "sortBy": "Deal Rating",
            "pageSize": limite,
            "onSale": 1,
            "metacritic": nota_minima,
        })
        resp.raise_for_status()
        ofertas = resp.json()
    except (requests.RequestException, ValueError) as erro:
        log.warning("Promoções indisponíveis: %s", erro)
        return []

    promocoes = []
    for o in ofertas:
        try:
            p = Promocao(
                jogo=o["title"],
                loja=nomes_lojas.get(o["storeID"], "Loja"),
                preco_normal=float(o["normalPrice"]),
                preco_promocional=float(o["salePrice"]),
                link=LINK_OFERTA.format(o["dealID"]),
                nota_metacritic=int(o["metacriticScore"]) or None,
            )
        except (KeyError, ValueError):
            continue
        if p.desconto >= desconto_minimo:
            promocoes.append(p)
    log.info("Promoções: %d com %d%%+ de desconto", len(promocoes), desconto_minimo)
    return promocoes

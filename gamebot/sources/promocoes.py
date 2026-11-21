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


HEADERS = {"User-Agent": "game-news-bot/1.0 (+https://github.com/Ericklevy/game-news-bot)"}


def _get(sessao: requests.Session, caminho: str, **params):
    resp = sessao.get(f"{API}/{caminho}", params=params or None, headers=HEADERS, timeout=TIMEOUT)
    if resp.status_code != 200:
        # Mostra o que a API respondeu, para saber o motivo do erro
        raise requests.HTTPError(f"{resp.status_code} em /{caminho}: {resp.text[:200].strip()}", response=resp)
    return resp.json()


def lojas(sessao: requests.Session) -> dict[str, str]:
    """Mapa storeID -> nome da loja (Steam, GOG, Epic...). Se falhar, segue sem os nomes."""
    try:
        return {s["storeID"]: s["storeName"] for s in _get(sessao, "stores") if s.get("isActive", 1)}
    except (requests.RequestException, ValueError, KeyError, TypeError) as erro:
        log.warning("Nomes das lojas indisponíveis (%s); seguindo sem eles", erro)
        return {}


def buscar(desconto_minimo: int = 50, nota_minima: int = 70, limite: int = 30,
           sessao: requests.Session | None = None) -> list[Promocao]:
    """Busca ofertas com desconto alto, ordenadas pela melhor relação preço/qualidade.

    Se a API estiver fora do ar, devolve lista vazia: o resumo sai só com as notícias.
    """
    sessao = sessao or requests.Session()
    nomes_lojas = lojas(sessao)
    try:
        ofertas = _get(sessao, "deals", sortBy="Deal Rating", pageSize=limite, onSale=1, metacritic=nota_minima)
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

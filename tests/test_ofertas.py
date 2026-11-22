from datetime import UTC, datetime, timedelta

import responses

from gamebot import ofertas, resumo
from gamebot.banco import Banco
from gamebot.models import Gratis, Promocao
from gamebot.resiliencia import Cache, Circuito
from gamebot.sources import cambio, gratis, promocoes


def _promo(**extra):
    base = dict(jogo="Hades", loja="Steam", preco_normal=24.99, preco_promocional=4.99,
                link="https://www.cheapshark.com/redirect?dealID=x", jogo_id="123")
    base.update(extra)
    return Promocao(**base)


@responses.activate
def test_cotacao_frankfurter():
    responses.get(cambio.URL, json={"base": "USD", "rates": {"BRL": 5.5}})
    assert cambio.dolar_em_reais() == 5.5


@responses.activate
def test_gratis_filtra_ativos_e_trata_201():
    responses.get(gratis.URL, json=[
        {"title": "Jogo A", "open_giveaway_url": "https://a", "platforms": "PC, Epic Games Store",
         "type": "Game", "worth": "$19.99", "end_date": "2026-11-30 23:59:00", "status": "Active"},
        {"title": "Jogo B", "open_giveaway_url": "https://b", "platforms": "PC", "type": "Game",
         "worth": "N/A", "end_date": "N/A", "status": "Expired"},
    ])
    lista = gratis.buscar()
    assert [g.titulo for g in lista] == ["Jogo A"]
    assert lista[0].termina_em == "2026-11-30" and lista[0].valor == "$19.99"

    responses.replace(responses.GET, gratis.URL, status=201, json={"status": 0})
    assert gratis.buscar() == []


@responses.activate
def test_menor_preco_historico_e_cache():
    responses.get(f"{promocoes.API}/games", json={"123": {"cheapestPriceEver": {"price": "4.99"}}})
    banco = Banco(":memory:")
    [p] = ofertas.enriquecer(banco, [_promo()])
    assert p.menor_da_historia
    # segunda vez vem do cache: nenhuma chamada nova para /games
    ofertas.enriquecer(banco, [_promo()])
    assert sum("/games" in c.request.url for c in responses.calls) == 1


def test_preco_anterior_do_historico():
    banco = Banco(":memory:")
    banco.conexao.execute("INSERT INTO precos VALUES ('123', 'Hades', 'Steam', 9.99, datetime('now', '-3 days'))")
    assert ofertas.precos_anteriores(banco, ["123"]) == {"123": 9.99}


def test_circuito_abre_e_pausa():
    banco = Banco(":memory:")
    agora = [datetime(2026, 1, 1, tzinfo=UTC)]
    circ = Circuito(banco, limite=2, relogio=lambda: agora[0])
    avisos: list[str] = []

    def quebra():
        raise RuntimeError("fora do ar")

    circ.chamar("X", quebra, avisos=avisos)
    circ.chamar("X", quebra, avisos=avisos)
    assert not circ.permitido("X") and len(avisos) == 1
    agora[0] += timedelta(hours=7)
    assert circ.permitido("X")


def test_cache_expira():
    banco = Banco(":memory:")
    agora = [datetime(2026, 1, 1, tzinfo=UTC)]
    cache = Cache(banco, relogio=lambda: agora[0])
    cache.gravar("k", 1, timedelta(hours=1))
    assert cache.ler("k") == 1
    agora[0] += timedelta(hours=2)
    assert cache.ler("k") is None


def test_mensagem_mostra_real_historia_e_gratis():
    p = _promo(cotacao_brl=5.0, menor_preco=4.99, preco_anterior=9.99)
    g = Gratis(titulo="Jogo A", link="https://a", plataformas="PC", tipo="Game",
               valor="$19.99", termina_em="2026-11-30")
    texto = resumo.montar([], [p], gratis=[g])
    assert "≈ R$ 24,95" in texto
    assert "menor preço da história" in texto and "caiu de US$ 9.99" in texto
    assert "Grátis para resgatar" in texto and "GamerPower" in texto and "até 30/11" in texto

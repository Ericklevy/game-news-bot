import responses

from gamebot.models import Promocao
from gamebot.sources import steam

SPECIALS = {
    "specials": {
        "items": [
            {"id": 1145360, "name": "Hades", "discounted": True, "discount_percent": 75,
             "original_price": 2499, "final_price": 624, "currency": "USD"},
            {"id": 730, "name": "CS2", "discounted": False,
             "original_price": 0, "final_price": 0, "currency": "USD"},
            {"id": 999, "name": "Pouco Desconto", "discounted": True, "discount_percent": 10,
             "original_price": 1000, "final_price": 900, "currency": "USD"},
        ]
    }
}


@responses.activate
def test_busca_specials_em_dolar_com_desconto_minimo():
    responses.get(steam.API, json=SPECIALS)

    resultado = steam.buscar(desconto_minimo=50)

    assert [p.jogo for p in resultado] == ["Hades"]
    hades = resultado[0]
    assert hades.loja == "Steam"
    assert hades.preco_normal == 24.99 and hades.preco_promocional == 6.24
    assert hades.desconto == 75
    assert hades.link == "https://store.steampowered.com/app/1145360"
    assert responses.calls[0].request.params["cc"] == "us"


@responses.activate
def test_steam_fora_do_ar_devolve_lista_vazia():
    responses.get(steam.API, status=503)

    assert steam.buscar() == []


@responses.activate
def test_resposta_sem_specials_nao_quebra():
    responses.get(steam.API, json={"top_sellers": {}})

    assert steam.buscar() == []


def test_jogo_repetido_fica_com_a_fonte_principal():
    cheapshark = [Promocao(jogo="Hades", loja="Steam", preco_normal=24.99, preco_promocional=6.24,
                           link="https://www.cheapshark.com/redirect?dealID=abc")]
    extras = [
        Promocao(jogo="HADES", loja="Steam", preco_normal=24.99, preco_promocional=6.24,
                 link="https://store.steampowered.com/app/1145360"),
        Promocao(jogo="Celeste", loja="Steam", preco_normal=19.99, preco_promocional=4.99,
                 link="https://store.steampowered.com/app/504230"),
    ]

    juntas = steam.sem_duplicadas(cheapshark, extras)

    assert [p.jogo for p in juntas] == ["Hades", "Celeste"]
    assert juntas[0].link.startswith("https://www.cheapshark.com")

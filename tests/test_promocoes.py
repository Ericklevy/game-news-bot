import json

import requests
import responses

from gamebot.models import Promocao
from gamebot.sources import promocoes


@responses.activate
def test_busca_promocoes_e_aplica_desconto_minimo(fixture):
    responses.get(f"{promocoes.API}/stores", json=json.loads(fixture("stores.json").read_text()))
    responses.get(f"{promocoes.API}/deals", json=json.loads(fixture("deals.json").read_text()))

    resultado = promocoes.buscar(desconto_minimo=50)

    assert [p.jogo for p in resultado] == ["Hades", "Jogo Grátis"]
    hades, gratis = resultado
    assert hades.loja == "Steam" and hades.desconto == 75 and hades.nota_metacritic == 93
    assert gratis.gratis and gratis.loja == "Epic Games Store" and gratis.nota_metacritic is None
    assert hades.link.endswith("dealID=abc")


@responses.activate
def test_api_fora_do_ar_nao_derruba_o_bot():
    responses.get(f"{promocoes.API}/stores", body=requests.ConnectionError("sem rede"))
    responses.get(f"{promocoes.API}/deals", body=requests.ConnectionError("sem rede"))
    assert promocoes.buscar() == []


@responses.activate
def test_falha_na_lista_de_lojas_nao_impede_as_promocoes(fixture, caplog):
    responses.get(f"{promocoes.API}/stores", status=400, body="Bad request")
    responses.get(f"{promocoes.API}/deals", json=json.loads(fixture("deals.json").read_text()))

    resultado = promocoes.buscar(desconto_minimo=50)

    assert [p.jogo for p in resultado] == ["Hades", "Jogo Grátis"]
    assert resultado[0].loja == "Loja"
    assert "400 em /stores: Bad request" in caplog.text


@responses.activate
def test_envia_user_agent_proprio(fixture):
    responses.get(f"{promocoes.API}/stores", json=[])
    responses.get(f"{promocoes.API}/deals", json=[])
    promocoes.buscar()
    assert all("game-news-bot" in c.request.headers["User-Agent"] for c in responses.calls)


def test_desconto_com_preco_zero_nao_divide_por_zero():
    assert Promocao("x", "y", 0, 0, "l").desconto == 0

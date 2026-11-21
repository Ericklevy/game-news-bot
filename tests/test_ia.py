import json

import pytest
import requests
import responses

from gamebot import ia
from gamebot.models import Noticia

NOTICIAS = [
    Noticia("PS5 Pro gets a price cut in Brazil", "https://a/1", "IGN", resumo="Sony lowers the price."),
    Noticia("Xbox Game Pass adds five games", "https://a/2", "GameSpot"),
]


def resposta_ia(itens, cerca=False):
    conteudo = json.dumps({"itens": itens}, ensure_ascii=False)
    if cerca:
        conteudo = f"Claro! Aqui está:\n```json\n{conteudo}\n```"
    return {"choices": [{"message": {"content": conteudo}}]}


TRADUCAO = [
    {"id": 0, "titulo": "PS5 Pro fica mais barato no Brasil", "resumo": "A Sony reduziu o preço."},
    {"id": 1, "titulo": "Xbox Game Pass recebe cinco jogos", "resumo": "Microsoft divulgou a lista."},
]


@pytest.fixture
def chaves(monkeypatch):
    for nome in ("OPENROUTER", "GROQ", "GEMINI", "SAMBANOVA"):
        monkeypatch.delenv(f"{nome}_API_KEY", raising=False)
    return lambda *nomes: [monkeypatch.setenv(f"{n.upper()}_API_KEY", "chave-teste") for n in nomes]


@responses.activate
def test_traduz_com_o_primeiro_provedor(chaves):
    chaves("openrouter")
    responses.post(ia.PADRAO["openrouter"].url, json=resposta_ia(TRADUCAO))

    resultado = ia.traduzir(NOTICIAS, ia.montar_provedores({}))

    assert [n.titulo for n in resultado] == ["PS5 Pro fica mais barato no Brasil", "Xbox Game Pass recebe cinco jogos"]
    assert all(n.traduzida for n in resultado)
    assert resultado[0].link == "https://a/1" and resultado[0].fonte == "IGN"
    enviado = json.loads(responses.calls[0].request.body)
    assert enviado["model"] == "openrouter/free"
    assert responses.calls[0].request.headers["Authorization"] == "Bearer chave-teste"


@responses.activate
def test_passa_para_o_proximo_quando_um_falha(chaves):
    chaves("openrouter", "groq", "gemini")
    responses.post(ia.PADRAO["openrouter"].url, status=429, body="rate limit")
    responses.post(ia.PADRAO["groq"].url, body=requests.ConnectionError("sem rede"))
    responses.post(ia.PADRAO["gemini"].url, json=resposta_ia(TRADUCAO, cerca=True))

    resultado = ia.traduzir(NOTICIAS, ia.montar_provedores({}))

    assert resultado[0].titulo == "PS5 Pro fica mais barato no Brasil"
    assert len(responses.calls) == 3


@responses.activate
def test_resposta_incompleta_conta_como_falha(chaves):
    chaves("openrouter", "groq")
    responses.post(ia.PADRAO["openrouter"].url, json=resposta_ia(TRADUCAO[:1]))
    responses.post(ia.PADRAO["groq"].url, json=resposta_ia(TRADUCAO))

    assert ia.traduzir(NOTICIAS, ia.montar_provedores({}))[1].titulo == "Xbox Game Pass recebe cinco jogos"


@responses.activate
def test_se_todos_falham_manda_em_ingles(chaves):
    chaves("openrouter", "sambanova")
    responses.post(ia.PADRAO["openrouter"].url, status=500)
    responses.post(ia.PADRAO["sambanova"].url, json={"choices": [{"message": {"content": "não sei"}}]})

    assert ia.traduzir(NOTICIAS, ia.montar_provedores({})) == NOTICIAS


def test_sem_chave_nao_chama_ninguem(chaves):
    # sem responses.activate: qualquer chamada de rede real quebraria o teste
    assert ia.traduzir(NOTICIAS, ia.montar_provedores({})) == NOTICIAS


def test_config_muda_ordem_e_modelo():
    provedores = ia.montar_provedores({"provedores": ["groq", "openrouter"], "modelos": {"groq": "llama-3.1-8b-instant"}})
    assert [p.nome for p in provedores] == ["groq", "openrouter"]
    assert provedores[0].modelo == "llama-3.1-8b-instant"
    assert provedores[0].variavel_chave == "GROQ_API_KEY"


@responses.activate
def test_erro_da_ia_nao_vaza_a_chave(chaves, caplog):
    chaves("openrouter")
    responses.post(ia.PADRAO["openrouter"].url, status=401, body="invalid key")
    ia.traduzir(NOTICIAS, ia.montar_provedores({"provedores": ["openrouter"]}))
    assert "chave-teste" not in caplog.text
    assert "HTTP 401" in caplog.text

from datetime import date, datetime, timezone

import pytest
import responses

from gamebot import resumo, telegram
from gamebot.__main__ import executar
from gamebot.banco import Banco
from gamebot.config import Config
from gamebot.models import Noticia, Promocao


def test_resumo_escapa_html_e_mostra_promocao():
    n = Noticia("Tom & Jerry <remaster>", "https://x.test/?a=1&b=2", "IGN", plataformas=frozenset({"PC"}))
    p = Promocao("Hades", "Steam", 24.99, 6.24, "https://deal.test/1", 93)
    texto = resumo.montar([n], [p], date(2026, 11, 21))
    assert "Tom &amp; Jerry &lt;remaster&gt;" in texto
    assert 'href="https://x.test/?a=1&amp;b=2"' in texto
    assert "-75%" in texto and "US$ 6.24" in texto and "Metacritic 93" in texto
    assert texto.startswith("<b>🕹️ Resumo gamer · 21/11/2026</b>")


def test_resumo_vazio():
    assert "Nada novo hoje" in resumo.montar([], [])


def test_divide_mensagem_grande_sem_cortar_itens():
    itens = [f"item {i} " + "x" * 300 for i in range(40)]
    blocos = resumo.dividir("\n\n".join(itens), limite=1000)
    assert all(len(b) <= 1000 for b in blocos)
    assert "\n\n".join(blocos) == "\n\n".join(itens)


@responses.activate
def test_envio_falho_levanta_erro_sem_vazar_token():
    responses.post("https://api.telegram.org/botSEGREDO/sendMessage",
                   json={"ok": False, "description": "chat not found"}, status=400)
    with pytest.raises(telegram.ErroTelegram) as erro:
        telegram.enviar("SEGREDO", "123", "oi")
    assert "chat not found" in str(erro.value)
    assert "SEGREDO" not in str(erro.value)


@responses.activate
def test_fluxo_completo_nao_reenvia_no_dia_seguinte(fixture, monkeypatch):
    monkeypatch.setattr(telegram.time, "sleep", lambda s: None)
    enviados = []
    responses.add_callback(responses.POST, "https://api.telegram.org/botT/sendMessage",
                           callback=lambda req: (enviados.append(req.body) or (200, {}, '{"ok": true}')),
                           content_type="application/json")
    for nome in ("OPENROUTER", "GROQ", "GEMINI", "SAMBANOVA"):
        monkeypatch.delenv(f"{nome}_API_KEY", raising=False)
    cfg = Config(
        feeds={"A": str(fixture("feed_a.xml")), "B": str(fixture("feed_b.xml"))},
        palavras_bloqueadas=["box office"], promocoes_ativas=False,
        telegram_token="T", telegram_chat_id="1", banco=":memory:",
    )
    agora = datetime(2026, 11, 21, 12, tzinfo=timezone.utc)

    banco = Banco(":memory:")
    monkeypatch.setattr("gamebot.__main__.Banco", lambda _: banco)
    monkeypatch.setattr(banco, "fechar", lambda: None)

    primeiro = executar(cfg, agora=agora)
    assert "Zelda" in primeiro and "PS5 Pro" in primeiro and "Game Pass" in primeiro
    assert "box office" not in primeiro.lower()     # palavra bloqueada
    assert "Old news" not in primeiro               # fora da janela de 30 h
    assert primeiro.count("Zelda") == 1             # mesmo assunto em dois sites

    arquivadas = banco.conexao.execute("SELECT COUNT(*) FROM noticias").fetchone()[0]
    assert arquivadas == primeiro.count("<a href=")

    segundo = executar(cfg, agora=agora)
    assert "Nada novo hoje" in segundo
    assert len(enviados) == 2


def test_resumo_mostra_frase_traduzida():
    n = Noticia("PS5 Pro fica mais barato", "https://x", "IGN", resumo="A Sony reduziu o preço.", traduzida=True)
    original = Noticia("PS5 Pro price cut", "https://y", "IGN", resumo="Sony lowers the price.")
    texto = resumo.montar([n, original], [])
    assert "A Sony reduziu o preço." in texto
    assert "Sony lowers the price." not in texto     # resumo em inglês não entra

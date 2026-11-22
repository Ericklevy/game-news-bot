from datetime import UTC, date, datetime

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
    agora = datetime(2026, 11, 21, 12, tzinfo=UTC)

    banco = Banco(":memory:")
    monkeypatch.setattr("gamebot.__main__.Banco", lambda _: banco)
    monkeypatch.setattr(banco, "fechar", lambda: None)

    primeiro = executar(cfg, agora=agora)
    assert "Zelda" in primeiro and "PS5 Pro" in primeiro and "Game Pass" in primeiro
    assert "box office" not in primeiro.lower()     # palavra bloqueada
    assert "Old news" not in primeiro               # fora da janela de 30 h
    assert primeiro.count("Zelda") == 1             # mesmo assunto em dois sites

    # O arquivo guarda TODAS as recentes (até a repetida de outro site), não só as enviadas
    arquivadas = {link for (link,) in banco.conexao.execute("SELECT link FROM noticias")}
    assert arquivadas == {"https://a.test/zelda", "https://b.test/zelda-2", "https://a.test/ps5",
                          "https://a.test/layoffs", "https://b.test/gamepass"}
    assert primeiro.count("<a href=") < len(arquivadas)

    segundo = executar(cfg, agora=agora)
    assert "Nada novo hoje" in segundo
    assert len(enviados) == 2


def test_resumo_mostra_frase_traduzida():
    n = Noticia("PS5 Pro fica mais barato", "https://x", "IGN", resumo="A Sony reduziu o preço.", traduzida=True)
    original = Noticia("PS5 Pro price cut", "https://y", "IGN", resumo="Sony lowers the price.")
    texto = resumo.montar([n, original], [])
    assert "A Sony reduziu o preço." in texto
    assert "Sony lowers the price." not in texto     # resumo em inglês não entra


def test_arquivo_bruto_nao_apaga_a_traducao():
    b = Banco(":memory:")
    traduzida = Noticia("Zelda novo", "https://z", "IGN", resumo="Em português", traduzida=True)
    original = Noticia("New Zelda", "https://z", "IGN", resumo="In English")
    assert b.arquivar([traduzida]) == 1
    assert b.arquivar([original], substituir=False) == 0       # já existe: não sobrescreve
    assert b.conexao.execute("SELECT titulo FROM noticias").fetchone()[0] == "Zelda novo"
    assert b.conexao.execute("SELECT COUNT(*) FROM noticias_busca").fetchone()[0] == 1


def test_avisos_quando_fonte_e_ia_falham(fixture, monkeypatch):
    for nome in ("OPENROUTER", "GROQ", "GEMINI", "SAMBANOVA"):
        monkeypatch.delenv(f"{nome}_API_KEY", raising=False)
    monkeypatch.setenv("GROQ_API_KEY", "x")
    import gamebot.__main__ as m
    monkeypatch.setattr(m.ia, "traduzir", lambda noticias, provedores: noticias)   # simula IA falhando
    monkeypatch.setattr(m, "coletar_promocoes", lambda cfg: [])
    cfg = Config(feeds={"A": str(fixture("feed_a.xml")), "Quebrado": "nao é feed <<<"}, banco=":memory:",
                 promocoes_ativas=True)
    avisos = []
    executar(cfg, dry_run=True, agora=datetime(2026, 11, 21, 12, tzinfo=UTC), avisos=avisos)
    assert "A fonte Quebrado não respondeu ou veio vazia." in avisos
    assert any("promoções" in a for a in avisos)
    assert any("tradução falhou" in a for a in avisos)


@responses.activate
def test_menu_de_comandos_so_no_chat_do_dono():
    import json as _json
    responses.post("https://api.telegram.org/botT/setMyCommands", json={"ok": True})
    telegram.definir_comandos("T", [("agora", "Publica")], chat_id="700")
    corpo = dict(x.split("=", 1) for x in responses.calls[0].request.body.split("&"))
    from urllib.parse import unquote_plus
    assert _json.loads(unquote_plus(corpo["scope"])) == {"type": "chat", "chat_id": "700"}
    assert _json.loads(unquote_plus(corpo["commands"])) == [{"command": "agora", "description": "Publica"}]

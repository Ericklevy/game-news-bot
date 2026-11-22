"""Backup, batimento, repetidas entre dias, promoção repetida, prévia e busca por significado."""
import gzip
import json
import sqlite3
from datetime import UTC, datetime, time
from zoneinfo import ZoneInfo

import pytest
import responses

from gamebot import assistente, ia, telegram
from gamebot.__main__ import executar
from gamebot.banco import Banco, copia_compactada, guardar_vetores, vetores_recentes
from gamebot.config import Config
from gamebot.escuta import Escuta
from gamebot.models import Noticia, Promocao

SP = ZoneInfo("America/Sao_Paulo")


# ---------- backup ----------

def test_copia_do_banco_abre_e_tem_os_dados(tmp_path):
    b = Banco(":memory:")
    b.arquivar([Noticia("Zelda novo", "https://z", "IGN")])
    arquivo = tmp_path / "copia.db"
    arquivo.write_bytes(gzip.decompress(copia_compactada(b)))
    assert sqlite3.connect(arquivo).execute("SELECT titulo FROM noticias").fetchone() == ("Zelda novo",)


@responses.activate
def test_envia_backup_como_documento():
    responses.post("https://api.telegram.org/botT/sendDocument", json={"ok": True})
    telegram.enviar_arquivo("T", "700", "copia.db.gz", b"dados", "legenda")
    corpo = responses.calls[0].request.body
    assert b'name="document"; filename="copia.db.gz"' in corpo and b"dados" in corpo


def _escuta(agora, **extra):
    estado = {"backups": 0, "batidas": 0, "respostas": []}
    e = Escuta(chat_autorizado="7", buscar=lambda o: [], rodar_resumo=lambda: "",
               responder=lambda c, t: estado["respostas"].append(t), horarios=[time(8, 17)],
               relogio=lambda: agora[0], fazer_backup=lambda: estado.__setitem__("backups", estado["backups"] + 1),
               **extra)
    return e, estado


def test_backup_semanal_uma_vez_no_domingo():
    agora = [datetime(2026, 11, 22, 3, 0, tzinfo=SP)]          # domingo
    e, estado = _escuta(agora, backup=(6, time(3, 17)))
    e.passo()
    assert estado["backups"] == 0
    agora[0] = datetime(2026, 11, 22, 3, 20, tzinfo=SP)
    e.passo()
    e.passo()
    assert estado["backups"] == 1
    assert "Backup do banco: domingo às 03h17." in e.texto_agenda()


def test_comando_backup():
    agora = [datetime(2026, 11, 22, 9, 0, tzinfo=SP)]
    e, estado = _escuta(agora)
    e.tratar({"update_id": 1, "message": {"chat": {"id": 7}, "text": "/backup"}})
    assert estado["backups"] == 1


# ---------- batimento ----------

def test_batimento_respeita_o_intervalo_e_nao_derruba(monkeypatch):
    relogio = [1000.0]
    monkeypatch.setattr("gamebot.escuta.time.monotonic", lambda: relogio[0])
    batidas = []

    def bater():
        batidas.append(1)
        if len(batidas) == 2:
            raise ConnectionError("monitor fora do ar")

    agora = [datetime(2026, 11, 22, 7, 0, tzinfo=SP)]
    e, _ = _escuta(agora, batimento=bater, intervalo_batimento=300)
    e.passo()
    e.passo()
    assert len(batidas) == 1
    relogio[0] += 301
    e.passo()                                    # segunda batida falha, mas o bot segue
    relogio[0] += 301
    e.passo()
    assert len(batidas) == 3


# ---------- repetidas entre dias, promoção repetida e prévia ----------

@pytest.fixture
def sem_ia(monkeypatch):
    for nome in ("OPENROUTER", "GROQ", "GEMINI", "SAMBANOVA"):
        monkeypatch.delenv(f"{nome}_API_KEY", raising=False)


@responses.activate
def test_nao_repete_assunto_nem_promocao_em_dias_seguidos(tmp_path, sem_ia, monkeypatch):
    import gamebot.__main__ as m
    feed1 = tmp_path / "d1.xml"
    feed1.write_text("""<?xml version="1.0"?><rss version="2.0"><channel>
      <item><title>Nintendo announces new Zelda game for Switch 2</title><link>https://a/zelda</link>
      <pubDate>Sat, 21 Nov 2026 10:00:00 GMT</pubDate></item></channel></rss>""")
    feed2 = tmp_path / "d2.xml"
    feed2.write_text("""<?xml version="1.0"?><rss version="2.0"><channel>
      <item><title>New Zelda game announced by Nintendo for Switch 2</title><link>https://b/zelda-de-novo</link>
      <pubDate>Sun, 22 Nov 2026 10:00:00 GMT</pubDate></item>
      <item><title>Hollow Knight Silksong gets surprise DLC</title><link>https://b/silksong</link>
      <pubDate>Sun, 22 Nov 2026 09:00:00 GMT</pubDate></item></channel></rss>""")

    ofertas = iter([[Promocao("Hades", "Steam", 24.99, 6.24, "https://deal/1")],
                    [Promocao("Hades", "GOG", 24.99, 5.99, "https://deal/2")]])
    monkeypatch.setattr(m, "coletar_promocoes", lambda cfg: next(ofertas))
    enviados = []
    responses.add_callback(responses.POST, "https://api.telegram.org/botT/sendMessage",
                           callback=lambda r: (enviados.append(json.loads(r.body)) or (200, {}, '{"ok": true}')),
                           content_type="application/json")
    monkeypatch.setattr(telegram.time, "sleep", lambda s: None)
    banco = Banco(":memory:")
    monkeypatch.setattr(m, "Banco", lambda _: banco)
    monkeypatch.setattr(banco, "fechar", lambda: None)

    base = dict(telegram_token="T", telegram_chat_id="1", banco=":memory:", janela_horas=48)
    executar(Config(feeds={"A": str(feed1)}, **base), agora=datetime(2026, 11, 21, 12, tzinfo=UTC))
    segundo = executar(Config(feeds={"B": str(feed2)}, **base), agora=datetime(2026, 11, 22, 12, tzinfo=UTC))

    assert "Silksong" in segundo
    assert "Zelda" not in segundo                 # mesmo assunto, outro título, dia seguinte
    assert "Hades" not in segundo                 # mesmo jogo em promoção, outra loja
    # prévia com imagem só na primeira notícia de cada post
    assert enviados[0]["link_preview_options"]["url"] == "https://a/zelda"
    assert enviados[1]["link_preview_options"]["url"] == "https://b/silksong"


@responses.activate
def test_sem_previa_quando_desligada():
    responses.post("https://api.telegram.org/botT/sendMessage", json={"ok": True})
    telegram.enviar("T", "1", "oi")
    assert json.loads(responses.calls[0].request.body)["link_preview_options"] == {"is_disabled": True}


# ---------- busca por significado ----------

EMB = "https://generativelanguage.googleapis.com/v1beta/openai/embeddings"


@pytest.fixture
def emb(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "g")
    return ia.montar_embeddings({"embeddings": {"ativo": True, "provedores": ["gemini"]}})


def test_embeddings_desligados_por_padrao():
    assert ia.montar_embeddings({}) == []


@responses.activate
def test_vetoriza_em_lote(emb):
    responses.post(EMB, json={"data": [{"index": 1, "embedding": [0, 1]}, {"index": 0, "embedding": [1, 0]}]})
    modelo, vetores = ia.vetorizar(["a", "b"], emb)
    assert modelo == "gemini/gemini-embedding-001" and vetores == [[1, 0], [0, 1]]
    assert json.loads(responses.calls[0].request.body)["input"] == ["a", "b"]


@responses.activate
def test_vetorizar_falhando_devolve_none(emb):
    responses.post(EMB, status=429)
    assert ia.vetorizar(["a"], emb) is None


@responses.activate
def test_busca_hibrida_acha_por_significado(emb):
    b = Banco(":memory:")
    b.arquivar([Noticia("GTA 6 bate recorde de vendas", "https://gta", "IGN"),
                Noticia("Zelda novo anunciado", "https://zelda", "IGN")])
    guardar_vetores(b, "gemini/gemini-embedding-001", [("https://gta", [1.0, 0.0]), ("https://zelda", [0.0, 1.0])])
    assert len(vetores_recentes(b, "gemini/gemini-embedding-001")) == 2
    # "jogo da Rockstar" não tem a palavra GTA, mas o vetor da pergunta fica perto do de GTA 6
    responses.post(EMB, json={"data": [{"index": 0, "embedding": [0.9, 0.1]}]})
    achadas = assistente.busca_hibrida("jogo da Rockstar", b, emb)
    assert [r.link for r in achadas] == ["https://gta"]


def test_busca_hibrida_sem_embeddings_usa_so_palavras():
    b = Banco(":memory:")
    b.arquivar([Noticia("Zelda novo anunciado", "https://zelda", "IGN")])
    assert [r.link for r in assistente.busca_hibrida("zelda", b, None)] == ["https://zelda"]

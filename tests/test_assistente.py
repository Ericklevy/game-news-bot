import json
from datetime import datetime, timezone

import pytest
import responses

from gamebot import assistente, ia
from gamebot.banco import Banco, buscar
from gamebot.escuta import Escuta
from gamebot.models import Noticia

URL = ia.PADRAO["openrouter"].url


def n(titulo, link, fonte="IGN", resumo=""):
    return Noticia(titulo, link, fonte, publicada_em=datetime(2026, 11, 21, tzinfo=timezone.utc),
                   resumo=resumo, traduzida=True)


@pytest.fixture
def banco():
    b = Banco(":memory:")
    b.arquivar([
        n("GTA 6 tem 99 no Metascore da crítica", "https://a/gta-nota", "Eurogamer", "Jogadores fazem review bombing."),
        n("GTA 6 está travando em alguns PS5", "https://a/gta-ps5", "Eurogamer", "Erro CE-108255-1 no console."),
        n("Vaca estranha de GTA 6 viraliza", "https://a/gta-vaca", "IGN"),
        n("Xbox Game Pass recebe cinco jogos em dezembro", "https://a/gamepass", "GameSpot"),
        n("Nintendo anuncia novo Zelda para o Switch 2", "https://a/zelda", "IGN", "Lançamento previsto para 2027."),
    ])
    return b


@pytest.fixture
def com_chave(monkeypatch):
    for nome in ("OPENROUTER", "GROQ", "GEMINI", "SAMBANOVA"):
        monkeypatch.delenv(f"{nome}_API_KEY", raising=False)
    monkeypatch.setenv("OPENROUTER_API_KEY", "teste")
    return ia.montar_provedores({"provedores": ["openrouter"]})


def ia_responde(texto):
    responses.post(URL, json={"choices": [{"message": {"content": texto}}]})


# ---------- busca ----------

def test_consulta_ignora_palavras_de_pergunta_e_acentos():
    assert assistente.consulta_fts("O que saiu de GTA 6 essa semana?") == '"gta"* OR "6"*'
    assert assistente.consulta_fts("Teve promoção boa?") == '"promocao"*'


def test_busca_acha_por_palavra_sem_acento(banco):
    achadas = buscar(banco, assistente.consulta_fts("travando no ps5"))
    assert achadas[0].link == "https://a/gta-ps5"


def test_banco_antigo_e_indexado_ao_abrir(tmp_path):
    caminho = tmp_path / "antigo.db"
    b = Banco(caminho)
    b.arquivar([n("Zelda novo anunciado", "https://a/z")])
    b.conexao.execute("DELETE FROM noticias_busca")   # simula banco de antes da busca existir
    b.conexao.commit()
    b.fechar()
    assert buscar(Banco(caminho), '"zelda"*')[0].link == "https://a/z"


# ---------- /perguntar ----------

@responses.activate
def test_perguntar_responde_com_fontes_citadas(banco, com_chave):
    ia_responde("O GTA 6 recebeu 99 de nota da crítica [1], mas tem travado em alguns PS5 [2].")
    texto = assistente.perguntar("o que saiu de GTA 6?", banco, com_chave)

    assert texto.startswith("💬 O GTA 6 recebeu 99")
    fontes = texto.split("<b>Fontes</b>")[1]
    assert fontes.count("<a href=") == 2                     # só as notícias citadas [1] e [2]
    assert all("gta" in linha.lower() for linha in fontes.strip().splitlines())
    enviado = json.loads(responses.calls[0].request.body)["messages"][1]["content"]
    assert "[1]" in enviado and "Pergunta: o que saiu de GTA 6?" in enviado


@responses.activate
def test_perguntar_sem_ia_devolve_as_noticias(banco, com_chave):
    responses.post(URL, status=429)
    texto = assistente.perguntar("zelda", banco, com_chave)
    assert "A IA não respondeu" in texto and "https://a/zelda" in texto


def test_perguntar_sem_resultado_nao_chama_ia(banco, com_chave):
    # sem responses.activate: uma chamada de rede quebraria o teste
    assert "Não achei nada" in assistente.perguntar("pokemon", banco, com_chave)


def test_perguntar_vazio_explica_o_uso(banco, com_chave):
    assert "/perguntar o que saiu" in assistente.perguntar("  ", banco, com_chave)


@responses.activate
def test_resposta_da_ia_e_escapada(banco, com_chave):
    ia_responde("Use <script> com cuidado [1]")
    assert "&lt;script&gt;" in assistente.perguntar("gta", banco, com_chave)


# ---------- /semana ----------

@responses.activate
def test_semana_ordena_assuntos_pela_quantidade(banco, com_chave):
    ia_responde('{"assuntos": [{"assunto": "Game Pass", "ids": [3]}, {"assunto": "GTA 6", "ids": [0, 1, 2]}]}')
    texto = assistente.semana(banco, com_chave)
    assert texto.index("GTA 6") < texto.index("Game Pass")
    assert "🥇 <b>GTA 6</b> · 3 notícia(s) em 2 site(s)" in texto


@responses.activate
def test_semana_sem_ia_usa_contagem_de_palavras(banco, com_chave):
    responses.post(URL, status=500)
    texto = assistente.semana(banco, com_chave)
    assert "🥇 <b>GTA</b> · 3 notícia(s)" in texto


def test_semana_com_poucas_noticias():
    assert "poucas notícias" in assistente.semana(Banco(":memory:"), [])


# ---------- comandos no Telegram ----------

def test_comandos_novos_respondem_ao_dono():
    respostas = []
    e = Escuta(chat_autorizado="7", buscar=lambda o: [], responder=lambda c, t: respostas.append(t),
               rodar_resumo=lambda: "", perguntar=lambda p: f"resposta para: {p}", semana=lambda: "ranking")
    e.tratar({"update_id": 1, "message": {"chat": {"id": 7}, "text": "/perguntar   tem Zelda novo?"}})
    e.tratar({"update_id": 2, "message": {"chat": {"id": 7}, "text": "/semana"}})
    assert "resposta para: tem Zelda novo?" in respostas
    assert respostas[-1] == "ranking"

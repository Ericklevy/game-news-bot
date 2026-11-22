from datetime import UTC, datetime

from gamebot import filtros
from gamebot.models import Noticia
from gamebot.sources.rss import ler_feed


def test_le_feed_limpa_html_e_detecta_plataforma(fixture):
    noticias = ler_feed("Site A", str(fixture("feed_a.xml")))
    zelda = noticias[0]
    assert zelda.titulo == "New Zelda game announced for Nintendo Switch 2"
    assert zelda.resumo == "Nintendo revealed the next Zelda today."
    assert zelda.plataformas == {"Nintendo"}
    assert zelda.publicada_em == datetime(2026, 11, 21, 10, tzinfo=UTC)


def test_feed_quebrado_vira_lista_vazia():
    assert ler_feed("Fora do ar", "isto não é um feed <<<") == []


def test_remove_mesmo_assunto_de_sites_diferentes(fixture):
    noticias = ler_feed("A", str(fixture("feed_a.xml"))) + ler_feed("B", str(fixture("feed_b.xml")))
    unicas = filtros.sem_repetidas(noticias)
    titulos = [n.titulo for n in unicas]
    assert "New Zelda game announced for Nintendo Switch 2" in titulos
    assert "Nintendo announces new Zelda game for Switch 2" not in titulos
    assert "Xbox Game Pass adds five games in December" in titulos


def test_titulos_diferentes_nao_sao_parecidos():
    assert not filtros.parecidos("PS5 Pro gets a price cut", "Xbox Game Pass adds five games")


def test_filtra_por_plataforma_e_mantem_gerais():
    ns = [
        Noticia("a", "1", "x", plataformas=frozenset({"Xbox"})),
        Noticia("b", "2", "x", plataformas=frozenset({"Nintendo"})),
        Noticia("c", "3", "x"),
    ]
    assert [n.titulo for n in filtros.por_plataforma(ns, {"Xbox"})] == ["a", "c"]
    assert [n.titulo for n in filtros.por_plataforma(ns, {"Xbox"}, incluir_gerais=False)] == ["a"]


def test_bloqueia_palavras_sem_ligar_para_acento_e_maiuscula():
    ns = [Noticia("Novo FILME de Mario", "1", "x"), Noticia("Mario Kart", "2", "x")]
    assert [n.titulo for n in filtros.sem_bloqueadas(ns, ["filme"])] == ["Mario Kart"]


def test_bloqueio_compara_palavras_inteiras():
    ns = [Noticia("Xbox Games Showcase date announced", "1", "x"),
          Noticia("How to unlock the Brooks safe in GTA 6", "2", "x")]
    assert [n.titulo for n in filtros.sem_bloqueadas(ns, ["how to"])] == ["Xbox Games Showcase date announced"]


def test_limita_noticias_por_site():
    ns = [Noticia(f"n{i}", str(i), "PC Gamer") for i in range(5)] + [Noticia("outra", "x", "IGN")]
    assert [n.titulo for n in filtros.limitar_por_fonte(ns, 3)] == ["n0", "n1", "n2", "outra"]


def test_plataforma_padrao_do_site(fixture):
    noticias = ler_feed("Site A", str(fixture("feed_a.xml")), plataforma_padrao="PC")
    por_titulo = {n.titulo: n.plataformas for n in noticias}
    assert por_titulo["Game industry layoffs hit another studio"] == {"PC"}            # sem plataforma no texto
    assert por_titulo["PS5 Pro gets a price cut in Brazil"] == {"PlayStation"}         # texto manda

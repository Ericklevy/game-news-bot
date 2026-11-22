import requests
import responses

from gamebot.sources import pagina

HTML = """<html><head><script>var x = '<p>não é parágrafo</p>';</script></head><body>
<nav><p>Menu do site com muitos links que não interessam para a matéria em si.</p></nav>
<article>
  <p>A Naughty Dog anunciou oficialmente The Last of Us Part III durante a cerimônia desta semana.</p>
  <p>Foto: divulgação</p>
  <p>O estúdio disse que o jogo chega ao PS5 em 2027 e trará &quot;a maior história&quot; da série até agora.</p>
</article>
<footer><p>Copyright e outros textos de rodapé que também devem ser ignorados pelo leitor.</p></footer>
</body></html>"""


def test_pega_so_os_paragrafos_da_materia():
    texto = pagina.extrair_texto(HTML)
    assert texto.splitlines() == [
        "A Naughty Dog anunciou oficialmente The Last of Us Part III durante a cerimônia desta semana.",
        'O estúdio disse que o jogo chega ao PS5 em 2027 e trará "a maior história" da série até agora.',
    ]


def test_corta_textos_longos():
    html = "<p>" + "palavra " * 1000 + "</p>"
    texto = pagina.extrair_texto(html, limite=200)
    assert len(texto) <= 201 and texto.endswith("…")


@responses.activate
def test_falhas_viram_texto_vazio():
    responses.get("https://x/404", status=404)
    responses.get("https://x/pdf", body=b"%PDF", content_type="application/pdf")
    responses.get("https://x/caiu", body=requests.ConnectionError("sem rede"))
    assert pagina.ler("https://x/404") == pagina.ler("https://x/pdf") == pagina.ler("https://x/caiu") == ""


@responses.activate
def test_le_a_pagina_com_user_agent_proprio():
    responses.get("https://x/ok", body=HTML, content_type="text/html; charset=utf-8")
    assert "Naughty Dog" in pagina.ler("https://x/ok")
    assert "game-news-bot" in responses.calls[0].request.headers["User-Agent"]

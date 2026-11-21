import pytest

from gamebot.plataformas import detectar


@pytest.mark.parametrize("texto, esperado", [
    ("PS5 Pro gets a price cut", {"PlayStation"}),
    ("Xbox Game Pass adds five games", {"Xbox"}),
    ("New Zelda for Nintendo Switch 2", {"Nintendo"}),
    ("Out now on Steam and PS5", {"PC", "PlayStation"}),
    ("Game industry layoffs hit another studio", set()),
])
def test_detecta_plataformas(texto, esperado):
    assert detectar(texto) == esperado


def test_nao_confunde_pedaco_de_palavra():
    # "pc" dentro de outra palavra não conta
    assert "PC" not in detectar("Epcot theme park")

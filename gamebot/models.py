"""Modelos de domínio: o que o bot coleta, filtra e envia."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class Noticia:
    titulo: str
    link: str
    fonte: str
    publicada_em: datetime | None = None
    resumo: str = ""
    plataformas: frozenset[str] = field(default_factory=frozenset)
    traduzida: bool = False


@dataclass(frozen=True)
class Promocao:
    jogo: str
    loja: str
    preco_normal: float
    preco_promocional: float
    link: str
    nota_metacritic: int | None = None
    plataformas: frozenset[str] = field(default_factory=lambda: frozenset({"PC"}))
    jogo_id: str = ""                    # gameID da CheapShark
    menor_preco: float | None = None     # menor preço da história (CheapShark)
    preco_anterior: float | None = None  # maior preço que o bot viu nos últimos 30 dias
    cotacao_brl: float | None = None     # dólar em reais, para mostrar o preço aproximado

    @property
    def menor_da_historia(self) -> bool:
        return self.menor_preco is not None and self.preco_promocional <= self.menor_preco + 0.001

    @property
    def desconto(self) -> int:
        """Desconto em porcentagem inteira (0 a 100)."""
        if self.preco_normal <= 0:
            return 0
        return round((1 - self.preco_promocional / self.preco_normal) * 100)

    @property
    def gratis(self) -> bool:
        return self.preco_promocional == 0


@dataclass(frozen=True)
class Gratis:
    """Jogo ou DLC dado de graça por tempo limitado (dados da GamerPower)."""
    titulo: str
    link: str
    plataformas: str
    tipo: str                     # Game, DLC...
    valor: str = ""               # preço normal, ex.: "$19.99"
    termina_em: str | None = None # "AAAA-MM-DD" ou None se não tem data

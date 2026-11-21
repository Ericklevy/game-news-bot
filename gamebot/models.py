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

    @property
    def desconto(self) -> int:
        """Desconto em porcentagem inteira (0 a 100)."""
        if self.preco_normal <= 0:
            return 0
        return round((1 - self.preco_promocional / self.preco_normal) * 100)

    @property
    def gratis(self) -> bool:
        return self.preco_promocional == 0

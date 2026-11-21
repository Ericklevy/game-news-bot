"""Guarda o que já foi enviado, para nunca mandar a mesma coisa duas vezes."""
from __future__ import annotations

import sqlite3
from collections.abc import Iterable
from datetime import datetime, timezone
from pathlib import Path

_ESQUEMA = """
CREATE TABLE IF NOT EXISTS enviados (
    link       TEXT PRIMARY KEY,
    tipo       TEXT NOT NULL,          -- 'noticia' ou 'promocao'
    titulo     TEXT NOT NULL,
    enviado_em TEXT NOT NULL
);
"""


class Banco:
    def __init__(self, caminho: str | Path = "data/gamebot.db"):
        if str(caminho) != ":memory:":
            Path(caminho).parent.mkdir(parents=True, exist_ok=True)
        self.conexao = sqlite3.connect(caminho)
        self.conexao.executescript(_ESQUEMA)

    def ja_enviados(self, links: Iterable[str]) -> set[str]:
        links = list(links)
        if not links:
            return set()
        marcas = ",".join("?" * len(links))
        cur = self.conexao.execute(f"SELECT link FROM enviados WHERE link IN ({marcas})", links)
        return {linha[0] for linha in cur}

    def marcar(self, itens: Iterable[tuple[str, str, str]]) -> None:
        """Registra itens (link, tipo, título) como enviados."""
        agora = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with self.conexao:
            self.conexao.executemany(
                "INSERT OR IGNORE INTO enviados (link, tipo, titulo, enviado_em) VALUES (?, ?, ?, ?)",
                [(link, tipo, titulo, agora) for link, tipo, titulo in itens],
            )

    def limpar_antigos(self, dias: int = 60) -> None:
        with self.conexao:
            self.conexao.execute(
                "DELETE FROM enviados WHERE enviado_em < datetime('now', ?)", (f"-{dias} days",)
            )

    def fechar(self) -> None:
        self.conexao.close()

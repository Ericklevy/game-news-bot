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

-- Arquivo das notícias enviadas, já traduzidas. É a base para buscas e RAG no futuro.
CREATE TABLE IF NOT EXISTS noticias (
    link        TEXT PRIMARY KEY,
    titulo      TEXT NOT NULL,
    resumo      TEXT NOT NULL DEFAULT '',
    fonte       TEXT NOT NULL,
    plataformas TEXT NOT NULL DEFAULT '',
    publicada_em TEXT,
    traduzida   INTEGER NOT NULL DEFAULT 0,
    salva_em    TEXT NOT NULL
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

    def arquivar(self, noticias) -> None:
        """Guarda as notícias (título e resumo já traduzidos, quando houver)."""
        agora = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with self.conexao:
            self.conexao.executemany(
                "INSERT OR REPLACE INTO noticias VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                [(n.link, n.titulo, n.resumo, n.fonte, ",".join(sorted(n.plataformas)),
                  n.publicada_em.isoformat() if n.publicada_em else None, int(n.traduzida), agora)
                 for n in noticias],
            )

    def limpar_antigos(self, dias: int = 60) -> None:
        with self.conexao:
            self.conexao.execute(
                "DELETE FROM enviados WHERE enviado_em < datetime('now', ?)", (f"-{dias} days",)
            )

    def fechar(self) -> None:
        self.conexao.close()

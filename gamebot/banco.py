"""Guarda o que já foi enviado, para nunca mandar a mesma coisa duas vezes."""
from __future__ import annotations

import sqlite3
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
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

-- Vetores (embeddings) das notícias enviadas, para a busca por significado
CREATE TABLE IF NOT EXISTS vetores (
    link   TEXT PRIMARY KEY,
    modelo TEXT NOT NULL,
    vetor  BLOB NOT NULL
);

-- Índice de busca de texto sobre o arquivo (título e resumo em português)
CREATE VIRTUAL TABLE IF NOT EXISTS noticias_busca USING fts5(
    link UNINDEXED, titulo, resumo, tokenize = 'unicode61 remove_diacritics 2'
);
"""


class Banco:
    def __init__(self, caminho: str | Path = "data/gamebot.db"):
        if str(caminho) != ":memory:":
            Path(caminho).parent.mkdir(parents=True, exist_ok=True)
        self.conexao = sqlite3.connect(caminho)
        self.conexao.executescript(_ESQUEMA)
        self._indexar_faltantes()

    def _indexar_faltantes(self) -> None:
        """Bancos criados antes da busca existir: indexa o arquivo antigo uma vez."""
        with self.conexao:
            self.conexao.execute(
                "INSERT INTO noticias_busca (link, titulo, resumo) "
                "SELECT link, titulo, resumo FROM noticias "
                "WHERE link NOT IN (SELECT link FROM noticias_busca)"
            )

    def ja_enviados(self, links: Iterable[str]) -> set[str]:
        links = list(links)
        if not links:
            return set()
        marcas = ",".join("?" * len(links))
        cur = self.conexao.execute(f"SELECT link FROM enviados WHERE link IN ({marcas})", links)
        return {linha[0] for linha in cur}

    def marcar(self, itens: Iterable[tuple[str, str, str]]) -> None:
        """Registra itens (link, tipo, título) como enviados."""
        agora = datetime.now(UTC).isoformat(timespec="seconds")
        with self.conexao:
            self.conexao.executemany(
                "INSERT OR IGNORE INTO enviados (link, tipo, titulo, enviado_em) VALUES (?, ?, ?, ?)",
                [(link, tipo, titulo, agora) for link, tipo, titulo in itens],
            )

    def arquivar(self, noticias, substituir: bool = True) -> int:
        """Guarda notícias no arquivo de busca. Devolve quantas entraram ou mudaram.

        substituir=True  -> sobrescreve (usado para gravar a versão traduzida das enviadas);
        substituir=False -> só acrescenta as novas (usado para o arquivo bruto, sem apagar traduções).
        """
        agora = datetime.now(UTC).isoformat(timespec="seconds")
        modo = "INSERT OR REPLACE" if substituir else "INSERT OR IGNORE"
        gravadas = 0
        with self.conexao:
            for n in noticias:
                cur = self.conexao.execute(
                    f"{modo} INTO noticias VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (n.link, n.titulo, n.resumo, n.fonte, ",".join(sorted(n.plataformas)),
                     n.publicada_em.isoformat() if n.publicada_em else None, int(n.traduzida), agora),
                )
                if cur.rowcount == 0:
                    continue
                gravadas += 1
                self.conexao.execute("DELETE FROM noticias_busca WHERE link = ?", (n.link,))
                self.conexao.execute("INSERT INTO noticias_busca (link, titulo, resumo) VALUES (?, ?, ?)",
                                     (n.link, n.titulo, n.resumo))
        return gravadas

    def limpar_antigos(self, dias: int = 60, dias_arquivo: int = 180) -> None:
        with self.conexao:
            self.conexao.execute(
                "DELETE FROM enviados WHERE enviado_em < datetime('now', ?)", (f"-{dias} days",)
            )
            # O arquivo de busca guarda seis meses; depois disso some
            self.conexao.execute(
                "DELETE FROM noticias_busca WHERE link IN "
                "(SELECT link FROM noticias WHERE salva_em < datetime('now', ?))", (f"-{dias_arquivo} days",)
            )
            self.conexao.execute("DELETE FROM noticias WHERE salva_em < datetime('now', ?)", (f"-{dias_arquivo} days",))
            self.conexao.execute("DELETE FROM vetores WHERE link NOT IN (SELECT link FROM noticias)")

    def fechar(self) -> None:
        self.conexao.close()


@dataclass(frozen=True)
class Registro:
    """Notícia guardada no arquivo, como sai do banco."""
    link: str
    titulo: str
    resumo: str
    fonte: str
    plataformas: str
    data: str            # publicada_em ou, se faltar, salva_em (ISO)


def _linhas(cur) -> list[Registro]:
    return [Registro(*linha) for linha in cur]


_COLUNAS = "n.link, n.titulo, n.resumo, n.fonte, n.plataformas, COALESCE(n.publicada_em, n.salva_em)"


def buscar(banco: Banco, consulta_fts: str, dias: int = 30, limite: int = 8) -> list[Registro]:
    """Busca de texto (FTS5, ordenada por relevância) nas notícias dos últimos `dias`."""
    if not consulta_fts:
        return []
    cur = banco.conexao.execute(
        f"SELECT {_COLUNAS} FROM noticias_busca b JOIN noticias n ON n.link = b.link "
        "WHERE noticias_busca MATCH ? AND n.salva_em >= datetime('now', ?) "
        "ORDER BY bm25(noticias_busca) LIMIT ?",
        (consulta_fts, f"-{dias} days", limite),
    )
    return _linhas(cur)


def recentes(banco: Banco, dias: int = 7, limite: int = 200) -> list[Registro]:
    cur = banco.conexao.execute(
        f"SELECT {_COLUNAS} FROM noticias n WHERE n.salva_em >= datetime('now', ?) "
        "ORDER BY COALESCE(n.publicada_em, n.salva_em) DESC LIMIT ?",
        (f"-{dias} days", limite),
    )
    return _linhas(cur)


def copia_compactada(banco: Banco) -> bytes:
    """Cópia consistente do banco (API de backup do SQLite), compactada com gzip."""
    import gzip
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as pasta:
        destino = Path(pasta) / "gamebot.db"
        alvo = sqlite3.connect(destino)
        with alvo:
            banco.conexao.backup(alvo)
        alvo.close()
        return gzip.compress(destino.read_bytes())


def titulos_enviados(banco: Banco, tipo: str, dias: int) -> list[str]:
    cur = banco.conexao.execute(
        "SELECT titulo FROM enviados WHERE tipo = ? AND enviado_em >= datetime('now', ?)", (tipo, f"-{dias} days"))
    return [t for (t,) in cur]


def guardar_vetores(banco: Banco, modelo: str, itens: list[tuple[str, list[float]]]) -> None:
    from array import array
    with banco.conexao:
        banco.conexao.executemany("INSERT OR REPLACE INTO vetores VALUES (?, ?, ?)",
                                  [(link, modelo, array("f", v).tobytes()) for link, v in itens])


def vetores_recentes(banco: Banco, modelo: str, dias: int = 30) -> list[tuple[Registro, list[float]]]:
    from array import array
    cur = banco.conexao.execute(
        f"SELECT {_COLUNAS}, v.vetor FROM vetores v JOIN noticias n ON n.link = v.link "
        "WHERE v.modelo = ? AND n.salva_em >= datetime('now', ?)", (modelo, f"-{dias} days"))
    resultado = []
    for *colunas, blob in cur:
        vetor = array("f")
        vetor.frombytes(blob)
        resultado.append((Registro(*colunas), vetor.tolist()))
    return resultado

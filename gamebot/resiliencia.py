"""Cache com validade e circuit breaker, guardados no próprio SQLite.

- Cache: cada dado tem um tempo de vida diferente (a cotação muda todo dia, o menor
  preço histórico quase nunca), o que poupa chamadas e respeita os limites das APIs.
- Circuit breaker: depois de N falhas seguidas, a fonte fica "aberta" (em pausa) por um
  tempo; o bot nem tenta chamá-la até lá. Um sucesso zera a contagem.
"""
from __future__ import annotations

import json
import logging
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from gamebot.banco import Banco

log = logging.getLogger(__name__)


def _agora() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d %H:%M:%S")     # mesmo formato do datetime('now') do SQLite


class Cache:
    def __init__(self, banco: Banco, relogio: Callable[[], datetime] = _agora):
        self.banco, self.relogio = banco, relogio

    def ler(self, chave: str) -> Any | None:
        linha = self.banco.conexao.execute(
            "SELECT valor FROM cache WHERE chave = ? AND expira_em > ?", (chave, _iso(self.relogio()))).fetchone()
        return json.loads(linha[0]) if linha else None

    def gravar(self, chave: str, valor: Any, validade: timedelta) -> None:
        with self.banco.conexao:
            self.banco.conexao.execute("INSERT OR REPLACE INTO cache VALUES (?, ?, ?)",
                                       (chave, json.dumps(valor), _iso(self.relogio() + validade)))

    def obter(self, chave: str, validade: timedelta, buscar: Callable[[], Any]) -> Any:
        """Devolve do cache ou busca e guarda. Um resultado None não é guardado."""
        valor = self.ler(chave)
        if valor is not None:
            return valor
        valor = buscar()
        if valor is not None:
            self.gravar(chave, valor, validade)
        return valor


class Circuito:
    def __init__(self, banco: Banco, limite: int = 3, pausa: timedelta = timedelta(hours=6),
                 relogio: Callable[[], datetime] = _agora):
        self.banco, self.limite, self.pausa, self.relogio = banco, limite, pausa, relogio

    def permitido(self, fonte: str) -> bool:
        linha = self.banco.conexao.execute("SELECT aberto_ate FROM circuito WHERE fonte = ?", (fonte,)).fetchone()
        return not (linha and linha[0] and linha[0] > _iso(self.relogio()))

    def sucesso(self, fonte: str) -> None:
        with self.banco.conexao:
            self.banco.conexao.execute("DELETE FROM circuito WHERE fonte = ?", (fonte,))

    def falha(self, fonte: str) -> bool:
        """Registra uma falha. Devolve True se o circuito acabou de abrir (para alertar o dono)."""
        with self.banco.conexao:
            self.banco.conexao.execute(
                "INSERT INTO circuito (fonte, falhas) VALUES (?, 1) "
                "ON CONFLICT(fonte) DO UPDATE SET falhas = falhas + 1", (fonte,))
            falhas = self.banco.conexao.execute("SELECT falhas FROM circuito WHERE fonte = ?", (fonte,)).fetchone()[0]
            if falhas >= self.limite:
                self.banco.conexao.execute("UPDATE circuito SET falhas = 0, aberto_ate = ? WHERE fonte = ?",
                                           (_iso(self.relogio() + self.pausa), fonte))
                log.warning("Circuito aberto para %s por %s", fonte, self.pausa)
                return True
        return False

    def chamar(self, fonte: str, funcao: Callable[[], Any], vazio_e_falha: bool = True,
               avisos: list[str] | None = None) -> Any:
        """Executa `funcao` respeitando o circuito. Exceção ou resultado vazio contam como falha."""
        if not self.permitido(fonte):
            log.info("%s em pausa (circuit breaker), pulando", fonte)
            return None
        try:
            resultado = funcao()
        except Exception as erro:  # qualquer erro da fonte conta como falha
            log.warning("%s falhou: %s", fonte, erro)
            resultado = None
        if resultado or (resultado is not None and not vazio_e_falha):
            self.sucesso(fonte)
            return resultado
        if self.falha(fonte) and avisos is not None:
            horas = int(self.pausa.total_seconds() // 3600)
            avisos.append(f"{fonte} falhou {self.limite} vezes seguidas e ficou em pausa por {horas} h.")
        return resultado

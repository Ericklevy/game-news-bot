"""Junta as promoções com as informações extras: real, menor preço da história, histórico e grátis.

Tudo com cache e circuit breaker, para não gastar chamadas nem insistir numa fonte fora do ar.
"""
from __future__ import annotations

import logging
from dataclasses import replace
from datetime import timedelta

from gamebot.banco import Banco
from gamebot.models import Gratis, Promocao
from gamebot.resiliencia import Cache, Circuito
from gamebot.sources import cambio
from gamebot.sources import gratis as fonte_gratis
from gamebot.sources import promocoes as fonte_promocoes

log = logging.getLogger(__name__)
VALIDADE_COTACAO = timedelta(hours=6)
VALIDADE_GRATIS = timedelta(hours=3)
VALIDADE_HISTORICO = timedelta(days=7)


def cotacao(cache: Cache, circuito: Circuito, avisos: list[str] | None = None) -> float | None:
    return cache.obter("cotacao:USD-BRL", VALIDADE_COTACAO,
                       lambda: circuito.chamar("Frankfurter (câmbio)", cambio.dolar_em_reais, avisos=avisos))


def menores_precos(cache: Cache, circuito: Circuito, ids: list[str],
                   avisos: list[str] | None = None) -> dict[str, float]:
    resultado, faltam = {}, []
    for i in ids:
        valor = cache.ler(f"menor:{i}")
        if valor is None:
            faltam.append(i)
        else:
            resultado[i] = valor
    if faltam:
        novos = circuito.chamar("CheapShark (histórico)",
                                lambda: fonte_promocoes.menores_precos(faltam), avisos=avisos) or {}
        for i, valor in novos.items():
            cache.gravar(f"menor:{i}", valor, VALIDADE_HISTORICO)
        resultado.update(novos)
    return resultado


def registrar_precos(banco: Banco, promocoes: list[Promocao]) -> None:
    with banco.conexao:
        banco.conexao.executemany(
            "INSERT INTO precos VALUES (?, ?, ?, ?, datetime('now'))",
            [(p.jogo_id, p.jogo, p.loja, p.preco_promocional) for p in promocoes if p.jogo_id])


def precos_anteriores(banco: Banco, ids: list[str], dias: int = 30) -> dict[str, float]:
    """Maior preço que o bot já viu de cada jogo nos últimos dias (antes de hoje)."""
    if not ids:
        return {}
    marcas = ",".join("?" * len(ids))
    linhas = banco.conexao.execute(
        f"SELECT jogo, MAX(preco) FROM precos WHERE jogo IN ({marcas}) "
        f"AND visto_em >= datetime('now', ?) AND visto_em < datetime('now', 'start of day') GROUP BY jogo",
        [*ids, f"-{dias} days"]).fetchall()
    return {j: p for j, p in linhas}


def enriquecer(banco: Banco, promocoes: list[Promocao], avisos: list[str] | None = None,
               registrar: bool = True) -> list[Promocao]:
    if not promocoes:
        return promocoes
    cache, circuito = Cache(banco), Circuito(banco)
    ids = [p.jogo_id for p in promocoes if p.jogo_id]
    taxa = cotacao(cache, circuito, avisos)
    menores = menores_precos(cache, circuito, ids, avisos)
    anteriores = precos_anteriores(banco, ids)
    em_dolar = [p for p in promocoes if p.moeda == "USD"]
    if registrar:
        registrar_precos(banco, em_dolar)
    saida = []
    for p in promocoes:
        anterior = anteriores.get(p.jogo_id)
        saida.append(replace(
            p, cotacao_brl=taxa if p.moeda == "USD" else None, menor_preco=menores.get(p.jogo_id),
            preco_anterior=anterior if anterior and anterior > p.preco_promocional + 0.01 else None))
    return saida


def jogos_gratis(banco: Banco, limite: int = 4, avisos: list[str] | None = None) -> list[Gratis]:
    cache, circuito = Cache(banco), Circuito(banco)
    dados = cache.obter("gratis:game", VALIDADE_GRATIS, lambda: _gratis_json(circuito, limite, avisos))
    return [Gratis(**d) for d in dados or []]


def _gratis_json(circuito: Circuito, limite: int, avisos):
    lista = circuito.chamar("GamerPower (grátis)", lambda: fonte_gratis.buscar("game", limite),
                            vazio_e_falha=False, avisos=avisos)
    return None if lista is None else [g.__dict__ for g in lista]

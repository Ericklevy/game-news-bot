"""Ponto de entrada: python -m gamebot [--dry-run] [--config config.yaml]"""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime, timedelta, timezone

from gamebot import filtros, ia, resumo, telegram
from gamebot.banco import Banco
from gamebot.config import Config, carregar
from gamebot.models import Noticia, Promocao
from gamebot.sources import promocoes as fonte_promocoes
from gamebot.sources.rss import ler_feed

log = logging.getLogger("gamebot")


def coletar_noticias(cfg: Config, agora: datetime) -> tuple[list[Noticia], list[Noticia]]:
    """Devolve (candidatas ao resumo, todas as recentes para o arquivo de busca)."""
    todas: list[Noticia] = []
    for nome, url in cfg.feeds.items():
        todas.extend(ler_feed(nome, url, cfg.plataforma_por_feed.get(nome)))
    limite = agora - timedelta(hours=cfg.janela_horas)
    recentes = [n for n in todas if n.publicada_em is None or n.publicada_em >= limite]
    recentes.sort(key=lambda n: n.publicada_em or agora, reverse=True)
    recentes = filtros.sem_bloqueadas(recentes, cfg.palavras_bloqueadas)
    recentes = filtros.por_plataforma(recentes, cfg.plataformas, cfg.incluir_gerais)
    # O arquivo guarda também as repetidas: o /semana conta em quantos sites cada assunto saiu
    return filtros.sem_repetidas(recentes), recentes


def coletar_promocoes(cfg: Config) -> list[Promocao]:
    if not cfg.promocoes_ativas or "PC" not in cfg.plataformas:
        return []
    return fonte_promocoes.buscar(cfg.desconto_minimo, cfg.nota_minima)


def executar(cfg: Config, dry_run: bool = False, agora: datetime | None = None) -> str:
    agora = agora or datetime.now(timezone.utc)
    banco = Banco(cfg.banco)
    try:
        noticias, para_arquivo = coletar_noticias(cfg, agora)
        promocoes = coletar_promocoes(cfg)
        if not dry_run:
            novas = banco.arquivar(para_arquivo, substituir=False)
            log.info("Arquivo de busca: %d notícias novas guardadas", novas)

        # Só o que ainda não foi enviado em dias anteriores
        vistos = banco.ja_enviados([n.link for n in noticias] + [p.link for p in promocoes])
        noticias = filtros.limitar_por_fonte([n for n in noticias if n.link not in vistos], cfg.max_por_fonte)
        noticias = noticias[: cfg.max_noticias]
        promocoes = [p for p in promocoes if p.link not in vistos][: cfg.max_promocoes]

        # Traduz só o que vai ser enviado (uma chamada de IA por dia)
        if cfg.ia.get("ativo", True):
            noticias = ia.traduzir(noticias, ia.montar_provedores(cfg.ia))

        texto = resumo.montar(noticias, promocoes, agora.date())
        if dry_run:
            print(texto)
            return texto

        if not cfg.telegram_token or not cfg.telegram_chat_id:
            raise SystemExit("Defina TELEGRAM_TOKEN e TELEGRAM_CHAT_ID (ou use --dry-run).")
        telegram.enviar(cfg.telegram_token, cfg.telegram_chat_id, texto)
        banco.marcar([(n.link, "noticia", n.titulo) for n in noticias] +
                     [(p.link, "promocao", p.jogo) for p in promocoes])
        banco.arquivar(noticias)
        banco.limpar_antigos()
        return texto
    finally:
        banco.fechar()


def _com_banco(cfg: Config, uso):
    banco = Banco(cfg.banco)
    try:
        return uso(banco)
    finally:
        banco.fechar()


def escutar(cfg: Config) -> None:
    from datetime import time as hora_do_dia

    from gamebot import assistente
    from gamebot.escuta import Escuta

    provedores = ia.montar_provedores(cfg.ia)

    if not cfg.telegram_token or not cfg.telegram_chat_id:
        raise SystemExit("Defina TELEGRAM_TOKEN e TELEGRAM_CHAT_ID.")
    from pathlib import Path

    h, m = (int(x) for x in cfg.hora_diaria.split(":"))
    marca = Path(cfg.banco).with_name("ultimo_diario.txt")
    marca.parent.mkdir(parents=True, exist_ok=True)
    Escuta(
        ultimo_diario=marca.read_text().strip() if marca.exists() else None,
        salvar_diario=marca.write_text,
        chat_autorizado=cfg.telegram_admin_id,
        buscar=lambda offset: telegram.atualizacoes(cfg.telegram_token, offset),
        responder=lambda chat, texto: telegram.enviar(cfg.telegram_token, chat, texto),
        rodar_resumo=lambda: executar(cfg),
        destino=cfg.telegram_chat_id,
        perguntar=lambda texto: _com_banco(cfg, lambda b: assistente.perguntar(texto, b, provedores)),
        semana=lambda: _com_banco(cfg, lambda b: assistente.semana(b, provedores)),
        hora_diaria=hora_do_dia(h, m),
    ).rodar()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Resumo diário de notícias e promoções de games no Telegram.")
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--dry-run", action="store_true", help="mostra o resumo no terminal sem enviar")
    parser.add_argument("--escutar", action="store_true",
                        help="fica ligado respondendo comandos e manda o resumo diário (modo servidor)")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    try:
        cfg = carregar(args.config)
        if args.escutar:
            escutar(cfg)
            return 0
        executar(cfg, dry_run=args.dry_run)
    except telegram.ErroTelegram as erro:
        log.error("%s", erro)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

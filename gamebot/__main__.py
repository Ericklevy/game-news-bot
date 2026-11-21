"""Ponto de entrada: python -m gamebot [--dry-run] [--config config.yaml]"""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime, timedelta, timezone

from gamebot import filtros, resumo, telegram
from gamebot.banco import Banco
from gamebot.config import Config, carregar
from gamebot.models import Noticia, Promocao
from gamebot.sources import promocoes as fonte_promocoes
from gamebot.sources.rss import ler_feed

log = logging.getLogger("gamebot")


def coletar_noticias(cfg: Config, agora: datetime) -> list[Noticia]:
    todas: list[Noticia] = []
    for nome, url in cfg.feeds.items():
        todas.extend(ler_feed(nome, url))
    limite = agora - timedelta(hours=cfg.janela_horas)
    recentes = [n for n in todas if n.publicada_em is None or n.publicada_em >= limite]
    recentes.sort(key=lambda n: n.publicada_em or agora, reverse=True)
    recentes = filtros.sem_bloqueadas(recentes, cfg.palavras_bloqueadas)
    recentes = filtros.por_plataforma(recentes, cfg.plataformas, cfg.incluir_gerais)
    return filtros.sem_repetidas(recentes)


def coletar_promocoes(cfg: Config) -> list[Promocao]:
    if not cfg.promocoes_ativas or "PC" not in cfg.plataformas:
        return []
    return fonte_promocoes.buscar(cfg.desconto_minimo, cfg.nota_minima)


def executar(cfg: Config, dry_run: bool = False, agora: datetime | None = None) -> str:
    agora = agora or datetime.now(timezone.utc)
    banco = Banco(cfg.banco)
    try:
        noticias = coletar_noticias(cfg, agora)
        promocoes = coletar_promocoes(cfg)

        # Só o que ainda não foi enviado em dias anteriores
        vistos = banco.ja_enviados([n.link for n in noticias] + [p.link for p in promocoes])
        noticias = [n for n in noticias if n.link not in vistos][: cfg.max_noticias]
        promocoes = [p for p in promocoes if p.link not in vistos][: cfg.max_promocoes]

        texto = resumo.montar(noticias, promocoes, agora.date())
        if dry_run:
            print(texto)
            return texto

        if not cfg.telegram_token or not cfg.telegram_chat_id:
            raise SystemExit("Defina TELEGRAM_TOKEN e TELEGRAM_CHAT_ID (ou use --dry-run).")
        telegram.enviar(cfg.telegram_token, cfg.telegram_chat_id, texto)
        banco.marcar([(n.link, "noticia", n.titulo) for n in noticias] +
                     [(p.link, "promocao", p.jogo) for p in promocoes])
        banco.limpar_antigos()
        return texto
    finally:
        banco.fechar()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Resumo diário de notícias e promoções de games no Telegram.")
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--dry-run", action="store_true", help="mostra o resumo no terminal sem enviar")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    try:
        executar(carregar(args.config), dry_run=args.dry_run)
    except telegram.ErroTelegram as erro:
        log.error("%s", erro)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

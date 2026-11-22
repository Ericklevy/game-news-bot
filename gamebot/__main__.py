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


def coletar_noticias(cfg: Config, agora: datetime,
                     avisos: list[str] | None = None) -> tuple[list[Noticia], list[Noticia]]:
    """Devolve (candidatas ao resumo, todas as recentes para o arquivo de busca)."""
    todas: list[Noticia] = []
    for nome, url in cfg.feeds.items():
        lidas = ler_feed(nome, url, cfg.plataforma_por_feed.get(nome))
        if not lidas and avisos is not None:
            avisos.append(f"A fonte {nome} não respondeu ou veio vazia.")
        todas.extend(lidas)
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


def executar(cfg: Config, dry_run: bool = False, agora: datetime | None = None,
             avisos: list[str] | None = None) -> str:
    """Coleta, filtra, traduz e publica. Problemas encontrados vão para `avisos` (para alertar o dono)."""
    agora = agora or datetime.now(timezone.utc)
    avisos = avisos if avisos is not None else []
    banco = Banco(cfg.banco)
    try:
        noticias, para_arquivo = coletar_noticias(cfg, agora, avisos)
        promocoes = coletar_promocoes(cfg)
        if not promocoes and cfg.promocoes_ativas and "PC" in cfg.plataformas:
            avisos.append("As promoções (CheapShark) não responderam ou vieram vazias.")
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
            provedores = ia.montar_provedores(cfg.ia)
            noticias = ia.traduzir(noticias, provedores)
            if noticias and any(p.chave for p in provedores) and not any(n.traduzida for n in noticias):
                avisos.append("A tradução falhou em todos os provedores de IA: o resumo saiu em inglês.")

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


def _hora(texto: str):
    from datetime import time as hora_do_dia
    h, m = (int(x) for x in texto.strip().split(":"))
    return hora_do_dia(h, m)


def escutar(cfg: Config) -> None:
    from pathlib import Path

    from gamebot import assistente
    from gamebot.escuta import COMANDOS, DIAS, Escuta

    if not cfg.telegram_token or not cfg.telegram_chat_id:
        raise SystemExit("Defina TELEGRAM_TOKEN e TELEGRAM_CHAT_ID.")
    provedores = ia.montar_provedores(cfg.ia)
    token, dono, canal = cfg.telegram_token, cfg.telegram_admin_id, cfg.telegram_chat_id

    def responder(chat: str, texto: str) -> None:
        telegram.enviar(token, chat, texto)

    # Alertas: cada problema é avisado no chat do dono no máximo uma vez por dia
    alertados: set[tuple[str, str]] = set()

    def publicar_resumo() -> str:
        avisos: list[str] = []
        texto = executar(cfg, avisos=avisos)
        hoje = datetime.now(timezone.utc).date().isoformat()
        novos = [a for a in avisos if (hoje, a) not in alertados]
        if novos:
            alertados.update((hoje, a) for a in novos)
            responder(dono, "⚠️ <b>Alerta do bot</b>\n" + "\n".join(f"• {a}" for a in novos))
        return texto

    def promocoes() -> str:
        return resumo.montar_promocoes(coletar_promocoes(cfg)[: cfg.max_promocoes])

    semanal = None
    if cfg.semanal.get("ativo"):
        semanal = (DIAS.index(str(cfg.semanal.get("dia", "domingo")).lower()), _hora(cfg.semanal.get("hora", "10:17")))

    # Agenda salva em arquivo, para um reinício não repetir publicações
    arquivo = Path(cfg.banco).with_name("agenda_feitos.txt")
    feitos = set(arquivo.read_text().split("\n")) - {""} if arquivo.exists() else set()

    try:
        telegram.definir_comandos(token, COMANDOS, chat_id=dono)
    except (telegram.ErroTelegram, Exception) as erro:  # o menu é só conveniência
        log.warning("Menu de comandos não foi cadastrado: %s", erro)

    Escuta(
        chat_autorizado=dono,
        buscar=lambda offset: telegram.atualizacoes(token, offset),
        responder=responder,
        rodar_resumo=publicar_resumo,
        horarios=[_hora(h) for h in cfg.horarios_diarios],
        semanal=semanal,
        publicar_semana=lambda: responder(canal, _com_banco(cfg, lambda b: assistente.semana(b, provedores))),
        feitos=feitos,
        salvar_feitos=lambda f: arquivo.write_text("\n".join(sorted(f))),
        destino=canal,
        perguntar=lambda texto: _com_banco(cfg, lambda b: assistente.perguntar(texto, b, provedores)),
        semana=lambda: _com_banco(cfg, lambda b: assistente.semana(b, provedores)),
        promocoes=promocoes,
        roteiro=lambda: _com_banco(cfg, lambda b: assistente.roteiro(b, provedores, coletar_promocoes(cfg))),
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

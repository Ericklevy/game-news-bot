"""Monta a mensagem do resumo diário em HTML do Telegram."""
from __future__ import annotations

from datetime import date
from html import escape

from gamebot.models import Noticia, Promocao

EMOJI = {"PC": "🖥️", "PlayStation": "🎮", "Xbox": "🟩", "Nintendo": "🍄"}
LIMITE_TELEGRAM = 4096


def _plataformas(itens: frozenset[str]) -> str:
    return " ".join(EMOJI[p] for p in sorted(itens) if p in EMOJI) or "🌐"


def _usd(valor_usd: float) -> str:
    return f"US$ {valor_usd:,.2f}"


def montar(noticias: list[Noticia], promocoes: list[Promocao], dia: date | None = None) -> str:
    dia = dia or date.today()
    partes = [f"<b>🕹️ Resumo gamer · {dia:%d/%m/%Y}</b>"]

    if noticias:
        partes.append("<b>📰 Notícias</b>")
        for n in noticias:
            partes.append(
                f"{_plataformas(n.plataformas)} <a href=\"{escape(n.link, quote=True)}\">{escape(n.titulo)}</a>"
                f"\n<i>{escape(n.fonte)}</i>"
            )

    if promocoes:
        partes.append("<b>💸 Promoções no PC</b>")
        for p in promocoes:
            preco = "<b>GRÁTIS</b>" if p.gratis else f"<b>{_usd(p.preco_promocional)}</b> <s>{_usd(p.preco_normal)}</s>"
            nota = f" · Metacritic {p.nota_metacritic}" if p.nota_metacritic else ""
            partes.append(
                f"<a href=\"{escape(p.link, quote=True)}\">{escape(p.jogo)}</a>{'' if p.gratis else f' · -{p.desconto}%'}\n"
                f"{preco} na {escape(p.loja)}{nota}"
            )

    if not noticias and not promocoes:
        partes.append("Nada novo hoje. Volto amanhã! 👋")

    return "\n\n".join(partes)


def dividir(texto: str, limite: int = LIMITE_TELEGRAM) -> list[str]:
    """Quebra a mensagem em blocos que cabem no Telegram, sem cortar um item no meio."""
    blocos, atual = [], ""
    for item in texto.split("\n\n"):
        candidato = f"{atual}\n\n{item}" if atual else item
        if len(candidato) <= limite:
            atual = candidato
            continue
        if atual:
            blocos.append(atual)
        atual = item[:limite]
    if atual:
        blocos.append(atual)
    return blocos

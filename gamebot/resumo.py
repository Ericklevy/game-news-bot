"""Monta a mensagem do resumo diário em HTML do Telegram."""
from __future__ import annotations

from datetime import date
from html import escape

from gamebot.models import Gratis, Noticia, Promocao

EMOJI = {"PC": "🖥️", "PlayStation": "🎮", "Xbox": "🟩", "Nintendo": "🍄"}
LIMITE_TELEGRAM = 4096


def _plataformas(itens: frozenset[str]) -> str:
    return " ".join(EMOJI[p] for p in sorted(itens) if p in EMOJI) or "🌐"


def _usd(valor_usd: float) -> str:
    return f"US$ {valor_usd:,.2f}"


def _brl(valor_brl: float) -> str:
    return "R$ " + f"{valor_brl:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _extras(p: Promocao) -> str:
    itens = []
    if p.cotacao_brl and not p.gratis:
        itens.append(f"≈ {_brl(p.preco_promocional * p.cotacao_brl)}")
    if p.menor_da_historia:
        itens.append("🔥 menor preço da história")
    elif p.menor_preco is not None:
        itens.append(f"menor já visto: {_usd(p.menor_preco)}")
    if p.preco_anterior:
        itens.append(f"📉 caiu de {_usd(p.preco_anterior)}")
    return ("\n" + " · ".join(itens)) if itens else ""


def _gratis(g: Gratis) -> str:
    fim = f" · até {g.termina_em[8:10]}/{g.termina_em[5:7]}" if g.termina_em else ""
    valor = f" <s>{escape(g.valor)}</s>" if g.valor else ""
    return (f"<a href=\"{escape(g.link, quote=True)}\">{escape(g.titulo)}</a>{valor}\n"
            f"<i>{escape(g.plataformas)}</i>{fim}")


def montar(noticias: list[Noticia], promocoes: list[Promocao], dia: date | None = None,
           gratis: list[Gratis] | None = None) -> str:
    dia = dia or date.today()
    partes = [f"<b>🕹️ Resumo gamer · {dia:%d/%m/%Y}</b>"]

    if noticias:
        partes.append("<b>📰 Notícias</b>")
        for n in noticias:
            partes.append(
                f"{_plataformas(n.plataformas)} <a href=\"{escape(n.link, quote=True)}\">{escape(n.titulo)}</a>"
                + (f"\n{escape(n.resumo)}" if n.traduzida and n.resumo else "")
                + f"\n<i>{escape(n.fonte)}</i>"
            )

    if promocoes:
        partes.append("<b>💸 Promoções no PC</b>")
        for p in promocoes:
            preco = "<b>GRÁTIS</b>" if p.gratis else f"<b>{_usd(p.preco_promocional)}</b> <s>{_usd(p.preco_normal)}</s>"
            nota = f" · Metacritic {p.nota_metacritic}" if p.nota_metacritic else ""
            partes.append(
                f"<a href=\"{escape(p.link, quote=True)}\">{escape(p.jogo)}</a>{'' if p.gratis else f' · -{p.desconto}%'}\n"
                f"{preco}{'' if p.loja == 'Loja' else ' na ' + escape(p.loja)}{nota}{_extras(p)}"
            )

    if gratis:
        partes.append("<b>🎁 Grátis para resgatar</b> <i>(via GamerPower)</i>")
        partes.extend(_gratis(g) for g in gratis)

    if not noticias and not promocoes and not gratis:
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


def montar_promocoes(promocoes: list[Promocao], gratis: list[Gratis] | None = None) -> str:
    """Mensagem do /promocoes: só as ofertas, sem notícias e sem IA."""
    if not promocoes and not gratis:
        return "💸 Nenhuma promoção boa agora (ou a loja de ofertas não respondeu). Tente mais tarde."
    texto = montar([], promocoes, gratis=gratis)
    return texto.split("\n\n", 1)[1]   # tira o cabeçalho do resumo diário

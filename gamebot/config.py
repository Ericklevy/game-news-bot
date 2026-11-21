"""Lê o config.yaml e as variáveis de ambiente (segredos nunca ficam no YAML)."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class Config:
    feeds: dict[str, str]
    plataformas: set[str] = field(default_factory=lambda: {"PC", "PlayStation", "Xbox", "Nintendo"})
    incluir_gerais: bool = True
    max_noticias: int = 8
    max_promocoes: int = 6
    janela_horas: int = 30
    palavras_bloqueadas: list[str] = field(default_factory=list)
    promocoes_ativas: bool = True
    desconto_minimo: int = 60
    nota_minima: int = 75
    telegram_token: str = ""
    telegram_chat_id: str = ""
    banco: str = "data/gamebot.db"
    max_por_fonte: int = 3
    plataforma_por_feed: dict[str, str] = field(default_factory=dict)
    ia: dict = field(default_factory=dict)


def carregar(caminho: str | Path = "config.yaml") -> Config:
    dados = yaml.safe_load(Path(caminho).read_text(encoding="utf-8")) or {}
    promo = dados.get("promocoes") or {}
    # Cada feed pode ser só a URL ou {url: ..., plataforma: PC}
    feeds, plataforma_por_feed = {}, {}
    for nome, valor in (dados.get("feeds") or {}).items():
        if isinstance(valor, dict):
            feeds[nome] = valor["url"]
            if valor.get("plataforma"):
                plataforma_por_feed[nome] = valor["plataforma"]
        else:
            feeds[nome] = valor
    return Config(
        feeds=feeds,
        plataforma_por_feed=plataforma_por_feed,
        max_por_fonte=int(dados.get("max_por_fonte", 3)),
        ia=dados.get("ia") or {},
        plataformas=set(dados.get("plataformas") or []),
        incluir_gerais=bool(dados.get("incluir_gerais", True)),
        max_noticias=int(dados.get("max_noticias", 8)),
        max_promocoes=int(dados.get("max_promocoes", 6)),
        janela_horas=int(dados.get("janela_horas", 30)),
        palavras_bloqueadas=list(dados.get("palavras_bloqueadas") or []),
        promocoes_ativas=bool(promo.get("ativo", True)),
        desconto_minimo=int(promo.get("desconto_minimo", 60)),
        nota_minima=int(promo.get("nota_metacritic_minima", 75)),
        telegram_token=os.getenv("TELEGRAM_TOKEN", ""),
        telegram_chat_id=os.getenv("TELEGRAM_CHAT_ID", ""),
        banco=os.getenv("GAMEBOT_DB", "data/gamebot.db"),
    )

"""Envio de mensagens pela API de bots do Telegram."""
from __future__ import annotations

import logging
import time

import requests

from gamebot.resumo import dividir

log = logging.getLogger(__name__)
API = "https://api.telegram.org/bot{token}/sendMessage"


class ErroTelegram(RuntimeError):
    pass


def enviar(token: str, chat_id: str, texto: str, sessao: requests.Session | None = None) -> int:
    """Envia o texto (em quantos blocos forem precisos). Retorna quantas mensagens saíram."""
    sessao = sessao or requests.Session()
    enviadas = 0
    for bloco in dividir(texto):
        resp = sessao.post(API.format(token=token), timeout=20, json={
            "chat_id": chat_id,
            "text": bloco,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        })
        corpo = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
        if not corpo.get("ok"):
            # Nunca loga o token: só o código e a descrição devolvidos pelo Telegram
            raise ErroTelegram(f"Telegram recusou a mensagem ({resp.status_code}): {corpo.get('description', 'sem detalhe')}")
        enviadas += 1
        time.sleep(0.5)  # respeita o limite de mensagens por segundo
    log.info("Telegram: %d mensagem(ns) enviada(s)", enviadas)
    return enviadas


def atualizacoes(token: str, offset: int | None, espera: int = 50,
                 sessao: requests.Session | None = None) -> list[dict]:
    """Busca mensagens novas por long polling (a conexão fica aberta até `espera` segundos)."""
    sessao = sessao or requests.Session()
    params = {"timeout": espera, "allowed_updates": '["message"]'}
    if offset is not None:
        params["offset"] = offset
    resp = sessao.get(API.format(token=token).replace("sendMessage", "getUpdates"),
                      params=params, timeout=espera + 15)
    corpo = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
    if not corpo.get("ok"):
        raise ErroTelegram(f"getUpdates falhou ({resp.status_code}): {corpo.get('description', 'sem detalhe')}")
    return corpo.get("result", [])


def definir_comandos(token: str, comandos: list[tuple[str, str]], chat_id: str | None = None,
                     sessao: requests.Session | None = None) -> None:
    """Cadastra o menu que aparece ao digitar "/" no Telegram (só no chat do dono, se chat_id vier)."""
    import json
    sessao = sessao or requests.Session()
    corpo = {"commands": [{"command": c, "description": d} for c, d in comandos]}
    if chat_id:
        corpo["scope"] = {"type": "chat", "chat_id": chat_id}
    resp = sessao.post(API.format(token=token).replace("sendMessage", "setMyCommands"),
                       data={k: json.dumps(v) for k, v in corpo.items()}, timeout=20)
    if not (resp.headers.get("content-type", "").startswith("application/json") and resp.json().get("ok")):
        raise ErroTelegram(f"setMyCommands falhou ({resp.status_code})")

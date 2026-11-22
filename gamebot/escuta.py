"""Modo servidor: fica ligado, responde comandos no Telegram e manda o resumo diário.

Pensado para rodar 24 horas numa máquina como a Oracle Cloud Always Free:
    python -m gamebot --escutar
"""
from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, time as hora_do_dia
from zoneinfo import ZoneInfo

log = logging.getLogger(__name__)

AJUDA = (
    "🕹️ <b>Resumo Gamer</b>\n\n"
    "/agora — publica as novidades deste momento\n"
    "/status — quando foi o último resumo\n"
    "/ajuda — esta mensagem\n\n"
    "Todo dia às {hora} o resumo chega sozinho."
)


@dataclass
class Escuta:
    """Laço principal. As dependências entram por parâmetro para dar para testar sem rede."""
    chat_autorizado: str
    buscar: Callable[[int | None], list[dict]]          # offset -> atualizações do Telegram
    responder: Callable[[str, str], None]                 # (chat_id, texto)
    rodar_resumo: Callable[[], str]                       # envia o resumo e devolve o texto
    hora_diaria: hora_do_dia = hora_do_dia(8, 17)
    fuso: ZoneInfo = field(default_factory=lambda: ZoneInfo("America/Sao_Paulo"))
    relogio: Callable[[], datetime] = field(default=None)  # type: ignore[assignment]
    ultimo_diario: str | None = None                       # data (AAAA-MM-DD) do último resumo automático
    ultimo_envio: datetime | None = None
    offset: int | None = None
    salvar_diario: Callable[[str], None] = lambda data: None   # guarda a data para sobreviver a reinícios
    destino: str = ""                                          # onde o resumo é publicado (para avisar o dono)

    def __post_init__(self):
        if self.relogio is None:
            self.relogio = lambda: datetime.now(self.fuso)

    # ---------- resumo diário ----------
    def hora_do_diario(self) -> bool:
        agora = self.relogio()
        return agora.time() >= self.hora_diaria and self.ultimo_diario != agora.date().isoformat()

    def enviar_resumo(self, motivo: str) -> None:
        log.info("Enviando resumo (%s)", motivo)
        self.rodar_resumo()
        self.ultimo_envio = self.relogio()

    # ---------- comandos ----------
    def tratar(self, atualizacao: dict) -> None:
        msg = atualizacao.get("message") or {}
        chat = str((msg.get("chat") or {}).get("id", ""))
        texto = (msg.get("text") or "").strip()
        if not chat or not texto.startswith("/"):
            return
        comando = texto.split()[0].split("@")[0].lower()

        if chat != self.chat_autorizado:
            # Bot pessoal: estranhos não gastam a cota da IA nem do Telegram
            log.info("Comando %s ignorado de um chat não autorizado", comando)
            self.responder(chat, "Este é um bot pessoal. 🙂")
            return

        if comando in ("/start", "/ajuda", "/help"):
            self.responder(chat, AJUDA.format(hora=self.hora_diaria.strftime("%Hh%M")))
        elif comando == "/agora":
            self.responder(chat, "🔎 Buscando as novidades…")
            self.enviar_resumo("pedido no /agora")
            if self.destino and self.destino != chat:
                self.responder(chat, f"✅ Resumo publicado em {self.destino}.")
        elif comando == "/status":
            if self.ultimo_envio:
                quando = self.ultimo_envio.astimezone(self.fuso).strftime("%d/%m às %Hh%M")
                self.responder(chat, f"✅ Estou no ar. Último resumo: {quando}.")
            else:
                self.responder(chat, "✅ Estou no ar. Ainda não mandei nenhum resumo desde que liguei.")
        else:
            self.responder(chat, "Não conheço esse comando. Use /ajuda.")

    # ---------- laço ----------
    def passo(self) -> None:
        """Uma volta do laço: confere o horário do diário e trata as mensagens novas."""
        if self.hora_do_diario():
            self.ultimo_diario = self.relogio().date().isoformat()
            self.salvar_diario(self.ultimo_diario)
            try:
                self.enviar_resumo("diário")
            except Exception:
                log.exception("Resumo diário falhou")
                self.responder(self.chat_autorizado, "⚠️ O resumo de hoje falhou. Use /agora para tentar de novo.")

        for atualizacao in self.buscar(self.offset):
            self.offset = atualizacao["update_id"] + 1
            try:
                self.tratar(atualizacao)
            except Exception:  # um comando com erro não pode derrubar o bot
                log.exception("Erro ao tratar comando")
                self.responder(self.chat_autorizado, "⚠️ Deu erro ao montar o resumo. Tento de novo depois.")

    def rodar(self) -> None:
        log.info("Bot escutando comandos. Resumo diário às %s.", self.hora_diaria.strftime("%H:%M"))
        while True:
            try:
                self.passo()
            except Exception:
                log.exception("Falha no laço; tentando de novo em 15 s")
                time.sleep(15)

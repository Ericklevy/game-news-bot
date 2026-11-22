"""Modo servidor: fica ligado, responde comandos no Telegram e publica no horário.

Pensado para rodar 24 horas numa máquina como a Oracle Cloud Always Free:
    python -m gamebot --escutar

Agenda:
  - resumo nos horários de `horarios` (ex.: 08:17, 13:17, 19:17);
  - ranking da semana publicado no canal no dia/hora de `semanal`.
Cada publicação feita é anotada em `feitos` (e salva em arquivo), para não repetir depois de um reinício.
"""
from __future__ import annotations

import logging
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta, time as hora_do_dia
from zoneinfo import ZoneInfo

log = logging.getLogger(__name__)

DIAS = ["segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo"]

# (comando, descrição) — aparece no /ajuda e no menu "/" do Telegram
COMANDOS = [
    ("agora", "Publica no canal as novidades deste momento"),
    ("promocoes", "Mostra as promoções de PC agora (sem IA)"),
    ("perguntar", "Responde com base nas notícias guardadas"),
    ("semana", "Ranking dos assuntos mais falados na semana"),
    ("roteiro", "Rascunho de roteiro de vídeo com a semana"),
    ("status", "Mostra se o bot está no ar e a agenda"),
    ("ajuda", "Lista os comandos"),
]


def _hhmm(h: hora_do_dia) -> str:
    return h.strftime("%Hh%M")


@dataclass
class Escuta:
    """Laço principal. As dependências entram por parâmetro para dar para testar sem rede."""
    chat_autorizado: str
    buscar: Callable[[int | None], list[dict]]          # offset -> atualizações do Telegram
    responder: Callable[[str, str], None]                 # (chat_id, texto)
    rodar_resumo: Callable[[], str]                       # publica o resumo e devolve o texto
    horarios: list[hora_do_dia] = field(default_factory=lambda: [hora_do_dia(8, 17)])
    semanal: tuple[int, hora_do_dia] | None = None        # (dia da semana 0=segunda..6=domingo, hora)
    publicar_semana: Callable[[], None] | None = None     # publica o ranking no canal
    fuso: ZoneInfo = field(default_factory=lambda: ZoneInfo("America/Sao_Paulo"))
    relogio: Callable[[], datetime] = field(default=None)  # type: ignore[assignment]
    feitos: set[str] = field(default_factory=set)        # "2026-11-22 08:17", "semana 2026-11-22"
    salvar_feitos: Callable[[set[str]], None] = lambda feitos: None
    ultimo_envio: datetime | None = None
    offset: int | None = None
    destino: str = ""                                      # onde o resumo é publicado (para avisar o dono)
    perguntar: Callable[[str], str] | None = None
    semana: Callable[[], str] | None = None
    promocoes: Callable[[], str] | None = None
    roteiro: Callable[[], str] | None = None

    def __post_init__(self):
        if self.relogio is None:
            self.relogio = lambda: datetime.now(self.fuso)
        self.horarios = sorted(self.horarios)
        if not self.feitos:
            # Primeira vez ligado: o que já passou hoje não é disparado de uma vez
            agora = self.relogio()
            self.feitos = {self._chave(agora, h) for h in self.horarios if agora.time() >= h}

    # ---------- agenda ----------
    @staticmethod
    def _chave(agora: datetime, h: hora_do_dia) -> str:
        return f"{agora.date().isoformat()} {h:%H:%M}"

    def _anotar(self, chaves: set[str]) -> None:
        limite = (self.relogio().date() - timedelta(days=8)).isoformat()
        # A data fica no começo ("2026-11-22 08:17") ou no fim ("semana 2026-11-22") da chave
        self.feitos = {c for c in self.feitos | chaves if (re.search(r"\d{4}-\d{2}-\d{2}", c) or [""])[0] >= limite}
        self.salvar_feitos(self.feitos)

    def agenda_do_momento(self) -> None:
        agora = self.relogio()
        # Resumo: se vários horários passaram (ex.: bot desligado), publica uma vez só
        pendentes = {self._chave(agora, h) for h in self.horarios if agora.time() >= h} - self.feitos
        if pendentes:
            self._anotar(pendentes)
            try:
                self.enviar_resumo("horário agendado")
            except Exception:
                log.exception("Resumo agendado falhou")
                self.responder(self.chat_autorizado, "⚠️ O resumo agendado falhou. Use /agora para tentar de novo.")

        if self.semanal and self.publicar_semana:
            dia, hora = self.semanal
            chave = f"semana {agora.date().isoformat()}"
            if agora.weekday() == dia and agora.time() >= hora and chave not in self.feitos:
                self._anotar({chave})
                try:
                    self.publicar_semana()
                except Exception:
                    log.exception("Ranking semanal falhou")
                    self.responder(self.chat_autorizado, "⚠️ O ranking da semana falhou. Use /semana para ver.")

    def enviar_resumo(self, motivo: str) -> None:
        log.info("Enviando resumo (%s)", motivo)
        self.rodar_resumo()
        self.ultimo_envio = self.relogio()

    def texto_agenda(self) -> str:
        horas = ", ".join(_hhmm(h) for h in self.horarios)
        texto = f"Resumo todo dia às {horas}."
        if self.semanal:
            texto += f"\nRanking da semana no canal: {DIAS[self.semanal[0]]} às {_hhmm(self.semanal[1])}."
        return texto

    # ---------- comandos ----------
    def tratar(self, atualizacao: dict) -> None:
        msg = atualizacao.get("message") or {}
        chat = str((msg.get("chat") or {}).get("id", ""))
        texto = (msg.get("text") or "").strip()
        if not chat or not texto.startswith("/"):
            return
        comando = texto.split()[0].split("@")[0].lower()
        argumento = texto[len(texto.split()[0]):].strip()

        if chat != self.chat_autorizado:
            # Bot pessoal: estranhos não gastam a cota da IA nem do Telegram
            log.info("Comando %s ignorado de um chat não autorizado", comando)
            self.responder(chat, "Este é um bot pessoal. 🙂")
            return

        if comando in ("/start", "/ajuda", "/help"):
            linhas = "\n".join(f"/{c} — {d}" for c, d in COMANDOS)
            self.responder(chat, f"🕹️ <b>Resumo Gamer</b>\n\n{linhas}\n\n{self.texto_agenda()}")
        elif comando == "/agora":
            self.responder(chat, "🔎 Buscando as novidades…")
            self.enviar_resumo("pedido no /agora")
            if self.destino and self.destino != chat:
                self.responder(chat, f"✅ Resumo publicado em {self.destino}.")
        elif comando == "/promocoes" and self.promocoes:
            self.responder(chat, self.promocoes())
        elif comando == "/perguntar" and self.perguntar:
            if argumento:
                self.responder(chat, "🔎 Procurando nas notícias…")
            self.responder(chat, self.perguntar(argumento))
        elif comando == "/semana" and self.semana:
            self.responder(chat, "📊 Montando o ranking da semana…")
            self.responder(chat, self.semana())
        elif comando == "/roteiro" and self.roteiro:
            self.responder(chat, "🎬 Escrevendo o roteiro da semana…")
            self.responder(chat, self.roteiro())
        elif comando == "/status":
            if self.ultimo_envio:
                quando = self.ultimo_envio.astimezone(self.fuso).strftime("%d/%m às %Hh%M")
                estado = f"Último resumo: {quando}."
            else:
                estado = "Ainda não mandei nenhum resumo desde que liguei."
            self.responder(chat, f"✅ Estou no ar. {estado}\n{self.texto_agenda()}")
        else:
            self.responder(chat, "Não conheço esse comando. Use /ajuda.")

    # ---------- laço ----------
    def passo(self) -> None:
        """Uma volta do laço: confere a agenda e trata as mensagens novas."""
        self.agenda_do_momento()

        for atualizacao in self.buscar(self.offset):
            self.offset = atualizacao["update_id"] + 1
            try:
                self.tratar(atualizacao)
            except Exception as erro:  # um comando com erro não pode derrubar o bot
                log.exception("Erro ao tratar comando")
                texto = ((atualizacao.get("message") or {}).get("text") or "").split()
                comando = texto[0] if texto else "comando"
                self.responder(self.chat_autorizado,
                               f"⚠️ O {comando} falhou: {type(erro).__name__}. Veja os logs do servidor.")

    def rodar(self) -> None:
        log.info("Bot escutando comandos. %s", self.texto_agenda().replace("\n", " "))
        while True:
            try:
                self.passo()
            except Exception:
                log.exception("Falha no laço; tentando de novo em 15 s")
                time.sleep(15)

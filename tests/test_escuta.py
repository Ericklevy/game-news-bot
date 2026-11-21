from datetime import datetime, time
from zoneinfo import ZoneInfo

from gamebot.escuta import Escuta

SP = ZoneInfo("America/Sao_Paulo")
DONO = "700"


def msg(update_id, texto, chat=DONO):
    return {"update_id": update_id, "message": {"chat": {"id": int(chat)}, "text": texto}}


class Simulador:
    """Faz o papel do Telegram e do relógio nos testes."""

    def __init__(self, agora=datetime(2026, 11, 21, 7, 0, tzinfo=SP)):
        self.agora = agora
        self.fila: list[dict] = []
        self.respostas: list[tuple[str, str]] = []
        self.resumos = 0
        self.offsets: list = []
        self.salvo = None

    def escuta(self, **extra):
        def resumo():
            self.resumos += 1
            return "resumo"

        def buscar(offset):
            self.offsets.append(offset)
            itens, self.fila = self.fila, []
            return itens

        return Escuta(chat_autorizado=DONO, buscar=buscar,
                      responder=lambda chat, texto: self.respostas.append((chat, texto)),
                      rodar_resumo=resumo, hora_diaria=time(8, 17), relogio=lambda: self.agora,
                      salvar_diario=lambda d: setattr(self, "salvo", d), **extra)


def test_agora_envia_resumo_e_avanca_offset():
    s = Simulador()
    e = s.escuta()
    s.fila = [msg(10, "/agora")]
    e.passo()
    assert s.resumos == 1
    assert s.respostas[0] == (DONO, "🔎 Buscando as novidades…")
    e.passo()
    assert s.offsets == [None, 11]      # não processa a mesma mensagem de novo


def test_estranho_nao_dispara_resumo():
    s = Simulador()
    e = s.escuta()
    s.fila = [msg(1, "/agora", chat="999")]
    e.passo()
    assert s.resumos == 0
    assert s.respostas == [("999", "Este é um bot pessoal. 🙂")]


def test_comando_com_nome_do_bot_e_maiuscula():
    s = Simulador()
    e = s.escuta()
    s.fila = [msg(1, "/AGORA@resumogamer_bot")]
    e.passo()
    assert s.resumos == 1


def test_texto_comum_e_ignorado_e_comando_desconhecido_responde():
    s = Simulador()
    e = s.escuta()
    s.fila = [msg(1, "oi"), msg(2, "/banana")]
    e.passo()
    assert s.respostas == [(DONO, "Não conheço esse comando. Use /ajuda.")]


def test_diario_sai_uma_vez_por_dia_depois_do_horario():
    s = Simulador(datetime(2026, 11, 21, 8, 0, tzinfo=SP))
    e = s.escuta()
    e.passo()
    assert s.resumos == 0                      # ainda não deu 8h17
    s.agora = datetime(2026, 11, 21, 8, 20, tzinfo=SP)
    e.passo(); e.passo()
    assert s.resumos == 1 and s.salvo == "2026-11-21"
    s.agora = datetime(2026, 11, 22, 8, 18, tzinfo=SP)
    e.passo()
    assert s.resumos == 2


def test_reinicio_nao_repete_o_diario():
    s = Simulador(datetime(2026, 11, 21, 15, 0, tzinfo=SP))
    e = s.escuta(ultimo_diario="2026-11-21")   # data lida do arquivo ao religar
    e.passo()
    assert s.resumos == 0


def test_erro_no_resumo_avisa_e_nao_derruba():
    s = Simulador()

    def quebra():
        raise RuntimeError("feed fora do ar")

    e = s.escuta()
    e.rodar_resumo = quebra
    s.fila = [msg(1, "/agora")]
    e.passo()
    assert any("Deu erro" in t for _, t in s.respostas)
    assert e.offset == 2


def test_status_depois_de_um_envio():
    s = Simulador(datetime(2026, 11, 21, 9, 30, tzinfo=SP))
    e = s.escuta(ultimo_diario="2026-11-21")
    s.fila = [msg(1, "/agora"), msg(2, "/status")]
    e.passo()
    assert s.respostas[-1] == (DONO, "✅ Estou no ar. Último resumo: 21/11 às 09h30.")

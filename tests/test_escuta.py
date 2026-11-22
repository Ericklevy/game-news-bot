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
        self.semanais = 0
        self.offsets: list = []
        self.salvo: set[str] = set()

    def escuta(self, **extra):
        def resumo():
            self.resumos += 1
            return "resumo"

        def buscar(offset):
            self.offsets.append(offset)
            itens, self.fila = self.fila, []
            return itens

        def publicar_semana():
            self.semanais += 1

        padrao = dict(chat_autorizado=DONO, buscar=buscar,
                      responder=lambda chat, texto: self.respostas.append((chat, texto)),
                      rodar_resumo=resumo, horarios=[time(8, 17)], relogio=lambda: self.agora,
                      publicar_semana=publicar_semana,
                      salvar_feitos=lambda f: setattr(self, "salvo", set(f)))
        padrao.update(extra)
        return Escuta(**padrao)


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
    assert s.resumos == 1 and "2026-11-21 08:17" in s.salvo
    s.agora = datetime(2026, 11, 22, 8, 18, tzinfo=SP)
    e.passo()
    assert s.resumos == 2


def test_varios_horarios_por_dia():
    s = Simulador(datetime(2026, 11, 21, 7, 0, tzinfo=SP))
    e = s.escuta(horarios=[time(19, 17), time(8, 17), time(13, 17)])
    for hora in (8, 13, 19):
        s.agora = datetime(2026, 11, 21, hora, 30, tzinfo=SP)
        e.passo()
    assert s.resumos == 3


def test_ligar_tarde_nao_dispara_os_horarios_que_ja_passaram():
    s = Simulador(datetime(2026, 11, 21, 20, 0, tzinfo=SP))
    e = s.escuta(horarios=[time(8, 17), time(13, 17), time(19, 17)])
    e.passo()
    assert s.resumos == 0
    s.agora = datetime(2026, 11, 22, 8, 20, tzinfo=SP)
    e.passo()
    assert s.resumos == 1


def test_bot_parado_por_horas_publica_uma_vez_so():
    s = Simulador(datetime(2026, 11, 21, 7, 0, tzinfo=SP))
    e = s.escuta(horarios=[time(8, 17), time(13, 17)])
    s.agora = datetime(2026, 11, 21, 14, 0, tzinfo=SP)   # perdeu as 8h17 e as 13h17
    e.passo()
    assert s.resumos == 1


def test_reinicio_nao_repete_o_que_ja_saiu():
    s = Simulador(datetime(2026, 11, 21, 15, 0, tzinfo=SP))
    e = s.escuta(feitos={"2026-11-21 08:17"}, horarios=[time(8, 17), time(13, 17)])
    e.passo()
    assert s.resumos == 1                       # só o das 13h17, que ainda não tinha saído
    e.passo()
    assert s.resumos == 1


def test_ranking_semanal_no_dia_e_hora_certos():
    domingo = datetime(2026, 11, 22, 10, 0, tzinfo=SP)
    assert domingo.weekday() == 6
    s = Simulador(domingo)
    e = s.escuta(semanal=(6, time(10, 17)))
    e.passo()
    assert s.semanais == 0
    s.agora = datetime(2026, 11, 22, 10, 20, tzinfo=SP)
    e.passo(); e.passo()
    assert s.semanais == 1
    s.agora = datetime(2026, 11, 23, 10, 20, tzinfo=SP)  # segunda-feira
    e.passo()
    assert s.semanais == 1


def test_feitos_antigos_sao_esquecidos():
    s = Simulador(datetime(2026, 11, 21, 9, 0, tzinfo=SP))
    e = s.escuta(feitos={"2026-11-01 08:17", "semana 2026-11-01", "2026-11-21 08:17"},
                 horarios=[time(8, 17), time(8, 30)])
    e.passo()
    assert s.salvo == {"2026-11-21 08:17", "2026-11-21 08:30"}


def test_erro_no_resumo_avisa_e_nao_derruba():
    s = Simulador()

    def quebra():
        raise RuntimeError("feed fora do ar")

    e = s.escuta()
    e.rodar_resumo = quebra
    s.fila = [msg(1, "/agora")]
    e.passo()
    assert any(t == "⚠️ O /agora falhou: RuntimeError. Veja os logs do servidor." for _, t in s.respostas)
    assert e.offset == 2


def test_status_depois_de_um_envio():
    s = Simulador(datetime(2026, 11, 21, 9, 30, tzinfo=SP))
    e = s.escuta(horarios=[time(8, 17), time(19, 17)], semanal=(6, time(10, 17)))
    s.fila = [msg(1, "/agora"), msg(2, "/status")]
    e.passo()
    assert s.respostas[-1] == (DONO, "✅ Estou no ar. Último resumo: 21/11 às 09h30.\n"
                                      "Resumo todo dia às 08h17, 19h17.\n"
                                      "Ranking da semana no canal: domingo às 10h17.")


def test_ajuda_lista_todos_os_comandos():
    s = Simulador()
    e = s.escuta()
    s.fila = [msg(1, "/ajuda")]
    e.passo()
    texto = s.respostas[0][1]
    for comando in ("/agora", "/promocoes", "/perguntar", "/semana", "/roteiro", "/status"):
        assert comando in texto


def test_promocoes_e_roteiro():
    s = Simulador()
    e = s.escuta(promocoes=lambda: "ofertas", roteiro=lambda: "roteiro pronto")
    s.fila = [msg(1, "/promocoes"), msg(2, "/roteiro")]
    e.passo()
    assert (DONO, "ofertas") in s.respostas and (DONO, "roteiro pronto") in s.respostas


def test_com_canal_comandos_continuam_so_com_o_dono():
    s = Simulador()
    e = s.escuta(destino="@ResumoGamerBR")
    s.fila = [msg(1, "/agora"), msg(2, "/agora", chat="-100123")]   # o canal/estranho não comanda
    e.passo()
    assert s.resumos == 1
    assert (DONO, "✅ Resumo publicado em @ResumoGamerBR.") in s.respostas


def test_admin_cai_para_o_chat_quando_vazio(monkeypatch, tmp_path):
    from gamebot.config import carregar
    cfg_yaml = tmp_path / "c.yaml"
    cfg_yaml.write_text("feeds: {}\n")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "@ResumoGamerBR")
    monkeypatch.delenv("TELEGRAM_ADMIN_ID", raising=False)
    assert carregar(cfg_yaml).telegram_admin_id == "@ResumoGamerBR"
    monkeypatch.setenv("TELEGRAM_ADMIN_ID", "700")
    assert carregar(cfg_yaml).telegram_admin_id == "700"

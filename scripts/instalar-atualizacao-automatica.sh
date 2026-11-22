#!/usr/bin/env bash
# Liga a atualização automática do bot (a cada 10 minutos).
# Uso, dentro da máquina:
#   bash ~/game-news-bot/scripts/instalar-atualizacao-automatica.sh
set -euo pipefail
USUARIO="$USER"
PASTA="$HOME/game-news-bot"

sudo tee /etc/systemd/system/game-news-bot-atualizar.service >/dev/null <<UNIT
[Unit]
Description=Atualiza o game-news-bot quando há versão nova aprovada no CI
After=network-online.target docker.service
Wants=network-online.target

[Service]
Type=oneshot
User=$USUARIO
SupplementaryGroups=docker
Environment=PASTA=$PASTA
ExecStart=/usr/bin/bash $PASTA/scripts/atualizar.sh
UNIT

sudo tee /etc/systemd/system/game-news-bot-atualizar.timer >/dev/null <<UNIT
[Unit]
Description=Confere a cada 10 minutos se há versão nova do game-news-bot

[Timer]
OnBootSec=3min
OnUnitActiveSec=10min
RandomizedDelaySec=60

[Install]
WantedBy=timers.target
UNIT

sudo systemctl daemon-reload
sudo systemctl enable --now game-news-bot-atualizar.timer
echo
echo "Atualização automática ligada. Para acompanhar:"
echo "  systemctl list-timers game-news-bot-atualizar.timer"
echo "  journalctl -u game-news-bot-atualizar -n 20"

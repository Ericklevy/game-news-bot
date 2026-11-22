#!/usr/bin/env bash
# Atualiza o bot sozinho: se houver versão nova no GitHub E o CI dela passou,
# baixa, reconstrói o contêiner e avisa o dono no Telegram.
# Roda a cada 10 minutos pelo timer do systemd (veja instalar-atualizacao-automatica.sh).
set -euo pipefail

PASTA="${PASTA:-$HOME/game-news-bot}"
REPO="Ericklevy/game-news-bot"
cd "$PASTA"

git fetch -q origin main
LOCAL=$(git rev-parse HEAD)
REMOTO=$(git rev-parse origin/main)
[ "$LOCAL" = "$REMOTO" ] && exit 0

# Só atualiza se todos os checks do CI dessa versão terminaram com sucesso
SITUACAO=$(curl -fsS -H "Accept: application/vnd.github+json" \
  "https://api.github.com/repos/$REPO/commits/$REMOTO/check-runs" | python3 -c '
import json, sys
runs = json.load(sys.stdin).get("check_runs", [])
if not runs:
    print("sem-ci")
elif any(r["status"] != "completed" for r in runs):
    print("rodando")
elif all(r["conclusion"] in ("success", "skipped", "neutral") for r in runs):
    print("ok")
else:
    print("falhou")
')

case "$SITUACAO" in
  ok) ;;
  rodando|sem-ci) echo "$(date -Is) versão ${REMOTO:0:7}: CI ainda não terminou, tento depois"; exit 0 ;;
  *) echo "$(date -Is) versão ${REMOTO:0:7}: CI falhou, não vou atualizar"; exit 0 ;;
esac

echo "$(date -Is) atualizando ${LOCAL:0:7} -> ${REMOTO:0:7}"
git merge -q --ff-only origin/main
docker compose up -d --build servidor
docker image prune -f >/dev/null || true

# Aviso no Telegram (lê o token e o dono do .env, sem imprimir nada)
TOKEN=$(grep -E '^TELEGRAM_TOKEN=' .env | cut -d= -f2- || true)
DONO=$(grep -E '^TELEGRAM_ADMIN_ID=' .env | cut -d= -f2- || true)
[ -z "$DONO" ] && DONO=$(grep -E '^TELEGRAM_CHAT_ID=' .env | cut -d= -f2- || true)
if [ -n "$TOKEN" ] && [ -n "$DONO" ]; then
  MSG="🔄 Bot atualizado sozinho para a versão ${REMOTO:0:7}: $(git log -1 --format=%s)"
  curl -fsS -o /dev/null "https://api.telegram.org/bot${TOKEN}/sendMessage" \
    --data-urlencode "chat_id=${DONO}" --data-urlencode "text=${MSG}" || true
fi
echo "$(date -Is) atualizado"

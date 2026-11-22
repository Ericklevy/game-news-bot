#!/usr/bin/env bash
# Prepara uma máquina Ubuntu (ex.: Oracle Cloud Always Free) para rodar o bot.
# Uso, dentro da máquina:
#   curl -fsSL https://raw.githubusercontent.com/Ericklevy/game-news-bot/main/scripts/instalar-servidor.sh | bash
set -euo pipefail

echo "==> 1/5 Memória extra (swap de 2 GB), importante em máquinas de 1 GB"
if ! swapon --show | grep -q /swapfile; then
  sudo fallocate -l 2G /swapfile
  sudo chmod 600 /swapfile
  sudo mkswap /swapfile >/dev/null
  sudo swapon /swapfile
  grep -q '^/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab >/dev/null
else
  echo "    swap já existe, pulando"
fi

echo "==> 2/5 Instalando Docker e Git"
sudo apt-get update -qq
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq docker.io docker-compose-v2 git >/dev/null
sudo systemctl enable --now docker >/dev/null
sudo usermod -aG docker "$USER"

echo "==> 3/5 Baixando o bot"
if [ -d "$HOME/game-news-bot/.git" ]; then
  git -C "$HOME/game-news-bot" pull -q
else
  git clone -q https://github.com/Ericklevy/game-news-bot.git "$HOME/game-news-bot"
fi

echo "==> 4/5 Ligando a atualização automática (a cada 10 minutos)"
bash "$HOME/game-news-bot/scripts/instalar-atualizacao-automatica.sh" >/dev/null

echo "==> 5/5 Criando o arquivo de configuração"
cd "$HOME/game-news-bot"
if [ ! -f .env ]; then
  cp .env.example .env
  chmod 600 .env
fi

cat <<'FIM'

Pronto! Faltam só dois passos:

  1) Coloque suas chaves no arquivo .env:
       cd ~/game-news-bot && nano .env
     (salve com Ctrl+O, Enter e saia com Ctrl+X)

  2) Ligue o bot:
       sudo docker compose up -d --build
       sudo docker compose logs -f servidor     (Ctrl+C para sair dos logs)

Depois mande /agora para o bot no Telegram.
FIM

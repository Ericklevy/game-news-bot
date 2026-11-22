#!/bin/sh
# Garante que a pasta de dados (montada do servidor) seja gravável pelo usuário "bot".
# Sem isso, quando o Docker cria ./data sozinho ela fica com dono root e o SQLite
# falha com "unable to open database file".
set -e
if [ "$(id -u)" = "0" ]; then
  mkdir -p /app/data
  chown -R bot:bot /app/data
  exec setpriv --reuid=bot --regid=bot --init-groups python -m gamebot "$@"
fi
exec python -m gamebot "$@"

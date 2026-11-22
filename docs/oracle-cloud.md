# Rodando o bot 24 horas na Oracle Cloud (Always Free)

Neste modo o bot fica ligado o tempo todo: responde `/agora`, `/status` e `/ajuda` na hora e manda o resumo diário sozinho às 8h17.

## 1. Criar a conta

1. Acesse https://www.oracle.com/cloud/free/ e clique em **Start for free**.
2. Na **Home Region**, escolha **Brazil East (São Paulo)** ou **Brazil Southeast (Vinhedo)**. Ela não pode ser trocada depois.
3. A Oracle pede um cartão só para verificar a identidade. Os recursos marcados como **Always Free** não são cobrados.

> Dica: se aparecer "Out of capacity" ao criar a máquina, tente outro *Availability Domain* ou tente de novo mais tarde. É comum nas regiões mais procuradas.

## 2. Criar a máquina virtual

1. No menu, vá em **Compute → Instances → Create instance**.
2. **Image:** Ubuntu (a versão LTS mais recente).
3. **Shape:** clique em *Change shape* → **Ampere** → `VM.Standard.A1.Flex`, com **1 OCPU e 6 GB de RAM** (sobra muito para o bot).
   Confira se aparece o selo **Always Free-eligible**.
4. **SSH keys:** escolha **Generate a key pair for me** e baixe a chave privada (arquivo `.key`). Guarde bem: sem ela você não entra na máquina.
5. Clique em **Create** e espere o status ficar **Running**. Anote o **Public IP address**.

Não precisa abrir nenhuma porta: o bot só faz conexões de saída para o Telegram.

## 3. Entrar na máquina

No PowerShell do Windows (troque o caminho da chave e o IP):

```powershell
ssh -i C:\Users\erick\Downloads\ssh-key.key ubuntu@IP_PUBLICO
```

Se o Windows reclamar das permissões da chave, rode antes:

```powershell
icacls C:\Users\erick\Downloads\ssh-key.key /inheritance:r /grant:r "$($env:USERNAME):(R)"
```

## 4. Instalar tudo com um comando

Já dentro da máquina, rode:

```bash
curl -fsSL https://raw.githubusercontent.com/Ericklevy/game-news-bot/main/scripts/instalar-servidor.sh | bash
```

Ele cria a memória extra (swap), instala Docker e Git, baixa o bot e cria o `.env`. Depois, pule para o passo 5.

## 4 (alternativa). Instalar Docker e baixar o bot passo a passo

Já dentro da máquina:

```bash
sudo apt update && sudo apt install -y docker.io docker-compose-v2 git
sudo usermod -aG docker $USER && newgrp docker
git clone https://github.com/Ericklevy/game-news-bot.git
cd game-news-bot
```

## 5. Colocar as chaves

```bash
cp .env.example .env
nano .env
```

Preencha `TELEGRAM_TOKEN`, `TELEGRAM_CHAT_ID` e as chaves de IA que tiver.
Se o resumo for para um canal, use `TELEGRAM_CHAT_ID=@NomeDoCanal` e coloque o id do seu chat em `TELEGRAM_ADMIN_ID`. Salve com `Ctrl+O`, `Enter` e saia com `Ctrl+X`.
O `.env` fica só na máquina: ele está no `.gitignore` e nunca vai para o GitHub.

## 6. Ligar o bot

```bash
docker compose run --rm bot --dry-run   # teste: mostra o resumo sem enviar
docker compose up -d --build            # liga o modo servidor em segundo plano
docker compose logs -f servidor         # acompanha o que ele está fazendo (Ctrl+C sai)
```

Mande `/ajuda` e depois `/agora` para o bot no Telegram.

## 7. Desligar o agendamento do GitHub Actions

Com o servidor ligado, o resumo diário sai dele. Para não receber dois resumos por dia, desligue o agendamento do GitHub:
**Actions → Resumo diário → botão `···` → Disable workflow**.
Se um dia o servidor sair do ar, é só reativar.

## Aviso se a máquina cair (opcional, grátis)

Se a máquina inteira cair, o bot não consegue avisar ninguém. Para isso existe um monitor externo:

1. Crie uma conta grátis em https://healthchecks.io e clique em **Add Check**.
2. Em **Period**, coloque **10 minutes**, e em **Grace**, **10 minutes**.
3. Copie a URL de ping (algo como `https://hc-ping.com/...`).
4. No `.env` da máquina, adicione `HEALTHCHECK_URL=` com essa URL e rode `sudo docker compose up -d --force-recreate`.

O bot avisa o monitor a cada 5 minutos. Se ficar 20 minutos sem sinal, o Healthchecks manda um e-mail para você.

## Backup

Todo domingo às 3h17 o bot manda uma cópia compactada do banco (`gamebot-AAAA-MM-DD.db.gz`) para o seu chat. Para restaurar numa máquina nova, descompacte, coloque em `~/game-news-bot/data/gamebot.db` e reinicie o bot. Também dá para pedir uma cópia com `/backup`.

## Atualização automática

A máquina confere o GitHub a cada 10 minutos. Quando há versão nova **e o CI dela passou**, ela baixa, reconstrói o bot e manda "🔄 Bot atualizado" no seu Telegram. Se os testes falharem, ela não atualiza.

O instalador já liga isso. Numa máquina instalada antes, ligue uma vez com:

```bash
bash ~/game-news-bot/scripts/instalar-atualizacao-automatica.sh
```

Para acompanhar: `journalctl -u game-news-bot-atualizar -n 20`.

## Comandos úteis

| O que fazer | Comando |
|---|---|
| Ver se está rodando | `docker compose ps` |
| Ver os logs | `docker compose logs -f servidor` |
| Atualizar para a versão nova do GitHub | `git pull && docker compose up -d --build` |
| Reiniciar | `docker compose restart servidor` |
| Desligar | `docker compose down` |

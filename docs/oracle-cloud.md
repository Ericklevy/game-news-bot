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

## 4. Instalar Docker e baixar o bot

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

## Comandos úteis

| O que fazer | Comando |
|---|---|
| Ver se está rodando | `docker compose ps` |
| Ver os logs | `docker compose logs -f servidor` |
| Atualizar para a versão nova do GitHub | `git pull && docker compose up -d --build` |
| Reiniciar | `docker compose restart servidor` |
| Desligar | `docker compose down` |

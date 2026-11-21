# 🕹️ Game News Bot

Bot que monta todo dia um **resumo de notícias e promoções de games** e envia no **Telegram**, **em português**. Ele lê os principais sites de games, separa por plataforma (PC, PlayStation, Xbox e Nintendo), junta a mesma notícia publicada em sites diferentes, traduz com IA, busca as melhores promoções de PC e nunca manda a mesma coisa duas vezes.

![Python](https://img.shields.io/badge/Python-3.12-3776AB?style=flat-square&logo=python&logoColor=white)
![Telegram](https://img.shields.io/badge/Telegram-Bot%20API-26A5E4?style=flat-square&logo=telegram&logoColor=white)
![GitHub Actions](https://img.shields.io/badge/GitHub%20Actions-agendado-2088FF?style=flat-square&logo=githubactions&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-pronto-2496ED?style=flat-square&logo=docker&logoColor=white)

## Como fica a mensagem

```
🕹️ Resumo gamer · 21/11/2026

📰 Notícias
🍄 Nintendo anuncia novo Zelda para o Switch 2
   A Nintendo revelou o próximo jogo da série. — GameSpot
🎮 PS5 Pro fica mais barato no Brasil
   A Sony reduziu o preço do console. — IGN
🟩 Xbox Game Pass recebe cinco jogos em dezembro — GameSpot
🌐 Demissões atingem mais um estúdio — IGN

💸 Promoções no PC
Hades · -75% — US$ 6.24 (era US$ 24.99) na Steam · Metacritic 93
Jogo Grátis — GRÁTIS na Epic Games Store
```

Cada título é um link. Os ícones mostram a plataforma: 🖥️ PC, 🎮 PlayStation, 🟩 Xbox, 🍄 Nintendo e 🌐 para notícias gerais do mundo dos games.

## Como funciona

```
  Feeds RSS (IGN, GameSpot,          API CheapShark
  Eurogamer, PC Gamer)               (promoções de PC)
          │                                 │
          ▼                                 ▼
   detecta plataforma               desconto e nota mínimos
   janela de 30 horas                       │
   palavras bloqueadas                      │
   junta notícias repetidas                 │
   no máximo 3 por site                     │
          └──────────────┬──────────────────┘
                         ▼
            SQLite: tira o que já foi enviado
                         ▼
     IA traduz tudo numa chamada só (OpenRouter → Groq
     → Gemini → SambaNova; se todos falharem, vai em inglês)
                         ▼
              Monta o resumo em HTML
                         ▼
             Telegram (divide se passar de 4096 caracteres)
```

- **Notícias repetidas:** a mesma notícia sai em vários sites com títulos diferentes. O bot compara os títulos sem acentos, pontuação e palavras vazias, e mantém só a mais recente.
- **Sem reenvio:** os links enviados ficam num SQLite. No GitHub Actions, esse arquivo é guardado em cache entre uma execução e outra.
- **Tradução com IA sem depender de um provedor:** a tradução usa o formato de chat da OpenAI, que OpenRouter, Groq, Gemini e SambaNova aceitam. O bot tenta na ordem do `config.yaml`, pula quem não tem chave e passa para o próximo se um falhar ou estourar o limite. As notícias do dia vão numa única chamada, então o uso cabe nos planos gratuitos.
- **Arquivo para buscas futuras:** cada notícia enviada fica salva já traduzida (título, resumo, site, plataforma e data). É a base para um comando de busca ou RAG.
- **Tolerante a falhas:** se um site ou a API de promoções cair, o resumo sai com o que estiver disponível.
- **Segredos fora do código:** o token do Telegram vem de variável de ambiente e nunca aparece nos logs, nem em mensagens de erro.

## Comandos no Telegram

No modo servidor (`python -m gamebot --escutar`), o bot fica ligado e responde:

| Comando | O que faz |
|---|---|
| `/agora` | Busca e envia as novidades na hora |
| `/status` | Mostra quando foi o último resumo |
| `/ajuda` | Lista os comandos |

Só o chat configurado em `TELEGRAM_CHAT_ID` pode usar os comandos, para ninguém gastar a sua cota de IA. O passo a passo para deixar o bot ligado 24 horas de graça está em [docs/oracle-cloud.md](docs/oracle-cloud.md).

## Configuração

Tudo fica no [`config.yaml`](config.yaml): plataformas, quantidade de itens, palavras bloqueadas, desconto mínimo das promoções e a lista de feeds. Para acrescentar um site, basta adicionar uma linha com o nome e a URL do RSS.

## Como usar

### 1. Criar o bot no Telegram

1. No Telegram, fale com o **@BotFather**, envie `/newbot` e siga os passos. Ele devolve o **token**.
2. Mande qualquer mensagem para o seu bot (ou adicione-o a um canal como administrador).
3. Abra `https://api.telegram.org/bot<TOKEN>/getUpdates` no navegador e copie o `chat.id`.

### 2. Rodar no seu computador

```bash
cp .env.example .env            # preencha TELEGRAM_TOKEN e TELEGRAM_CHAT_ID
pip install -r requirements.txt
python -m gamebot --dry-run     # mostra o resumo no terminal, sem enviar
python -m gamebot               # envia de verdade
```

Ou com Docker:

```bash
docker compose run --rm bot --dry-run   # uma execução de teste
docker compose up -d --build            # modo servidor, ligado 24 horas
```

### 3. Receber todo dia, de graça, com GitHub Actions

1. No repositório, vá em **Settings → Secrets and variables → Actions** e crie os secrets `TELEGRAM_TOKEN` e `TELEGRAM_CHAT_ID`.
   Para receber em português, crie também pelo menos um destes: `OPENROUTER_API_KEY`, `GROQ_API_KEY`, `GEMINI_API_KEY` ou `SAMBANOVA_API_KEY`.
2. Pronto. O workflow [`resumo-diario.yml`](.github/workflows/resumo-diario.yml) roda todo dia às 8h17 (horário de Brasília).
3. Para testar na hora: aba **Actions → Resumo diário → Run workflow**.

## Testes

```bash
pip install -r requirements-dev.txt
pytest -q
```

São 41 testes, que rodam sem internet, usando feeds e respostas de API salvos em `tests/fixtures`. Eles cobrem a detecção de plataforma, a junção de notícias repetidas, os filtros, as promoções (inclusive com a API fora do ar), a tradução (troca de provedor, resposta incompleta, nenhuma chave e chave fora dos logs), a formatação e a divisão da mensagem, o envio com erro o fluxo completo sem reenviar no dia seguinte e o modo servidor (comandos, chat não autorizado, horário do resumo diário e reinício sem repetir o resumo). O CI roda tudo a cada push.

## Próximos passos

- Comandos no bot, como `/promocoes` e `/noticias zelda`, com busca no histórico.
- Promoções de console (PlayStation Store, eShop e Xbox), que hoje não têm uma API pública simples.
- Comando `/perguntar` com RAG sobre o arquivo de notícias.

## Estrutura

```
gamebot/
├── __main__.py      orquestra coleta → filtros → histórico → envio
├── config.py        lê config.yaml e variáveis de ambiente
├── models.py        Noticia e Promocao
├── plataformas.py   detecta PC, PlayStation, Xbox e Nintendo no texto
├── filtros.py       plataformas, palavras bloqueadas e repetidas
├── banco.py         histórico em SQLite
├── resumo.py        monta e divide a mensagem
├── ia.py            tradução com OpenRouter, Groq, Gemini ou SambaNova
├── escuta.py        modo servidor: comandos e resumo diário
├── telegram.py      envio e leitura de mensagens pela Bot API
└── sources/
    ├── rss.py       leitura dos feeds
    └── promocoes.py API da CheapShark
```

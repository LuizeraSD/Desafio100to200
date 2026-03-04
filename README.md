# Desafio $100 → $200

Bot de trading automatizado com 4 estratégias descorrelacionadas, orquestradas por um loop central com circuit breakers, rebalanceamento diário e monitoramento via Telegram.

> **Disclaimer:** Projeto educacional/entretenimento. Risco real de perda total do capital. Não é recomendação financeira.

---

## Estratégias

| Perna | Capital | Exchange | Estratégia |
|-------|---------|----------|------------|
| 1 | $35 | Binance Futures | Grid Bot (SOL/USDT, 20 grids, 3x leverage, ATR dinâmico) |
| 2 | $25 | IC Markets MT5 | Forex Breakout (GBP/USD + EUR/JPY, range asiático) |
| 3 | $25 | Polymarket CLOB | Modelo Claude API (edge mín 12% vs preço de mercado) |
| 4 | $15 | Bybit Futures | Momentum Scalper (vol 3x médio + VWAP, 5x leverage) |

**Proteção de risco:**

- Circuit breaker por perna: -40% da alocação → perna desligada, capital redistribuído
- Stop global: -50% do portfólio → tudo para
- Rebalanceamento diário às 23:00 UTC

---

## Pré-requisitos

### Contas e depósitos

- [Binance](https://www.binance.com) — conta Futures, mín. $35
- [Bybit](https://www.bybit.com) — conta Futures, mín. $15
- [Polymarket](https://polymarket.com) — carteira Polygon, mín. $25
- [IC Markets](https://www.icmarkets.com) — conta MT5 Raw Spread, mín. $25 *(opcional, Forex EA independente)*

### API Keys necessárias

| Serviço | Permissões necessárias |
|---------|----------------------|
| Binance | Leitura + Futures Trading (sem saque) |
| Bybit | Leitura + Futures Trading (sem saque) |
| Polymarket | CLOB API key via [docs](https://docs.polymarket.com/) |
| Anthropic | API key em [console.anthropic.com](https://console.anthropic.com) |
| Telegram | Bot token via [@BotFather](https://t.me/BotFather) + seu Chat ID |

### Software

- Python 3.11+
- Docker (para rodar localmente em container)
- MetaTrader 5 em Windows/VPS *(apenas para Forex EA — opcional)*

---

## Desenvolvimento Local (Paper Trading)

### 1. Clonar e configurar ambiente

```bash
git clone https://github.com/SEU_USUARIO/desafio-100-200
cd desafio-100-200

python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configurar variáveis de ambiente

```bash
cp .env.example .env
```

Editar `.env`:

```env
PAPER_TRADE=true          # mantenha true para começar

ANTHROPIC_API_KEY=sk-ant-...   # obrigatório para Polymarket

# Opcionais em paper trading (bot simula sem eles):
BINANCE_API_KEY=
BINANCE_SECRET=
BYBIT_API_KEY=
BYBIT_SECRET=

# Telegram (opcional mas recomendado para monitorar):
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
```

> Em paper trading, apenas `ANTHROPIC_API_KEY` é obrigatório (para o modelo Polymarket).
> As exchanges Binance e Bybit ainda buscam preços reais via API pública (sem autenticação).

### 3. Rodar

```bash
# Terminal 1 — orchestrator
python orchestrator/main.py

# Terminal 2 — dashboard (opcional)
streamlit run dashboard/app.py
# Acessa em: http://localhost:8501
```

### 4. Comandos Telegram

```
/status   — resumo do portfólio e status de cada perna
/pnl      — P&L detalhado (realizado + não realizado)
/stop     — parada de emergência (fecha todas as posições)
```

---

## Deploy em Produção — Digital Ocean Apps

### Arquitetura

```
DO App: desafio-100-200
└── Web Service "bot" (basic-xs: 1GB RAM, $12/mês)
    ├── python orchestrator/main.py    (background)
    ├── streamlit run dashboard/app.py (porta $PORT, health check)
    └── Volume persistente /app/state  (crash recovery, $0.10/mês)
```

### Passo a Passo

#### 1. Repositório GitHub

```bash
# Garanta que .env não está no repo
git status   # .env deve aparecer como ignored

git add .
git commit -m "feat: production-ready deploy"
git push origin main
```

#### 2. Criar App no Digital Ocean

1. Acesse [cloud.digitalocean.com/apps](https://cloud.digitalocean.com/apps)
2. Clique em **Create App**
3. Conecte seu repositório GitHub
4. Selecione a branch `main`
5. O DO detectará o `Dockerfile` automaticamente

#### 3. Configurar o App Spec

Edite `.do/app.yaml` substituindo o repo:

```yaml
github:
  repo: SEU_USUARIO/desafio-100-200
  branch: main
```

No painel DO, vá em **Settings → App Spec** e cole o conteúdo do arquivo `.do/app.yaml`.

#### 4. Configurar Secrets (painel DO)

Em **Settings → App-Level Environment Variables**, adicione como **Encrypted**:

| Variável | Valor |
|----------|-------|
| `PAPER_TRADE` | `true` *(começa em paper)* |
| `DASHBOARD_PASSWORD` | senha de sua escolha |
| `BINANCE_API_KEY` | sua key |
| `BINANCE_SECRET` | seu secret |
| `BYBIT_API_KEY` | sua key |
| `BYBIT_SECRET` | seu secret |
| `POLY_API_KEY` | sua key |
| `POLY_SECRET` | seu secret |
| `POLY_PASSPHRASE` | sua passphrase |
| `ANTHROPIC_API_KEY` | sua key |
| `TELEGRAM_BOT_TOKEN` | token do bot |
| `TELEGRAM_CHAT_ID` | seu chat ID |

#### 5. Estado e Persistência — Limitação do DO App Platform

> ⚠ **DO App Platform não suporta volumes persistentes.** O filesystem é efêmero — resetado a cada restart ou redeploy.

**O que isso significa na prática:**

| Estado | Impacto de um restart |
| ------ | --------------------- |
| Grid Bot (Binance) | Sem impacto — reconcilia posições com a exchange no boot |
| Momentum (Bybit) | Sem impacto — reconcilia posições com a exchange no boot |
| Polymarket | Posições abertas são perdidas — risco de double-bet |
| Equity history | Curva do dashboard é resetada |

**Para o desafio de 5 dias**, o risco prático é baixo se o container não reiniciar (DO normalmente mantém containers estáveis por semanas). Para mitigar:

- Configure Telegram (`TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID`) para receber alertas imediatos de qualquer crash
- Evite redeploys desnecessários enquanto houver posições Polymarket abertas

**Para produção de longo prazo**, use [DO Spaces](https://docs.digitalocean.com/products/spaces/) como storage S3-compatível (plano básico: $5/mês) ou migre para [Fly.io](https://fly.io/) que suporta volumes persistentes nativamente.

#### 6. Deploy

```bash
# Clique em "Deploy" no painel DO
# Aguarde o build (~3-5 minutos)
# Health check via Streamlit: /_stcore/health
```

#### 7. Validar

Após deploy bem-sucedido:

1. Acesse a URL do app (ex: `https://desafio-100-200-xxxxx.ondigitalocean.app`)
2. Dashboard deve aparecer com senha configurada
3. Telegram: envie `/status` ao bot
4. Verifique os logs em **Runtime Logs** no painel DO

### Ativar Live Trading

Após mínimo **48 horas em paper trading** sem erros:

1. No painel DO → Settings → Environment Variables
2. Altere `PAPER_TRADE` de `true` para `false`
3. Clique em **Save** → **Deploy** (manual)
4. Monitore a primeira hora intensamente via Telegram

---

## Forex EA (MetaTrader 5)

O Forex EA é independente do orchestrator Python — roda diretamente no MT5.

### Setup

1. Copie `SessionBreakout/SessionBreakout_v1.ex5` para a pasta `Experts` do MT5
2. Aplique no gráfico GBP/USD M5 (conta IC Markets Raw Spread)
3. Repita para EUR/JPY M5
4. Siga o guia completo: [SessionBreakout/SETUP_GUIDE_SessionBreakout.md](SessionBreakout/SETUP_GUIDE_SessionBreakout.md)

> O orchestrator Python **não controla** o Forex EA — é por design. O EA roda 24/7 no terminal MT5 independentemente.

---

## Validar Build Local (Docker)

```bash
# Build da imagem
docker build -t desafio-100-200 .

# Testar com .env local
docker run -p 8501:8501 --env-file .env desafio-100-200

# Dashboard em: http://localhost:8501
# Logs do orchestrator: docker logs <container_id>
```

---

## Estrutura do Projeto

```
desafio-100-200/
├── orchestrator/
│   ├── main.py           # Loop central, rebalanceamento, circuit breakers
│   ├── portfolio.py      # P&L consolidado, curva de equity
│   ├── risk_manager.py   # Circuit breakers, redistribuição de capital
│   └── notifier.py       # Telegram: /status /pnl /stop
│
├── strategies/
│   ├── base.py           # Interface: tick(), close_all(), resize(), get_pnl()
│   ├── paper_exchange.py # Wrapper ccxt para simulação sem capital real
│   ├── state_manager.py  # Crash recovery: state/*.json
│   ├── grid_bot/         # Perna 1 — Binance Futures
│   ├── momentum/         # Perna 4 — Bybit Futures
│   └── polymarket/       # Perna 3 — Polymarket CLOB + Claude API
│
├── SessionBreakout/
│   ├── SessionBreakout_v1.mq5   # Perna 2 — EA MQL5 (MetaTrader 5)
│   └── SETUP_GUIDE_SessionBreakout.md
│
├── dashboard/
│   └── app.py            # Dashboard Streamlit (lê state/portfolio.json)
│
├── state/                # Gerado em runtime (gitignored)
│   ├── portfolio.json    # Estado consolidado (atualizado a cada 60s)
│   ├── grid_bot.json     # Posições do grid
│   ├── momentum.json     # Trades abertos
│   └── polymarket.json   # Apostas abertas
│
├── Dockerfile            # Imagem para Digital Ocean Apps
├── start.sh              # Entrypoint: orchestrator + Streamlit
├── .do/app.yaml          # Digital Ocean App spec
└── docker-compose.yml    # Desenvolvimento local com Docker
```

---

## Troubleshooting

### Bot não conecta na Binance/Bybit

- Verifique se as API keys têm permissão Futures
- Confirme que a conta tem saldo em Futures (não só Spot)
- No paper trading, a conexão é feita mas ordens são simuladas

### Polymarket: 0 candidatos encontrados

- Normal no primeiro run — o scanner precisa paginar ~3000+ mercados (~3min)
- Cache é salvo em `state/polymarket_candidates.json` (válido por 4h)
- Se persistir, verifique se `ANTHROPIC_API_KEY` está configurada

### Dashboard não aparece / health check falha

- Aguarde 60s após o deploy (o orchestrator carrega mercados antes do Streamlit subir)
- Verifique logs em Runtime Logs no painel DO
- O health check do DO usa `/_stcore/health` (endpoint nativo do Streamlit)

### Orchestrator crasha em loop

- Verifique os logs: `docker logs <container>` ou Runtime Logs no DO
- Erro de DNS no Windows: resolvido com `ThreadedResolver` (já implementado)
- Erro de API key: confirme variáveis de ambiente no painel DO

### Estado perdido após redeploy

- Confirme que o volume `state-data` está montado em `/app/state`
- O volume DO é persistente — sobrevive a deploys e restarts
- Se não houver volume, o bot recria o estado do zero (reconcilia com a exchange)

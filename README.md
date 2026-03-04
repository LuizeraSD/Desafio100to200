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

```text
/status   — resumo do portfólio e status de cada perna
/pnl      — P&L detalhado (realizado + não realizado)
/stop     — parada de emergência (fecha todas as posições)
```

---

## Deploy em Produção — Digital Ocean Droplet

### Por que Droplet e não App Platform?

- **IP fixo** — necessário para whitelist nas exchanges (Binance, Bybit)
- **Disco persistente** — `state/*.json` sobrevive a restarts e reboots
- **Controle total** — SSH direto, logs em tempo real, fácil troubleshooting
- **Custo similar** — Basic Droplet $6/mês (1 vCPU, 1GB RAM) ou $12/mês (2GB RAM)

### Arquitetura

```text
DO Droplet: desafio-100-200 (Frankfurt — fra1)
├── IP fixo (Reserved IP vinculado ao Droplet)
├── python orchestrator/main.py    (systemd service, reinicia automático)
├── streamlit run dashboard/app.py (porta 8501, acessível via IP:8501)
└── /root/desafio/state/           (crash recovery, disco persistente)
```

### Passo a Passo

#### 1. Criar Droplet

1. Acesse [cloud.digitalocean.com/droplets](https://cloud.digitalocean.com/droplets)
2. **Create Droplet** com as seguintes opções:
   - **Região:** Frankfurt (`fra1`) — Binance não é geo-bloqueada na Europa
   - **Imagem:** Ubuntu 24.04 LTS
   - **Plano:** Basic → Regular → **$6/mês** (1 vCPU, 1 GB RAM) ou **$12/mês** (2 GB) se quiser mais folga
   - **Authentication:** SSH key (recomendado) ou senha
3. Após criação, anote o **IP público** do Droplet

#### 2. Vincular Reserved IP (IP fixo)

1. No painel DO → **Networking → Reserved IPs**
2. **Assign Reserved IP** ao seu Droplet
3. Anote o IP fixo — este é o IP que você usará na whitelist das exchanges

> O Reserved IP é gratuito enquanto vinculado a um Droplet ativo.

#### 3. Configurar API Keys nas Exchanges

Com o IP fixo em mãos, configure nas exchanges:

- **Binance:** API Management → Edit → IP Access → adicionar o Reserved IP
- **Bybit:** API Management → Edit → IP restriction → adicionar o Reserved IP

#### 4. Setup do Servidor

Conecte via SSH e execute:

```bash
ssh root@SEU_IP_FIXO

# Atualizar sistema
apt update && apt upgrade -y

# Instalar dependências do sistema (Ubuntu 24.04 já inclui Python 3.12)
apt install -y python3-venv python3-pip git

# Clonar o repositório
cd /root
git clone https://github.com/SEU_USUARIO/desafio-100-200.git desafio
cd desafio

# Criar ambiente virtual e instalar dependências
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

#saia do venv apos instalar as dependencias do python
deactivate

# Criar diretórios necessários
mkdir -p state logs
```

#### 5. Configurar Variáveis de Ambiente

```bash
cp .env.example .env
nano .env
```

Preencha todas as variáveis:

```env
PAPER_TRADE=true

BINANCE_API_KEY=...
BINANCE_SECRET=...
BYBIT_API_KEY=...
BYBIT_SECRET=...
POLY_API_KEY=...
POLY_SECRET=...
POLY_PASSPHRASE=...
ANTHROPIC_API_KEY=sk-ant-...
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...
DASHBOARD_PASSWORD=...
```

#### 6. Criar Serviços systemd

Crie o serviço do orchestrator:

```bash
cat > /etc/systemd/system/desafio-orchestrator.service << 'EOF'
[Unit]
Description=Desafio 100-200 Orchestrator
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=root
WorkingDirectory=/root/desafio
EnvironmentFile=/root/desafio/.env
ExecStart=/root/desafio/venv/bin/python -u orchestrator/main.py
Restart=on-failure
RestartSec=10
StandardOutput=append:/root/desafio/logs/orchestrator.log
StandardError=append:/root/desafio/logs/orchestrator.log

[Install]
WantedBy=multi-user.target
EOF
```

Crie o serviço do dashboard:

```bash
cat > /etc/systemd/system/desafio-dashboard.service << 'EOF'
[Unit]
Description=Desafio 100-200 Dashboard
After=desafio-orchestrator.service

[Service]
Type=simple
User=root
WorkingDirectory=/root/desafio
EnvironmentFile=/root/desafio/.env
ExecStart=/root/desafio/venv/bin/streamlit run dashboard/app.py \
    --server.port 8501 \
    --server.headless true \
    --server.address 0.0.0.0 \
    --server.enableCORS false \
    --server.enableXsrfProtection false
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
```

Ative e inicie os serviços:

```bash
systemctl daemon-reload
systemctl enable desafio-orchestrator desafio-dashboard
systemctl start desafio-orchestrator desafio-dashboard
```

#### 7. Validar

```bash
# Status dos serviços
systemctl status desafio-orchestrator
systemctl status desafio-dashboard

# Logs em tempo real do orchestrator
journalctl -u desafio-orchestrator -f

# Ou diretamente no arquivo
tail -f /root/desafio/logs/orchestrator.log
```

- Dashboard: acesse `http://SEU_IP_FIXO:8501` no navegador
- Telegram: envie `/status` ao bot

#### 8. Comandos Úteis

```bash
# Reiniciar orchestrator (ex: após mudar .env)
systemctl restart desafio-orchestrator

# Parar tudo
systemctl stop desafio-orchestrator desafio-dashboard

# Atualizar código
cd /root/desafio
git pull origin main
source venv/bin/activate
pip install -r requirements.txt
systemctl restart desafio-orchestrator desafio-dashboard

# Ver logs das últimas 2 horas
journalctl -u desafio-orchestrator --since "2 hours ago"
```

### Ativar Live Trading

Após mínimo **48 horas em paper trading** sem erros:

```bash
# 1. Editar .env
nano /root/desafio/.env
# Alterar PAPER_TRADE=true → PAPER_TRADE=false

# 2. Reiniciar orchestrator
systemctl restart desafio-orchestrator

# 3. Acompanhar o boot em tempo real
journalctl -u desafio-orchestrator -f

# 4. Monitorar a primeira hora via Telegram
```

### Segurança Básica do Droplet

```bash
# Firewall: liberar apenas SSH e Dashboard
ufw allow 22/tcp      # SSH
ufw allow 8501/tcp    # Dashboard Streamlit
ufw enable

# (Opcional) Trocar porta SSH padrão
# nano /etc/ssh/sshd_config → Port 2222
# ufw allow 2222/tcp && ufw delete allow 22/tcp
# systemctl restart sshd
```

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

```text
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
├── Dockerfile            # Imagem Docker (dev local ou alternativo)
├── start.sh              # Entrypoint Docker: orchestrator + Streamlit
├── .do/app.yaml          # DO App Platform spec (alternativo ao Droplet)
└── docker-compose.yml    # Desenvolvimento local com Docker
```

---

## Troubleshooting

### Bot não conecta na Binance/Bybit

- Verifique se as API keys têm permissão Futures
- Confirme que o **Reserved IP do Droplet** está na whitelist da exchange
- Confirme que a conta tem saldo em Futures (não só Spot)
- No paper trading, a conexão é feita mas ordens são simuladas

### Binance: HTTP 451 / "restricted location"

- A Binance bloqueia requests de IPs nos EUA. Use Droplet na Europa (Frankfurt `fra1`)
- O orchestrator detecta este erro automaticamente e desabilita a perna (sem crash)

### Polymarket: 0 candidatos encontrados

- Normal no primeiro run — o scanner precisa paginar ~3000+ mercados (~3min)
- Cache é salvo em `state/polymarket_candidates.json` (válido por 4h)
- Se persistir, verifique se `ANTHROPIC_API_KEY` está configurada

### Dashboard não aparece

- Verifique se o serviço está ativo: `systemctl status desafio-dashboard`
- Confirme que a porta 8501 está liberada no firewall: `ufw status`
- Teste localmente: `curl http://localhost:8501/_stcore/health`

### Orchestrator crasha em loop

- Verifique os logs: `journalctl -u desafio-orchestrator -f`
- O systemd reinicia automaticamente após 10s (`RestartSec=10`)
- Erro de API key: confirme variáveis em `/root/desafio/.env`
- Erro de DNS no Windows (dev local): resolvido com `ThreadedResolver` (já implementado)

### Atualizar código em produção

```bash
cd /root/desafio
git pull origin main
source venv/bin/activate
pip install -r requirements.txt
systemctl restart desafio-orchestrator desafio-dashboard
```

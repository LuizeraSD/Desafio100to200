# CLAUDE.md — Desafio $100 → $200 em 5 Dias

> Projeto de entretenimento/educacional. 4 estratégias automatizadas, 4 mercados, 100% bot-driven.
> **⚠ Disclaimer:** Risco real de perder 100% do capital. Não é recomendação financeira.

---

## Visão Geral do Projeto

**Tese central:** Combinar 4 estratégias descorrelacionadas para gerar ~15% ao dia composto durante 5 dias. Cada "perna" opera independentemente — se uma falha, as outras compensam.

| Métrica          | Valor                  |
|------------------|------------------------|
| Capital Inicial  | $100                   |
| Meta             | $200 (100% em 5 dias)  |
| Meta Diária      | ~14.87% composto       |
| Dedicação        | < 1 hora/dia           |
| Perfil Técnico   | Avançado (APIs, bots)  |

### Por que Portfólio Combinado?

- **Descorrelação de retornos:** Grid bot lucra em mercado lateral, momentum em tendência, Polymarket em eventos discretos, forex em sessões específicas. Raramente todos falham juntos.
- **Kelly Criterion adaptado:** Alocação proporcional ao edge estimado e inversa à variância.
- **Rebalanceamento diário:** Lucros redistribuídos ao fim de cada dia. Compound effect acelerado.
- **Circuit breakers independentes:** Cada estratégia tem stop loss próprio. Se uma perde 40%, é desligada e o capital vai para as que funcionam.

---

## Alocação de Capital

### Perna 1: Grid Trading Bot — $30 (30%)

- **Plataforma:** Bybit Futures (migrado de Binance — geo-bloqueada no Brasil)
- **Target:** +5-8%/dia
- **Por que Bybit:** Binance Futures é inacessível do Brasil. Bybit já é usada pelo Momentum Scalper, simplificando a operação (1 exchange para 2 pernas crypto).
- **Config:**
  - Par: SOL/USDT:USDT perp (volatilidade alta + liquidez)
  - Grids: 20 níveis, range dinâmico baseado em ATR(24h)
  - Alavancagem: 3x (margem isolada)
  - Profit per grid: ~0.25-0.4%
  - Reinvestimento: automático a cada 12h
  - **Nota:** Grid + Momentum compartilham a mesma instância ccxt.bybit e saldo Bybit (~$50 total)

### Perna 2: Session Breakout Forex — $25 (25%)

- **Plataforma:** IC Markets (cTrader/MT5)
- **Target:** +8-12%/dia
- **Por que 25%:** Estratégia mecânica com edge estatístico comprovado. Opera 1 vez/dia no breakout da sessão asiática → Londres. IC Markets tem spreads raw a partir de 0.0 pips.
- **Config:**
  - Pares: GBP/USD + EUR/JPY (2 trades/dia max)
  - Range asiático: 00:00-08:00 GMT
  - Entry: buy/sell stop nos extremos do range
  - TP: 1.5x range, SL: 0.5x range (R:R = 3:1)
  - Conta: Raw Spread (comissão $3.50/lot, spread ~0.1)
  - Alavancagem: 30:1 (micro lots: 0.02-0.05)
  - Automação: **MT5 EA (MQL5)** ← escolha do usuário (já implementado: `strategies/forex_breakout/SessionBreakout_v1.mq5`)
  - Win rate histórico: ~45%, mas R:R compensa

### Perna 3: Polymarket Model-Based — $25 (25%)

- **Plataforma:** Polymarket
- **Target:** +10-20%/evento
- **Por que 25%:** Mercados de previsão são ineficientes, especialmente em eventos de nicho. Um modelo usando Claude API + dados de polling/news pode encontrar edges de 10-20% vs preço de mercado.
- **Config:**
  - Focar em mercados com volume > $50k
  - Usar Claude API para analisar probabilidades
  - Só apostar quando edge estimado > 12%
  - Max $8-10 por posição individual
  - 2-4 posições simultâneas
  - Diversificar entre categorias (política, tech, esportes)

### Perna 4: Momentum Scalper — $20 (20%)

- **Plataforma:** Bybit Futures
- **Target:** +10-25%/dia
- **Por que 20%:** Perna de "convexidade". Capital menor porque é a mais arriscada, mas com potencial de retorno assimétrico.
- **Config:**
  - Monitorar top 30 altcoins por volume 24h
  - Trigger: volume 3x acima da média + preço rompendo VWAP
  - Entry: market order no breakout
  - TP: trailing stop de 1.5%, ou +3% fixo
  - SL: -1.5% fixo
  - Max 3 trades simultâneos
  - Alavancagem: 5x (margem isolada)

### Cenários Projetados (5 dias)

| Cenário      | Resultado | Variação  |
|--------------|-----------|-----------|
| 🔴 Pessimista | $65       | -35%      |
| 🟡 Realista   | $155      | +55%      |
| 🟢 Otimista   | $220      | +120%     |
| 🚀 Best Case  | $300+     | +200%+    |

> Cenário realista assume: Grid +4%/dia, Forex +5%/dia (2 de 5 dias ganham), Polymarket +15% em 2 de 3 apostas, Momentum +8%/dia médio. Com rebalanceamento.

---

## Arquitetura do Projeto

### Estrutura de Diretórios

```
100-to-200/
├── orchestrator/
│   ├── main.py              # Loop principal, rebalanceamento
│   ├── portfolio.py          # Estado do portfólio, P&L tracking
│   ├── risk_manager.py       # Circuit breakers, position sizing
│   └── notifier.py           # Alertas via Telegram
│
├── strategies/
│   ├── grid_bot/
│   │   ├── engine.py         # Lógica do grid (ccxt + Bybit)
│   │   └── config.yaml       # Params: grids, range, leverage
│   │
│   ├── forex_breakout/
│   │   ├── SessionBreakout_v1.mq5  # ✅ EA MT5 (já implementado)
│   │   ├── SETUP_GUIDE.md          # ✅ Guia de instalação (já criado)
│   │   └── config.yaml
│   │
│   ├── polymarket/
│   │   ├── scanner.py         # Busca mercados ativos
│   │   ├── model.py           # Claude API p/ estimar probabilidades
│   │   ├── executor.py        # Coloca ordens via Polymarket API
│   │   └── config.yaml
│   │
│   └── momentum/
│       ├── detector.py        # Volume scanner (Bybit websocket)
│       ├── executor.py        # Entry/exit logic
│       └── config.yaml
│
├── dashboard/
│   └── app.py                # Streamlit dashboard p/ monitoramento
│
├── docker-compose.yml        # Deploy tudo em containers
├── requirements.txt
├── .env                      # API keys (NUNCA committar)
├── .gitignore
└── CLAUDE.md                 # ← Este arquivo
```

### Interface de cada Estratégia

Cada estratégia é um módulo independente que implementa a interface:

- `tick()` → Executa lógica, retorna status (P&L, posições abertas, estado)
- `close_all()` → Fecha todas as posições (circuit breaker)
- `resize(new_alloc)` → Ajusta tamanho das posições (rebalanceamento)
- `get_pnl()` → Retorna lucro/prejuízo em USD

### Orchestrator (pseudocódigo)

```python
# Loop principal - roda a cada 60s
async def main_loop():
    portfolio = Portfolio(initial=100)
    risk = RiskManager(max_drawdown=0.40, daily_target=0.15)
    notify = TelegramNotifier(chat_id=CHAT_ID)

    strategies = [
        GridBot(alloc=30.0, exchange="bybit"),
        ForexBreakout(alloc=0.25, broker="icmarkets"),
        PolymarketModel(alloc=25.0),
        MomentumScalper(alloc=20.0, exchange="bybit"),
    ]

    while True:
        for strat in strategies:
            # Cada estratégia reporta P&L e status
            status = await strat.tick()
            portfolio.update(strat.id, status)

            # Circuit breaker individual
            if risk.should_stop(strat):
                await strat.close_all()
                await notify.alert(f"⛔ {strat.id} stopped: {status}")
                risk.redistribute(portfolio, strat)

        # Rebalanceamento diário (23:00 UTC)
        if is_rebalance_time():
            portfolio.rebalance()
            await notify.daily_report(portfolio)

        # Check meta global
        if portfolio.total_value >= 200:
            await notify.alert("🎯 META ATINGIDA! $200+")

        if risk.total_drawdown > 0.50:
            await notify.alert("🚨 DRAWDOWN 50% - TUDO PARADO")
            for s in strategies: await s.close_all()
            break

        await asyncio.sleep(60)
```

### Chaves de API Necessárias (.env)

```env
# Bybit (Grid Bot + Momentum)
BYBIT_API_KEY=
BYBIT_SECRET=

# IC Markets (Forex - MT5 EA roda direto no terminal)
ICMARKETS_MT5_LOGIN=
ICMARKETS_MT5_PASSWORD=
ICMARKETS_MT5_SERVER=ICMarketsSC-MT5

# Polymarket (via CLOB API)
POLY_API_KEY=
POLY_SECRET=
POLY_PASSPHRASE=

# Claude API (modelo de probabilidades)
ANTHROPIC_API_KEY=

# Telegram (notificações)
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
```

---

## Dependências

```txt
ccxt>=4.0              # Bybit (Grid Bot + Momentum)
py-clob-client         # Polymarket CLOB
anthropic              # Claude API (modelo)
python-telegram-bot    # Notificações
aiohttp                # Async HTTP
pandas                 # Análise de dados
pyyaml                 # Configs
streamlit              # Dashboard (opcional)
python-dotenv          # .env loading
```

> **Nota sobre Forex:** O EA MQL5 roda direto no MetaTrader 5 (IC Markets). Não precisa de dependência Python para forex. Se no futuro quiser integrar com o orchestrator Python, usar `MetaTrader5` (Windows) ou `metaapi-cloud` (cross-platform).

---

## Timeline Dia a Dia

### D0 — Setup & Deploy (dia anterior)

| Hora  | Ação |
|-------|------|
| 14:00 | Depositar $50 na Bybit (Grid+Momentum), $25 na IC Markets, $25 na Polymarket |
| 16:00 | Configurar API keys em todas as plataformas |
| 18:00 | Deploy dos bots (VPS ou local via Docker) |
| 20:00 | Testar cada estratégia com $1-2 em modo real |
| 22:00 | Configurar Telegram bot para notificações |
| 23:00 | Ativar grid bot e forex EA (MT5/cTrader). Polymarket: selecionar primeiros mercados |

**CHECKPOINT:** Todos os bots respondendo via Telegram. Trades de teste executados com sucesso.

### D1 — Ignição

| Hora  | Ação |
|-------|------|
| 00:00 | Grid bot ativo em SOL/USDT (20 grids, 3x leverage) |
| 08:00 | Forex breakout: ordens armadas no range asiático de GBP/USD e EUR/JPY |
| 09:00 | Polymarket: Claude analisa 10 mercados, seleciona 2-3 com edge >12% |
| 24/7  | Momentum bot scannando volume em loop (Bybit websocket) |
| 23:00 | Review via Telegram: checar P&L de cada perna |

**CHECKPOINT:** Meta: portfólio em $112-118. Grid deve ter capturado 3-5% se mercado moveu. Forex 1 trade executado.

### D2 — Calibração

| Hora  | Ação |
|-------|------|
| 08:00 | Revisar performance D1 (5 min). Ajustar grid range se volatilidade mudou |
| 08:15 | Polymarket: reavaliar posições, fechar as que convergiram, abrir novas |
| 08:30 | Se momentum teve >3 trades, analisar win rate. Ajustar thresholds se <40% |
| 24/7  | Bots continuam operando automaticamente |
| 23:00 | Rebalanceamento: mover lucros da melhor perna para as outras |

**CHECKPOINT:** Meta: portfólio em $128-140. Se abaixo de $90, considerar aumentar risco na perna momentum.

### D3 — Aceleração

| Hora  | Ação |
|-------|------|
| 08:00 | Se total > $140: manter curso. Se < $120: aumentar leverage do grid para 5x |
| 08:15 | Polymarket: buscar mercados que resolvem nos dias 4-5 para maximizar capital efficiency |
| 24/7  | Bots operando. Momentum pode ter capturado 1-2 pumps significativos |
| 23:00 | Rebalanceamento + decisão: dobrar na estratégia que mais está performando |

**CHECKPOINT:** Meta: portfólio em $150-170. Ponto de inflexão — compound começa a acelerar.

### D4 — Sprint Final

| Hora  | Ação |
|-------|------|
| 08:00 | Se > $170: modo conservador (reduzir leverage, proteger ganhos) |
| 08:00 | Se $140-170: manter ritmo, sem mudanças |
| 08:00 | Se < $140: modo agressivo — concentrar no que está funcionando |
| 24/7  | Bots operando. Apertar stops no momentum (proteger lucros) |
| 23:00 | Último rebalanceamento. Projetar se meta é viável |

**CHECKPOINT:** Meta: portfólio em $175-200. Se aqui, D5 é só para consolidar.

### D5 — Conclusão

| Hora  | Ação |
|-------|------|
| 08:00 | Review final. Se meta batida: começar a fechar posições gradualmente |
| 12:00 | Fechar posições Polymarket (vender shares se não resolvidas) |
| 16:00 | Fechar grid bot e momentum |
| 18:00 | Fechar forex positions |
| 20:00 | Consolidar saldos. Screenshot final. Post-mortem de cada estratégia |

**CHECKPOINT FINAL:** Meta: $200+. Documentar tudo para conteúdo.

---

## Regras de Risco

### 🛑 Regras Invioláveis

1. **Stop Loss Global: -50% ($50)** — Se o portfólio total cair abaixo de $50, TODOS os bots são desligados imediatamente. Não existe "recuperar". Aceitar a perda e documentar.

2. **Circuit Breaker por Estratégia: -40%** — Se qualquer estratégia individual perder 40% da sua alocação, é desligada. O capital remanescente é redistribuído proporcionalmente entre as estratégias no positivo.

3. **Nunca Adicionar Capital** — O desafio é $100 → $200. Se perder, perdeu. Adicionar mais dinheiro invalida o experimento.

### 📐 Position Sizing

- **Max Leverage:** Grid max 5x. Momentum max 5x (margem isolada). Forex max 30:1 (micro lots). Polymarket sem alavancagem (spot).
- **Correlação:** Nunca estar long crypto no grid E no momentum ao mesmo tempo com mais de 50% do capital total. Se grid está 100% long, momentum deve estar neutro ou com bias short.
- **Rebalanceamento:** Às 23:00 UTC, equalizar proporções. Se uma perna está +30% e outra -10%, transferir parte do lucro. Manter a diversificação.

### Cenários de Risco Específicos

- **Flash crash de crypto:** Grid bot e Momentum sofrem (ambos na Bybit). Mitigação: margem isolada + stop no grid inferior + correlação guard (máx 50% long). Máx perda crypto: ~$15-20.
- **Mercado lateral sem volume:** Grid ganha pouco, momentum sem oportunidades, forex falha (falsos breakouts). Mitigação: Polymarket é independente.
- **Polymarket apostas erradas:** Eventos resolvem contra. Mitigação: max $8-10/posição, diversificar em 3+ mercados.
- **Problemas técnicos:** API cai, bot crasha, latência. Mitigação: Docker restart automático, stop loss na exchange (não só no bot), heartbeat via Telegram.

---

## Setup Técnico

### Infraestrutura

```bash
# Opção A: VPS barata ($5/mês - DigitalOcean, Hetzner)
# Ubuntu 22.04, 2GB RAM, 1 vCPU é suficiente

# Opção B: Rodar local com Docker
docker-compose up -d

# Opção C: Rodar local sem Docker
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Ordem de Implementação

| # | Módulo              | Status |
|---|---------------------|--------|
| 1 | Grid Bot (Bybit)    | ✅ DONE — `strategies/grid_bot/engine.py` (migrado de Binance) |
| 2 | Forex Breakout (MT5)| ✅ DONE — `SessionBreakout/SessionBreakout_v1.mq5` |
| 3 | Polymarket Model    | ✅ DONE — `strategies/polymarket/` |
| 4 | Momentum Scanner    | ✅ DONE — `strategies/momentum/` |
| 5 | Orchestrator + TG   | ✅ DONE — `orchestrator/main.py` |
| 6 | Dashboard Streamlit | ✅ DONE — `dashboard/app.py` |
| 7 | Crash Recovery      | ✅ DONE — `strategies/state_manager.py` |
| 8 | Infra Docker / DO   | ✅ DONE — `Dockerfile`, `.do/app.yaml` |

### Checklist de Go-Live

- [ ] API keys configuradas e testadas (cada exchange/broker)
- [ ] Depósitos confirmados em todas as plataformas
- [ ] Telegram bot respondendo a /status
- [ ] Grid bot executou pelo menos 5 grids em modo paper
- [ ] Forex EA colocou ordens de teste no IC Markets (0.01 lot via MT5)
- [ ] Polymarket: scanner encontrando candidatos (log "X mercados passaram nos filtros")
- [ ] Momentum: scanner detectando pelo menos 1 sinal por hora
- [ ] Circuit breakers testados (simular drawdown -40%)
- [ ] Docker build sem erros: `docker build -t desafio .`
- [ ] Container roda localmente: `docker run -p 8501:8501 --env-file .env desafio`
- [ ] Dashboard acessível em `http://localhost:8501`
- [ ] Backup do .env em local seguro (nunca no repo)
- [ ] 48h mínimo em paper trading antes de ativar live

### Deploy em Produção (Digital Ocean Droplet)

Ver [README.md](README.md) para o guia passo-a-passo completo.

**Por que Droplet (e não App Platform):**

- IP fixo (Reserved IP) — necessário para whitelist nas exchanges
- Disco persistente nativo — `state/*.json` sobrevive a restarts
- SSH direto para troubleshooting e logs em tempo real

**Arquivos de infraestrutura:**

- `Dockerfile` + `start.sh` — alternativa Docker para dev local
- `.do/app.yaml` — spec DO App Platform (alternativo, não recomendado)

**Estrutura no Droplet:**

```text
DO Droplet: desafio-100-200 (Frankfurt — fra1)
├── IP fixo (Reserved IP — whitelist nas exchanges)
├── systemd: desafio-orchestrator.service (reinicia automático)
├── systemd: desafio-dashboard.service    (porta 8501)
└── /root/desafio/state/                  (crash recovery, persistente)
```

**Ativar live trading:**

1. Validar 48h em paper trading no Droplet
2. Editar `.env`: `PAPER_TRADE=false`
3. `systemctl restart desafio-orchestrator`
4. Monitorar primeira hora via Telegram

---

## Convenções de Código

- **Linguagem principal:** Python 3.11+ (async/await)
- **Forex:** MQL5 (EA rodando no MetaTrader 5 da IC Markets, independente do Python)
- **Estilo:** Cada estratégia é um módulo com interface `tick()`, `close_all()`, `resize()`, `get_pnl()`
- **Config:** YAML por estratégia, `.env` para secrets
- **Logs:** Estruturado com nível + timestamp, + Telegram para alertas críticos
- **Testes:** Backtest de cada estratégia antes de ir live. Usar conta demo por 1 dia mínimo

---

## Referências Rápidas para Claude

Ao trabalhar neste projeto, considere:

- **Para Grid Bot:** usar `ccxt` library. Exchange `bybit`. Futures API com margem isolada. Precisa calcular ATR para range dinâmico. Compartilha instância Bybit com Momentum — atenção à correlação (máx 50% long crypto simultâneo).
- **Para Forex:** EA já pronto em MQL5. Se precisar integrar com orchestrator Python, usar MetaApi cloud wrapper como ponte.
- **Para Polymarket:** usar `py-clob-client` para CLOB API. Usar `anthropic` SDK para o modelo de probabilidades. O modelo deve receber contexto do evento + dados relevantes e retornar uma estimativa de probabilidade.
- **Para Momentum:** websocket real-time via `ccxt.pro` ou `aiohttp` direto na Bybit WS API. Scanner de volume precisa ser eficiente (processar 30+ pares em parallel).
- **Para Orchestrator:** `asyncio` event loop. Cada estratégia roda como task independente. Risk manager centralizado.
- **Para Telegram:** `python-telegram-bot` v20+ (async). Comandos: `/status`, `/pnl`, `/stop`, `/restart`.

import { useState } from "react";

const palette = {
  bg: "#08080D",
  card: "rgba(255,255,255,0.03)",
  cardHover: "rgba(255,255,255,0.055)",
  border: "rgba(255,255,255,0.07)",
  text: "#E8E8ED",
  muted: "rgba(255,255,255,0.42)",
  dimmer: "rgba(255,255,255,0.25)",
  accent1: "#F7931A",
  accent2: "#3B82F6",
  accent3: "#8B5CF6",
  accent4: "#F43F5E",
  green: "#10B981",
  red: "#EF4444",
  yellow: "#FBBF24",
};

const tabs = [
  { id: "overview", label: "Visão Geral" },
  { id: "allocation", label: "Alocação" },
  { id: "architecture", label: "Arquitetura" },
  { id: "day-by-day", label: "Dia a Dia" },
  { id: "risk", label: "Risco & Regras" },
  { id: "setup", label: "Setup Técnico" },
];

const Section = ({ title, color, children }) => (
  <div style={{ marginBottom: 28 }}>
    <h3
      style={{
        fontSize: 11,
        fontWeight: 800,
        textTransform: "uppercase",
        letterSpacing: "0.12em",
        color: color || palette.muted,
        margin: "0 0 14px",
        display: "flex",
        alignItems: "center",
        gap: 8,
      }}
    >
      <span
        style={{
          width: 16,
          height: 2,
          background: color || palette.muted,
          borderRadius: 1,
          display: "inline-block",
        }}
      />
      {title}
    </h3>
    {children}
  </div>
);

const InfoBox = ({ color, children, mono }) => (
  <div
    style={{
      background: (color || palette.muted) + "08",
      border: `1px solid ${(color || palette.muted)}18`,
      borderRadius: 12,
      padding: "14px 16px",
      fontSize: 12.5,
      color: palette.muted,
      lineHeight: 1.7,
      fontFamily: mono ? "'SF Mono', 'Fira Code', monospace" : "inherit",
    }}
  >
    {children}
  </div>
);

const Metric = ({ label, value, sub, color }) => (
  <div
    style={{
      background: palette.card,
      border: `1px solid ${palette.border}`,
      borderRadius: 12,
      padding: "14px 16px",
      flex: 1,
      minWidth: 100,
    }}
  >
    <div
      style={{
        fontSize: 9,
        fontWeight: 700,
        textTransform: "uppercase",
        letterSpacing: "0.1em",
        color: palette.dimmer,
        marginBottom: 6,
      }}
    >
      {label}
    </div>
    <div
      style={{
        fontSize: 22,
        fontWeight: 900,
        color: color || palette.text,
        fontFamily: "'SF Mono', monospace",
        letterSpacing: "-0.02em",
      }}
    >
      {value}
    </div>
    {sub && (
      <div style={{ fontSize: 10, color: palette.dimmer, marginTop: 2 }}>{sub}</div>
    )}
  </div>
);

const StrategyRow = ({ icon, name, alloc, color, target, market, rationale }) => {
  const [open, setOpen] = useState(false);
  return (
    <div
      style={{
        background: palette.card,
        border: `1px solid ${open ? color + "33" : palette.border}`,
        borderRadius: 12,
        overflow: "hidden",
        transition: "all 0.25s",
        marginBottom: 8,
      }}
    >
      <div
        onClick={() => setOpen(!open)}
        style={{
          display: "flex",
          alignItems: "center",
          gap: 12,
          padding: "14px 16px",
          cursor: "pointer",
        }}
      >
        <span style={{ fontSize: 22 }}>{icon}</span>
        <div style={{ flex: 1 }}>
          <div style={{ fontSize: 14, fontWeight: 700, color: palette.text }}>{name}</div>
          <span
            style={{
              fontSize: 10,
              fontWeight: 600,
              padding: "2px 8px",
              borderRadius: 4,
              background: color + "15",
              color,
            }}
          >
            {market}
          </span>
        </div>
        <div style={{ textAlign: "right" }}>
          <div
            style={{
              fontSize: 20,
              fontWeight: 900,
              color,
              fontFamily: "monospace",
            }}
          >
            ${alloc}
          </div>
          <div style={{ fontSize: 10, color: palette.dimmer }}>
            target: {target}
          </div>
        </div>
      </div>
      {open && (
        <div
          style={{
            padding: "0 16px 16px",
            borderTop: `1px solid ${palette.border}`,
            paddingTop: 14,
            animation: "fadeSlide 0.25s ease",
          }}
        >
          <div style={{ fontSize: 12, color: palette.muted, lineHeight: 1.7 }}>
            {rationale}
          </div>
        </div>
      )}
    </div>
  );
};

const CodeBlock = ({ title, code }) => (
  <div style={{ marginBottom: 14 }}>
    {title && (
      <div
        style={{
          fontSize: 10,
          fontWeight: 700,
          color: palette.dimmer,
          textTransform: "uppercase",
          letterSpacing: "0.08em",
          marginBottom: 6,
        }}
      >
        {title}
      </div>
    )}
    <pre
      style={{
        background: "rgba(0,0,0,0.4)",
        border: `1px solid ${palette.border}`,
        borderRadius: 10,
        padding: 14,
        fontSize: 11,
        lineHeight: 1.6,
        color: "rgba(255,255,255,0.55)",
        fontFamily: "'SF Mono', 'Fira Code', monospace",
        overflowX: "auto",
        margin: 0,
        whiteSpace: "pre-wrap",
        wordBreak: "break-word",
      }}
    >
      {code}
    </pre>
  </div>
);

const DayCard = ({ day, title, color, tasks, checkpoint }) => (
  <div
    style={{
      background: palette.card,
      border: `1px solid ${palette.border}`,
      borderRadius: 14,
      padding: 18,
      marginBottom: 10,
      position: "relative",
      overflow: "hidden",
    }}
  >
    <div
      style={{
        position: "absolute",
        top: 0,
        left: 0,
        bottom: 0,
        width: 3,
        background: color,
        borderRadius: "3px 0 0 3px",
      }}
    />
    <div style={{ display: "flex", alignItems: "baseline", gap: 10, marginBottom: 12 }}>
      <span
        style={{
          fontSize: 28,
          fontWeight: 900,
          color,
          fontFamily: "monospace",
          letterSpacing: "-0.03em",
        }}
      >
        D{day}
      </span>
      <span style={{ fontSize: 14, fontWeight: 700, color: palette.text }}>{title}</span>
    </div>
    {tasks.map((t, i) => (
      <div
        key={i}
        style={{
          display: "flex",
          gap: 8,
          marginBottom: 6,
          fontSize: 12.5,
          color: palette.muted,
          lineHeight: 1.6,
        }}
      >
        <span style={{ color, fontWeight: 700, flexShrink: 0, fontFamily: "monospace", fontSize: 11 }}>
          {t.time}
        </span>
        <span>{t.action}</span>
      </div>
    ))}
    {checkpoint && (
      <div
        style={{
          marginTop: 12,
          padding: "10px 12px",
          background: color + "0C",
          border: `1px solid ${color}20`,
          borderRadius: 8,
          fontSize: 11.5,
          color: palette.muted,
          fontFamily: "monospace",
        }}
      >
        <strong style={{ color }}>CHECKPOINT:</strong> {checkpoint}
      </div>
    )}
  </div>
);

const RuleCard = ({ icon, title, rule, severity }) => (
  <div
    style={{
      background: palette.card,
      border: `1px solid ${severity === "critical" ? palette.red + "22" : palette.border}`,
      borderRadius: 12,
      padding: 14,
      marginBottom: 8,
    }}
  >
    <div style={{ display: "flex", gap: 10, alignItems: "flex-start" }}>
      <span style={{ fontSize: 18 }}>{icon}</span>
      <div>
        <div
          style={{
            fontSize: 13,
            fontWeight: 700,
            color: severity === "critical" ? palette.red : palette.text,
            marginBottom: 4,
          }}
        >
          {title}
        </div>
        <div style={{ fontSize: 12, color: palette.muted, lineHeight: 1.6 }}>{rule}</div>
      </div>
    </div>
  </div>
);

function OverviewTab() {
  return (
    <>
      <Section title="Tese Central" color={palette.green}>
        <InfoBox color={palette.green}>
          Combinar 4 estratégias descorrelacionadas para gerar{" "}
          <strong style={{ color: palette.text }}>~15% ao dia composto</strong> durante 5 dias.
          Cada "perna" opera independentemente. Se uma falha, as outras compensam.
          Meta: $100 → $200 (100% em 5 dias = ~14.87% composto/dia).
        </InfoBox>
      </Section>

      <Section title="Métricas do Plano" color={palette.accent2}>
        <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
          <Metric label="Capital Inicial" value="$100" color={palette.text} />
          <Metric label="Meta" value="$200" sub="100% em 5 dias" color={palette.green} />
          <Metric label="Meta Diária" value="~15%" sub="composto" color={palette.accent2} />
          <Metric label="Dedicação" value="<1h" sub="por dia" color={palette.accent3} />
        </div>
      </Section>

      <Section title="Por que Portfólio Combinado?" color={palette.accent3}>
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          {[
            {
              title: "Descorrelação de retornos",
              desc: "Grid bot lucra em mercado lateral, momentum em tendência, Polymarket em eventos discretos, forex em sessões específicas. Raramente todos falham juntos.",
            },
            {
              title: "Kelly Criterion adaptado",
              desc: "Alocação proporcional ao edge estimado e inversa à variância. Mais capital onde há mais vantagem e menos incerteza.",
            },
            {
              title: "Rebalanceamento diário",
              desc: "Ao fim de cada dia, lucros são redistribuídos. Estratégias vencedoras financiam as que precisam de mais capital. Compound effect acelerado.",
            },
            {
              title: "Circuit breakers independentes",
              desc: "Cada estratégia tem stop loss próprio. Se uma perna perde 40%, é desligada e o capital remanescente vai para as que estão funcionando.",
            },
          ].map((item, i) => (
            <div
              key={i}
              style={{
                background: palette.card,
                border: `1px solid ${palette.border}`,
                borderRadius: 10,
                padding: "12px 14px",
              }}
            >
              <div style={{ fontSize: 13, fontWeight: 700, color: palette.text, marginBottom: 3 }}>
                {item.title}
              </div>
              <div style={{ fontSize: 12, color: palette.muted, lineHeight: 1.6 }}>{item.desc}</div>
            </div>
          ))}
        </div>
      </Section>
    </>
  );
}

function AllocationTab() {
  return (
    <>
      <Section title="Distribuição de Capital" color={palette.accent1}>
        <StrategyRow
          icon="◈"
          name="Grid Trading Bot"
          alloc={35}
          color={palette.accent1}
          target="+5-8%/dia"
          market="Binance Futures"
          rationale={
            <>
              <strong style={{ color: palette.text }}>Por que $35 (35%):</strong> É a perna mais previsível. Grid bots em pares de alta liquidez (SOL/USDT, ETH/USDT) com alavancagem 3-5x geram retornos consistentes em mercado volátil. É o "motor base" do portfólio.
              {"\n\n"}
              <strong style={{ color: palette.text }}>Config específica:</strong>{"\n"}
              • Par: SOL/USDT perp (volatilidade alta + liquidez){"\n"}
              • Grids: 20 níveis, range dinâmico baseado em ATR(24h){"\n"}
              • Alavancagem: 3x (margem isolada){"\n"}
              • Profit per grid: ~0.25-0.4%{"\n"}
              • Reinvestimento: automático a cada 12h
            </>
          }
        />
        <StrategyRow
          icon="◰"
          name="Session Breakout Forex"
          alloc={25}
          color={palette.accent2}
          target="+8-12%/dia"
          market="IC Markets (cTrader)"
          rationale={
            <>
              <strong style={{ color: palette.text }}>Por que $25 (25%):</strong> Estratégia mecânica com edge estatístico comprovado. Opera 1 vez/dia no breakout da sessão asiática → Londres. IC Markets via cTrader Open API ou MT5 — spreads raw a partir de 0.0 pips, ideal pra scalping.
              {"\n\n"}
              <strong style={{ color: palette.text }}>Config específica:</strong>{"\n"}
              • Pares: GBP/USD + EUR/JPY (2 trades/dia max){"\n"}
              • Range asiático: 00:00-08:00 GMT{"\n"}
              • Entry: buy/sell stop nos extremos do range{"\n"}
              • TP: 1.5x range, SL: 0.5x range (R:R = 3:1){"\n"}
              • Conta: Raw Spread (comissão $3.50/lot, spread ~0.1){"\n"}
              • Alavancagem: 30:1 (micro lots: 0.02-0.05){"\n"}
              • Automação: cTrader Automate (C#) ou MT5 EA (MQL5){"\n"}
              • Win rate histórico: ~45%, mas R:R compensa
            </>
          }
        />
        <StrategyRow
          icon="🧠"
          name="Polymarket Model-Based"
          alloc={25}
          color={palette.accent3}
          target="+10-20%/evento"
          market="Polymarket"
          rationale={
            <>
              <strong style={{ color: palette.text }}>Por que $25 (25%):</strong> Mercados de previsão são ineficientes, especialmente em eventos de nicho. Um modelo usando Claude API + dados de polling/news pode encontrar edges de 10-20% vs preço de mercado. Melhor "convexidade" do portfólio.
              {"\n\n"}
              <strong style={{ color: palette.text }}>Config específica:</strong>{"\n"}
              • Focar em mercados com volume > $50k{"\n"}
              • Usar Claude API para analisar probabilidades{"\n"}
              • Só apostar quando edge estimado > 12%{"\n"}
              • Max $8-10 por posição individual{"\n"}
              • 2-4 posições simultâneas{"\n"}
              • Diversificar entre categorias (política, tech, esportes)
            </>
          }
        />
        <StrategyRow
          icon="⚡"
          name="Momentum Scalper"
          alloc={15}
          color={palette.accent4}
          target="+10-25%/dia"
          market="Bybit Futures"
          rationale={
            <>
              <strong style={{ color: palette.text }}>Por que $15 (15%):</strong> É a perna de "convexidade". Capital menor porque é a mais arriscada, mas com potencial de retorno assimétrico. Detecta pumps em altcoins via volume anormal e surfa o momentum.
              {"\n\n"}
              <strong style={{ color: palette.text }}>Config específica:</strong>{"\n"}
              • Monitorar top 30 altcoins por volume 24h{"\n"}
              • Trigger: volume 3x acima da média + preço rompendo VWAP{"\n"}
              • Entry: market order no breakout{"\n"}
              • TP: trailing stop de 1.5%, ou +3% fixo{"\n"}
              • SL: -1.5% fixo{"\n"}
              • Max 3 trades simultâneos{"\n"}
              • Alavancagem: 5x (margem isolada)
            </>
          }
        />
      </Section>

      <Section title="Cenários Projetados (5 dias)" color={palette.yellow}>
        <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
          <Metric label="🔴 Pessimista" value="$65" sub="Perda de 35%" color={palette.red} />
          <Metric label="🟡 Realista" value="$155" sub="Lucro de 55%" color={palette.yellow} />
          <Metric label="🟢 Otimista" value="$220" sub="Lucro de 120%" color={palette.green} />
          <Metric label="🚀 Best Case" value="$300+" sub="Tudo alinha" color={palette.accent3} />
        </div>
        <div style={{ marginTop: 12, fontSize: 11.5, color: palette.dimmer, lineHeight: 1.7 }}>
          * Cenário realista assume: Grid +4%/dia, Forex +5%/dia (2 de 5 dias ganham), 
          Polymarket +15% em 2 de 3 apostas, Momentum +8%/dia médio. Com rebalanceamento.
        </div>
      </Section>
    </>
  );
}

function ArchitectureTab() {
  return (
    <>
      <Section title="Stack Técnico" color={palette.accent2}>
        <CodeBlock
          title="Estrutura do Projeto"
          code={`100-to-200/
├── orchestrator/
│   ├── main.py              # Loop principal, rebalanceamento
│   ├── portfolio.py          # Estado do portfólio, P&L tracking
│   ├── risk_manager.py       # Circuit breakers, position sizing
│   └── notifier.py           # Alertas via Telegram
│
├── strategies/
│   ├── grid_bot/
│   │   ├── engine.py         # Lógica do grid (ccxt + Binance)
│   │   └── config.yaml       # Params: grids, range, leverage
│   │
│   ├── forex_breakout/
│   │   ├── session_scanner.py # Detecta range asiático
│   │   ├── executor.py        # Coloca ordens via IC Markets (MT5/cTrader)
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
└── .env                      # API keys (NUNCA committar)`}
        />
      </Section>

      <Section title="Fluxo do Orchestrator" color={palette.green}>
        <CodeBlock
          title="orchestrator/main.py (pseudocódigo)"
          code={`# Loop principal - roda a cada 60s
async def main_loop():
    portfolio = Portfolio(initial=100)
    risk = RiskManager(max_drawdown=0.40, daily_target=0.15)
    notify = TelegramNotifier(chat_id=CHAT_ID)
    
    strategies = [
        GridBot(alloc=0.35, exchange="binance"),
        ForexBreakout(alloc=0.25, broker="icmarkets"),
        PolymarketModel(alloc=0.25),
        MomentumScalper(alloc=0.15, exchange="bybit"),
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
                # Redistribuir capital
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
            
        await asyncio.sleep(60)`}
        />
      </Section>

      <Section title="Comunicação entre Componentes" color={palette.accent3}>
        <InfoBox color={palette.accent3}>
          <strong style={{ color: palette.text }}>Cada estratégia é um módulo independente que implementa a interface:</strong>
          {"\n\n"}
          • <code>tick()</code> → Executa lógica, retorna status (P&L, posições abertas, estado){"\n"}
          • <code>close_all()</code> → Fecha todas as posições (circuit breaker){"\n"}
          • <code>resize(new_alloc)</code> → Ajusta tamanho das posições (rebalanceamento){"\n"}
          • <code>get_pnl()</code> → Retorna lucro/prejuízo em USD{"\n\n"}
          <strong style={{ color: palette.text }}>Notificações via Telegram Bot:</strong> Alertas de trades, report diário, circuit breakers, meta atingida. Permite monitorar pelo celular sem abrir nada.
        </InfoBox>
      </Section>

      <Section title="Chaves de API Necessárias" color={palette.accent1}>
        <CodeBlock
          title=".env"
          code={`# Binance (Grid Bot)
BINANCE_API_KEY=...
BINANCE_SECRET=...

# Bybit (Momentum)
BYBIT_API_KEY=...
BYBIT_SECRET=...

# IC Markets (Forex - via MetaApi or cTrader Open API)
ICMARKETS_MT5_LOGIN=...
ICMARKETS_MT5_PASSWORD=...
ICMARKETS_MT5_SERVER=ICMarketsSC-MT5
# Ou via MetaApi (wrapper cloud p/ MT5):
METAAPI_TOKEN=...
METAAPI_ACCOUNT_ID=...

# Polymarket (via CLOB API)
POLY_API_KEY=...
POLY_SECRET=...
POLY_PASSPHRASE=...

# Claude API (modelo de probabilidades)
ANTHROPIC_API_KEY=...

# Telegram (notificações)
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...`}
        />
      </Section>
    </>
  );
}

function DayByDayTab() {
  return (
    <>
      <Section title="Timeline de Execução" color={palette.accent2}>
        <DayCard
          day={0}
          title="Setup & Deploy (dia anterior)"
          color={palette.dimmer}
          tasks={[
            { time: "14:00", action: "Depositar $35 na Binance, $25 na IC Markets, $25 na Polymarket, $15 na Bybit" },
            { time: "16:00", action: "Configurar API keys em todas as plataformas" },
            { time: "18:00", action: "Deploy dos bots (VPS ou local via Docker)" },
            { time: "20:00", action: "Testar cada estratégia com $1-2 em modo real" },
            { time: "22:00", action: "Configurar Telegram bot para notificações" },
            { time: "23:00", action: "Ativar grid bot e forex EA (MT5/cTrader). Polymarket: selecionar primeiros mercados" },
          ]}
          checkpoint="Todos os bots respondendo via Telegram. Trades de teste executados com sucesso."
        />

        <DayCard
          day={1}
          title="Ignição"
          color={palette.accent1}
          tasks={[
            { time: "00:00", action: "Grid bot ativo em SOL/USDT (20 grids, 3x leverage)" },
            { time: "08:00", action: "Forex breakout: ordens armadas no range asiático de GBP/USD e EUR/JPY" },
            { time: "09:00", action: "Polymarket: Claude analisa 10 mercados, seleciona 2-3 com edge >12%" },
            { time: "24/7 ", action: "Momentum bot scannando volume em loop (Bybit websocket)" },
            { time: "23:00", action: "Review via Telegram: checar P&L de cada perna" },
          ]}
          checkpoint="Meta: portfólio em $112-118. Grid deve ter capturado 3-5% se mercado moveu. Forex 1 trade executado."
        />

        <DayCard
          day={2}
          title="Calibração"
          color={palette.accent2}
          tasks={[
            { time: "08:00", action: "Revisar performance D1 (5 min). Ajustar grid range se volatilidade mudou." },
            { time: "08:15", action: "Polymarket: reavaliar posições, fechar as que convergiram, abrir novas" },
            { time: "08:30", action: "Se momentum teve >3 trades, analisar win rate. Ajustar thresholds se <40%" },
            { time: "24/7 ", action: "Bots continuam operando automaticamente" },
            { time: "23:00", action: "Rebalanceamento: mover lucros da melhor perna para as outras" },
          ]}
          checkpoint="Meta: portfólio em $128-140. Se abaixo de $90, considerar aumentar risco na perna momentum."
        />

        <DayCard
          day={3}
          title="Aceleração"
          color={palette.accent3}
          tasks={[
            { time: "08:00", action: "Se total > $140: manter curso. Se < $120: aumentar leverage do grid para 5x" },
            { time: "08:15", action: "Polymarket: buscar mercados que resolvem nos dias 4-5 para maximizar capital efficiency" },
            { time: "24/7 ", action: "Bots operando. Momentum pode ter capturado 1-2 pumps significativos" },
            { time: "23:00", action: "Rebalanceamento + decisão: dobrar na estratégia que mais está performando" },
          ]}
          checkpoint="Meta: portfólio em $150-170. Ponto de inflexão — compound começa a acelerar."
        />

        <DayCard
          day={4}
          title="Sprint Final"
          color={palette.accent4}
          tasks={[
            { time: "08:00", action: "Se > $170: modo conservador (reduzir leverage, proteger ganhos)" },
            { time: "08:00", action: "Se $140-170: manter ritmo, sem mudanças" },
            { time: "08:00", action: "Se < $140: modo agressivo — concentrar no que está funcionando" },
            { time: "24/7 ", action: "Bots operando. Apertar stops no momentum (proteger lucros)" },
            { time: "23:00", action: "Último rebalanceamento. Projetar se meta é viável." },
          ]}
          checkpoint="Meta: portfólio em $175-200. Se aqui, D5 é só para consolidar."
        />

        <DayCard
          day={5}
          title="Conclusão"
          color={palette.green}
          tasks={[
            { time: "08:00", action: "Review final. Se meta batida: começar a fechar posições gradualmente" },
            { time: "12:00", action: "Fechar posições Polymarket (vender shares se não resolvidas)" },
            { time: "16:00", action: "Fechar grid bot e momentum" },
            { time: "18:00", action: "Fechar forex positions" },
            { time: "20:00", action: "Consolidar saldos. Screenshot final. Post-mortem de cada estratégia" },
          ]}
          checkpoint="Meta final: $200+. Documentar tudo para conteúdo."
        />
      </Section>
    </>
  );
}

function RiskTab() {
  return (
    <>
      <Section title="Regras Invioláveis" color={palette.red}>
        <RuleCard
          icon="🛑"
          severity="critical"
          title="Stop Loss Global: -50% ($50)"
          rule="Se o portfólio total cair abaixo de $50, TODOS os bots são desligados imediatamente. Não existe 'recuperar'. Aceitar a perda e documentar o que deu errado."
        />
        <RuleCard
          icon="⛔"
          severity="critical"
          title="Circuit Breaker por Estratégia: -40%"
          rule="Se qualquer estratégia individual perder 40% da sua alocação, é desligada. O capital remanescente é redistribuído proporcionalmente entre as estratégias que estão no positivo."
        />
        <RuleCard
          icon="🚫"
          severity="critical"
          title="Nunca Adicionar Capital"
          rule="O desafio é $100 → $200. Se perder, perdeu. Adicionar mais dinheiro invalida o experimento e pode virar uma espiral de prejuízo."
        />
      </Section>

      <Section title="Regras de Position Sizing" color={palette.yellow}>
        <RuleCard
          icon="📐"
          title="Max Leverage por Perna"
          rule="Grid bot: max 5x. Momentum: max 5x (margem isolada). Forex: max 30:1 (micro lots). Polymarket: sem alavancagem (spot only)."
        />
        <RuleCard
          icon="📊"
          title="Correlação de Posições"
          rule="Nunca estar long crypto no grid E no momentum ao mesmo tempo com mais de 50% do capital total. Se grid está 100% long, momentum deve estar neutro ou com bias short."
        />
        <RuleCard
          icon="🔄"
          title="Rebalanceamento Diário"
          rule="Às 23:00 UTC, equalizar proporções. Se uma perna está +30% e outra -10%, transferir parte do lucro. Manter a diversificação mesmo quando uma estratégia está 'quente'."
        />
      </Section>

      <Section title="Cenários de Risco Específicos" color={palette.accent3}>
        <InfoBox color={palette.accent3}>
          <strong style={{ color: palette.text }}>Flash crash de crypto:</strong> Grid bot sofre (posições long viram negativas). Mitigação: margem isolada + stop no grid inferior. Máx perda: ~$15-20.{"\n\n"}
          <strong style={{ color: palette.text }}>Mercado lateral sem volume:</strong> Grid ganha pouco, momentum não encontra oportunidades. Forex breakout falha (falsos breakouts). Mitigação: Polymarket é independente de mercados financeiros.{"\n\n"}
          <strong style={{ color: palette.text }}>Polymarket: apostas erradas:</strong> Eventos resolvem contra. Mitigação: max $8-10 por posição, diversificar em 3+ mercados.{"\n\n"}
          <strong style={{ color: palette.text }}>Problemas técnicos:</strong> API cai, bot crasha, latência. Mitigação: Docker restart automático, stop loss em exchange (não só no bot), heartbeat monitoring via Telegram.
        </InfoBox>
      </Section>
    </>
  );
}

function SetupTab() {
  return (
    <>
      <Section title="Passo 1: Infraestrutura" color={palette.accent2}>
        <CodeBlock
          title="VPS (recomendado) ou local"
          code={`# Opção A: VPS barata ($5/mês - DigitalOcean, Hetzner)
# Ubuntu 22.04, 2GB RAM, 1 vCPU é suficiente

# Opção B: Rodar local com Docker
docker-compose up -d

# Opção C: Rodar local sem Docker (mais simples)
python -m venv venv
source venv/bin/activate
pip install ccxt metaapi-cloud python-telegram-bot anthropic aiohttp`}
        />
      </Section>

      <Section title="Passo 2: Dependências" color={palette.accent1}>
        <CodeBlock
          title="requirements.txt"
          code={`ccxt>=4.0          # Binance + Bybit
MetaTrader5        # IC Markets via MT5 (Windows/Wine)
# ou: metaapi-cloud # IC Markets via MetaApi (cloud, cross-platform)
py-clob-client     # Polymarket CLOB
anthropic          # Claude API (modelo)
python-telegram-bot # Notificações
aiohttp            # Async HTTP
pandas             # Análise de dados
pyyaml             # Configs
streamlit          # Dashboard (opcional)
python-dotenv      # .env loading`}
        />
      </Section>

      <Section title="Passo 3: Ordem de Implementação" color={palette.green}>
        <InfoBox color={palette.green}>
          <strong style={{ color: palette.text }}>Prioridade de desenvolvimento (2-3 dias de setup):</strong>
          {"\n\n"}
          <strong style={{ color: palette.accent1 }}>1. Grid Bot (4h)</strong> → Mais simples de implementar. ccxt tem exemplos prontos. Testar com $5 antes de alocar os $35.
          {"\n\n"}
          <strong style={{ color: palette.accent2 }}>2. Forex Breakout (3h)</strong> → Lógica clara e mecânica. Duas opções de automação: (a) MT5 EA em MQL5 rodando direto no terminal — mais simples, mas precisa de Windows/Wine. (b) MetaApi (cloud wrapper do MT5) — roda em qualquer OS via REST API, ideal pra integrar com Python. Testar 1 dia em paper trading.
          {"\n\n"}
          <strong style={{ color: palette.accent3 }}>3. Polymarket Model (4h)</strong> → Claude API para estimar probabilidades. Polymarket CLOB API para executar. Parte mais "artesanal" — requer curadoria de mercados.
          {"\n\n"}
          <strong style={{ color: palette.accent4 }}>4. Momentum Scanner (5h)</strong> → Mais complexo: websocket real-time, detector de volume, entry/exit rápido. Implementar por último.
          {"\n\n"}
          <strong style={{ color: palette.text }}>5. Orchestrator + Telegram (2h)</strong> → Cola tudo junto. Loop principal + notificações.
        </InfoBox>
      </Section>

      <Section title="Passo 4: Checklist de Go-Live" color={palette.yellow}>
        {[
          "API keys configuradas e testadas (cada exchange/broker)",
          "Depósitos confirmados em todas as plataformas",
          "Telegram bot respondendo a /status",
          "Grid bot executou pelo menos 5 grids em teste real ($2-3)",
          "Forex EA colocou ordens de teste no IC Markets (0.01 lot via MT5 ou MetaApi)",
          "Polymarket: 1 posição de teste de $1",
          "Momentum: scanner detectando pelo menos 5 sinais/hora",
          "Circuit breakers testados (simular drawdown -40%)",
          "Docker containers reiniciam automaticamente após crash",
          "Backup do .env em local seguro (não no repo)",
        ].map((item, i) => (
          <div
            key={i}
            style={{
              display: "flex",
              gap: 10,
              alignItems: "flex-start",
              padding: "8px 0",
              borderBottom: `1px solid ${palette.border}`,
              fontSize: 12.5,
              color: palette.muted,
              lineHeight: 1.5,
            }}
          >
            <span
              style={{
                width: 20,
                height: 20,
                borderRadius: 6,
                border: `2px solid ${palette.border}`,
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                flexShrink: 0,
                fontSize: 10,
                color: palette.dimmer,
              }}
            >
              {i + 1}
            </span>
            {item}
          </div>
        ))}
      </Section>
    </>
  );
}

const tabContent = {
  overview: OverviewTab,
  allocation: AllocationTab,
  architecture: ArchitectureTab,
  "day-by-day": DayByDayTab,
  risk: RiskTab,
  setup: SetupTab,
};

export default function App() {
  const [activeTab, setActiveTab] = useState("overview");
  const Content = tabContent[activeTab];

  return (
    <div
      style={{
        minHeight: "100vh",
        background: palette.bg,
        color: palette.text,
        fontFamily: "'SF Pro Display', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
      }}
    >
      <style>{`
        @keyframes fadeSlide {
          from { opacity: 0; transform: translateY(-4px); }
          to { opacity: 1; transform: translateY(0); }
        }
        * { box-sizing: border-box; }
        code {
          background: rgba(255,255,255,0.06);
          padding: 2px 6px;
          border-radius: 4px;
          font-size: 11px;
          font-family: 'SF Mono', 'Fira Code', monospace;
        }
        ::-webkit-scrollbar { width: 4px; height: 4px; }
        ::-webkit-scrollbar-track { background: transparent; }
        ::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.1); border-radius: 4px; }
      `}</style>

      <div style={{ maxWidth: 780, margin: "0 auto", padding: "32px 20px 60px" }}>
        {/* Header */}
        <div style={{ marginBottom: 28 }}>
          <div
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: 6,
              padding: "4px 12px",
              borderRadius: 6,
              background: "rgba(16, 185, 129, 0.08)",
              border: "1px solid rgba(16, 185, 129, 0.15)",
              fontSize: 10,
              fontWeight: 700,
              color: palette.green,
              letterSpacing: "0.1em",
              textTransform: "uppercase",
              marginBottom: 14,
            }}
          >
            PLANO DE IMPLEMENTAÇÃO
          </div>
          <h1
            style={{
              fontSize: 30,
              fontWeight: 900,
              letterSpacing: "-0.03em",
              margin: "0 0 6px",
              lineHeight: 1.1,
            }}
          >
            Estratégia Combinada{" "}
            <span style={{ color: palette.green }}>$100→$200</span>
          </h1>
          <p style={{ fontSize: 13, color: palette.muted, margin: 0 }}>
            4 estratégias • 4 mercados • 5 dias • 100% automatizado
          </p>
        </div>

        {/* Tabs */}
        <div
          style={{
            display: "flex",
            gap: 4,
            marginBottom: 28,
            overflowX: "auto",
            paddingBottom: 4,
          }}
        >
          {tabs.map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              style={{
                padding: "8px 16px",
                borderRadius: 8,
                border: "1px solid",
                borderColor: activeTab === tab.id ? "rgba(255,255,255,0.15)" : "transparent",
                background: activeTab === tab.id ? "rgba(255,255,255,0.07)" : "transparent",
                color: activeTab === tab.id ? palette.text : palette.dimmer,
                fontSize: 12,
                fontWeight: 600,
                cursor: "pointer",
                whiteSpace: "nowrap",
                transition: "all 0.2s",
              }}
            >
              {tab.label}
            </button>
          ))}
        </div>

        {/* Content */}
        <div key={activeTab} style={{ animation: "fadeSlide 0.3s ease" }}>
          <Content />
        </div>

        {/* Footer */}
        <div
          style={{
            marginTop: 36,
            padding: "14px 16px",
            borderRadius: 12,
            background: "rgba(239, 68, 68, 0.04)",
            border: "1px solid rgba(239, 68, 68, 0.1)",
            fontSize: 11,
            color: palette.dimmer,
            lineHeight: 1.6,
          }}
        >
          <strong style={{ color: palette.red }}>⚠ Disclaimer:</strong> Projeto para fins de
          entretenimento e educação. Risco real de perder 100% do capital. Não é recomendação financeira.
        </div>
      </div>
    </div>
  );
}

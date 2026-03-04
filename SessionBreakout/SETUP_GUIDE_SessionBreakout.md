# Session Breakout EA — Guia de Setup (IC Markets MT5)

## 1. Instalar o EA

1. Abra o MetaTrader 5 (conta IC Markets Raw Spread)
2. Menu: **Arquivo → Abrir Pasta de Dados**
3. Navegue até `MQL5/Experts/`
4. Copie o arquivo `SessionBreakout_v1.mq5` para esta pasta
5. No MT5, abra o **MetaEditor** (F4) e compile o arquivo (F7)
6. Volte ao MT5 e atualize a árvore de EAs (clique direito → Atualizar)

## 2. Configurar o Gráfico

Abra **dois gráficos** (um para cada par):

| Gráfico | Par      | Timeframe |
|---------|----------|-----------|
| 1       | GBP/USD  | M15       |
| 2       | EUR/JPY  | M15       |

> M15 é recomendado para melhor resolução do range asiático.
> O EA funciona em qualquer TF mas M15 dá mais precisão nos extremos.

## 3. Arrastar o EA para cada gráfico

Arraste o EA do Navigator para cada gráfico. Configure:

### GBP/USD (config recomendada)
```
Sessão Asiática:
  AsianStartHour    = 0
  AsianEndHour      = 8
  GMTOffset          = 0    (ajustar p/ horário de verão se necessário)

Entry & Exit:
  TP_Multiplier     = 1.5
  SL_Multiplier     = 0.5
  MinRangePips      = 25    (GBP/USD tem range maior)
  MaxRangePips      = 70
  BufferPips         = 3
  ExpirationBars    = 8

Risk Management:
  RiskPercent        = 5.0
  MaxDailyLossPct   = 15.0
  MaxTradesPerDay   = 2
  UseFixedLot       = true  (recomendado pro desafio)
  FixedLot           = 0.03  (ajustar ao balanço)

Filtros:
  FilterFriday      = true
  MaxSpreadPips     = 3

Identificação:
  MagicNumber       = 100201  (diferente para cada par!)
```

### EUR/JPY (config recomendada)
```
Sessão Asiática:
  AsianStartHour    = 0
  AsianEndHour      = 8
  GMTOffset          = 0

Entry & Exit:
  TP_Multiplier     = 1.5
  SL_Multiplier     = 0.5
  MinRangePips      = 20    (EUR/JPY pode ter range menor)
  MaxRangePips      = 60
  BufferPips         = 3
  ExpirationBars    = 8

Risk Management:
  RiskPercent        = 5.0
  MaxDailyLossPct   = 15.0
  MaxTradesPerDay   = 2
  UseFixedLot       = true
  FixedLot           = 0.02

Identificação:
  MagicNumber       = 100202  (diferente do GBP/USD!)
```

## 4. Habilitar Algo Trading

- Certifique-se que o botão **Algo Trading** está ativo (verde) na toolbar
- Em cada gráfico: clique direito no EA → Propriedades → aba "Comum":
  - ☑ Permitir negociação algorítmica
  - ☑ Permitir importação de DLLs (se necessário)

## 5. Habilitar Push Notifications

Para receber alertas no celular:
1. Instale o **MetaTrader 5** no smartphone
2. No app: Configurações → MetaQuotes ID → copie o ID
3. No MT5 desktop: Ferramentas → Opções → Notificações
4. Cole o MetaQuotes ID e teste com "Enviar notificação de teste"

## 6. Checar Horário do Servidor

**IMPORTANTE**: O offset GMT varia!

- IC Markets SC (Seychelles): GMT+0 no inverno, GMT+1 no verão (DST)
- IC Markets AU (Austrália): GMT+2 no inverno, GMT+3 no verão

Para verificar:
1. No MT5, abra a janela "Observação do Mercado"
2. Compare o horário do servidor com o horário GMT atual
3. A diferença é o seu `GMTOffset`

## 7. Teste antes de rodar de verdade

1. Primeiro teste no **Strategy Tester** (Ctrl+R):
   - Símbolo: GBPUSD
   - Período: M15
   - Datas: últimos 3 meses
   - Modelo: Cada tick baseado em ticks reais
   - Depósito: 25 (simula a alocação)

2. Depois rode **1 dia em conta demo** com os mesmos parâmetros

3. Só então ative na conta real com os $25

## 8. Fluxo Diário Esperado

```
00:00 GMT  → EA começa a monitorar range asiático
             (calcula high/low dos candles M15)

08:00 GMT  → Range finalizado. EA avalia:
             ✓ Range entre 20-70 pips? → Arma ordens
             ✗ Range fora dos limites? → Skip do dia

08:00-16:00 → Aguarda breakout
              Se BUY STOP ativado → cancela SELL STOP (OCO)
              Se SELL STOP ativado → cancela BUY STOP (OCO)

Posição aberta → Monitora:
  - Break-even quando preço anda 80% do range a favor
  - TP e SL já definidos na ordem

Nenhum breakout → Ordens expiram após 8 horas

23:00 GMT  → Novo dia, reset de estado
```

## 9. Troubleshooting

| Problema | Solução |
|----------|---------|
| "Trade disabled" | Verificar se Algo Trading está ativo |
| "Invalid stops" | SL/TP muito perto do preço. Aumentar BufferPips |
| "Not enough money" | Reduzir FixedLot ou RiskPercent |
| Ordens não aparecem | Checar GMTOffset — pode estar calculando range errado |
| "Expiration denied" | IC Markets pode não aceitar GTD. Mudar ExpirationBars para 0 (sem expiração, EA cancela manualmente) |
| Spread alert constante | Normal fora do horário de Londres. EA só tenta armar às 08:00 GMT |

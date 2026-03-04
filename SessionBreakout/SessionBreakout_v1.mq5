//+------------------------------------------------------------------+
//|                                       SessionBreakout_v1.mq5     |
//|                        Desafio $100 → $200 | Perna Forex         |
//|                          IC Markets | Raw Spread Account         |
//+------------------------------------------------------------------+
#property copyright "100to200 Challenge"
#property version   "1.00"
#property description "Asian Session Breakout → London/NY"
#property description "Opera o rompimento do range asiático"
#property description "R:R 3:1 | Max 1 trade/dia/par"

//+------------------------------------------------------------------+
//| INPUTS - Configuração Principal                                   |
//+------------------------------------------------------------------+
input group "═══ Sessão Asiática ═══"
input int      AsianStartHour     = 0;     // Hora início sessão asiática (GMT)
input int      AsianEndHour       = 8;     // Hora fim sessão asiática (GMT)
input int      GMTOffset          = 0;     // Offset do servidor vs GMT (IC Markets SC = 0 no inverno, ajustar se necessário)

input group "═══ Entry & Exit ═══"
input double   TP_Multiplier      = 1.5;   // Take Profit = X * range asiático
input double   SL_Multiplier      = 0.5;   // Stop Loss = X * range asiático
input int      MinRangePips       = 20;    // Range mínimo (pips) para operar
input int      MaxRangePips       = 80;    // Range máximo (pips) — evita dias de range enorme
input int      BufferPips         = 3;     // Buffer acima/abaixo do range para entry
input int      ExpirationBars     = 8;     // Cancelar pending orders após X barras H1

input group "═══ Risk Management ═══"
input double   RiskPercent        = 5.0;   // Risco por trade (% da conta)
input double   MaxDailyLossPct    = 15.0;  // Max perda diária (% da conta) — circuit breaker
input int      MaxTradesPerDay    = 2;     // Max trades por dia (total, todos os pares)
input bool     UseFixedLot        = false; // Usar lote fixo ao invés de % risco
input double   FixedLot           = 0.02;  // Lote fixo (se UseFixedLot = true)

input group "═══ Filtros ═══"
input bool     FilterFriday       = true;  // Não operar sexta-feira (rollover + spread)
input bool     FilterNews         = false; // Filtro de notícias (manual — desabilitar EA antes de NFP)
input bool     OnlyLondonOpen     = true;  // Só armar ordens na abertura de Londres
input int      MaxSpreadPips      = 3;     // Max spread permitido no momento da order

input group "═══ Notificação ═══"
input bool     SendPushNotif      = true;  // Enviar push notification pro celular
input bool     SendAlert          = true;  // Alerta sonoro no terminal

input group "═══ Identificação ═══"
input int      MagicNumber        = 100200;// Magic number para identificar ordens deste EA
input string   TradeComment       = "SB_v1"; // Comentário nas ordens

//+------------------------------------------------------------------+
//| Variáveis Globais                                                 |
//+------------------------------------------------------------------+
double   g_asianHigh;
double   g_asianLow;
double   g_asianRange;
bool     g_rangeCalculated;
bool     g_tradePlacedToday;
int      g_tradesToday;
double   g_dailyStartBalance;
datetime g_lastTradeDate;
double   g_point;
int      g_digits;

//+------------------------------------------------------------------+
//| Expert initialization                                             |
//+------------------------------------------------------------------+
int OnInit()
{
   // Validar inputs
   if(TP_Multiplier <= 0 || SL_Multiplier <= 0)
   {
      Print("❌ TP e SL multipliers devem ser > 0");
      return INIT_PARAMETERS_INCORRECT;
   }
   
   if(RiskPercent <= 0 || RiskPercent > 20)
   {
      Print("❌ RiskPercent deve estar entre 0.1 e 20");
      return INIT_PARAMETERS_INCORRECT;
   }
   
   // Configurar variáveis do símbolo
   g_point  = SymbolInfoDouble(_Symbol, SYMBOL_POINT);
   g_digits = (int)SymbolInfoInteger(_Symbol, SYMBOL_DIGITS);
   
   // Resetar estado
   ResetDailyState();
   
   Print("═══════════════════════════════════════");
   Print("  Session Breakout EA v1.0 | $100→$200");
   Print("  Símbolo: ", _Symbol);
   Print("  Timeframe: ", EnumToString(Period()));
   Print("  Magic: ", MagicNumber);
   Print("  Risco/trade: ", RiskPercent, "%");
   Print("  R:R = ", TP_Multiplier / SL_Multiplier, ":1");
   Print("═══════════════════════════════════════");
   
   return INIT_SUCCEEDED;
}

//+------------------------------------------------------------------+
//| Expert deinitialization                                           |
//+------------------------------------------------------------------+
void OnDeinit(const int reason)
{
   Print("EA desligado. Razão: ", reason);
}

//+------------------------------------------------------------------+
//| Expert tick function                                              |
//+------------------------------------------------------------------+
void OnTick()
{
   // Checar novo dia
   CheckNewDay();
   
   // Circuit breaker diário
   if(CheckDailyCircuitBreaker())
      return;
   
   // Não operar sexta se filtro ativo
   MqlDateTime dt;
   TimeCurrent(dt);
   if(FilterFriday && dt.day_of_week == 5)
      return;
   
   // Hora atual do servidor ajustada para GMT
   int serverHour = dt.hour;
   int gmtHour = (serverHour - GMTOffset + 24) % 24;
   
   //--- FASE 1: Calcular range asiático (durante a sessão)
   if(!g_rangeCalculated && gmtHour >= AsianStartHour && gmtHour < AsianEndHour)
   {
      CalculateAsianRange();
   }
   
   //--- FASE 2: Armar ordens no fim da sessão asiática
   if(!g_rangeCalculated && gmtHour == AsianEndHour)
   {
      FinalizeAsianRange();
   }
   
   //--- FASE 3: Monitorar ordens pendentes (cancelar se expiradas)
   ManagePendingOrders();
   
   //--- FASE 4: Gerenciar posições abertas (trailing, etc)
   ManageOpenPositions();
}

//+------------------------------------------------------------------+
//| Calcular range asiático em tempo real                             |
//+------------------------------------------------------------------+
void CalculateAsianRange()
{
   MqlDateTime dt;
   TimeCurrent(dt);
   int gmtHour = (dt.hour - GMTOffset + 24) % 24;
   
   // Buscar candles da sessão asiática de hoje
   datetime startTime = GetSessionStartTime();
   
   int bars = Bars(_Symbol, PERIOD_M15, startTime, TimeCurrent());
   if(bars <= 0) return;
   
   double high[], low[];
   ArraySetAsSeries(high, true);
   ArraySetAsSeries(low, true);
   
   if(CopyHigh(_Symbol, PERIOD_M15, startTime, TimeCurrent(), high) <= 0) return;
   if(CopyLow(_Symbol, PERIOD_M15, startTime, TimeCurrent(), low) <= 0) return;
   
   int count = ArraySize(high);
   if(count == 0) return;
   
   g_asianHigh = high[ArrayMaximum(high, 0, count)];
   g_asianLow  = low[ArrayMinimum(low, 0, count)];
   g_asianRange = g_asianHigh - g_asianLow;
}

//+------------------------------------------------------------------+
//| Finalizar range e armar ordens                                    |
//+------------------------------------------------------------------+
void FinalizeAsianRange()
{
   if(g_tradePlacedToday || g_tradesToday >= MaxTradesPerDay)
      return;
   
   // Calcular range final
   CalculateAsianRange();
   
   double rangePips = g_asianRange / PipSize();
   
   // Validar range
   if(rangePips < MinRangePips)
   {
      Print("⏭️ Range muito pequeno: ", DoubleToString(rangePips, 1), " pips < ", MinRangePips);
      Notify("⏭️ " + _Symbol + " skip: range " + DoubleToString(rangePips, 1) + " pips (mín: " + IntegerToString(MinRangePips) + ")");
      g_rangeCalculated = true;
      return;
   }
   
   if(rangePips > MaxRangePips)
   {
      Print("⏭️ Range muito grande: ", DoubleToString(rangePips, 1), " pips > ", MaxRangePips);
      Notify("⏭️ " + _Symbol + " skip: range " + DoubleToString(rangePips, 1) + " pips (máx: " + IntegerToString(MaxRangePips) + ")");
      g_rangeCalculated = true;
      return;
   }
   
   // Checar spread
   double currentSpread = SymbolInfoInteger(_Symbol, SYMBOL_SPREAD) * g_point / PipSize();
   if(currentSpread > MaxSpreadPips)
   {
      Print("⏭️ Spread muito alto: ", DoubleToString(currentSpread, 1), " pips");
      g_rangeCalculated = true;
      return;
   }
   
   // Calcular níveis
   double buffer = BufferPips * PipSize();
   double buyEntry  = NormalizeDouble(g_asianHigh + buffer, g_digits);
   double sellEntry = NormalizeDouble(g_asianLow - buffer, g_digits);
   
   double buyTP  = NormalizeDouble(buyEntry + g_asianRange * TP_Multiplier, g_digits);
   double buySL  = NormalizeDouble(buyEntry - g_asianRange * SL_Multiplier, g_digits);
   double sellTP = NormalizeDouble(sellEntry - g_asianRange * TP_Multiplier, g_digits);
   double sellSL = NormalizeDouble(sellEntry + g_asianRange * SL_Multiplier, g_digits);
   
   // Calcular lote
   double riskAmount = AccountInfoDouble(ACCOUNT_BALANCE) * (RiskPercent / 100.0);
   double slPips     = g_asianRange * SL_Multiplier / PipSize();
   double lotSize    = CalculateLotSize(riskAmount, slPips);
   
   if(UseFixedLot)
      lotSize = FixedLot;
   
   // Expiração das ordens
   datetime expiration = TimeCurrent() + ExpirationBars * 3600;
   
   // Colocar Buy Stop
   bool buyPlaced = PlacePendingOrder(ORDER_TYPE_BUY_STOP, buyEntry, buySL, buyTP, lotSize, expiration, "BUY_BRK");
   
   // Colocar Sell Stop
   bool sellPlaced = PlacePendingOrder(ORDER_TYPE_SELL_STOP, sellEntry, sellSL, sellTP, lotSize, expiration, "SELL_BRK");
   
   if(buyPlaced || sellPlaced)
   {
      g_tradePlacedToday = true;
      g_tradesToday++;
      
      string msg = StringFormat(
         "🎯 %s Breakout Armado\n"
         "Range: %.1f pips\n"
         "BUY STOP: %s (TP: %s | SL: %s)\n"
         "SELL STOP: %s (TP: %s | SL: %s)\n"
         "Lote: %.2f | Risco: $%.2f",
         _Symbol, rangePips,
         DoubleToString(buyEntry, g_digits), DoubleToString(buyTP, g_digits), DoubleToString(buySL, g_digits),
         DoubleToString(sellEntry, g_digits), DoubleToString(sellTP, g_digits), DoubleToString(sellSL, g_digits),
         lotSize, riskAmount
      );
      
      Print(msg);
      Notify(msg);
   }
   
   g_rangeCalculated = true;
}

//+------------------------------------------------------------------+
//| Colocar ordem pendente                                            |
//+------------------------------------------------------------------+
bool PlacePendingOrder(ENUM_ORDER_TYPE type, double price, double sl, double tp, 
                       double lots, datetime expiration, string label)
{
   MqlTradeRequest request = {};
   MqlTradeResult  result  = {};
   
   request.action     = TRADE_ACTION_PENDING;
   request.symbol     = _Symbol;
   request.volume     = lots;
   request.type       = type;
   request.price      = price;
   request.sl         = sl;
   request.tp         = tp;
   request.magic      = MagicNumber;
   request.comment    = TradeComment + "_" + label;
   request.type_time  = ORDER_TIME_SPECIFIED;
   request.expiration = expiration;
   
   // Filling mode
   long filling = SymbolInfoInteger(_Symbol, SYMBOL_FILLING_MODE);
   if(filling & SYMBOL_FILLING_IOC)
      request.type_filling = ORDER_FILLING_IOC;
   else if(filling & SYMBOL_FILLING_FOK)
      request.type_filling = ORDER_FILLING_FOK;
   else
      request.type_filling = ORDER_FILLING_RETURN;
   
   if(!OrderSend(request, result))
   {
      Print("❌ Erro ao colocar ", EnumToString(type), ": ", result.retcode, " - ", GetRetcodeDescription(result.retcode));
      return false;
   }
   
   Print("✅ ", label, " colocada @ ", DoubleToString(price, g_digits), " | Ticket: ", result.order);
   return true;
}

//+------------------------------------------------------------------+
//| Gerenciar ordens pendentes                                        |
//+------------------------------------------------------------------+
void ManagePendingOrders()
{
   // OCO Logic: Se uma ordem é ativada, cancelar a outra
   bool hasPosition = false;
   
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      if(PositionGetSymbol(i) == _Symbol && 
         PositionGetInteger(POSITION_MAGIC) == MagicNumber)
      {
         hasPosition = true;
         break;
      }
   }
   
   // Se temos posição aberta, cancelar todas as pendentes
   if(hasPosition)
   {
      for(int i = OrdersTotal() - 1; i >= 0; i--)
      {
         ulong ticket = OrderGetTicket(i);
         if(ticket > 0 && 
            OrderGetString(ORDER_SYMBOL) == _Symbol && 
            OrderGetInteger(ORDER_MAGIC) == MagicNumber)
         {
            MqlTradeRequest request = {};
            MqlTradeResult  result  = {};
            request.action = TRADE_ACTION_REMOVE;
            request.order  = ticket;
            
            if(OrderSend(request, result))
               Print("🗑️ Ordem pendente cancelada (OCO): #", ticket);
         }
      }
   }
}

//+------------------------------------------------------------------+
//| Gerenciar posições abertas                                        |
//+------------------------------------------------------------------+
void ManageOpenPositions()
{
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      if(PositionGetSymbol(i) != _Symbol) continue;
      if(PositionGetInteger(POSITION_MAGIC) != MagicNumber) continue;
      
      ulong ticket = PositionGetInteger(POSITION_TICKET);
      double profit = PositionGetDouble(POSITION_PROFIT);
      double openPrice = PositionGetDouble(POSITION_PRICE_OPEN);
      double currentSL = PositionGetDouble(POSITION_SL);
      double currentTP = PositionGetDouble(POSITION_TP);
      ENUM_POSITION_TYPE posType = (ENUM_POSITION_TYPE)PositionGetInteger(POSITION_TYPE);
      
      // Break-even: mover SL para entry quando preço anda 1x o range a favor
      double moveThreshold = g_asianRange * 0.8;
      double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
      double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
      
      if(posType == POSITION_TYPE_BUY)
      {
         // Se preço subiu o suficiente e SL ainda abaixo do entry
         if(bid - openPrice >= moveThreshold && currentSL < openPrice)
         {
            ModifySL(ticket, NormalizeDouble(openPrice + BufferPips * PipSize(), g_digits));
            Notify("🔒 " + _Symbol + " BUY: SL movido para break-even + buffer");
         }
      }
      else if(posType == POSITION_TYPE_SELL)
      {
         // Se preço desceu o suficiente e SL ainda acima do entry
         if(openPrice - ask >= moveThreshold && currentSL > openPrice)
         {
            ModifySL(ticket, NormalizeDouble(openPrice - BufferPips * PipSize(), g_digits));
            Notify("🔒 " + _Symbol + " SELL: SL movido para break-even + buffer");
         }
      }
   }
}

//+------------------------------------------------------------------+
//| Modificar Stop Loss                                               |
//+------------------------------------------------------------------+
void ModifySL(ulong ticket, double newSL)
{
   MqlTradeRequest request = {};
   MqlTradeResult  result  = {};
   
   request.action   = TRADE_ACTION_SLTP;
   request.position = ticket;
   request.symbol   = _Symbol;
   request.sl       = newSL;
   request.tp       = PositionGetDouble(POSITION_TP);
   
   if(!OrderSend(request, result))
      Print("❌ Erro ao mover SL: ", result.retcode);
   else
      Print("🔒 SL movido para ", DoubleToString(newSL, g_digits));
}

//+------------------------------------------------------------------+
//| Circuit Breaker diário                                            |
//+------------------------------------------------------------------+
bool CheckDailyCircuitBreaker()
{
   double currentBalance = AccountInfoDouble(ACCOUNT_BALANCE);
   double dailyPnL = (currentBalance - g_dailyStartBalance) / g_dailyStartBalance * 100.0;
   
   if(dailyPnL < -MaxDailyLossPct)
   {
      // Fechar todas as posições
      CloseAllPositions();
      CancelAllPendingOrders();
      
      string msg = StringFormat(
         "🚨 CIRCUIT BREAKER ATIVADO!\n"
         "Perda diária: %.2f%% (limite: %.2f%%)\n"
         "Todas posições fechadas. EA pausado até amanhã.",
         dailyPnL, MaxDailyLossPct
      );
      Print(msg);
      Notify(msg);
      
      return true;
   }
   
   return false;
}

//+------------------------------------------------------------------+
//| Fechar todas as posições deste EA                                 |
//+------------------------------------------------------------------+
void CloseAllPositions()
{
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      if(PositionGetSymbol(i) != _Symbol) continue;
      if(PositionGetInteger(POSITION_MAGIC) != MagicNumber) continue;
      
      ulong ticket = PositionGetInteger(POSITION_TICKET);
      
      MqlTradeRequest request = {};
      MqlTradeResult  result  = {};
      
      request.action   = TRADE_ACTION_DEAL;
      request.position = ticket;
      request.symbol   = _Symbol;
      request.volume   = PositionGetDouble(POSITION_VOLUME);
      request.type     = (PositionGetInteger(POSITION_TYPE) == POSITION_TYPE_BUY) 
                         ? ORDER_TYPE_SELL : ORDER_TYPE_BUY;
      request.price    = (request.type == ORDER_TYPE_SELL) 
                         ? SymbolInfoDouble(_Symbol, SYMBOL_BID) 
                         : SymbolInfoDouble(_Symbol, SYMBOL_ASK);
      request.magic    = MagicNumber;
      request.comment  = "CIRCUIT_BREAKER";
      
      long filling = SymbolInfoInteger(_Symbol, SYMBOL_FILLING_MODE);
      if(filling & SYMBOL_FILLING_IOC)
         request.type_filling = ORDER_FILLING_IOC;
      else if(filling & SYMBOL_FILLING_FOK)
         request.type_filling = ORDER_FILLING_FOK;
      else
         request.type_filling = ORDER_FILLING_RETURN;
      
      if(OrderSend(request, result))
         Print("🔴 Posição fechada (CB): #", ticket);
      else
         Print("❌ Erro ao fechar posição: ", result.retcode);
   }
}

//+------------------------------------------------------------------+
//| Cancelar todas as ordens pendentes                                |
//+------------------------------------------------------------------+
void CancelAllPendingOrders()
{
   for(int i = OrdersTotal() - 1; i >= 0; i--)
   {
      ulong ticket = OrderGetTicket(i);
      if(ticket > 0 && 
         OrderGetString(ORDER_SYMBOL) == _Symbol && 
         OrderGetInteger(ORDER_MAGIC) == MagicNumber)
      {
         MqlTradeRequest request = {};
         MqlTradeResult  result  = {};
         request.action = TRADE_ACTION_REMOVE;
         request.order  = ticket;
         
         if(OrderSend(request, result))
            Print("🗑️ Ordem pendente cancelada (CB): #", ticket);
      }
   }
}

//+------------------------------------------------------------------+
//| Calcular tamanho do lote baseado no risco                         |
//+------------------------------------------------------------------+
double CalculateLotSize(double riskAmount, double slPips)
{
   if(slPips <= 0) return SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
   
   // Valor do pip para 1 lote
   double tickValue = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_VALUE);
   double tickSize  = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE);
   double pipValue  = tickValue * (PipSize() / tickSize);
   
   if(pipValue <= 0) return SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
   
   double lots = riskAmount / (slPips * pipValue);
   
   // Normalizar para step do broker
   double minLot  = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
   double maxLot  = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MAX);
   double lotStep = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);
   
   lots = MathFloor(lots / lotStep) * lotStep;
   lots = MathMax(lots, minLot);
   lots = MathMin(lots, maxLot);
   
   return NormalizeDouble(lots, 2);
}

//+------------------------------------------------------------------+
//| Helper: Tamanho do pip                                            |
//+------------------------------------------------------------------+
double PipSize()
{
   // Para pares JPY: 1 pip = 0.01 | Para outros: 1 pip = 0.0001
   if(g_digits == 3 || g_digits == 5)
      return g_point * 10;
   else
      return g_point;
}

//+------------------------------------------------------------------+
//| Helper: Hora de início da sessão asiática de hoje                 |
//+------------------------------------------------------------------+
datetime GetSessionStartTime()
{
   MqlDateTime dt;
   TimeCurrent(dt);
   dt.hour = AsianStartHour + GMTOffset;
   dt.min  = 0;
   dt.sec  = 0;
   return StructToTime(dt);
}

//+------------------------------------------------------------------+
//| Checar novo dia e resetar estado                                  |
//+------------------------------------------------------------------+
void CheckNewDay()
{
   MqlDateTime dtNow;
   TimeCurrent(dtNow);
   
   MqlDateTime dtLast;
   TimeToStruct(g_lastTradeDate, dtLast);
   
   if(dtNow.day != dtLast.day || dtNow.mon != dtLast.mon || dtNow.year != dtLast.year)
   {
      ResetDailyState();
      
      // Log do novo dia
      double balance = AccountInfoDouble(ACCOUNT_BALANCE);
      double equity  = AccountInfoDouble(ACCOUNT_EQUITY);
      string msg = StringFormat(
         "📅 Novo dia: %d/%02d/%02d\n"
         "Balance: $%.2f | Equity: $%.2f\n"
         "Meta: $200 | Falta: $%.2f",
         dtNow.year, dtNow.mon, dtNow.day,
         balance, equity,
         MathMax(200.0 - balance, 0)
      );
      Print(msg);
      Notify(msg);
   }
}

//+------------------------------------------------------------------+
//| Resetar estado diário                                             |
//+------------------------------------------------------------------+
void ResetDailyState()
{
   g_asianHigh        = 0;
   g_asianLow         = DBL_MAX;
   g_asianRange       = 0;
   g_rangeCalculated  = false;
   g_tradePlacedToday = false;
   g_tradesToday      = 0;
   g_dailyStartBalance = AccountInfoDouble(ACCOUNT_BALANCE);
   g_lastTradeDate    = TimeCurrent();
}

//+------------------------------------------------------------------+
//| Notificação unificada                                             |
//+------------------------------------------------------------------+
void Notify(string message)
{
   if(SendPushNotif)
      SendNotification(message);
   if(SendAlert)
      Alert(message);
}

//+------------------------------------------------------------------+
//| Descrição de retcode                                              |
//+------------------------------------------------------------------+
string GetRetcodeDescription(uint retcode)
{
   switch(retcode)
   {
      case 10004: return "Requote";
      case 10006: return "Request rejected";
      case 10007: return "Request canceled by trader";
      case 10008: return "Order placed";
      case 10009: return "Request completed";
      case 10010: return "Only part filled";
      case 10011: return "Request processing error";
      case 10012: return "Request canceled by timeout";
      case 10013: return "Invalid request";
      case 10014: return "Invalid volume";
      case 10015: return "Invalid price";
      case 10016: return "Invalid stops";
      case 10017: return "Trade disabled";
      case 10018: return "Market closed";
      case 10019: return "Not enough money";
      case 10020: return "Price changed";
      case 10021: return "No quotes to process";
      case 10022: return "Order state invalid";
      case 10023: return "Request too frequent";
      case 10024: return "Auto trading disabled";
      case 10025: return "Modification denied (too close to market)";
      case 10026: return "Trade context busy";
      case 10027: return "Expiration denied by broker";
      case 10028: return "Too many pending orders";
      default:    return "Unknown error (" + IntegerToString(retcode) + ")";
   }
}

//+------------------------------------------------------------------+
//| Trade event handler — notificar quando ordem é executada          |
//+------------------------------------------------------------------+
void OnTradeTransaction(const MqlTradeTransaction& trans,
                        const MqlTradeRequest& request,
                        const MqlTradeResult& result)
{
   // Notificar quando uma pending order é ativada (vira deal)
   if(trans.type == TRADE_TRANSACTION_DEAL_ADD)
   {
      // Verificar se é nosso
      if(trans.order_state != ORDER_STATE_STARTED) return;
      
      HistoryDealSelect(trans.deal);
      long dealMagic = HistoryDealGetInteger(trans.deal, DEAL_MAGIC);
      
      if(dealMagic == MagicNumber)
      {
         ENUM_DEAL_TYPE dealType = (ENUM_DEAL_TYPE)HistoryDealGetInteger(trans.deal, DEAL_TYPE);
         double dealPrice  = HistoryDealGetDouble(trans.deal, DEAL_PRICE);
         double dealVolume = HistoryDealGetDouble(trans.deal, DEAL_VOLUME);
         double dealProfit = HistoryDealGetDouble(trans.deal, DEAL_PROFIT);
         
         string direction = (dealType == DEAL_TYPE_BUY) ? "BUY" : "SELL";
         
         // Checar se é abertura ou fechamento
         ENUM_DEAL_ENTRY entry = (ENUM_DEAL_ENTRY)HistoryDealGetInteger(trans.deal, DEAL_ENTRY);
         
         if(entry == DEAL_ENTRY_IN)
         {
            string msg = StringFormat(
               "🟢 BREAKOUT ATIVADO!\n"
               "%s %s @ %s\n"
               "Volume: %.2f lots\n"
               "Asian range: %.1f pips",
               direction, _Symbol,
               DoubleToString(dealPrice, g_digits),
               dealVolume,
               g_asianRange / PipSize()
            );
            Notify(msg);
         }
         else if(entry == DEAL_ENTRY_OUT)
         {
            string emoji = (dealProfit >= 0) ? "💰" : "🔴";
            string msg = StringFormat(
               "%s Trade Fechado!\n"
               "%s %s @ %s\n"
               "P&L: $%.2f\n"
               "Balance: $%.2f",
               emoji, direction, _Symbol,
               DoubleToString(dealPrice, g_digits),
               dealProfit,
               AccountInfoDouble(ACCOUNT_BALANCE)
            );
            Notify(msg);
         }
      }
   }
}
//+------------------------------------------------------------------+

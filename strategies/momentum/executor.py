"""
Momentum Scalper — abre posições no breakout e gerencia saída.

Configuração (momentum/config.yaml):
  - trailing_stop_pct : 1.5%  (trailing stop sobe com o preço)
  - fixed_tp_pct      : 3.0%  (take profit fixo)
  - sl_pct            : 1.5%  (stop loss fixo)
  - max_open_trades   : 3     (máximo de trades simultâneos)
  - leverage          : 5x    (margem isolada)

Paper trading: injetar PaperExchange(ccxt.bybit) como exchange.
A lógica de execução não muda — PaperExchange simula ordens localmente.

Crash recovery:
  - Estado salvo em state/momentum.json após cada trade aberto/fechado.
  - Na reinicialização: carrega trades salvos + reconcilia com exchange (live).
  - Paper mode: aceita estado salvo diretamente.
"""
import asyncio
import dataclasses
import logging
import time
from dataclasses import dataclass, field

from strategies.base import BaseStrategy, StrategyStatus
from strategies.momentum.detector import MomentumDetector, Signal
from strategies.state_manager import clear_state, load_state, save_state

log = logging.getLogger("momentum")


@dataclass
class Trade:
    symbol: str
    side: str             # "buy"
    size: float           # contratos (USD alocado * leverage / price)
    entry_price: float
    tp_price: float       # take profit
    sl_price: float       # stop loss
    trailing_stop: float  # sobe com o preço de pico
    peak_price: float     # maior preço atingido desde a entrada
    leverage: int = 5
    timestamp: float = field(default_factory=time.time)
    pnl: float = 0.0      # P&L corrente (com alavancagem)
    closed: bool = False
    close_reason: str = ""


class MomentumScalper(BaseStrategy):
    """
    Estratégia momentum completa:
      - Detector identifica breakouts de volume+VWAP
      - Executor abre posição (market order) e gerencia trailing/SL/TP
      - Max 3 trades simultâneos; capital proporcional à alocação
    """

    def __init__(self, config: dict, exchange, allocation: float, paper_trade: bool = False):
        super().__init__("momentum", allocation, paper_trade)
        self.cfg = config
        self.ex = exchange
        self.detector = MomentumDetector(config, exchange)

        self.tp_pct       = float(config.get("fixed_tp_pct",      3.0)) / 100.0
        self.sl_pct       = float(config.get("sl_pct",            1.5)) / 100.0
        self.trailing_pct = float(config.get("trailing_stop_pct", 1.5)) / 100.0
        self.leverage     = int(config.get("leverage",   5))
        self.max_trades   = int(config.get("max_open_trades", 3))

        self._trades: dict[str, Trade] = {}  # symbol → Trade (última por símbolo)
        self._realized_pnl: float = 0.0
        self._state_loaded: bool = False     # flag: recovery executado?

    # ─────────────────────────────────────────────
    # Interface BaseStrategy
    # ─────────────────────────────────────────────

    async def tick(self) -> StrategyStatus:
        """Ciclo principal: recovery (1ª vez) → gerencia posições → detecta sinais."""
        # Recovery: executado apenas no primeiro tick
        if not self._state_loaded:
            self._state_loaded = True
            self._load_state()
            if self._trades and not self.paper_trade:
                await self._reconcile_with_exchange()

        # 1. Gerencia trades abertos (trailing, SL, TP)
        await self._manage_trades()

        # 2. Busca novos sinais se abaixo do limite
        open_count = sum(1 for t in self._trades.values() if not t.closed)
        if open_count < self.max_trades:
            try:
                signals = await self.detector.get_signals()
            except Exception as exc:
                log.error("Erro ao buscar sinais: %s", exc)
                signals = []

            for sig in signals:
                if open_count >= self.max_trades:
                    break
                existing = self._trades.get(sig.symbol)
                if existing and not existing.closed:
                    continue
                await self._open_trade(sig)
                open_count += 1

        # 3. Calcula P&L não realizado
        open_count = sum(1 for t in self._trades.values() if not t.closed)
        unrealized  = sum(t.pnl for t in self._trades.values() if not t.closed)

        return StrategyStatus(
            id=self.id,
            active=self._active,
            pnl_realized=self._realized_pnl,
            pnl_unrealized=unrealized,
            allocation=self.allocation,
            open_orders=open_count,
            paper_trade=self.paper_trade,
            extra={
                "open_trades":  open_count,
                "total_trades": len(self._trades),
            },
        )

    async def close_all(self) -> None:
        """Fecha todos os trades abertos e limpa estado persistido.
        Usado por circuit breakers — fecha tudo e limpa estado."""
        tasks = [
            self._close_trade(t, "close_all")
            for t in self._trades.values()
            if not t.closed
        ]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        clear_state(self.id)
        log.info("Momentum: todas as posições fechadas e estado limpo")

    async def shutdown(self) -> None:
        """Encerramento gracioso: salva estado sem fechar posições.
        Trades permanecem abertos e serão reconciliados no próximo boot."""
        self._save_state()
        open_count = sum(1 for t in self._trades.values() if not t.closed)
        log.info(
            "Momentum: shutdown gracioso — %d trade(s) salvos para recovery",
            open_count,
        )

    async def resize(self, new_allocation: float) -> None:
        self.allocation = new_allocation

    async def get_pnl(self) -> float:
        unrealized = sum(t.pnl for t in self._trades.values() if not t.closed)
        return self._realized_pnl + unrealized

    # ─────────────────────────────────────────────
    # Abertura de trade
    # ─────────────────────────────────────────────

    async def _open_trade(self, signal: Signal) -> None:
        """Abre trade de breakout (market order)."""
        sym   = signal.symbol
        entry = signal.current_price
        if entry <= 0:
            return

        alloc_per_trade = self.allocation / self.max_trades
        size = round((alloc_per_trade * self.leverage) / entry, 4)
        if size <= 0:
            return

        tp    = entry * (1.0 + self.tp_pct)
        sl    = entry * (1.0 - self.sl_pct)
        trail = entry * (1.0 - self.trailing_pct)

        try:
            await self.ex.set_leverage(self.leverage, sym)
            await self.ex.set_margin_mode("isolated", sym)
            await self.ex.create_market_order(sym, "buy", size, params={"reduceOnly": False})

            trade = Trade(
                symbol=sym,
                side="buy",
                size=size,
                entry_price=entry,
                tp_price=tp,
                sl_price=sl,
                trailing_stop=trail,
                peak_price=entry,
                leverage=self.leverage,
            )
            self._trades[sym] = trade
            self._save_state()

            mode = "[PAPER]" if self.paper_trade else "[LIVE]"
            log.info(
                "%s Trade aberto: %s | size=%.4f entry=%.4f TP=%.4f SL=%.4f vol=%.1fx",
                mode, sym, size, entry, tp, sl, signal.volume_ratio,
            )
        except Exception as exc:
            log.error("Erro ao abrir trade %s: %s", sym, exc)

    # ─────────────────────────────────────────────
    # Gerenciamento de trades abertos
    # ─────────────────────────────────────────────

    async def _manage_trades(self) -> None:
        """Atualiza trailing stop e verifica condições de saída."""
        tasks = [
            self._check_trade(trade)
            for trade in self._trades.values()
            if not trade.closed
        ]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _check_trade(self, trade: Trade) -> None:
        """Verifica um trade: atualiza trailing stop e fecha se necessário."""
        try:
            ticker = await self.ex.fetch_ticker(trade.symbol)
            current = float(ticker["last"])
        except Exception as exc:
            log.debug("Erro ao buscar ticker %s: %s", trade.symbol, exc)
            return

        if current > trade.peak_price:
            trade.peak_price = current
            new_trail = current * (1.0 - self.trailing_pct)
            if new_trail > trade.trailing_stop:
                trade.trailing_stop = new_trail

        trade.pnl = (current - trade.entry_price) * trade.size * trade.leverage

        if current >= trade.tp_price:
            await self._close_trade(trade, "TP")
        elif current <= trade.sl_price:
            await self._close_trade(trade, "SL")
        elif current <= trade.trailing_stop and current > trade.entry_price:
            await self._close_trade(trade, "trailing_stop")

    async def _close_trade(self, trade: Trade, reason: str) -> None:
        """Fecha um trade específico (market order reduceOnly)."""
        if trade.closed:
            return
        try:
            ticker = await self.ex.fetch_ticker(trade.symbol)
            exit_price = float(ticker["last"])

            await self.ex.create_market_order(
                trade.symbol, "sell", trade.size, params={"reduceOnly": True}
            )

            trade.pnl = (exit_price - trade.entry_price) * trade.size * trade.leverage
            self._realized_pnl += trade.pnl
            trade.closed = True
            trade.close_reason = reason
            self._save_state()

            mode = "[PAPER]" if self.paper_trade else "[LIVE]"
            log.info(
                "%s Trade fechado (%s): %s | exit=%.4f P&L=$%.2f",
                mode, reason, trade.symbol, exit_price, trade.pnl,
            )
        except Exception as exc:
            log.error("Erro ao fechar trade %s (%s): %s", trade.symbol, reason, exc)

    # ─────────────────────────────────────────────
    # Persistência e recuperação de estado
    # ─────────────────────────────────────────────

    def _save_state(self) -> None:
        """Persiste trades abertos em JSON."""
        open_trades = {
            sym: dataclasses.asdict(t)
            for sym, t in self._trades.items()
            if not t.closed
        }
        save_state(self.id, {
            "trades":       open_trades,
            "realized_pnl": self._realized_pnl,
        })

    def _load_state(self) -> None:
        """
        Carrega trades salvos na inicialização.
        Só restaura trades não fechados.
        """
        state = load_state(self.id)
        if not state:
            return

        self._realized_pnl = float(state.get("realized_pnl", 0.0))
        restored = 0
        for sym, t_data in state.get("trades", {}).items():
            if t_data.get("closed", True):
                continue
            try:
                self._trades[sym] = Trade(**t_data)
                restored += 1
            except Exception as exc:
                log.warning("Erro ao restaurar trade %s: %s", sym, exc)

        if restored:
            log.info(
                "Momentum: %d trade(s) restaurados do estado salvo | P&L=%.2f",
                restored, self._realized_pnl,
            )

    async def _reconcile_with_exchange(self) -> None:
        """
        Live mode: reconcilia trades restaurados com posições reais no Bybit.

        - Posição encontrada na exchange → mantém trade, atualiza entry_price
        - Posição NÃO encontrada → trade fechou enquanto o bot estava offline;
          marca como fechado e registra P&L como zero (não temos o preço de saída)
        """
        if not self._trades:
            return

        symbols = list(self._trades.keys())
        try:
            positions = await self.ex.fetch_positions(symbols)
            pos_by_sym = {
                p["symbol"]: p
                for p in positions
                if abs(p.get("contracts", 0) or 0) > 0
            }
        except Exception as exc:
            log.error("Momentum: reconciliação falhou (%s) — mantendo estado salvo", exc)
            return

        for sym, trade in list(self._trades.items()):
            if sym in pos_by_sym:
                # Posição ainda aberta — sincroniza entry_price com a exchange
                actual_entry = float(pos_by_sym[sym].get("entryPrice", trade.entry_price))
                trade.entry_price = actual_entry
                log.info("Momentum: trade %s reconciliado (entry=%.4f)", sym, actual_entry)
            else:
                # Posição fechou enquanto o bot estava offline
                log.info(
                    "Momentum: trade %s não encontrado na exchange — "
                    "marcando como fechado (P&L desconhecido)",
                    sym,
                )
                trade.closed = True
                trade.close_reason = "closed_while_offline"

        self._save_state()

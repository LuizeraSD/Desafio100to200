"""
Grid Bot — Perna 1 | Binance Futures | SOL/USDT
Range dinâmico baseado em ATR(24h).
Auto-rebalance: se preço sair do range, fecha tudo e reabre grid centrado no novo preço.
"""
import asyncio
import logging
import time
from typing import Optional

import ccxt.async_support as ccxt

from strategies.base import BaseStrategy, StrategyStatus
from strategies.state_manager import clear_state, load_state, save_state

log = logging.getLogger("grid_bot")


class GridBot(BaseStrategy):
    def __init__(self, config: dict, exchange, allocation: float, paper_trade: bool = False):
        super().__init__("grid_bot", allocation, paper_trade)
        self.cfg = config
        self.ex = exchange  # ccxt.bybit ou PaperExchange(ccxt.bybit)

        self.symbol: str = config["symbol"]
        self.leverage: int = config["leverage"]
        self.margin_mode: str = config["margin_mode"]
        self.num_grids: int = config["num_grids"]
        self.atr_period: int = config["atr_period"]
        self.atr_multiplier: float = config["atr_multiplier"]
        self.circuit_breaker_pct: float = config["circuit_breaker_pct"]

        # Estado do grid
        self.grid_levels: list[float] = []
        self.grid_top: float = 0.0
        self.grid_bottom: float = 0.0
        self.grid_step: float = 0.0

        # Rastreamento de ordens: {nível_idx: client_order_id}
        self.buy_orders: dict[int, str] = {}
        self.sell_orders: dict[int, str] = {}

        # P&L
        self.pnl_realized: float = 0.0
        self.initial_allocation: float = allocation
        self._initialized: bool = False
        self._last_reinvest: float = 0.0

        # Notifier (opcional — injetado pelo orchestrator)
        self.notify = None

    # ─────────────────────────────────────────────
    # Interface BaseStrategy
    # ─────────────────────────────────────────────

    async def tick(self) -> StrategyStatus:
        if not self._active:
            return self._status(active=False)

        try:
            if not self._initialized:
                await self._setup()
                # Tenta retomar de estado salvo (crash recovery).
                # Se não encontrar estado válido, abre grid novo.
                if not await self._try_resume_from_state():
                    await self._open_grid()
                self._initialized = True

            price = await self._get_price()

            # Auto-rebalance: preço fora do range
            if price < self.grid_bottom or price > self.grid_top:
                log.warning(
                    "Preço %.4f fora do range [%.4f, %.4f] — reposicionando grid",
                    price, self.grid_bottom, self.grid_top,
                )
                if self.notify:
                    await self.notify(
                        f"⚡ Grid Bot: preço {price:.2f} saiu do range "
                        f"[{self.grid_bottom:.2f}, {self.grid_top:.2f}]\n"
                        "Reposicionando grid..."
                    )
                await self.close_all()
                await self._open_grid()

            # Checar ordens preenchidas e recolocar opostas (passa preço já obtido)
            await self._process_fills(price)

            # Reinvestimento automático
            await self._maybe_reinvest()

            pnl_unrealized = await self._get_unrealized_pnl()
            open_orders = len(self.buy_orders) + len(self.sell_orders)

            extra = {
                "price": price,
                "grid_top": self.grid_top,
                "grid_bottom": self.grid_bottom,
                "grid_step": self.grid_step,
            }
            if self.paper_trade and hasattr(self.ex, "get_paper_summary"):
                extra["paper_summary"] = self.ex.get_paper_summary(self.symbol)

            return self._status(
                pnl_realized=self.pnl_realized,
                pnl_unrealized=pnl_unrealized,
                open_orders=open_orders,
                extra=extra,
            )

        except ccxt.NetworkError as e:
            log.error("Erro de rede: %s", e)
            return self._status(extra={"error": str(e)})
        except ccxt.ExchangeError as e:
            log.error("Erro na exchange: %s", e)
            return self._status(extra={"error": str(e)})

    async def close_all(self) -> None:
        log.info("Fechando todas as ordens e posições do Grid Bot")
        symbol_ccxt = self.symbol

        # Cancelar todas as ordens via cancel_all_orders (sem fetch_open_orders).
        # Importante: fetch_open_orders no PaperExchange simula fills — chamar antes
        # do cancel preencheria ordens limit indevidamente durante o fechamento.
        try:
            await self.ex.cancel_all_orders(symbol_ccxt)
            log.debug("Todas as ordens canceladas via cancel_all_orders")
        except Exception as e:
            log.error("Erro ao cancelar ordens: %s", e)

        # Fechar posição aberta (se houver)
        try:
            position = await self._get_position()
            if position and abs(position["contracts"]) > 0:
                side = "sell" if position["side"] == "long" else "buy"
                await self.ex.create_market_order(
                    symbol_ccxt,
                    side,
                    abs(position["contracts"]),
                    params={"reduceOnly": True},
                )
                log.info("Posição fechada: %s", position)
        except Exception as e:
            log.error("Erro ao fechar posição: %s", e)

        self.buy_orders.clear()
        self.sell_orders.clear()
        self._initialized = False
        # Remove estado salvo: encerramento limpo → próximo restart inicia do zero
        clear_state(self.id)

    async def shutdown(self) -> None:
        """Encerramento gracioso: salva estado do grid sem fechar posições.
        Ordens na exchange permanecem ativas; serão reconciliadas no próximo boot."""
        self._save_state()
        log.info(
            "Grid Bot: shutdown gracioso — %d buy + %d sell ordens salvas para recovery",
            len(self.buy_orders), len(self.sell_orders),
        )

    async def resize(self, new_allocation: float) -> None:
        log.info("Resize: %.2f → %.2f", self.allocation, new_allocation)
        self.allocation = new_allocation
        # Fechar grid atual e reabrir com nova alocação
        if self._initialized:
            await self.close_all()
            await self._open_grid()
            self._initialized = True

    async def get_pnl(self) -> float:
        unrealized = await self._get_unrealized_pnl()
        return self.pnl_realized + unrealized

    # ─────────────────────────────────────────────
    # Setup inicial
    # ─────────────────────────────────────────────

    async def _setup(self) -> None:
        """Configura alavancagem e margem isolada."""
        symbol_ccxt = self.symbol
        log.info("Configurando %s: %dx leverage, %s margin", symbol_ccxt, self.leverage, self.margin_mode)
        try:
            await self.ex.set_leverage(self.leverage, symbol_ccxt)
            await self.ex.set_margin_mode(self.margin_mode, symbol_ccxt)
        except ccxt.ExchangeError as e:
            # Bybit/Binance retorna erro se alavancagem já está configurada — ignorar
            if "No need to change leverage" not in str(e) and "marginType" not in str(e) and "not modified" not in str(e).lower():
                raise

    # ─────────────────────────────────────────────
    # Grid: cálculo e abertura
    # ─────────────────────────────────────────────

    async def _open_grid(self) -> None:
        """Calcula ATR, define range e coloca todas as ordens do grid."""
        price = await self._get_price()
        atr = await self._calculate_atr()

        self.grid_bottom = price - atr * self.atr_multiplier
        self.grid_top = price + atr * self.atr_multiplier
        self.grid_step = (self.grid_top - self.grid_bottom) / (self.num_grids - 1)

        self.grid_levels = [
            round(self.grid_bottom + i * self.grid_step, self._price_precision())
            for i in range(self.num_grids)
        ]

        # Tamanho por ordem: capital total / número de ordens de compra
        order_size = self._order_size(price)

        log.info(
            "Grid aberto | preço=%.4f ATR=%.4f bottom=%.4f top=%.4f step=%.4f size=%.4f",
            price, atr, self.grid_bottom, self.grid_top, self.grid_step, order_size,
        )

        self.buy_orders.clear()
        self.sell_orders.clear()

        for i, level in enumerate(self.grid_levels):
            if level < price:
                # Compra limite abaixo do preço
                cid = self._cid(i, "buy")
                try:
                    order = await self.ex.create_limit_buy_order(
                        self.symbol, order_size, level,
                        params={"newClientOrderId": cid, "timeInForce": "GTC"},
                    )
                    self.buy_orders[i] = order["id"]
                except Exception as e:
                    log.error("Erro ao colocar buy@%.4f: %s", level, e)

            elif level > price:
                # Venda limite acima do preço
                cid = self._cid(i, "sell")
                try:
                    order = await self.ex.create_limit_sell_order(
                        self.symbol, order_size, level,
                        params={"newClientOrderId": cid, "timeInForce": "GTC"},
                    )
                    self.sell_orders[i] = order["id"]
                except Exception as e:
                    log.error("Erro ao colocar sell@%.4f: %s", level, e)

        # Persiste estado do grid (garante recovery após crash)
        self._save_state()

        if self.notify:
            buy_count = len(self.buy_orders)
            sell_count = len(self.sell_orders)
            prefix = "[PAPER] " if self.paper_trade else ""
            await self.notify(
                f"{prefix}◈ Grid Bot iniciado\n"
                f"SOL/USDT | Range: {self.grid_bottom:.2f}–{self.grid_top:.2f}\n"
                f"Step: {self.grid_step:.2f} | {buy_count} compras + {sell_count} vendas\n"
                f"ATR(24h): {atr:.4f} | Size/ordem: {order_size:.4f}"
            )

    # ─────────────────────────────────────────────
    # Processar ordens preenchidas
    # ─────────────────────────────────────────────

    async def _process_fills(self, current_price: float = 0.0) -> None:
        """Verifica ordens preenchidas e coloca ordem oposta no nível adjacente."""
        try:
            open_orders = await self.ex.fetch_open_orders(self.symbol)
        except Exception as e:
            log.error("Erro ao buscar ordens abertas: %s", e)
            return

        open_ids = {o["id"] for o in open_orders}
        if current_price <= 0:
            current_price = await self._get_price()
        order_size = self._order_size(current_price)
        precision = self._price_precision()

        # Checar buys preenchidos
        filled_buy_levels = [
            lvl for lvl, oid in list(self.buy_orders.items())
            if oid not in open_ids
        ]
        for lvl in filled_buy_levels:
            del self.buy_orders[lvl]
            sell_lvl = lvl + 1
            if sell_lvl < self.num_grids:
                sell_price = round(self.grid_levels[sell_lvl], precision)
                cid = self._cid(sell_lvl, "sell")
                try:
                    order = await self.ex.create_limit_sell_order(
                        self.symbol, order_size, sell_price,
                        params={"newClientOrderId": cid, "timeInForce": "GTC"},
                    )
                    self.sell_orders[sell_lvl] = order["id"]
                    profit = self.grid_step * order_size
                    self.pnl_realized += profit
                    log.info(
                        "Buy@%d preenchido → Sell@%d colocado | P&L cycle: +%.4f",
                        lvl, sell_lvl, profit,
                    )
                except Exception as e:
                    log.error("Erro ao colocar sell após fill: %s", e)

        # Checar sells preenchidos
        filled_sell_levels = [
            lvl for lvl, oid in list(self.sell_orders.items())
            if oid not in open_ids
        ]
        for lvl in filled_sell_levels:
            del self.sell_orders[lvl]
            buy_lvl = lvl - 1
            if buy_lvl >= 0:
                buy_price = round(self.grid_levels[buy_lvl], precision)
                cid = self._cid(buy_lvl, "buy")
                try:
                    order = await self.ex.create_limit_buy_order(
                        self.symbol, order_size, buy_price,
                        params={"newClientOrderId": cid, "timeInForce": "GTC"},
                    )
                    self.buy_orders[buy_lvl] = order["id"]
                    log.info("Sell@%d preenchido → Buy@%d recolocado", lvl, buy_lvl)
                except Exception as e:
                    log.error("Erro ao recolocar buy após fill: %s", e)

        # Persiste após qualquer mudança de estado (fills + novas ordens)
        if filled_buy_levels or filled_sell_levels:
            self._save_state()

    # ─────────────────────────────────────────────
    # ATR
    # ─────────────────────────────────────────────

    async def _calculate_atr(self) -> float:
        """Calcula ATR(24h) usando velas de 1h. Retorna valor em USD."""
        ohlcv = await self.ex.fetch_ohlcv(self.symbol, "1h", limit=self.atr_period + 5)
        if len(ohlcv) < self.atr_period + 1:
            raise ValueError(f"Dados insuficientes para ATR: {len(ohlcv)} velas")

        true_ranges = []
        for i in range(1, len(ohlcv)):
            high = ohlcv[i][2]
            low = ohlcv[i][3]
            prev_close = ohlcv[i - 1][4]
            tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
            true_ranges.append(tr)

        atr = sum(true_ranges[-self.atr_period:]) / self.atr_period
        return atr

    # ─────────────────────────────────────────────
    # Reinvestimento
    # ─────────────────────────────────────────────

    async def _maybe_reinvest(self) -> None:
        interval = self.cfg.get("reinvest_interval_hours", 12) * 3600
        if time.time() - self._last_reinvest < interval:
            return
        if self.pnl_realized <= 0:
            return

        # Aumentar alocação com os lucros realizados
        self.allocation += self.pnl_realized
        self.pnl_realized = 0.0
        self._last_reinvest = time.time()

        log.info("Reinvestindo lucros — nova alocação: %.2f", self.allocation)
        if self.notify:
            await self.notify(
                f"♻️ Grid Bot: reinvestimento automático\n"
                f"Nova alocação: ${self.allocation:.2f}"
            )

        # Reabrir grid com nova alocação
        await self.close_all()
        await self._open_grid()
        self._initialized = True

    # ─────────────────────────────────────────────
    # Helpers
    # ─────────────────────────────────────────────

    async def _get_price(self) -> float:
        ticker = await self.ex.fetch_ticker(self.symbol)
        return ticker["last"]

    async def _get_position(self) -> Optional[dict]:
        positions = await self.ex.fetch_positions([self.symbol])
        for p in positions:
            if p["symbol"] == self.symbol and abs(p.get("contracts", 0) or 0) > 0:
                return p
        return None

    async def _get_unrealized_pnl(self) -> float:
        position = await self._get_position()
        if position:
            return float(position.get("unrealizedPnl", 0) or 0)
        return 0.0

    def _order_size(self, price: float) -> float:
        """Calcula o tamanho de cada ordem em contratos."""
        # Capital por ordem: alocação * leverage / (num_grids / 2)
        # dividido pelo preço = contratos
        orders_count = self.num_grids // 2
        capital_per_order = (self.allocation * self.leverage) / orders_count
        size = capital_per_order / price
        # Arredondar para precisão mínima da exchange
        return round(size, self._size_precision())

    def _price_precision(self) -> int:
        # SOL/USDT tem precisão de 2 casas decimais no preço
        return 2

    def _size_precision(self) -> int:
        # SOL/USDT tem precisão de 1 casa decimal no tamanho
        return 1

    def _symbol_key(self) -> str:
        return self.symbol.replace("/", "").replace(":", "")

    def _cid(self, level_idx: int, side: str) -> str:
        return f"grid_{self._symbol_key()}_{level_idx}_{side}"

    # ─────────────────────────────────────────────
    # Persistência e recuperação de estado
    # ─────────────────────────────────────────────

    def _save_state(self) -> None:
        """Persiste estado do grid em JSON (chamado após qualquer mudança)."""
        save_state(self.id, {
            "grid_levels":  self.grid_levels,
            "grid_top":     self.grid_top,
            "grid_bottom":  self.grid_bottom,
            "grid_step":    self.grid_step,
            "buy_orders":   {str(k): v for k, v in self.buy_orders.items()},
            "sell_orders":  {str(k): v for k, v in self.sell_orders.items()},
            "pnl_realized": self.pnl_realized,
            "allocation":   self.allocation,
        })

    async def _try_resume_from_state(self) -> bool:
        """
        Tenta retomar estado salvo após restart/crash.
        Retorna True se retomou com sucesso; False se deve abrir grid novo.

        Paper mode : aceita estado salvo diretamente (sem reconciliação).
        Live mode  : reconcilia IDs de ordens com a exchange.
                     Se nenhuma ordem válida encontrada → abre grid novo.
        """
        state = load_state(self.id)
        if not state:
            return False

        # Restaura geometria do grid
        self.grid_levels  = state.get("grid_levels",  [])
        self.grid_top     = state.get("grid_top",     0.0)
        self.grid_bottom  = state.get("grid_bottom",  0.0)
        self.grid_step    = state.get("grid_step",    0.0)
        self.pnl_realized = state.get("pnl_realized", 0.0)
        saved_alloc       = state.get("allocation",   self.allocation)
        if saved_alloc > 0:
            # Cap: nunca restaurar alocação maior que a inicial (pode ser state antigo)
            if saved_alloc > self.initial_allocation * 1.5:
                log.warning(
                    "Grid Bot: alocação salva ($%.2f) muito acima da inicial ($%.2f) "
                    "— possível state antigo. Usando alocação inicial.",
                    saved_alloc, self.initial_allocation,
                )
                self.allocation = self.initial_allocation
            else:
                self.allocation = saved_alloc

        saved_buy  = {int(k): v for k, v in state.get("buy_orders",  {}).items()}
        saved_sell = {int(k): v for k, v in state.get("sell_orders", {}).items()}

        if self.paper_trade:
            self.buy_orders  = saved_buy
            self.sell_orders = saved_sell
            log.info(
                "Grid Bot: estado PAPER restaurado — %d buy + %d sell ordens | P&L=%.2f",
                len(self.buy_orders), len(self.sell_orders), self.pnl_realized,
            )
            return True

        # Live: reconcilia IDs com ordens reais na exchange
        try:
            open_orders = await self.ex.fetch_open_orders(self.symbol)
            open_ids = {o["id"] for o in open_orders}
        except Exception as exc:
            log.warning(
                "Grid Bot: reconciliação falhou (%s) — abrindo grid novo", exc
            )
            return False

        self.buy_orders  = {lvl: oid for lvl, oid in saved_buy.items()  if oid in open_ids}
        self.sell_orders = {lvl: oid for lvl, oid in saved_sell.items() if oid in open_ids}

        active = len(self.buy_orders) + len(self.sell_orders)
        total  = len(saved_buy) + len(saved_sell)
        log.info(
            "Grid Bot: reconciliação — %d/%d ordens ativas na Bybit | P&L=%.2f",
            active, total, self.pnl_realized,
        )

        if active == 0:
            log.info("Grid Bot: nenhuma ordem válida — abrindo grid novo")
            return False

        return True

    def _status(self, active: bool = True, pnl_realized: float = 0.0,
                pnl_unrealized: float = 0.0, open_orders: int = 0,
                extra: dict = None) -> StrategyStatus:
        return StrategyStatus(
            id=self.id,
            active=active and self._active,
            pnl_realized=pnl_realized,
            pnl_unrealized=pnl_unrealized,
            allocation=self.allocation,
            open_orders=open_orders,
            paper_trade=self.paper_trade,
            extra=extra or {},
        )

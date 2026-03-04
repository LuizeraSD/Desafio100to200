"""
PaperExchange — wrapper de paper trading para qualquer exchange ccxt.

Intercepta chamadas de escrita (ordens, posições) e simula localmente.
Passa as chamadas de leitura (ticker, ohlcv) diretamente para a exchange real,
garantindo que preços e dados de mercado sejam sempre reais.

Compatível com Grid Bot e Momentum Scalper (ambos usam ccxt).

Lógica de fill:
  - Buy limit: preenche quando last_price <= order_price
  - Sell limit: preenche quando last_price >= order_price
  - Market order: preenche imediatamente ao preço atual (ask para buy, bid para sell)
"""
import logging
import time
from typing import Optional

log = logging.getLogger("paper_exchange")


class PaperExchange:
    """
    Drop-in replacement para um ccxt exchange em modo paper trading.
    Instanciar com a exchange real: PaperExchange(ccxt.binance(...))
    """

    def __init__(self, real_exchange, label: str = ""):
        self._ex = real_exchange
        self._label = label or real_exchange.__class__.__name__

        # Ordens virtuais em aberto: id -> order dict
        self._orders: dict[str, dict] = {}
        self._next_id: int = 1

        # Posição virtual por símbolo: symbol -> position dict
        self._positions: dict[str, dict] = {}

        # Leverage virtual por símbolo
        self._leverage: dict[str, int] = {}

        # Histórico de fills para log/debug
        self._fill_log: list[dict] = []

    # ─────────────────────────────────────────────
    # Read-through (dados reais da exchange)
    # ─────────────────────────────────────────────

    async def fetch_ticker(self, symbol: str) -> dict:
        return await self._ex.fetch_ticker(symbol)

    async def fetch_tickers(self, symbols: list = None) -> dict:
        return await self._ex.fetch_tickers(symbols)

    async def fetch_ohlcv(self, symbol: str, timeframe: str = "1m",
                          since=None, limit: int = None, params: dict = None) -> list:
        kwargs = {}
        if since is not None:
            kwargs["since"] = since
        if limit is not None:
            kwargs["limit"] = limit
        return await self._ex.fetch_ohlcv(symbol, timeframe, **kwargs)

    async def load_markets(self, reload: bool = False) -> dict:
        return await self._ex.load_markets(reload)

    # ─────────────────────────────────────────────
    # Simulação de configuração
    # ─────────────────────────────────────────────

    async def set_leverage(self, leverage: int, symbol: str, params: dict = None) -> dict:
        self._leverage[symbol] = leverage
        log.info("[PAPER:%s] set_leverage %dx em %s", self._label, leverage, symbol)
        return {"leverage": leverage, "symbol": symbol}

    async def set_margin_mode(self, mode: str, symbol: str, params: dict = None) -> dict:
        log.info("[PAPER:%s] set_margin_mode '%s' em %s", self._label, mode, symbol)
        return {"marginMode": mode, "symbol": symbol}

    # ─────────────────────────────────────────────
    # Simulação de ordens
    # ─────────────────────────────────────────────

    async def create_limit_buy_order(self, symbol: str, amount: float, price: float,
                                     params: dict = None) -> dict:
        return self._add_order(symbol, "buy", "limit", amount, price, params)

    async def create_limit_sell_order(self, symbol: str, amount: float, price: float,
                                      params: dict = None) -> dict:
        return self._add_order(symbol, "sell", "limit", amount, price, params)

    async def create_market_order(self, symbol: str, side: str, amount: float,
                                  params: dict = None) -> dict:
        """Market order: fill imediato ao preço atual."""
        ticker = await self._ex.fetch_ticker(symbol)
        # Binance Futures pode retornar ask/bid = None via REST.
        # Usa last como fallback para evitar TypeError no log e no _update_position.
        if side == "buy":
            fill_price = ticker.get("ask") or ticker.get("last")
        else:
            fill_price = ticker.get("bid") or ticker.get("last")
        is_reduce = (params or {}).get("reduceOnly", False)
        self._update_position(symbol, side, amount, fill_price, is_reduce)

        order_id = self._new_id()
        log.info(
            "[PAPER:%s] MARKET %s %s | size=%.4f @ %.4f | reduceOnly=%s",
            self._label, side.upper(), symbol, amount, fill_price, is_reduce,
        )
        return {
            "id": order_id,
            "symbol": symbol,
            "type": "market",
            "side": side,
            "amount": amount,
            "price": fill_price,
            "status": "closed",
        }

    async def cancel_order(self, order_id: str, symbol: str = None,
                           params: dict = None) -> dict:
        removed = self._orders.pop(order_id, None)
        if removed:
            log.debug("[PAPER:%s] Ordem cancelada: %s", self._label, order_id)
        return {"id": order_id, "status": "canceled"}

    async def cancel_all_orders(self, symbol: str = None) -> list:
        to_cancel = [
            oid for oid, o in self._orders.items()
            if symbol is None or o["symbol"] == symbol
        ]
        for oid in to_cancel:
            self._orders.pop(oid)
        log.info("[PAPER:%s] %d ordens canceladas em %s", self._label, len(to_cancel), symbol)
        return [{"id": oid, "status": "canceled"} for oid in to_cancel]

    # ─────────────────────────────────────────────
    # Fetch de ordens e posições (com simulação de fill)
    # ─────────────────────────────────────────────

    async def fetch_open_orders(self, symbol: str = None, params: dict = None) -> list:
        """
        Antes de retornar as ordens abertas, verifica se alguma deve ser preenchida
        com base no preço atual. Ordens preenchidas são removidas e a posição
        é atualizada. Isso simula o fill passivo de ordens limite.
        """
        ticker = await self._ex.fetch_ticker(symbol or list(self._orders.values())[0]["symbol"]
                                             if self._orders else symbol)
        last = ticker["last"]

        filled = []
        for oid, order in list(self._orders.items()):
            if symbol and order["symbol"] != symbol:
                continue
            if order["type"] != "limit":
                continue

            should_fill = (
                (order["side"] == "buy" and last <= order["price"]) or
                (order["side"] == "sell" and last >= order["price"])
            )
            if should_fill:
                filled.append(oid)

        for oid in filled:
            order = self._orders.pop(oid)
            self._update_position(order["symbol"], order["side"], order["amount"], order["price"])
            self._fill_log.append({
                "ts": time.time(),
                "symbol": order["symbol"],
                "side": order["side"],
                "amount": order["amount"],
                "price": order["price"],
            })
            log.info(
                "[PAPER:%s] FILL %s %s | size=%.4f @ %.4f (last=%.4f)",
                self._label, order["side"].upper(), order["symbol"],
                order["amount"], order["price"], last,
            )

        open_for_symbol = [
            o for o in self._orders.values()
            if symbol is None or o["symbol"] == symbol
        ]
        return open_for_symbol

    async def fetch_positions(self, symbols: list = None) -> list:
        result = []
        for symbol, pos in self._positions.items():
            if symbols and symbol not in symbols:
                continue
            if pos["contracts"] == 0:
                continue

            # P&L não realizado
            ticker = await self._ex.fetch_ticker(symbol)
            current = ticker["last"]
            lev = self._leverage.get(symbol, 1)

            if pos["side"] == "long":
                upnl = (current - pos["avg_price"]) * pos["contracts"] * lev
            else:
                upnl = (pos["avg_price"] - current) * pos["contracts"] * lev

            result.append({
                "symbol": symbol,
                "side": pos["side"],
                "contracts": pos["contracts"],
                "entryPrice": pos["avg_price"],
                "unrealizedPnl": upnl,
                "leverage": lev,
            })
        return result

    # ─────────────────────────────────────────────
    # Estado / diagnóstico
    # ─────────────────────────────────────────────

    def get_paper_summary(self, symbol: str = None) -> dict:
        """Retorna resumo do estado virtual: posições, ordens, fills."""
        positions = {s: p for s, p in self._positions.items()
                     if (symbol is None or s == symbol) and p["contracts"] > 0}
        open_orders = {oid: o for oid, o in self._orders.items()
                       if symbol is None or o["symbol"] == symbol}
        recent_fills = [f for f in self._fill_log[-20:]
                        if symbol is None or f["symbol"] == symbol]
        return {
            "positions": positions,
            "open_orders_count": len(open_orders),
            "fills_total": len(self._fill_log),
            "recent_fills": recent_fills,
        }

    async def close(self) -> None:
        await self._ex.close()

    # ─────────────────────────────────────────────
    # Helpers internos
    # ─────────────────────────────────────────────

    def _new_id(self) -> str:
        oid = f"paper_{self._next_id}"
        self._next_id += 1
        return oid

    def _add_order(self, symbol: str, side: str, order_type: str,
                   amount: float, price: float, params: dict = None) -> dict:
        oid = self._new_id()
        cid = (params or {}).get("newClientOrderId", oid)
        order = {
            "id": oid,
            "clientOrderId": cid,
            "symbol": symbol,
            "type": order_type,
            "side": side,
            "amount": amount,
            "price": price,
            "status": "open",
        }
        self._orders[oid] = order
        log.debug(
            "[PAPER:%s] LIMIT %s %s | size=%.4f @ %.4f | cid=%s",
            self._label, side.upper(), symbol, amount, price, cid,
        )
        return order

    def _update_position(self, symbol: str, side: str, amount: float,
                         price: float, reduce_only: bool = False) -> None:
        pos = self._positions.setdefault(symbol, {
            "side": None, "contracts": 0.0, "avg_price": 0.0,
        })

        is_long_add = side == "buy" and (pos["side"] == "long" or pos["contracts"] == 0)
        is_short_add = side == "sell" and (pos["side"] == "short" or pos["contracts"] == 0)

        if pos["contracts"] == 0 and not reduce_only:
            # Abrindo nova posição
            pos["side"] = "long" if side == "buy" else "short"
            pos["contracts"] = amount
            pos["avg_price"] = price
        elif is_long_add or is_short_add:
            # Aumentando posição existente (média ponderada)
            total_cost = pos["avg_price"] * pos["contracts"] + price * amount
            pos["contracts"] += amount
            pos["avg_price"] = total_cost / pos["contracts"]
        else:
            # Reduzindo ou fechando posição
            pos["contracts"] = max(0.0, pos["contracts"] - amount)
            if pos["contracts"] == 0:
                pos["side"] = None
                pos["avg_price"] = 0.0

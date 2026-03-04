"""
Momentum Detector — monitora top altcoins no Bybit e detecta breakouts de volume.

Abordagem: polling REST (ccxt) a cada tick do orchestrator.
  1. Lista top N símbolos por quoteVolume 24h (atualiza a cada 1h)
  2. Para cada símbolo: busca OHLCV 1m (últimas 50 velas)
  3. Calcula VWAP(30 períodos) e volume_ratio = vol_atual / MA(20)
  4. Emite sinal quando vol_ratio >= multiplier E close > VWAP

Compatível com ccxt.bybit e PaperExchange (pass-through de fetch_ohlcv/fetch_tickers).
"""
import asyncio
import logging
import time
from dataclasses import dataclass

log = logging.getLogger("momentum.detector")

try:
    import pandas as pd
    _PANDAS_AVAILABLE = True
except ImportError:
    _PANDAS_AVAILABLE = False
    log.warning("pandas não instalado — MomentumDetector desabilitado")


@dataclass
class Signal:
    symbol: str
    side: str           # sempre "buy" (long breakout)
    current_price: float
    vwap: float
    volume_ratio: float  # vol_atual / MA(20)


class MomentumDetector:
    """
    Detecta breakouts de volume em altcoins Bybit.
    Retorna lista de Signal para o MomentumScalper abrir posições.
    """

    def __init__(self, config: dict, exchange):
        self.cfg = config
        self.ex = exchange
        self.volume_multiplier = float(config.get("volume_multiplier", 3.0))
        self.top_n = int(config.get("top_n_symbols", 30))
        self._symbols_ttl = 3600.0            # refresh da lista a cada 1h
        self._top_symbols: list[str] = []
        self._last_symbols_ts: float = 0.0
        # Intervalo mínimo entre scans completos (evita 30 fetch_ohlcv a cada tick)
        self._scan_interval = float(config.get("scan_interval_seconds", 300))  # 5 min
        self._last_scan_ts: float = 0.0
        self._cached_signals: list[Signal] = []

    async def get_signals(self) -> list[Signal]:
        """
        Retorna lista de sinais de breakout prontos para execução.
        Cada sinal contém: symbol, side, current_price, vwap, volume_ratio.
        Resultado é cacheado por scan_interval_seconds (padrão: 5 min).
        """
        if not _PANDAS_AVAILABLE:
            return []

        now = time.time()
        if now - self._last_scan_ts < self._scan_interval:
            return self._cached_signals

        await self._refresh_top_symbols()
        if not self._top_symbols:
            return []

        # Verifica todos os símbolos em paralelo (com limite de concorrência)
        sem = asyncio.Semaphore(5)  # max 5 requisições simultâneas (reduz pico de CPU)

        async def check_with_sem(sym: str) -> Signal | None:
            async with sem:
                return await self._check_symbol(sym)

        results = await asyncio.gather(
            *[check_with_sem(s) for s in self._top_symbols],
            return_exceptions=True,
        )

        signals = [r for r in results if isinstance(r, Signal)]
        self._cached_signals = signals
        self._last_scan_ts = now
        if signals:
            log.info(
                "Momentum: %d sinais detectados de %d símbolos",
                len(signals), len(self._top_symbols),
            )
        else:
            log.debug("Momentum: 0 sinais de %d símbolos", len(self._top_symbols))
        return signals

    # ─────────────────────────────────────────────
    # Manutenção da lista de símbolos
    # ─────────────────────────────────────────────

    async def _refresh_top_symbols(self) -> None:
        """Atualiza top N símbolos por quoteVolume se TTL expirou."""
        if time.time() - self._last_symbols_ts < self._symbols_ttl:
            return

        try:
            tickers = await self.ex.fetch_tickers()
        except Exception as exc:
            log.error("Erro ao buscar tickers Bybit: %s", exc)
            return

        # Filtra apenas contratos USDT perpétuos (formato ccxt: "BTC/USDT:USDT")
        perps = {
            sym: t
            for sym, t in tickers.items()
            if ":USDT" in sym and float(t.get("quoteVolume") or 0) > 0
        }
        sorted_syms = sorted(
            perps.items(),
            key=lambda kv: float(kv[1].get("quoteVolume") or 0),
            reverse=True,
        )
        self._top_symbols = [sym for sym, _ in sorted_syms[: self.top_n]]
        self._last_symbols_ts = time.time()
        log.info(
            "Momentum: lista atualizada — top %d símbolos por volume",
            len(self._top_symbols),
        )

    # ─────────────────────────────────────────────
    # Análise por símbolo
    # ─────────────────────────────────────────────

    async def _check_symbol(self, symbol: str) -> Signal | None:
        """
        Busca OHLCV 1m e verifica condição de breakout.
        Retorna Signal se sinal ativo, None caso contrário.
        """
        try:
            ohlcv = await self.ex.fetch_ohlcv(symbol, "1m", limit=50)
        except Exception as exc:
            log.debug("fetch_ohlcv(%s): %s", symbol, exc)
            return None

        if not ohlcv or len(ohlcv) < 25:
            return None

        try:
            df = pd.DataFrame(
                ohlcv, columns=["ts", "open", "high", "low", "close", "volume"]
            ).astype(float)

            # VWAP(30): Preço Típico * Volume / Σ Volume
            df30 = df.tail(30)
            typical = (df30["high"] + df30["low"] + df30["close"]) / 3
            total_vol = df30["volume"].sum()
            if total_vol <= 0:
                return None
            vwap = (typical * df30["volume"]).sum() / total_vol

            # Volume ratio: vela atual vs. MA(20) das últimas 20 velas
            vol_ma20 = df["volume"].iloc[-21:-1].mean()
            if vol_ma20 <= 0:
                return None
            vol_current = float(df["volume"].iloc[-1])
            vol_ratio = vol_current / vol_ma20

            current_price = float(df["close"].iloc[-1])

            # Condição de sinal: volume spike + fechamento acima do VWAP
            if vol_ratio >= self.volume_multiplier and current_price > vwap:
                log.info(
                    "Sinal: %s | price=%.4f vwap=%.4f vol_ratio=%.1fx",
                    symbol, current_price, vwap, vol_ratio,
                )
                return Signal(
                    symbol=symbol,
                    side="buy",
                    current_price=current_price,
                    vwap=vwap,
                    volume_ratio=vol_ratio,
                )
        except Exception as exc:
            log.debug("Erro ao analisar %s: %s", symbol, exc)

        return None

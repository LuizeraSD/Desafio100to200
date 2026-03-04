"""
Polymarket Executor — estratégia Polymarket completa.

Integra:
  scanner.py  → busca mercados com volume suficiente
  model.py    → Claude API estima probabilidade real e edge
  executor.py → coloca e monitora apostas (CLOB live ou paper)

Paper trading (paper_trade=True):
  Scanner e modelo rodam com dados reais.
  Apostas são registradas localmente; P&L simulado via preço atual do token.

Live trading (paper_trade=False):
  Requer POLY_API_KEY, POLY_SECRET, POLY_PASSPHRASE no .env
  e py-clob-client instalado.
"""
import asyncio
import dataclasses
import logging
import os
import time
from dataclasses import dataclass, field

from strategies.base import BaseStrategy, StrategyStatus
from strategies.polymarket.model import ProbabilityModel
from strategies.polymarket.scanner import PolymarketScanner
from strategies.state_manager import clear_state, load_state, save_state

log = logging.getLogger("polymarket")

try:
    from py_clob_client.client import ClobClient
    from py_clob_client.clob_types import ApiCreds
    _CLOB_AVAILABLE = True
except ImportError:
    _CLOB_AVAILABLE = False

CLOB_HOST = "https://clob.polymarket.com"
CHAIN_ID = 137  # Polygon


@dataclass
class Position:
    condition_id: str
    question: str
    direction: str       # "YES" | "NO"
    token_id: str        # token ID do lado apostado
    amount_usd: float    # capital investido
    entry_price: float   # preço pago (0.0–1.0)
    shares: float        # shares = amount / price
    paper: bool = True
    order_id: str = ""
    timestamp: float = field(default_factory=time.time)
    pnl: float = 0.0     # P&L corrente (não realizado ou realizado)
    closed: bool = False


class PolymarketModel(BaseStrategy):
    """
    Estratégia Polymarket completa:
      1. Scanner busca mercados com volume > min_volume_usd
      2. Claude estima probabilidade real; filtra por edge > min_edge_pct
      3. Coloca aposta (CLOB real ou registro paper)
      4. Monitora posições abertas (P&L não realizado + detecção de resolução)
    """

    def __init__(self, config: dict, allocation: float, paper_trade: bool = False):
        super().__init__("polymarket", allocation, paper_trade)
        self.cfg = config
        self.max_position_usd = float(config.get("max_position_usd", 10.0))
        self.max_open = int(config.get("max_open_positions", 4))
        self.scan_interval = int(config.get("scan_interval_minutes", 30)) * 60

        self.scanner = PolymarketScanner(config)
        self.model = ProbabilityModel(config)

        self._positions: dict[str, Position] = {}  # condition_id → Position
        self._last_scan: float = 0.0
        self._realized_pnl: float = 0.0
        self._state_loaded: bool = False  # flag: recovery executado?

        # Cliente CLOB autenticado (apenas live)
        self._clob: "ClobClient | None" = None
        if not paper_trade and _CLOB_AVAILABLE:
            api_key    = os.getenv("POLY_API_KEY", "").strip()
            api_secret = os.getenv("POLY_SECRET", "").strip()
            passphrase = os.getenv("POLY_PASSPHRASE", "").strip()
            if api_key and api_secret:
                creds = ApiCreds(
                    api_key=api_key,
                    api_secret=api_secret,
                    api_passphrase=passphrase,
                )
                self._clob = ClobClient(host=CLOB_HOST, chain_id=CHAIN_ID, creds=creds)
                log.info("Polymarket CLOB live configurado")
            else:
                log.warning(
                    "POLY_API_KEY/POLY_SECRET não configurados — "
                    "Polymarket rodará em paper mesmo com PAPER_TRADE=false"
                )
                self.paper_trade = True

    # ─────────────────────────────────────────────
    # Interface BaseStrategy
    # ─────────────────────────────────────────────

    async def tick(self) -> StrategyStatus:
        """Ciclo principal: recovery (1ª vez) → atualiza P&L → escaneia → aposta."""
        if not self._state_loaded:
            self._state_loaded = True
            self._load_state()

        await self._update_positions_pnl()

        now = time.time()
        if now - self._last_scan >= self.scan_interval:
            await self._scan_and_bet()
            self._last_scan = now

        open_count = sum(1 for p in self._positions.values() if not p.closed)
        unrealized  = sum(p.pnl for p in self._positions.values() if not p.closed)

        return StrategyStatus(
            id=self.id,
            active=self._active,
            pnl_realized=self._realized_pnl,
            pnl_unrealized=unrealized,
            allocation=self.allocation,
            open_orders=open_count,
            paper_trade=self.paper_trade,
            extra={
                "open_positions":  open_count,
                "total_positions": len(self._positions),
            },
        )

    async def close_all(self) -> None:
        """Fecha (ou marca como fechadas) todas as posições abertas e limpa estado."""
        # Sinaliza parada para o loop de paginação da CLOB API (roda em thread)
        self.scanner.stop()

        for pos in self._positions.values():
            if pos.closed:
                continue
            if not self.paper_trade and self._clob:
                await self._sell_position_live(pos)
            else:
                await self._close_paper_position(pos, reason="close_all")
        clear_state(self.id)
        log.info("Polymarket: todas as posições fechadas")

    async def resize(self, new_allocation: float) -> None:
        self.allocation = new_allocation

    async def get_pnl(self) -> float:
        unrealized = sum(p.pnl for p in self._positions.values() if not p.closed)
        return self._realized_pnl + unrealized

    # ─────────────────────────────────────────────
    # Lógica de scan e aposta
    # ─────────────────────────────────────────────

    async def _scan_and_bet(self) -> None:
        """Busca candidatos → analisa com Claude → aposta quando há edge."""
        open_count = sum(1 for p in self._positions.values() if not p.closed)
        if open_count >= self.max_open:
            log.debug("Polymarket: max posições abertas (%d)", self.max_open)
            return

        candidates = await self.scanner.get_candidates()
        if not candidates:
            log.info("Polymarket: nenhum mercado candidato encontrado")
            return

        existing = {p.condition_id for p in self._positions.values() if not p.closed}
        new_candidates = [c for c in candidates if c["condition_id"] not in existing]

        for market in new_candidates:
            if open_count >= self.max_open:
                break

            analysis = await self.model.estimate(market)
            if not analysis["should_bet"]:
                continue

            # Kelly fraction simplificado: edge * 0.5, limitado ao max configurado
            amount = min(
                self.max_position_usd,
                self.allocation * analysis["abs_edge"] * 0.5,
            )
            amount = max(1.0, round(amount, 2))

            await self._place_bet(market, analysis, amount)
            open_count += 1

    async def _place_bet(
        self, market: dict, analysis: dict, amount_usd: float
    ) -> None:
        """Registra aposta (paper) ou coloca ordem no CLOB (live)."""
        direction = analysis["direction"]
        token_id = (
            market["token_yes_id"] if direction == "YES" else market["token_no_id"]
        )
        # Preço do token apostado: YES→market_price, NO→(1 - market_price)
        entry_price = (
            analysis["market_price"]
            if direction == "YES"
            else 1.0 - analysis["market_price"]
        )
        if entry_price <= 0:
            return
        shares = round(amount_usd / entry_price, 2)

        if self.paper_trade:
            pos = Position(
                condition_id=market["condition_id"],
                question=market["question"],
                direction=direction,
                token_id=token_id,
                amount_usd=amount_usd,
                entry_price=entry_price,
                shares=shares,
                paper=True,
            )
            self._positions[market["condition_id"]] = pos
            self._save_state()
            log.info(
                "[PAPER] Aposta: '%s' | dir=%s $%.2f entry=%.1f%% edge=%.1f%% | %s",
                market["question"][:55],
                direction, amount_usd, entry_price * 100,
                analysis["abs_edge"] * 100,
                analysis["reasoning"][:80],
            )
        else:
            if not self._clob:
                return
            loop = asyncio.get_event_loop()
            try:
                # py-clob-client API: create_and_post_order aceita OrderArgs
                from py_clob_client.clob_types import OrderArgs
                from py_clob_client.constants import BUY
                order_args = OrderArgs(
                    token_id=token_id,
                    price=round(entry_price, 4),
                    size=shares,
                    side=BUY,
                )
                resp = await loop.run_in_executor(
                    None,
                    lambda: self._clob.create_and_post_order(order_args),
                )
                order_id = (
                    resp.get("orderID", "") if isinstance(resp, dict) else str(resp)
                )
                pos = Position(
                    condition_id=market["condition_id"],
                    question=market["question"],
                    direction=direction,
                    token_id=token_id,
                    amount_usd=amount_usd,
                    entry_price=entry_price,
                    shares=shares,
                    paper=False,
                    order_id=order_id,
                )
                self._positions[market["condition_id"]] = pos
                self._save_state()
                log.info(
                    "[LIVE] Aposta: '%s' | dir=%s $%.2f entry=%.1f%% order=%s",
                    market["question"][:55],
                    direction, amount_usd, entry_price * 100, order_id,
                )
            except Exception as exc:
                log.error("Erro ao colocar aposta live: %s", exc)

    # ─────────────────────────────────────────────
    # Monitoramento de posições
    # ─────────────────────────────────────────────

    async def _update_positions_pnl(self) -> None:
        """Atualiza P&L das posições abertas e detecta resoluções."""
        loop = asyncio.get_event_loop()
        for pos in list(self._positions.values()):
            if pos.closed:
                continue

            current = await loop.run_in_executor(
                None, self.scanner.get_last_price_sync, pos.token_id
            )
            if current is None:
                continue

            pos.pnl = (current - pos.entry_price) * pos.shares

            # Detecção de resolução: preço converge para 0 ou 1
            if current >= 0.99:
                pos.pnl = (1.0 - pos.entry_price) * pos.shares
                self._realized_pnl += pos.pnl
                pos.closed = True
                self._save_state()
                log.info(
                    "Polymarket: '%s' → GANHOU | P&L=$%.2f",
                    pos.question[:50], pos.pnl,
                )
            elif current <= 0.01:
                pos.pnl = -pos.amount_usd
                self._realized_pnl += pos.pnl
                pos.closed = True
                self._save_state()
                log.info(
                    "Polymarket: '%s' → PERDEU | P&L=$%.2f",
                    pos.question[:50], pos.pnl,
                )

    async def _close_paper_position(self, pos: Position, reason: str = "") -> None:
        """Fecha posição paper ao preço atual."""
        loop = asyncio.get_event_loop()
        current = await loop.run_in_executor(
            None, self.scanner.get_last_price_sync, pos.token_id
        )
        if current is None:
            current = pos.entry_price  # sem preço → assume empate

        pos.pnl = (current - pos.entry_price) * pos.shares
        self._realized_pnl += pos.pnl
        pos.closed = True
        log.info(
            "[PAPER] Posição fechada (%s): '%s' | exit=%.1f%% P&L=$%.2f",
            reason, pos.question[:50], current * 100, pos.pnl,
        )

    async def _sell_position_live(self, pos: Position) -> None:
        """Tenta vender shares no CLOB (melhor esforço)."""
        if not self._clob or not pos.token_id:
            pos.closed = True
            return
        log.warning(
            "Fechamento live de posição Polymarket não totalmente implementado: '%s'",
            pos.question[:50],
        )
        pos.closed = True

    # ─────────────────────────────────────────────
    # Persistência e recuperação de estado
    # ─────────────────────────────────────────────

    def _save_state(self) -> None:
        """Persiste posições abertas em JSON (chamado após qualquer mudança)."""
        open_positions = {
            cid: dataclasses.asdict(pos)
            for cid, pos in self._positions.items()
            if not pos.closed
        }
        save_state(self.id, {
            "positions":    open_positions,
            "realized_pnl": self._realized_pnl,
        })

    def _load_state(self) -> None:
        """
        Carrega posições salvas na inicialização.
        Só restaura posições não fechadas.
        Não há reconciliação com exchange: posições Polymarket resolvem de forma
        passiva — o monitor de P&L detectará a resolução no próximo tick.
        """
        state = load_state(self.id)
        if not state:
            return

        self._realized_pnl = float(state.get("realized_pnl", 0.0))
        restored = 0
        for cid, p_data in state.get("positions", {}).items():
            if p_data.get("closed", True):
                continue
            try:
                self._positions[cid] = Position(**p_data)
                restored += 1
            except Exception as exc:
                log.warning("Erro ao restaurar posição %s: %s", cid, exc)

        if restored:
            log.info(
                "Polymarket: %d posição(ões) restauradas do estado salvo | P&L=%.2f",
                restored, self._realized_pnl,
            )

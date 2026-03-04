"""
Portfolio — rastreia estado consolidado do portfólio e P&L de cada perna.
Persiste state/portfolio.json a cada tick para o dashboard ler.
"""
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict

from strategies.base import StrategyStatus

_EQUITY_MAX_POINTS = 2880  # 48h a 60s/tick


@dataclass
class Portfolio:
    initial: float = 100.0
    _snapshots: Dict[str, StrategyStatus] = field(default_factory=dict)
    _equity_history: list = field(default_factory=list)

    def update(self, strategy_id: str, status: StrategyStatus) -> None:
        self._snapshots[strategy_id] = status

    @property
    def total_pnl(self) -> float:
        return sum(s.total_pnl for s in self._snapshots.values())

    @property
    def total_value(self) -> float:
        return self.initial + self.total_pnl

    @property
    def drawdown(self) -> float:
        """Drawdown percentual em relação ao capital inicial."""
        if self.total_value >= self.initial:
            return 0.0
        return (self.initial - self.total_value) / self.initial

    def summary(self) -> str:
        lines = [f"Portfólio: ${self.total_value:.2f} (P&L: {self.total_pnl:+.2f})"]
        for sid, s in self._snapshots.items():
            lines.append(
                f"  {sid}: P&L={s.total_pnl:+.2f} alloc=${s.allocation:.2f} active={s.active}"
            )
        return "\n".join(lines)

    def rebalance(self) -> dict:
        """
        Rebalanceia alocações proporcionalmente ao valor total atual.

        Mantém as proporções relativas entre estratégias (peso = alloc_original / total_alloc).
        Retorna dict {strategy_id: nova_alocacao} para o orchestrator aplicar via resize().
        Não altera estratégias inativas (alloc <= 0).
        """
        total = self.total_value
        if total <= 0 or not self._snapshots:
            return {}

        total_alloc = sum(s.allocation for s in self._snapshots.values() if s.allocation > 0)
        if total_alloc <= 0:
            return {}

        new_allocs: dict = {}
        for sid, s in self._snapshots.items():
            if s.allocation <= 0:
                continue
            proportion = s.allocation / total_alloc
            new_alloc = round(total * proportion, 2)
            new_allocs[sid] = new_alloc
            s.allocation = new_alloc  # atualiza snapshot local

        return new_allocs

    # ─────────────────────────────────────────────
    # Persistência para o dashboard
    # ─────────────────────────────────────────────

    def record_snapshot(self) -> None:
        """Appenda ponto à curva de equity (chamado ao fim de cada tick)."""
        self._equity_history.append({
            "timestamp": time.time(),
            "value": round(self.total_value, 4),
        })
        # Limita tamanho para não crescer indefinidamente
        if len(self._equity_history) > _EQUITY_MAX_POINTS:
            self._equity_history = self._equity_history[-_EQUITY_MAX_POINTS:]

    def to_state_dict(self, paper_trade: bool = False) -> dict:
        """Serializa estado completo para salvar em state/portfolio.json."""
        now = datetime.now(timezone.utc)
        strategies_data = {}
        for sid, s in self._snapshots.items():
            strategies_data[sid] = {
                "active":          s.active,
                "allocation":      round(s.allocation, 2),
                "pnl_realized":    round(s.pnl_realized, 4),
                "pnl_unrealized":  round(s.pnl_unrealized, 4),
                "total_pnl":       round(s.total_pnl, 4),
                "open_orders":     s.open_orders,
                "paper_trade":     s.paper_trade,
            }

        return {
            "timestamp":       time.time(),
            "last_update_str": now.strftime("%Y-%m-%d %H:%M:%S UTC"),
            "total_value":     round(self.total_value, 4),
            "total_pnl":       round(self.total_pnl, 4),
            "drawdown":        round(self.drawdown, 6),
            "paper_trade":     paper_trade,
            "strategies":      strategies_data,
            "equity_history":  self._equity_history,
        }

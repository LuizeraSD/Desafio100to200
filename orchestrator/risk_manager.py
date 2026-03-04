"""
Risk Manager — circuit breakers e position sizing.
"""
import logging

from strategies.base import BaseStrategy, StrategyStatus

log = logging.getLogger("risk_manager")


class RiskManager:
    def __init__(self, max_drawdown: float = 0.40, daily_target: float = 0.15):
        self.max_drawdown = max_drawdown        # -40% por perna → desliga
        self.daily_target = daily_target        # +15%/dia meta
        self.global_stop = 0.50                 # -50% total → para tudo

    def should_stop(self, strategy: BaseStrategy, status: StrategyStatus) -> bool:
        """Retorna True se a estratégia deve ser desligada (circuit breaker)."""
        if not status.active:
            return False
        if status.allocation <= 0:
            return False
        drawdown = -status.total_pnl / status.allocation
        if drawdown >= self.max_drawdown:
            log.warning(
                "Circuit breaker: %s perdeu %.1f%% (limite: %.1f%%)",
                strategy.id, drawdown * 100, self.max_drawdown * 100,
            )
            return True
        return False

    def redistribute(self, portfolio, stopped_strategy: BaseStrategy) -> None:
        """Redistribui capital da estratégia parada proporcionalmente entre as ativas."""
        freed = stopped_strategy.allocation
        if freed <= 0:
            return

        active = [
            s for s in portfolio._snapshots.values()
            if s.active and s.id != stopped_strategy.id and s.allocation > 0
        ]
        if not active:
            log.warning(
                "redistribute: nenhuma perna ativa para receber capital de '%s'",
                stopped_strategy.id,
            )
            return

        total_active = sum(s.allocation for s in active)
        for s in active:
            share = freed * (s.allocation / total_active)
            s.allocation = round(s.allocation + share, 2)

        stopped_strategy.allocation = 0.0
        log.info(
            "redistribute: $%.2f de '%s' redistribuídos para %d pernas ativas",
            freed, stopped_strategy.id, len(active),
        )

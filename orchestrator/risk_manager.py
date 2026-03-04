"""
Risk Manager — circuit breakers, position sizing e guarda de correlação.

Com Grid Bot e Momentum na mesma exchange (Bybit), é necessário
monitorar a exposição agregada para evitar risco concentrado.
"""
import logging

from strategies.base import BaseStrategy, StrategyStatus

log = logging.getLogger("risk_manager")


class RiskManager:
    def __init__(self, max_drawdown: float = 0.40, daily_target: float = 0.15):
        self.max_drawdown = max_drawdown        # -40% por perna → desliga
        self.daily_target = daily_target        # +15%/dia meta
        self.global_stop = 0.50                 # -50% total → para tudo
        self.max_crypto_exposure = 0.50         # máx 50% do capital total long crypto

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

    def check_crypto_correlation(
        self, portfolio, grid_strategy: BaseStrategy, momentum_strategy: BaseStrategy
    ) -> str | None:
        """
        Verifica exposição agregada long em crypto (Grid + Momentum na Bybit).

        Regra: nunca estar long crypto no Grid E no Momentum ao mesmo
        tempo com mais de 50% do capital total do portfólio.

        Retorna mensagem de alerta se violado, None se OK.
        """
        grid_snap = portfolio._snapshots.get(grid_strategy.id)
        mom_snap = portfolio._snapshots.get(momentum_strategy.id)

        if not grid_snap or not mom_snap:
            return None

        total_value = portfolio.total_value
        if total_value <= 0:
            return None

        # Exposição = alocação ativa (posições abertas) de cada perna crypto
        crypto_exposure = grid_snap.allocation + mom_snap.allocation
        exposure_ratio = crypto_exposure / total_value

        if exposure_ratio > self.max_crypto_exposure:
            msg = (
                f"⚠ Correlação crypto: exposição {exposure_ratio:.0%} "
                f"(Grid ${grid_snap.allocation:.2f} + Momentum ${mom_snap.allocation:.2f}) "
                f"> limite {self.max_crypto_exposure:.0%} do portfólio ${total_value:.2f}"
            )
            log.warning(msg)
            return msg

        return None

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

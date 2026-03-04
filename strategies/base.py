from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class StrategyStatus:
    id: str
    active: bool
    pnl_realized: float = 0.0
    pnl_unrealized: float = 0.0
    allocation: float = 0.0
    open_orders: int = 0
    paper_trade: bool = False
    extra: dict = field(default_factory=dict)

    @property
    def total_pnl(self) -> float:
        return self.pnl_realized + self.pnl_unrealized


class BaseStrategy(ABC):
    """Interface comum para todas as estratégias do portfólio."""

    def __init__(self, strategy_id: str, allocation: float, paper_trade: bool = False):
        self.id = strategy_id
        self.allocation = allocation  # USD alocado nessa perna
        self.paper_trade = paper_trade
        self._active = True

    @abstractmethod
    async def tick(self) -> StrategyStatus:
        """Executa a lógica da estratégia. Chamado a cada ciclo do orchestrator."""

    @abstractmethod
    async def close_all(self) -> None:
        """Cancela todas as ordens abertas e fecha todas as posições."""

    @abstractmethod
    async def resize(self, new_allocation: float) -> None:
        """Ajusta o tamanho das posições para a nova alocação (rebalanceamento)."""

    @abstractmethod
    async def get_pnl(self) -> float:
        """Retorna P&L total (realizado + não realizado) em USD."""

    @property
    def active(self) -> bool:
        return self._active

    def disable(self) -> None:
        self._active = False

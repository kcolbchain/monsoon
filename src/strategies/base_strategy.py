"""Base strategy class for farming operations."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


@dataclass
class Action:
    description: str
    protocol: str
    action_type: str  # swap, bridge, deposit, withdraw, approve
    params: dict = None

    def __post_init__(self):
        if self.params is None:
            self.params = {}


class BaseStrategy(ABC):
    """Abstract base for all farming strategies."""

    name: str = "base"
    weight: float = 1.0  # for weighted random selection
    supported_chains: list[str] = []

    @abstractmethod
    def get_actions(self, wallet, chain: str) -> list[Action]:
        """Return available actions for this wallet on this chain."""
        ...

    @abstractmethod
    def evaluate_eligibility(self, wallet) -> float:
        """Score 0-1 estimating airdrop eligibility for this wallet."""
        ...

    @abstractmethod
    def execute(self, wallet, chain: str, action: Action) -> dict:
        """Execute an action. Returns result dict with tx_hash, gas_spent, etc."""
        ...

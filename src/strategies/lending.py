"""Aave V3 lending strategy — deposit / withdraw on schedule with wallet rotation,
simulation mode, and per-wallet interaction tracking.

Integrates with FarmingAgent via the BaseStrategy interface.
"""

from __future__ import annotations

import logging
import random
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional

from .base_strategy import BaseStrategy, Action
from ..protocols.aave_v3 import AaveV3Protocol, AAVE_V3_ADDRESSES

logger = logging.getLogger(__name__)

# Default assets the strategy will rotate through
DEFAULT_ASSETS = ["USDC", "USDT", "WETH", "DAI"]

# Deposit amount ranges per asset (human-readable units)
DEFAULT_AMOUNT_RANGES: dict[str, tuple[float, float]] = {
    "USDC": (10.0, 500.0),
    "USDT": (10.0, 500.0),
    "DAI": (10.0, 500.0),
    "WETH": (0.005, 0.1),
}


@dataclass
class LendingSchedule:
    """Controls when deposits and withdrawals happen."""
    deposit_interval_seconds: int = 3600       # 1 hour default
    withdraw_interval_seconds: int = 14400     # 4 hours default
    min_hold_seconds: int = 1800               # min time to keep deposit before withdraw
    jitter_pct: float = 0.25                   # ±25 % randomisation on intervals


class LendingStrategy(BaseStrategy):
    """Farm airdrops by supplying / withdrawing assets on Aave V3.

    Features
    --------
    * Multi-asset support (USDC, USDT, WETH, DAI)
    * Scheduled deposit / withdraw with configurable intervals
    * Wallet rotation (via FarmingAgent round-robin)
    * Simulation / dry-run mode
    * Per-wallet interaction counter
    * Health-factor checks before borrow-related actions
    """

    name = "lending"
    weight = 1.2
    supported_chains = list(AAVE_V3_ADDRESSES.keys())

    def __init__(
        self,
        *,
        simulate: bool = True,
        assets: list[str] | None = None,
        amount_ranges: dict[str, tuple[float, float]] | None = None,
        schedule: LendingSchedule | None = None,
        min_health_factor: float = 1.5,
    ):
        self.simulate = simulate
        self.assets = assets or list(DEFAULT_ASSETS)
        self.amount_ranges = amount_ranges or dict(DEFAULT_AMOUNT_RANGES)
        self.schedule = schedule or LendingSchedule()
        self.min_health_factor = min_health_factor

        # Per-wallet state --------------------------------------------------
        # wallet_address → int
        self._interaction_count: dict[str, int] = defaultdict(int)
        # wallet_address → datetime of last deposit
        self._last_deposit_time: dict[str, datetime] = {}
        # wallet_address → datetime of last withdraw
        self._last_withdraw_time: dict[str, datetime] = {}
        # wallet_address → list of (asset, amount, timestamp) active deposits
        self._active_deposits: dict[str, list[dict]] = defaultdict(list)

        # Protocol instances per chain (lazy-created)
        self._protocols: dict[str, AaveV3Protocol] = {}

    # ------------------------------------------------------------------
    # BaseStrategy interface
    # ------------------------------------------------------------------

    def get_actions(self, wallet, chain: str) -> list[Action]:
        """Return available lending actions for *wallet* on *chain*."""
        if chain not in AAVE_V3_ADDRESSES:
            return []

        protocol = self._get_protocol(chain)
        available_assets = [
            a for a in self.assets if a in protocol.get_supported_assets()
        ]
        if not available_assets:
            return []

        actions: list[Action] = []
        addr = wallet.address
        now = datetime.utcnow()

        # -- Deposit action (if interval elapsed) --------------------------
        if self._can_deposit(addr, now):
            asset = random.choice(available_assets)
            lo, hi = self.amount_ranges.get(asset, (10.0, 100.0))
            amount = round(random.uniform(lo, hi), 6)
            actions.append(Action(
                description=f"Supply {amount} {asset} to Aave V3",
                protocol="aave_v3",
                action_type="deposit",
                params={
                    "asset": asset,
                    "amount": amount,
                    "chain": chain,
                    "wallet": addr,
                },
            ))

        # -- Withdraw action (if there is an active deposit old enough) ----
        for dep in list(self._active_deposits.get(addr, [])):
            held = (now - dep["timestamp"]).total_seconds()
            if held >= self.schedule.min_hold_seconds and self._can_withdraw(addr, now):
                actions.append(Action(
                    description=f"Withdraw {dep['amount']} {dep['asset']} from Aave V3",
                    protocol="aave_v3",
                    action_type="withdraw",
                    params={
                        "asset": dep["asset"],
                        "amount": dep["amount"],
                        "chain": chain,
                        "wallet": addr,
                    },
                ))
                break  # one withdraw per tick

        return actions

    def evaluate_eligibility(self, wallet) -> float:
        """Score 0–1 estimating airdrop eligibility for this wallet."""
        interactions = self._interaction_count.get(wallet.address, 0)
        unique_days = wallet.unique_days_active
        unique_protocols = len(wallet.unique_protocols)

        score = 0.0
        score += min(interactions / 20, 0.3)       # lending volume
        score += min(unique_days / 30, 0.3)         # consistency
        score += min(unique_protocols / 5, 0.2)     # protocol diversity
        score += min(wallet.total_gas_spent / 0.5, 0.2)

        return min(score, 1.0)

    def execute(self, wallet, chain: str, action: Action) -> dict:
        """Execute a deposit or withdraw action."""
        protocol = self._get_protocol(chain)
        params = action.params
        addr = wallet.address
        asset = params["asset"]
        amount = params["amount"]

        if action.action_type == "deposit":
            result = protocol.supply(addr, asset, amount)
            if result.success:
                self._record_deposit(addr, asset, amount)
            return self._to_result_dict(result)

        if action.action_type == "withdraw":
            result = protocol.withdraw(addr, asset, amount)
            if result.success:
                self._record_withdraw(addr, asset, amount)
            return self._to_result_dict(result)

        raise ValueError(f"Unsupported action type: {action.action_type}")

    # ------------------------------------------------------------------
    # Interaction tracking
    # ------------------------------------------------------------------

    def get_interaction_count(self, wallet_address: str) -> int:
        return self._interaction_count.get(wallet_address, 0)

    def get_all_interaction_counts(self) -> dict[str, int]:
        return dict(self._interaction_count)

    def get_active_deposits(self, wallet_address: str) -> list[dict]:
        return list(self._active_deposits.get(wallet_address, []))

    # ------------------------------------------------------------------
    # Health-factor gate
    # ------------------------------------------------------------------

    def check_health(self, wallet_address: str, chain: str) -> bool:
        """Return True if the wallet's Aave health factor is above threshold."""
        protocol = self._get_protocol(chain)
        report = protocol.get_health_factor(wallet_address)
        return report.health_factor >= self.min_health_factor

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _get_protocol(self, chain: str) -> AaveV3Protocol:
        if chain not in self._protocols:
            self._protocols[chain] = AaveV3Protocol(chain, simulate=self.simulate)
        return self._protocols[chain]

    def _jittered(self, base_seconds: int) -> float:
        jitter = base_seconds * self.schedule.jitter_pct
        return base_seconds + random.uniform(-jitter, jitter)

    def _can_deposit(self, addr: str, now: datetime) -> bool:
        last = self._last_deposit_time.get(addr)
        if last is None:
            return True
        return (now - last).total_seconds() >= self._jittered(
            self.schedule.deposit_interval_seconds
        )

    def _can_withdraw(self, addr: str, now: datetime) -> bool:
        last = self._last_withdraw_time.get(addr)
        if last is None:
            return True
        return (now - last).total_seconds() >= self._jittered(
            self.schedule.withdraw_interval_seconds
        )

    def _record_deposit(self, addr: str, asset: str, amount: float):
        self._interaction_count[addr] += 1
        self._last_deposit_time[addr] = datetime.utcnow()
        self._active_deposits[addr].append({
            "asset": asset,
            "amount": amount,
            "timestamp": datetime.utcnow(),
        })
        logger.info(
            f"[lending] {addr[:10]}… deposited {amount} {asset} "
            f"(interactions: {self._interaction_count[addr]})"
        )

    def _record_withdraw(self, addr: str, asset: str, amount: float):
        self._interaction_count[addr] += 1
        self._last_withdraw_time[addr] = datetime.utcnow()
        deposits = self._active_deposits.get(addr, [])
        self._active_deposits[addr] = [
            d for d in deposits
            if not (d["asset"] == asset and d["amount"] == amount)
        ]
        logger.info(
            f"[lending] {addr[:10]}… withdrew {amount} {asset} "
            f"(interactions: {self._interaction_count[addr]})"
        )

    @staticmethod
    def _to_result_dict(result) -> dict:
        return {
            "success": result.success,
            "tx_hash": result.tx_hash,
            "asset": result.asset,
            "amount": result.amount,
            "chain": result.chain,
            "simulated": result.simulated,
            "gas_spent": result.gas_spent,
        }

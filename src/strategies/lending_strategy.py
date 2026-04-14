"""Lending protocol strategy (Aave V3, Compound V3).

Deposits, borrows, and repays on lending protocols to accumulate
protocol interactions for airdrop eligibility.

Implements issue #2: Extend BaseStrategy, support Aave V3 and Compound V3.
"""

from typing import Dict, Any, Optional
import random
import logging

from web3 import Web3

from .base_strategy import BaseStrategy, Action
from ..chains.evm import EVMConnector

logger = logging.getLogger(__name__)


# ── Protocol definitions ──────────────────────────────────────────────────────

LENDING_PROTOCOLS = {
    "ethereum": [
        {"name": "AaveV3", "label": "Aave V3", "version": 3},
        {"name": "CompoundV3", "label": "Compound V3", "version": 3},
        {"name": "Spark", "label": "Spark Protocol", "version": 3},
    ],
    "arbitrum": [
        {"name": "AaveV3", "label": "Aave V3", "version": 3},
        {"name": "CompoundV3", "label": "Compound V3", "version": 3},
    ],
    "optimism": [
        {"name": "AaveV3", "label": "Aave V3", "version": 3},
        {"name": "Sonne", "label": "Sonne Finance", "version": 2},
    ],
    "base": [
        {"name": "AaveV3", "label": "Aave V3", "version": 3},
        {"name": "CompoundV3", "label": "Compound V3", "version": 3},
        {"name": "Moonwell", "label": "Moonwell", "version": 3},
    ],
    "polygon": [
        {"name": "AaveV3", "label": "Aave V3", "version": 3},
        {"name": "CompoundV3", "label": "Compound V3", "version": 3},
    ],
}

SUPPLY_TOKENS = [
    ("ETH", 0.01, 0.5),
    ("USDC", 100, 5000),
    ("USDT", 100, 5000),
    ("DAI", 100, 5000),
    ("WBTC", 0.001, 0.05),
]

BORROW_TOKENS = [
    ("USDC", 50, 2000),
    ("USDT", 50, 2000),
    ("DAI", 50, 2000),
    ("ETH", 0.005, 0.2),
]


# ── Interaction Tracker ────────────────────────────────────────────────────────

class InteractionTracker:
    """Tracks protocol interaction counts per wallet."""

    def __init__(self):
        self._counts: Dict[str, int] = {}
        logger.info("Initialized InteractionTracker.")

    def increment(self, wallet_address: str):
        self._counts[wallet_address] = self._counts.get(wallet_address, 0) + 1

    def get_count(self, wallet_address: str) -> int:
        return self._counts.get(wallet_address, 0)

    def get_all_counts(self) -> Dict[str, int]:
        return self._counts.copy()


# ── Protocol Client ────────────────────────────────────────────────────────────

class ProtocolClient:
    """Client for interacting with Aave V3 or Compound V3."""

    def __init__(self, web3: Web3, protocol_name: str, config: Dict[str, Any]):
        self.web3 = web3
        self.protocol_name = protocol_name
        self.config = config
        logger.info(f"Initialized {protocol_name} client for chain_id={self.web3.eth.chain_id}")

    def deposit(self, wallet_address: str, asset_address: str, amount: int,
                simulate: bool = False) -> Optional[str]:
        action_desc = f"Deposit {self.web3.from_wei(amount, 'ether')} of {asset_address} to {self.protocol_name} from {wallet_address}"
        if simulate:
            logger.info(f"[SIMULATION] {action_desc}")
            return None
        logger.info(action_desc)
        return f"mock_tx_hash_{self.protocol_name}_deposit_{wallet_address}_{amount}"

    def withdraw(self, wallet_address: str, asset_address: str, amount: int,
                 simulate: bool = False) -> Optional[str]:
        action_desc = f"Withdraw {self.web3.from_wei(amount, 'ether')} of {asset_address} from {self.protocol_name} to {wallet_address}"
        if simulate:
            logger.info(f"[SIMULATION] {action_desc}")
            return None
        logger.info(action_desc)
        return f"mock_tx_hash_{self.protocol_name}_withdraw_{wallet_address}_{amount}"


# ── Lending Strategy (extends BaseStrategy) ────────────────────────────────────

class LendingStrategy(BaseStrategy):
    """Farm airdrops by interacting with lending protocols.

    Generates deposit, borrow, and repay actions that signal
    genuine protocol usage for airdrop eligibility.

    Extends BaseStrategy as required by issue #2.
    Supports Aave V3 and Compound V3 (and compatible protocols).
    """

    name = "lending"
    weight = 0.8
    supported_chains = ["ethereum", "arbitrum", "optimism", "base", "polygon"]

    def __init__(self, interaction_tracker: Optional[InteractionTracker] = None,
                 protocol_name: Optional[str] = None):
        self.interaction_tracker = interaction_tracker or InteractionTracker()
        self._protocol_name = protocol_name  # Optional: restrict to single protocol

    def get_actions(self, wallet, chain: str) -> list[Action]:
        actions = []
        protocols = LENDING_PROTOCOLS.get(chain, [])

        # Optionally filter to single protocol
        if self._protocol_name:
            protocols = [p for p in protocols if p["name"] == self._protocol_name]

        for protocol in protocols:
            # Supply action
            token, min_amt, max_amt = random.choice(SUPPLY_TOKENS)
            supply_amount = round(random.uniform(min_amt, max_amt), 4)

            actions.append(Action(
                description=f"Supply {supply_amount} {token} to {protocol['label']}",
                protocol=protocol["name"],
                action_type="deposit",
                params={
                    "protocol": protocol["name"],
                    "action": "supply",
                    "token": token,
                    "amount": supply_amount,
                    "version": protocol["version"],
                },
            ))

            # Borrow action (70% chance)
            if random.random() > 0.3:
                borrow_token, b_min, b_max = random.choice(BORROW_TOKENS)
                borrow_amount = round(random.uniform(b_min, b_max), 4)

                actions.append(Action(
                    description=f"Borrow {borrow_amount} {borrow_token} from {protocol['label']}",
                    protocol=protocol["name"],
                    action_type="borrow",
                    params={
                        "protocol": protocol["name"],
                        "action": "borrow",
                        "token": borrow_token,
                        "amount": borrow_amount,
                        "version": protocol["version"],
                    },
                ))

            # Repay action (40% chance)
            if random.random() > 0.6:
                repay_token, _, _ = random.choice(BORROW_TOKENS)
                repay_amount = round(random.uniform(50, 1000), 4)

                actions.append(Action(
                    description=f"Repay {repay_amount} {repay_token} to {protocol['label']}",
                    protocol=protocol["name"],
                    action_type="repay",
                    params={
                        "protocol": protocol["name"],
                        "action": "repay",
                        "token": repay_token,
                        "amount": repay_amount,
                        "version": protocol["version"],
                    },
                ))

        return actions

    def evaluate_eligibility(self, wallet) -> float:
        """Score 0-1 for airdrop eligibility based on lending activity."""
        lending_actions = [
            a for a in wallet.activity
            if a.action in ("deposit", "borrow", "repay", "supply")
            or a.protocol in ("AaveV3", "CompoundV3", "Spark", "Sonne", "Moonwell")
        ]

        unique_days = wallet.unique_days_active
        unique_protocols = len(wallet.unique_protocols)
        deposit_count = sum(1 for a in lending_actions if a.action in ("deposit", "supply"))
        borrow_count = sum(1 for a in lending_actions if a.action == "borrow")
        repay_count = sum(1 for a in lending_actions if a.action == "repay")

        score = 0.0
        score += min(deposit_count / 15, 0.25)
        score += min(borrow_count / 10, 0.20)
        score += min(repay_count / 5, 0.15)
        score += min(unique_days / 30, 0.20)
        score += min(unique_protocols / 4, 0.10)
        score += min(wallet.total_gas_spent / 0.3, 0.10)

        return min(score, 1.0)

    def execute(self, wallet, chain: str, action: Action) -> dict:
        """Execute a lending action via EVM connector."""
        connector = EVMConnector(chain, simulate=True)

        protocol_addresses = {
            "AaveV3": "0x" + "aa" * 20,
            "CompoundV3": "0x" + "cc" * 20,
            "Spark": "0x" + "sp" * 20,
            "Sonne": "0x" + "sn" * 20,
            "Moonwell": "0x" + "mw" * 20,
        }

        to_addr = protocol_addresses.get(action.params.get("protocol", ""), "0x" + "ff" * 20)

        result = connector.simulate_transaction(
            from_addr=wallet.address,
            to_addr=to_addr,
            value=action.params.get("amount", 0),
            tx_type=action.action_type,
        )

        logger.info(f"[{wallet.label}] {action.description} -> {result['tx_hash'][:16]}...")

        wallet.record_activity(
            chain=chain,
            protocol=action.params.get("protocol", "unknown"),
            action=action.action_type,
            tx_hash=result["tx_hash"],
            gas_spent=result.get("gas_cost_eth", 0.001),
        )

        self.interaction_tracker.increment(wallet.address)

        return result

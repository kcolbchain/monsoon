"""Solana chain farming strategy — SPL transfers, staking, DeFi interactions."""

import random
import logging
from dataclasses import dataclass
from typing import Optional

from .base_strategy import BaseStrategy, Action
from ..chains.solana import SolanaConnector, SolanaWallet

logger = logging.getLogger(__name__)


SOLANA_DEFI_PROTOCOLS = [
    {"name": "jupiter", "label": "Jupiter DEX"},  # Solana's main DEX aggregator
    {"name": "raydium", "label": "Raydium AMM"},
    {"name": "orca", "label": "Orca Whirlpool"},
    {"name": "marinade", "label": "Marinade Finance (staking)"},  # Liquid staking
    {"name": "lido", "label": "Lido Solana (staking)"},
]

SOLANA_ACTIVITY_TYPES = [
    ("transfer", "transfer_sol", 0.000005),
    ("spl_transfer", "transfer_spl", 0.00001),
    ("stake", "stake_sol", 0.000025),
    ("swap", "jupiter_swap", 0.000025),
]


@dataclass
class SolanaActivity:
    """Represents a single Solana activity."""
    action: str
    protocol: str
    params: dict
    chain: str = "solana"


class SolanaStrategy(BaseStrategy):
    """
    Farm Solana ecosystem airdrops via wallet activity.

    Activities include:
    - SOL transfers between wallets
    - SPL token transfers
    - Liquid staking (Marinade/Lido)
    - DEX swaps (Jupiter/Raydium/Orca)

    Note: This strategy works in simulation mode by default.
    Set simulate=False on the connector for live interactions.
    """

    name = "solana"
    weight = 1.2  # Slightly lower weight due to fewer airdrop confirmations historically
    supported_chains = ["solana"]

    def __init__(self, network: str = "mainnet", simulate: bool = True):
        """
        Initialize Solana strategy.

        Args:
            network: "mainnet" or "devnet"
            simulate: If True, all operations are stubs. If False, hits real RPC.
        """
        self.network = network
        self.simulate = simulate
        self.connector = SolanaConnector(network=network, simulate=simulate)
        self._activity_log: list[SolanaActivity] = []

    def get_actions(self, wallet: SolanaWallet, **kwargs) -> list[Action]:
        """
        Generate farming actions for a Solana wallet.

        Args:
            wallet: SolanaWallet instance

        Returns:
            List of Action objects representing activity to perform
        """
        actions = []

        # Generate 3-5 random activities per wallet
        num_activities = random.randint(3, 5)

        for _ in range(num_activities):
            activity_type = random.choice(SOLANA_ACTIVITY_TYPES)
            action_name, method_name, fee = activity_type

            protocol = random.choice(SOLANA_DEFI_PROTOCOLS)

            if action_name == "transfer":
                # Random SOL transfer
                recipient = self._generate_fake_pubkey()
                amount = round(random.uniform(0.01, 0.5), 4)
                params = {
                    "recipient": recipient,
                    "amount_sol": amount,
                    "network": self.network,
                }
                desc = f"Transfer {amount} SOL to {recipient[:8]}... via {protocol['label']}"

            elif action_name == "spl_transfer":
                # Random SPL token transfer (simulated)
                recipient = self._generate_fake_pubkey()
                mint = random.choice([
                    "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",  # USDC
                    "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB",  # USDT
                    "mSoLzYCxHdYgdzU16g5QSh3i5K3z3KZK7ytfqcVp7q",  # mSOL
                ])
                amount = round(random.uniform(1, 100), 2)
                params = {
                    "recipient": recipient,
                    "mint": mint,
                    "amount": amount,
                    "network": self.network,
                }
                desc = f"Transfer {amount} SPL ({mint[:8]}...) via {protocol['label']}"

            elif action_name == "stake":
                # Liquid staking
                amount = round(random.uniform(0.5, 5.0), 2)
                params = {
                    "amount_sol": amount,
                    "protocol": protocol["name"],
                    "network": self.network,
                }
                desc = f"Stake {amount} SOL via {protocol['label']}"

            else:  # swap
                # Simulated DEX swap
                from_token = random.choice(["SOL", "USDC", "USDT"])
                to_token = random.choice(["mSOL", "jitoSOL", "bSOL"])
                amount_in = round(random.uniform(0.1, 2.0), 3)
                params = {
                    "from_token": from_token,
                    "to_token": to_token,
                    "amount_in": amount_in,
                    "protocol": protocol["name"],
                    "network": self.network,
                }
                desc = f"Swap {amount_in} {from_token} → {to_token} via {protocol['label']}"

            actions.append(Action(
                description=desc,
                protocol=protocol["name"],
                action_type=action_name,
                params=params,
            ))

            # Log the activity
            self._activity_log.append(SolanaActivity(
                action=action_name,
                protocol=protocol["name"],
                params=params,
            ))

        return actions

    def evaluate_eligibility(self, wallet: SolanaWallet) -> float:
        """
        Evaluate airdrop eligibility score based on activity history.

        Returns a float 0.0 - 1.0 representing eligibility strength.

        Solana eligibility factors:
        - Transaction count
        - Unique protocols used
        - SOL volume transferred
        - SPL token activity
        - Staking participation
        """
        activities = [a for a in self._activity_log if a.protocol != ""]

        if not activities:
            return 0.0

        score = 0.0

        # Transaction count (up to 0.3)
        score += min(len(activities) / 30, 0.3)

        # Protocol diversity (up to 0.25)
        unique_protocols = len({a.protocol for a in activities})
        score += min(unique_protocols / 5, 0.25)

        # Activity diversity (up to 0.25)
        activity_types = len({a.action for a in activities})
        score += min(activity_types / 4, 0.25)

        # SOL volume (up to 0.2)
        sol_transfers = [a for a in activities if a.action == "transfer"]
        if sol_transfers:
            total_sol = sum(a.params.get("amount_sol", 0) for a in sol_transfers)
            score += min(total_sol / 10, 0.2)

        return min(score, 1.0)

    def execute_action(self, wallet: SolanaWallet, action: Action) -> dict:
        """
        Execute a single action (simulation or live).

        Returns dict with execution result.
        """
        if self.simulate:
            return self._simulate_action(wallet, action)
        return self._live_action(wallet, action)

    def _simulate_action(self, wallet: SolanaWallet, action: Action) -> dict:
        """Simulate an action without network calls."""
        import random, string

        tx_hash = "".join(random.choices(string.ascii_letters + string.digits, k=88))

        return {
            "success": True,
            "tx_hash": tx_hash,
            "action": action.action_type,
            "protocol": action.protocol,
            "params": action.params,
            "simulated": True,
            "fee_sol": random.uniform(0.000005, 0.000025),
        }

    def _live_action(self, wallet: SolanaWallet, action: Action) -> dict:
        """Execute action against real Solana network."""
        if action.action_type == "transfer":
            return self.connector.transfer_sol(
                wallet=wallet,
                recipient=action.params["recipient"],
                amount_sol=action.params["amount_sol"],
            )
        elif action.action_type == "spl_transfer":
            return self.connector.transfer_spl(
                wallet=wallet,
                recipient=action.params["recipient"],
                mint=action.params["mint"],
                amount=action.params["amount"],
            )
        elif action.action_type == "stake":
            # For staking, we'd call the stake program
            # This is a simplified stub - real implementation would use staking SDK
            return {
                "success": True,
                "tx_hash": "STAKE_PLACEHOLDER",
                "action": "stake",
                "protocol": action.params["protocol"],
                "simulated": False,
                "note": "Staking requires special SDK integration",
            }
        elif action.action_type == "swap":
            # Jupiter/Raydium/Orca integration would go here
            return {
                "success": True,
                "tx_hash": "SWAP_PLACEHOLDER",
                "action": "swap",
                "protocol": action.params["protocol"],
                "simulated": False,
                "note": "DEX swap requires Jupiter/Raydium SDK",
            }

        return {"success": False, "error": "Unknown action type"}

    def _generate_fake_pubkey(self) -> str:
        """Generate a fake Solana pubkey for simulation."""
        import random, string
        chars = string.ascii_letters + string.digits
        return "".join(random.choices(chars, k=44))

    def get_supported_protocols(self) -> list[dict]:
        """Return list of supported DeFi protocols."""
        return SOLANA_DEFI_PROTOCOLS

    def __repr__(self) -> str:
        mode = "simulate" if self.simulate else "live"
        return f"SolanaStrategy(network={self.network}, {mode})"

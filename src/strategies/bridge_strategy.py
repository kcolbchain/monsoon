"""Cross-chain bridge farming strategy."""

import random
import logging
from ..strategies.base_strategy import BaseStrategy, Action
from ..chains.evm import EVMConnector

logger = logging.getLogger(__name__)

BRIDGE_PROTOCOLS = [
    {"name": "stargate", "label": "Stargate Finance"},
    {"name": "across", "label": "Across Protocol"},
    {"name": "hop", "label": "Hop Protocol"},
    {"name": "synapse", "label": "Synapse Bridge"},
]

BRIDGE_ROUTES = [
    ("ethereum", "arbitrum"),
    ("ethereum", "optimism"),
    ("ethereum", "base"),
    ("arbitrum", "optimism"),
    ("arbitrum", "base"),
    ("optimism", "base"),
    ("polygon", "ethereum"),
    ("bsc", "polygon"),
]


class BridgeStrategy(BaseStrategy):
    """Farm airdrops by bridging assets across chains."""

    name = "bridge"
    weight = 1.5
    supported_chains = ["ethereum", "arbitrum", "optimism", "base", "polygon", "bsc"]

    def get_actions(self, wallet, chain: str) -> list[Action]:
        actions = []
        routes = [r for r in BRIDGE_ROUTES if r[0] == chain]

        for src, dst in routes:
            protocol = random.choice(BRIDGE_PROTOCOLS)
            amount = round(random.uniform(0.001, 0.05), 4)
            actions.append(Action(
                description=f"Bridge {amount} ETH {src}→{dst} via {protocol['label']}",
                protocol=protocol["name"],
                action_type="bridge",
                params={"src": src, "dst": dst, "amount": amount,
                        "bridge": protocol["name"]},
            ))

        return actions

    def evaluate_eligibility(self, wallet) -> float:
        bridge_actions = [a for a in wallet.activity if a.action.startswith("Bridge")]
        unique_days = wallet.unique_days_active
        unique_chains = len({a.chain for a in wallet.activity})

        score = 0.0
        score += min(len(bridge_actions) / 20, 0.3)  # volume: up to 0.3
        score += min(unique_days / 30, 0.3)  # consistency: up to 0.3
        score += min(unique_chains / 5, 0.2)  # chain diversity: up to 0.2
        score += min(wallet.total_gas_spent / 0.5, 0.2)  # gas spent: up to 0.2

        return min(score, 1.0)

    def execute(self, wallet, chain: str, action: Action) -> dict:
        connector = EVMConnector(chain, simulate=True)
        result = connector.simulate_transaction(
            from_addr=wallet.address,
            to_addr=f"0x{'b1' * 20}",  # mock bridge contract
            value=action.params.get("amount", 0.01),
            tx_type="bridge",
        )
        logger.info(f"[{wallet.label}] {action.description} -> {result['tx_hash'][:16]}...")
        return result

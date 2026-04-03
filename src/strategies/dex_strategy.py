"""DEX interaction farming strategy."""

import random
import logging
from ..strategies.base_strategy import BaseStrategy, Action
from ..chains.evm import EVMConnector

logger = logging.getLogger(__name__)

DEX_PROTOCOLS = {
    "ethereum": [{"name": "uniswap", "label": "Uniswap V3"}],
    "arbitrum": [{"name": "uniswap", "label": "Uniswap V3"}, {"name": "camelot", "label": "Camelot"}],
    "optimism": [{"name": "velodrome", "label": "Velodrome"}, {"name": "uniswap", "label": "Uniswap V3"}],
    "base": [{"name": "aerodrome", "label": "Aerodrome"}, {"name": "uniswap", "label": "Uniswap V3"}],
    "bsc": [{"name": "pancakeswap", "label": "PancakeSwap"}],
    "polygon": [{"name": "quickswap", "label": "QuickSwap"}, {"name": "uniswap", "label": "Uniswap V3"}],
}

TOKEN_PAIRS = [
    ("ETH", "USDC"), ("ETH", "USDT"), ("ETH", "DAI"),
    ("WBTC", "ETH"), ("ETH", "ARB"), ("ETH", "OP"),
]


class DexStrategy(BaseStrategy):
    """Farm airdrops by interacting with DEXes."""

    name = "dex"
    weight = 1.0
    supported_chains = ["ethereum", "arbitrum", "optimism", "base", "bsc", "polygon"]

    def get_actions(self, wallet, chain: str) -> list[Action]:
        actions = []
        dexes = DEX_PROTOCOLS.get(chain, [])

        for dex in dexes:
            pair = random.choice(TOKEN_PAIRS)
            amount = round(random.uniform(0.001, 0.1), 4)

            actions.append(Action(
                description=f"Swap {amount} {pair[0]}→{pair[1]} on {dex['label']}",
                protocol=dex["name"],
                action_type="swap",
                params={"dex": dex["name"], "token_in": pair[0],
                        "token_out": pair[1], "amount": amount},
            ))

            # Also add liquidity provision actions
            if random.random() > 0.5:
                actions.append(Action(
                    description=f"Add LP {pair[0]}/{pair[1]} on {dex['label']}",
                    protocol=dex["name"],
                    action_type="deposit",
                    params={"dex": dex["name"], "token_a": pair[0],
                            "token_b": pair[1], "amount": amount},
                ))

        return actions

    def evaluate_eligibility(self, wallet) -> float:
        swap_actions = [a for a in wallet.activity if "Swap" in a.action or "LP" in a.action]
        unique_days = wallet.unique_days_active
        unique_protocols = len(wallet.unique_protocols)

        score = 0.0
        score += min(len(swap_actions) / 30, 0.3)  # volume
        score += min(unique_days / 30, 0.3)  # consistency
        score += min(unique_protocols / 5, 0.2)  # protocol diversity
        score += min(wallet.total_gas_spent / 0.5, 0.2)  # gas spent

        return min(score, 1.0)

    def execute(self, wallet, chain: str, action: Action) -> dict:
        connector = EVMConnector(chain, simulate=True)
        result = connector.simulate_transaction(
            from_addr=wallet.address,
            to_addr=f"0x{'d3' * 20}",  # mock dex router
            value=action.params.get("amount", 0.01),
            tx_type=action.action_type,
        )
        logger.info(f"[{wallet.label}] {action.description} -> {result['tx_hash'][:16]}...")
        return result

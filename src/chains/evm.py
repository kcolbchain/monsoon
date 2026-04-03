"""EVM chain connector — transaction building, gas estimation, multi-chain support."""

import logging
from dataclasses import dataclass
from typing import Optional

import yaml

logger = logging.getLogger(__name__)


@dataclass
class ChainConfig:
    name: str
    chain_id: int
    rpc_url: str
    native_token: str
    explorer_url: str
    avg_gas_price_gwei: float = 20.0


CHAINS: dict[str, ChainConfig] = {
    "ethereum": ChainConfig("Ethereum", 1, "https://eth.llamarpc.com", "ETH", "https://etherscan.io", 30),
    "arbitrum": ChainConfig("Arbitrum", 42161, "https://arb1.arbitrum.io/rpc", "ETH", "https://arbiscan.io", 0.1),
    "optimism": ChainConfig("Optimism", 10, "https://mainnet.optimism.io", "ETH", "https://optimistic.etherscan.io", 0.01),
    "base": ChainConfig("Base", 8453, "https://mainnet.base.org", "ETH", "https://basescan.org", 0.01),
    "bsc": ChainConfig("BSC", 56, "https://bsc-dataseed.binance.org", "BNB", "https://bscscan.com", 3),
    "polygon": ChainConfig("Polygon", 137, "https://polygon-rpc.com", "MATIC", "https://polygonscan.com", 30),
}


class EVMConnector:
    """Connect to EVM chains, build and simulate transactions."""

    def __init__(self, chain: str, simulate: bool = True):
        if chain not in CHAINS:
            raise ValueError(f"Unknown chain: {chain}. Supported: {list(CHAINS.keys())}")
        self.chain_config = CHAINS[chain]
        self.simulate = simulate
        self.web3 = None

        if not simulate:
            try:
                from web3 import Web3
                self.web3 = Web3(Web3.HTTPProvider(self.chain_config.rpc_url))
                logger.info(f"Connected to {chain}: block {self.web3.eth.block_number}")
            except Exception as e:
                logger.error(f"Failed to connect to {chain}: {e}")

    def estimate_gas(self, tx_type: str = "swap") -> dict:
        """Estimate gas for common transaction types."""
        gas_limits = {
            "transfer": 21000,
            "swap": 150000,
            "bridge": 200000,
            "approve": 46000,
            "deposit": 100000,
            "withdraw": 120000,
        }
        gas_limit = gas_limits.get(tx_type, 150000)
        gas_price_gwei = self.chain_config.avg_gas_price_gwei
        cost_eth = gas_limit * gas_price_gwei / 1e9

        return {
            "gas_limit": gas_limit,
            "gas_price_gwei": gas_price_gwei,
            "estimated_cost_native": cost_eth,
            "chain": self.chain_config.name,
        }

    def simulate_transaction(self, from_addr: str, to_addr: str,
                             value: float, tx_type: str = "swap") -> dict:
        """Simulate a transaction without broadcasting."""
        gas = self.estimate_gas(tx_type)
        import random
        return {
            "success": True,
            "tx_hash": f"0x{''.join(random.choices('abcdef0123456789', k=64))}",
            "from": from_addr,
            "to": to_addr,
            "value": value,
            "gas_spent": gas["estimated_cost_native"],
            "chain": self.chain_config.name,
            "simulated": True,
        }

    def get_balance(self, address: str) -> float:
        """Get native token balance."""
        if self.simulate:
            import random
            return random.uniform(0.01, 2.0)
        if self.web3:
            bal = self.web3.eth.get_balance(address)
            return float(self.web3.from_wei(bal, "ether"))
        return 0.0

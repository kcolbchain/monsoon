"""
Wallet intelligence — track what smart money wallets are doing.

Monitors known alpha wallets (early airdrop claimers, whale farmers)
to identify which protocols they're interacting with → signal for targets.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

import aiohttp

logger = logging.getLogger(__name__)


@dataclass
class WalletActivity:
    address: str
    chain: str
    protocol: str
    action: str
    timestamp: datetime
    tx_hash: str
    value_usd: Optional[float] = None


@dataclass
class TrackedWallet:
    address: str
    label: str
    tags: list[str] = field(default_factory=list)  # e.g., ["airdrop_hunter", "whale", "smart_money"]
    recent_activity: list[WalletActivity] = field(default_factory=list)


# Known alpha wallets — these addresses historically qualify early for airdrops
# Source: on-chain analysis of early Arbitrum, Optimism, Jito, Jupiter claimers
ALPHA_WALLETS = [
    TrackedWallet(
        address="0x2c169dfe5fbba12957bdd0ba47d9cedbfe260ca7",
        label="early-arb-claimer-1",
        tags=["airdrop_hunter", "multi_chain"],
    ),
    TrackedWallet(
        address="0x4838b106fce9647bdf1e7877bf73ce8b0bad5f97",
        label="layerzero-whale",
        tags=["bridge_heavy", "smart_money"],
    ),
    # Add more via on-chain analysis or community lists
]


class WalletIntel:
    """Monitor smart money wallet activity for airdrop signals."""

    def __init__(self, wallets: list[TrackedWallet] = None):
        self.wallets = wallets or list(ALPHA_WALLETS)

    async def fetch_recent_activity(self, wallet: TrackedWallet, chain: str = "ethereum") -> list[WalletActivity]:
        """Fetch recent transactions for a tracked wallet via block explorer API."""
        # Etherscan-compatible API (works for Arbiscan, Optimistic Etherscan, BaseScan)
        explorer_apis = {
            "ethereum": "https://api.etherscan.io/api",
            "arbitrum": "https://api.arbiscan.io/api",
            "optimism": "https://api-optimistic.etherscan.io/api",
            "base": "https://api.basescan.org/api",
        }

        api_url = explorer_apis.get(chain)
        if not api_url:
            return []

        params = {
            "module": "account",
            "action": "txlist",
            "address": wallet.address,
            "startblock": 0,
            "endblock": 99999999,
            "page": 1,
            "offset": 20,  # last 20 txns
            "sort": "desc",
            "apikey": "",  # works without key at lower rate
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(api_url, params=params, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status != 200:
                        return []
                    data = await resp.json()
                    if data.get("status") != "1":
                        return []

                    activities = []
                    for tx in data.get("result", []):
                        activities.append(WalletActivity(
                            address=wallet.address,
                            chain=chain,
                            protocol=self._identify_protocol(tx.get("to", ""), chain),
                            action=f"tx to {tx.get('to', 'unknown')[:10]}...",
                            timestamp=datetime.fromtimestamp(int(tx.get("timeStamp", 0))),
                            tx_hash=tx.get("hash", ""),
                            value_usd=None,  # would need price feed
                        ))

                    wallet.recent_activity = activities
                    return activities
        except Exception as e:
            logger.warning(f"Failed to fetch activity for {wallet.label}: {e}")
            return []

    def _identify_protocol(self, to_address: str, chain: str) -> str:
        """Map contract addresses to protocol names."""
        # Known protocol routers/contracts
        known = {
            "0x68b3465833fb72a70ecdf485e0e4c7bd8665fc45": "uniswap_v3",
            "0xe592427a0aece92de3edee1f18e0157c05861564": "uniswap_v3",
            "0x1111111254eeb25477b68fb85ed929f73a960582": "1inch",
            "0xdef1c0ded9bec7f1a1670819833240f027b25eff": "0x_protocol",
            "0x3fc91a3afd70395cd496c647d5a6cc9d4b2b7fad": "uniswap_universal",
            "0x7a250d5630b4cf539739df2c5dacb4c659f2488d": "uniswap_v2",
            "0xd9e1ce17f2641f24ae83637ab66a2cca9c378b9f": "sushiswap",
        }
        return known.get(to_address.lower(), "unknown")

    async def scan_all(self, chains: list[str] = None) -> dict[str, list[WalletActivity]]:
        """Scan all tracked wallets across specified chains."""
        chains = chains or ["ethereum", "arbitrum", "optimism", "base"]
        results = {}

        for wallet in self.wallets:
            all_activity = []
            for chain in chains:
                activity = await self.fetch_recent_activity(wallet, chain)
                all_activity.extend(activity)
            results[wallet.label] = all_activity
            logger.info(f"Scanned {wallet.label}: {len(all_activity)} recent txns")

        return results

    def get_protocol_signals(self) -> dict[str, int]:
        """Aggregate: which protocols are smart money wallets interacting with most?"""
        protocol_counts: dict[str, int] = {}
        for wallet in self.wallets:
            for activity in wallet.recent_activity:
                proto = activity.protocol
                if proto != "unknown":
                    protocol_counts[proto] = protocol_counts.get(proto, 0) + 1

        return dict(sorted(protocol_counts.items(), key=lambda x: x[1], reverse=True))

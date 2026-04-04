"""
Airdrop target tracker — maintains a ranked list of protocols likely to airdrop.

Sources:
1. Curated target list (known unfunded protocols with token plans)
2. On-chain signals (TVL growth, governance activity, token contract deployments)
3. Social signals (X mentions, Discord activity, blog announcements)
4. Funding signals (VC raises without token → likely future airdrop)
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional

logger = logging.getLogger(__name__)


class Confidence(Enum):
    HIGH = "high"         # confirmed token, snapshot likely
    MEDIUM = "medium"     # strong signals but no confirmation
    LOW = "low"           # speculative
    CLAIMED = "claimed"   # already airdropped


@dataclass
class AirdropTarget:
    """A protocol that may airdrop tokens."""
    name: str
    chain: str
    confidence: Confidence
    category: str  # bridge, dex, lending, nft, social, l2, infra
    contracts: list[str] = field(default_factory=list)  # key contract addresses to interact with
    criteria: dict = field(default_factory=dict)  # known eligibility criteria
    notes: str = ""
    last_updated: datetime = field(default_factory=datetime.utcnow)
    priority_score: float = 0.0  # 0-10, computed from signals

    def __repr__(self):
        return f"<AirdropTarget {self.name} [{self.chain}] {self.confidence.value} score={self.priority_score:.1f}>"


# ============================================================
# Curated target database — the core alpha
# Updated manually + via automated signals
# ============================================================

CURATED_TARGETS: list[AirdropTarget] = [
    # ----- HIGH CONFIDENCE (confirmed token plans, no airdrop yet) -----
    AirdropTarget(
        name="Berachain",
        chain="berachain",
        confidence=Confidence.HIGH,
        category="l2",
        criteria={
            "testnet_activity": True,
            "mainnet_launch": "Q2 2026",
            "bgt_staking": True,
        },
        notes="Proof of Liquidity consensus. BGT token confirmed. Mainnet live, airdrop criteria being finalized.",
        priority_score=9.0,
    ),
    AirdropTarget(
        name="Monad",
        chain="monad",
        confidence=Confidence.HIGH,
        category="l2",
        criteria={
            "testnet_activity": True,
            "mainnet_launch": "2026",
            "raised": "$225M",
        },
        notes="Parallel EVM L1. $225M raised (Paradigm). Testnet live. No token yet → high airdrop probability.",
        priority_score=9.0,
    ),
    AirdropTarget(
        name="Linea",
        chain="linea",
        confidence=Confidence.HIGH,
        category="l2",
        contracts=["0x508Aa4F4e15A305300B9D2d0E602BDb57FBf3442"],  # Linea bridge
        criteria={
            "bridge_volume": ">0.1 ETH",
            "dex_swaps": ">5",
            "unique_months": ">3",
        },
        notes="Consensys zkEVM L2. Voyage program for points. LXP tokens tracking activity.",
        priority_score=8.5,
    ),
    AirdropTarget(
        name="Scroll",
        chain="scroll",
        confidence=Confidence.MEDIUM,
        category="l2",
        contracts=["0xD8A791fE2bE73eb6E6cF1eb0cb3F36adC9B3F8f9"],  # Scroll bridge
        criteria={
            "bridge_usage": True,
            "dex_interaction": True,
            "session_marks": True,
        },
        notes="zkEVM L2. SCR token launched but more airdrops expected. Marks program active.",
        priority_score=7.0,
    ),

    # ----- MEDIUM CONFIDENCE (strong signals) -----
    AirdropTarget(
        name="LayerZero",
        chain="multi",
        confidence=Confidence.MEDIUM,
        category="bridge",
        criteria={
            "cross_chain_messages": ">50",
            "unique_chains": ">3",
            "organic_activity": True,
        },
        notes="Omnichain messaging. ZRO token exists but more distributions possible. Anti-sybil checks aggressive.",
        priority_score=6.5,
    ),
    AirdropTarget(
        name="Ambient (CrocSwap)",
        chain="scroll",
        confidence=Confidence.MEDIUM,
        category="dex",
        criteria={
            "swap_volume": ">$1000",
            "lp_provision": True,
        },
        notes="DEX on Scroll. No token. Growing TVL. Community expects airdrop.",
        priority_score=6.0,
    ),
    AirdropTarget(
        name="Hyperlane",
        chain="multi",
        confidence=Confidence.MEDIUM,
        category="infra",
        criteria={
            "message_relay": True,
            "validator_run": True,
        },
        notes="Permissionless interoperability. Raised $18.5M. No token yet.",
        priority_score=6.5,
    ),

    # ----- ACTIVE POINT SYSTEMS (farm points → convert to tokens) -----
    AirdropTarget(
        name="EigenLayer",
        chain="ethereum",
        confidence=Confidence.HIGH,
        category="infra",
        criteria={
            "restake_eth": True,
            "avs_delegate": True,
            "eigen_points": True,
        },
        notes="Restaking. EIGEN token exists, ongoing point seasons for additional drops.",
        priority_score=7.5,
    ),
    AirdropTarget(
        name="Ethena",
        chain="ethereum",
        confidence=Confidence.MEDIUM,
        category="defi",
        criteria={
            "usde_mint": True,
            "sats_campaign": True,
            "sena_stake": True,
        },
        notes="USDe synthetic dollar. Sats campaign for points. Multiple airdrop seasons.",
        priority_score=6.0,
    ),
]


class AirdropTracker:
    """Manages the list of airdrop targets and their priority."""

    def __init__(self):
        self.targets: list[AirdropTarget] = list(CURATED_TARGETS)
        self._sort()

    def _sort(self):
        self.targets.sort(key=lambda t: t.priority_score, reverse=True)

    def get_active_targets(self, min_confidence: Confidence = Confidence.LOW) -> list[AirdropTarget]:
        """Get targets filtered by minimum confidence level."""
        confidence_order = {Confidence.HIGH: 3, Confidence.MEDIUM: 2, Confidence.LOW: 1, Confidence.CLAIMED: 0}
        min_level = confidence_order[min_confidence]
        return [t for t in self.targets if confidence_order[t.confidence] >= min_level]

    def get_targets_for_chain(self, chain: str) -> list[AirdropTarget]:
        """Get targets active on a specific chain."""
        return [t for t in self.targets if t.chain == chain or t.chain == "multi"]

    def add_target(self, target: AirdropTarget):
        self.targets.append(target)
        self._sort()

    def mark_claimed(self, name: str):
        for t in self.targets:
            if t.name == name:
                t.confidence = Confidence.CLAIMED
                logger.info(f"Marked {name} as claimed")

    def print_targets(self):
        """Print ranked target list."""
        print(f"\n{'#':>3}  {'Score':>5}  {'Confidence':>10}  {'Chain':>10}  {'Category':>8}  Name")
        print("─" * 70)
        for i, t in enumerate(self.targets):
            conf_color = {"high": "🟢", "medium": "🟡", "low": "🔴", "claimed": "⚪"}.get(t.confidence.value, "")
            print(f"{i+1:>3}  {t.priority_score:>5.1f}  {conf_color} {t.confidence.value:>8}  {t.chain:>10}  {t.category:>8}  {t.name}")

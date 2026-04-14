"""Airdrop-rights NFT wrapper — secondary market for farm positions.

Wraps airdrop farming positions as ERC-721 NFTs, allowing:
- Transfer of airdrop eligibility to other wallets
- Secondary market trading of farming positions
- Composability with DeFi (use NFT as collateral)

Issue #15: Wrap airdrop-rights as transferable NFT.
"""

import hashlib
import json
import logging
from dataclasses import dataclass, asdict, field
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class AirdropPosition:
    """Represents a farming position eligible for airdrops."""
    wallet_address: str
    wallet_label: str
    chain: str
    protocols: list[str]
    total_gas_spent: float
    total_actions: int
    unique_days: int
    eligibility_score: float
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def to_metadata(self) -> dict:
        """Generate NFT metadata."""
        return {
            "name": f"Airdrop Right: {self.wallet_label}",
            "description": f"Transferable airdrop eligibility position on {self.chain}",
            "image": f"data:image/svg+xml,{self._generate_badge_svg()}",
            "attributes": [
                {"trait_type": "Chain", "value": self.chain},
                {"trait_type": "Protocols", "value": ", ".join(self.protocols)},
                {"trait_type": "Total Gas (ETH)", "value": round(self.total_gas_spent, 4), "display_type": "number"},
                {"trait_type": "Total Actions", "value": self.total_actions, "display_type": "number"},
                {"trait_type": "Unique Days", "value": self.unique_days, "display_type": "number"},
                {"trait_type": "Eligibility Score", "value": round(self.eligibility_score, 2), "display_type": "number"},
                {"trait_type": "Created", "value": self.created_at},
            ],
        }

    def _generate_badge_svg(self) -> str:
        """Generate a simple SVG badge for the NFT image."""
        score_pct = int(self.eligibility_score * 100)
        color = "#22c55e" if score_pct >= 70 else "#eab308" if score_pct >= 40 else "#ef4444"
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="200" height="200">'
            f'<rect width="200" height="200" rx="20" fill="#1a1a2e"/>'
            f'<text x="100" y="50" text-anchor="middle" fill="white" font-size="14" font-family="monospace">'
            f'AIRDROP RIGHT</text>'
            f'<text x="100" y="80" text-anchor="middle" fill="{color}" font-size="36" font-weight="bold">'
            f'{score_pct}%</text>'
            f'<text x="100" y="120" text-anchor="middle" fill="#888" font-size="11">{self.chain}</text>'
            f'<text x="100" y="145" text-anchor="middle" fill="#888" font-size="11">'
            f'{", ".join(self.protocols[:3])}</text>'
            f'<text x="100" y="180" text-anchor="middle" fill="#555" font-size="9">{self.wallet_label}</text>'
            f'</svg>'
        )

    def token_id(self) -> str:
        """Generate deterministic token ID from position data."""
        data = f"{self.wallet_address}:{self.chain}:{','.join(sorted(self.protocols))}"
        return hashlib.sha256(data.encode()).hexdigest()[:16]


class AirdropNFTManager:
    """Manage airdrop-rights NFTs.

    Mints, transfers, and tracks NFT positions representing
    airdrop farming eligibility.
    """

    def __init__(self, simulate: bool = True):
        self.simulate = simulate
        self._tokens: dict[str, dict] = {}  # token_id -> {owner, position, metadata}
        self._transfer_log: list[dict] = []
        logger.info(f"AirdropNFTManager initialized (simulate={simulate})")

    def mint(self, position: AirdropPosition) -> str:
        """Mint an airdrop-rights NFT from a farming position."""
        token_id = position.token_id()

        metadata = position.to_metadata()
        self._tokens[token_id] = {
            "owner": position.wallet_address,
            "position": asdict(position),
            "metadata": metadata,
            "minted_at": datetime.utcnow().isoformat(),
        }

        logger.info(f"Minted airdrop NFT #{token_id} for {position.wallet_label} "
                     f"(score: {position.eligibility_score:.2f})")
        return token_id

    def transfer(self, token_id: str, from_addr: str, to_addr: str) -> bool:
        """Transfer an airdrop-rights NFT to a new owner."""
        if token_id not in self._tokens:
            logger.error(f"Token #{token_id} not found")
            return False

        token = self._tokens[token_id]
        if token["owner"] != from_addr:
            logger.error(f"Not owner of token #{token_id}")
            return False

        token["owner"] = to_addr
        self._transfer_log.append({
            "token_id": token_id,
            "from": from_addr,
            "to": to_addr,
            "timestamp": datetime.utcnow().isoformat(),
        })

        logger.info(f"Transferred NFT #{token_id}: {from_addr[:10]}... → {to_addr[:10]}...")
        return True

    def get_token(self, token_id: str) -> Optional[dict]:
        """Get token details by ID."""
        return self._tokens.get(token_id)

    def get_tokens_by_owner(self, owner: str) -> list[dict]:
        """Get all tokens owned by an address."""
        return [
            {"token_id": tid, **info}
            for tid, info in self._tokens.items()
            if info["owner"] == owner
        ]

    def get_transfer_history(self, token_id: Optional[str] = None) -> list[dict]:
        """Get transfer history, optionally filtered by token."""
        if token_id:
            return [t for t in self._transfer_log if t["token_id"] == token_id]
        return self._transfer_log

    def get_market_listings(self) -> list[dict]:
        """Get all minted tokens (for marketplace display)."""
        return [
            {
                "token_id": tid,
                "owner": info["owner"],
                "chain": info["position"]["chain"],
                "eligibility_score": info["position"]["eligibility_score"],
                "protocols": info["position"]["protocols"],
            }
            for tid, info in self._tokens.items()
        ]

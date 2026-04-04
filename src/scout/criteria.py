"""
Eligibility checker — score wallets against known airdrop criteria.

Combines on-chain data with curated criteria to estimate
how likely a wallet is to qualify for specific airdrops.
"""

import logging
from dataclasses import dataclass
from typing import Optional

from ..agent.wallet_manager import Wallet
from .tracker import AirdropTarget

logger = logging.getLogger(__name__)


@dataclass
class EligibilityScore:
    target: str
    wallet: str
    score: float  # 0-100
    met_criteria: list[str]
    missing_criteria: list[str]
    recommendations: list[str]


class EligibilityChecker:
    """Check wallet eligibility against airdrop target criteria."""

    def check(self, wallet: Wallet, target: AirdropTarget) -> EligibilityScore:
        """Score a wallet against a target's known criteria."""
        met = []
        missing = []
        recommendations = []
        score = 0.0
        criteria = target.criteria

        # Check transaction volume
        if criteria.get("bridge_volume") or criteria.get("bridge_usage"):
            bridge_txns = [a for a in wallet.activity if "bridge" in a.action.lower()]
            if len(bridge_txns) >= 3:
                met.append("Bridge activity (3+ txns)")
                score += 15
            else:
                missing.append(f"Bridge activity (have {len(bridge_txns)}, need 3+)")
                recommendations.append(f"Bridge assets to {target.chain} via Stargate or Across")

        # Check DEX interaction
        if criteria.get("dex_swaps") or criteria.get("dex_interaction") or criteria.get("swap_volume"):
            swap_txns = [a for a in wallet.activity if "swap" in a.action.lower()]
            if len(swap_txns) >= 5:
                met.append("DEX swaps (5+ txns)")
                score += 15
            else:
                missing.append(f"DEX swaps (have {len(swap_txns)}, need 5+)")
                recommendations.append(f"Swap on native DEXes on {target.chain}")

        # Check unique active months
        if criteria.get("unique_months"):
            months = wallet.unique_days_active  # proxy
            target_months = int(str(criteria["unique_months"]).replace(">", ""))
            if months >= target_months * 4:  # ~4 days per month
                met.append(f"Active {months}+ days (multi-month)")
                score += 20
            else:
                missing.append(f"Activity consistency (need {target_months}+ months)")
                recommendations.append("Maintain regular activity over multiple months")

        # Check protocol diversity
        if len(wallet.unique_protocols) >= 3:
            met.append(f"Protocol diversity ({len(wallet.unique_protocols)} protocols)")
            score += 10
        else:
            missing.append(f"Protocol diversity (have {len(wallet.unique_protocols)}, want 3+)")
            recommendations.append("Interact with more protocols on the chain")

        # Check chain diversity
        unique_chains = len({a.chain for a in wallet.activity})
        if unique_chains >= 3:
            met.append(f"Chain diversity ({unique_chains} chains)")
            score += 10
        else:
            missing.append(f"Chain diversity (have {unique_chains}, want 3+)")
            recommendations.append("Use bridges to interact with more chains")

        # Check gas spent (anti-sybil signal)
        if wallet.total_gas_spent >= 0.05:
            met.append(f"Gas spent (${wallet.total_gas_spent:.3f} ETH)")
            score += 10
        else:
            missing.append("Gas spend too low — looks like a new/inactive wallet")
            recommendations.append("Increase organic transaction volume")

        # Check testnet activity flag
        if criteria.get("testnet_activity"):
            missing.append("Testnet activity (check manually)")
            recommendations.append(f"Participate in {target.name} testnet if available")

        # Check staking/restaking
        if criteria.get("restake_eth") or criteria.get("bgt_staking"):
            missing.append(f"Staking on {target.name} (check manually)")
            recommendations.append(f"Stake/restake on {target.name}")

        # Bonus for early activity
        if wallet.unique_days_active >= 30:
            met.append("Long-term user (30+ active days)")
            score += 10

        # Cap at 100
        score = min(score, 100)

        return EligibilityScore(
            target=target.name,
            wallet=wallet.label,
            score=score,
            met_criteria=met,
            missing_criteria=missing,
            recommendations=recommendations,
        )

    def check_all_targets(self, wallet: Wallet, targets: list[AirdropTarget]) -> list[EligibilityScore]:
        """Check wallet against all targets, sorted by score."""
        scores = [self.check(wallet, t) for t in targets]
        scores.sort(key=lambda s: s.score, reverse=True)
        return scores

    def print_report(self, scores: list[EligibilityScore]):
        """Print eligibility report for a wallet."""
        print(f"\n{'Target':>20}  {'Score':>6}  {'Met':>4}  {'Missing':>8}  Top recommendation")
        print("─" * 80)
        for s in scores:
            rec = s.recommendations[0] if s.recommendations else "—"
            icon = "🟢" if s.score >= 60 else "🟡" if s.score >= 30 else "🔴"
            print(f"{s.target:>20}  {icon} {s.score:>4.0f}%  {len(s.met_criteria):>4}  {len(s.missing_criteria):>8}  {rec}")

"""Tests for LendingStrategy (issue #2: Extend BaseStrategy, support Aave V3 / Compound V3)."""

import pytest
from unittest.mock import MagicMock, patch
from src.strategies.lending_strategy import (
    LendingStrategy,
    InteractionTracker,
    LENDING_PROTOCOLS,
)
from src.strategies.base_strategy import Action
from src.agent.wallet_manager import Wallet, WalletManager


@pytest.fixture
def strategy():
    return LendingStrategy()


@pytest.fixture
def wallet():
    manager = WalletManager(simulate=True)
    return manager.create_wallet("test-lender")


# ── BaseStrategy compliance ───────────────────────────────────────────────────

class TestBaseStrategyCompliance:
    def test_extends_base_strategy(self):
        from src.strategies.base_strategy import BaseStrategy
        assert issubclass(LendingStrategy, BaseStrategy)

    def test_has_required_attributes(self, strategy):
        assert strategy.name == "lending"
        assert strategy.weight > 0
        assert len(strategy.supported_chains) > 0

    def test_get_actions_returns_list(self, strategy, wallet):
        actions = strategy.get_actions(wallet, "ethereum")
        assert isinstance(actions, list)

    def test_evaluate_eligibility_returns_float(self, strategy, wallet):
        score = strategy.evaluate_eligibility(wallet)
        assert isinstance(score, float)
        assert 0.0 <= score <= 1.0


# ── Aave V3 support ───────────────────────────────────────────────────────────

class TestAaveV3:
    def test_aave_on_ethereum(self, strategy, wallet):
        actions = strategy.get_actions(wallet, "ethereum")
        aave_actions = [a for a in actions if a.params["protocol"] == "AaveV3"]
        assert len(aave_actions) >= 1  # At least supply

    def test_aave_on_arbitrum(self, strategy, wallet):
        actions = strategy.get_actions(wallet, "arbitrum")
        aave_actions = [a for a in actions if a.params["protocol"] == "AaveV3"]
        assert len(aave_actions) >= 1

    def test_aave_deposit_action(self, strategy, wallet):
        actions = strategy.get_actions(wallet, "base")
        deposits = [a for a in actions if a.action_type == "deposit" and a.params["protocol"] == "AaveV3"]
        assert len(deposits) >= 1


# ── Compound V3 support ──────────────────────────────────────────────────────

class TestCompoundV3:
    def test_compound_on_ethereum(self, strategy, wallet):
        actions = strategy.get_actions(wallet, "ethereum")
        compound_actions = [a for a in actions if a.params["protocol"] == "CompoundV3"]
        assert len(compound_actions) >= 1

    def test_compound_on_base(self, strategy, wallet):
        actions = strategy.get_actions(wallet, "base")
        compound_actions = [a for a in actions if a.params["protocol"] == "CompoundV3"]
        assert len(compound_actions) >= 1


# ── Action types ───────────────────────────────────────────────────────────────

class TestActionTypes:
    def test_supply_action_generated(self, strategy, wallet):
        actions = strategy.get_actions(wallet, "ethereum")
        supply = [a for a in actions if a.action_type == "deposit"]
        assert len(supply) >= 1

    def test_borrow_action_has_correct_params(self, strategy, wallet):
        """Borrow actions should include protocol, token, amount."""
        with patch('random.random', return_value=0.1):  # Force borrow
            actions = strategy.get_actions(wallet, "ethereum")
            borrows = [a for a in actions if a.action_type == "borrow"]
            if borrows:
                b = borrows[0]
                assert "protocol" in b.params
                assert "token" in b.params
                assert "amount" in b.params

    def test_repay_action_has_correct_params(self, strategy, wallet):
        # Run multiple times to eventually get a repay action
        for _ in range(20):
            actions = strategy.get_actions(wallet, "ethereum")
            repays = [a for a in actions if a.action_type == "repay"]
            if repays:
                r = repays[0]
                assert r.params["action"] == "repay"
                return
        pytest.skip("No repay action generated in 20 attempts (random)")


# ── Interaction Tracker ────────────────────────────────────────────────────────

class TestInteractionTracker:
    def test_increment(self):
        tracker = InteractionTracker()
        tracker.increment("0xabc")
        assert tracker.get_count("0xabc") == 1

    def test_increment_accumulates(self):
        tracker = InteractionTracker()
        tracker.increment("0xabc")
        tracker.increment("0xabc")
        tracker.increment("0xabc")
        assert tracker.get_count("0xabc") == 3

    def test_separate_wallets(self):
        tracker = InteractionTracker()
        tracker.increment("0xabc")
        tracker.increment("0xdef")
        assert tracker.get_count("0xabc") == 1
        assert tracker.get_count("0xdef") == 1

    def test_get_all_counts(self):
        tracker = InteractionTracker()
        tracker.increment("0xabc")
        tracker.increment("0xdef")
        counts = tracker.get_all_counts()
        assert counts == {"0xabc": 1, "0xdef": 1}

    def test_untracked_wallet_returns_zero(self):
        tracker = InteractionTracker()
        assert tracker.get_count("0xunknown") == 0


# ── Eligibility scoring ───────────────────────────────────────────────────────

class TestEligibility:
    def test_empty_wallet_low_score(self, strategy, wallet):
        score = strategy.evaluate_eligibility(wallet)
        assert score < 0.3  # No activity = low score

    def test_active_wallet_higher_score(self, strategy):
        manager = WalletManager(simulate=True)
        wallet = manager.create_wallet("active-lender")
        wallet.record_activity("ethereum", "AaveV3", "deposit", gas_spent=0.01)
        wallet.record_activity("ethereum", "AaveV3", "borrow", gas_spent=0.005)
        wallet.record_activity("ethereum", "CompoundV3", "deposit", gas_spent=0.01)

        score = strategy.evaluate_eligibility(wallet)
        assert score > 0.1  # Should be higher than empty wallet

    def test_score_bounded_0_to_1(self, strategy, wallet):
        # Even with lots of activity, score should not exceed 1.0
        for _ in range(50):
            wallet.record_activity("ethereum", "AaveV3", "deposit", gas_spent=0.01)

        score = strategy.evaluate_eligibility(wallet)
        assert 0.0 <= score <= 1.0


# ── Protocol filtering ────────────────────────────────────────────────────────

class TestProtocolFiltering:
    def test_single_protocol_filter(self):
        strategy = LendingStrategy(protocol_name="AaveV3")
        wallet = WalletManager(simulate=True).create_wallet("test")
        actions = strategy.get_actions(wallet, "ethereum")
        protocols = {a.params["protocol"] for a in actions}
        assert protocols == {"AaveV3"}

    def test_unsupported_chain_returns_empty(self, strategy, wallet):
        actions = strategy.get_actions(wallet, "solana")
        assert actions == []

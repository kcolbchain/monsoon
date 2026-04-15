"""Integration tests for wallet rotation and cooldown logic (issue #7).

Tests the full WalletManager ↔ Wallet lifecycle:
- Round-robin rotation across available wallets
- Cooldown prevents wallet selection
- Cooldown expiry restores wallet to pool
- Activity recording and portfolio summary
- Edge cases: no wallets, all on cooldown, single wallet
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import patch
from src.agent.wallet_manager import Wallet, WalletActivity, WalletManager


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def manager():
    return WalletManager(simulate=True)


@pytest.fixture
def manager_with_wallets(manager):
    manager.create_wallet("alpha")
    manager.create_wallet("beta")
    manager.create_wallet("gamma")
    return manager


# ── Wallet rotation ───────────────────────────────────────────────────────────

class TestWalletRotation:
    def test_round_robin_cycles_through_wallets(self, manager_with_wallets):
        m = manager_with_wallets
        order = [m.get_next_wallet().label for _ in range(6)]
        assert order == ["alpha", "beta", "gamma", "alpha", "beta", "gamma"]

    def test_rotation_wraps_correctly(self, manager_with_wallets):
        m = manager_with_wallets
        first = m.get_next_wallet()
        second = m.get_next_wallet()
        third = m.get_next_wallet()
        fourth = m.get_next_wallet()

        # 4th call wraps back to first (3 wallets, round-robin)
        assert fourth.label == first.label  # alpha -> beta -> gamma -> alpha

    def test_single_wallet_rotation(self, manager):
        manager.create_wallet("only")
        w1 = manager.get_next_wallet()
        w2 = manager.get_next_wallet()
        assert w1.label == w2.label == "only"

    def test_no_wallets_returns_none(self, manager):
        assert manager.get_next_wallet() is None

    def test_rotation_skips_inactive_wallets(self, manager_with_wallets):
        m = manager_with_wallets
        m.wallets[1].active = False  # Deactivate "beta"
        order = [m.get_next_wallet().label for _ in range(4)]
        assert order == ["alpha", "gamma", "alpha", "gamma"]

    def test_rotation_skips_cooldown_wallets(self, manager_with_wallets):
        m = manager_with_wallets
        future = datetime.utcnow() + timedelta(hours=1)
        m.wallets[1].cooldown_until = future  # "beta" on cooldown
        order = [m.get_next_wallet().label for _ in range(4)]
        assert order == ["alpha", "gamma", "alpha", "gamma"]

    def test_rotation_with_all_on_cooldown_returns_none(self, manager_with_wallets):
        m = manager_with_wallets
        future = datetime.utcnow() + timedelta(hours=1)
        for w in m.wallets:
            w.cooldown_until = future
        assert m.get_next_wallet() is None


# ── Cooldown logic ────────────────────────────────────────────────────────────

class TestCooldownLogic:
    def test_wallet_not_on_cooldown_by_default(self, manager):
        wallet = manager.create_wallet("test")
        assert not wallet.is_on_cooldown

    def test_wallet_on_cooldown_until_future(self, manager):
        wallet = manager.create_wallet("test")
        wallet.cooldown_until = datetime.utcnow() + timedelta(hours=2)
        assert wallet.is_on_cooldown

    def test_wallet_cooldown_expires(self, manager):
        wallet = manager.create_wallet("test")
        wallet.cooldown_until = datetime.utcnow() - timedelta(seconds=1)
        assert not wallet.is_on_cooldown

    def test_cooldown_wallet_excluded_from_available(self, manager):
        wallet = manager.create_wallet("active")
        cooldown_wallet = manager.create_wallet("cooling")
        cooldown_wallet.cooldown_until = datetime.utcnow() + timedelta(hours=1)

        available = manager.get_available_wallets()
        assert len(available) == 1
        assert available[0].label == "active"

    def test_cooldown_expiry_restores_to_pool(self, manager):
        wallet = manager.create_wallet("test")
        wallet.cooldown_until = datetime.utcnow() - timedelta(seconds=1)  # Already expired
        available = manager.get_available_wallets()
        assert wallet in available

    def test_inactive_wallet_excluded_regardless_of_cooldown(self, manager):
        wallet = manager.create_wallet("test")
        wallet.active = False
        wallet.cooldown_until = None  # Not on cooldown
        available = manager.get_available_wallets()
        assert wallet not in available


# ── Activity recording ────────────────────────────────────────────────────────

class TestActivityRecording:
    def test_record_activity(self, manager):
        wallet = manager.create_wallet("test")
        wallet.record_activity("ethereum", "uniswap", "swap", tx_hash="0xabc", gas_spent=0.01)
        assert len(wallet.activity) == 1
        assert wallet.activity[0].protocol == "uniswap"
        assert wallet.activity[0].gas_spent == 0.01

    def test_total_gas_spent(self, manager):
        wallet = manager.create_wallet("test")
        wallet.record_activity("eth", "aave", "deposit", gas_spent=0.005)
        wallet.record_activity("eth", "compound", "supply", gas_spent=0.015)
        assert wallet.total_gas_spent == pytest.approx(0.02)

    def test_unique_protocols(self, manager):
        wallet = manager.create_wallet("test")
        wallet.record_activity("eth", "aave", "deposit")
        wallet.record_activity("eth", "aave", "withdraw")
        wallet.record_activity("eth", "compound", "supply")
        assert wallet.unique_protocols == {"aave", "compound"}

    def test_unique_days_active(self, manager):
        wallet = manager.create_wallet("test")
        wallet.record_activity("eth", "aave", "deposit")
        assert wallet.unique_days_active >= 1

    def test_multiple_wallets_activity(self, manager):
        w1 = manager.create_wallet("a")
        w2 = manager.create_wallet("b")
        w1.record_activity("eth", "uniswap", "swap", gas_spent=0.01)
        w2.record_activity("sol", "raydium", "swap", gas_spent=0.005)
        assert w1.total_gas_spent != w2.total_gas_spent


# ── Portfolio summary ─────────────────────────────────────────────────────────

class TestPortfolioSummary:
    def test_empty_manager_summary(self, manager):
        summary = manager.get_portfolio_summary()
        assert summary["total_wallets"] == 0
        assert summary["active"] == 0

    def test_summary_with_wallets(self, manager_with_wallets):
        summary = manager_with_wallets.get_portfolio_summary()
        assert summary["total_wallets"] == 3
        assert summary["active"] == 3
        assert summary["on_cooldown"] == 0

    def test_summary_with_cooldown(self, manager_with_wallets):
        m = manager_with_wallets
        m.wallets[0].cooldown_until = datetime.utcnow() + timedelta(hours=1)
        summary = m.get_portfolio_summary()
        assert summary["on_cooldown"] == 1
        assert summary["active"] == 3  # Still active, just cooling

    def test_summary_with_activities(self, manager_with_wallets):
        m = manager_with_wallets
        m.wallets[0].record_activity("eth", "uniswap", "swap", gas_spent=0.01)
        m.wallets[1].record_activity("eth", "aave", "deposit", gas_spent=0.005)
        summary = m.get_portfolio_summary()
        assert summary["total_activities"] == 2
        assert summary["unique_protocols"] == 2

    def test_summary_gas_spent(self, manager_with_wallets):
        m = manager_with_wallets
        m.wallets[0].record_activity("eth", "uniswap", "swap", gas_spent=0.01)
        summary = m.get_portfolio_summary()
        assert summary["total_gas_spent"] == pytest.approx(0.01)


# ── Wallet creation ───────────────────────────────────────────────────────────

class TestWalletCreation:
    def test_create_simulated_wallet(self, manager):
        wallet = manager.create_wallet("test")
        assert wallet.address.startswith("0x")
        assert wallet.label == "test"
        assert wallet.active is True
        assert wallet.private_key is None  # Simulated wallets don't have keys

    def test_import_wallet(self, manager):
        wallet = manager.import_wallet("imported", "0x1234567890abcdef" + "0" * 24)
        assert wallet.label == "imported"
        assert wallet in manager.wallets

    def test_add_wallet_object(self, manager):
        wallet = Wallet(address="0xabc", label="direct")
        result = manager.add_wallet(wallet)
        assert result.label == "direct"
        assert wallet in manager.wallets

    def test_get_wallet_by_label(self, manager_with_wallets):
        w = manager_with_wallets.get_wallet_by_label("beta")
        assert w is not None
        assert w.label == "beta"

    def test_get_wallet_by_label_not_found(self, manager_with_wallets):
        assert manager_with_wallets.get_wallet_by_label("nonexistent") is None

"""Tests for Rich-based TUI dashboard (issue #5)."""

import pytest
from datetime import datetime, timedelta
from rich.table import Table
from rich.panel import Panel

from src.agent.wallet_manager import WalletManager, Wallet, WalletActivity
from src.agent.dashboard import (
    render_wallet_table,
    render_gas_by_chain,
    render_strategy_history,
    render_cooldown_panel,
    render_summary,
    render_dashboard,
)


@pytest.fixture
def manager_with_activity():
    manager = WalletManager(simulate=True)
    w1 = manager.create_wallet("alpha")
    w2 = manager.create_wallet("beta")

    w1.record_activity("ethereum", "uniswap", "swap", gas_spent=0.01)
    w1.record_activity("ethereum", "aave", "deposit", gas_spent=0.005)
    w1.record_activity("arbitrum", "camelot", "swap", gas_spent=0.003)

    w2.record_activity("ethereum", "compound", "supply", gas_spent=0.008)
    w2.record_activity("base", "aerodrome", "swap", gas_spent=0.002)

    return manager


@pytest.fixture
def manager_on_cooldown():
    manager = WalletManager(simulate=True)
    w1 = manager.create_wallet("cooling")
    w1.cooldown_until = datetime.utcnow() + timedelta(minutes=30)
    w1.record_activity("ethereum", "uniswap", "swap", gas_spent=0.01)
    return manager


# ── Wallet table ──────────────────────────────────────────────────────────────

class TestWalletTable:
    def test_renders_wallets(self, manager_with_activity):
        table = render_wallet_table(manager_with_activity)
        assert isinstance(table, Table)

    def test_empty_manager(self):
        table = render_wallet_table(WalletManager(simulate=True))
        assert isinstance(table, Table)

    def test_shows_activity_count(self, manager_with_activity):
        table = render_wallet_table(manager_with_activity)
        # Should have 2 data rows (alpha, beta)
        assert table.row_count == 2


# ── Gas by chain ───────────────────────────────────────────────────────────────

class TestGasByChain:
    def test_renders_gas_table(self, manager_with_activity):
        table = render_gas_by_chain(manager_with_activity)
        assert isinstance(table, Table)

    def test_empty_manager(self):
        table = render_gas_by_chain(WalletManager(simulate=True))
        assert isinstance(table, Table)

    def test_shows_multiple_chains(self, manager_with_activity):
        table = render_gas_by_chain(manager_with_activity)
        # ethereum, arbitrum, base = 3 chains
        assert table.row_count == 3


# ── Strategy history ───────────────────────────────────────────────────────────

class TestStrategyHistory:
    def test_renders_history(self, manager_with_activity):
        table = render_strategy_history(manager_with_activity)
        assert isinstance(table, Table)

    def test_empty_manager(self):
        table = render_strategy_history(WalletManager(simulate=True))
        assert isinstance(table, Table)

    def test_limited_to_20(self):
        manager = WalletManager(simulate=True)
        w = manager.create_wallet("busy")
        for i in range(30):
            w.record_activity("ethereum", "uniswap", "swap", gas_spent=0.001)
        table = render_strategy_history(manager)
        assert table.row_count == 20


# ── Cooldown panel ─────────────────────────────────────────────────────────────

class TestCooldownPanel:
    def test_no_cooldown(self):
        panel = render_cooldown_panel(WalletManager(simulate=True))
        assert isinstance(panel, Panel)

    def test_with_cooldown(self, manager_on_cooldown):
        panel = render_cooldown_panel(manager_on_cooldown)
        assert isinstance(panel, Panel)


# ── Summary ────────────────────────────────────────────────────────────────────

class TestSummary:
    def test_summary_panel(self, manager_with_activity):
        panel = render_summary(manager_with_activity)
        assert isinstance(panel, Panel)

    def test_empty_manager_summary(self):
        panel = render_summary(WalletManager(simulate=True))
        assert isinstance(panel, Panel)


# ── Full dashboard ─────────────────────────────────────────────────────────────

class TestFullDashboard:
    def test_dashboard_layout(self, manager_with_activity):
        from rich.layout import Layout
        layout = render_dashboard(manager_with_activity)
        assert isinstance(layout, Layout)

    def test_empty_dashboard(self):
        from rich.layout import Layout
        layout = render_dashboard(WalletManager(simulate=True))
        assert isinstance(layout, Layout)

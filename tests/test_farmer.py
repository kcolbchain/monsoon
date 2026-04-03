"""Tests for the farming agent."""

import pytest
from src.agent.wallet_manager import WalletManager, Wallet
from src.agent.farmer import FarmingAgent
from src.strategies.bridge_strategy import BridgeStrategy
from src.strategies.dex_strategy import DexStrategy


def test_wallet_creation():
    wm = WalletManager(simulate=True)
    w = wm.create_wallet("test-1")
    assert w.label == "test-1"
    assert w.active is True
    assert len(wm.wallets) == 1


def test_wallet_rotation():
    wm = WalletManager(simulate=True)
    wm.create_wallet("w1")
    wm.create_wallet("w2")
    wm.create_wallet("w3")

    first = wm.get_next_wallet()
    second = wm.get_next_wallet()
    third = wm.get_next_wallet()
    fourth = wm.get_next_wallet()

    assert first.label == "w1"
    assert second.label == "w2"
    assert third.label == "w3"
    assert fourth.label == "w1"  # wraps around


def test_wallet_activity_tracking():
    wm = WalletManager(simulate=True)
    w = wm.create_wallet("test")
    w.record_activity("arbitrum", "stargate", "Bridge 0.01 ETH", gas_spent=0.001)
    assert len(w.activity) == 1
    assert w.total_gas_spent == 0.001
    assert "stargate" in w.unique_protocols


def test_bridge_strategy_generates_actions():
    wm = WalletManager(simulate=True)
    w = wm.create_wallet("test")
    strategy = BridgeStrategy()
    actions = strategy.get_actions(w, "ethereum")
    assert len(actions) > 0
    assert all(a.action_type == "bridge" for a in actions)


def test_dex_strategy_generates_actions():
    wm = WalletManager(simulate=True)
    w = wm.create_wallet("test")
    strategy = DexStrategy()
    actions = strategy.get_actions(w, "arbitrum")
    assert len(actions) > 0


def test_farmer_runs_simulation():
    wm = WalletManager(simulate=True)
    for i in range(3):
        wm.create_wallet(f"sim-{i}")

    config = {"simulate": True, "min_delay_seconds": 0, "max_delay_seconds": 0,
              "wallet_cooldown_hours": 4, "max_actions_per_day": 100}
    agent = FarmingAgent(wm, config)
    agent.add_strategy(BridgeStrategy())
    agent.add_strategy(DexStrategy())
    agent.run(ticks=10)

    assert agent.total_actions > 0
    status = agent.get_status()
    assert status["total_actions"] > 0


def test_eligibility_scoring():
    wm = WalletManager(simulate=True)
    w = wm.create_wallet("scorer")
    strategy = BridgeStrategy()

    # No activity = low score
    assert strategy.evaluate_eligibility(w) == 0.0

    # Add some activity
    for i in range(10):
        w.record_activity("arbitrum", "stargate", "Bridge", gas_spent=0.01)
    score = strategy.evaluate_eligibility(w)
    assert score > 0

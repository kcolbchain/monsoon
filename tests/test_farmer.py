"""Tests for the farming agent."""

import pytest
from datetime import datetime, timedelta
from unittest.mock import patch

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


# Helper to count wallet activity for a specific day
def get_wallet_daily_activity_count(wallet: Wallet, current_time: datetime) -> int:
    today = current_time.date()
    return sum(1 for activity in wallet.activity if activity.timestamp.date() == today)


def test_farmer_wallet_cooldown_mechanics():
    wm = WalletManager(simulate=True)
    w1 = wm.create_wallet("w1")
    w2 = wm.create_wallet("w2")
    w3 = wm.create_wallet("w3")

    initial_time = datetime(2023, 1, 1, 10, 0, 0)
    cooldown_duration = timedelta(hours=1)
    max_actions_per_day = 1 # Set to 1 for quick cooldown triggering

    config = {
        "simulate": True,
        "min_delay_seconds": 0,
        "max_delay_seconds": 0,
        "wallet_cooldown_hours": cooldown_duration.total_seconds() / 3600, # agent config expects hours
        "max_actions_per_day": max_actions_per_day,
    }
    agent = FarmingAgent(wm, config)
    agent.add_strategy(BridgeStrategy())

    # Use patch to control datetime.utcnow for time-sensitive logic
    # This mock affects Wallet.record_activity and Wallet.is_on_cooldown
    with patch('src.agent.wallet_manager.datetime') as mock_wm_datetime:
        mock_wm_datetime.utcnow.return_value = initial_time
        # Set a side_effect to ensure other datetime methods (like timedelta arithmetic) work normally
        mock_wm_datetime.side_effect = lambda *args, **kw: datetime(*args, **kw)


        # --- Test: Cooldown triggers after N actions (N=1 here) ---

        # Tick 1: w1 performs 1 action, hits max_actions_per_day, goes on cooldown.
        agent.run(ticks=1)
        assert get_wallet_daily_activity_count(w1, initial_time) == 1
        assert w1.is_on_cooldown
        assert w1.cooldown_until == initial_time + cooldown_duration
        assert agent.total_actions == 1
        assert not w2.is_on_cooldown # w2 not yet acted
        assert not w3.is_on_cooldown # w3 not yet acted

        # --- Test: Cooled-down wallets are skipped ---

        # Tick 2: w1 is on cooldown. `wm.get_next_wallet()` should skip w1.
        # Next in logical rotation from available wallets is w2.
        agent.run(ticks=1)
        assert get_wallet_daily_activity_count(w2, initial_time) == 1
        assert w2.is_on_cooldown
        assert w2.cooldown_until == initial_time + cooldown_duration
        assert agent.total_actions == 2
        assert w1.is_on_cooldown # w1 still cooled down

        # Tick 3: w1, w2 are on cooldown. w3 should be picked.
        agent.run(ticks=1)
        assert get_wallet_daily_activity_count(w3, initial_time) == 1
        assert w3.is_on_cooldown
        assert w3.cooldown_until == initial_time + cooldown_duration
        assert agent.total_actions == 3
        assert w1.is_on_cooldown # w1 still cooled down
        assert w2.is_on_cooldown # w2 still cooled down

        # After 3 ticks, all wallets have performed 1 action and should be on cooldown.
        assert not wm.get_available_wallets() # No wallets should be available

        # Tick 4: No wallets available. Agent should perform no actions.
        agent.run(ticks=1)
        assert agent.total_actions == 3 # Total actions remains 3

        # --- Test: Wallets re-enter after expiry ---

        # Advance time past cooldown for all wallets
        new_time = initial_time + cooldown_duration + timedelta(minutes=1)
        mock_wm_datetime.utcnow.return_value = new_time
        mock_wm_datetime.now.return_value = new_time

        # All wallets should now be off cooldown
        assert not w1.is_on_cooldown
        assert not w2.is_on_cooldown
        assert not w3.is_on_cooldown
        assert len(wm.get_available_wallets()) == 3 # All wallets available again

        # Tick 5: w1 should be picked again.
        # Rotation index in WalletManager correctly wraps around the newly available wallets.
        agent.run(ticks=1)
        # Verify new activity recorded on the new "day" (due to time jump)
        assert get_wallet_daily_activity_count(w1, new_time) == 1
        assert len(w1.activity) == 2 # Total activity count increased
        assert w1.is_on_cooldown # w1 should go on cooldown again
        assert w1.cooldown_until == new_time + cooldown_duration
        assert agent.total_actions == 4

        # Tick 6: w1 is on cooldown. Next available in rotation is w2.
        agent.run(ticks=1)
        assert get_wallet_daily_activity_count(w2, new_time) == 1
        assert len(w2.activity) == 2
        assert w2.is_on_cooldown
        assert w2.cooldown_until == new_time + cooldown_duration
        assert agent.total_actions == 5

        # Tick 7: w1, w2 on cooldown. Next available in rotation is w3.
        agent.run(ticks=1)
        assert get_wallet_daily_activity_count(w3, new_time) == 1
        assert len(w3.activity) == 2
        assert w3.is_on_cooldown
        assert w3.cooldown_until == new_time + cooldown_duration
        assert agent.total_actions == 6

        assert not wm.get_available_wallets() # All wallets cooled down again

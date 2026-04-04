"""Comprehensive tests for the Aave V3 lending strategy and protocol interface."""

import pytest
from datetime import datetime, timedelta

from src.agent.wallet_manager import WalletManager, Wallet
from src.agent.farmer import FarmingAgent
from src.protocols.aave_v3 import (
    AaveV3Protocol,
    AAVE_V3_ADDRESSES,
    SUPPORTED_ASSETS,
    POOL_ABI,
    POOL_DATA_PROVIDER_ABI,
    ERC20_ABI,
    HealthReport,
    SupplyResult,
    WithdrawResult,
    BorrowResult,
)
from src.strategies.lending import (
    LendingStrategy,
    LendingSchedule,
    DEFAULT_ASSETS,
    DEFAULT_AMOUNT_RANGES,
)
from src.strategies.base_strategy import Action


# =====================================================================
# Fixtures
# =====================================================================

@pytest.fixture
def wallet_manager():
    wm = WalletManager(simulate=True)
    for i in range(3):
        wm.create_wallet(f"lend-{i+1}")
    return wm


@pytest.fixture
def strategy():
    return LendingStrategy(simulate=True)


@pytest.fixture
def fast_schedule():
    return LendingSchedule(
        deposit_interval_seconds=0,
        withdraw_interval_seconds=0,
        min_hold_seconds=0,
        jitter_pct=0.0,
    )


# =====================================================================
# AaveV3Protocol — unit tests
# =====================================================================

class TestAaveV3Protocol:

    def test_create_simulated_protocol(self):
        proto = AaveV3Protocol("ethereum", simulate=True)
        assert proto.chain == "ethereum"
        assert proto.simulate is True

    def test_unsupported_chain_raises(self):
        with pytest.raises(ValueError, match="not available"):
            AaveV3Protocol("solana", simulate=True)

    def test_supported_chains_listed(self):
        assert "ethereum" in AaveV3Protocol.SUPPORTED_CHAINS
        assert "arbitrum" in AaveV3Protocol.SUPPORTED_CHAINS
        assert len(AaveV3Protocol.SUPPORTED_CHAINS) >= 4

    def test_get_supported_assets(self):
        proto = AaveV3Protocol("ethereum", simulate=True)
        assets = proto.get_supported_assets()
        assert "USDC" in assets
        assert "WETH" in assets

    def test_resolve_asset_known(self):
        proto = AaveV3Protocol("ethereum", simulate=True)
        addr = proto.resolve_asset("USDC")
        assert addr.startswith("0x")

    def test_resolve_asset_unknown_raises(self):
        proto = AaveV3Protocol("ethereum", simulate=True)
        with pytest.raises(ValueError, match="not supported"):
            proto.resolve_asset("SHIB")

    def test_simulate_supply(self):
        proto = AaveV3Protocol("arbitrum", simulate=True)
        result = proto.supply("0x" + "a1" * 20, "USDC", 100.0)
        assert result.success is True
        assert result.simulated is True
        assert result.tx_hash.startswith("0x")
        assert result.asset == "USDC"
        assert result.amount == 100.0
        assert result.chain == "arbitrum"

    def test_simulate_withdraw(self):
        proto = AaveV3Protocol("optimism", simulate=True)
        result = proto.withdraw("0x" + "b2" * 20, "DAI", 50.0)
        assert result.success is True
        assert result.simulated is True
        assert result.asset == "DAI"

    def test_simulate_borrow(self):
        proto = AaveV3Protocol("polygon", simulate=True)
        result = proto.borrow("0x" + "c3" * 20, "USDT", 200.0)
        assert result.success is True
        assert result.simulated is True
        assert result.interest_rate_mode == 2

    def test_health_factor_simulation(self):
        proto = AaveV3Protocol("ethereum", simulate=True)
        report = proto.get_health_factor("0x" + "d4" * 20)
        assert isinstance(report, HealthReport)
        assert report.is_safe is True
        assert report.health_factor == float("inf")

    def test_health_report_unsafe(self):
        report = HealthReport(
            total_collateral_usd=1000, total_debt_usd=900,
            available_borrows_usd=10, ltv=0.8,
            liquidation_threshold=0.85, health_factor=1.1,
        )
        assert report.is_safe is False

    def test_pool_abi_has_supply(self):
        names = {entry["name"] for entry in POOL_ABI}
        assert "supply" in names
        assert "withdraw" in names
        assert "getUserAccountData" in names

    def test_pool_data_provider_abi(self):
        names = {entry["name"] for entry in POOL_DATA_PROVIDER_ABI}
        assert "getUserReserveData" in names
        assert "getReserveData" in names

    def test_erc20_abi(self):
        names = {entry["name"] for entry in ERC20_ABI}
        assert "approve" in names
        assert "balanceOf" in names


# =====================================================================
# LendingStrategy — unit tests
# =====================================================================

class TestLendingStrategy:

    def test_strategy_name_and_weight(self, strategy):
        assert strategy.name == "lending"
        assert strategy.weight == 1.2

    def test_supported_chains(self, strategy):
        assert "ethereum" in strategy.supported_chains
        assert "arbitrum" in strategy.supported_chains

    def test_default_assets(self, strategy):
        assert set(strategy.assets) == {"USDC", "USDT", "WETH", "DAI"}

    def test_get_actions_deposit(self, wallet_manager, fast_schedule):
        strategy = LendingStrategy(simulate=True, schedule=fast_schedule)
        wallet = wallet_manager.wallets[0]
        actions = strategy.get_actions(wallet, "ethereum")
        assert len(actions) >= 1
        deposit_actions = [a for a in actions if a.action_type == "deposit"]
        assert len(deposit_actions) == 1
        assert deposit_actions[0].protocol == "aave_v3"

    def test_get_actions_unsupported_chain(self, wallet_manager, strategy):
        actions = strategy.get_actions(wallet_manager.wallets[0], "solana")
        assert actions == []

    def test_execute_deposit(self, wallet_manager, fast_schedule):
        strategy = LendingStrategy(simulate=True, schedule=fast_schedule)
        wallet = wallet_manager.wallets[0]
        action = Action(
            description="Supply 100 USDC to Aave V3",
            protocol="aave_v3",
            action_type="deposit",
            params={"asset": "USDC", "amount": 100.0,
                    "chain": "ethereum", "wallet": wallet.address},
        )
        result = strategy.execute(wallet, "ethereum", action)
        assert result["success"] is True
        assert result["simulated"] is True
        assert result["tx_hash"].startswith("0x")

    def test_execute_withdraw(self, wallet_manager, fast_schedule):
        strategy = LendingStrategy(simulate=True, schedule=fast_schedule)
        wallet = wallet_manager.wallets[0]

        # First deposit so there's something to withdraw
        dep_action = Action(
            description="Supply 50 DAI to Aave V3",
            protocol="aave_v3", action_type="deposit",
            params={"asset": "DAI", "amount": 50.0,
                    "chain": "ethereum", "wallet": wallet.address},
        )
        strategy.execute(wallet, "ethereum", dep_action)

        # Now withdraw
        wd_action = Action(
            description="Withdraw 50 DAI from Aave V3",
            protocol="aave_v3", action_type="withdraw",
            params={"asset": "DAI", "amount": 50.0,
                    "chain": "ethereum", "wallet": wallet.address},
        )
        result = strategy.execute(wallet, "ethereum", wd_action)
        assert result["success"] is True

    def test_interaction_count_increments(self, wallet_manager, fast_schedule):
        strategy = LendingStrategy(simulate=True, schedule=fast_schedule)
        wallet = wallet_manager.wallets[0]
        addr = wallet.address

        assert strategy.get_interaction_count(addr) == 0

        action = Action(
            description="Supply 100 USDC",
            protocol="aave_v3", action_type="deposit",
            params={"asset": "USDC", "amount": 100.0,
                    "chain": "ethereum", "wallet": addr},
        )
        strategy.execute(wallet, "ethereum", action)
        assert strategy.get_interaction_count(addr) == 1

        strategy.execute(wallet, "ethereum", action)
        assert strategy.get_interaction_count(addr) == 2

    def test_interaction_count_per_wallet(self, wallet_manager, fast_schedule):
        strategy = LendingStrategy(simulate=True, schedule=fast_schedule)
        w1, w2 = wallet_manager.wallets[0], wallet_manager.wallets[1]

        action1 = Action(
            description="Supply 100 USDC",
            protocol="aave_v3", action_type="deposit",
            params={"asset": "USDC", "amount": 100.0,
                    "chain": "ethereum", "wallet": w1.address},
        )
        action2 = Action(
            description="Supply 200 USDT",
            protocol="aave_v3", action_type="deposit",
            params={"asset": "USDT", "amount": 200.0,
                    "chain": "ethereum", "wallet": w2.address},
        )
        strategy.execute(w1, "ethereum", action1)
        strategy.execute(w1, "ethereum", action1)
        strategy.execute(w2, "ethereum", action2)

        counts = strategy.get_all_interaction_counts()
        assert counts[w1.address] == 2
        assert counts[w2.address] == 1

    def test_active_deposits_tracked(self, wallet_manager, fast_schedule):
        strategy = LendingStrategy(simulate=True, schedule=fast_schedule)
        wallet = wallet_manager.wallets[0]

        action = Action(
            description="Supply 100 USDC",
            protocol="aave_v3", action_type="deposit",
            params={"asset": "USDC", "amount": 100.0,
                    "chain": "ethereum", "wallet": wallet.address},
        )
        strategy.execute(wallet, "ethereum", action)

        deposits = strategy.get_active_deposits(wallet.address)
        assert len(deposits) == 1
        assert deposits[0]["asset"] == "USDC"
        assert deposits[0]["amount"] == 100.0

    def test_withdraw_removes_active_deposit(self, wallet_manager, fast_schedule):
        strategy = LendingStrategy(simulate=True, schedule=fast_schedule)
        wallet = wallet_manager.wallets[0]

        dep = Action(description="Supply", protocol="aave_v3",
                     action_type="deposit",
                     params={"asset": "WETH", "amount": 0.05,
                             "chain": "arbitrum", "wallet": wallet.address})
        strategy.execute(wallet, "arbitrum", dep)
        assert len(strategy.get_active_deposits(wallet.address)) == 1

        wd = Action(description="Withdraw", protocol="aave_v3",
                    action_type="withdraw",
                    params={"asset": "WETH", "amount": 0.05,
                            "chain": "arbitrum", "wallet": wallet.address})
        strategy.execute(wallet, "arbitrum", wd)
        assert len(strategy.get_active_deposits(wallet.address)) == 0

    def test_schedule_blocks_rapid_deposit(self, wallet_manager):
        schedule = LendingSchedule(
            deposit_interval_seconds=9999,
            withdraw_interval_seconds=9999,
            min_hold_seconds=0,
            jitter_pct=0.0,
        )
        strategy = LendingStrategy(simulate=True, schedule=schedule)
        wallet = wallet_manager.wallets[0]

        # First call should produce a deposit action
        actions1 = strategy.get_actions(wallet, "ethereum")
        deposits1 = [a for a in actions1 if a.action_type == "deposit"]
        assert len(deposits1) == 1

        # Simulate executing the deposit to record the timestamp
        strategy.execute(wallet, "ethereum", deposits1[0])

        # Second call should NOT produce a deposit (interval not elapsed)
        actions2 = strategy.get_actions(wallet, "ethereum")
        deposits2 = [a for a in actions2 if a.action_type == "deposit"]
        assert len(deposits2) == 0

    def test_withdraw_appears_after_hold(self, wallet_manager):
        schedule = LendingSchedule(
            deposit_interval_seconds=0,
            withdraw_interval_seconds=0,
            min_hold_seconds=0,
            jitter_pct=0.0,
        )
        strategy = LendingStrategy(simulate=True, schedule=schedule)
        wallet = wallet_manager.wallets[0]

        # Deposit first
        actions = strategy.get_actions(wallet, "ethereum")
        dep = [a for a in actions if a.action_type == "deposit"][0]
        strategy.execute(wallet, "ethereum", dep)

        # Now get_actions should include withdraw
        actions2 = strategy.get_actions(wallet, "ethereum")
        wds = [a for a in actions2 if a.action_type == "withdraw"]
        assert len(wds) == 1

    def test_eligibility_zero_for_new_wallet(self, wallet_manager, strategy):
        wallet = wallet_manager.wallets[0]
        score = strategy.evaluate_eligibility(wallet)
        assert score == 0.0

    def test_eligibility_increases_with_interactions(self, wallet_manager, fast_schedule):
        strategy = LendingStrategy(simulate=True, schedule=fast_schedule)
        wallet = wallet_manager.wallets[0]

        for _ in range(10):
            action = Action(description="Supply", protocol="aave_v3",
                            action_type="deposit",
                            params={"asset": "USDC", "amount": 100.0,
                                    "chain": "ethereum", "wallet": wallet.address})
            strategy.execute(wallet, "ethereum", action)

        score = strategy.evaluate_eligibility(wallet)
        assert score > 0.0

    def test_health_check_passes_in_simulation(self, strategy):
        assert strategy.check_health("0x" + "aa" * 20, "ethereum") is True

    def test_execute_invalid_action_type_raises(self, wallet_manager, fast_schedule):
        strategy = LendingStrategy(simulate=True, schedule=fast_schedule)
        wallet = wallet_manager.wallets[0]
        bad = Action(description="bad", protocol="aave_v3",
                     action_type="swap",
                     params={"asset": "USDC", "amount": 10.0,
                             "chain": "ethereum", "wallet": wallet.address})
        with pytest.raises(ValueError, match="Unsupported action"):
            strategy.execute(wallet, "ethereum", bad)

    def test_custom_assets_and_ranges(self, wallet_manager):
        schedule = LendingSchedule(
            deposit_interval_seconds=0, withdraw_interval_seconds=0,
            min_hold_seconds=0, jitter_pct=0.0,
        )
        strategy = LendingStrategy(
            simulate=True,
            assets=["WETH"],
            amount_ranges={"WETH": (0.01, 0.02)},
            schedule=schedule,
        )
        wallet = wallet_manager.wallets[0]
        actions = strategy.get_actions(wallet, "ethereum")
        dep = [a for a in actions if a.action_type == "deposit"]
        assert len(dep) == 1
        assert dep[0].params["asset"] == "WETH"
        assert 0.01 <= dep[0].params["amount"] <= 0.02

    def test_multiple_chains(self, wallet_manager, fast_schedule):
        strategy = LendingStrategy(simulate=True, schedule=fast_schedule)
        wallet = wallet_manager.wallets[0]

        for chain in ["ethereum", "arbitrum", "optimism"]:
            actions = strategy.get_actions(wallet, chain)
            assert len(actions) >= 1, f"No actions on {chain}"


# =====================================================================
# Integration with FarmingAgent
# =====================================================================

class TestLendingFarmingIntegration:

    def test_farming_agent_with_lending(self, wallet_manager):
        config = {
            "simulate": True,
            "min_delay_seconds": 0,
            "max_delay_seconds": 0,
            "wallet_cooldown_hours": 24,
            "max_actions_per_day": 100,
        }
        agent = FarmingAgent(wallet_manager, config)

        schedule = LendingSchedule(
            deposit_interval_seconds=0, withdraw_interval_seconds=0,
            min_hold_seconds=0, jitter_pct=0.0,
        )
        strategy = LendingStrategy(simulate=True, schedule=schedule)
        agent.add_strategy(strategy)
        agent.run(ticks=10)

        assert agent.total_actions > 0
        status = agent.get_status()
        assert "lending" in status["strategies"]

    def test_wallet_rotation_distributes(self, wallet_manager):
        config = {
            "simulate": True,
            "min_delay_seconds": 0,
            "max_delay_seconds": 0,
            "wallet_cooldown_hours": 24,
            "max_actions_per_day": 100,
        }
        agent = FarmingAgent(wallet_manager, config)
        schedule = LendingSchedule(
            deposit_interval_seconds=0, withdraw_interval_seconds=0,
            min_hold_seconds=0, jitter_pct=0.0,
        )
        strategy = LendingStrategy(simulate=True, schedule=schedule)
        agent.add_strategy(strategy)
        agent.run(ticks=9)

        # With 3 wallets and 9 ticks, each wallet should be selected ~3 times
        wallets_used = {w.label for w in wallet_manager.wallets if len(w.activity) > 0}
        assert len(wallets_used) >= 2  # at least 2 wallets were used

    def test_mixed_strategies(self, wallet_manager):
        from src.strategies.bridge_strategy import BridgeStrategy
        from src.strategies.dex_strategy import DexStrategy

        config = {
            "simulate": True,
            "min_delay_seconds": 0,
            "max_delay_seconds": 0,
            "wallet_cooldown_hours": 24,
            "max_actions_per_day": 100,
        }
        agent = FarmingAgent(wallet_manager, config)
        schedule = LendingSchedule(
            deposit_interval_seconds=0, withdraw_interval_seconds=0,
            min_hold_seconds=0, jitter_pct=0.0,
        )
        agent.add_strategy(BridgeStrategy())
        agent.add_strategy(DexStrategy())
        agent.add_strategy(LendingStrategy(simulate=True, schedule=schedule))

        agent.run(ticks=20)
        assert agent.total_actions > 0


# =====================================================================
# Edge cases
# =====================================================================

class TestEdgeCases:

    def test_supply_result_dataclass(self):
        r = SupplyResult(success=True, tx_hash="0xabc", asset="USDC",
                         amount=100.0, chain="ethereum")
        assert r.simulated is True
        assert r.error is None

    def test_withdraw_result_dataclass(self):
        r = WithdrawResult(success=False, error="insufficient balance",
                           asset="WETH", amount=1.0, chain="arbitrum")
        assert r.success is False
        assert "insufficient" in r.error

    def test_borrow_result_dataclass(self):
        r = BorrowResult(success=True, interest_rate_mode=1, asset="DAI",
                         amount=500.0, chain="polygon")
        assert r.interest_rate_mode == 1

    def test_base_chain_limited_assets(self):
        proto = AaveV3Protocol("base", simulate=True)
        assets = proto.get_supported_assets()
        assert "USDC" in assets
        assert "WETH" in assets
        # Base doesn't have USDT in our mapping
        assert "USDT" not in assets

    def test_lending_strategy_filters_unavailable_assets(self):
        schedule = LendingSchedule(
            deposit_interval_seconds=0, withdraw_interval_seconds=0,
            min_hold_seconds=0, jitter_pct=0.0,
        )
        strategy = LendingStrategy(simulate=True, schedule=schedule)
        wm = WalletManager(simulate=True)
        w = wm.create_wallet("base-test")
        actions = strategy.get_actions(w, "base")
        # Should only produce actions for assets available on Base
        for a in actions:
            if a.action_type == "deposit":
                assert a.params["asset"] in SUPPORTED_ASSETS["base"]

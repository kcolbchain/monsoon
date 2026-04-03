"""Core farming agent — orchestrates strategies across wallets and chains."""

import logging
import random
import time
from datetime import datetime, timedelta
from typing import Optional

import click

from .wallet_manager import WalletManager, Wallet
from ..strategies.base_strategy import BaseStrategy, Action

logger = logging.getLogger(__name__)


class FarmingAgent:
    """Autonomous agent that executes farming strategies across wallets."""

    def __init__(self, wallet_manager: WalletManager, config: dict):
        self.wm = wallet_manager
        self.config = config
        self.strategies: list[BaseStrategy] = []
        self.is_running = False
        self.total_actions = 0
        self.errors: list[dict] = []

        # Timing config
        self.min_delay = config.get("min_delay_seconds", 30)
        self.max_delay = config.get("max_delay_seconds", 300)
        self.cooldown_hours = config.get("wallet_cooldown_hours", 4)
        self.max_actions_per_wallet_per_day = config.get("max_actions_per_day", 10)

    def add_strategy(self, strategy: BaseStrategy):
        self.strategies.append(strategy)
        logger.info(f"Added strategy: {strategy.name}")

    def run(self, ticks: int = 10):
        """Run the farming loop for N ticks."""
        self.is_running = True
        logger.info(f"Starting farming agent — {len(self.strategies)} strategies, "
                     f"{len(self.wm.wallets)} wallets, {ticks} ticks")

        for tick in range(ticks):
            if not self.is_running:
                break

            wallet = self.wm.get_next_wallet()
            if wallet is None:
                logger.warning("No available wallets — all on cooldown")
                continue

            strategy = self._pick_strategy()
            if strategy is None:
                continue

            self._execute_tick(wallet, strategy, tick)

            # Random delay between actions
            delay = random.uniform(self.min_delay, self.max_delay)
            logger.debug(f"Sleeping {delay:.0f}s before next tick")
            if not self.config.get("simulate", True):
                time.sleep(delay)

        self.is_running = False
        logger.info(f"Farming complete — {self.total_actions} actions executed")

    def _pick_strategy(self) -> Optional[BaseStrategy]:
        """Weighted random strategy selection."""
        if not self.strategies:
            return None
        weights = [s.weight for s in self.strategies]
        return random.choices(self.strategies, weights=weights, k=1)[0]

    def _execute_tick(self, wallet: Wallet, strategy: BaseStrategy, tick: int):
        """Execute one farming tick — get actions and run them."""
        chain = random.choice(strategy.supported_chains)

        try:
            actions = strategy.get_actions(wallet, chain)
            if not actions:
                logger.debug(f"Tick {tick}: no actions for {wallet.label} on {chain}")
                return

            # Pick one action (don't spam)
            action = random.choice(actions)
            logger.info(f"Tick {tick}: {wallet.label} | {chain} | "
                        f"{strategy.name} | {action.description}")

            result = strategy.execute(wallet, chain, action)

            wallet.record_activity(
                chain=chain,
                protocol=strategy.name,
                action=action.description,
                tx_hash=result.get("tx_hash"),
                gas_spent=result.get("gas_spent", 0),
            )
            self.total_actions += 1

            # Apply cooldown if wallet hit daily limit
            today_actions = sum(
                1 for a in wallet.activity
                if a.timestamp.date() == datetime.utcnow().date()
            )
            if today_actions >= self.max_actions_per_wallet_per_day:
                wallet.cooldown_until = datetime.utcnow() + timedelta(hours=self.cooldown_hours)
                logger.info(f"Wallet {wallet.label} hit daily limit — cooldown until {wallet.cooldown_until}")

        except Exception as e:
            logger.error(f"Tick {tick} error: {e}")
            self.errors.append({
                "tick": tick, "wallet": wallet.label,
                "strategy": strategy.name, "error": str(e),
                "timestamp": datetime.utcnow().isoformat(),
            })

    def get_status(self) -> dict:
        return {
            "running": self.is_running,
            "strategies": [s.name for s in self.strategies],
            "total_actions": self.total_actions,
            "errors": len(self.errors),
            **self.wm.get_portfolio_summary(),
        }


@click.command()
@click.option("--simulate", is_flag=True, default=True, help="Run in simulation mode")
@click.option("--wallets", default=5, help="Number of wallets to create")
@click.option("--ticks", default=20, help="Number of farming ticks")
@click.option("--strategy", default="all", help="Strategy to run: bridge, dex, all")
def main(simulate, wallets, ticks, strategy):
    """Run the airdrop farming agent."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(message)s", datefmt="%H:%M:%S")

    wm = WalletManager(simulate=simulate)
    for i in range(wallets):
        wm.create_wallet(f"farmer-{i+1}")

    config = {"simulate": simulate, "min_delay_seconds": 1, "max_delay_seconds": 3,
              "wallet_cooldown_hours": 4, "max_actions_per_day": 10}
    agent = FarmingAgent(wm, config)

    from ..strategies.bridge_strategy import BridgeStrategy
    from ..strategies.dex_strategy import DexStrategy

    if strategy in ("bridge", "all"):
        agent.add_strategy(BridgeStrategy())
    if strategy in ("dex", "all"):
        agent.add_strategy(DexStrategy())

    agent.run(ticks=ticks)

    status = agent.get_status()
    click.echo(f"\n--- Results ---")
    for k, v in status.items():
        click.echo(f"  {k}: {v}")


if __name__ == "__main__":
    main()

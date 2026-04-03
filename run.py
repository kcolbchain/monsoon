#!/usr/bin/env python3
"""
kcolbchain airdrop-agents runner.

Usage:
    python run.py                          # simulate mode (default config)
    python run.py --config config/live.yaml  # live mode
    python run.py --ticks 5 --simulate     # 5 ticks, simulate only
"""
import argparse
import logging
import os
import yaml
from pathlib import Path

from src.agent.farmer import FarmingAgent
from src.agent.wallet_manager import WalletManager, Wallet
from src.strategies.bridge_strategy import BridgeStrategy
from src.strategies.dex_strategy import DexStrategy


def load_config(path: str) -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


def setup_wallets(config: dict) -> WalletManager:
    wm = WalletManager()
    wallets_cfg = config.get("wallets", [])

    for i, w in enumerate(wallets_cfg):
        env_key = f"WALLET_{i+1}_KEY"
        pk = os.environ.get(env_key)
        if not pk:
            logging.warning(f"No private key for {w.get('label', f'wallet-{i}')} "
                          f"(set {env_key} env var). Skipping.")
            continue

        from eth_account import Account
        acct = Account.from_key(pk)
        wallet = Wallet(
            address=acct.address,
            label=w.get("label", f"wallet-{i}"),
            private_key=pk,
        )
        wm.add_wallet(wallet)
        logging.info(f"Loaded wallet: {wallet.label} ({wallet.address[:8]}...)")

    return wm


def setup_strategies(config: dict) -> list:
    strategies = []
    strat_cfg = config.get("strategies", {})
    chains_cfg = config.get("chains", {})
    chain_names = list(chains_cfg.keys())

    if strat_cfg.get("bridge", {}).get("enabled"):
        s = BridgeStrategy(
            supported_chains=chain_names,
            weight=strat_cfg["bridge"].get("weight", 3),
        )
        strategies.append(s)

    if strat_cfg.get("dex", {}).get("enabled"):
        s = DexStrategy(
            supported_chains=chain_names,
            weight=strat_cfg["dex"].get("weight", 5),
        )
        strategies.append(s)

    return strategies


def main():
    parser = argparse.ArgumentParser(description="kcolbchain airdrop farming agent")
    parser.add_argument("--config", default="config/default.yaml", help="Config file path")
    parser.add_argument("--ticks", type=int, default=10, help="Number of action ticks")
    parser.add_argument("--simulate", action="store_true", help="Force simulation mode")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-8s [%(name)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    config = load_config(args.config)
    if args.simulate:
        config.setdefault("agent", {})["simulate"] = True

    agent_cfg = config.get("agent", {})
    wm = setup_wallets(config)

    if len(wm.wallets) == 0:
        logging.error("No wallets loaded. Set WALLET_1_KEY env var.")
        logging.info("Running in simulate mode with dummy wallet...")
        agent_cfg["simulate"] = True
        dummy = Wallet(address="0x" + "0" * 40, label="simulate-dummy")
        wm.add_wallet(dummy)

    agent = FarmingAgent(wm, agent_cfg)

    for strategy in setup_strategies(config):
        agent.add_strategy(strategy)

    mode = "SIMULATE" if agent_cfg.get("simulate", True) else "LIVE"
    logging.info(f"=== kcolbchain airdrop-agents [{mode}] ===")
    logging.info(f"Wallets: {len(wm.wallets)}, Strategies: {len(agent.strategies)}, Ticks: {args.ticks}")

    agent.run(ticks=args.ticks)


if __name__ == "__main__":
    main()

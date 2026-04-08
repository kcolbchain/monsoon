# monsoon

> Research scaffold for autonomous airdrop farming agents — multi-wallet, multi-chain, simulation-first.

By [kcolbchain](https://kcolbchain.com) (est. 2015).

**Documentation:** [docs.kcolbchain.com/monsoon](https://docs.kcolbchain.com/monsoon/)
**Powered by:** [kcolbchain/scout](https://github.com/kcolbchain/scout) for the registry, fit scoring, and wallet activity primitives.

## What this is

This repository is a **public research scaffold** for thinking about airdrop farming as a systems problem: wallet rotation, cooldowns, strategy plug-ins, eligibility scoring, and simulation mode for safe iteration.

It is **not** a turnkey production farmer:

- The strategy modules in `src/strategies/` build a representative *plan*, but execution is wired through `src.chains.evm.EVMConnector.simulate_transaction()` which always returns mock results.
- There is no signing, broadcasting, gas pricing, slippage protection, or error recovery in this repository.
- The `--simulate` flag is the only mode that exists today. Live mode is intentionally not implemented in the public scaffold.

For the *intelligence layer* (target registry, fit scoring, wallet activity tracking) used by the production agent, see **[kcolbchain/scout](https://github.com/kcolbchain/scout)** — it's a standalone library: `pip install scout-onchain`.

The kcolbchain operational agent that actually executes transactions is private. That repo lives separately and uses scout as a dependency.

## Why publish a scaffold?

Two reasons:

1. **Open science.** Thinking about airdrop farming as a structured systems problem (rotation, cooldowns, eligibility scoring) instead of opaque manual clicking is independently useful — for researchers, for grant narratives, and for operators reasoning about anti-sybil patterns.
2. **Substrate for scout.** The data model in this repo (Wallet, Activity, Target, Strategy) is the same one scout consumes. Publishing the scaffold makes the integration boundary explicit.

If you want to build your own farmer, fork this and add your own executor. The simulation harness gives you a safe place to iterate before any real funds are at stake.

## Quick start (simulation only)

```bash
git clone https://github.com/kcolbchain/monsoon.git
cd monsoon
pip install -r requirements.txt

# Simulation mode is the only mode this repo supports
python -m src.agent.farmer --simulate --strategy bridge
python run.py --config config/default.yaml --ticks 10 --simulate
python -m src.monitor.dashboard
```

For the intelligence side:

```bash
pip install scout-onchain
python -m scout targets
python -m scout get Linea
```

## Architecture (scaffold view)

```
┌─────────────────────────────────────┐
│          Farming Agent              │
│   (scheduling, rotation, cooldown)  │
├──────────┬──────────────────────────┤
│ Wallet   │      Strategies          │
│ Manager  │  (bridge, dex)           │
├──────────┴──────────────────────────┤
│   Chain Connectors (simulation)     │
├─────────────────────────────────────┤
│     Monitor / CLI Dashboard         │
└─────────────────────────────────────┘
            ▲
            │ uses
            │
┌─────────────────────────────────────┐
│  scout (separate package)           │
│  • Registry (curated targets)       │
│  • FitScorer (eligibility 0–100)    │
│  • WalletTracker (activity feeds)   │
└─────────────────────────────────────┘
```

## Supported chains (simulation chain configs)

| Chain | Chain ID |
|-------|----------|
| Ethereum | 1 |
| Arbitrum | 42161 |
| Optimism | 10 |
| Base | 8453 |
| BSC | 56 |
| Polygon | 137 |

## Project structure

```
src/
  agent/         — Farming agent loop and wallet manager
  chains/        — EVM chain connector (simulation only)
  strategies/    — Bridge and DEX strategy scaffolds
  monitor/       — CLI dashboard
config/          — Chain and protocol configs
tests/           — Test suite
```

## What's not in this repo

If you came here looking for any of these, they live elsewhere:

| Looking for | Where to go |
|---|---|
| Real on-chain execution | Not public — kcolbchain runs this privately |
| Target registry, criteria, fit scoring | [kcolbchain/scout](https://github.com/kcolbchain/scout) |
| Smart-money wallet tracking | [kcolbchain/scout](https://github.com/kcolbchain/scout) (`WalletTracker`) |
| Live signing / broadcasting | Not public |
| Browser-based dApp automation | Not public |
| Profit sweeping / treasury management | Not public |

## Disclaimer

This software is for educational and research purposes. Users are responsible for compliance with applicable laws and protocol terms of service. kcolbchain does not endorse sybil attacks or violations of protocol rules.

## Contributing

Issues and PRs that improve the *scaffold* — better documentation, additional strategy examples, more thoughtful wallet hygiene patterns, ideas for the data model — are welcome. Issues asking for live execution code or wallet keys will be closed.

For data contributions to the registry (new targets, alpha wallets, contract identifications), open a PR against [kcolbchain/scout](https://github.com/kcolbchain/scout) instead.

## License

MIT — see [LICENSE](LICENSE)

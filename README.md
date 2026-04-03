# monsoon

Autonomous airdrop farming agent framework — multi-wallet, multi-chain, strategy-driven. By [kcolbchain](https://kcolbchain.com) (est. 2015).

**Documentation:** [docs.kcolbchain.com/monsoon](https://docs.kcolbchain.com/monsoon/)

## Overview

Systematic airdrop farming using autonomous agents. Instead of manually interacting with protocols hoping for a drop, define strategies that agents execute across wallets and chains on autopilot.

- **Multi-wallet** — manage and rotate across multiple wallets
- **Multi-chain** — Ethereum, Arbitrum, Optimism, Base, BSC, Polygon
- **Strategy-driven** — pluggable strategies for bridges, DEXes, lending, social
- **Simulation mode** — test strategies without real transactions
- **Dashboard** — CLI monitor for wallet status, actions, eligibility scores

## Architecture

```
┌─────────────────────────────────────┐
│          Farming Agent              │
│   (scheduling, rotation, cooldown)  │
├──────────┬──────────────────────────┤
│ Wallet   │      Strategies          │
│ Manager  │  (bridge, dex, lending)  │
├──────────┴──────────────────────────┤
│        Chain Connectors (EVM)       │
├─────────────────────────────────────┤
│     Monitor / CLI Dashboard         │
└─────────────────────────────────────┘
```

## Supported Chains

| Chain | Chain ID | Status |
|-------|----------|--------|
| Ethereum | 1 | Supported |
| Arbitrum | 42161 | Supported |
| Optimism | 10 | Supported |
| Base | 8453 | Supported |
| BSC | 56 | Supported |
| Polygon | 137 | Supported |

## Getting Started

```bash
git clone https://github.com/kcolbchain/monsoon.git
cd monsoon
pip install -r requirements.txt

# Run in simulation mode (no real txns)
python -m src.agent.farmer --simulate --strategy bridge

# Or use YAML config + env wallets (see config/default.yaml)
python run.py --config config/default.yaml --ticks 10 --simulate

# Monitor dashboard
python -m src.monitor.dashboard
```

## Writing Strategies

Extend `BaseStrategy` in `src/strategies/`:

```python
from src.strategies.base_strategy import BaseStrategy, Action

class MyStrategy(BaseStrategy):
    def get_actions(self, wallet, chain) -> list[Action]:
        # Define what actions to take
        ...

    def evaluate_eligibility(self, wallet) -> float:
        # Score 0-1 for airdrop eligibility
        ...
```

## Project Structure

```
src/
  agent/         — Core farming agent and wallet manager
  chains/        — EVM chain connectors
  strategies/    — Pluggable farming strategies
  monitor/       — CLI dashboard
config/          — Chain and protocol configs
tests/           — Test suite
```

## Disclaimer

This software is for educational and research purposes. Users are responsible for compliance with applicable laws and protocol terms of service. kcolbchain does not endorse sybil attacks or violations of protocol rules.

## Contributing

We welcome contributions. See open issues tagged `good-first-issue`.

## License

MIT — see [LICENSE](LICENSE)

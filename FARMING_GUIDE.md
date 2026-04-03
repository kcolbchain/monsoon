# Monsoon — Live Farming Guide

## Prerequisites

1. **Wallets:** Create 5-10 fresh wallets. Never reuse wallets from other activities.
2. **Funding:** Fund each with 0.05-0.1 ETH on Arbitrum, Optimism, and Base.
3. **RPCs:** Get private RPC URLs from Alchemy, Infura, or QuickNode. Free tiers work.
4. **Environment:** Copy `.env.example` to `.env` and fill in RPC URLs and wallet keys.

## Setup

```bash
cp .env.example .env
# Edit .env with your RPC URLs and wallet private keys

# Test in simulation mode first
python -m src.agent.farmer --config config/live.yaml --simulate --ticks 20

# When ready, edit config/live.yaml: set simulate: false
python -m src.agent.farmer --config config/live.yaml --ticks 50
```

## Target Protocols (Q2 2026)

### High Priority
| Protocol | Chain | Strategy | Why |
|----------|-------|----------|-----|
| LayerZero V2 | Multi-chain | Bridge (Stargate) | Season 2 active |
| Scroll | Scroll | Bridge + DEX | Marks program |
| Linea | Linea | Bridge + DEX | Surge program |

### Medium Priority
| Protocol | Chain | Strategy | Why |
|----------|-------|----------|-----|
| Base ecosystem | Base | DEX (Aerodrome) | Multiple pre-token protocols |
| zkSync Era | zkSync | Bridge + DEX | Ongoing distribution possible |
| Berachain | Berachain | DEX (BEX) | BGT farming, PoL |

## Wallet Hygiene

- Never transfer funds between farming wallets
- Each wallet should have unique activity patterns (Monsoon handles this)
- Keep wallets funded from different sources if possible
- Don't farm from wallets linked to your identity (ENS, known addresses)
- Minimum 2 months of activity before expecting any drop

## Monitoring

```bash
# Check wallet status and eligibility scores
python -m src.monitor.dashboard

# Export activity log
python -m src.monitor.dashboard --export csv
```

## Expected Timeline

- **Month 1-2:** Building activity history, unique days, protocol diversity
- **Month 3-4:** Most airdrops snapshot in this window
- **Month 4-6:** Claims start opening

## Cost Estimates

| Chain | Avg gas per action | Actions/day/wallet | Monthly cost/wallet |
|-------|-------------------|-------------------|-------------------|
| Arbitrum | $0.02-0.10 | 3-5 | $2-15 |
| Optimism | $0.01-0.05 | 3-5 | $1-8 |
| Base | $0.01-0.03 | 3-5 | $1-5 |
| **Total (5 wallets)** | | | **$20-140/month** |

Conservative ROI: $20-80K in drops against $100-500 in gas costs.

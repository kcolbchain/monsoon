"""Rich-based TUI dashboard for Monsoon farming agent.

Displays:
- Per-wallet activity counts
- Chain-by-chain gas spent
- Strategy execution history and cooldown timers
- Real-time refresh from agent event log

Issue #5: Build analytics dashboard with Rich/Textual TUI.
"""

import time
from datetime import datetime
from typing import Optional

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.layout import Layout
from rich.live import Live
from rich.text import Text
from rich.columns import Columns

from .wallet_manager import WalletManager

console = Console()


def render_wallet_table(manager: WalletManager) -> Table:
    """Render per-wallet activity counts table."""
    table = Table(title="👛 Wallet Activity", show_lines=True)
    table.add_column("Label", style="cyan", no_wrap=True)
    table.add_column("Address", style="dim", max_width=20)
    table.add_column("Active", justify="center")
    table.add_column("Cooldown", justify="center")
    table.add_column("Actions", justify="right", style="green")
    table.add_column("Gas Spent", justify="right", style="yellow")
    table.add_column("Protocols", justify="right", style="magenta")
    table.add_column("Days", justify="right", style="blue")

    for wallet in manager.wallets:
        active = "✅" if wallet.active else "❌"
        cooldown = "⏳" if wallet.is_on_cooldown else "—"
        if wallet.is_on_cooldown and wallet.cooldown_until:
            remaining = wallet.cooldown_until - datetime.utcnow()
            cooldown = f"⏳ {int(remaining.total_seconds() // 60)}m"

        addr_short = f"{wallet.address[:8]}...{wallet.address[-6:]}"
        protocols = ", ".join(wallet.unique_protocols) if wallet.unique_protocols else "—"
        gas = f"{wallet.total_gas_spent:.4f} ETH"

        table.add_row(
            wallet.label,
            addr_short,
            active,
            cooldown,
            str(len(wallet.activity)),
            gas,
            protocols,
            str(wallet.unique_days_active),
        )

    return table


def render_gas_by_chain(manager: WalletManager) -> Table:
    """Render chain-by-chain gas spent table."""
    table = Table(title="⛽ Gas by Chain", show_lines=True)
    table.add_column("Chain", style="cyan")
    table.add_column("Total Gas (ETH)", justify="right", style="yellow")
    table.add_column("Actions", justify="right", style="green")
    table.add_column("Wallets", justify="right", style="blue")

    chain_data: dict[str, dict] = {}
    for wallet in manager.wallets:
        for activity in wallet.activity:
            if activity.chain not in chain_data:
                chain_data[activity.chain] = {"gas": 0.0, "actions": 0, "wallets": set()}
            chain_data[activity.chain]["gas"] += activity.gas_spent
            chain_data[activity.chain]["actions"] += 1
            chain_data[activity.chain]["wallets"].add(wallet.label)

    if not chain_data:
        table.add_row("—", "0.0000", "0", "0")
    else:
        for chain, data in sorted(chain_data.items(), key=lambda x: x[1]["gas"], reverse=True):
            table.add_row(
                chain,
                f"{data['gas']:.4f}",
                str(data["actions"]),
                str(len(data["wallets"])),
            )

    return table


def render_strategy_history(manager: WalletManager) -> Table:
    """Render strategy execution history table."""
    table = Table(title="📋 Strategy History", show_lines=True)
    table.add_column("Time", style="dim", max_width=19)
    table.add_column("Wallet", style="cyan")
    table.add_column("Chain", style="blue")
    table.add_column("Protocol", style="magenta")
    table.add_column("Action", style="green")
    table.add_column("TX", style="dim", max_width=16)

    # Collect all activities across wallets, sorted by time (most recent first)
    all_activities = []
    for wallet in manager.wallets:
        for activity in wallet.activity:
            all_activities.append((wallet.label, activity))

    all_activities.sort(key=lambda x: x[1].timestamp, reverse=True)

    # Show last 20 actions
    for label, act in all_activities[:20]:
        time_str = act.timestamp.strftime("%Y-%m-%d %H:%M:%S")
        tx_short = (act.tx_hash or "—")[:16]
        table.add_row(time_str, label, act.chain, act.protocol, act.action, tx_short)

    if not all_activities:
        table.add_row("—", "—", "—", "—", "—", "—")

    return table


def render_cooldown_panel(manager: WalletManager) -> Panel:
    """Render cooldown timers panel."""
    cooldown_wallets = [w for w in manager.wallets if w.is_on_cooldown]

    if not cooldown_wallets:
        return Panel("✅ No wallets on cooldown", title="⏱️ Cooldown Timers", border_style="green")

    lines = []
    for wallet in cooldown_wallets:
        remaining = wallet.cooldown_until - datetime.utcnow()
        mins = int(remaining.total_seconds() // 60)
        secs = int(remaining.total_seconds() % 60)
        lines.append(f"[cyan]{wallet.label}[/] — {mins}m {secs}s remaining")

    content = "\n".join(lines)
    return Panel(content, title="⏱️ Cooldown Timers", border_style="yellow")


def render_summary(manager: WalletManager) -> Panel:
    """Render portfolio summary panel."""
    summary = manager.get_portfolio_summary()

    content = (
        f"[bold]Total wallets:[/] {summary['total_wallets']}  "
        f"[bold]Active:[/] {summary['active']}  "
        f"[bold]On cooldown:[/] {summary['on_cooldown']}\n"
        f"[bold]Total gas:[/] {summary['total_gas_spent']:.4f} ETH  "
        f"[bold]Activities:[/] {summary['total_activities']}  "
        f"[bold]Protocols:[/] {summary['unique_protocols']}"
    )

    return Panel(content, title="📊 Portfolio Summary", border_style="blue")


def render_dashboard(manager: WalletManager) -> Layout:
    """Render full dashboard layout."""
    layout = Layout()

    layout.split_column(
        Layout(name="summary", size=4),
        Layout(name="body"),
    )
    layout["body"].split_row(
        Layout(name="left"),
        Layout(name="right"),
    )

    layout["summary"].update(render_summary(manager))
    layout["left"].update(
        Columns([render_wallet_table(manager), render_gas_by_chain(manager)])
    )
    layout["right"].update(
        Columns([render_strategy_history(manager), render_cooldown_panel(manager)])
    )

    return layout


def run_dashboard(manager: WalletManager, refresh_interval: float = 5.0):
    """Run live dashboard with auto-refresh."""
    with Live(console=console, refresh_per_second=1, screen=True) as live:
        while True:
            layout = render_dashboard(manager)
            live.update(layout)
            time.sleep(refresh_interval)


def print_dashboard(manager: WalletManager):
    """Print a static snapshot of the dashboard (for testing/non-interactive use)."""
    console.print(render_summary(manager))
    console.print()
    console.print(render_wallet_table(manager))
    console.print()
    console.print(render_gas_by_chain(manager))
    console.print()
    console.print(render_strategy_history(manager))
    console.print()
    console.print(render_cooldown_panel(manager))

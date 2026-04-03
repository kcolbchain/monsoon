"""CLI dashboard for monitoring farming operations."""

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.layout import Layout

from ..agent.wallet_manager import WalletManager


def render_wallet_table(wm: WalletManager) -> Table:
    table = Table(title="Wallets", show_lines=True)
    table.add_column("Label", style="cyan")
    table.add_column("Address", style="dim")
    table.add_column("Activities", justify="right")
    table.add_column("Unique Days", justify="right")
    table.add_column("Protocols", justify="right")
    table.add_column("Gas Spent", justify="right", style="yellow")
    table.add_column("Status", style="bold")

    for w in wm.wallets:
        status = "[red]Cooldown[/]" if w.is_on_cooldown else "[green]Active[/]" if w.active else "[dim]Inactive[/]"
        table.add_row(
            w.label,
            f"{w.address[:10]}...{w.address[-6:]}",
            str(len(w.activity)),
            str(w.unique_days_active),
            str(len(w.unique_protocols)),
            f"{w.total_gas_spent:.4f}",
            status,
        )

    return table


def render_summary(wm: WalletManager) -> Panel:
    summary = wm.get_portfolio_summary()
    text = (
        f"Total Wallets: {summary['total_wallets']}\n"
        f"Active: {summary['active']} | Cooldown: {summary['on_cooldown']}\n"
        f"Total Activities: {summary['total_activities']}\n"
        f"Unique Protocols: {summary['unique_protocols']}\n"
        f"Total Gas Spent: {summary['total_gas_spent']:.4f}"
    )
    return Panel(text, title="Portfolio Summary", border_style="green")


def show_dashboard(wm: WalletManager):
    console = Console()
    console.print(render_summary(wm))
    console.print(render_wallet_table(wm))


if __name__ == "__main__":
    # Demo dashboard with mock data
    wm = WalletManager(simulate=True)
    for i in range(5):
        w = wm.create_wallet(f"farmer-{i+1}")
        for j in range(3):
            w.record_activity("arbitrum", "stargate", f"Bridge 0.01 ETH", gas_spent=0.0001)
            w.record_activity("optimism", "velodrome", f"Swap 0.05 ETH→USDC", gas_spent=0.00005)

    show_dashboard(wm)

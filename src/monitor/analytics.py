"""Per-wallet analytics, heatmaps, gas efficiency, and CSV export."""

import csv
import io
from collections import defaultdict
from datetime import datetime
from typing import Optional

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.columns import Columns

from ..agent.wallet_manager import WalletManager, Wallet
from ..scout.criteria import EligibilityChecker
from ..scout.tracker import AirdropTarget


# ── Eligibility across strategies ────────────────────────────────────

def wallet_eligibility_table(
    wm: WalletManager,
    targets: list[AirdropTarget],
    checker: Optional[EligibilityChecker] = None,
) -> Table:
    """Per-wallet eligibility score across all tracked targets."""
    checker = checker or EligibilityChecker()

    table = Table(title="Wallet Eligibility Matrix", show_lines=True)
    table.add_column("Wallet", style="cyan")
    for t in targets:
        table.add_column(t.name, justify="center")
    table.add_column("Avg", justify="right", style="bold yellow")

    for w in wm.wallets:
        scores = checker.check_all_targets(w, targets)
        score_map = {s.target: s.score for s in scores}
        cells = []
        for t in targets:
            s = score_map.get(t.name, 0)
            color = "green" if s >= 60 else "yellow" if s >= 30 else "red"
            cells.append(f"[{color}]{s:.0f}%[/{color}]")

        avg = sum(score_map.values()) / len(score_map) if score_map else 0
        table.add_row(w.label, *cells, f"{avg:.0f}%")

    return table


# ── Action heatmap ───────────────────────────────────────────────────

def _weekday_name(d: int) -> str:
    return ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"][d]


def action_heatmap(wallet: Wallet) -> Table:
    """Heatmap: actions per day-of-week × chain."""
    heat: dict[str, dict[int, int]] = defaultdict(lambda: defaultdict(int))
    for a in wallet.activity:
        heat[a.chain][a.timestamp.weekday()] += 1

    table = Table(title=f"Action Heatmap — {wallet.label}", show_lines=True)
    table.add_column("Chain", style="cyan")
    for d in range(7):
        table.add_column(_weekday_name(d), justify="center")
    table.add_column("Total", justify="right", style="bold")

    for chain in sorted(heat):
        row = []
        total = 0
        for d in range(7):
            count = heat[chain][d]
            total += count
            if count == 0:
                row.append("[dim]·[/dim]")
            elif count < 3:
                row.append(f"[yellow]{count}[/yellow]")
            else:
                row.append(f"[green bold]{count}[/green bold]")
        table.add_row(chain, *row, str(total))

    return table


def portfolio_heatmap(wm: WalletManager) -> Table:
    """Aggregate heatmap across all wallets."""
    heat: dict[str, dict[int, int]] = defaultdict(lambda: defaultdict(int))
    for w in wm.wallets:
        for a in w.activity:
            heat[a.chain][a.timestamp.weekday()] += 1

    table = Table(title="Portfolio Action Heatmap", show_lines=True)
    table.add_column("Chain", style="cyan")
    for d in range(7):
        table.add_column(_weekday_name(d), justify="center")
    table.add_column("Total", justify="right", style="bold")

    for chain in sorted(heat):
        row = []
        total = 0
        for d in range(7):
            count = heat[chain][d]
            total += count
            if count == 0:
                row.append("[dim]·[/dim]")
            elif count < 5:
                row.append(f"[yellow]{count}[/yellow]")
            else:
                row.append(f"[green bold]{count}[/green bold]")
        table.add_row(chain, *row, str(total))

    return table


# ── Gas efficiency ───────────────────────────────────────────────────

def gas_efficiency_table(wm: WalletManager) -> Table:
    """Gas efficiency metrics per wallet."""
    table = Table(title="Gas Efficiency", show_lines=True)
    table.add_column("Wallet", style="cyan")
    table.add_column("Total Gas", justify="right", style="yellow")
    table.add_column("Txn Count", justify="right")
    table.add_column("Avg Gas/Txn", justify="right")
    table.add_column("Protocols Hit", justify="right")
    table.add_column("Gas/Protocol", justify="right", style="bold")
    table.add_column("Efficiency", justify="center")

    for w in wm.wallets:
        txn_count = len(w.activity)
        total_gas = w.total_gas_spent
        avg_gas = total_gas / txn_count if txn_count else 0
        proto_count = len(w.unique_protocols)
        gas_per_proto = total_gas / proto_count if proto_count else 0

        # Efficiency rating
        if proto_count >= 3 and gas_per_proto < 0.001:
            eff = "[green]★★★[/green]"
        elif proto_count >= 2 and gas_per_proto < 0.005:
            eff = "[yellow]★★[/yellow]"
        else:
            eff = "[red]★[/red]"

        table.add_row(
            w.label,
            f"{total_gas:.6f}",
            str(txn_count),
            f"{avg_gas:.6f}",
            str(proto_count),
            f"{gas_per_proto:.6f}",
            eff,
        )

    return table


# ── CSV export ───────────────────────────────────────────────────────

def export_csv(wm: WalletManager, filepath: str):
    """Export all wallet analytics to CSV for spreadsheet analysis."""
    with open(filepath, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "wallet_label",
            "address",
            "active",
            "on_cooldown",
            "total_gas",
            "txn_count",
            "unique_days",
            "unique_protocols",
            "unique_chains",
            "avg_gas_per_txn",
            "gas_per_protocol",
        ])
        for w in wm.wallets:
            txn_count = len(w.activity)
            proto_count = len(w.unique_protocols)
            chain_count = len({a.chain for a in w.activity})
            avg_gas = w.total_gas_spent / txn_count if txn_count else 0
            gas_per_proto = w.total_gas_spent / proto_count if proto_count else 0

            writer.writerow([
                w.label,
                w.address,
                w.active,
                w.is_on_cooldown,
                f"{w.total_gas_spent:.6f}",
                txn_count,
                w.unique_days_active,
                proto_count,
                chain_count,
                f"{avg_gas:.6f}",
                f"{gas_per_proto:.6f}",
            ])

    return filepath


def export_csv_string(wm: WalletManager) -> str:
    """Return CSV as string (useful for tests / piping)."""
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "wallet_label", "address", "active", "txn_count",
        "total_gas", "unique_protocols", "unique_chains",
    ])
    for w in wm.wallets:
        writer.writerow([
            w.label, w.address, w.active, len(w.activity),
            f"{w.total_gas_spent:.6f}", len(w.unique_protocols),
            len({a.chain for a in w.activity}),
        ])
    return buf.getvalue()


# ── Full analytics dashboard ─────────────────────────────────────────

def show_analytics(wm: WalletManager, targets: Optional[list[AirdropTarget]] = None):
    """Render the full analytics dashboard."""
    console = Console()

    console.print()
    console.print(gas_efficiency_table(wm))
    console.print()
    console.print(portfolio_heatmap(wm))

    if targets:
        console.print()
        console.print(wallet_eligibility_table(wm, targets))

    console.print()
    console.print("[dim]Export: monsoon analytics --export wallet_analytics.csv[/dim]")

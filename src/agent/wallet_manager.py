"""Multi-wallet management for farming operations."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
from eth_account import Account
import logging

logger = logging.getLogger(__name__)


@dataclass
class WalletActivity:
    chain: str
    protocol: str
    action: str
    timestamp: datetime
    tx_hash: Optional[str] = None
    gas_spent: float = 0.0


@dataclass
class Wallet:
    address: str
    label: str
    private_key: Optional[str] = None  # never log this
    created_at: datetime = field(default_factory=datetime.utcnow)
    balances: dict[str, float] = field(default_factory=dict)  # chain -> native balance
    activity: list[WalletActivity] = field(default_factory=list)
    active: bool = True
    cooldown_until: Optional[datetime] = None

    @property
    def total_gas_spent(self) -> float:
        return sum(a.gas_spent for a in self.activity)

    @property
    def unique_days_active(self) -> int:
        dates = {a.timestamp.date() for a in self.activity}
        return len(dates)

    @property
    def unique_protocols(self) -> set[str]:
        return {a.protocol for a in self.activity}

    @property
    def is_on_cooldown(self) -> bool:
        if self.cooldown_until is None:
            return False
        return datetime.utcnow() < self.cooldown_until

    def record_activity(self, chain: str, protocol: str, action: str,
                        tx_hash: str = None, gas_spent: float = 0.0):
        self.activity.append(WalletActivity(
            chain=chain, protocol=protocol, action=action,
            timestamp=datetime.utcnow(), tx_hash=tx_hash, gas_spent=gas_spent,
        ))


class WalletManager:
    """Manage multiple wallets for farming operations."""

    def __init__(self, simulate: bool = True):
        self.wallets: list[Wallet] = []
        self.simulate = simulate
        self._rotation_index = 0

    def create_wallet(self, label: str) -> Wallet:
        if self.simulate:
            # Deterministic fake address for simulation
            addr = f"0x{label.encode().hex()[:40].ljust(40, '0')}"
            wallet = Wallet(address=addr, label=label)
        else:
            account = Account.create()
            wallet = Wallet(
                address=account.address,
                label=label,
                private_key=account.key.hex(),
            )
        self.wallets.append(wallet)
        logger.info(f"Created wallet '{label}': {wallet.address}")
        return wallet

    def import_wallet(self, label: str, address: str, private_key: str = None) -> Wallet:
        wallet = Wallet(address=address, label=label, private_key=private_key)
        self.wallets.append(wallet)
        logger.info(f"Imported wallet '{label}': {address}")
        return wallet

    def get_available_wallets(self) -> list[Wallet]:
        return [w for w in self.wallets if w.active and not w.is_on_cooldown]

    def get_next_wallet(self) -> Optional[Wallet]:
        """Round-robin wallet rotation."""
        available = self.get_available_wallets()
        if not available:
            return None
        wallet = available[self._rotation_index % len(available)]
        self._rotation_index += 1
        return wallet

    def get_wallet_by_label(self, label: str) -> Optional[Wallet]:
        for w in self.wallets:
            if w.label == label:
                return w
        return None

    def update_balance(self, wallet: Wallet, chain: str, balance: float):
        wallet.balances[chain] = balance

    def get_portfolio_summary(self) -> dict:
        return {
            "total_wallets": len(self.wallets),
            "active": len([w for w in self.wallets if w.active]),
            "on_cooldown": len([w for w in self.wallets if w.is_on_cooldown]),
            "total_gas_spent": sum(w.total_gas_spent for w in self.wallets),
            "total_activities": sum(len(w.activity) for w in self.wallets),
            "unique_protocols": len(set().union(*(w.unique_protocols for w in self.wallets))) if self.wallets else 0,
        }

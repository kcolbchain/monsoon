"""Solana chain connector — wallet management, SOL/SPL transfers, tx confirmation."""

import logging
import time
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

# Solana constants
LAMPORTS_PER_SOL = 1_000_000_000
DEFAULT_RPC_URL = "https://api.mainnet-beta.solana.com"
DEVNET_RPC_URL = "https://api.devnet.solana.com"
SPL_TOKEN_PROGRAM_ID = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"
ASSOCIATED_TOKEN_PROGRAM_ID = "ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL"
SYSTEM_PROGRAM_ID = "11111111111111111111111111111111"

# Confirmation levels
CONFIRMATION_FINALIZED = "finalized"
CONFIRMATION_CONFIRMED = "confirmed"
CONFIRMATION_PROCESSED = "processed"


@dataclass
class SolanaConfig:
    """Configuration for a Solana network endpoint."""
    name: str
    rpc_url: str
    ws_url: Optional[str] = None
    explorer_url: str = "https://solscan.io"
    native_token: str = "SOL"
    is_devnet: bool = False


SOLANA_NETWORKS: dict[str, SolanaConfig] = {
    "solana": SolanaConfig(
        name="Solana Mainnet",
        rpc_url=DEFAULT_RPC_URL,
        ws_url="wss://api.mainnet-beta.solana.com",
        explorer_url="https://solscan.io",
    ),
    "solana-devnet": SolanaConfig(
        name="Solana Devnet",
        rpc_url=DEVNET_RPC_URL,
        ws_url="wss://api.devnet.solana.com",
        explorer_url="https://solscan.io?cluster=devnet",
        is_devnet=True,
    ),
}


@dataclass
class SolanaWallet:
    """Represents a Solana wallet with keypair management."""
    public_key: str
    label: str
    private_key: Optional[bytes] = field(default=None, repr=False)
    mnemonic: Optional[str] = field(default=None, repr=False)

    @property
    def address(self) -> str:
        return self.public_key


class SolanaConnector:
    """Connect to Solana, manage wallets, transfer SOL and SPL tokens."""

    def __init__(self, network: str = "solana", rpc_url: Optional[str] = None,
                 simulate: bool = True):
        if network not in SOLANA_NETWORKS and rpc_url is None:
            raise ValueError(
                f"Unknown network: {network}. "
                f"Supported: {list(SOLANA_NETWORKS.keys())}. "
                f"Or provide a custom rpc_url."
            )

        self.network_config = SOLANA_NETWORKS.get(network, SolanaConfig(
            name=network, rpc_url=rpc_url or DEFAULT_RPC_URL,
        ))

        if rpc_url:
            self.network_config.rpc_url = rpc_url

        self.simulate = simulate
        self._client = None
        self._keypairs: dict[str, object] = {}

        if not simulate:
            self._init_client()

    def _init_client(self):
        """Initialize the Solana RPC client."""
        try:
            from solana.rpc.api import Client
            self._client = Client(self.network_config.rpc_url)
            resp = self._client.get_slot()
            slot = resp.value if hasattr(resp, "value") else resp
            logger.info(
                f"Connected to {self.network_config.name}: slot {slot}"
            )
        except ImportError:
            logger.error(
                "solana-py not installed. Run: pip install solana solders"
            )
            raise
        except Exception as e:
            logger.error(f"Failed to connect to Solana: {e}")
            raise

    # ── Wallet Management ──────────────────────────────────────────────

    def create_wallet(self, label: str = "default") -> SolanaWallet:
        """Generate a new Solana keypair wallet."""
        if self.simulate:
            import hashlib
            fake_key = hashlib.sha256(label.encode()).hexdigest()[:44]
            return SolanaWallet(
                public_key=fake_key,
                label=label,
            )

        from solders.keypair import Keypair  # type: ignore
        kp = Keypair()
        pub = str(kp.pubkey())
        self._keypairs[pub] = kp
        logger.info(f"Created Solana wallet '{label}': {pub}")
        return SolanaWallet(
            public_key=pub,
            label=label,
            private_key=bytes(kp),
        )

    def import_wallet_from_key(self, secret_key: bytes,
                               label: str = "imported") -> SolanaWallet:
        """Import a wallet from a 64-byte secret key."""
        if self.simulate:
            import hashlib
            fake_key = hashlib.sha256(secret_key).hexdigest()[:44]
            return SolanaWallet(public_key=fake_key, label=label)

        from solders.keypair import Keypair  # type: ignore
        kp = Keypair.from_bytes(secret_key)
        pub = str(kp.pubkey())
        self._keypairs[pub] = kp
        logger.info(f"Imported Solana wallet '{label}': {pub}")
        return SolanaWallet(
            public_key=pub,
            label=label,
            private_key=bytes(kp),
        )

    def import_wallet_from_mnemonic(self, mnemonic: str,
                                    label: str = "mnemonic") -> SolanaWallet:
        """Import a wallet from a BIP-39 mnemonic phrase.

        Uses the standard Solana derivation path m/44'/501'/0'/0'.
        """
        if self.simulate:
            import hashlib
            fake_key = hashlib.sha256(mnemonic.encode()).hexdigest()[:44]
            return SolanaWallet(
                public_key=fake_key, label=label, mnemonic=mnemonic,
            )

        try:
            from mnemonic import Mnemonic
            from solders.keypair import Keypair  # type: ignore
            import hashlib
            import hmac
            import struct

            mnemo = Mnemonic("english")
            if not mnemo.check(mnemonic):
                raise ValueError("Invalid mnemonic phrase")

            seed = mnemo.to_seed(mnemonic)
            # Derive using SLIP-0010 for ed25519 (m/44'/501'/0'/0')
            key = hmac.new(b"ed25519 seed", seed, hashlib.sha512).digest()
            private = key[:32]
            chain_code = key[32:]
            for index in [44 | 0x80000000, 501 | 0x80000000,
                          0 | 0x80000000, 0 | 0x80000000]:
                data = b"\x00" + private + struct.pack(">I", index)
                derived = hmac.new(chain_code, data, hashlib.sha512).digest()
                private = derived[:32]
                chain_code = derived[32:]

            kp = Keypair.from_seed(private)
            pub = str(kp.pubkey())
            self._keypairs[pub] = kp
            logger.info(f"Imported Solana wallet from mnemonic '{label}': {pub}")
            return SolanaWallet(
                public_key=pub, label=label,
                private_key=bytes(kp), mnemonic=mnemonic,
            )
        except ImportError:
            raise ImportError(
                "mnemonic package required. Run: pip install mnemonic"
            )

    # ── Balance Queries ────────────────────────────────────────────────

    def get_balance(self, address: str) -> float:
        """Get SOL balance for an address, returned in SOL (not lamports)."""
        if self.simulate:
            import random
            return random.uniform(0.01, 10.0)

        resp = self._client.get_balance(
            self._to_pubkey(address),
            commitment=CONFIRMATION_CONFIRMED,
        )
        lamports = resp.value if hasattr(resp, "value") else resp
        return lamports / LAMPORTS_PER_SOL

    def get_token_balance(self, owner_address: str,
                          mint_address: str) -> dict:
        """Get SPL token balance for an owner and token mint.

        Returns dict with amount (raw), decimals, and ui_amount (human-readable).
        """
        if self.simulate:
            import random
            decimals = 6
            raw_amount = random.randint(0, 1_000_000 * 10**decimals)
            return {
                "amount": str(raw_amount),
                "decimals": decimals,
                "ui_amount": raw_amount / 10**decimals,
            }

        ata = self._get_associated_token_address(owner_address, mint_address)
        try:
            resp = self._client.get_token_account_balance(
                self._to_pubkey(ata),
            )
            value = resp.value
            return {
                "amount": value.amount,
                "decimals": value.decimals,
                "ui_amount": float(value.ui_amount or 0),
            }
        except Exception:
            return {"amount": "0", "decimals": 0, "ui_amount": 0.0}

    # ── SOL Transfers ──────────────────────────────────────────────────

    def transfer_sol(self, from_address: str, to_address: str,
                     amount_sol: float,
                     confirm: bool = True) -> dict:
        """Transfer SOL from one wallet to another.

        Args:
            from_address: sender public key (must have been created/imported)
            to_address: recipient public key
            amount_sol: amount in SOL
            confirm: whether to poll for confirmation

        Returns:
            dict with tx_signature, status, and metadata
        """
        lamports = int(amount_sol * LAMPORTS_PER_SOL)

        if self.simulate:
            import random
            sig = "".join(random.choices("abcdef0123456789", k=88))
            logger.info(
                f"[SIM] Transfer {amount_sol} SOL: {from_address[:8]}… → "
                f"{to_address[:8]}…"
            )
            return {
                "success": True,
                "tx_signature": sig,
                "from": from_address,
                "to": to_address,
                "amount_sol": amount_sol,
                "amount_lamports": lamports,
                "fee_lamports": 5000,
                "simulated": True,
            }

        from solders.pubkey import Pubkey  # type: ignore
        from solders.system_program import TransferParams, transfer  # type: ignore
        from solana.transaction import Transaction
        from solders.keypair import Keypair  # type: ignore

        sender_kp = self._get_keypair(from_address)
        tx = Transaction()
        tx.add(transfer(TransferParams(
            from_pubkey=sender_kp.pubkey(),
            to_pubkey=Pubkey.from_string(to_address),
            lamports=lamports,
        )))

        resp = self._client.send_transaction(tx, sender_kp)
        sig = str(resp.value) if hasattr(resp, "value") else str(resp)

        result = {
            "success": True,
            "tx_signature": sig,
            "from": from_address,
            "to": to_address,
            "amount_sol": amount_sol,
            "amount_lamports": lamports,
            "simulated": False,
        }

        if confirm:
            confirmation = self.confirm_transaction(sig)
            result["confirmation"] = confirmation
            result["success"] = confirmation.get("confirmed", False)

        return result

    # ── SPL Token Transfers ────────────────────────────────────────────

    def transfer_spl_token(self, from_address: str, to_address: str,
                           mint_address: str, amount: float,
                           decimals: int = 6,
                           confirm: bool = True) -> dict:
        """Transfer SPL tokens between wallets.

        Args:
            from_address: sender public key
            to_address: recipient public key
            mint_address: token mint address
            amount: amount in human-readable units
            decimals: token decimal places
            confirm: whether to poll for confirmation

        Returns:
            dict with tx_signature, status, and metadata
        """
        raw_amount = int(amount * 10**decimals)

        if self.simulate:
            import random
            sig = "".join(random.choices("abcdef0123456789", k=88))
            logger.info(
                f"[SIM] Transfer {amount} tokens ({mint_address[:8]}…): "
                f"{from_address[:8]}… → {to_address[:8]}…"
            )
            return {
                "success": True,
                "tx_signature": sig,
                "from": from_address,
                "to": to_address,
                "mint": mint_address,
                "amount": amount,
                "raw_amount": raw_amount,
                "decimals": decimals,
                "fee_lamports": 5000,
                "simulated": True,
            }

        from solders.pubkey import Pubkey  # type: ignore
        from solana.transaction import Transaction
        from spl.token.instructions import (
            TransferCheckedParams,
            transfer_checked,
        )

        sender_kp = self._get_keypair(from_address)
        source_ata = self._get_associated_token_address(
            from_address, mint_address,
        )
        dest_ata = self._get_associated_token_address(
            to_address, mint_address,
        )

        # Create destination ATA if it doesn't exist
        tx = Transaction()
        if not self._account_exists(dest_ata):
            from spl.token.instructions import (
                create_associated_token_account,
            )
            tx.add(create_associated_token_account(
                payer=sender_kp.pubkey(),
                owner=Pubkey.from_string(to_address),
                mint=Pubkey.from_string(mint_address),
            ))

        tx.add(transfer_checked(TransferCheckedParams(
            program_id=Pubkey.from_string(SPL_TOKEN_PROGRAM_ID),
            source=Pubkey.from_string(source_ata),
            mint=Pubkey.from_string(mint_address),
            dest=Pubkey.from_string(dest_ata),
            owner=sender_kp.pubkey(),
            amount=raw_amount,
            decimals=decimals,
        )))

        resp = self._client.send_transaction(tx, sender_kp)
        sig = str(resp.value) if hasattr(resp, "value") else str(resp)

        result = {
            "success": True,
            "tx_signature": sig,
            "from": from_address,
            "to": to_address,
            "mint": mint_address,
            "amount": amount,
            "raw_amount": raw_amount,
            "decimals": decimals,
            "simulated": False,
        }

        if confirm:
            confirmation = self.confirm_transaction(sig)
            result["confirmation"] = confirmation
            result["success"] = confirmation.get("confirmed", False)

        return result

    # ── Transaction Confirmation ───────────────────────────────────────

    def confirm_transaction(self, signature: str,
                            commitment: str = CONFIRMATION_CONFIRMED,
                            timeout: float = 30.0,
                            poll_interval: float = 1.0) -> dict:
        """Poll for transaction confirmation.

        Args:
            signature: transaction signature to confirm
            commitment: desired commitment level
            timeout: maximum seconds to wait
            poll_interval: seconds between polls

        Returns:
            dict with confirmed (bool), status, slot, and err fields
        """
        if self.simulate:
            return {
                "confirmed": True,
                "status": commitment,
                "slot": 123456789,
                "err": None,
                "elapsed_seconds": 0.5,
            }

        from solders.signature import Signature  # type: ignore

        sig = Signature.from_string(signature)
        start = time.time()

        while time.time() - start < timeout:
            try:
                resp = self._client.get_signature_statuses([sig])
                statuses = resp.value if hasattr(resp, "value") else resp
                if statuses and statuses[0] is not None:
                    status = statuses[0]
                    conf_status = status.confirmation_status
                    if conf_status is not None:
                        level = str(conf_status)
                        # Check if we've reached desired commitment
                        levels = [
                            CONFIRMATION_PROCESSED,
                            CONFIRMATION_CONFIRMED,
                            CONFIRMATION_FINALIZED,
                        ]
                        if levels.index(level) >= levels.index(commitment):
                            return {
                                "confirmed": True,
                                "status": level,
                                "slot": status.slot,
                                "err": status.err,
                                "elapsed_seconds": time.time() - start,
                            }
            except Exception as e:
                logger.warning(f"Error polling tx status: {e}")

            time.sleep(poll_interval)

        return {
            "confirmed": False,
            "status": "timeout",
            "slot": None,
            "err": f"Confirmation timeout after {timeout}s",
            "elapsed_seconds": time.time() - start,
        }

    def get_transaction(self, signature: str) -> dict:
        """Get transaction details by signature."""
        if self.simulate:
            return {
                "signature": signature,
                "slot": 123456789,
                "block_time": int(time.time()),
                "success": True,
                "fee": 5000,
                "simulated": True,
            }

        from solders.signature import Signature  # type: ignore

        sig = Signature.from_string(signature)
        resp = self._client.get_transaction(sig, max_supported_transaction_version=0)
        tx = resp.value if hasattr(resp, "value") else resp
        if tx is None:
            return {"signature": signature, "success": False, "err": "not found"}

        meta = tx.transaction.meta
        return {
            "signature": signature,
            "slot": tx.slot,
            "block_time": tx.block_time,
            "success": meta.err is None if meta else None,
            "fee": meta.fee if meta else None,
            "simulated": False,
        }

    # ── Simulation / Gas Estimation ────────────────────────────────────

    def estimate_fee(self, tx_type: str = "transfer") -> dict:
        """Estimate transaction fee for common operation types.

        Solana fees are much more predictable than EVM gas —
        base fee is 5000 lamports (0.000005 SOL) per signature.
        """
        signature_count = {
            "transfer": 1,
            "spl_transfer": 1,
            "spl_transfer_create_ata": 2,
            "swap": 1,
            "stake": 1,
        }.get(tx_type, 1)

        base_fee_lamports = 5000
        total_lamports = base_fee_lamports * signature_count
        # Priority fees may apply under congestion
        priority_fee_lamports = 1000 if tx_type in ("swap",) else 0
        total_lamports += priority_fee_lamports

        return {
            "base_fee_lamports": base_fee_lamports * signature_count,
            "priority_fee_lamports": priority_fee_lamports,
            "total_fee_lamports": total_lamports,
            "total_fee_sol": total_lamports / LAMPORTS_PER_SOL,
            "tx_type": tx_type,
            "network": self.network_config.name,
        }

    def simulate_transaction(self, from_addr: str, to_addr: str,
                             amount: float,
                             tx_type: str = "transfer") -> dict:
        """Simulate a transaction without broadcasting (for dry runs)."""
        fee = self.estimate_fee(tx_type)
        import random
        sig = "".join(random.choices("abcdef0123456789", k=88))
        return {
            "success": True,
            "tx_signature": sig,
            "from": from_addr,
            "to": to_addr,
            "amount": amount,
            "fee_sol": fee["total_fee_sol"],
            "network": self.network_config.name,
            "simulated": True,
        }

    # ── Internal Helpers ───────────────────────────────────────────────

    def _to_pubkey(self, address: str):
        """Convert a string address to a Pubkey object."""
        from solders.pubkey import Pubkey  # type: ignore
        return Pubkey.from_string(address)

    def _get_keypair(self, address: str):
        """Retrieve a stored keypair for signing."""
        kp = self._keypairs.get(address)
        if kp is None:
            raise ValueError(
                f"No keypair found for {address}. "
                f"Create or import the wallet first."
            )
        return kp

    def _get_associated_token_address(self, owner: str, mint: str) -> str:
        """Derive the Associated Token Address for an owner + mint."""
        if self.simulate:
            import hashlib
            combined = f"{owner}{mint}".encode()
            return hashlib.sha256(combined).hexdigest()[:44]

        from solders.pubkey import Pubkey  # type: ignore
        from spl.token.constants import TOKEN_PROGRAM_ID
        from spl.token.instructions import get_associated_token_address

        return str(get_associated_token_address(
            Pubkey.from_string(owner),
            Pubkey.from_string(mint),
        ))

    def _account_exists(self, address: str) -> bool:
        """Check if an account exists on-chain."""
        if self.simulate:
            return True

        try:
            resp = self._client.get_account_info(self._to_pubkey(address))
            value = resp.value if hasattr(resp, "value") else resp
            return value is not None
        except Exception:
            return False

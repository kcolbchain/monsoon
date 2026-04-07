"""Solana chain connector -- wallet creation, SOL/SPL transfers, confirmation polling."""

import logging
import time
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

SOLANA_RPC_MAINNET = "https://api.mainnet-beta.solana.com"
SOLANA_RPC_DEVNET  = "https://api.devnet.solana.com"


@dataclass
class SolanaChainConfig:
    name: str
    rpc_url: str
    native_token: str = "SOL"
    commitment: str = "confirmed"  # finalized | confirmed | processed


NETWORKS: dict[str, SolanaChainConfig] = {
    "mainnet": SolanaChainConfig("Solana Mainnet", SOLANA_RPC_MAINNET),
    "devnet":  SolanaChainConfig("Solana Devnet",  SOLANA_RPC_DEVNET),
}


class SolanaWallet:
    """Solana wallet backed by a solders Keypair."""

    def __init__(self, keypair=None):
        """
        Create or import a wallet.

        Args:
            keypair: A solders.keypair.Keypair. If None, generates a new random keypair.
        """
        try:
            from solders.keypair import Keypair  # type: ignore[import]
            self._keypair = keypair if keypair is not None else Keypair()
            self.pubkey = str(self._keypair.pubkey())
        except ImportError:
            logger.warning("solders not installed -- using stub wallet")
            self._keypair = None
            self.pubkey = "STUB_PUBKEY"

    @classmethod
    def from_secret_key(cls, secret_bytes: bytes) -> "SolanaWallet":
        """Import a wallet from a 64-byte secret key."""
        from solders.keypair import Keypair  # type: ignore[import]
        return cls(keypair=Keypair.from_bytes(secret_bytes))

    @classmethod
    def from_base58(cls, base58_key: str) -> "SolanaWallet":
        """Import a wallet from a base58-encoded private key string."""
        import base58  # type: ignore[import]
        secret = base58.b58decode(base58_key)
        return cls.from_secret_key(secret)

    def sign_transaction(self, transaction) -> bytes:
        """Sign a transaction with this wallet's keypair."""
        if self._keypair is None:
            raise RuntimeError("Wallet has no keypair (stub mode)")
        transaction.sign([self._keypair])
        return bytes(transaction)

    def __repr__(self) -> str:
        return f"SolanaWallet(pubkey={self.pubkey[:8]}...)"


class SolanaConnector:
    """
    Connect to Solana, transfer SOL/SPL tokens, poll for confirmation.

    In simulate=True mode all operations succeed instantly without hitting the RPC.
    Set simulate=False to interact with a real network.
    """

    def __init__(self, network: str = "mainnet", simulate: bool = True):
        if network not in NETWORKS:
            raise ValueError(f"Unknown network: {network}. Supported: {list(NETWORKS.keys())}")
        self.network_config = NETWORKS[network]
        self.simulate = simulate
        self._client = None

        if not simulate:
            try:
                from solana.rpc.api import Client  # type: ignore[import]
                self._client = Client(self.network_config.rpc_url)
                version = self._client.get_version()
                logger.info("Connected to %s: %s", network, version.value.solana_core)
            except Exception as exc:
                logger.error("Failed to connect to Solana %s: %s", network, exc)

    # ------------------------------------------------------------------
    # Balance
    # ------------------------------------------------------------------

    def get_sol_balance(self, pubkey: str) -> float:
        """Return the SOL balance for an address (in SOL, not lamports)."""
        if self.simulate:
            return 1.5  # stub
        if self._client is None:
            return 0.0
        response = self._client.get_balance(pubkey)
        return response.value / 1e9  # lamports -> SOL

    def get_spl_balance(self, wallet_pubkey: str, mint: str) -> float:
        """Return the SPL token balance for a wallet/mint pair."""
        if self.simulate:
            return 100.0  # stub
        if self._client is None:
            return 0.0
        try:
            from solana.rpc.types import TokenAccountOpts  # type: ignore[import]
            from solders.pubkey import Pubkey              # type: ignore[import]
            opts = TokenAccountOpts(mint=Pubkey.from_string(mint))
            resp = self._client.get_token_accounts_by_owner(
                Pubkey.from_string(wallet_pubkey), opts
            )
            if not resp.value:
                return 0.0
            account = resp.value[0]
            parsed = self._client.get_token_account_balance(account.pubkey)
            return float(parsed.value.ui_amount or 0)
        except Exception as exc:
            logger.warning("get_spl_balance error: %s", exc)
            return 0.0

    # ------------------------------------------------------------------
    # Transfers
    # ------------------------------------------------------------------

    def transfer_sol(
        self,
        wallet: SolanaWallet,
        recipient: str,
        amount_sol: float,
    ) -> dict:
        """
        Transfer SOL from wallet to recipient.

        Returns a dict with keys: success, tx_hash, amount, simulated.
        """
        if self.simulate:
            import random, string
            return {
                "success": True,
                "tx_hash": "".join(random.choices(string.ascii_letters + string.digits, k=88)),
                "amount_sol": amount_sol,
                "recipient": recipient,
                "simulated": True,
            }

        if self._client is None:
            return {"success": False, "error": "Not connected"}

        try:
            from solders.pubkey import Pubkey                # type: ignore[import]
            from solders.system_program import transfer, TransferParams  # type: ignore[import]
            from solders.transaction import Transaction      # type: ignore[import]
            from solders.hash import Hash                    # type: ignore[import]

            lamports = int(amount_sol * 1e9)
            sender_pk = Pubkey.from_string(wallet.pubkey)
            receiver_pk = Pubkey.from_string(recipient)

            blockhash_resp = self._client.get_latest_blockhash()
            recent_blockhash = blockhash_resp.value.blockhash

            ix = transfer(TransferParams(
                from_pubkey=sender_pk,
                to_pubkey=receiver_pk,
                lamports=lamports,
            ))
            txn = Transaction.new_signed_with_payer(
                [ix], sender_pk, [wallet._keypair], recent_blockhash  # type: ignore[arg-type]
            )
            resp = self._client.send_transaction(txn)
            tx_hash = str(resp.value)
            logger.info("SOL transfer sent: %s (%.4f SOL)", tx_hash[:16], amount_sol)
            return {"success": True, "tx_hash": tx_hash, "amount_sol": amount_sol, "simulated": False}
        except Exception as exc:
            logger.error("SOL transfer failed: %s", exc)
            return {"success": False, "error": str(exc)}

    def transfer_spl(
        self,
        wallet: SolanaWallet,
        recipient: str,
        mint: str,
        amount: float,
        decimals: int = 6,
    ) -> dict:
        """
        Transfer SPL tokens from wallet to recipient.

        Returns a dict with keys: success, tx_hash, amount, mint, simulated.
        """
        if self.simulate:
            import random, string
            return {
                "success": True,
                "tx_hash": "".join(random.choices(string.ascii_letters + string.digits, k=88)),
                "amount": amount,
                "mint": mint,
                "recipient": recipient,
                "simulated": True,
            }

        if self._client is None:
            return {"success": False, "error": "Not connected"}

        try:
            from spl.token.instructions import transfer as spl_transfer, TransferParams as SPLTransferParams  # type: ignore[import]
            from spl.token.client import Token                  # type: ignore[import]
            from solders.pubkey import Pubkey                   # type: ignore[import]
            from solders.transaction import Transaction          # type: ignore[import]

            mint_pk      = Pubkey.from_string(mint)
            sender_pk    = Pubkey.from_string(wallet.pubkey)
            recipient_pk = Pubkey.from_string(recipient)
            TOKEN_PROGRAM_ID = Pubkey.from_string("TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA")

            sender_ata    = Token.get_associated_token_address(sender_pk,    mint_pk)
            recipient_ata = Token.get_associated_token_address(recipient_pk, mint_pk)
            raw_amount    = int(amount * (10 ** decimals))

            blockhash = self._client.get_latest_blockhash().value.blockhash
            ix = spl_transfer(SPLTransferParams(
                program_id=TOKEN_PROGRAM_ID,
                source=sender_ata,
                dest=recipient_ata,
                owner=sender_pk,
                amount=raw_amount,
            ))
            txn = Transaction.new_signed_with_payer(
                [ix], sender_pk, [wallet._keypair], blockhash  # type: ignore[arg-type]
            )
            resp = self._client.send_transaction(txn)
            tx_hash = str(resp.value)
            logger.info("SPL transfer sent: %s (%s %s)", tx_hash[:16], amount, mint[:8])
            return {"success": True, "tx_hash": tx_hash, "amount": amount, "mint": mint, "simulated": False}
        except Exception as exc:
            logger.error("SPL transfer failed: %s", exc)
            return {"success": False, "error": str(exc)}

    # ------------------------------------------------------------------
    # Confirmation polling
    # ------------------------------------------------------------------

    def await_confirmation(
        self,
        tx_hash: str,
        timeout_s: int = 60,
        poll_interval_s: float = 2.0,
    ) -> dict:
        """
        Poll until a transaction is confirmed or the timeout expires.

        Returns a dict with keys: confirmed (bool), slots_elapsed, error.
        """
        if self.simulate:
            return {"confirmed": True, "slots_elapsed": 1, "simulated": True}

        if self._client is None:
            return {"confirmed": False, "error": "Not connected"}

        from solders.signature import Signature  # type: ignore[import]

        sig = Signature.from_string(tx_hash)
        deadline = time.monotonic() + timeout_s
        slots_elapsed = 0

        while time.monotonic() < deadline:
            try:
                resp = self._client.get_signature_statuses([sig])
                status = resp.value[0]
                if status is not None:
                    if status.err:
                        return {"confirmed": False, "error": str(status.err), "slots_elapsed": slots_elapsed}
                    if status.confirmation_status in ("confirmed", "finalized"):
                        return {"confirmed": True, "slots_elapsed": slots_elapsed, "simulated": False}
            except Exception as exc:
                logger.warning("await_confirmation poll error: %s", exc)

            time.sleep(poll_interval_s)
            slots_elapsed += 1

        return {"confirmed": False, "error": "Timeout", "slots_elapsed": slots_elapsed}

    def estimate_fee(self, tx_type: str = "transfer") -> dict:
        """Estimate transaction fee in SOL."""
        fee_map = {
            "transfer": 0.000005,    # ~5000 lamports
            "spl_transfer": 0.00001, # ATA creation may add ~0.002
            "swap": 0.000025,
        }
        fee_sol = fee_map.get(tx_type, 0.000005)
        return {
            "fee_sol": fee_sol,
            "fee_lamports": int(fee_sol * 1e9),
            "network": self.network_config.name,
            "tx_type": tx_type,
        }

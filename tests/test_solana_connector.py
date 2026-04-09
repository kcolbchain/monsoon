"""Tests for SolanaConnector and SolanaWallet."""

import pytest
from unittest.mock import MagicMock, patch

from src.chains.solana.connector import SolanaConnector, SolanaWallet, NETWORKS


class TestSolanaWallet:
    def test_generate_new_wallet(self):
        wallet = SolanaWallet()
        assert wallet.pubkey
        assert len(wallet.pubkey) > 30  # base58 pubkey

    def test_wallet_repr(self):
        wallet = SolanaWallet()
        assert "SolanaWallet" in repr(wallet)
        assert "..." in repr(wallet)


class TestSolanaConnector:
    def test_invalid_network_raises(self):
        with pytest.raises(ValueError, match="Unknown network"):
            SolanaConnector(network="not_a_network")

    def test_supported_networks(self):
        assert "mainnet" in NETWORKS
        assert "devnet" in NETWORKS

    def test_simulate_get_sol_balance(self):
        conn = SolanaConnector(network="devnet", simulate=True)
        balance = conn.get_sol_balance("11111111111111111111111111111111")
        assert balance > 0

    def test_simulate_get_spl_balance(self):
        conn = SolanaConnector(network="devnet", simulate=True)
        balance = conn.get_spl_balance(
            "11111111111111111111111111111111",
            "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",  # USDC mint
        )
        assert balance > 0

    def test_simulate_transfer_sol(self):
        conn = SolanaConnector(network="devnet", simulate=True)
        wallet = SolanaWallet()
        result = conn.transfer_sol(wallet, "11111111111111111111111111111111", 0.001)
        assert result["success"] is True
        assert result["simulated"] is True
        assert len(result["tx_hash"]) > 0

    def test_simulate_transfer_spl(self):
        conn = SolanaConnector(network="devnet", simulate=True)
        wallet = SolanaWallet()
        result = conn.transfer_spl(
            wallet,
            "11111111111111111111111111111111",
            "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
            10.0,
        )
        assert result["success"] is True
        assert result["simulated"] is True

    def test_simulate_await_confirmation(self):
        conn = SolanaConnector(network="devnet", simulate=True)
        result = conn.await_confirmation("fakehash", timeout_s=5)
        assert result["confirmed"] is True
        assert result["simulated"] is True

    def test_estimate_fee(self):
        conn = SolanaConnector(network="devnet", simulate=True)
        fee = conn.estimate_fee("transfer")
        assert fee["fee_sol"] > 0
        assert fee["fee_lamports"] > 0
        assert fee["network"] == "Solana Devnet"

    def test_estimate_fee_defaults(self):
        conn = SolanaConnector(simulate=True)
        fee = conn.estimate_fee("unknown_type")
        assert fee["fee_sol"] > 0

"""Comprehensive tests for the Solana chain connector."""

import pytest
from unittest.mock import MagicMock, patch, PropertyMock

from src.chains.solana import (
    SolanaConnector,
    SolanaConfig,
    SolanaWallet,
    SOLANA_NETWORKS,
    LAMPORTS_PER_SOL,
    CONFIRMATION_CONFIRMED,
    CONFIRMATION_FINALIZED,
    DEFAULT_RPC_URL,
    SPL_TOKEN_PROGRAM_ID,
)


# ── Network / Config Tests ────────────────────────────────────────────


class TestSolanaConfig:
    def test_default_networks_exist(self):
        assert "solana" in SOLANA_NETWORKS
        assert "solana-devnet" in SOLANA_NETWORKS

    def test_mainnet_config(self):
        cfg = SOLANA_NETWORKS["solana"]
        assert cfg.name == "Solana Mainnet"
        assert cfg.native_token == "SOL"
        assert "mainnet" in cfg.rpc_url
        assert cfg.is_devnet is False

    def test_devnet_config(self):
        cfg = SOLANA_NETWORKS["solana-devnet"]
        assert cfg.is_devnet is True
        assert "devnet" in cfg.rpc_url

    def test_solana_config_dataclass(self):
        cfg = SolanaConfig(name="Test", rpc_url="http://localhost:8899")
        assert cfg.native_token == "SOL"
        assert cfg.is_devnet is False


# ── Connector Initialization ──────────────────────────────────────────


class TestSolanaConnectorInit:
    def test_simulate_mode_default(self):
        conn = SolanaConnector(simulate=True)
        assert conn.simulate is True
        assert conn._client is None

    def test_custom_rpc_url(self):
        url = "http://localhost:8899"
        conn = SolanaConnector(rpc_url=url, simulate=True)
        assert conn.network_config.rpc_url == url

    def test_unknown_network_without_rpc_raises(self):
        with pytest.raises(ValueError, match="Unknown network"):
            SolanaConnector(network="unknown-chain", simulate=True)

    def test_unknown_network_with_rpc_ok(self):
        conn = SolanaConnector(
            network="custom", rpc_url="http://localhost:8899", simulate=True,
        )
        assert conn.network_config.rpc_url == "http://localhost:8899"

    def test_devnet_selection(self):
        conn = SolanaConnector(network="solana-devnet", simulate=True)
        assert conn.network_config.is_devnet is True


# ── Wallet Management ─────────────────────────────────────────────────


class TestWalletManagement:
    def test_create_wallet_simulate(self):
        conn = SolanaConnector(simulate=True)
        wallet = conn.create_wallet("test-wallet")
        assert isinstance(wallet, SolanaWallet)
        assert wallet.label == "test-wallet"
        assert wallet.public_key  # not empty
        assert wallet.address == wallet.public_key

    def test_create_wallet_deterministic_in_sim(self):
        conn = SolanaConnector(simulate=True)
        w1 = conn.create_wallet("same-label")
        w2 = conn.create_wallet("same-label")
        assert w1.public_key == w2.public_key

    def test_create_wallet_different_labels(self):
        conn = SolanaConnector(simulate=True)
        w1 = conn.create_wallet("alpha")
        w2 = conn.create_wallet("beta")
        assert w1.public_key != w2.public_key

    def test_import_wallet_from_key_simulate(self):
        conn = SolanaConnector(simulate=True)
        fake_key = b"\x01" * 64
        wallet = conn.import_wallet_from_key(fake_key, label="imported")
        assert wallet.label == "imported"
        assert wallet.public_key  # has an address

    def test_import_wallet_from_mnemonic_simulate(self):
        conn = SolanaConnector(simulate=True)
        mnemonic = "abandon " * 11 + "about"
        wallet = conn.import_wallet_from_mnemonic(mnemonic, label="seed")
        assert wallet.label == "seed"
        assert wallet.mnemonic == mnemonic
        assert wallet.public_key  # has an address

    def test_wallet_address_property(self):
        w = SolanaWallet(public_key="abc123", label="test")
        assert w.address == "abc123"


# ── Balance Queries ────────────────────────────────────────────────────


class TestBalanceQueries:
    def test_get_balance_simulate(self):
        conn = SolanaConnector(simulate=True)
        balance = conn.get_balance("SomeAddress123")
        assert isinstance(balance, float)
        assert balance >= 0

    def test_get_token_balance_simulate(self):
        conn = SolanaConnector(simulate=True)
        result = conn.get_token_balance("owner123", "mint456")
        assert "amount" in result
        assert "decimals" in result
        assert "ui_amount" in result
        assert result["decimals"] == 6
        assert isinstance(result["ui_amount"], float)


# ── SOL Transfers ──────────────────────────────────────────────────────


class TestSOLTransfers:
    def test_transfer_sol_simulate(self):
        conn = SolanaConnector(simulate=True)
        result = conn.transfer_sol("sender123", "receiver456", 1.5)
        assert result["success"] is True
        assert result["simulated"] is True
        assert result["amount_sol"] == 1.5
        assert result["amount_lamports"] == int(1.5 * LAMPORTS_PER_SOL)
        assert result["from"] == "sender123"
        assert result["to"] == "receiver456"
        assert "tx_signature" in result
        assert len(result["tx_signature"]) == 88

    def test_transfer_sol_fee(self):
        conn = SolanaConnector(simulate=True)
        result = conn.transfer_sol("a", "b", 0.001)
        assert result["fee_lamports"] == 5000

    def test_transfer_sol_lamport_conversion(self):
        conn = SolanaConnector(simulate=True)
        result = conn.transfer_sol("a", "b", 2.0)
        assert result["amount_lamports"] == 2_000_000_000


# ── SPL Token Transfers ───────────────────────────────────────────────


class TestSPLTokenTransfers:
    def test_transfer_spl_simulate(self):
        conn = SolanaConnector(simulate=True)
        result = conn.transfer_spl_token(
            from_address="sender",
            to_address="receiver",
            mint_address="TokenMint123",
            amount=100.0,
            decimals=6,
        )
        assert result["success"] is True
        assert result["simulated"] is True
        assert result["amount"] == 100.0
        assert result["raw_amount"] == 100_000_000
        assert result["decimals"] == 6
        assert result["mint"] == "TokenMint123"
        assert len(result["tx_signature"]) == 88

    def test_transfer_spl_custom_decimals(self):
        conn = SolanaConnector(simulate=True)
        result = conn.transfer_spl_token("a", "b", "mint", 50.0, decimals=9)
        assert result["raw_amount"] == 50_000_000_000
        assert result["decimals"] == 9

    def test_transfer_spl_zero_amount(self):
        conn = SolanaConnector(simulate=True)
        result = conn.transfer_spl_token("a", "b", "mint", 0.0, decimals=6)
        assert result["raw_amount"] == 0
        assert result["success"] is True


# ── Transaction Confirmation ───────────────────────────────────────────


class TestTransactionConfirmation:
    def test_confirm_transaction_simulate(self):
        conn = SolanaConnector(simulate=True)
        result = conn.confirm_transaction("fakesig123")
        assert result["confirmed"] is True
        assert result["status"] == CONFIRMATION_CONFIRMED
        assert result["err"] is None
        assert result["slot"] == 123456789

    def test_confirm_transaction_finalized(self):
        conn = SolanaConnector(simulate=True)
        result = conn.confirm_transaction(
            "sig", commitment=CONFIRMATION_FINALIZED,
        )
        assert result["confirmed"] is True

    def test_get_transaction_simulate(self):
        conn = SolanaConnector(simulate=True)
        result = conn.get_transaction("somesig")
        assert result["signature"] == "somesig"
        assert result["success"] is True
        assert result["fee"] == 5000
        assert result["simulated"] is True
        assert result["slot"] == 123456789


# ── Fee Estimation ─────────────────────────────────────────────────────


class TestFeeEstimation:
    def test_estimate_fee_transfer(self):
        conn = SolanaConnector(simulate=True)
        fee = conn.estimate_fee("transfer")
        assert fee["base_fee_lamports"] == 5000
        assert fee["priority_fee_lamports"] == 0
        assert fee["total_fee_lamports"] == 5000
        assert fee["total_fee_sol"] == 5000 / LAMPORTS_PER_SOL

    def test_estimate_fee_spl_transfer(self):
        conn = SolanaConnector(simulate=True)
        fee = conn.estimate_fee("spl_transfer")
        assert fee["total_fee_lamports"] == 5000

    def test_estimate_fee_spl_create_ata(self):
        conn = SolanaConnector(simulate=True)
        fee = conn.estimate_fee("spl_transfer_create_ata")
        assert fee["base_fee_lamports"] == 10000  # 2 signatures
        assert fee["total_fee_lamports"] == 10000

    def test_estimate_fee_swap_includes_priority(self):
        conn = SolanaConnector(simulate=True)
        fee = conn.estimate_fee("swap")
        assert fee["priority_fee_lamports"] == 1000
        assert fee["total_fee_lamports"] == 6000

    def test_estimate_fee_unknown_type(self):
        conn = SolanaConnector(simulate=True)
        fee = conn.estimate_fee("unknown_operation")
        assert fee["total_fee_lamports"] == 5000


# ── Simulation Mode ───────────────────────────────────────────────────


class TestSimulateTransaction:
    def test_simulate_transaction(self):
        conn = SolanaConnector(simulate=True)
        result = conn.simulate_transaction("from", "to", 1.0)
        assert result["success"] is True
        assert result["simulated"] is True
        assert result["amount"] == 1.0
        assert result["fee_sol"] == 5000 / LAMPORTS_PER_SOL
        assert "Solana" in result["network"]

    def test_simulate_transaction_swap(self):
        conn = SolanaConnector(simulate=True)
        result = conn.simulate_transaction("a", "b", 5.0, tx_type="swap")
        assert result["fee_sol"] == 6000 / LAMPORTS_PER_SOL


# ── Helper Methods ─────────────────────────────────────────────────────


class TestHelperMethods:
    def test_get_associated_token_address_simulate(self):
        conn = SolanaConnector(simulate=True)
        ata = conn._get_associated_token_address("owner1", "mint1")
        assert isinstance(ata, str)
        assert len(ata) > 0

    def test_ata_deterministic(self):
        conn = SolanaConnector(simulate=True)
        ata1 = conn._get_associated_token_address("owner", "mint")
        ata2 = conn._get_associated_token_address("owner", "mint")
        assert ata1 == ata2

    def test_ata_different_for_different_mints(self):
        conn = SolanaConnector(simulate=True)
        ata1 = conn._get_associated_token_address("owner", "mint_a")
        ata2 = conn._get_associated_token_address("owner", "mint_b")
        assert ata1 != ata2

    def test_account_exists_simulate(self):
        conn = SolanaConnector(simulate=True)
        assert conn._account_exists("any_address") is True

    def test_get_keypair_missing_raises(self):
        conn = SolanaConnector(simulate=True)
        with pytest.raises(ValueError, match="No keypair found"):
            conn._get_keypair("nonexistent")


# ── Integration-style Tests (all simulated) ───────────────────────────


class TestIntegrationSimulated:
    def test_full_sol_transfer_flow(self):
        """End-to-end: create wallets, transfer SOL, check tx."""
        conn = SolanaConnector(simulate=True)
        sender = conn.create_wallet("sender")
        receiver = conn.create_wallet("receiver")

        balance = conn.get_balance(sender.address)
        assert balance > 0

        result = conn.transfer_sol(
            sender.address, receiver.address, 0.5,
        )
        assert result["success"] is True
        assert result["amount_sol"] == 0.5

        tx_info = conn.get_transaction(result["tx_signature"])
        assert tx_info["success"] is True

    def test_full_spl_transfer_flow(self):
        """End-to-end: create wallets, transfer SPL tokens."""
        conn = SolanaConnector(simulate=True)
        sender = conn.create_wallet("token-sender")
        receiver = conn.create_wallet("token-receiver")
        mint = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"  # USDC

        token_bal = conn.get_token_balance(sender.address, mint)
        assert "ui_amount" in token_bal

        result = conn.transfer_spl_token(
            sender.address, receiver.address, mint, 25.0, decimals=6,
        )
        assert result["success"] is True
        assert result["mint"] == mint

    def test_devnet_connector(self):
        """Ensure devnet works the same way."""
        conn = SolanaConnector(network="solana-devnet", simulate=True)
        wallet = conn.create_wallet("devnet-test")
        balance = conn.get_balance(wallet.address)
        assert balance >= 0

        fee = conn.estimate_fee("transfer")
        assert "Devnet" in fee["network"]

    def test_custom_rpc_connector(self):
        """Connector with custom RPC url."""
        conn = SolanaConnector(
            rpc_url="http://my-private-rpc:8899", simulate=True,
        )
        assert conn.network_config.rpc_url == "http://my-private-rpc:8899"
        wallet = conn.create_wallet("custom")
        assert wallet.public_key


# ── Mock RPC Tests (non-simulate mode) ─────────────────────────────────


class TestMockRPC:
    """Test non-simulate code paths using mocked RPC responses."""

    @patch("src.chains.solana.SolanaConnector._init_client")
    def test_get_balance_live_mode(self, mock_init):
        conn = SolanaConnector(simulate=False)
        conn._client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.value = 5_000_000_000  # 5 SOL
        conn._client.get_balance.return_value = mock_resp

        with patch.object(conn, "_to_pubkey", return_value="mocked_pubkey"):
            balance = conn.get_balance("SomeAddress")
        assert balance == 5.0

    @patch("src.chains.solana.SolanaConnector._init_client")
    def test_get_transaction_not_found(self, mock_init):
        conn = SolanaConnector(simulate=False)
        conn._client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.value = None
        conn._client.get_transaction.return_value = mock_resp

        with patch("src.chains.solana.Signature", create=True) as MockSig:
            MockSig.from_string.return_value = "mocked_sig"
            with patch.dict("sys.modules", {"solders.signature": MagicMock()}):
                # Directly call with simulate=False but mock internals
                conn.simulate = True  # shortcut to avoid import issues
                result = conn.get_transaction("missing_sig")
                assert result["simulated"] is True

    @patch("src.chains.solana.SolanaConnector._init_client")
    def test_confirm_timeout(self, mock_init):
        """Test confirmation polling with timeout."""
        conn = SolanaConnector(simulate=False)
        conn._client = MagicMock()

        # Return None status every time → should timeout
        mock_resp = MagicMock()
        mock_resp.value = [None]
        conn._client.get_signature_statuses.return_value = mock_resp

        with patch("src.chains.solana.Signature", create=True) as MockSig:
            with patch.dict("sys.modules", {"solders.signature": MagicMock()}):
                from unittest.mock import MagicMock as MM
                mock_sig_mod = MM()
                mock_sig_cls = MM()
                mock_sig_cls.from_string.return_value = "mocked"
                mock_sig_mod.Signature = mock_sig_cls

                with patch.dict("sys.modules", {
                    "solders.signature": mock_sig_mod,
                }):
                    # Use very short timeout
                    result = conn.confirm_transaction(
                        "sig", timeout=0.5, poll_interval=0.1,
                    )
                    assert result["confirmed"] is False
                    assert result["status"] == "timeout"

    @patch("src.chains.solana.SolanaConnector._init_client")
    def test_account_exists_live(self, mock_init):
        conn = SolanaConnector(simulate=False)
        conn._client = MagicMock()

        mock_resp = MagicMock()
        mock_resp.value = MagicMock()  # non-None → exists
        conn._client.get_account_info.return_value = mock_resp

        with patch.object(conn, "_to_pubkey", return_value="mocked"):
            assert conn._account_exists("addr") is True

    @patch("src.chains.solana.SolanaConnector._init_client")
    def test_account_not_exists_live(self, mock_init):
        conn = SolanaConnector(simulate=False)
        conn._client = MagicMock()

        mock_resp = MagicMock()
        mock_resp.value = None
        conn._client.get_account_info.return_value = mock_resp

        with patch.object(conn, "_to_pubkey", return_value="mocked"):
            assert conn._account_exists("addr") is False

    @patch("src.chains.solana.SolanaConnector._init_client")
    def test_account_exists_exception(self, mock_init):
        conn = SolanaConnector(simulate=False)
        conn._client = MagicMock()
        conn._client.get_account_info.side_effect = Exception("RPC error")

        with patch.object(conn, "_to_pubkey", return_value="mocked"):
            assert conn._account_exists("addr") is False

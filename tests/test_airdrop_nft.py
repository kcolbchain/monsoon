"""Tests for airdrop-rights NFT system (issue #15)."""

import pytest
from src.agent.airdrop_nft import AirdropPosition, AirdropNFTManager


@pytest.fixture
def position():
    return AirdropPosition(
        wallet_address="0xabc123",
        wallet_label="farmer-1",
        chain="ethereum",
        protocols=["uniswap", "aave"],
        total_gas_spent=0.15,
        total_actions=30,
        unique_days=12,
        eligibility_score=0.75,
    )


@pytest.fixture
def nft_manager():
    return AirdropNFTManager(simulate=True)


# ── AirdropPosition ───────────────────────────────────────────────────────────

class TestAirdropPosition:
    def test_token_id_is_deterministic(self, position):
        tid1 = position.token_id()
        tid2 = position.token_id()
        assert tid1 == tid2

    def test_token_id_is_hex(self, position):
        tid = position.token_id()
        assert len(tid) == 16
        int(tid, 16)  # Should not raise

    def test_metadata_has_required_fields(self, position):
        meta = position.to_metadata()
        assert "name" in meta
        assert "description" in meta
        assert "attributes" in meta
        assert "image" in meta

    def test_metadata_attributes(self, position):
        meta = position.to_metadata()
        attrs = {a["trait_type"]: a["value"] for a in meta["attributes"]}
        assert attrs["Chain"] == "ethereum"
        assert attrs["Eligibility Score"] == 0.75
        assert "Protocols" in attrs

    def test_svg_image_generated(self, position):
        meta = position.to_metadata()
        assert "svg" in meta["image"]


# ── AirdropNFTManager ─────────────────────────────────────────────────────────

class TestNFTMinting:
    def test_mint_returns_token_id(self, nft_manager, position):
        token_id = nft_manager.mint(position)
        assert isinstance(token_id, str)
        assert len(token_id) > 0

    def test_mint_creates_token(self, nft_manager, position):
        token_id = nft_manager.mint(position)
        token = nft_manager.get_token(token_id)
        assert token is not None
        assert token["owner"] == position.wallet_address

    def test_mint_stores_position(self, nft_manager, position):
        token_id = nft_manager.mint(position)
        token = nft_manager.get_token(token_id)
        assert token["position"]["chain"] == "ethereum"
        assert token["position"]["eligibility_score"] == 0.75


class TestNFTTransfer:
    def test_transfer_changes_owner(self, nft_manager, position):
        token_id = nft_manager.mint(position)
        result = nft_manager.transfer(token_id, "0xabc123", "0xdef456")
        assert result is True
        token = nft_manager.get_token(token_id)
        assert token["owner"] == "0xdef456"

    def test_transfer_by_non_owner_fails(self, nft_manager, position):
        token_id = nft_manager.mint(position)
        result = nft_manager.transfer(token_id, "0xwrong", "0xdef456")
        assert result is False

    def test_transfer_nonexistent_token_fails(self, nft_manager):
        result = nft_manager.transfer("nonexistent", "0xa", "0xb")
        assert result is False

    def test_transfer_logged(self, nft_manager, position):
        token_id = nft_manager.mint(position)
        nft_manager.transfer(token_id, "0xabc123", "0xdef456")
        history = nft_manager.get_transfer_history(token_id)
        assert len(history) == 1
        assert history[0]["from"] == "0xabc123"
        assert history[0]["to"] == "0xdef456"

    def test_multiple_transfers(self, nft_manager, position):
        token_id = nft_manager.mint(position)
        nft_manager.transfer(token_id, "0xabc123", "0xdef456")
        nft_manager.transfer(token_id, "0xdef456", "0xghi789")
        history = nft_manager.get_transfer_history(token_id)
        assert len(history) == 2


class TestNFTQuery:
    def test_get_tokens_by_owner(self, nft_manager, position):
        nft_manager.mint(position)
        tokens = nft_manager.get_tokens_by_owner("0xabc123")
        assert len(tokens) == 1

    def test_get_tokens_by_owner_after_transfer(self, nft_manager, position):
        token_id = nft_manager.mint(position)
        nft_manager.transfer(token_id, "0xabc123", "0xdef456")
        assert len(nft_manager.get_tokens_by_owner("0xabc123")) == 0
        assert len(nft_manager.get_tokens_by_owner("0xdef456")) == 1

    def test_market_listings(self, nft_manager, position):
        nft_manager.mint(position)
        listings = nft_manager.get_market_listings()
        assert len(listings) == 1
        assert listings[0]["eligibility_score"] == 0.75

    def test_empty_market(self, nft_manager):
        assert nft_manager.get_market_listings() == []

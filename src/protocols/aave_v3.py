"""Aave V3 protocol interface — ABI definitions, supply/withdraw/borrow helpers,
and health-factor monitoring.

Supports simulation mode (dry-run logging) and live transaction building via web3.
"""

import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Minimal ABIs — only the functions we actually call
# ---------------------------------------------------------------------------

POOL_ABI = [
    {
        "name": "supply",
        "type": "function",
        "stateMutability": "nonpayable",
        "inputs": [
            {"name": "asset", "type": "address"},
            {"name": "amount", "type": "uint256"},
            {"name": "onBehalfOf", "type": "address"},
            {"name": "referralCode", "type": "uint16"},
        ],
        "outputs": [],
    },
    {
        "name": "withdraw",
        "type": "function",
        "stateMutability": "nonpayable",
        "inputs": [
            {"name": "asset", "type": "address"},
            {"name": "amount", "type": "uint256"},
            {"name": "to", "type": "address"},
        ],
        "outputs": [{"name": "", "type": "uint256"}],
    },
    {
        "name": "borrow",
        "type": "function",
        "stateMutability": "nonpayable",
        "inputs": [
            {"name": "asset", "type": "address"},
            {"name": "amount", "type": "uint256"},
            {"name": "interestRateMode", "type": "uint256"},
            {"name": "referralCode", "type": "uint16"},
            {"name": "onBehalfOf", "type": "address"},
        ],
        "outputs": [],
    },
    {
        "name": "repay",
        "type": "function",
        "stateMutability": "nonpayable",
        "inputs": [
            {"name": "asset", "type": "address"},
            {"name": "amount", "type": "uint256"},
            {"name": "interestRateMode", "type": "uint256"},
            {"name": "onBehalfOf", "type": "address"},
        ],
        "outputs": [{"name": "", "type": "uint256"}],
    },
    {
        "name": "getUserAccountData",
        "type": "function",
        "stateMutability": "view",
        "inputs": [{"name": "user", "type": "address"}],
        "outputs": [
            {"name": "totalCollateralBase", "type": "uint256"},
            {"name": "totalDebtBase", "type": "uint256"},
            {"name": "availableBorrowsBase", "type": "uint256"},
            {"name": "currentLiquidationThreshold", "type": "uint256"},
            {"name": "ltv", "type": "uint256"},
            {"name": "healthFactor", "type": "uint256"},
        ],
    },
]

POOL_DATA_PROVIDER_ABI = [
    {
        "name": "getUserReserveData",
        "type": "function",
        "stateMutability": "view",
        "inputs": [
            {"name": "asset", "type": "address"},
            {"name": "user", "type": "address"},
        ],
        "outputs": [
            {"name": "currentATokenBalance", "type": "uint256"},
            {"name": "currentStableDebt", "type": "uint256"},
            {"name": "currentVariableDebt", "type": "uint256"},
            {"name": "principalStableDebt", "type": "uint256"},
            {"name": "scaledVariableDebt", "type": "uint256"},
            {"name": "stableBorrowRate", "type": "uint256"},
            {"name": "liquidityRate", "type": "uint256"},
            {"name": "stableRateLastUpdated", "type": "uint40"},
            {"name": "usageAsCollateralEnabled", "type": "bool"},
        ],
    },
    {
        "name": "getReserveData",
        "type": "function",
        "stateMutability": "view",
        "inputs": [{"name": "asset", "type": "address"}],
        "outputs": [
            {"name": "unbacked", "type": "uint256"},
            {"name": "accruedToTreasuryScaled", "type": "uint256"},
            {"name": "totalAToken", "type": "uint256"},
            {"name": "totalStableDebt", "type": "uint256"},
            {"name": "totalVariableDebt", "type": "uint256"},
            {"name": "liquidityRate", "type": "uint256"},
            {"name": "variableBorrowRate", "type": "uint256"},
            {"name": "stableBorrowRate", "type": "uint256"},
            {"name": "averageStableBorrowRate", "type": "uint256"},
            {"name": "liquidityIndex", "type": "uint256"},
            {"name": "variableBorrowIndex", "type": "uint256"},
            {"name": "lastUpdateTimestamp", "type": "uint40"},
        ],
    },
]

ERC20_ABI = [
    {
        "name": "approve",
        "type": "function",
        "stateMutability": "nonpayable",
        "inputs": [
            {"name": "spender", "type": "address"},
            {"name": "amount", "type": "uint256"},
        ],
        "outputs": [{"name": "", "type": "bool"}],
    },
    {
        "name": "allowance",
        "type": "function",
        "stateMutability": "view",
        "inputs": [
            {"name": "owner", "type": "address"},
            {"name": "spender", "type": "address"},
        ],
        "outputs": [{"name": "", "type": "uint256"}],
    },
    {
        "name": "balanceOf",
        "type": "function",
        "stateMutability": "view",
        "inputs": [{"name": "account", "type": "address"}],
        "outputs": [{"name": "", "type": "uint256"}],
    },
]

# ---------------------------------------------------------------------------
# Deployed addresses per chain  (Aave V3 canonical deployments)
# ---------------------------------------------------------------------------

AAVE_V3_ADDRESSES: dict[str, dict[str, str]] = {
    "ethereum": {
        "pool": "0x87870Bca3F3fD6335C3F4ce8392D69350B4fA4E2",
        "pool_data_provider": "0x7B4EB56E7CD4b454BA8ff71E4518426c6B507677",
    },
    "arbitrum": {
        "pool": "0x794a61358D6845594F94dc1DB02A252b5b4814aD",
        "pool_data_provider": "0x69FA688f1Dc47d4B5d8029D5a35FB7a548310654",
    },
    "optimism": {
        "pool": "0x794a61358D6845594F94dc1DB02A252b5b4814aD",
        "pool_data_provider": "0x69FA688f1Dc47d4B5d8029D5a35FB7a548310654",
    },
    "base": {
        "pool": "0xA238Dd80C259a72e81d7e4664a9801593F98d1c5",
        "pool_data_provider": "0x2d8A3C5677189723C4cB8873CfC9C8976FDF38Ac",
    },
    "polygon": {
        "pool": "0x794a61358D6845594F94dc1DB02A252b5b4814aD",
        "pool_data_provider": "0x69FA688f1Dc47d4B5d8029D5a35FB7a548310654",
    },
}

# ---------------------------------------------------------------------------
# Supported assets — token addresses per chain
# ---------------------------------------------------------------------------

SUPPORTED_ASSETS: dict[str, dict[str, str]] = {
    "ethereum": {
        "USDC": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
        "USDT": "0xdAC17F958D2ee523a2206206994597C13D831ec7",
        "DAI": "0x6B175474E89094C44Da98b954EedeAC495271d0F",
        "WETH": "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2",
    },
    "arbitrum": {
        "USDC": "0xaf88d065e77c8cC2239327C5EDb3A432268e5831",
        "USDT": "0xFd086bC7CD5C481DCC9C85ebE478A1C0b69FCbb9",
        "DAI": "0xDA10009cBd5D07dd0CeCc66161FC93D7c9000da1",
        "WETH": "0x82aF49447D8a07e3bd95BD0d56f35241523fBab1",
    },
    "optimism": {
        "USDC": "0x0b2C639c533813f4Aa9D7837CAf62653d097Ff85",
        "USDT": "0x94b008aA00579c1307B0EF2c499aD98a8ce58e58",
        "DAI": "0xDA10009cBd5D07dd0CeCc66161FC93D7c9000da1",
        "WETH": "0x4200000000000000000000000000000000000006",
    },
    "base": {
        "USDC": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
        "DAI": "0x50c5725949A6F0c72E6C4a641F24049A917DB0Cb",
        "WETH": "0x4200000000000000000000000000000000000006",
    },
    "polygon": {
        "USDC": "0x3c499c542cEF5E3811e1192ce70d8cC03d5c3359",
        "USDT": "0xc2132D05D31c914a87C6611C10748AEb04B58e8F",
        "DAI": "0x8f3Cf7ad23Cd3CaDbD9735AFf958023239c6A063",
        "WETH": "0x7ceB23fD6bC0adD59E62ac25578270cFf1b9f619",
    },
}


# ---------------------------------------------------------------------------
# Data-classes for structured results
# ---------------------------------------------------------------------------

@dataclass
class HealthReport:
    total_collateral_usd: float
    total_debt_usd: float
    available_borrows_usd: float
    ltv: float
    liquidation_threshold: float
    health_factor: float
    is_safe: bool = True

    def __post_init__(self):
        self.is_safe = self.health_factor > 1.5


@dataclass
class SupplyResult:
    success: bool
    tx_hash: Optional[str] = None
    asset: str = ""
    amount: float = 0.0
    chain: str = ""
    simulated: bool = True
    gas_spent: float = 0.0
    error: Optional[str] = None


@dataclass
class WithdrawResult:
    success: bool
    tx_hash: Optional[str] = None
    asset: str = ""
    amount: float = 0.0
    chain: str = ""
    simulated: bool = True
    gas_spent: float = 0.0
    error: Optional[str] = None


@dataclass
class BorrowResult:
    success: bool
    tx_hash: Optional[str] = None
    asset: str = ""
    amount: float = 0.0
    chain: str = ""
    interest_rate_mode: int = 2
    simulated: bool = True
    gas_spent: float = 0.0
    error: Optional[str] = None


# ---------------------------------------------------------------------------
# Core protocol interface
# ---------------------------------------------------------------------------

class AaveV3Protocol:
    """Interface to Aave V3 Pool and PoolDataProvider contracts.

    In *simulate* mode every call is dry-run: logged but never sent on-chain.
    """

    SUPPORTED_CHAINS = list(AAVE_V3_ADDRESSES.keys())

    def __init__(self, chain: str, *, simulate: bool = True):
        if chain not in AAVE_V3_ADDRESSES:
            raise ValueError(
                f"Aave V3 not available on '{chain}'. "
                f"Supported: {self.SUPPORTED_CHAINS}"
            )
        self.chain = chain
        self.simulate = simulate
        self.addresses = AAVE_V3_ADDRESSES[chain]
        self.assets = SUPPORTED_ASSETS.get(chain, {})
        self._pool = None
        self._data_provider = None
        self._web3 = None

        if not simulate:
            self._connect()

    # ------ connection helpers (live mode only) ------

    def _connect(self):
        from web3 import Web3
        from ..chains.evm import CHAINS

        chain_cfg = CHAINS.get(self.chain)
        if chain_cfg is None:
            raise ValueError(f"No chain config for {self.chain}")

        self._web3 = Web3(Web3.HTTPProvider(chain_cfg.rpc_url))
        self._pool = self._web3.eth.contract(
            address=Web3.to_checksum_address(self.addresses["pool"]),
            abi=POOL_ABI,
        )
        self._data_provider = self._web3.eth.contract(
            address=Web3.to_checksum_address(self.addresses["pool_data_provider"]),
            abi=POOL_DATA_PROVIDER_ABI,
        )
        logger.info(f"Connected to Aave V3 on {self.chain}")

    # ------ public API ------

    def get_supported_assets(self) -> list[str]:
        """Return asset symbols available on the current chain."""
        return list(self.assets.keys())

    def resolve_asset(self, symbol: str) -> str:
        """Resolve a symbol (e.g. 'USDC') to its on-chain address."""
        addr = self.assets.get(symbol.upper())
        if addr is None:
            raise ValueError(
                f"Asset '{symbol}' not supported on {self.chain}. "
                f"Available: {list(self.assets.keys())}"
            )
        return addr

    # ------ supply / withdraw / borrow ------

    def supply(self, wallet_address: str, asset_symbol: str,
               amount: float, *, private_key: str = None) -> SupplyResult:
        """Supply (deposit) *amount* of *asset_symbol* into Aave V3."""
        asset_address = self.resolve_asset(asset_symbol)

        if self.simulate:
            return self._simulate_supply(wallet_address, asset_symbol, amount)

        return self._live_supply(
            wallet_address, asset_address, asset_symbol, amount, private_key,
        )

    def withdraw(self, wallet_address: str, asset_symbol: str,
                 amount: float, *, private_key: str = None) -> WithdrawResult:
        """Withdraw *amount* of *asset_symbol* from Aave V3."""
        asset_address = self.resolve_asset(asset_symbol)

        if self.simulate:
            return self._simulate_withdraw(wallet_address, asset_symbol, amount)

        return self._live_withdraw(
            wallet_address, asset_address, asset_symbol, amount, private_key,
        )

    def borrow(self, wallet_address: str, asset_symbol: str,
               amount: float, *, interest_rate_mode: int = 2,
               private_key: str = None) -> BorrowResult:
        """Borrow *amount* of *asset_symbol*.  interest_rate_mode: 1=stable, 2=variable."""
        asset_address = self.resolve_asset(asset_symbol)

        if self.simulate:
            return self._simulate_borrow(
                wallet_address, asset_symbol, amount, interest_rate_mode,
            )

        return self._live_borrow(
            wallet_address, asset_address, asset_symbol, amount,
            interest_rate_mode, private_key,
        )

    # ------ health factor ------

    def get_health_factor(self, wallet_address: str) -> HealthReport:
        """Query on-chain health factor (or return a safe dummy in sim mode)."""
        if self.simulate:
            return HealthReport(
                total_collateral_usd=10_000.0,
                total_debt_usd=0.0,
                available_borrows_usd=7_500.0,
                ltv=0.75,
                liquidation_threshold=0.82,
                health_factor=float("inf"),
            )

        data = self._pool.functions.getUserAccountData(
            self._web3.to_checksum_address(wallet_address),
        ).call()

        hf = data[5] / 1e18 if data[5] > 0 else float("inf")
        return HealthReport(
            total_collateral_usd=data[0] / 1e8,
            total_debt_usd=data[1] / 1e8,
            available_borrows_usd=data[2] / 1e8,
            ltv=data[4] / 1e4,
            liquidation_threshold=data[3] / 1e4,
            health_factor=hf,
        )

    # ------ simulation helpers ------

    def _simulate_supply(self, wallet: str, symbol: str,
                         amount: float) -> SupplyResult:
        import random
        tx = f"0x{''.join(random.choices('abcdef0123456789', k=64))}"
        gas = round(random.uniform(0.0005, 0.003), 6)
        logger.info(
            f"[SIM] Aave V3 supply {amount} {symbol} on {self.chain} "
            f"from {wallet[:10]}… → tx {tx[:16]}…"
        )
        return SupplyResult(
            success=True, tx_hash=tx, asset=symbol,
            amount=amount, chain=self.chain, simulated=True, gas_spent=gas,
        )

    def _simulate_withdraw(self, wallet: str, symbol: str,
                           amount: float) -> WithdrawResult:
        import random
        tx = f"0x{''.join(random.choices('abcdef0123456789', k=64))}"
        gas = round(random.uniform(0.0005, 0.003), 6)
        logger.info(
            f"[SIM] Aave V3 withdraw {amount} {symbol} on {self.chain} "
            f"to {wallet[:10]}… → tx {tx[:16]}…"
        )
        return WithdrawResult(
            success=True, tx_hash=tx, asset=symbol,
            amount=amount, chain=self.chain, simulated=True, gas_spent=gas,
        )

    def _simulate_borrow(self, wallet: str, symbol: str, amount: float,
                         rate_mode: int) -> BorrowResult:
        import random
        tx = f"0x{''.join(random.choices('abcdef0123456789', k=64))}"
        gas = round(random.uniform(0.0005, 0.003), 6)
        mode_label = "stable" if rate_mode == 1 else "variable"
        logger.info(
            f"[SIM] Aave V3 borrow {amount} {symbol} ({mode_label}) on "
            f"{self.chain} for {wallet[:10]}… → tx {tx[:16]}…"
        )
        return BorrowResult(
            success=True, tx_hash=tx, asset=symbol, amount=amount,
            chain=self.chain, interest_rate_mode=rate_mode,
            simulated=True, gas_spent=gas,
        )

    # ------ live transaction helpers ------

    def _live_supply(self, wallet: str, asset_addr: str, symbol: str,
                     amount: float, private_key: str) -> SupplyResult:
        try:
            w3 = self._web3
            amount_wei = int(amount * 1e18) if symbol == "WETH" else int(amount * 1e6)

            # Approve pool to spend asset
            token = w3.eth.contract(
                address=w3.to_checksum_address(asset_addr), abi=ERC20_ABI,
            )
            pool_addr = w3.to_checksum_address(self.addresses["pool"])
            nonce = w3.eth.get_transaction_count(w3.to_checksum_address(wallet))

            approve_tx = token.functions.approve(pool_addr, amount_wei).build_transaction({
                "from": w3.to_checksum_address(wallet),
                "nonce": nonce,
                "gas": 60000,
                "gasPrice": w3.eth.gas_price,
            })
            signed = w3.eth.account.sign_transaction(approve_tx, private_key)
            w3.eth.send_raw_transaction(signed.raw_transaction)

            # Supply
            nonce += 1
            supply_tx = self._pool.functions.supply(
                w3.to_checksum_address(asset_addr),
                amount_wei,
                w3.to_checksum_address(wallet),
                0,
            ).build_transaction({
                "from": w3.to_checksum_address(wallet),
                "nonce": nonce,
                "gas": 300000,
                "gasPrice": w3.eth.gas_price,
            })
            signed = w3.eth.account.sign_transaction(supply_tx, private_key)
            tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
            receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
            gas_cost = receipt.gasUsed * receipt.effectiveGasPrice / 1e18

            return SupplyResult(
                success=receipt.status == 1,
                tx_hash=tx_hash.hex(),
                asset=symbol, amount=amount, chain=self.chain,
                simulated=False, gas_spent=gas_cost,
            )
        except Exception as exc:
            logger.error(f"Aave V3 supply failed: {exc}")
            return SupplyResult(success=False, error=str(exc), asset=symbol,
                                amount=amount, chain=self.chain, simulated=False)

    def _live_withdraw(self, wallet: str, asset_addr: str, symbol: str,
                       amount: float, private_key: str) -> WithdrawResult:
        try:
            w3 = self._web3
            amount_wei = int(amount * 1e18) if symbol == "WETH" else int(amount * 1e6)
            nonce = w3.eth.get_transaction_count(w3.to_checksum_address(wallet))

            withdraw_tx = self._pool.functions.withdraw(
                w3.to_checksum_address(asset_addr),
                amount_wei,
                w3.to_checksum_address(wallet),
            ).build_transaction({
                "from": w3.to_checksum_address(wallet),
                "nonce": nonce,
                "gas": 300000,
                "gasPrice": w3.eth.gas_price,
            })
            signed = w3.eth.account.sign_transaction(withdraw_tx, private_key)
            tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
            receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
            gas_cost = receipt.gasUsed * receipt.effectiveGasPrice / 1e18

            return WithdrawResult(
                success=receipt.status == 1,
                tx_hash=tx_hash.hex(),
                asset=symbol, amount=amount, chain=self.chain,
                simulated=False, gas_spent=gas_cost,
            )
        except Exception as exc:
            logger.error(f"Aave V3 withdraw failed: {exc}")
            return WithdrawResult(success=False, error=str(exc), asset=symbol,
                                  amount=amount, chain=self.chain, simulated=False)

    def _live_borrow(self, wallet: str, asset_addr: str, symbol: str,
                     amount: float, rate_mode: int,
                     private_key: str) -> BorrowResult:
        try:
            w3 = self._web3
            amount_wei = int(amount * 1e18) if symbol == "WETH" else int(amount * 1e6)
            nonce = w3.eth.get_transaction_count(w3.to_checksum_address(wallet))

            borrow_tx = self._pool.functions.borrow(
                w3.to_checksum_address(asset_addr),
                amount_wei,
                rate_mode,
                0,
                w3.to_checksum_address(wallet),
            ).build_transaction({
                "from": w3.to_checksum_address(wallet),
                "nonce": nonce,
                "gas": 350000,
                "gasPrice": w3.eth.gas_price,
            })
            signed = w3.eth.account.sign_transaction(borrow_tx, private_key)
            tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
            receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
            gas_cost = receipt.gasUsed * receipt.effectiveGasPrice / 1e18

            return BorrowResult(
                success=receipt.status == 1,
                tx_hash=tx_hash.hex(),
                asset=symbol, amount=amount, chain=self.chain,
                interest_rate_mode=rate_mode,
                simulated=False, gas_spent=gas_cost,
            )
        except Exception as exc:
            logger.error(f"Aave V3 borrow failed: {exc}")
            return BorrowResult(success=False, error=str(exc), asset=symbol,
                                amount=amount, chain=self.chain, simulated=False)

from typing import Dict, Any, Optional
from web3 import Web3
import logging

logger = logging.getLogger(__name__)

class ProtocolClient:
    """
    A placeholder client for interacting with Aave V3 or Compound V3.
    In a real implementation, this would handle ABI loading, contract initialization,
    and specific protocol interactions (deposit, withdraw, etc.) for the chosen protocol.
    """
    def __init__(self, web3: Web3, protocol_name: str, config: Dict[str, Any]):
        self.web3 = web3
        self.protocol_name = protocol_name
        self.config = config
        # TODO: Load actual contract ABIs and addresses from config
        # self.contract = self.web3.eth.contract(address=config["router_address"], abi=config["abi"])
        logger.info(f"Initialized {protocol_name} client for chain_id={self.web3.eth.chain_id}")
        logger.debug(f"ProtocolClient config: {config}")

    def deposit(self, wallet_address: str, asset_address: str, amount: int, simulate: bool = False) -> Optional[str]:
        """
        Deposits a specified amount of an asset into the lending protocol.
        """
        action_desc = f"Deposit {self.web3.from_wei(amount, 'ether')} of {asset_address} to {self.protocol_name} from {wallet_address}"
        if simulate:
            logger.info(f"[SIMULATION] {action_desc}")
            return None
        
        logger.info(action_desc)
        # TODO: Implement actual contract interaction for deposit
        # Example:
        # tx_hash = self.contract.functions.deposit(asset_address, amount).transact({'from': wallet_address})
        # return tx_hash
        # For now, return a mock transaction hash
        return f"mock_tx_hash_{self.protocol_name}_deposit_{wallet_address}_{amount}"

    def withdraw(self, wallet_address: str, asset_address: str, amount: int, simulate: bool = False) -> Optional[str]:
        """
        Withdraws a specified amount of an asset from the lending protocol.
        """
        action_desc = f"Withdraw {self.web3.from_wei(amount, 'ether')} of {asset_address} from {self.protocol_name} to {wallet_address}"
        if simulate:
            logger.info(f"[SIMULATION] {action_desc}")
            return None

        logger.info(action_desc)
        # TODO: Implement actual contract interaction for withdraw
        # Example:
        # tx_hash = self.contract.functions.withdraw(asset_address, amount).transact({'from': wallet_address})
        # return tx_hash
        # For now, return a mock transaction hash
        return f"mock_tx_hash_{self.protocol_name}_withdraw_{wallet_address}_{amount}"

class InteractionTracker:
    """
    Tracks protocol interaction counts per wallet.
    In a real application, this would use a database or persistent storage
    to ensure data persistence across agent runs.
    """
    def __init__(self):
        self._counts: Dict[str, int] = {} # {wallet_address: count}
        logger.info("Initialized InteractionTracker.")

    def increment(self, wallet_address: str):
        """Increments the interaction count for a given wallet."""
        self._counts[wallet_address] = self._counts.get(wallet_address, 0) + 1
        logger.debug(f"Interaction count for {wallet_address}: {self._counts[wallet_address]}")

    def get_count(self, wallet_address: str) -> int:
        """Returns the current interaction count for a given wallet."""
        return self._counts.get(wallet_address, 0)

    def get_all_counts(self) -> Dict[str, int]:
        """Returns all tracked interaction counts."""
        return self._counts.copy()

class LendingStrategy:
    """
    Lending protocol strategy for Aave V3 or Compound V3.
    Deposits/withdraws assets to accumulate protocol interactions for airdrop eligibility.
    """
    def __init__(self,
                 protocol_name: str, # "AaveV3" or "CompoundV3"
                 asset_address: str, # Address of the asset to deposit/withdraw
                 amount_to_deposit: int, # Amount in wei
                 amount_to_withdraw: int, # Amount in wei
                 protocol_config: Dict[str, Any], # e.g., router/pool addresses, ABI paths
                 interaction_tracker: InteractionTracker,
                 initial_action: str = "deposit" # "deposit" or "withdraw" for the first action
                 ):
        if protocol_name not in ["AaveV3", "CompoundV3"]:
            raise ValueError("Protocol must be 'AaveV3' or 'CompoundV3'")
        if initial_action not in ["deposit", "withdraw"]:
            raise ValueError("Initial action must be 'deposit' or 'withdraw'")

        self.protocol_name = protocol_name
        self.asset_address = asset_address
        self.amount_to_deposit = amount_to_deposit
        self.amount_to_withdraw = amount_to_withdraw
        self.protocol_config = protocol_config
        self.interaction_tracker = interaction_tracker
        
        # Internal state to manage simple alternating schedule for each wallet
        # A more complex scheduler (e.g., time-based) would be handled by the FarmingAgent
        self._next_action_map: Dict[str, str] = {} # {wallet_address: "deposit" | "withdraw"}
        self.initial_action = initial_action # Default first action

        logger.info(f"Initialized LendingStrategy for {protocol_name}: asset={asset_address}, deposit={amount_to_deposit}, withdraw={amount_to_withdraw}")
        logger.debug(f"Strategy config: {protocol_config}")

    def _get_protocol_client(self, web3: Web3) -> ProtocolClient:
        """
        Returns a ProtocolClient instance, initialized with the given web3 connection.
        This allows the client to be created per execution context if needed.
        """
        return ProtocolClient(web3, self.protocol_name, self.protocol_config)

    def execute(self,
                wallet_address: str,
                web3: Web3,
                simulate: bool = False,
                ) -> bool:
        """
        Executes the lending strategy for a given wallet.
        Decides whether to deposit or withdraw based on internal schedule logic.

        Args:
            wallet_address: The address of the wallet to use.
            web3: A connected web3 instance for blockchain interaction.
            simulate: If True, performs a dry-run without sending transactions.

        Returns:
            True if an action was attempted (even if simulated), False otherwise.
        """
        logger.info(f"Executing LendingStrategy for wallet {wallet_address} (simulate={simulate})")

        protocol_client = self._get_protocol_client(web3)
        action_performed = False

        # Determine the next action for this wallet
        # If no action recorded, use the initial_action
        current_next_action = self._next_action_map.get(wallet_address, self.initial_action)

        tx_hash: Optional[str] = None
        if current_next_action == "deposit":
            tx_hash = protocol_client.deposit(wallet_address, self.asset_address, self.amount_to_deposit, simulate)
            if simulate or tx_hash:
                self.interaction_tracker.increment(wallet_address)
                self._next_action_map[wallet_address] = "withdraw" # Next time, withdraw
                action_performed = True
                logger.info(f"Strategy for {wallet_address}: Deposited {self.web3.from_wei(self.amount_to_deposit, 'ether')}. Tx: {tx_hash or 'SIMULATED'}")
            else:
                logger.error(f"Failed to deposit for {wallet_address}. Tx_hash was None.")
        elif current_next_action == "withdraw":
            tx_hash = protocol_client.withdraw(wallet_address, self.asset_address, self.amount_to_withdraw, simulate)
            if simulate or tx_hash:
                self.interaction_tracker.increment(wallet_address)
                self._next_action_map[wallet_address] = "deposit" # Next time, deposit
                action_performed = True
                logger.info(f"Strategy for {wallet_address}: Withdrew {self.web3.from_wei(self.amount_to_withdraw, 'ether')}. Tx: {tx_hash or 'SIMULATED'}")
            else:
                logger.error(f"Failed to withdraw for {wallet_address}. Tx_hash was None.")
        
        if not action_performed:
            logger.warning(f"No action performed for wallet {wallet_address}. Current next action: {current_next_action}")

        return action_performed

    def get_interaction_counts(self) -> Dict[str, int]:
        """
        Returns the current interaction counts for all wallets managed by this strategy.
        """
        return self.interaction_tracker.get_all_counts()

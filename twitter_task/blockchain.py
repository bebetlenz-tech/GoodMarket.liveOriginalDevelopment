
import os
import logging
from web3 import Web3
from eth_account import Account

logger = logging.getLogger(__name__)

class TwitterTaskBlockchain:
    """Twitter Task Direct Private Key Disbursement"""

    def __init__(self):
        # Network configuration
        self.celo_rpc_url = os.getenv('CELO_RPC_URL', 'https://forno.celo.org')
        self.chain_id = int(os.getenv('CHAIN_ID', 42220))
        self.gooddollar_contract = os.getenv('GOODDOLLAR_CONTRACT', '0x62B8B11039FcfE5aB0C56E502b1C372A3d2a9c7A')

        # Private key for Twitter Task disbursements
        self.task_key = os.getenv('TASK_KEY')

        # Initialize Web3
        self.w3 = Web3(Web3.HTTPProvider(self.celo_rpc_url))

        if self.w3.is_connected():
            logger.info("✅ Connected to Celo network for Twitter Task")
        else:
            logger.error("❌ Failed to connect to Celo network")

        logger.info("🐦 Twitter Task Private Key Service initialized")

    def mask_wallet_address(self, wallet_address: str) -> str:
        """Mask wallet address for logging"""
        if not wallet_address or len(wallet_address) < 10:
            return wallet_address
        return wallet_address[:6] + "..." + wallet_address[-4:]

    async def disburse_twitter_reward(self, wallet_address: str, amount: float) -> dict:
        """
        Disburse Twitter Task rewards via direct private key transfer

        Args:
            wallet_address: Recipient wallet address
            amount: Amount in G$ to disburse

        Returns:
            dict: Result with success status, tx_hash, or error
        """
        try:
            logger.info(f"🐦 Starting Twitter reward disbursement: {amount} G$ to {self.mask_wallet_address(wallet_address)}")

            if not self.task_key:
                logger.error("❌ TASK_KEY not configured")
                return {"success": False, "error": "Task key not configured"}

            # Get task account from private key
            try:
                task_account = Account.from_key(self.task_key)
                logger.info(f"✅ Task account loaded: {self.mask_wallet_address(task_account.address)}")
            except Exception as key_error:
                logger.error(f"❌ Failed to load task account: {key_error}")
                return {"success": False, "error": "Invalid task key"}

            # Load GoodDollar contract
            erc20_abi = [
                {
                    "constant": False,
                    "inputs": [
                        {"name": "_to", "type": "address"},
                        {"name": "_value", "type": "uint256"}
                    ],
                    "name": "transfer",
                    "outputs": [{"name": "", "type": "bool"}],
                    "type": "function"
                },
                {
                    "constant": True,
                    "inputs": [],
                    "name": "decimals",
                    "outputs": [{"name": "", "type": "uint8"}],
                    "type": "function"
                },
                {
                    "constant": True,
                    "inputs": [{"name": "_owner", "type": "address"}],
                    "name": "balanceOf",
                    "outputs": [{"name": "balance", "type": "uint256"}],
                    "type": "function"
                }
            ]

            contract = self.w3.eth.contract(
                address=Web3.to_checksum_address(self.gooddollar_contract),
                abi=erc20_abi
            )

            # Get decimals
            try:
                decimals = contract.functions.decimals().call()
                logger.info(f"📊 Token decimals: {decimals}")
            except Exception as decimals_error:
                logger.error(f"❌ Failed to get token decimals: {decimals_error}")
                return {"success": False, "error": "Failed to get token decimals"}

            # Convert amount to wei
            amount_wei = int(amount * (10 ** decimals))
            logger.info(f"💰 Amount in wei: {amount_wei}")

            # Check balance
            try:
                balance = contract.functions.balanceOf(task_account.address).call()
                logger.info(f"💵 Task account balance: {balance / (10 ** decimals)} G$")

                if balance < amount_wei:
                    logger.error(f"❌ Insufficient balance: {balance / (10 ** decimals)} G$ < {amount} G$")
                    return {"success": False, "error": "insufficient_balance", "error_type": "insufficient_balance"}
            except Exception as balance_error:
                logger.error(f"❌ Failed to check balance: {balance_error}")
                return {"success": False, "error": "Failed to check balance"}

            # Get network information
            try:
                nonce = self.w3.eth.get_transaction_count(task_account.address)
                gas_price_wei = self.w3.eth.gas_price
                gas_price = int(gas_price_wei * 1.2)
                logger.info(f"⛽ Gas price set to: {gas_price} wei")
            except Exception as network_error:
                logger.error(f"❌ Failed to get network information: {network_error}")
                return {"success": False, "error": "Network error"}

            # Build the transfer transaction
            try:
                transfer_txn = contract.functions.transfer(
                    Web3.to_checksum_address(wallet_address),
                    amount_wei
                ).build_transaction({
                    'chainId': self.chain_id,
                    'gas': 250000,
                    'gasPrice': gas_price,
                    'nonce': nonce,
                    'from': task_account.address
                })
            except Exception as build_txn_error:
                logger.error(f"❌ Failed to build transfer transaction: {build_txn_error}")
                return {"success": False, "error": "Failed to build transaction"}

            # Sign transaction
            try:
                signed_txn = self.w3.eth.account.sign_transaction(transfer_txn, self.task_key)
                logger.info("✅ Transaction signed successfully")
            except Exception as sign_error:
                logger.error(f"❌ Failed to sign transaction: {sign_error}")
                return {"success": False, "error": "Failed to sign transaction"}

            # Send transaction
            try:
                tx_hash = self.w3.eth.send_raw_transaction(signed_txn.raw_transaction)
                tx_hash_hex = tx_hash.hex()
                if not tx_hash_hex.startswith('0x'):
                    tx_hash_hex = '0x' + tx_hash_hex
                logger.info(f"📤 Transaction sent: {tx_hash_hex}")
            except Exception as send_error:
                logger.error(f"❌ Failed to send transaction: {send_error}")
                return {"success": False, "error": f"Failed to send transaction: {str(send_error)}"}

            # Wait for confirmation
            try:
                receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)

                if receipt.status == 1:
                    logger.info(f"✅ Twitter reward disbursement successful: {tx_hash_hex}")
                    return {
                        "success": True,
                        "tx_hash": tx_hash_hex,
                        "amount": amount,
                        "recipient": wallet_address
                    }
                else:
                    logger.error(f"❌ Transaction failed on-chain: {tx_hash_hex}")
                    return {"success": False, "error": "Transaction failed on-chain", "tx_hash": tx_hash_hex}

            except Exception as receipt_error:
                logger.error(f"❌ Failed to get transaction receipt: {receipt_error}")
                return {"success": False, "error": "Transaction timeout", "tx_hash": tx_hash_hex}

        except Exception as e:
            logger.error(f"❌ Twitter reward disbursement error: {e}")
            import traceback
            logger.error(f"🔍 Traceback: {traceback.format_exc()}")
            return {"success": False, "error": str(e)}

    def disburse_twitter_reward_sync(self, wallet_address: str, amount: float) -> dict:
        """Synchronous wrapper for async disbursement"""
        import asyncio
        import concurrent.futures

        try:
            # Try to get the running event loop
            loop = asyncio.get_running_loop()
            # If we're already in an async context, execute in separate thread
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(self._run_in_new_loop, wallet_address, amount)
                return future.result()
        except RuntimeError:
            # No running loop, safe to use asyncio.run
            return asyncio.run(self.disburse_twitter_reward(wallet_address, amount))
        except Exception as e:
            logger.error(f"❌ Sync disbursement wrapper error: {e}")
            return {"success": False, "error": str(e)}

    def _run_in_new_loop(self, wallet_address: str, amount: float) -> dict:
        """Helper to run async function in a new loop in a separate thread"""
        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(self.disburse_twitter_reward(wallet_address, amount))
        finally:
            loop.close()

# Global instance
twitter_blockchain_service = TwitterTaskBlockchain()

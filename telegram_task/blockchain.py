
import os
import asyncio
import logging
from datetime import datetime
from web3 import Web3
from eth_account import Account
from supabase_client import get_supabase_client

logger = logging.getLogger(__name__)

class TelegramTaskBlockchain:
    """Telegram Task Direct Private Key Disbursement"""

    def __init__(self):
        # Network configuration
        self.celo_rpc_url = os.getenv('CELO_RPC_URL', 'https://forno.celo.org')
        self.chain_id = int(os.getenv('CHAIN_ID', 42220))
        self.gooddollar_contract = os.getenv('GOODDOLLAR_CONTRACT', '0x62B8B11039FcfE5aB0C56E502b1C372A3d2a9c7A')

        # Private key for Telegram Task disbursements
        self.task_key = os.getenv('TASK_KEY')

        # Initialize Web3
        self.w3 = Web3(Web3.HTTPProvider(self.celo_rpc_url))

        if self.w3.is_connected():
            logger.info("✅ Connected to Celo network for Telegram Task")
        else:
            logger.error("❌ Failed to connect to Celo network")

        logger.info("📱 Telegram Task Private Key Service initialized")

    def mask_wallet_address(self, wallet_address: str) -> str:
        """Mask wallet address for logging"""
        if not wallet_address or len(wallet_address) < 10:
            return wallet_address
        return wallet_address[:6] + "..." + wallet_address[-4:]

    async def disburse_telegram_reward(self, wallet_address: str, amount: float) -> dict:
        """
        Disburse Telegram Task rewards via direct private key transfer

        Args:
            wallet_address: Recipient wallet address
            amount: Amount in G$ to disburse

        Returns:
            Dict with success status, transaction hash, and details
        """
        try:
            masked_wallet = self.mask_wallet_address(wallet_address)
            logger.info(f"📱 Telegram Task reward disbursement: {amount} G$ to {masked_wallet}")

            if not self.task_key:
                logger.error("❌ TASK_KEY not configured for Telegram Task disbursement")
                return {"success": False, "error": "Task key not configured"}

            if not self.w3.is_connected():
                logger.error("❌ Not connected to Celo network")
                return {"success": False, "error": "Blockchain connection failed"}

            # Load the account that will send the tokens
            try:
                if self.task_key.startswith('0x'):
                    task_account = Account.from_key(self.task_key)
                else:
                    task_account = Account.from_key('0x' + self.task_key)
                logger.info(f"🔑 Using Telegram Task account: {self.mask_wallet_address(task_account.address)}")
            except Exception as key_error:
                logger.error(f"❌ Failed to load TASK_KEY: {key_error}")
                return {"success": False, "error": "Key loading error"}

            # ERC20 ABI for transfer function
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
                }
            ]

            # Instantiate the GoodDollar contract
            try:
                contract = self.w3.eth.contract(
                    address=Web3.to_checksum_address(self.gooddollar_contract),
                    abi=erc20_abi
                )
            except Exception as contract_error:
                logger.error(f"❌ Failed to instantiate GoodDollar contract: {contract_error}")
                return {"success": False, "error": "Contract instantiation error"}

            # Prepare transaction details
            amount_wei = int(amount * (10 ** 18))  # Convert G$ to wei

            try:
                nonce = self.w3.eth.get_transaction_count(task_account.address)
                gas_price_wei = self.w3.eth.gas_price
                gas_price = int(gas_price_wei * 1.2)  # 20% buffer
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
                    'gas': 250000,  # 250k gas limit for Telegram Task
                    'gasPrice': gas_price,
                    'nonce': nonce,
                    'from': task_account.address
                })
            except Exception as build_txn_error:
                logger.error(f"❌ Failed to build transfer transaction: {build_txn_error}")
                return {"success": False, "error": "Transaction build error"}

            # Sign the transaction
            try:
                signed_txn = self.w3.eth.account.sign_transaction(transfer_txn, self.task_key)
            except Exception as sign_error:
                logger.error(f"❌ Failed to sign transaction: {sign_error}")
                return {"success": False, "error": "Transaction signing error"}

            # Send the transaction
            try:
                tx_hash = self.w3.eth.send_raw_transaction(signed_txn.raw_transaction)
                tx_hash_hex = tx_hash.hex()
                if not tx_hash_hex.startswith('0x'):
                    tx_hash_hex = '0x' + tx_hash_hex
                logger.info(f"🔗 Telegram Task transaction sent: {tx_hash_hex}")
            except Exception as send_error:
                logger.error(f"❌ Failed to send transaction: {send_error}")
                return {"success": False, "error": "Transaction send error"}

            # Wait for transaction receipt
            try:
                logger.info(f"⏳ Waiting for transaction {tx_hash_hex} confirmation...")
                receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=180)
            except Exception as receipt_error:
                logger.error(f"❌ Error fetching transaction receipt: {receipt_error}")
                return {
                    "success": False,
                    "error": "Receipt fetch error",
                    "tx_hash": tx_hash_hex,
                    "explorer_url": f"https://explorer.celo.org/mainnet/tx/{tx_hash_hex}"
                }

            # Check transaction status
            if receipt.status == 1:
                logger.info(f"✅ Telegram Task reward successfully disbursed to {masked_wallet}. TX: {tx_hash_hex}")
                return {
                    "success": True,
                    "tx_hash": tx_hash_hex,
                    "amount": amount,
                    "explorer_url": f"https://explorer.celo.org/mainnet/tx/{tx_hash_hex}"
                }
            else:
                logger.error(f"❌ Telegram Task transaction failed on-chain. TX: {tx_hash_hex}")

                # Try to get revert reason
                try:
                    tx = self.w3.eth.get_transaction(tx_hash)
                    replay_tx = {
                        'from': tx['from'],
                        'to': tx['to'],
                        'data': tx['input'],
                        'value': tx.get('value', 0)
                    }
                    self.w3.eth.call(replay_tx, tx['blockNumber'])
                except Exception as revert_error:
                    error_msg = str(revert_error).lower()
                    if "insufficient funds" in error_msg or "insufficient balance" in error_msg:
                        logger.error(f"❌ Insufficient funds in Telegram Task treasury wallet")
                        logger.error(f"❌ Treasury wallet needs refunding for telegram_task rewards")
                        return {
                            "success": False,
                            "error": "Insufficient funds in treasury",
                            "message": "The Telegram Task treasury needs to be refunded. Please contact support.",
                            "tx_hash": tx_hash_hex,
                            "explorer_url": f"https://explorer.celo.org/mainnet/tx/{tx_hash_hex}"
                        }
                    elif "execution reverted" in error_msg:
                        logger.error(f"❌ Transaction reverted: {error_msg}")
                        return {
                            "success": False,
                            "error": "Transaction reverted",
                            "message": f"Transaction failed: {error_msg}",
                            "tx_hash": tx_hash_hex,
                            "explorer_url": f"https://explorer.celo.org/mainnet/tx/{tx_hash_hex}"
                        }

                return {
                    "success": False,
                    "error": "Transaction failed on-chain",
                    "message": "Transaction was processed but failed. Please check the block explorer.",
                    "tx_hash": tx_hash_hex,
                    "explorer_url": f"https://explorer.celo.org/mainnet/tx/{tx_hash_hex}"
                }

        except Exception as e:
            logger.error(f"❌ Telegram Task reward disbursement error: {e}", exc_info=True)
            return {"success": False, "error": str(e)}

    def disburse_telegram_reward_sync(self, wallet_address: str, amount: float) -> dict:
        """Synchronous wrapper for disburse_telegram_reward to avoid event loop issues"""
        import asyncio
        import concurrent.futures

        try:
            # Check if event loop is running
            try:
                loop = asyncio.get_running_loop()
                # Already running, execute in a separate thread with new loop
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    future = pool.submit(self._run_in_new_loop, wallet_address, amount)
                    return future.result()
            except RuntimeError:
                # No running loop, safe to use asyncio.run
                return asyncio.run(self.disburse_telegram_reward(wallet_address, amount))
        except Exception as e:
            logger.error(f"❌ Sync disbursement wrapper error: {e}")
            return {"success": False, "error": str(e)}

    def _run_in_new_loop(self, wallet_address: str, amount: float) -> dict:
        """Helper to run async function in a new loop in a separate thread"""
        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(self.disburse_telegram_reward(wallet_address, amount))
        finally:
            loop.close()


# Global instance
telegram_blockchain_service = TelegramTaskBlockchain()

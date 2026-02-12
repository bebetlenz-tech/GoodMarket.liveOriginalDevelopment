
import os
import logging
from web3 import Web3
from typing import Dict, Any

logger = logging.getLogger(__name__)

class FacebookBlockchainService:
    """Blockchain service for Facebook task rewards"""
    
    def __init__(self):
        self.w3 = None
        self.gooddollar_contract = None
        self.task_key = None
        self.chain_id = None
        
        self._initialize_blockchain()
    
    def _initialize_blockchain(self):
        """Initialize blockchain connection"""
        try:
            celo_rpc_url = os.getenv('CELO_RPC_URL', 'https://forno.celo.org')
            self.w3 = Web3(Web3.HTTPProvider(celo_rpc_url))
            self.chain_id = int(os.getenv('CHAIN_ID', 42220))
            
            if not self.w3.is_connected():
                logger.error("❌ Failed to connect to Celo network")
                return False
            
            gooddollar_address = os.getenv('GOODDOLLAR_CONTRACT', '0x62B8B11039FcfE5aB0C56E502b1C372A3d2a9c7A')
            
            erc20_abi = [
                {"constant": False, "inputs": [{"name": "_to", "type": "address"}, {"name": "_value", "type": "uint256"}], "name": "transfer", "outputs": [{"name": "", "type": "bool"}], "type": "function"},
                {"constant": True, "inputs": [], "name": "decimals", "outputs": [{"name": "", "type": "uint8"}], "type": "function"},
                {"constant": True, "inputs": [{"name": "_owner", "type": "address"}], "name": "balanceOf", "outputs": [{"name": "balance", "type": "uint256"}], "type": "function"}
            ]
            
            self.gooddollar_contract = self.w3.eth.contract(
                address=Web3.to_checksum_address(gooddollar_address),
                abi=erc20_abi
            )
            
            self.task_key = os.getenv('TASK_KEY')
            
            if self.task_key:
                logger.info(f"✅ Facebook blockchain service initialized")
                return True
            else:
                logger.warning("⚠️ TASK_KEY not configured")
                return False
                
        except Exception as e:
            logger.error(f"❌ Blockchain initialization error: {e}")
            return False
    
    def disburse_facebook_reward_sync(self, wallet_address: str, amount: float) -> Dict[str, Any]:
        """Disburse Facebook task reward"""
        try:
            logger.info(f"🔄 Starting Facebook reward disbursement: {amount} G$ to {wallet_address[:8]}...")
            
            if not self.w3 or not self.gooddollar_contract:
                logger.error("❌ Blockchain not initialized")
                return {'success': False, 'error': 'Blockchain not initialized'}
            
            if not self.task_key:
                logger.error("❌ TASK_KEY not configured")
                return {'success': False, 'error': 'Task key not configured'}
            
            # Check connection
            if not self.w3.is_connected():
                logger.error("❌ Web3 connection lost")
                return {'success': False, 'error': 'Blockchain connection failed'}
            
            # Get task account from private key
            from eth_account import Account
            try:
                if self.task_key.startswith('0x'):
                    task_account = Account.from_key(self.task_key)
                else:
                    task_account = Account.from_key('0x' + self.task_key)
                logger.info(f"🔑 Using Facebook Task account: {task_account.address[:6]}...{task_account.address[-4:]}")
            except Exception as key_error:
                logger.error(f"❌ Failed to load TASK_KEY: {key_error}")
                return {'success': False, 'error': 'Key loading error'}
            
            # Validate wallet address
            try:
                recipient = Web3.to_checksum_address(wallet_address)
            except Exception as e:
                logger.error(f"❌ Invalid wallet address: {e}")
                return {'success': False, 'error': f'Invalid wallet address: {str(e)}'}
            
            amount_wei = int(amount * (10 ** 18))
            logger.info(f"💰 Amount in wei: {amount_wei}")
            
            # Check task account balance
            try:
                task_balance = self.gooddollar_contract.functions.balanceOf(task_account.address).call()
                logger.info(f"💵 Task account balance: {task_balance / (10**18)} G$")
                
                if task_balance < amount_wei:
                    error_msg = f'Insufficient task account balance. Has {task_balance / (10**18)} G$, needs {amount} G$'
                    logger.error(f"❌ {error_msg}")
                    return {'success': False, 'error': error_msg}
            except Exception as e:
                logger.warning(f"⚠️ Could not check balance: {e}")
            
            # Get nonce
            nonce = self.w3.eth.get_transaction_count(task_account.address)
            logger.info(f"🔢 Nonce: {nonce}")
            
            # Get gas price with buffer
            try:
                gas_price_wei = self.w3.eth.gas_price
                gas_price = int(gas_price_wei * 1.2)  # 20% buffer
                logger.info(f"⛽ Gas price: {gas_price}")
            except Exception as e:
                logger.warning(f"⚠️ Could not get gas price, using default: {e}")
                gas_price = self.w3.to_wei('1', 'gwei')
            
            # Build transaction with 250k gas limit (same as Telegram and Twitter)
            transaction = self.gooddollar_contract.functions.transfer(
                recipient,
                amount_wei
            ).build_transaction({
                'chainId': self.chain_id,
                'from': task_account.address,
                'nonce': nonce,
                'gas': 250000,  # 250k gas limit for Facebook Task
                'gasPrice': gas_price
            })
            
            logger.info(f"📝 Transaction built: gas={transaction['gas']}, gasPrice={transaction['gasPrice']}")
            
            # Sign transaction
            signed_txn = self.w3.eth.account.sign_transaction(transaction, self.task_key)
            logger.info("✍️ Transaction signed")
            
            # Send transaction
            tx_hash = self.w3.eth.send_raw_transaction(signed_txn.raw_transaction)
            tx_hash_hex = tx_hash.hex()
            if not tx_hash_hex.startswith('0x'):
                tx_hash_hex = '0x' + tx_hash_hex
            logger.info(f"📤 Transaction sent: {tx_hash_hex}")
            
            # Wait for receipt
            logger.info("⏳ Waiting for transaction receipt...")
            receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
            
            if receipt.status == 1:
                logger.info(f"✅ Facebook reward disbursed successfully: {amount} G$ to {wallet_address[:8]}...")
                logger.info(f"📜 TX Hash: {tx_hash_hex}")
                logger.info(f"⛽ Gas used: {receipt.gasUsed}")
                return {
                    'success': True,
                    'tx_hash': tx_hash_hex,
                    'amount': amount
                }
            else:
                error_msg = f'Transaction failed with status {receipt.status}'
                logger.error(f"❌ {error_msg}")
                logger.error(f"📜 Failed TX: {tx_hash_hex}")
                return {'success': False, 'error': error_msg, 'tx_hash': tx_hash_hex}
                
        except ValueError as e:
            error_msg = str(e)
            logger.error(f"❌ ValueError in disbursement: {error_msg}")
            if 'insufficient funds' in error_msg.lower():
                return {'success': False, 'error': 'Insufficient funds for gas or transfer'}
            return {'success': False, 'error': error_msg}
        except Exception as e:
            logger.error(f"❌ Disbursement error: {e}")
            import traceback
            logger.error(f"🔍 Full traceback: {traceback.format_exc()}")
            return {'success': False, 'error': str(e)}

# Global instance
facebook_blockchain_service = FacebookBlockchainService()

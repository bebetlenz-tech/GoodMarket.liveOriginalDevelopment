
import requests
from datetime import datetime, timedelta, timezone
import logging
import os

logger = logging.getLogger("blockchain")

CELO_CHAIN_ID = int(os.getenv("CHAIN_ID", "42220"))
CELO_RPC = os.getenv("CELO_RPC_URL", "https://forno.celo.org")

GOODDOLLAR_CONTRACTS = {
    "UBI_PROXY": os.getenv("UBI_PROXY_CONTRACT", "0x43d72Ff17701B2DA814620735C39C620Ce0ea4A1"),
    "UBI_IMPLEMENTATION": "",
    "GOODDOLLAR_TOKEN": os.getenv("GOODDOLLAR_TOKEN_CONTRACT", "0x62B8B11039FcfE5aB0C56E502b1C372A3d2a9c7A"),
}

UBI_EVENT_SIGNATURES = {
    "TRANSFER": "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef",
    "UBI_CLAIMED": "0x89ed24731df6b066e4c5186901fffdba18cd9a10f07494aff900bdee260d1304",
    "UBI_CALCULATED": "0x836fa39995340265746dfe9587d9fe5c5de35b7bce778afd9b124ce1cfeafdc4",
    "UBI_CYCLE_CALCULATED": "0x83e0d535b9e84324e0a25922406398d6ff5f96d0c686204ee490e16d7670566f",
}

CUTOFF_HOURS = 24

log = logging.getLogger("blockchain")


def _topic_for_address(wallet: str) -> str:
    return "0x" + ("0" * 24) + wallet.lower().replace("0x", "")


def _format_timestamp(block_number: int) -> str:
    try:
        payload = {
            "jsonrpc": "2.0",
            "method": "eth_getBlockByNumber",
            "params": [hex(block_number), False],
            "id": 1
        }
        response = requests.post(CELO_RPC, json=payload, timeout=10)
        result = response.json()

        if "result" in result and result["result"]:
            timestamp = int(result["result"]["timestamp"], 16)
            block_time = datetime.fromtimestamp(timestamp, tz=timezone.utc)
            now = datetime.now(timezone.utc)
            diff = now - block_time

            if diff.days > 0:
                relative = f"{diff.days}d ago"
            elif diff.seconds > 3600:
                hours = diff.seconds // 3600
                relative = f"{hours}h ago"
            else:
                minutes = diff.seconds // 60
                relative = f"{minutes}m ago"

            exact_time = block_time.strftime("%b %d %Y %H:%M:%S %p (+00:00 UTC)")
            return f"{relative} | {exact_time}"
    except Exception as e:
        logger.error(f"🔍 DEBUG: Error formatting timestamp for block {block_number}: {e}")

    return f"Block #{block_number}"


def _get_latest_block_number() -> int:
    try:
        payload = {
            "jsonrpc": "2.0",
            "method": "eth_blockNumber",
            "params": [],
            "id": 1
        }
        response = requests.post(CELO_RPC, json=payload, timeout=10)
        result = response.json()
        return int(result["result"], 16)
    except Exception as e:
        print(f"🔍 DEBUG: Error getting latest block: {e}")
        return 0


def _calculate_block_range(hours_back: int) -> tuple:
    blocks_per_hour = 720
    latest_block = _get_latest_block_number()
    from_block = latest_block - (hours_back * blocks_per_hour)

    print(f"🔍 DEBUG: Block range: {from_block} to {latest_block} (last {hours_back} hours)")
    return hex(from_block), hex(latest_block)


def has_recent_ubi_claim(wallet_address: str) -> dict:
    try:
        # Get block range for last 7 days (extended for better detection)
        search_hours = max(CUTOFF_HOURS, 24 * 7)  # At least 7 days
        from_block, to_block = _calculate_block_range(search_hours)

        ubi_proxy_address = GOODDOLLAR_CONTRACTS["UBI_PROXY"]
        gooddollar_token = GOODDOLLAR_CONTRACTS["GOODDOLLAR_TOKEN"]

        all_activities = []

        # Check for G$ transfers FROM UBI Proxy TO user
        payload = {
            "jsonrpc": "2.0",
            "method": "eth_getLogs",
            "params": [{
                "fromBlock": from_block,
                "toBlock": to_block,
                "address": gooddollar_token,
                "topics": [
                    UBI_EVENT_SIGNATURES["TRANSFER"],
                    _topic_for_address(ubi_proxy_address),  # FROM: UBI Proxy
                    _topic_for_address(wallet_address)      # TO: user wallet
                ]
            }],
            "id": 1
        }

        try:
            response = requests.post(CELO_RPC, json=payload, timeout=15)
            result = response.json()

            if "error" not in result:
                logs = result.get("result", [])

                for log_entry in logs:
                    block_num = int(log_entry.get("blockNumber", "0x0"), 16)
                    tx_hash = log_entry.get("transactionHash", "Unknown")
                    timestamp_info = _format_timestamp(block_num)

                    # Extract amount
                    amount_hex = log_entry.get("data", "0x0")
                    try:
                        amount_wei = int(amount_hex, 16)
                        amount_g = amount_wei / (10 ** 18)
                    except:
                        amount_g = 0

                    all_activities.append({
                        "contract": "UBI Proxy",
                        "contract_address": ubi_proxy_address,
                        "block": block_num,
                        "tx_hash": tx_hash,
                        "timestamp": timestamp_info,
                        "method": "UBI claim",
                        "status": "success",
                        "amount": f"{amount_g:.6f} G$",
                        "activity_type": "ubi_claim"
                    })
        except Exception as e:
            logger.error(f"Error checking UBI Proxy transfers: {e}")

        # Check for UBI-specific events on UBI Proxy contract
        for event_name, event_signature in UBI_EVENT_SIGNATURES.items():
            if event_name == "TRANSFER":  # Already checked above
                continue

            # Different topic configurations for different events
            topics = [event_signature]

            # UBI claim events typically have the claimer as first indexed parameter
            if event_name in ["UBI_CLAIMED", "CLAIM", "REWARD_CLAIMED", "UBI_DISTRIBUTED", "DAILY_UBI"]:
                topics.append(_topic_for_address(wallet_address))  # claimer as indexed parameter
            else:
                # For other events, try both with and without wallet filter
                topics.append(None)  # Will check without specific wallet filter first

            payload = {
                "jsonrpc": "2.0",
                "method": "eth_getLogs",
                "params": [{
                    "fromBlock": from_block,
                    "toBlock": to_block,
                    "address": ubi_proxy_address,
                    "topics": topics
                }],
                "id": 1
            }

            try:
                response = requests.post(CELO_RPC, json=payload, timeout=15)
                result = response.json()

                if "error" not in result:
                    logs = result.get("result", [])

                    # Filter logs manually if we didn't filter by wallet in topics
                    if event_name not in ["UBI_CLAIMED", "CLAIM", "REWARD_CLAIMED", "UBI_DISTRIBUTED", "DAILY_UBI"]:
                        # Check if any topic contains our wallet address
                        filtered_logs = []
                        wallet_topic = _topic_for_address(wallet_address)
                        for log in logs:
                            log_topics = log.get("topics", [])
                            if wallet_topic in log_topics:
                                filtered_logs.append(log)
                        logs = filtered_logs

                    if len(logs) > 0:
                        for log_entry in logs:
                            block_num = int(log_entry.get("blockNumber", "0x0"), 16)
                            tx_hash = log_entry.get("transactionHash", "Unknown")
                            timestamp_info = _format_timestamp(block_num)

                            # Try to extract amount from data field
                            amount_str = "Event logged"
                            try:
                                data = log_entry.get("data", "0x")
                                if data and data != "0x":
                                    # For UBI events, amount is typically in the data field
                                    amount_wei = int(data, 16)
                                    amount_g = amount_wei / (10 ** 18)
                                    amount_str = f"{amount_g:.6f} G$"
                            except:
                                # If data parsing fails, check topics for amount
                                try:
                                    topics = log_entry.get("topics", [])
                                    if len(topics) > 2:  # Some events have amount as indexed parameter
                                        amount_wei = int(topics[2], 16)
                                        amount_g = amount_wei / (10 ** 18)
                                        amount_str = f"{amount_g:.6f} G$"
                                except:
                                    pass

                            all_activities.append({
                                "contract": "UBI Proxy",
                                "contract_address": ubi_proxy_address,
                                "block": block_num,
                                "tx_hash": tx_hash,
                                "timestamp": timestamp_info,
                                "method": event_name.lower().replace("_", " "),
                                "status": "success",
                                "amount": amount_str,
                                "activity_type": "ubi_event"
                            })
            except Exception as e:
                logger.error(f"Error checking {event_name}: {e}")

        if len(all_activities) > 0:
            # Sort by block number to get latest
            all_activities.sort(key=lambda x: x['block'], reverse=True)
            latest_activity = all_activities[0]

            # Categorize activities
            claims = [a for a in all_activities if a["activity_type"] == "ubi_claim"]
            events = [a for a in all_activities if a["activity_type"] == "ubi_event"]

            success_message = f"✅ UBI VERIFICATION SUCCESS!\n\n"
            success_message += f"🎯 Found {len(all_activities)} UBI activities from UBI Proxy contract\n"
            success_message += f"   💰 UBI Claims: {len(claims)}\n"
            success_message += f"   📋 Events: {len(events)}\n\n"

            success_message += f"🕐 Most Recent Activity:\n"
            success_message += f"   Contract: {latest_activity['contract']}\n"
            success_message += f"   Type: {latest_activity['method']}\n"
            success_message += f"   Amount: {latest_activity['amount']}\n"
            success_message += f"   Block: #{latest_activity['block']}\n"
            success_message += f"   Time: {latest_activity['timestamp']}\n"
            success_message += f"   Tx: {latest_activity['tx_hash'][:16]}...\n"

            if len(all_activities) > 1:
                success_message += f"\n📊 All UBI Activities (last 24 hours):\n"
                for i, activity in enumerate(all_activities[:5], 1):  # Show top 5
                    success_message += f"   {i}. {activity['amount']} ({activity['method']}) - {activity['timestamp']}\n"

                if len(all_activities) > 5:
                    success_message += f"   ... and {len(all_activities) - 5} more activities\n"

            return {
                "status": "success",
                "message": success_message,
                "activities": all_activities,
                "summary": {
                    "total_activities": len(all_activities),
                    "claims": len(claims),
                    "events": len(events),
                    "contracts_involved": 1,  # Only UBI Proxy
                    "latest_activity": latest_activity
                }
            }
        else:
            return {
                "status": "error",
                "message": "You need to claim G$ once every 24 hours to access GoodMarket.\n\nClaim G$ using:\n• MiniPay app (built into Opera Mini)\n• goodwallet.xyz\n• gooddapp.org"
            }

    except Exception as e:
        logger.error(f"Exception in UBI verification: {e}")
        return {"status": "error", "message": f"⚠️ UBI verification failed: {e}"}


def get_gooddollar_balance(wallet_address: str) -> dict:
    try:
        # Initialize Web3 connection
        import requests
        from web3 import Web3

        w3 = Web3(Web3.HTTPProvider(CELO_RPC))

        if not w3.is_connected():
            return {
                "success": False,
                "error": "Failed to connect to Celo network",
                "balance": 0,
                "balance_formatted": "Connection Error"
            }

        # GoodDollar ERC20 ABI for balance checking
        erc20_abi = [
            {
                "constant": True,
                "inputs": [{"name": "_owner", "type": "address"}],
                "name": "balanceOf",
                "outputs": [{"name": "balance", "type": "uint256"}],
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
                "inputs": [],
                "name": "symbol",
                "outputs": [{"name": "", "type": "string"}],
                "type": "function"
            }
        ]

        # Use GoodDollar token contract address
        gooddollar_token = GOODDOLLAR_CONTRACTS["GOODDOLLAR_TOKEN"]

        # Create contract instance
        contract = w3.eth.contract(
            address=Web3.to_checksum_address(gooddollar_token),
            abi=erc20_abi
        )

        # Get balance
        wallet_checksum = Web3.to_checksum_address(wallet_address)
        balance_wei = contract.functions.balanceOf(wallet_checksum).call()

        # Convert from wei to G$ (18 decimals)
        balance_g = balance_wei / (10 ** 18)

        return {
            "success": True,
            "balance": float(balance_g),
            "balance_formatted": f"{balance_g:.6f} G$",
            "wallet": wallet_address,
            "contract": gooddollar_token
        }

    except Exception as e:
        logger.error(f"Balance check error: {e}")
        return {
            "success": False,
            "error": str(e),
            "balance": 0,
            "balance_formatted": "Error loading balance"
        }


if __name__ == "__main__":
    test_wallet = "0xFf00A683f7bD77665754A65F2B82fdEFc4371a50"
    result = has_recent_ubi_claim(test_wallet)
    print(result["message"])

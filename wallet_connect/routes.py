import os
from flask import Blueprint, jsonify, session

wallet_connect_bp = Blueprint("wallet_connect", __name__, url_prefix="/wallet-connect")


@wallet_connect_bp.route("/config", methods=["GET"])
def wallet_connect_config():
    """Expose WalletConnect runtime config to frontend module."""
    project_id = os.getenv("WALLETCONNECT_PROJECT_ID", "")

    return jsonify({
        "success": True,
        "walletconnect": {
            "project_id": project_id,
            "chain_id": 42220,
            "rpc_url": os.getenv("CELO_RPC_URL", "https://forno.celo.org")
        }
    })


@wallet_connect_bp.route("/session", methods=["GET"])
def wallet_connect_session_status():
    """Debug-friendly wallet session status for wallet-connect module."""
    return jsonify({
        "success": True,
        "session": {
            "wallet": session.get("wallet"),
            "verified": bool(session.get("verified")),
            "ubi_verified": bool(session.get("ubi_verified"))
        }
    })

from flask import Flask, request, jsonify, render_template, session, redirect
from blockchain import has_recent_ubi_claim
from analytics_service import analytics
from routes import routes
# Removed: from hour_bonus import (...)
from learn_and_earn import init_learn_and_earn
from web3 import Web3
from datetime import datetime # Import datetime for session timestamp
import os
import logging
import subprocess
import sys
import json

# Removed: Reloadly imports
# from services.reloadly.client import ReloadlyClient
# from services.reloadly.currency import CurrencyConverter
# from services.reloadly.blockchain import ReloadlyBlockchain


from functools import wraps
from time import time
from flask_compress import Compress

# Simple in-memory cache for frequently accessed data
_cache = {}
_cache_timestamps = {}
CACHE_DURATION = 60  # 60 seconds

def cached_response(duration=CACHE_DURATION):
    """Decorator to cache API responses"""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # Create cache key from function name and args
            cache_key = f"{f.__name__}:{str(args)}:{str(kwargs)}"

            # Check if cached and still valid
            if cache_key in _cache:
                if time() - _cache_timestamps.get(cache_key, 0) < duration:
                    return _cache[cache_key]

            # Execute function and cache result
            result = f(*args, **kwargs)
            _cache[cache_key] = result
            _cache_timestamps[cache_key] = time()

            # Limit cache size (keep only 100 most recent)
            if len(_cache) > 100:
                oldest_key = min(_cache_timestamps, key=_cache_timestamps.get)
                del _cache[oldest_key]
                del _cache_timestamps[oldest_key]

            return result
        return decorated_function
    return decorator

# Configure logging - reduced for production performance
logging.basicConfig(level=logging.WARNING)  # Changed from INFO to WARNING
logger = logging.getLogger(__name__)

# Reduce werkzeug logging for health checks
logging.getLogger('werkzeug').setLevel(logging.ERROR)  # Changed from WARNING to ERROR
logging.getLogger('httpx').setLevel(logging.ERROR)  # Reduce httpx logging

app = Flask(__name__, static_folder='static', static_url_path='/static')
app.secret_key = os.environ.get('SECRET_KEY', 'your-secret-key-here')

# Enable gzip compression
compress = Compress()
compress.init_app(app)

# Configure session for better persistence
from datetime import timedelta
app.permanent_session_lifetime = timedelta(hours=24)  # 24 hour session lifetime
app.config['SESSION_COOKIE_SECURE'] = True  # Use HTTPS for cookies
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_DOMAIN'] = None  # Allow cookies on all domains (including custom domains)

# Memory optimization for Reserved VM (1 vCPU / 2 GiB RAM)
app.config['MAX_CONTENT_LENGTH'] = 8 * 1024 * 1024  # 8MB max file upload (reduced)
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 31536000  # Cache static files for 1 year

# Performance optimization for low-resource deployment
app.config['JSON_SORT_KEYS'] = False  # Reduce JSON processing overhead
app.config['JSONIFY_PRETTYPRINT_REGULAR'] = False  # Disable pretty printing for better performance
app.config['TEMPLATES_AUTO_RELOAD'] = False  # Disable template auto-reload in production

# Database connection pooling
app.config['SQLALCHEMY_POOL_SIZE'] = 5
app.config['SQLALCHEMY_POOL_TIMEOUT'] = 10
app.config['SQLALCHEMY_POOL_RECYCLE'] = 3600
app.config['SQLALCHEMY_MAX_OVERFLOW'] = 2

# Removed: Initialize Reloadly clients and services
# reloadly_client = None
# currency_converter = None
# reloadly_blockchain = None

# Removed: initialize_reloadly function
# def initialize_reloadly():
#     global reloadly_client, currency_converter, reloadly_blockchain
#     try:
#         # Load environment variables
#         reloadly_client_id = os.getenv("RELOADLY_CLIENT_ID")
#         reloadly_client_secret = os.getenv("RELOADLY_CLIENT_SECRET")
#         gooddollar_contract_address = os.getenv("GOODDOLLAR_CONTRACT_ADDRESS")
#         celo_rpc_url = os.getenv("CELO_RPC_URL", 'https://forno.celo.org')
#         chain_id = int(os.getenv("CHAIN_ID", 44787)) # Default to Alfajores if not set
#         merchant_address = os.getenv("MERCHANT_ADDRESS")
#         refund_key = os.getenv("REFUND_KEY")
#         gd_usd_price = float(os.getenv("GD_USD_PRICE", 0.002)) # Default to $0.002 per G$
#         forex_rates_path = os.getenv("DEFAULT_FX_JSON_PATH", "data/forex_rates.json")
#
#         # Initialize Reloadly Client for production (will work even without credentials using fallback data)
#         reloadly_client = ReloadlyClient(reloadly_client_id, reloadly_client_secret, environment="production")
#
#         if reloadly_client.is_initialized:
#             logger.info("✅ Reloadly API client initialized with credentials.")
#         else:
#             logger.warning("⚠️ Reloadly API client initialized with fallback data (no credentials).")
#
#         # Initialize Currency Converter
#         try:
#             currency_converter = CurrencyConverter()
#             logger.info("✅ Currency converter initialized.")
#         except Exception as cc_error:
#             logger.warning(f"⚠️ Currency converter failed to initialize: {cc_error}")
#             currency_converter = None
#
#         # Initialize Reloadly Blockchain service (optional)
#         try:
#             if all([merchant_address, refund_key, gooddollar_contract_address, celo_rpc_url]):
#                 reloadly_blockchain = ReloadlyBlockchain()
#                 logger.info("✅ Reloadly Blockchain service initialized.")
#             else:
#                 logger.warning("⚠️ Reloadly Blockchain service not initialized (missing config)")
#                 reloadly_blockchain = None
#         except Exception as rb_error:
#             logger.warning(f"⚠️ Reloadly Blockchain service failed to initialize: {rb_error}")
#             reloadly_blockchain = None
#
#         return True
#
#     except Exception as e:
#         logger.error(f"❌ Error initializing Reloadly services: {e}")
#         return False



# Blockchain configuration for wallet balance checking
CELO_RPC_URL = os.getenv('CELO_RPC_URL', 'https://forno.celo.org')  # Default to Celo's public RPC
# Use the main G$ token contract for balance checking
GOODDOLLAR_CONTRACT_ADDRESS = os.getenv('GOODDOLLAR_CONTRACT', '0x62B8B11039FcfE5aB0C56E502b1C372A3d2a9c7A')

# Global blockchain variables
w3 = None
gooddollar_contract = None

# Initialize blockchain connection
def initialize_blockchain():
    """Initialize blockchain connection for wallet balance checking"""
    global w3, gooddollar_contract
    try:
        from web3 import Web3

        # Initialize Web3 connection
        w3 = Web3(Web3.HTTPProvider(CELO_RPC_URL))

        if not w3.is_connected():
            logger.error("❌ Failed to connect to Celo network")
            return False

        logger.info("✅ Connected to Celo network")

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
            },
            {
                "constant": True,
                "inputs": [],
                "name": "name",
                "outputs": [{"name": "", "type": "string"}],
                "type": "function"
            }
        ]

        # Create GoodDollar contract instance
        gooddollar_contract = w3.eth.contract(
            address=Web3.to_checksum_address(GOODDOLLAR_CONTRACT_ADDRESS),
            abi=erc20_abi
        )

        logger.info(f"✅ GoodDollar contract loaded: {GOODDOLLAR_CONTRACT_ADDRESS}")
        return True

    except Exception as e:
        logger.error(f"❌ Blockchain initialization error: {e}")
        return False

# Initialize smart contract system
def initialize_smart_contract():
    """Initialize smart contract system"""
    try:
        # Contract system temporarily disabled - using direct blockchain integration
        logger.info("⚠️ Smart contract system disabled - using direct blockchain integration")
        return True

    except Exception as e:
        logger.error(f"❌ Smart contract initialization error: {e}")
        return False

# Initialize the blockchain connection when the app starts
if not initialize_blockchain():
    logger.warning("Blockchain initialization failed. Wallet balance features might not work.")

# Initialize smart contract system
if not initialize_smart_contract():
    logger.warning("Smart contract system initialization failed. Contract features might not work.")

# Removed: Initialize Reloadly services
# if not initialize_reloadly():
#     logger.warning("Reloadly services initialization failed. Top-up features might not work.")

# Blockchain service removed - will be replaced with new smart contract integration

# Register the routes blueprint FIRST (contains all API routes including /api/recent-daily-tasks)
# This must be before any catch-all routes
app.register_blueprint(routes)
logger.info("✅ Routes blueprint registered with API endpoints")

# Register GoodMarket blueprint
# Removed: from goodmarket.routes import goodmarket_bp
# Removed: app.register_blueprint(goodmarket_bp, url_prefix='/goodmarket')

# Initialize Telegram Task
from telegram_task import init_telegram_task
if not init_telegram_task(app):
    logger.warning("⚠️ Telegram Task initialization failed")
else:
    logger.info("✅ Telegram Task initialized successfully")

# Initialize Twitter Task
from twitter_task import init_twitter_task
if not init_twitter_task(app):
    logger.warning("⚠️ Twitter Task initialization failed")
else:
    logger.info("✅ Twitter Task initialized successfully")

# Initialize Facebook Task
from facebook_task import init_facebook_task
if not init_facebook_task(app):
    logger.warning("⚠️ Facebook Task initialization failed")
else:
    logger.info("✅ Facebook Task initialized successfully")

# Initialize News Feed first
from news_feed import init_news_feed, news_feed_service
init_news_feed(app)

# Initialize Minigames System
logger.info("🎮 Initializing Minigames system...")
from minigames import init_minigames
if init_minigames(app):
    logger.info("✅ Minigames system initialized")
else:
    logger.error("❌ Minigames initialization failed")

# Initialize Community Stories System
logger.info("🌟 Initializing Community Stories system...")
from community_stories import init_community_stories
if init_community_stories(app):
    logger.info("✅ Community Stories system initialized")
else:
    logger.error("❌ Community Stories initialization failed")

# Initialize Reward Configuration Service
logger.info("💰 Initializing Reward Configuration Service...")
try:
    from reward_config_service import reward_config_service
    logger.info("✅ Reward Configuration Service initialized")
except Exception as e:
    logger.error(f"❌ Reward Configuration Service initialization failed: {e}")

# Initialize Learn & Earn System at module level (required for gunicorn)
logger.info("🎓 Initializing Learn & Earn system...")
if init_learn_and_earn(app):
    logger.info("✅ Learn & Earn system initialized")
else:
    logger.error("❌ Learn & Earn initialization failed")

# Notification service removed - all references cleaned up




@app.route("/")
def health_check():
    """Health check endpoint for deployment"""
    return jsonify({
        "status": "healthy",
        "service": "GoodDollar Analytics Platform",
        "version": "1.0.0"
    }), 200

@app.route("/login")
def home():
    return render_template("login.html")

@app.route("/api")
def api_status():
    return jsonify({
        "status": "online",
        "message": "GoodDollar Analytics Platform API",
        "version": "1.0.0",
        "endpoints": [
            "/api/analytics",
            # Removed: "/api/hour-bonus/status",
            "/api/gooddollar-balance",
            "/api/forum/posts",
            "/api/p2p/history",
            "/api/learn-earn/history"
        ]
    })



@app.route("/verify-ubi", methods=["POST"])
def verify_ubi():
    data = request.get_json()
    wallet = data.get("wallet")
    if not wallet:
        return jsonify({"status": "error", "message": "⚠️ Wallet address required"}), 400

    # Validate wallet format first
    if not (len(wallet) == 42 and wallet.startswith("0x")):
        result = {"status": "error", "message": "❌ Invalid wallet address format"}
        analytics.track_verification_attempt(wallet, False)
        return jsonify(result)

    # Use actual blockchain verification
    result = has_recent_ubi_claim(wallet)

    if result["status"] == "success":
        # Store wallet in session if verified
        session["wallet_address"] = wallet
        session["wallet"] = wallet # Keep this for backward compatibility if needed
        session["verified"] = True
        session["ubi_verified"] = True # Add this for clarity
        session.permanent = True
        analytics.track_verification_attempt(wallet, True)
        analytics.track_user_session(wallet)

        return jsonify({
            "status": "success",
            "message": result["message"],
            "wallet": wallet,
            "block_number": result.get("summary", {}).get("latest_activity", {}).get("block"),
            "claim_amount": result.get("summary", {}).get("latest_activity", {}).get("amount", "N/A"),
            "redirect_to": "/overview"  # Skip terms page, go directly to overview
        })
    else:
        analytics.track_verification_attempt(wallet, False)
        return jsonify({
            "status": "error",
            "message": result["message"],
            "reason": "no_recent_claim"
        }), 400

@app.route("/dashboard")
def dashboard():
    wallet = session.get("wallet")
    if not wallet or not session.get("verified"):
        return render_template("login.html")

    # Track page view and get dashboard data
    analytics.track_page_view(wallet, "dashboard")
    dashboard_data = analytics.get_dashboard_stats(wallet)

    return render_template("dashboard.html", wallet=wallet, data=dashboard_data)

@app.route("/overview")
def overview():
    wallet = session.get("wallet")
    if not wallet or not session.get("verified"):
        return render_template("login.html")

    # Track page view and get analytics data
    analytics.track_page_view(wallet, "overview")
    overview_data = analytics.get_dashboard_stats(wallet)

    return render_template("overview.html", wallet=wallet, data=overview_data)

@app.route("/api/analytics")
@cached_response(duration=30)  # Cache for 30 seconds
def api_analytics():
    wallet = session.get("wallet")
    if not wallet or not session.get("verified"):
        return jsonify({"error": "Unauthorized"}), 401

    return jsonify(analytics.get_user_analytics(wallet))

# Removed: /api/hour-bonus/status route
# Removed: /api/hour-bonus/claim route
# Removed: /api/hour-bonus/history route
# Removed: /api/hour-bonus/system-status route

@app.route("/api/gooddollar-balance", methods=["GET"])
def get_gooddollar_balance_api():
    """Get GoodDollar balance for current user"""
    wallet = session.get("wallet")
    if not wallet or not session.get("verified"):
        return jsonify({"success": False, "error": "Unauthorized"}), 401

    try:
        # Use blockchain.py get_gooddollar_balance function directly
        from blockchain import get_gooddollar_balance as get_balance
        result = get_balance(wallet)

        if not result:
            return jsonify({
                "success": False,
                "error": "Failed to fetch balance",
                "balance_formatted": "Error loading"
            }), 500

        return jsonify(result)
    except Exception as e:
        logger.error(f"❌ Balance API error: {e}")
        return jsonify({
            "success": False,
            "error": str(e),
            "balance_formatted": "Error loading"
        }), 500

@app.route("/api/balance/<wallet_address>", methods=["GET"])
def get_balance_by_wallet(wallet_address):
    """Get GoodDollar balance for specific wallet (used by overview page)"""
    session_wallet = session.get("wallet")
    if not session_wallet or not session.get("verified"):
        return jsonify({"success": False, "error": "Unauthorized"}), 401

    # Only allow getting balance for the authenticated user's wallet
    if wallet_address != session_wallet:
        return jsonify({"success": False, "error": "Unauthorized"}), 401

    try:
        # Use blockchain.py get_gooddollar_balance function directly
        from blockchain import get_gooddollar_balance as get_balance
        result = get_balance(wallet_address)

        if not result:
            return jsonify({
                'success': False,
                'error': 'Failed to fetch balance',
                'balance_formatted': 'Error loading'
            }), 500

        return jsonify(result)
    except Exception as e:
        logger.error(f"Balance API error: {e}")
        return jsonify({
            'success': False,
            'error': str(e),
            'balance_formatted': 'Error loading'
        }), 500

# Contract info route removed - will be replaced with new smart contract integration

# Terms & Service route removed - no longer needed

# Accept terms route removed - no longer needed

# Decline terms route removed - no longer needed

@app.route("/logout")
def logout():
    session.clear()
    return render_template("login.html")

# API endpoints for dashboard functionality
@app.route('/api/gooddollar-balance')
def get_gooddollar_balance():
    """Get GoodDollar balance for authenticated user"""
    try:
        wallet_address = session.get('wallet') or session.get('wallet_address')
        if not wallet_address or not session.get('verified'):
            return jsonify({'success': False, 'error': 'Not authenticated'}), 401

        # Use blockchain.py get_gooddollar_balance function directly
        from blockchain import get_gooddollar_balance as get_balance
        balance_result = get_balance(wallet_address)

        return jsonify(balance_result)
    except Exception as e:
        logger.error(f"Balance API error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

# Note: /api/news-feed routes are handled by news_feed.py via init_news_feed(app)

# Community Forum module removed




@app.route('/api/twitter-task/transaction-history')
def get_twitter_task_transaction_history():
    """Get user's Twitter task transaction history for dashboard integration"""
    try:
        wallet = session.get('wallet') or session.get('wallet_address')
        verified = session.get('verified') or session.get('ubi_verified')

        if not wallet or not verified:
            return jsonify({
                "success": True,
                "transactions": [],
                "total": 0
            }), 200

        limit = int(request.args.get('limit', 50))

        logger.info(f"📋 Getting Twitter task history for {wallet[:8]}... (limit: {limit})")

        from twitter_task.twitter_task import twitter_task_service

        # Get transaction history
        history = twitter_task_service.get_transaction_history(wallet, limit)

        return jsonify(history)

    except Exception as e:
        logger.error(f"❌ Error getting Twitter task history: {e}")
        return jsonify({
            "success": False,
            "error": str(e),
            "transactions": [],
            "total": 0
        }), 500

@app.route('/learn-earn/quiz-history')
def get_learn_earn_quiz_history():
    """Get user's Learn & Earn quiz history for dashboard integration - ALL HISTORICAL DATA"""
    try:
        wallet = session.get('wallet') or session.get('wallet_address')
        verified = session.get('verified') or session.get('ubi_verified')

        if not wallet or not verified:
            logger.warning(f"⚠️ Unauthorized Learn & Earn history request - no wallet/verification")
            return jsonify({
                "success": True,
                "quiz_history": [],
                "total": 0,
                "message": "Not authenticated"
            }), 200

        limit = int(request.args.get('limit', 500))  # Default 500 records for comprehensive history

        logger.info(f"📋 Getting ALL Learn & Earn history for {wallet[:8]}... (limit: {limit})")

        from learn_and_earn.learn_and_earn import quiz_manager

        # Get quiz history - NO DATE FILTERING, ALL HISTORICAL LOGS
        history = quiz_manager.get_quiz_history(wallet, limit)

        # Ensure history is a list
        if not isinstance(history, list):
            logger.error(f"❌ Quiz history is not a list: {type(history)}")
            history = []

        # Format history for dashboard display
        formatted_history = []
        for record in history:
            try:
                formatted_record = {
                    'quiz_id': record.get('quiz_id'),
                    'score': record.get('score'),
                    'total_questions': record.get('total_questions'),
                    'amount_g$': record.get('amount_g$'),
                    'timestamp': record.get('timestamp'),
                    'transaction_hash': record.get('transaction_hash'),
                    'status': 'completed' if record.get('status') else 'failed',
                    'reward_status': record.get('reward_status', 'completed'),
                    'username': record.get('username', 'User')
                }
                formatted_history.append(formatted_record)
            except Exception as format_error:
                logger.error(f"❌ Error formatting quiz record: {format_error}")
                continue

        logger.info(f"✅ Found {len(formatted_history)} Learn & Earn records for {wallet[:8]}... (ALL TIME)")

        # Log date range if there are records
        if formatted_history:
            dates = [r['timestamp'] for r in formatted_history if r.get('timestamp')]
            if dates:
                oldest_date = min(dates)
                newest_date = max(dates)
                logger.info(f"📅 Complete history range: {oldest_date} (oldest) to {newest_date} (newest)")

        response_data = {
            "success": True,
            "quiz_history": formatted_history,
            "total": len(formatted_history)
        }

        if formatted_history:
            response_data["oldest_record"] = formatted_history[-1]['timestamp']
            response_data["newest_record"] = formatted_history[0]['timestamp']

        logger.info(f"✅ Returning Learn & Earn history response with {len(formatted_history)} records")
        return jsonify(response_data), 200

    except Exception as e:
        logger.error(f"❌ Error getting Learn & Earn history: {e}")
        import traceback
        logger.error(f"🔍 Traceback: {traceback.format_exc()}")
        return jsonify({
            "success": True,
            "quiz_history": [],
            "total": 0,
            "error": str(e)
        }), 200

@app.route('/api/debug/session', methods=['GET'])
def debug_session():
    """Debug endpoint to check session status"""
    try:
        return jsonify({
            'success': True,
            'session_data': {
                'wallet': session.get('wallet'),
                'wallet_address': session.get('wallet_address'),
                'verified': session.get('verified'),
                'ubi_verified': session.get('ubi_verified'),
                'username': session.get('username'),
                'terms_accepted': session.get('terms_accepted'),
                'permanent': session.permanent
            }
        })
    except Exception as e:
        logger.error(f"❌ Session debug error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

# Forum like route is handled by community forum module

# Community Forum endpoints removed


@app.route('/verify-identity', methods=['POST'])
def verify_identity():
    """Handle identity verification with UBI validation"""
    try:
        data = request.get_json()
        wallet_address = data.get('wallet_address', '').strip()
        referral_code = data.get('referral_code', '').strip()

        if not wallet_address:
            return jsonify({'error': 'Wallet address is required'}), 400

        # Validate wallet address format
        if not Web3.is_address(wallet_address):
            return jsonify({'error': 'Invalid wallet address format'}), 400

        logger.info(f"🔐 Identity verification attempt for {wallet_address}")

        # Check if user is already verified in the session
        if session.get('verified') and session.get('wallet') == wallet_address:
            logger.info(f"✅ User {wallet_address} already verified in session")
            return jsonify({
                'success': True,
                'message': 'Already verified!',
                'wallet': wallet_address,
                'already_verified': True
            })

        # 🔥 IMPORTANT: Verify UBI claim first before processing referral
        logger.info(f"🔍 Checking UBI verification for {wallet_address}")
        ubi_result = has_recent_ubi_claim(wallet_address)

        if ubi_result["status"] != "success":
            logger.warning(f"❌ UBI verification failed for {wallet_address}: {ubi_result['message']}")
            # ALWAYS use the custom message from blockchain.py response
            custom_message = ubi_result.get("message", "You need to claim G$ once every 24 hours to access GoodMarket.\n\nClaim G$ using:\n• MiniPay app (built into Opera Mini)\n• goodwallet.xyz\n• gooddapp.org")

            # Return the EXACT same format as routes.py to ensure consistency
            return jsonify({
                'success': False,
                'error': custom_message,
                'message': custom_message,
                'status': 'error',
                'reason': 'no_recent_claim'
            }), 400

        logger.info(f"✅ UBI verification successful for {wallet_address}")

        # Referral processing removed
        referral_recorded = False

        # Track verification attempt
        analytics.track_verification_attempt(wallet_address, True)

        # Store in session with permanent flag
        session.permanent = True  # Make session persistent across browser restarts
        session['wallet'] = wallet_address
        session['wallet_address'] = wallet_address
        session['verified'] = True
        session['ubi_verified'] = True # Add this for clarity
        session['verification_time'] = datetime.now().isoformat()

        # Referral system removed

        logger.info(f"✅ Identity verification successful for {wallet_address}")

        return jsonify({
                'success': True,
                'message': 'Identity verification successful!',
                'wallet': wallet_address,
                'ubi_verified': True,
                'redirect_to': '/overview'
            })

    except Exception as e:
        logger.error(f"❌ Identity verification error: {e}")
        return jsonify({'error': 'Verification failed'}), 500


# Notification endpoints removed - notification service is disabled

# Community Forum post creation removed

# Routes for username editing are in routes.py blueprint

@app.route('/api/debug/database-status')
def debug_database_status():
    """Debug endpoint to check database connection and data fetching"""
    try:
        from supabase_client import get_supabase_client, supabase_enabled

        status = {
            "supabase_enabled": supabase_enabled,
            "environment_vars": {
                "SUPABASE_URL_exists": bool(os.getenv("SUPABASE_URL")),
                "SUPABASE_ANON_KEY_exists": bool(os.getenv("SUPABASE_ANON_KEY"))
            },
            "connection_test": None,
            "analytics_test": None
        }

        # Test connection
        supabase = get_supabase_client()
        if supabase:
            try:
                # Try a simple query
                test_query = supabase.table("user_data").select("id").limit(1).execute()
                status["connection_test"] = {
                    "success": True,
                    "message": "Database connection successful"
                }
            except Exception as conn_error:
                status["connection_test"] = {
                    "success": False,
                    "error": str(conn_error)
                }
        else:
            status["connection_test"] = {
                "success": False,
                "error": "Supabase client not initialized"
            }

        # Test analytics data fetch
        try:
            disbursement_stats = analytics._get_total_disbursements_stats()
            status["analytics_test"] = {
                "success": True,
                "has_breakdown_formatted": "breakdown_formatted" in disbursement_stats,
                "breakdown_categories": len(disbursement_stats.get("breakdown_formatted", {})),
                "total_disbursed": disbursement_stats.get("total_g_disbursed", 0)
            }
        except Exception as analytics_error:
            status["analytics_test"] = {
                "success": False,
                "error": str(analytics_error)
            }

        return jsonify(status)

    except Exception as e:
        logger.error(f"❌ Database status check error: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/debug/task-data/<wallet_address>')
def debug_task_data(wallet_address):
    """Debug endpoint to check task completion data for specific user"""
    try:
        # Security check - only allow current session user or admins
        session_wallet = session.get('wallet')
        if not session_wallet or not session.get('verified'):
            return jsonify({'error': 'Not authenticated'}), 401

        if wallet_address != session_wallet:
            return jsonify({'error': 'Unauthorized'}), 401

        from supabase_client import get_supabase_client
        supabase = get_supabase_client()

        if not supabase:
            return jsonify({'error': 'Database not available'})

        # Get task completion logs
        from task_completion.task_manager import task_manager
        masked_wallet = task_manager._mask_wallet(wallet_address)

        logger.info(f"🔍 Debug: Checking task data for {wallet_address}")
        logger.info(f"🔍 Debug: Masked wallet: {masked_wallet}")

        # Get task completions
        completions = supabase.table('task_completion_log')\
            .select('*')\
            .eq('wallet_address', masked_wallet)\
            .order('timestamp', desc=True)\
            .execute()

        # Get pending rewards
        pending = supabase.table('task_pending_rewards')\
            .select('*')\
            .eq('wallet_address', wallet_address)\
            .execute()

        # Calculate total from completions
        total_from_completions = 0
        if completions.data:
            total_from_completions = sum(float(c.get('reward_amount', 0)) for c in completions.data)

        debug_data = {
            'wallet_address': wallet_address,
            'masked_wallet': masked_wallet,
            'task_completions': {
                'count': len(completions.data) if completions.data else 0,
                'total_amount': total_from_completions,
                'completions': completions.data[:10] if completions.data else []  # First 10
            },
            'pending_rewards': {
                'count': len(pending.data) if pending.data else 0,
                'data': pending.data
            },
            'sync_needed': total_from_completions > 0
        }

        logger.info(f"🔍 Debug results for {wallet_address[:8]}...")
        logger.info(f"   Task completions: {debug_data['task_completions']['count']}")
        logger.info(f"   Total from completions: {debug_data['task_completions']['total_amount']} G$")
        logger.info(f"   Pending records: {debug_data['pending_rewards']['count']}")

        return jsonify(debug_data)

    except Exception as e:
        logger.error(f"❌ Debug task data error: {e}")
        return jsonify({'error': str(e)}), 500


# Removed: All Reloadly Top-up Routes
# Removed: @app.route("/topup")
# Removed: def topup_page(): ...
# Removed: @app.route("/treasury-deposit")
# Removed: def treasury_deposit_page(): ...
# Removed: @app.route("/api/operators/<country_code>")
# Removed: def get_operators(country_code): ...
# Removed: @app.route("/api/products/<int:operator_id>")
# Removed: def get_products(operator_id): ...
# Removed: @app.route("/api/merchant")
# Removed: def get_merchant(): ...
# Removed: @app.route("/api/quote", methods=["POST"])
# Removed: def create_quote(): ...
# Removed: @app.route("/purchase_topup", methods=["POST"])
# Removed: def purchase_topup(): ...
# Removed: @app.route("/api/payment-status/<order_id>")
# Removed: def check_payment_status(order_id): ...
# Removed: @app.route("/api/countries")
# Removed: def get_countries(): ...
# Removed: @app.route("/api/operators")
# Removed: def get_all_operators(): ...
# Removed: @app.route("/api/products")
# Removed: def get_all_products(): ...
# Removed: @app.route("/api/reloadly/test")
# Removed: def test_reloadly_apis(): ...


# Username functionality removed


if __name__ == "__main__":
    logger.info("🚀 Starting GoodDollar Analytics Platform...")

    # Initialize Supabase logger first
    # analytics.supabase_logger = supabase_logger # This line might be an issue if supabase_logger is not defined

    # Initialize modules with feature toggles
    ENABLE_HEAVY_FEATURES = True  # Force enable for P2P Trading

    # Removed: Hourly Bonus system initialization
    # if ENABLE_HEAVY_FEATURES:
    #     from hour_bonus import init_hour_bonus
    #     if init_hour_bonus(app):
    #         logger.info("✅ Hourly Bonus system ready")
    #     else:
    #         logger.error("❌ Hourly Bonus system failed to initialize")
    # else:
    #     logger.info("⚠️ Heavy features disabled for performance")

    # Initialize Referral Program system
    logger.info("🎁 Initializing Referral Program system...")
    try:
        from referral_program import referral_bp
        app.register_blueprint(referral_bp)
        logger.info("✅ Referral Program system ready")
        logger.info("🔗 Available endpoints:")
        logger.info("   POST /api/referral/generate-code - Generate referral code")
        logger.info("   POST /api/referral/validate-code - Validate referral code")
        logger.info("   GET  /api/referral/stats - Get referral statistics")
    except Exception as e:
        logger.error(f"❌ Referral Program initialization failed: {e}")

    # Learn & Earn is now initialized at module level (above) for gunicorn compatibility

    port = int(os.environ.get("PORT", 5000))
    logger.info(f"🌐 Starting Flask server on http://0.0.0.0:{port}")
    logger.info(f"✅ Server is ready to accept connections")
    logger.info(f"📡 Webview URL: https://{os.environ.get('REPL_SLUG', 'app')}.{os.environ.get('REPL_OWNER', 'replit')}.repl.co")

    # Start Flask with threaded mode for better concurrent request handling
    app.run(host="0.0.0.0", port=port, debug=False, threaded=True, use_reloader=False)

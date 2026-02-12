from flask import Blueprint, render_template, request, jsonify, session, redirect, url_for
from blockchain import has_recent_ubi_claim, GOODDOLLAR_CONTRACTS
from analytics_service import analytics
from supabase_client import get_supabase_client, safe_supabase_operation, supabase_logger, log_admin_action
import json
import logging
import os

# Logger for this module
logger = logging.getLogger(__name__)

# Create Blueprint FIRST - BEFORE any route decorators
routes = Blueprint("routes", __name__)

def auth_required(f):
    """Decorator for endpoints requiring authentication with auto-logout on expiry"""
    def wrapper(*args, **kwargs):
        wallet = session.get("wallet")
        verified = session.get("verified")

        if not verified or not wallet:
            return jsonify({"success": False, "error": "Authentication required"}), 401

        # Check if UBI claim is still valid (recent within 24 hours)
        from blockchain import has_recent_ubi_claim
        ubi_check = has_recent_ubi_claim(wallet)

        if ubi_check["status"] != "success":
            # UBI claim expired - auto logout
            logger.warning(f"⚠️ Auto-logout: UBI verification expired for {wallet[:8]}...")
            session.clear()
            return jsonify({
                "success": False,
                "error": "Session expired. Please log in again.",
                "auto_logout": True,
                "redirect": "/"
            }), 401

        return f(*args, **kwargs)
    wrapper.__name__ = f.__name__
    return wrapper

def admin_required(f):
    """Decorator for endpoints requiring admin authentication"""
    def wrapper(*args, **kwargs):
        wallet = session.get("wallet")
        if not session.get("verified") or not wallet:
            return jsonify({"success": False, "error": "Authentication required"}), 401

        from supabase_client import is_admin
        if not is_admin(wallet):
            return jsonify({"success": False, "error": "Admin access required"}), 403

        return f(*args, **kwargs)
    wrapper.__name__ = f.__name__
    return wrapper

@routes.route('/api/daily-task/claim', methods=['POST'])
@auth_required
def claim_daily_task():
    """Claim unified daily task (Twitter or Telegram)"""
    try:
        wallet = session.get('wallet')
        data = request.get_json()

        platform = data.get('platform')  # 'twitter' or 'telegram' or 'facebook'
        post_url = data.get('post_url')

        if platform not in ['twitter', 'telegram', 'facebook']:
            return jsonify({
                'success': False,
                'error': 'Invalid platform. Choose twitter, telegram, or facebook.'
            }), 400

        if not post_url:
            return jsonify({
                'success': False,
                'error': f'{platform.capitalize()} post URL is required'
            }), 400

        # Import appropriate service
        if platform == 'twitter':
            from twitter_task.twitter_task import twitter_task_service
            service = twitter_task_service
        elif platform == 'telegram':
            from telegram_task.telegram_task import telegram_task_service
            service = telegram_task_service
        else:  # facebook
            from facebook_task.facebook_task import facebook_task_service
            service = facebook_task_service

        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        try:
            result = loop.run_until_complete(
                service.claim_task_reward(wallet, post_url)
            )

            if result.get('success'):
                return jsonify(result), 200
            else:
                return jsonify(result), 400

        finally:
            loop.close()

    except Exception as e:
        logger.error(f"❌ Daily task claim error: {e}")
        import traceback
        logger.error(f"🔍 Traceback: {traceback.format_exc()}")
        return jsonify({'success': False, 'error': 'Failed to claim reward'}), 500

@routes.route('/api/daily-task/status', methods=['GET'])
@auth_required
def get_daily_task_status():
    """Get unified daily task status (checks both Twitter and Telegram)"""
    try:
        wallet = session.get('wallet')

        # Import both services
        from twitter_task.twitter_task import twitter_task_service
        from telegram_task.telegram_task import telegram_task_service
        from datetime import datetime, timezone

        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        try:
            # Check all three tasks
            twitter_status = loop.run_until_complete(twitter_task_service.check_eligibility(wallet))
            telegram_status = loop.run_until_complete(telegram_task_service.check_eligibility(wallet))

            from facebook_task.facebook_task import facebook_task_service
            facebook_status = loop.run_until_complete(facebook_task_service.check_eligibility(wallet))

            # CRITICAL FIX: Check ALL platforms for pending AND check database for actual pending submissions
            # This ensures real-time accuracy even with caching issues

            # First, check direct database for ANY pending submissions
            supabase = get_supabase_client()
            actual_pending = False
            actual_pending_platform = None

            if supabase:
                # Check Twitter pending
                twitter_pending_check = safe_supabase_operation(
                    lambda: supabase.table('twitter_task_log')\
                        .select('id')\
                        .eq('wallet_address', wallet)\
                        .eq('status', 'pending')\
                        .limit(1)\
                        .execute(),
                    fallback_result=type('obj', (object,), {'data': []})(),
                    operation_name="check twitter pending"
                )

                if twitter_pending_check.data and len(twitter_pending_check.data) > 0:
                    actual_pending = True
                    actual_pending_platform = 'Twitter'

                # Check Telegram pending only if Twitter not pending
                if not actual_pending:
                    telegram_pending_check = safe_supabase_operation(
                        lambda: supabase.table('telegram_task_log')\
                            .select('id')\
                            .eq('wallet_address', wallet)\
                            .eq('status', 'pending')\
                            .limit(1)\
                            .execute(),
                        fallback_result=type('obj', (object,), {'data': []})(),
                        operation_name="check telegram pending"
                    )

                    if telegram_pending_check.data and len(telegram_pending_check.data) > 0:
                        actual_pending = True
                        actual_pending_platform = 'Telegram'

                # Check Facebook pending only if Twitter and Telegram not pending
                if not actual_pending:
                    facebook_pending_check = safe_supabase_operation(
                        lambda: supabase.table('facebook_task_log')\
                            .select('id')\
                            .eq('wallet_address', wallet)\
                            .eq('status', 'pending')\
                            .limit(1)\
                            .execute(),
                        fallback_result=type('obj', (object,), {'data': []})(),
                        operation_name="check facebook pending"
                    )

                    if facebook_pending_check.data and len(facebook_pending_check.data) > 0:
                        actual_pending = True
                        actual_pending_platform = 'Facebook'


            # Determine pending platform based on actual database check
            if actual_pending:
                pending_platform = actual_pending_platform
            else:
                pending_platform = None

            # Determine next claim time based on eligible platform cooldowns
            next_claim_time = None
            if actual_pending:
                # If there's a pending submission, next_claim_time is not relevant for claiming
                pass
            else:
                # Check for cooldown (completed claims) - if ANY platform has cooldown, ALL are blocked
                if not twitter_status.get('can_claim') or not telegram_status.get('can_claim') or not facebook_status.get('can_claim'):
                    # If any platform has cooldown active (from completed claims), all are blocked
                    twitter_next = twitter_status.get('next_claim_time')
                    facebook_next = facebook_status.get('next_claim_time')
                    telegram_next = telegram_status.get('next_claim_time')

                    # Find the earliest next claim time among all platforms
                    possible_next_claims = [t for t in [twitter_next, telegram_next, facebook_next] if t]
                    if possible_next_claims:
                        next_claim_time = min(possible_next_claims)

            # Calculate time remaining if next_claim_time exists
            time_remaining_seconds = 0
            if next_claim_time:
                next_claim_dt = datetime.fromisoformat(next_claim_time.replace('Z', '+00:00'))
                now = datetime.now(timezone.utc)
                time_remaining_seconds = max(0, int((next_claim_dt - now).total_seconds()))

            # User can claim if ALL platforms are available (shared cooldown) and no pending submissions
            can_claim = twitter_status.get('can_claim', False) and \
                        telegram_status.get('can_claim', False) and \
                        facebook_status.get('can_claim', False) and \
                        not actual_pending

            return jsonify({
                'can_claim': can_claim,
                'has_pending_submission': actual_pending,
                'pending_platform': pending_platform,
                'next_claim_time': next_claim_time,
                'time_remaining_seconds': time_remaining_seconds
            }), 200
        finally:
            loop.close()

    except Exception as e:
        logger.error(f"❌ Daily task status error: {e}")
        import traceback
        logger.error(f"🔍 Traceback: {traceback.format_exc()}")
        return jsonify({'error': 'Failed to get task status'}), 500


@routes.route('/api/daily-task/history', methods=['GET'])
@auth_required
def get_daily_task_history():
    """Get combined Twitter and Telegram task history"""
    try:
        wallet = session.get('wallet')
        limit = int(request.args.get('limit', 50))

        from twitter_task.twitter_task import twitter_task_service
        from telegram_task.telegram_task import telegram_task_service
        from facebook_task.facebook_task import facebook_task_service

        # Get all histories
        twitter_history = twitter_task_service.get_transaction_history(wallet, limit)
        telegram_history = telegram_task_service.get_transaction_history(wallet, limit)
        facebook_history = facebook_task_service.get_transaction_history(wallet, limit)

        # Combine transactions
        all_transactions = []

        if twitter_history.get('success') and twitter_history.get('transactions'):
            for tx in twitter_history['transactions']:
                tx['platform'] = 'twitter'
                # Ensure rejection_reason is included
                if 'rejection_reason' not in tx:
                    tx['rejection_reason'] = None
                all_transactions.append(tx)

        if telegram_history.get('success') and telegram_history.get('transactions'):
            for tx in telegram_history['transactions']:
                tx['platform'] = 'telegram'
                # Ensure rejection_reason is included
                if 'rejection_reason' not in tx:
                    tx['rejection_reason'] = None
                all_transactions.append(tx)

        if facebook_history.get('success') and facebook_history.get('transactions'):
            for tx in facebook_history['transactions']:
                tx['platform'] = 'facebook'
                # Ensure rejection_reason is included
                if 'rejection_reason' not in tx:
                    tx['rejection_reason'] = None
                all_transactions.append(tx)

        # Sort by date (newest first)
        all_transactions.sort(key=lambda x: x.get('created_at', ''), reverse=True)

        # Limit results
        all_transactions = all_transactions[:limit]

        # Calculate totals
        total_earned = sum(float(tx.get('reward_amount', 0)) for tx in all_transactions)

        return jsonify({
            'success': True,
            'transactions': all_transactions,
            'total_count': len(all_transactions),
            'total_earned': total_earned
        })

    except Exception as e:
        logger.error(f"❌ Daily task history error: {e}")
        import traceback
        logger.error(f"🔍 Traceback: {traceback.format_exc()}")
        return jsonify({
            'success': False,
            'error': 'Failed to get history',
            'transactions': [],
            'total_count': 0,
            'total_earned': 0
        }), 500


@routes.route("/api/recent-daily-tasks", methods=["GET"])
def get_recent_daily_tasks():
    """Get recent daily task submissions from last 24 hours"""
    try:
        from datetime import datetime, timedelta
        from supabase_client import get_supabase_client
        from flask import Response
        from cache_utils import api_cache, cached

        # Check cache first (2 minute TTL)
        cache_key = "recent_daily_tasks"
        cached_result = api_cache.get(cache_key)
        if cached_result:
            response = jsonify(cached_result)
            response.headers['Content-Type'] = 'application/json'
            response.headers['Cache-Control'] = 'public, max-age=120'
            return response, 200

        supabase = get_supabase_client()
        if not supabase:
            response = jsonify({"success": False, "submissions": []})
            response.headers['Content-Type'] = 'application/json'
            return response, 200

        # Calculate 24 hours ago
        twenty_four_hours_ago = (datetime.utcnow() - timedelta(hours=24)).isoformat()

        # Get Twitter task submissions from last 24 hours
        twitter_submissions = safe_supabase_operation(
            lambda: supabase.table('twitter_task_log')\
                .select('wallet_address, reward_amount, created_at, twitter_url')\
                .gte('created_at', twenty_four_hours_ago)\
                .order('created_at', desc=True)\
                .limit(50)\
                .execute(),
            fallback_result=type('obj', (object,), {'data': []})(),
            operation_name="get recent twitter tasks"
        )

        # Get Telegram task submissions from last 24 hours
        telegram_submissions = safe_supabase_operation(
            lambda: supabase.table('telegram_task_log')\
                .select('wallet_address, reward_amount, created_at, telegram_url')\
                .gte('created_at', twenty_four_hours_ago)\
                .order('created_at', desc=True)\
                .limit(50)\
                .execute(),
            fallback_result=type('obj', (object,), {'data': []})(),
            operation_name="get recent telegram tasks"
        )

        # Get Facebook task submissions from last 24 hours
        facebook_submissions = safe_supabase_operation(
            lambda: supabase.table('facebook_task_log')\
                .select('wallet_address, reward_amount, created_at, facebook_url')\
                .gte('created_at', twenty_four_hours_ago)\
                .order('created_at', desc=True)\
                .limit(50)\
                .execute(),
            fallback_result=type('obj', (object,), {'data': []})(),
            operation_name="get recent facebook tasks"
        )

        # Combine and format submissions WITH MESSAGES/LINKS
        all_submissions = []

        # Add Twitter submissions WITH LINKS - USE CACHED USERNAMES
        if twitter_submissions and twitter_submissions.data:
            for sub in twitter_submissions.data:
                wallet = sub.get('wallet_address', '')

                all_submissions.append({
                    'wallet_address': wallet,
                    'display_name': f"{wallet[:6]}...{wallet[-4:]}",
                    'reward_amount': float(sub.get('reward_amount', 0)),
                    'created_at': sub.get('created_at'),
                    'platform': 'Twitter',
                    'submission_url': sub.get('twitter_url', ''),
                    'submission_type': 'twitter_post',
                    'status': sub.get('status', 'completed'),
                    'rejection_reason': sub.get('rejection_reason')
                })

        # Add Telegram submissions WITH LINKS
        if telegram_submissions and telegram_submissions.data:
            for sub in telegram_submissions.data:
                wallet = sub.get('wallet_address', '')

                all_submissions.append({
                    'wallet_address': wallet,
                    'display_name': f"{wallet[:6]}...{wallet[-4:]}",
                    'reward_amount': float(sub.get('reward_amount', 0)),
                    'created_at': sub.get('created_at'),
                    'platform': 'Telegram',
                    'submission_url': sub.get('telegram_url', ''),
                    'submission_type': 'telegram_post',
                    'status': sub.get('status', 'completed'),
                    'rejection_reason': sub.get('rejection_reason')
                })

        # Add Facebook submissions WITH LINKS
        if facebook_submissions and facebook_submissions.data:
            for sub in facebook_submissions.data:
                wallet = sub.get('wallet_address', '')

                all_submissions.append({
                    'wallet_address': wallet,
                    'display_name': f"{wallet[:6]}...{wallet[-4:]}",
                    'reward_amount': float(sub.get('reward_amount', 0)),
                    'created_at': sub.get('created_at'),
                    'platform': 'Facebook',
                    'submission_url': sub.get('facebook_url', ''),
                    'submission_type': 'facebook_post',
                    'status': sub.get('status', 'completed'),
                    'rejection_reason': sub.get('rejection_reason')
                })


        # Sort by created_at (newest first)
        all_submissions.sort(key=lambda x: x['created_at'], reverse=True)

        # Limit to 20 most recent
        all_submissions = all_submissions[:20]

        logger.info(f"✅ Returning {len(all_submissions)} recent daily task submissions")

        result = {
            "success": True,
            "submissions": all_submissions,
            "total_count": len(all_submissions)
        }

        # Cache for 2 minutes for better performance
        api_cache.set(cache_key, result, ttl=120)

        response = jsonify(result)
        response.headers['Content-Type'] = 'application/json'
        response.headers['Cache-Control'] = 'public, max-age=120'
        return response, 200

    except Exception as e:
        logger.error(f"❌ Error getting recent daily tasks: {e}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        error_response = jsonify({"success": False, "submissions": [], "error": str(e)})
        error_response.headers['Content-Type'] = 'application/json'
        return error_response, 500

@routes.route("/api/learn-earn-participants", methods=["GET"])
def get_learn_earn_participants():
    """Get Learn & Earn participants for a specific date or date range"""
    try:
        from datetime import datetime
        from supabase_client import get_supabase_client

        supabase = get_supabase_client()
        if not supabase:
            return jsonify({"success": False, "participants": []})

        # Get date parameter (format: YYYY-MM-DD)
        target_date = request.args.get('date')

        if target_date:
            # Query for specific date with proper UTC timezone format
            start_datetime = f"{target_date}T00:00:00Z"
            end_datetime = f"{target_date}T23:59:59Z"
        else:
            # Default to today with proper UTC timezone format
            today = datetime.utcnow().strftime('%Y-%m-%d')
            start_datetime = f"{today}T00:00:00Z"
            end_datetime = f"{today}T23:59:59Z"

        logger.info(f"📊 Fetching Learn & Earn participants for {target_date or 'today'}")
        logger.info(f"🕐 Date range: {start_datetime} to {end_datetime}")

        # Get all Learn & Earn participants for the date
        participants = safe_supabase_operation(
            lambda: supabase.table('learnearn_log')\
                .select('wallet_address, amount_g$, timestamp, transaction_hash, quiz_id')\
                .gte('timestamp', start_datetime)\
                .lte('timestamp', end_datetime)\
                .eq('status', True)\
                .order('timestamp', desc=False)\
                .execute(),
            fallback_result=type('obj', (object,), {'data': []})(),
            operation_name="get learn earn participants"
        )

        # Format participants
        formatted_participants = []
        total_g_disbursed = 0

        if participants and participants.data:
            logger.info(f"✅ Found {len(participants.data)} Learn & Earn participants")
            for p in participants.data:
                wallet = p.get('wallet_address', '')
                amount = float(p.get('amount_g$', 0))
                total_g_disbursed += amount

                formatted_participants.append({
                    'wallet_address': wallet,
                    'display_name': f"{wallet[:6]}...{wallet[-4:]}",
                    'amount_g$': amount,
                    'amount_formatted': f"{amount:,.1f} G$",
                    'timestamp': p.get('timestamp'),
                    'transaction_hash': p.get('transaction_hash', 'N/A'),
                    'quiz_id': p.get('quiz_id', 'N/A')
                })
        else:
            logger.info(f"ℹ️ No Learn & Earn participants found for {target_date or 'today'}")

        return jsonify({
            "success": True,
            "participants": formatted_participants,
            "total_count": len(formatted_participants),
            "total_g_disbursed": total_g_disbursed,
            "total_g_disbursed_formatted": f"{total_g_disbursed:,.2f} G$",
            "date": target_date if target_date else datetime.utcnow().strftime('%Y-%m-%d')
        })

    except Exception as e:
        logger.error(f"❌ Error getting Learn & Earn participants: {e}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        return jsonify({
            "success": False,
            "participants": [],
            "total_count": 0,
            "total_g_disbursed": 0,
            "error": str(e)
        })

@routes.route("/api/screenshot/<path:filename>", methods=["GET"])
def serve_screenshot(filename):
    """Serve screenshot from Object Storage"""
    try:
        from object_storage_client import download_screenshot
        from flask import send_file
        import io

        # Download from Object Storage
        file_data = download_screenshot(filename)

        if not file_data:
            return jsonify({"success": False, "error": "Screenshot not found"}), 404

        # Return as image
        return send_file(
            io.BytesIO(file_data),
            mimetype='image/png',
            as_attachment=False
        )

    except Exception as e:
        logger.error(f"❌ Error serving screenshot: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

@routes.route("/api/community-screenshots", methods=["GET"])
def get_community_screenshots():
    """Get community screenshots for homepage"""
    try:
        from community_stories.community_stories_service import community_stories_service
        from supabase_client import get_supabase_client
        from cache_utils import api_cache

        # Check cache first (2 minute TTL)
        cache_key = "community_screenshots"
        cached_result = api_cache.get(cache_key)
        if cached_result:
            return jsonify(cached_result)

        supabase = get_supabase_client()
        if not supabase:
            return jsonify({"success": False, "screenshots": []})

        limit = int(request.args.get('limit', 12))

        result = community_stories_service.get_screenshots_for_homepage(limit)

        if result.get('success') and result.get('screenshots'):
            # Display names are now just wallet truncations (no username lookup)
            for screenshot in result['screenshots']:
                wallet = screenshot.get('wallet_address', '')
                screenshot['display_name'] = f"{wallet[:6]}...{wallet[-4:]}"

        # Cache for 2 minutes for better performance
        api_cache.set(cache_key, result, ttl=120)

        return jsonify(result)

    except Exception as e:
        logger.error(f"❌ Error getting community screenshots: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

@routes.route("/api/recent-community-stories", methods=["GET"])
def get_recent_community_stories():
    """Get recent approved community stories"""
    try:
        from supabase_client import get_supabase_client

        supabase = get_supabase_client()
        if not supabase:
            return jsonify({"success": False, "stories": []})

        limit = int(request.args.get('limit', 50))

        # Get approved community stories (both high and low rewards)
        stories = safe_supabase_operation(
            lambda: supabase.table('community_stories_submissions')\
                .select('*')\
                .in_('status', ['approved_high', 'approved_low'])\
                .order('reviewed_at', desc=True)\
                .limit(limit)\
                .execute(),
            fallback_result=type('obj', (object,), {'data': []})(),
            operation_name="get recent community stories"
        )

        # Format stories without username
        formatted_stories = []
        if stories and stories.data:
            for story in stories.data:
                wallet = story.get('wallet_address', '')

                formatted_stories.append({
                    'wallet_address': wallet,
                    'display_name': f"{wallet[:6]}...{wallet[-4:]}",
                    'reward_amount': float(story.get('reward_amount', 0)),
                    'reviewed_at': story.get('reviewed_at'),
                    'status': story.get('status'),
                    'tweet_url': story.get('tweet_url', ''),
                    'submission_id': story.get('submission_id')
                })

        return jsonify({
            "success": True,
            "stories": formatted_stories,
            "total_count": len(formatted_stories)
        })

    except Exception as e:
        logger.error(f"❌ Error getting recent community stories: {e}")
        return jsonify({"success": False, "stories": []})

@routes.route("/api/admin/maintenance-status", methods=["GET"])
@admin_required
def get_maintenance_status_api():
    feature = request.args.get('feature', 'wallet_connection')
    from maintenance_service import maintenance_service
    result = maintenance_service.get_maintenance_status(feature)
    return jsonify(result)

@routes.route("/api/admin/maintenance-status", methods=["POST"])
@admin_required
def set_maintenance_status_api():
    data = request.get_json()
    feature_name = data.get('feature_name')
    is_maintenance = data.get('is_maintenance')
    message = data.get('message')
    admin_wallet = session.get('wallet')
    
    from maintenance_service import maintenance_service
    result = maintenance_service.set_maintenance_status(feature_name, is_maintenance, message, admin_wallet)
    return jsonify(result)

@routes.route("/api/maintenance-status", methods=["GET"])
def public_maintenance_status():
    feature = request.args.get('feature', 'wallet_connection')
    wallet_address = request.args.get('wallet') # Get wallet from query param for exemption check
    
    from maintenance_service import maintenance_service
    result = maintenance_service.get_maintenance_status(feature)
    
    # Check if the specific wallet provided is an admin
    check_wallet = wallet_address or session.get('wallet')
    
    if check_wallet:
        from supabase_client import is_admin
        if is_admin(check_wallet):
            logger.info(f"🛡️ Admin {check_wallet[:8]}... detected, bypassing maintenance for {feature}")
            result['is_maintenance'] = False
            result['message'] = ""
            
    return jsonify(result)

@routes.route("/")
def index():
    """Main homepage with Connect Wallet style"""
    # If already logged in, redirect to overview
    if session.get("verified") and session.get("wallet"):
        return redirect("/overview")
    return render_template("homepage.html")

@routes.route("/login")
def login_page():
    """Legacy login page - redirect to homepage"""
    return redirect(url_for("routes.index"))

@routes.route("/login", methods=["POST"])
def login():
    """Legacy login endpoint - redirects to main page"""
    # This legacy login should ideally be updated or removed
    # For now, assuming it sets session['wallet'] and session['verified'] if needed
    # For the purpose of this edit, we assume session['wallet'] is set by other means if this is bypassed
    # If session['wallet'] is not set, the subsequent checks will handle redirection.
    return redirect(url_for("routes.index"))

@routes.route("/verify-ubi-page")
def verify_ubi_page():
    """Legacy verify page - redirects to main page"""
    return redirect(url_for("routes.index"))

@routes.route("/verify-ubi", methods=["POST"])
def verify_ubi():
    try:
        data = request.get_json()
        wallet_address = data.get("wallet", "").strip()
        referral_code = data.get("referral_code", None) # Get referral code from request
        track_analytics = data.get("track_analytics", False)

        if not wallet_address:
            return jsonify({"status": "error", "message": "⚠️ Wallet address required"}), 400

        # Use the correct function name from blockchain.py
        result = has_recent_ubi_claim(wallet_address)

        if result["status"] == "success":
            # Track successful verification
            analytics.track_verification_attempt(wallet_address, True)
            analytics.track_user_session(wallet_address)

            # Store in session
            session["wallet"] = wallet_address
            session["verified"] = True

            # Extract block and amount from the latest activity
            latest_activity = result.get("summary", {}).get("latest_activity", {})
            block_number = latest_activity.get("block", "N/A")
            claim_amount = latest_activity.get("amount", "N/A")

            # Process referral rewards automatically (CRITICAL: This happens during UBI verification)
            referral_recorded = False
            referral_error_message = None
            referrer_reward_tx = None
            referee_reward_tx = None

            if referral_code and referral_code.strip():
                try:
                    from referral_program.referral_service import referral_service
                    from referral_program.blockchain import referral_blockchain_service
                    from datetime import datetime

                    logger.info(f"🎁 ========================================")
                    logger.info(f"🎁 REFERRAL REWARD PROCESSING STARTED")
                    logger.info(f"🎁 Code: {referral_code}")
                    logger.info(f"🎁 New User (Referee): {wallet_address[:8]}...")
                    logger.info(f"🎁 ========================================")

                    # Step 1: Validate referral code
                    validation = referral_service.validate_referral_code(referral_code)
                    logger.info(f"🔍 Step 1 - Validation: {validation}")

                    if not validation.get('valid'):
                        error_msg = validation.get('error', 'Invalid referral code')
                        logger.error(f"❌ FAILED: {error_msg}")
                        raise Exception(error_msg)

                    referrer_wallet = validation['referrer_wallet']
                    logger.info(f"✅ Valid code - Referrer: {referrer_wallet[:8]}...")

                    # Step 2: Record the referral in database
                    logger.info(f"📝 Step 2 - Recording referral in database...")
                    record_result = referral_service.record_referral(
                        referral_code=referral_code,
                        referee_wallet=wallet_address
                    )
                    logger.info(f"🔍 Record result: {record_result}")

                    if not record_result.get('success'):
                        error_msg = record_result.get('error', 'Failed to record referral')
                        logger.error(f"❌ FAILED to record: {error_msg}")
                        raise Exception(error_msg)

                    referral_recorded = True
                    logger.info(f"✅ Referral recorded in database")

                    # Step 3: Disburse 200 G$ to REFERRER (User A who shared the code)
                    logger.info(f"💰 Step 3 - Disbursing 200 G$ to REFERRER {referrer_wallet[:8]}...")
                    referrer_result = referral_blockchain_service.disburse_referral_reward_sync(
                        wallet_address=referrer_wallet,
                        amount=200.0,
                        reward_type='referrer'
                    )
                    logger.info(f"🔍 Referrer disbursement result: {referrer_result}")

                    if referrer_result.get('success'):
                        referrer_reward_tx = referrer_result.get('tx_hash')
                        logger.info(f"✅ Referrer reward sent! TX: {referrer_reward_tx}")
                    else:
                        error_msg = referrer_result.get('error', 'Unknown blockchain error')
                        logger.error(f"❌ Referrer reward FAILED: {error_msg}")
                        referral_error_message = f"Referrer reward failed: {error_msg}"

                    # Step 4: Disburse 100 G$ to REFEREE (New user - User B)
                    logger.info(f"💰 Step 4 - Disbursing 100 G$ to REFEREE (new user) {wallet_address[:8]}...")
                    referee_result = referral_blockchain_service.disburse_referral_reward_sync(
                        wallet_address=wallet_address,
                        amount=100.0,
                        reward_type='referee'
                    )
                    logger.info(f"🔍 Referee disbursement result: {referee_result}")

                    if referee_result.get('success'):
                        referee_reward_tx = referee_result.get('tx_hash')
                        logger.info(f"✅ Referee reward sent! TX: {referee_reward_tx}")
                    else:
                        error_msg = referee_result.get('error', 'Unknown blockchain error')
                        logger.error(f"❌ Referee reward FAILED: {error_msg}")
                        if not referral_error_message:
                            referral_error_message = f"Referee reward failed: {error_msg}"

                    # Step 5: Log rewards to database
                    supabase_client = get_supabase_client()
                    if supabase_client:
                        if referrer_result.get('success'):
                            logger.info(f"📝 Logging referrer reward to database...")
                            safe_supabase_operation(
                                lambda: supabase_client.table('referral_rewards_log').insert({
                                    'wallet_address': referrer_wallet,
                                    'reward_amount': 200.0,
                                    'reward_type': 'referrer',
                                    'referral_code': referral_code,
                                    'tx_hash': referrer_reward_tx,
                                    'created_at': datetime.now().isoformat()
                                }).execute(),
                                fallback_result=None,
                                operation_name="log referrer reward"
                            )

                        if referee_result.get('success'):
                            logger.info(f"📝 Logging referee reward to database...")
                            safe_supabase_operation(
                                lambda: supabase_client.table('referral_rewards_log').insert({
                                    'wallet_address': wallet_address,
                                    'reward_amount': 100.0,
                                    'reward_type': 'referee',
                                    'referral_code': referral_code,
                                    'tx_hash': referee_reward_tx,
                                    'created_at': datetime.now().isoformat()
                                }).execute(),
                                fallback_result=None,
                                operation_name="log referee reward"
                            )

                        # Step 6: Update referral status
                        both_successful = referrer_result.get('success') and referee_result.get('success')
                        status_to_set = 'completed' if both_successful else 'failed'
                        logger.info(f"📝 Updating referral status to: {status_to_set}")

                        safe_supabase_operation(
                            lambda: supabase_client.table('referrals').update({
                                'status': status_to_set,
                                'completed_at': datetime.now().isoformat() if status_to_set == 'completed' else None,
                                'error_message': referral_error_message
                            }).eq('referral_code', referral_code).eq('referee_wallet', wallet_address).execute(),
                            fallback_result=None,
                            operation_name="update referral status"
                        )

                    # Final status log
                    logger.info(f"🎁 ========================================")
                    if referrer_result.get('success') and referee_result.get('success'):
                        logger.info(f"✅ ✅ ✅ REFERRAL REWARDS FULLY SUCCESSFUL! ✅ ✅ ✅")
                        logger.info(f"💰 Referrer {referrer_wallet[:8]}... received 200 G$")
                        logger.info(f"📜 TX: {referrer_reward_tx}")
                        logger.info(f"💰 Referee {wallet_address[:8]}... received 100 G$")
                        logger.info(f"📜 TX: {referee_reward_tx}")
                    else:
                        logger.error(f"⚠️ REFERRAL REWARDS PARTIALLY FAILED")
                        if referrer_result.get('success'):
                            logger.info(f"✅ Referrer got reward: {referrer_reward_tx}")
                        else:
                            logger.error(f"❌ Referrer reward failed")
                        if referee_result.get('success'):
                            logger.info(f"✅ Referee got reward: {referee_reward_tx}")
                        else:
                            logger.error(f"❌ Referee reward failed")
                    logger.info(f"🎁 ========================================")

                except Exception as ref_error:
                    logger.error(f"❌ ❌ ❌ REFERRAL PROCESSING EXCEPTION ❌ ❌ ❌")
                    logger.error(f"❌ Error: {ref_error}")
                    logger.exception("Full referral error traceback:")
                    referral_recorded = False
                    referral_error_message = str(ref_error)
                    logger.error(f"🎁 ========================================")

            # Set permanent session
            session.permanent = True

            return jsonify({
                'success': True,
                'message': 'Identity verification successful!',
                'wallet': wallet_address,
                'ubi_verified': True,
                'redirect_to': '/overview'
            })
        else:
            # Track failed verification
            analytics.track_verification_attempt(wallet_address, False)

            # Use the detailed message from blockchain.py
            error_message = result.get("message", "You need to claim G$ once every 24 hours to access GoodMarket.\n\nClaim G$ using:\n• MiniPay app (built into Opera Mini)\n• goodwallet.xyz\n• gooddapp.org")

            return jsonify({
                "status": "error",
                "message": error_message,
                "reason": "no_recent_claim",
                "help_links": {
                    "minipay": "https://www.opera.com/products/minipay",
                    "goodwallet": "https://goodwallet.xyz",
                    "gooddapp": "https://gooddapp.org"
                }
            }), 400

    except Exception as e:
        logger.exception("Verification error occurred")
        # Return custom message instead of generic error
        error_message = "You need to claim G$ once every 24 hours to access GoodMarket.\n\nClaim G$ using:\n• MiniPay app (built into Opera Mini)\n• goodwallet.xyz\n• gooddapp.org"
        return jsonify({
            "status": "error",
            "message": error_message,
            "reason": "verification_error"
        }), 500

@routes.route("/overview")
def overview():
    wallet = session.get('wallet') or session.get('wallet_address')
    verified = session.get('verified') or session.get('ubi_verified')
    username = None

    # Check if user has valid session
    if wallet and verified:
        # Validate UBI claim is still recent for authenticated users
        from blockchain import has_recent_ubi_claim
        ubi_check = has_recent_ubi_claim(wallet)

        if ubi_check["status"] != "success":
            # UBI claim expired - clear session and show guest view
            logger.warning(f"⚠️ Session expired for {wallet[:8]}... - showing guest view")
            session.clear()
            wallet = None
            verified = False
        else:
            # Valid session - track overview page visit
            analytics.track_page_view(wallet, "overview")

    # Get analytics - pass None for guest users, wallet for authenticated users
    stats = analytics.get_dashboard_stats(wallet if wallet and verified else None)

    # Debug logging
    logger.info(f"🔍 Overview page - Wallet: {wallet[:8] if wallet else 'Guest'}...")
    logger.info(f"🔍 Overview page - stats keys: {list(stats.keys())}")
    logger.info(f"🔍 Overview page - disbursement_analytics present: {'disbursement_analytics' in stats}")
    if 'disbursement_analytics' in stats:
        logger.info(f"🔍 Overview page - disbursement_analytics keys: {list(stats['disbursement_analytics'].keys())}")
        logger.info(f"🔍 Overview page - breakdown_formatted present: {'breakdown_formatted' in stats['disbursement_analytics']}")

    return render_template("overview.html",
                         wallet=wallet if wallet and verified else None,
                         data=stats)

@routes.route("/dashboard")
def dashboard():
    """Dashboard page"""
    wallet = session.get('wallet') or session.get('wallet_address')
    verified = session.get('verified') or session.get('ubi_verified')

    if not wallet or not verified:
        return redirect(url_for("routes.index"))

    # Validate UBI claim is still recent
    from blockchain import has_recent_ubi_claim
    ubi_check = has_recent_ubi_claim(wallet)

    if ubi_check["status"] != "success":
        # UBI claim expired - auto logout and redirect to homepage
        logger.warning(f"⚠️ Auto-logout: UBI verification expired for {wallet[:8]}...")
        session.clear()
        return redirect(url_for("routes.index"))



    # Track dashboard visit
    analytics.track_page_view(wallet, "dashboard")

    # Get user analytics
    stats = analytics.get_dashboard_stats(wallet)

    return render_template("dashboard.html",
                         wallet=wallet,
                         user_stats=stats.get("user_stats", {}),
                         gooddollar_info=stats.get("gooddollar_info", {}),
                         platform_stats=stats.get("platform_stats", {}))

@routes.route("/track-analytics", methods=["POST"])
def track_analytics_endpoint(): # Renamed to avoid conflict with analytics_service
    try:
        data = request.get_json()
        if not data:
            logger.error("❌ track-analytics: No JSON data received")
            return jsonify({"status": "error", "message": "No data provided"}), 400

        event = data.get("event")
        wallet = data.get("wallet")
        # Add username to track if available in request data
        username = data.get("username")

        logger.info(f"🔍 track-analytics: event='{event}', wallet='{wallet}', username='{username}'")

        if event and wallet:
            # Track page view (analytics.track_page_view only takes wallet and page)
            analytics.track_page_view(wallet, event)
            return jsonify({"status": "success"})

        missing = []
        if not event:
            missing.append("event")
        if not wallet:
            missing.append("wallet")

        error_msg = f"Missing required fields: {', '.join(missing)}"
        logger.error(f"❌ track-analytics: {error_msg}")
        return jsonify({"status": "error", "message": error_msg}), 400

    except Exception as e:
        logger.exception("❌ track-analytics error") # Use logger.exception for full traceback
        return jsonify({"status": "error", "message": str(e)}), 500

@routes.route("/ubi-tracker")
def ubi_tracker_page():
    if not session.get("verified") or not session.get("wallet"):
        return redirect(url_for("routes.index"))

    wallet = session.get("wallet")

    analytics.track_page_view(wallet, "ubi_tracker")

    return render_template("ubi_tracker.html",
                         wallet=wallet,
                         contract_count=len(GOODDOLLAR_CONTRACTS))

@routes.route("/logout")
def logout():
    wallet = session.get("wallet")
    if wallet:
        # Log logout to Supabase
        supabase_logger.log_logout(wallet)

    # Completely clear the session
    session.clear()

    # Create response with redirect
    response = redirect(url_for("routes.index"))

    # Clear all session cookies
    response.set_cookie('session', '', expires=0, path='/')
    response.set_cookie('wallet', '', expires=0, path='/')
    response.set_cookie('verified', '', expires=0, path='/')
    response.set_cookie('username', '', expires=0, path='/')

    # Add cache control headers to prevent caching
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate, private'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'

    return response


@routes.route("/news")
def news_feed_page():
    if not session.get("verified") or not session.get("wallet"):
        return redirect(url_for("routes.index"))

    wallet = session.get("wallet")

    # Track news page visit
    analytics.track_page_view(wallet, "news_feed")

    # Get news feed data for initial page load
    from news_feed import news_feed_service

    featured_news = news_feed_service.get_featured_news(limit=3)
    recent_news = news_feed_service.get_news_feed(limit=10)
    news_stats = news_feed_service.get_news_stats()

    return render_template("news_feed.html",
                         wallet=wallet,
                         featured_news=featured_news,
                         recent_news=recent_news,
                         news_stats=news_stats,
                         categories=news_feed_service.categories)

@routes.route('/news/article/<article_id>')
def news_article_page(article_id: str):
    """Individual news article page"""
    from news_feed import news_feed_service # Import moved here to avoid circular import issues if news_feed is used elsewhere before this route is called

    article = news_feed_service.get_news_article(article_id)

    if not article:
        # return render_template("404.html"), 404 # Assuming a 404 template exists
        return "Article not found", 404

    # Get the full article URL for sharing
    article_url = request.url

    # Prepare meta tags for social media sharing - this is now handled by passing article_url to the template
    # meta_tags = {
    #     "title": article.get('title', 'GoodDollar News'),
    #     "description": article.get('content', '')[:200], # Truncate description
    #     "image": article.get('image_url', ''),
    #     "url": article_url # Use the correctly constructed article URL
    # }

    # Add any additional session/wallet checks if this page requires authentication
    wallet = session.get("wallet")
    verified = session.get("verified")
    username = None
    if wallet and verified:
        # username = supabase_logger.get_username(wallet) # Username fetching moved to template rendering if needed
        analytics.track_page_view(wallet, f"news_article_{article_id}")

    return render_template("news_article.html",
                         article=article,
                         article_url=article_url, # Pass article_url to template
                         wallet=wallet if wallet and verified else None,
                         username=username if username else "Guest")


@routes.route("/api/admin/check", methods=["GET"])
@auth_required
def check_admin_status():
    """Check if current user is admin"""
    try:
        wallet = session.get("wallet")
        from supabase_client import is_admin

        is_admin_user = is_admin(wallet)

        return jsonify({
            "success": True,
            "is_admin": is_admin_user,
            "wallet": wallet[:8] + "..." if wallet else None
        })
    except Exception as e:
        logger.error(f"❌ Admin check error: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

@routes.route("/api/admin/users", methods=["GET"])
@admin_required
def get_all_users():
    """Get all users (admin only)"""
    try:
        supabase = get_supabase_client()
        if not supabase:
            return jsonify({"success": False, "error": "Database not available"}), 500

        limit = int(request.args.get('limit', 100))
        offset = int(request.args.get('offset', 0))

        # Get users with pagination
        users = safe_supabase_operation(
            lambda: supabase.table('user_data')\
                .select('wallet_address, username, ubi_verified, total_logins, last_login, created_at')\
                .order('created_at', desc=True)\
                .range(offset, offset + limit - 1)\
                .execute(),
            fallback_result=type('obj', (object,), {'data': []})(),
            operation_name="get all users"
        )

        return jsonify({
            "success": True,
            "users": users.data if users.data else [],
            "count": len(users.data) if users.data else 0
        })
    except Exception as e:
        logger.error(f"❌ Get users error: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

@routes.route("/api/admin/stats", methods=["GET"])
@admin_required
def get_admin_stats():
    """Get platform statistics (admin only)"""
    try:
        from analytics_service import analytics

        # Get comprehensive platform stats using the correct method
        platform_stats = analytics.get_global_analytics()

        # Extract relevant stats for admin dashboard
        stats = {
            "total_users": platform_stats.get("metrics", {}).get("total_users", 0),
            "verified_users": platform_stats.get("metrics", {}).get("successful_verifications", 0),
            "total_page_views": platform_stats.get("user_activity", {}).get("total_page_views", 0),
            "verification_rate": platform_stats.get("verification_stats", {}).get("success_rate", "0%")
        }

        return jsonify({
            "success": True,
            "stats": stats
        })
    except Exception as e:
        logger.error(f"❌ Get admin stats error: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

@routes.route("/api/admin/set-admin", methods=["POST"])
@admin_required
def set_user_admin_status():
    """Set admin status for a user (admin only)"""
    try:
        from supabase_client import set_admin_status, log_admin_action

        data = request.json
        target_wallet = data.get("wallet_address")
        is_admin_status = data.get("is_admin", False)

        if not target_wallet:
            return jsonify({"success": False, "error": "Wallet address required"}), 400

        admin_wallet = session.get("wallet")

        # Set admin status
        result = set_admin_status(target_wallet, is_admin_status)

        if result.get("success"):
            # Log admin action
            log_admin_action(
                admin_wallet=admin_wallet,
                action_type="set_admin_status",
                target_wallet=target_wallet,
                action_details={"is_admin": is_admin_status}
            )

        return jsonify(result)
    except Exception as e:
        logger.error(f"❌ Set admin status error: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

@routes.route("/api/admin/actions-log", methods=["GET"])
@admin_required
def get_admin_actions_log():
    """Get admin actions log (admin only)"""
    try:
        supabase = get_supabase_client()
        if not supabase:
            return jsonify({"success": False, "error": "Database not available"}), 500

        limit = int(request.args.get('limit', 50))
        offset = int(request.args.get('offset', 0))

        # Get admin actions with pagination
        actions = safe_supabase_operation(
            lambda: supabase.table('admin_actions_log')\
                .select('*')\
                .order('created_at', desc=True)\
                .range(offset, offset + limit - 1)\
                .execute(),
            fallback_result=type('obj', (object,), {'data': []})(),
            operation_name="get admin actions log"
        )

        return jsonify({
            "success": True,
            "actions": actions.data if actions.data else [],
            "count": len(actions.data) if actions.data else 0
        })
    except Exception as e:
        logger.error(f"❌ Get admin actions log error: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

@routes.route("/api/admin/reward-config", methods=["GET"])
@admin_required
def get_reward_config():
    """Get all reward configurations (admin only)"""
    try:
        from reward_config_service import reward_config_service

        result = reward_config_service.get_all_rewards()
        return jsonify(result)
    except Exception as e:
        logger.error(f"❌ Get reward config error: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

@routes.route("/api/admin/reward-config", methods=["POST"])
@admin_required
def update_reward_config():
    """Update reward configuration (admin only)"""
    try:
        from reward_config_service import reward_config_service

        data = request.json
        task_type = data.get('task_type')
        new_amount = float(data.get('reward_amount', 0))
        admin_wallet = session.get('wallet')

        if not task_type or task_type not in ['telegram_task', 'twitter_task', 'facebook_task']:
            return jsonify({"success": False, "error": "Invalid task type"}), 400

        result = reward_config_service.update_reward_amount(task_type, new_amount, admin_wallet)

        if result.get('success'):
            # Log admin action
            log_admin_action(
                admin_wallet=admin_wallet,
                action_type="update_reward_config",
                action_details={
                    "task_type": task_type,
                    "new_amount": new_amount
                }
            )

        return jsonify(result)
    except Exception as e:
        logger.error(f"❌ Update reward config error: {e}")
        return jsonify({"success": False, "error": str(e)}), 500



@routes.route("/api/admin/quiz-questions", methods=["GET"])
@admin_required
def get_quiz_questions():
    """Get all quiz questions (admin only)"""
    try:
        supabase = get_supabase_client()
        if not supabase:
            return jsonify({"success": False, "error": "Database not available"}), 500

        logger.info("📚 Fetching quiz questions from Supabase 'quiz_questions' table...")

        # Get all quiz questions
        questions = safe_supabase_operation(
            lambda: supabase.table('quiz_questions')\
                .select('*')\
                .order('created_at', desc=True)\
                .execute(),
            fallback_result=type('obj', (object,), {'data': []})(),
            operation_name="get quiz questions"
        )

        logger.info(f"✅ Retrieved {len(questions.data) if questions.data else 0} questions from Supabase")
        if questions.data and len(questions.data) > 0:
            logger.info(f"📝 Sample question: ID={questions.data[0].get('question_id')}, Question={questions.data[0].get('question')[:50]}...")

        return jsonify({
            "success": True,
            "questions": questions.data if questions.data else [],
            "count": len(questions.data) if questions.data else 0,
            "data_source": "supabase_quiz_questions_table"
        })
    except Exception as e:
        logger.error(f"❌ Get quiz questions error: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

@routes.route("/api/admin/quiz-questions", methods=["POST"])
@admin_required
def add_quiz_question():
    """Add new quiz question (admin only)"""
    try:
        data = request.json

        # Validate required fields
        required_fields = ['question_id', 'question', 'answer_a', 'answer_b', 'answer_c', 'answer_d', 'correct']
        for field in required_fields:
            if not data.get(field):
                return jsonify({"success": False, "error": f"Missing required field: {field}"}), 400

        # Validate correct answer is A, B, C, or D
        if data['correct'].upper() not in ['A', 'B', 'C', 'D']:
            return jsonify({"success": False, "error": "Correct answer must be A, B, C, or D"}), 400

        supabase = get_supabase_client()
        if not supabase:
            return jsonify({"success": False, "error": "Database not available"}), 500

        # Check if question_id already exists
        existing = safe_supabase_operation(
            lambda: supabase.table('quiz_questions')\
                .select('question_id')\
                .eq('question_id', data['question_id'])\
                .execute(),
            fallback_result=type('obj', (object,), {'data': []})(),
            operation_name="check question_id"
        )

        if existing.data and len(existing.data) > 0:
            return jsonify({"success": False, "error": "Question ID already exists"}), 400

        # Add new question
        from datetime import datetime
        question_data = {
            'question_id': data['question_id'],
            'question': data['question'],
            'answer_a': data['answer_a'],
            'answer_b': data['answer_b'],
            'answer_c': data['answer_c'],
            'answer_d': data['answer_d'],
            'correct': data['correct'].upper(),
            'created_at': datetime.utcnow().isoformat() + 'Z'
        }

        result = safe_supabase_operation(
            lambda: supabase.table('quiz_questions').insert(question_data).execute(),
            fallback_result=type('obj', (object,), {'data': []})(),
            operation_name="add quiz question"
        )

        if result.data:
            # Log admin action
            admin_wallet = session.get("wallet")
            log_admin_action(
                admin_wallet=admin_wallet,
                action_type="add_quiz_question",
                action_details={"question_id": data['question_id']}
            )

            logger.info(f"✅ Quiz question added: {data['question_id']}")
            return jsonify({"success": True, "question": result.data[0]})
        else:
            return jsonify({"success": False, "error": "Failed to add question"}), 500

    except Exception as e:
        logger.error(f"❌ Add quiz question error: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

@routes.route("/api/admin/quiz-questions/<question_id>", methods=["PUT"])
@admin_required
def update_quiz_question(question_id):
    """Update quiz question (admin only)"""
    try:
        data = request.json

        # Validate correct answer if provided
        if 'correct' in data and data['correct'].upper() not in ['A', 'B', 'C', 'D']:
            return jsonify({"success": False, "error": "Correct answer must be A, B, C, or D"}), 400

        supabase = get_supabase_client()
        if not supabase:
            return jsonify({"success": False, "error": "Database not available"}), 500

        # Build update data
        update_data = {}
        allowed_fields = ['question', 'answer_a', 'answer_b', 'answer_c', 'answer_d', 'correct']
        for field in allowed_fields:
            if field in data:
                update_data[field] = data[field].upper() if field == 'correct' else data[field]

        if not update_data:
            return jsonify({"success": False, "error": "No valid fields to update"}), 400

        # Update question
        result = safe_supabase_operation(
            lambda: supabase.table('quiz_questions')\
                .update(update_data)\
                .eq('question_id', question_id)\
                .execute(),
            fallback_result=type('obj', (object,), {'data': []})(),
            operation_name="update quiz question"
        )

        if result.data:
            # Log admin action
            admin_wallet = session.get("wallet")
            log_admin_action(
                admin_wallet=admin_wallet,
                action_type="update_quiz_question",
                action_details={"question_id": question_id, "updated_fields": list(update_data.keys())}
            )

            logger.info(f"✅ Quiz question updated: {question_id}")
            return jsonify({"success": True, "question": result.data[0]})
        else:
            return jsonify({"success": False, "error": "Question not found"}), 404

    except Exception as e:
        logger.error(f"❌ Update quiz question error: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

@routes.route("/api/admin/quiz-questions/<question_id>", methods=["DELETE"])
@admin_required
def delete_quiz_question(question_id):
    """Delete quiz question (admin only)"""
    try:
        supabase = get_supabase_client()
        if not supabase:
            return jsonify({"success": False, "error": "Database not available"}), 500

        # Delete question
        result = safe_supabase_operation(
            lambda: supabase.table('quiz_questions')\
                .delete()\
                .eq('question_id', question_id)\
                .execute(),
            fallback_result=type('obj', (object,), {'data': []})(),
            operation_name="delete quiz question"
        )

        if result.data:
            # Log admin action
            admin_wallet = session.get("wallet")
            log_admin_action(
                admin_wallet=admin_wallet,
                action_type="delete_quiz_question",
                action_details={"question_id": question_id}
            )

            logger.info(f"✅ Quiz question deleted: {question_id}")
            return jsonify({"success": True})
        else:
            return jsonify({"success": False, "error": "Question not found"}), 404

    except Exception as e:
        logger.error(f"❌ Delete quiz question error: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

@routes.route("/api/admin/quiz-questions/delete-all", methods=["DELETE"])
@admin_required
def delete_all_quiz_questions():
    """Delete all quiz questions (admin only)"""
    try:
        supabase = get_supabase_client()
        if not supabase:
            return jsonify({"success": False, "error": "Database not available"}), 500

        # Get count of questions before deletion
        count_result = safe_supabase_operation(
            lambda: supabase.table('quiz_questions').select('quiz_id').execute(),
            fallback_result=type('obj', (object,), {'data': []})(),
            operation_name="count quiz questions"
        )

        question_count = len(count_result.data) if count_result.data else 0

        if question_count == 0:
            return jsonify({"success": False, "error": "No questions to delete"}), 400

        # Delete all questions
        result = safe_supabase_operation(
            lambda: supabase.table('quiz_questions').delete().neq('quiz_id', 0).execute(),
            fallback_result=type('obj', (object,), {'data': []})(),
            operation_name="delete all quiz questions"
        )

        # Log admin action
        admin_wallet = session.get("wallet")
        log_admin_action(
            admin_wallet=admin_wallet,
            action_type="delete_all_quiz_questions",
            action_details={"deleted_count": question_count}
        )

        logger.info(f"✅ All quiz questions deleted: {question_count} questions")
        return jsonify({
            "success": True,
            "deleted_count": question_count
        })

    except Exception as e:
        logger.error(f"❌ Delete all quiz questions error: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

@routes.route("/api/admin/broadcast-message", methods=["POST"])
@admin_required
def send_broadcast_message():
    """Send broadcast message to all users (admin only)"""
    try:
        data = request.json
        title = data.get('title', '').strip()
        message = data.get('message', '').strip()

        if not title or not message:
            return jsonify({"success": False, "error": "Title and message are required"}), 400

        supabase = get_supabase_client()
        if not supabase:
            return jsonify({"success": False, "error": "Database not available"}), 500

        admin_wallet = session.get("wallet")

        from datetime import datetime
        broadcast_data = {
            'title': title,
            'message': message,
            'sender_wallet': admin_wallet,
            'is_active': True,
            'created_at': datetime.utcnow().isoformat()
        }

        result = safe_supabase_operation(
            lambda: supabase.table('admin_broadcast_messages').insert(broadcast_data).execute(),
            fallback_result=type('obj', (object,), {'data': []})(),
            operation_name="send broadcast message"
        )

        if result.data:
            # Log admin action
            log_admin_action(
                admin_wallet=admin_wallet,
                action_type="send_broadcast_message",
                action_details={"title": title, "message_length": len(message)}
            )

            logger.info(f"✅ Broadcast message sent by admin {admin_wallet[:8]}...")
            return jsonify({
                "success": True,
                "message": "Broadcast message sent successfully!",
                "broadcast_id": result.data[0].get('id')
            })
        else:
            return jsonify({"success": False, "error": "Failed to send broadcast message"}), 500

    except Exception as e:
        logger.error(f"❌ Send broadcast message error: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

@routes.route("/api/admin/broadcast-messages", methods=["GET"])
@admin_required
def get_broadcast_messages():
    """Get all broadcast messages (admin only)"""
    try:
        supabase = get_supabase_client()
        if not supabase:
            return jsonify({"success": False, "error": "Database not available"}), 500

        limit = int(request.args.get('limit', 50))

        messages = safe_supabase_operation(
            lambda: supabase.table('admin_broadcast_messages')\
                .select('*')\
                .order('created_at', desc=True)\
                .limit(limit)\
                .execute(),
            fallback_result=type('obj', (object,), {'data': []})(),
            operation_name="get broadcast messages"
        )

        return jsonify({
            "success": True,
            "messages": messages.data if messages.data else [],
            "count": len(messages.data) if messages.data else 0
        })

    except Exception as e:
        logger.error(f"❌ Get broadcast messages error: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

@routes.route("/api/admin/broadcast-message/<int:broadcast_id>", methods=["DELETE"])
@admin_required
def delete_broadcast_message(broadcast_id):
    """Delete/deactivate broadcast message (admin only)"""
    try:
        supabase = get_supabase_client()
        if not supabase:
            return jsonify({"success": False, "error": "Database not available"}), 500

        # Deactivate instead of delete
        result = safe_supabase_operation(
            lambda: supabase.table('admin_broadcast_messages')\
                .update({'is_active': False})\
                .eq('id', broadcast_id)\
                .execute(),
            fallback_result=type('obj', (object,), {'data': []})(),
            operation_name="deactivate broadcast message"
        )

        if result.data:
            admin_wallet = session.get("wallet")
            log_admin_action(
                admin_wallet=admin_wallet,
                action_type="delete_broadcast_message",
                action_details={"broadcast_id": broadcast_id}
            )

            logger.info(f"✅ Broadcast message {broadcast_id} deactivated")
            return jsonify({"success": True})
        else:
            return jsonify({"success": False, "error": "Message not found"}), 404

    except Exception as e:
        logger.error(f"❌ Delete broadcast message error: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

@routes.route("/api/admin/news-history", methods=["GET"])
@admin_required
def get_news_history():
    """Get all news articles (admin only)"""
    try:
        from news_feed import news_feed_service

        supabase = get_supabase_client()
        if not supabase:
            return jsonify({"success": False, "error": "Database not available"}), 500

        # Get all news articles
        news = safe_supabase_operation(
            lambda: supabase.table('news_articles')\
                .select('*')\
                .order('created_at', desc=True)\
                .execute(),
            fallback_result=type('obj', (object,), {'data': []})(),
            operation_name="get all news articles"
        )

        return jsonify({
            "success": True,
            "news": news.data if news.data else [],
            "count": len(news.data) if news.data else 0
        })

    except Exception as e:
        logger.error(f"❌ Error getting news history: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

@routes.route("/api/admin/news/<int:news_id>", methods=["DELETE"])
@admin_required
def delete_news_article(news_id):
    """Delete news article (admin only)"""
    try:
        supabase = get_supabase_client()
        if not supabase:
            return jsonify({"success": False, "error": "Database not available"}), 500

        # Delete news article
        result = safe_supabase_operation(
            lambda: supabase.table('news_articles')\
                .delete()\
                .eq('id', news_id)\
                .execute(),
            fallback_result=type('obj', (object,), {'data': []})(),
            operation_name="delete news article"
        )

        if result.data:
            # Log admin action
            admin_wallet = session.get('wallet')
            log_admin_action(
                admin_wallet=admin_wallet,
                action_type="delete_news_article",
                action_details={"news_id": news_id}
            )

            logger.info(f"✅ News article {news_id} deleted by admin {admin_wallet[:8]}...")
            return jsonify({"success": True})
        else:
            return jsonify({"success": False, "error": "News article not found"}), 404

    except Exception as e:
        logger.error(f"❌ Error deleting news article: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

@routes.route("/api/admin/publish-news", methods=["POST"])
@admin_required
def publish_news_article():
    """Publish a news article (admin only)"""
    try:
        from news_feed import news_feed_service

        # Get form data
        title = request.form.get('title', '').strip()
        content = request.form.get('content', '').strip()
        category = request.form.get('category', 'announcement')
        priority = request.form.get('priority', 'medium')
        featured = request.form.get('featured') == 'true'
        url = request.form.get('url', '').strip()

        # Validate required fields
        if not title or not content:
            return jsonify({"success": False, "error": "Title and content are required"}), 400

        # Handle image upload if present
        image_url = None
        if 'image' in request.files:
            image_file = request.files['image']
            if image_file and image_file.filename:
                # Upload to ImgBB
                try:
                    import requests
                    import base64

                    imgbb_api_key = os.getenv('IMGBB_API_KEY')
                    if not imgbb_api_key:
                        logger.warning("⚠️ IMGBB_API_KEY not configured - skipping image upload")
                    else:
                        # Reset file pointer to beginning and read image
                        image_file.seek(0)
                        image_data = image_file.read()

                        # Validate image data
                        if not image_data or len(image_data) == 0:
                            logger.error("❌ Image file is empty")
                            return jsonify({"success": False, "error": "Image file is empty"}), 400

                        # Encode to base64
                        encoded_image = base64.b64encode(image_data).decode('utf-8')

                        logger.info(f"📤 Uploading image to ImgBB: {image_file.filename} ({len(image_data)} bytes)")

                        # Upload to ImgBB
                        imgbb_response = requests.post(
                            'https://api.imgbb.com/1/upload',
                            data={
                                'key': imgbb_api_key,
                                'image': encoded_image,
                                'name': f"news_{title[:30]}"
                            },
                            timeout=30
                        )

                        logger.info(f"📥 ImgBB Response: {imgbb_response.status_code}")

                        if imgbb_response.status_code == 200:
                            imgbb_data = imgbb_response.json()
                            if imgbb_data.get('success'):
                                image_url = imgbb_data['data']['url']
                                logger.info(f"✅ Image uploaded to ImgBB: {image_url}")
                            else:
                                error_msg = imgbb_data.get('error', {}).get('message', 'Unknown error')
                                logger.error(f"❌ ImgBB API error: {error_msg}")
                                return jsonify({"success": False, "error": f"Image upload failed: {error_msg}"}), 500
                        else:
                            logger.error(f"❌ ImgBB upload failed: {imgbb_response.status_code} - {imgbb_response.text[:500]}")
                            return jsonify({"success": False, "error": f"Image upload failed with status {imgbb_response.status_code}"}), 500

                except Exception as img_error:
                    logger.error(f"❌ Image upload error: {img_error}")
                    import traceback
                    logger.error(f"Traceback: {traceback.format_exc()}")
                    return jsonify({"success": False, "error": f"Image upload error: {str(img_error)}"}), 500

        # Get admin wallet
        admin_wallet = session.get("wallet")

        # Add news article
        result = news_feed_service.add_news_article(
            title=title,
            content=content,
            category=category,
            priority=priority,
            author=f"Admin ({admin_wallet[:8]}...)",
            featured=featured,
            image_url=image_url,
            url=url if url else None
        )

        if result.get('success'):
            # Log admin action
            log_admin_action(
                admin_wallet=admin_wallet,
                action_type="publish_news_article",
                action_details={
                    "title": title,
                    "category": category,
                    "featured": featured,
                    "has_image": bool(image_url)
                }
            )

            logger.info(f"✅ News article published: {title}")
            return jsonify({
                "success": True,
                "message": "News article published successfully!",
                "article": result.get('article')
            })
        else:
            return jsonify({
                "success": False,
                "error": result.get('error', 'Failed to publish article')
            }), 500

    except Exception as e:
        logger.error(f"❌ Publish news article error: {e}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        return jsonify({"success": False, "error": str(e)}), 500

@routes.route("/api/admin/maintenance/learn-earn", methods=["GET"])
@admin_required
def get_learn_earn_maintenance():
    """Get Learn & Earn maintenance status"""
    try:
        from maintenance_service import maintenance_service

        status = maintenance_service.get_maintenance_status('learn_earn')
        return jsonify(status)
    except Exception as e:
        logger.error(f"❌ Error getting maintenance status: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

@routes.route("/api/admin/maintenance/learn-earn", methods=["POST"])
@admin_required
def set_learn_earn_maintenance():
    """Set Learn & Earn maintenance status"""
    try:
        from maintenance_service import maintenance_service

        data = request.json
        is_maintenance = data.get('is_maintenance', False)
        message = data.get('message', '')
        admin_wallet = session.get('wallet')

        if is_maintenance and not message:
            return jsonify({
                "success": False,
                "error": "Custom message is required when enabling maintenance mode"
            }), 400

        result = maintenance_service.set_maintenance_status(
            'learn_earn',
            is_maintenance,
            message,
            admin_wallet
        )

        return jsonify(result)
    except Exception as e:
        logger.error(f"❌ Error setting maintenance status: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

@routes.route("/api/admin/maintenance/minigames", methods=["GET"])
@admin_required
def get_minigames_maintenance():
    """Get Minigames maintenance status"""
    try:
        from maintenance_service import maintenance_service

        status = maintenance_service.get_maintenance_status('minigames')
        return jsonify(status)
    except Exception as e:
        logger.error(f"❌ Error getting minigames maintenance status: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

@routes.route("/api/admin/maintenance/minigames", methods=["POST"])
@admin_required
def set_minigames_maintenance():
    """Set Minigames maintenance status"""
    try:
        from maintenance_service import maintenance_service

        data = request.json
        is_maintenance = data.get('is_maintenance', False)
        message = data.get('message', '')
        admin_wallet = session.get('wallet')

        if is_maintenance and not message:
            return jsonify({
                "success": False,
                "error": "Custom message is required when enabling maintenance mode"
            }), 400

        result = maintenance_service.set_maintenance_status(
            'minigames',
            is_maintenance,
            message,
            admin_wallet
        )

        return jsonify(result)
    except Exception as e:
        logger.error(f"❌ Error setting minigames maintenance status: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

@routes.route("/api/admin/quiz-settings", methods=["GET"])
@admin_required
def get_quiz_settings():
    """Get current quiz settings"""
    try:
        from learn_and_earn.learn_and_earn import quiz_manager

        settings = quiz_manager.get_quiz_settings()
        return jsonify({
            "success": True,
            "settings": settings
        })
    except Exception as e:
        logger.error(f"❌ Error getting quiz settings: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

@routes.route("/api/admin/community-stories-settings", methods=["GET"])
@admin_required
def get_community_stories_settings():
    """Get Community Stories settings (admin only)"""
    try:
        from community_stories.community_stories_service import community_stories_service

        config = community_stories_service.get_config()

        # Get message from database
        supabase = get_supabase_client()
        message = None

        if supabase:
            result = safe_supabase_operation(
                lambda: supabase.table('maintenance_settings')\
                    .select('custom_message')\
                    .eq('feature_name', 'community_stories_message')\
                    .execute(),
                fallback_result=type('obj', (object,), {'data': []})(),
                operation_name="get community stories message"
            )

            if result.data and len(result.data) > 0:
                message = result.data[0].get('custom_message')

        return jsonify({
            "success": True,
            "settings": {
                "low_reward": config['LOW_REWARD'],
                "high_reward": config['HIGH_REWARD'],
                "required_mentions": config['REQUIRED_MENTIONS'],
                "window_start_day": config['WINDOW_START_DAY'],
                "window_end_day": config['WINDOW_END_DAY'],
                "message": message or """💰 Earn G$ by sharing our story:
2,000 G$ - Text post on Twitter/X
5,000 G$ - Video post (min. 30 seconds)

📋 Requirements:
Must use hashtags: @gooddollarorg @GoodDollarTeam
Post must be public
Original content only

📅 Participation Schedule:
Opens: 26th of each month at 12:00 AM UTC
Closes: 30th of each month at 11:59 PM UTC
Duration: 5 days only each month
After reward: Blocked until next 26th

⚠️ Late submissions after 30th are NOT accepted!"""
            }
        })
    except Exception as e:
        logger.error(f"❌ Error getting Community Stories settings: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

@routes.route("/api/admin/community-stories-settings", methods=["POST"])
@admin_required
def update_community_stories_settings():
    """Update Community Stories settings (admin only)"""
    try:
        data = request.json
        low_reward = data.get('low_reward')
        high_reward = data.get('high_reward')
        required_mentions = data.get('required_mentions')
        window_start_day = data.get('window_start_day')
        window_end_day = data.get('window_end_day')
        message = data.get('message', '').strip()

        if not all([low_reward, high_reward, required_mentions, window_start_day, window_end_day]):
            return jsonify({"success": False, "error": "All fields are required"}), 400

        supabase = get_supabase_client()
        if not supabase:
            return jsonify({"success": False, "error": "Database not available"}), 500

        # Store settings in database using custom_message field for JSON data
        settings_json = json.dumps({
            'low_reward': float(low_reward),
            'high_reward': float(high_reward),
            'required_mentions': str(required_mentions),
            'window_start_day': int(window_start_day),
            'window_end_day': int(window_end_day)
        })

        settings_data = {
            'feature_name': 'community_stories_config',
            'is_maintenance': False,  # Use boolean field properly
            'custom_message': settings_json  # Store JSON in text field
        }

        # Check if exists
        existing = safe_supabase_operation(
            lambda: supabase.table('maintenance_settings')\
                .select('id')\
                .eq('feature_name', 'community_stories_config')\
                .execute(),
            fallback_result=type('obj', (object,), {'data': []})(),
            operation_name="check community stories config"
        )

        if existing.data and len(existing.data) > 0:
            result = safe_supabase_operation(
                lambda: supabase.table('maintenance_settings')\
                    .update(settings_data)\
                    .eq('feature_name', 'community_stories_config')\
                    .execute(),
                fallback_result=type('obj', (object,), {'data': []})(),
                operation_name="update community stories config"
            )
        else:
            result = safe_supabase_operation(
                lambda: supabase.table('maintenance_settings').insert(settings_data).execute(),
                fallback_result=type('obj', (object,), {'data': []})(),
                operation_name="insert community stories config"
            )

        # Store message separately
        if message:
            message_data = {
                'feature_name': 'community_stories_message',
                'is_maintenance': False,  # Use boolean field properly
                'custom_message': message  # Store message in text field
            }

            existing_msg = safe_supabase_operation(
                lambda: supabase.table('maintenance_settings')\
                    .select('id')\
                    .eq('feature_name', 'community_stories_message')\
                    .execute(),
                fallback_result=type('obj', (object,), {'data': []})(),
                operation_name="check community stories message"
            )

            if existing_msg.data and len(existing_msg.data) > 0:
                safe_supabase_operation(
                    lambda: supabase.table('maintenance_settings')\
                        .update(message_data)\
                        .eq('feature_name', 'community_stories_message')\
                        .execute(),
                    fallback_result=type('obj', (object,), {'data': []})(),
                    operation_name="update community stories message"
                )
            else:
                safe_supabase_operation(
                    lambda: supabase.table('maintenance_settings').insert(message_data).execute(),
                    fallback_result=type('obj', (object,), {'data': []})(),
                    operation_name="insert community stories message"
                )

        if result.data:
            # Log admin action
            admin_wallet = session.get('wallet')
            log_admin_action(
                admin_wallet=admin_wallet,
                action_type="update_community_stories_settings",
                action_details={
                    "low_reward": low_reward,
                    "high_reward": high_reward,
                    "window_start_day": window_start_day,
                    "window_end_day": window_end_day,
                    "message_updated": bool(message)
                }
            )

            logger.info(f"✅ Community Stories settings updated by admin {admin_wallet[:8]}...")
            return jsonify({"success": True})
        else:
            return jsonify({"success": False, "error": "Failed to update settings"}), 500

    except Exception as e:
        logger.error(f"❌ Error updating Community Stories settings: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

@routes.route("/api/admin/insufficient-balance-message", methods=["GET"])
@admin_required
def get_insufficient_balance_message():
    """Get current insufficient balance error message"""
    try:
        supabase = get_supabase_client()
        if not supabase:
            return jsonify({"success": False, "error": "Database not available"}), 500

        # Get message from maintenance_settings table
        result = safe_supabase_operation(
            lambda: supabase.table('maintenance_settings')\
                .select('custom_message')\
                .eq('feature_name', 'learn_earn_insufficient_balance')\
                .execute(),
            fallback_result=type('obj', (object,), {'data': []})(),
            operation_name="get insufficient balance message"
        )

        message = None
        if result.data and len(result.data) > 0:
            message = result.data[0].get('custom_message')

        return jsonify({
            "success": True,
            "message": message
        })
    except Exception as e:
        logger.error(f"❌ Error getting insufficient balance message: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

@routes.route("/api/admin/insufficient-balance-message", methods=["POST"])
@admin_required
def update_insufficient_balance_message():
    """Update insufficient balance error message"""
    try:
        data = request.json
        message = data.get('message', '').strip()

        if not message:
            return jsonify({
                "success": False,
                "error": "Message is required"
            }), 400

        supabase = get_supabase_client()
        if not supabase:
            return jsonify({"success": False, "error": "Database not available"}), 500

        # Check if record exists
        existing = safe_supabase_operation(
            lambda: supabase.table('maintenance_settings')\
                .select('id')\
                .eq('feature_name', 'learn_earn_insufficient_balance')\
                .execute(),
            fallback_result=type('obj', (object,), {'data': []})(),
            operation_name="check existing message"
        )

        if existing.data and len(existing.data) > 0:
            # Update existing record
            result = safe_supabase_operation(
                lambda: supabase.table('maintenance_settings')\
                    .update({'custom_message': message})\
                    .eq('feature_name', 'learn_earn_insufficient_balance')\
                    .execute(),
                fallback_result=type('obj', (object,), {'data': []})(),
                operation_name="update insufficient balance message"
            )
        else:
            # Insert new record
            from datetime import datetime
            result = safe_supabase_operation(
                lambda: supabase.table('maintenance_settings').insert({
                    'feature_name': 'learn_earn_insufficient_balance',
                    'is_maintenance': False,
                    'custom_message': message,
                    'created_at': datetime.utcnow().isoformat()
                }).execute(),
                fallback_result=type('obj', (object,), {'data': []})(),
                operation_name="insert insufficient balance message"
            )

        if result.data:
            # Log admin action
            admin_wallet = session.get('wallet')
            log_admin_action(
                admin_wallet=admin_wallet,
                action_type="update_insufficient_balance_message",
                action_details={"message_length": len(message)}
            )

            logger.info(f"✅ Insufficient balance message updated by admin {admin_wallet[:8]}...")
            return jsonify({"success": True})
        else:
            return jsonify({"success": False, "error": "Failed to update message"}), 500

    except Exception as e:
        logger.error(f"❌ Error updating insufficient balance message: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

@routes.route("/api/admin/quiz-settings", methods=["POST"])
@admin_required
def update_quiz_settings():
    """Update quiz settings"""
    try:
        from learn_and_earn.learn_and_earn import quiz_manager

        data = request.json
        questions_per_quiz = data.get('questions_per_quiz')
        time_per_question = data.get('time_per_question')
        max_reward_per_quiz = data.get('max_reward_per_quiz')

        # Validate inputs
        if questions_per_quiz is not None and (questions_per_quiz < 5 or questions_per_quiz > 30):
            return jsonify({
                "success": False,
                "error": "Questions per quiz must be between 5 and 30"
            }), 400

        if time_per_question is not None and (time_per_question < 10 or time_per_question > 60):
            return jsonify({
                "success": False,
                "error": "Time per question must be between 10 and 60 seconds"
            }), 400

        if max_reward_per_quiz is not None and (max_reward_per_quiz < 500 or max_reward_per_quiz > 10000):
            return jsonify({
                "success": False,
                "error": "Max reward must be between 500 and 10,000 G$"
            }), 400

        result = quiz_manager.update_quiz_settings(
            questions_per_quiz=questions_per_quiz,
            time_per_question=time_per_question,
            max_reward_per_quiz=max_reward_per_quiz
        )

        if result.get('success'):
            # Log admin action
            admin_wallet = session.get('wallet')
            log_admin_action(
                admin_wallet=admin_wallet,
                action_type="update_quiz_settings",
                action_details={
                    "questions_per_quiz": questions_per_quiz,
                    "time_per_question": time_per_question,
                    "max_reward_per_quiz": max_reward_per_quiz
                }
            )

        return jsonify(result)
    except Exception as e:
        logger.error(f"❌ Error updating quiz settings: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

@routes.route("/api/referral/check/<referral_code>", methods=["GET"])
def check_referral_status(referral_code):
    """Check referral code status and history (for debugging)"""
    try:
        from referral_program.referral_service import referral_service

        # Validate code
        validation = referral_service.validate_referral_code(referral_code)

        # Get referrals using this code
        supabase = get_supabase_client()
        if not supabase:
            return jsonify({"success": False, "error": "Database not available"}), 500

        referrals = safe_supabase_operation(
            lambda: supabase.table('referrals').select('*').eq('referral_code', referral_code).execute(),
            fallback_result=type('obj', (object,), {'data': []})(),
            operation_name="get referrals by code"
        )

        rewards = safe_supabase_operation(
            lambda: supabase.table('referral_rewards_log').select('*').eq('referral_code', referral_code).execute(),
            fallback_result=type('obj', (object,), {'data': []})(),
            operation_name="get rewards by code"
        )

        return jsonify({
            "success": True,
            "referral_code": referral_code,
            "validation": validation,
            "referrals": referrals.data if referrals.data else [],
            "rewards": rewards.data if rewards.data else [],
            "total_referrals": len(referrals.data) if referrals.data else 0,
            "total_rewards": len(rewards.data) if rewards.data else 0
        })
    except Exception as e:
        logger.error(f"❌ Error checking referral status: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

@routes.route("/api/admin/daily-tasks/pending", methods=["GET"])
@admin_required
def get_pending_daily_tasks():
    """Get pending daily task submissions (admin only)"""
    try:
        supabase = get_supabase_client()
        if not supabase:
            return jsonify({"success": False, "error": "Database not available"}), 500

        # Get pending Telegram tasks
        telegram_pending = safe_supabase_operation(
            lambda: supabase.table('telegram_task_log')\
                .select('*')\
                .eq('status', 'pending')\
                .order('created_at', desc=False)\
                .execute(),
            fallback_result=type('obj', (object,), {'data': []})(),
            operation_name="get pending telegram tasks"
        )

        # Get pending Twitter tasks
        twitter_pending = safe_supabase_operation(
            lambda: supabase.table('twitter_task_log')\
                .select('*')\
                .eq('status', 'pending')\
                .order('created_at', desc=False)\
                .execute(),
            fallback_result=type('obj', (object,), {'data': []})(),
            operation_name="get pending twitter tasks"
        )

        # Get pending Telegram tasks
        telegram_pending = safe_supabase_operation(
            lambda: supabase.table('telegram_task_log')\
                .select('*')\
                .eq('status', 'pending')\
                .order('created_at', desc=False)\
                .execute(),
            fallback_result=type('obj', (object,), {'data': []})(),
            operation_name="get pending telegram tasks"
        )

        # Get pending Twitter tasks
        twitter_pending = safe_supabase_operation(
            lambda: supabase.table('twitter_task_log')\
                .select('*')\
                .eq('status', 'pending')\
                .order('created_at', desc=False)\
                .execute(),
            fallback_result=type('obj', (object,), {'data': []})(),
            operation_name="get pending twitter tasks"
        )

        # Get pending Facebook tasks
        facebook_pending = safe_supabase_operation(
            lambda: supabase.table('facebook_task_log')\
                .select('*')\
                .eq('status', 'pending')\
                .order('created_at', desc=False)\
                .execute(),
            fallback_result=type('obj', (object,), {'data': []})(),
            operation_name="get pending facebook tasks"
        )

        telegram_tasks = []
        if telegram_pending.data:
            for task in telegram_pending.data:
                telegram_tasks.append({
                    'id': task.get('id'),
                    'wallet_address': task.get('wallet_address'),
                    'url': task.get('telegram_url'),
                    'reward_amount': task.get('reward_amount'),
                    'created_at': task.get('created_at'),
                    'platform': 'telegram'
                })

        twitter_tasks = []
        if twitter_pending.data:
            for task in twitter_pending.data:
                twitter_tasks.append({
                    'id': task.get('id'),
                    'wallet_address': task.get('wallet_address'),
                    'url': task.get('twitter_url'),
                    'reward_amount': task.get('reward_amount'),
                    'created_at': task.get('created_at'),
                    'platform': 'twitter'
                })

        facebook_tasks = []
        if facebook_pending.data:
            for task in facebook_pending.data:
                facebook_tasks.append({
                    'id': task.get('id'),
                    'wallet_address': task.get('wallet_address'),
                    'url': task.get('facebook_url'),
                    'reward_amount': task.get('reward_amount'),
                    'created_at': task.get('created_at'),
                    'platform': 'facebook'
                })


        return jsonify({
            "success": True,
            "telegram_tasks": telegram_tasks,
            "twitter_tasks": twitter_tasks,
            "facebook_tasks": facebook_tasks,
            "total_pending": len(telegram_tasks) + len(twitter_tasks) + len(facebook_tasks)
        })

    except Exception as e:
        logger.error(f"❌ Error getting pending tasks: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

@routes.route("/api/admin/daily-tasks/approve", methods=["POST"])
@admin_required
def approve_daily_task():
    """Approve a daily task submission (admin only)"""
    try:
        data = request.json
        submission_id = data.get('submission_id')
        platform = data.get('platform')  # 'telegram' or 'twitter' or 'facebook'
        admin_wallet = session.get('wallet')

        if not submission_id or not platform:
            return jsonify({"success": False, "error": "Missing required fields"}), 400

        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        try:
            result = None
            if platform == 'telegram':
                from telegram_task.telegram_task import telegram_task_service
                result = loop.run_until_complete(
                    telegram_task_service.approve_submission(submission_id, admin_wallet)
                )
            elif platform == 'twitter':
                from twitter_task.twitter_task import twitter_task_service
                result = loop.run_until_complete(
                    twitter_task_service.approve_submission(submission_id, admin_wallet)
                )
            elif platform == 'facebook':
                from facebook_task.facebook_task import facebook_task_service
                result = loop.run_until_complete(
                    facebook_task_service.approve_submission(submission_id, admin_wallet)
                )
            else:
                return jsonify({"success": False, "error": "Invalid platform"}), 400

            # Log admin action
            if result and result.get('success'):
                log_admin_action(
                    admin_wallet=admin_wallet,
                    action_type=f"approve_{platform}_task",
                    action_details={"submission_id": submission_id}
                )

            return jsonify(result) if result else jsonify({"success": False, "error": "Failed to process approval"}), 500
        finally:
            loop.close()

    except Exception as e:
        logger.error(f"❌ Error approving task: {e}")
        import traceback
        logger.error(f"🔍 Traceback: {traceback.format_exc()}")
        return jsonify({"success": False, "error": str(e)}), 500

@routes.route("/api/admin/daily-tasks/reject", methods=["POST"])
@admin_required
def reject_daily_task():
    """Reject a daily task submission (admin only)"""
    try:
        data = request.json
        submission_id = data.get('submission_id')
        platform = data.get('platform')  # 'telegram' or 'twitter' or 'facebook'
        reason = data.get('reason', '')
        admin_wallet = session.get('wallet')

        if not submission_id or not platform:
            return jsonify({"success": False, "error": "Missing required fields"}), 400

        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        try:
            result = None
            if platform == 'telegram':
                from telegram_task.telegram_task import telegram_task_service
                result = loop.run_until_complete(
                    telegram_task_service.reject_submission(submission_id, admin_wallet, reason)
                )
            elif platform == 'twitter':
                from twitter_task.twitter_task import twitter_task_service
                result = loop.run_until_complete(
                    twitter_task_service.reject_submission(submission_id, admin_wallet, reason)
                )
            elif platform == 'facebook':
                from facebook_task.facebook_task import facebook_task_service
                result = loop.run_until_complete(
                    facebook_task_service.reject_submission(submission_id, admin_wallet, reason)
                )
            else:
                return jsonify({"success": False, "error": "Invalid platform"}), 400

            # Log admin action
            if result and result.get('success'):
                log_admin_action(
                    admin_wallet=admin_wallet,
                    action_type=f"reject_{platform}_task",
                    action_details={"submission_id": submission_id, "reason": reason}
                )

            return jsonify(result) if result else jsonify({"success": False, "error": "Failed to process rejection"}), 500
        finally:
            loop.close()

    except Exception as e:
        logger.error(f"❌ Error rejecting task: {e}")
        import traceback
        logger.error(f"🔍 Traceback: {traceback.format_exc()}")
        return jsonify({"success": False, "error": str(e)}), 500

@routes.route("/api/admin/quiz-questions/upload", methods=["POST"])
@admin_required
def upload_quiz_questions():
    """Upload quiz questions from TXT file (admin only)"""
    try:
        if 'file' not in request.files:
            return jsonify({"success": False, "error": "No file uploaded"}), 400

        file = request.files['file']

        if file.filename == '':
            return jsonify({"success": False, "error": "No file selected"}), 400

        if not file.filename.endswith('.txt'):
            return jsonify({"success": False, "error": "File must be .txt format"}), 400

        # Read file content
        content = file.read().decode('utf-8')

        # Parse questions from TXT content
        questions = []
        current_question = {}
        parse_errors = []
        line_number = 0

        for line in content.split('\n'):
            line_number += 1
            line = line.strip()

            if not line:
                # Empty line - end of question
                if current_question:
                    # Check if all required fields are present
                    required_fields = ['question_id', 'question', 'answer_a', 'answer_b', 'answer_c', 'answer_d', 'correct']
                    missing_fields = [f for f in required_fields if f not in current_question]

                    if missing_fields:
                        parse_errors.append(f"Question at line ~{line_number}: Missing fields: {', '.join(missing_fields)}")
                    else:
                        questions.append(current_question)
                    current_question = {}
                continue

            if line.startswith('QUESTION_ID:'):
                current_question['question_id'] = line.replace('QUESTION_ID:', '').strip()
            elif line.startswith('QUESTION:'):
                current_question['question'] = line.replace('QUESTION:', '').strip()
            elif line.startswith('A)') or line.startswith('A:'):
                current_question['answer_a'] = line.replace('A)', '').replace('A:', '').strip()
            elif line.startswith('B)') or line.startswith('B:'):
                current_question['answer_b'] = line.replace('B)', '').replace('B:', '').strip()
            elif line.startswith('C)') or line.startswith('C:'):
                current_question['answer_c'] = line.replace('C)', '').replace('C:', '').strip()
            elif line.startswith('D)') or line.startswith('D:'):
                current_question['answer_d'] = line.replace('D)', '').replace('D:', '').strip()
            elif line.startswith('CORRECT:'):
                correct = line.replace('CORRECT:', '').strip().upper()
                if correct in ['A', 'B', 'C', 'D']:
                    current_question['correct'] = correct
                else:
                    parse_errors.append(f"Line {line_number}: Invalid correct answer '{correct}'. Must be A, B, C, or D")

        # Add last question if exists
        if current_question:
            required_fields = ['question_id', 'question', 'answer_a', 'answer_b', 'answer_c', 'answer_d', 'correct']
            missing_fields = [f for f in required_fields if f not in current_question]

            if missing_fields:
                parse_errors.append(f"Last question: Missing fields: {', '.join(missing_fields)}")
            else:
                questions.append(current_question)

        if not questions:
            example_format = """
Expected format (each question must have ALL fields):

QUESTION_ID: Q001
QUESTION: What is GoodDollar?
A: A cryptocurrency for UBI
B: A bank
C: A credit card
D: A website
CORRECT: A

(Empty line between questions)

QUESTION_ID: Q002
QUESTION: How often can you claim UBI?
A: Monthly
B: Daily
C: Yearly
D: Once
CORRECT: B
"""
            error_msg = "No valid questions found in file."
            if parse_errors:
                error_msg += f" Errors found: {'; '.join(parse_errors[:3])}"
            error_msg += f" Please check file format. {example_format}"

            return jsonify({
                "success": False,
                "error": error_msg,
                "parse_errors": parse_errors,
                "example_format": example_format
            }), 400

        # Insert questions into database
        supabase = get_supabase_client()
        if not supabase:
            return jsonify({"success": False, "error": "Database not available"}), 500

        added_count = 0
        skipped_count = 0
        error_count = 0
        error_details = []

        admin_wallet = session.get("wallet")

        for q in questions:
            try:
                # Check if question_id already exists
                existing = safe_supabase_operation(
                    lambda: supabase.table('quiz_questions')\
                        .select('question_id')\
                        .eq('question_id', q['question_id'])\
                        .execute(),
                    fallback_result=type('obj', (object,), {'data': []})(),
                    operation_name="check question exists"
                )

                if existing.data and len(existing.data) > 0:
                    skipped_count += 1
                    logger.info(f"⚠️ Skipped duplicate question: {q['question_id']}")
                    continue

                # Add created_at timestamp
                from datetime import datetime
                q['created_at'] = datetime.utcnow().isoformat() + 'Z'

                # Insert question
                result = safe_supabase_operation(
                    lambda: supabase.table('quiz_questions').insert(q).execute(),
                    fallback_result=type('obj', (object,), {'data': []})(),
                    operation_name="insert question from file"
                )

                if result.data:
                    added_count += 1
                    logger.info(f"✅ Added question from file: {q['question_id']}")
                else:
                    error_count += 1
                    error_details.append(f"Failed to add {q['question_id']}")

            except Exception as e:
                error_count += 1
                error_details.append(f"{q.get('question_id', 'unknown')}: {str(e)}")
                logger.error(f"❌ Error adding question {q.get('question_id', 'unknown')}: {e}")

        # Log admin action
        log_admin_action(
            admin_wallet=admin_wallet,
            action_type="upload_quiz_questions",
            action_details={
                "total_questions": len(questions),
                "added": added_count,
                "skipped": skipped_count,
                "errors": error_count
            }
        )

        logger.info(f"✅ Quiz upload complete: {added_count} added, {skipped_count} skipped, {error_count} errors")

        return jsonify({
            "success": True,
            "total": len(questions),
            "added": added_count,
            "skipped": skipped_count,
            "errors": error_count,
            "error_details": error_details[:10]  # Limit to first 10 errors
        })

    except Exception as e:
        logger.error(f"❌ Upload quiz questions error: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

@routes.route("/api/admin/module-links", methods=["GET"])
@admin_required
def get_module_links():
    """Get all module links (admin only)"""
    try:
        supabase = get_supabase_client()
        if not supabase:
            return jsonify({"success": False, "error": "Database not available"}), 500

        # Get all module links
        links = safe_supabase_operation(
            lambda: supabase.table('learn_earn_module_links')\
                .select('*')\
                .order('display_order', desc=False)\
                .execute(),
            fallback_result=type('obj', (object,), {'data': []})(),
            operation_name="get module links"
        )

        return jsonify({
            "success": True,
            "links": links.data if links.data else [],
            "count": len(links.data) if links.data else 0
        })
    except Exception as e:
        logger.error(f"❌ Get module links error: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

@routes.route("/api/admin/module-links", methods=["POST"])
@admin_required
def add_module_link():
    """Add new module link (admin only) - supports auto-scraping from URL"""
    try:
        data = request.json
        title = data.get('title', '').strip()
        url = data.get('url', '').strip()
        description = data.get('description', '').strip()
        content = data.get('content', '').strip()
        reading_time_minutes = int(data.get('reading_time_minutes', 5))
        display_order = int(data.get('display_order', 1))

        if not title:
            return jsonify({"success": False, "error": "Title is required"}), 400

        # Auto-scrape content from URL if no content provided - ALWAYS ENABLED
        if url and not content:
            logger.info(f"🔍 🤖 AUTO-SCRAPING ENABLED - Fetching content from URL: {url}")
            try:
                import requests
                from bs4 import BeautifulSoup

                # Fetch webpage with comprehensive headers to avoid bot detection
                logger.info(f"📥 Downloading webpage...")
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
                    'Accept-Language': 'en-US,en;q=0.9',
                    'Accept-Encoding': 'gzip, deflate, br',
                    'DNT': '1',
                    'Connection': 'keep-alive',
                    'Upgrade-Insecure-Requests': '1',
                    'Sec-Fetch-Dest': 'document',
                    'Sec-Fetch-Mode': 'navigate',
                    'Sec-Fetch-Site': 'none',
                    'Cache-Control': 'max-age=0',
                }

                response = requests.get(url, timeout=15, headers=headers, allow_redirects=True)
                response.raise_for_status()
                logger.info(f"✅ Webpage downloaded successfully ({len(response.content)} bytes)")

                # Parse HTML
                soup = BeautifulSoup(response.content, 'html.parser')

                # Remove script, style, and nav elements
                for element in soup(['script', 'style', 'nav', 'footer', 'header', 'aside', 'iframe', 'noscript']):
                    element.decompose()

                # Extract main content (try common article containers, including Medium-specific)
                main_content = (
                    soup.find('article') or
                    soup.find('div', class_='postArticle-content') or  # Medium specific
                    soup.find('section', class_='section--body') or  # Medium specific
                    soup.find('main') or
                    soup.find('div', class_='content') or
                    soup.find('div', class_='article') or
                    soup.find('body')
                )

                if main_content:
                    logger.info(f"📄 Found main content container: {main_content.name}")
                    # Get text with basic HTML structure
                    scraped_html = ""

                    # Extract headings and paragraphs
                    for element in main_content.find_all(['h1', 'h2', 'h3', 'p', 'ul', 'ol']):
                        if element.name == 'h1':
                            scraped_html += f"<h2>{element.get_text().strip()}</h2>\n"
                        elif element.name == 'h2':
                            scraped_html += f"<h3>{element.get_text().strip()}</h3>\n"
                        elif element.name == 'h3':
                            scraped_html += f"<h3>{element.get_text().strip()}</h3>\n"
                        elif element.name == 'p':
                            text = element.get_text().strip()
                            if text:
                                scraped_html += f"<p>{text}</p>\n"
                        elif element.name == 'ul':
                            scraped_html += "<ul>\n"
                            for li in element.find_all('li', recursive=False):
                                scraped_html += f"<li>{li.get_text().strip()}</li>\n"
                            scraped_html += "</ul>\n"
                        elif element.name == 'ol':
                            scraped_html += "<ol>\n"
                            for li in element.find_all('li', recursive=False):
                                scraped_html += f"<li>{li.get_text().strip()}</li>\n"
                            scraped_html += "</ol>\n"

                    content = scraped_html.strip()

                    # Auto-calculate reading time (average 200 words per minute)
                    word_count = len(content.split())
                    reading_time_minutes = max(1, round(word_count / 200))

                    logger.info(f"✅ ✅ ✅ AUTO-SCRAPE SUCCESSFUL!")
                    logger.info(f"📊 Content: {len(content)} characters")
                    logger.info(f"📊 Words: {word_count}")
                    logger.info(f"⏰ Reading time: ~{reading_time_minutes} minutes")
                else:
                    logger.warning(f"⚠️ Could not find main content in {url}")

            except Exception as scrape_error:
                logger.error(f"❌ Auto-scrape error: {scrape_error}")
                import traceback
                logger.error(f"🔍 Traceback: {traceback.format_exc()}")

                # Provide helpful error message
                error_msg = str(scrape_error)
                if "403" in error_msg or "Forbidden" in error_msg:
                    error_msg = "Website blocked auto-scraping (403 Forbidden). Please copy and paste the content manually instead."
                elif "404" in error_msg:
                    error_msg = "Page not found (404). Please check the URL."
                elif "timeout" in error_msg.lower():
                    error_msg = "Request timed out. Please try again or paste content manually."
                else:
                    error_msg = f"Failed to scrape URL: {error_msg}"

                return jsonify({
                    "success": False,
                    "error": error_msg
                }), 400

        # Validate content exists
        if not content:
            return jsonify({"success": False, "error": "Content is required (or enable auto-scrape with valid URL)"}), 400

        supabase = get_supabase_client()
        if not supabase:
            return jsonify({"success": False, "error": "Database not available"}), 500

        from datetime import datetime
        link_data = {
            'title': title,
            'url': url,
            'description': description,
            'content': content,
            'reading_time_minutes': reading_time_minutes,
            'display_order': display_order,
            'is_active': True,
            'created_at': datetime.utcnow().isoformat(),
            'updated_at': datetime.utcnow().isoformat()
        }

        result = safe_supabase_operation(
            lambda: supabase.table('learn_earn_module_links').insert(link_data).execute(),
            fallback_result=type('obj', (object,), {'data': []})(),
            operation_name="add module link"
        )

        if result.data:
            admin_wallet = session.get('wallet')
            log_admin_action(
                admin_wallet=admin_wallet,
                action_type="add_module_link",
                action_details={"title": title, "url": url}
            )

            logger.info(f"✅ Module link added: {title}")
            return jsonify({"success": True, "link": result.data[0]})
        else:
            return jsonify({"success": False, "error": "Failed to add module link"}), 500

    except Exception as e:
        logger.error(f"❌ Add module link error: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

@routes.route("/api/admin/module-links/<int:link_id>", methods=["PUT"])
@admin_required
def update_module_link(link_id):
    """Update module link (admin only)"""
    try:
        data = request.json
        if not data:
            return jsonify({"success": False, "error": "No data provided"}), 400

        supabase = get_supabase_client()
        if not supabase:
            return jsonify({"success": False, "error": "Database not available"}), 500

        from datetime import datetime
        update_data = {}

        if 'title' in data:
            update_data['title'] = data['title'].strip()
        if 'url' in data:
            update_data['url'] = data['url'].strip()
        if 'description' in data:
            update_data['description'] = data['description'].strip()
        if 'content' in data:
            update_data['content'] = data['content'].strip()
        if 'reading_time_minutes' in data:
            update_data['reading_time_minutes'] = int(data['reading_time_minutes'])
        if 'display_order' in data:
            update_data['display_order'] = int(data['display_order'])
        if 'is_active' in data:
            update_data['is_active'] = data['is_active'] in [True, 'true', '1', 1]

        update_data['updated_at'] = datetime.utcnow().isoformat()

        result = safe_supabase_operation(
            lambda: supabase.table('learn_earn_module_links')\
                .update(update_data)\
                .eq('id', link_id)\
                .execute(),
            fallback_result=type('obj', (object,), {'data': []})(),
            operation_name="update module link"
        )

        if result.data:
            admin_wallet = session.get('wallet')
            log_admin_action(
                admin_wallet=admin_wallet,
                action_type="update_module_link",
                action_details={"link_id": link_id, "updated_fields": list(update_data.keys())}
            )

            logger.info(f"✅ Module link {link_id} updated")
            return jsonify({"success": True, "link": result.data[0]})
        else:
            return jsonify({"success": False, "error": "Link not found"}), 404

    except Exception as e:
        logger.error(f"❌ Update module link error: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

@routes.route("/api/admin/module-links/<int:link_id>", methods=["DELETE"])
@admin_required
def delete_module_link(link_id):
    """Delete module link (admin only)"""
    try:
        supabase = get_supabase_client()
        if not supabase:
            return jsonify({"success": False, "error": "Database not available"}), 500

        result = safe_supabase_operation(
            lambda: supabase.table('learn_earn_module_links')\
                .delete()\
                .eq('id', link_id)\
                .execute(),
            fallback_result=type('obj', (object,), {'data': []})(),
            operation_name="delete module link"
        )

        if result.data:
            admin_wallet = session.get('wallet')
            log_admin_action(
                admin_wallet=admin_wallet,
                action_type="delete_module_link",
                action_details={"link_id": link_id}
            )

            logger.info(f"✅ Module link {link_id} deleted")
            return jsonify({"success": True})
        else:
            return jsonify({"success": False, "error": "Link not found"}), 404

    except Exception as e:
        logger.error(f"❌ Delete module link error: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

@routes.route("/admin")
@auth_required
def admin_dashboard():
    """Admin dashboard page"""
    wallet = session.get("wallet")

    from supabase_client import is_admin
    if not is_admin(wallet):
        logger.warning(f"⚠️ Non-admin access attempt from {wallet[:8]}...")
        return redirect("/dashboard")

    logger.info(f"✅ Admin access granted to {wallet[:8]}...")

    return render_template("admin_dashboard.html", wallet=wallet)


    return render_template("forum_post_detail.html",
                         wallet=wallet,
                         username=username, # Pass username to template
                         post=post,
                         categories=community_forum_service.categories)

@routes.route("/learn-earn")
def learn_earn_page():
    if not session.get("verified") or not session.get("wallet"):
        return redirect(url_for("routes.index"))

    wallet = session.get("wallet")

    # Track Learn & Earn page visit
    analytics.track_page_view(wallet, "learn_earn")

    return render_template("learn_and_earn.html",
                         wallet=wallet)

# Username functionality removed


@routes.route('/api/p2p/history')
def get_p2p_history_api():
    """P2P trading has been removed - return empty history"""
    try:
        wallet = session.get('wallet')
        if not wallet or not session.get('verified'):
            return jsonify({"success": False, "error": "Not authenticated"}), 401

        logger.info(f"📋 P2P trading disabled - returning empty history for {wallet[:8]}...")

        return jsonify({
            "success": True,
            "trades": [],
            "total": 0,
            "message": "P2P trading feature has been disabled"
        })

    except Exception as e:
        logger.error(f"❌ Error in P2P history endpoint: {e}")
        return jsonify({
            "success": False,
            "error": str(e),
            "trades": [],
            "total": 0
        }), 500

@routes.route("/api/admin/community-stories-notifications", methods=["GET"])
@admin_required
def get_admin_notifications():
    """Get pending submissions for admin"""
    try:
        wallet = session.get("wallet")

        supabase = get_supabase_client()
        if not supabase:
            return jsonify({"success": False, "error": "Database not available"}), 500

        # Get pending submissions directly to include storage_path
        pending = safe_supabase_operation(
            lambda: supabase.table('community_stories_submissions')\
                .select('*')\
                .eq('status', 'pending')\
                .order('submitted_at', desc=True)\
                .execute(),
            fallback_result=type('obj', (object,), {'data': []})(),
            operation_name="get pending community stories"
        )

        # Format for admin display
        notifications = []
        if pending.data:
            for sub in pending.data:
                notifications.append({
                    'submission_id': sub.get('submission_id'),
                    'community_stories_submissions': sub
                })

        return jsonify({
            "success": True,
            "notifications": notifications,
            "count": len(notifications)
        })

    except Exception as e:
        logger.error(f"❌ Error getting admin notifications: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

@routes.route("/api/admin/developer-profile", methods=["POST"])
@admin_required
def upload_developer_profile():
    """Upload developer profile image (admin only) - supports multiple profiles"""
    try:
        from object_storage_client import upload_to_imgbb

        if 'image' not in request.files:
            return jsonify({"success": False, "error": "No image file provided"}), 400

        image_file = request.files['image']
        name = request.form.get('name', '').strip()
        position = request.form.get('position', '').strip()

        if not name or not position:
            return jsonify({"success": False, "error": "Name and position are required"}), 400

        # Upload to ImgBB
        upload_result = upload_to_imgbb(image_file)

        if not upload_result.get('success'):
            return jsonify({"success": False, "error": upload_result.get('error', 'Upload failed')}), 500

        image_url = upload_result.get('url')

        # Store in database
        supabase = get_supabase_client()
        if not supabase:
            return jsonify({"success": False, "error": "Database not available"}), 500

        from datetime import datetime
        profile_data = {
            'name': name,
            'position': position,
            'image_url': image_url,
            'is_active': True,
            'created_at': datetime.utcnow().isoformat()
        }

        # Always insert new profile (allows multiple developers)
        result = safe_supabase_operation(
            lambda: supabase.table('developer_profile').insert(profile_data).execute(),
            fallback_result=type('obj', (object,), {'data': []})(),
            operation_name="insert developer profile"
        )

        if result.data:
            admin_wallet = session.get('wallet')
            log_admin_action(
                admin_wallet=admin_wallet,
                action_type="upload_developer_profile",
                action_details={"name": name, "position": position}
            )

            logger.info(f"✅ Developer profile uploaded: {name}")
            return jsonify({"success": True, "profile": result.data[0]})
        else:
            return jsonify({"success": False, "error": "Failed to save profile"}), 500

    except Exception as e:
        logger.error(f"❌ Upload developer profile error: {e}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        return jsonify({"success": False, "error": str(e)}), 500

@routes.route("/api/developer-profile", methods=["GET"])
def get_developer_profile():
    """Get all active developer profiles for homepage"""
    try:
        supabase = get_supabase_client()
        if not supabase:
            return jsonify({"success": False, "profiles": []})

        result = safe_supabase_operation(
            lambda: supabase.table('developer_profile')\
                .select('*')\
                .eq('is_active', True)\
                .order('created_at', desc=False)\
                .execute(),
            fallback_result=type('obj', (object,), {'data': []})(),
            operation_name="get developer profiles"
        )

        profiles = result.data if result.data else []

        return jsonify({
            "success": True,
            "profiles": profiles,
            "count": len(profiles)
        })

    except Exception as e:
        logger.error(f"❌ Get developer profiles error: {e}")
        return jsonify({"success": False, "profiles": []})

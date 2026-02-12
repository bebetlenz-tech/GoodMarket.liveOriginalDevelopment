import logging
import asyncio
from flask import Blueprint, request, jsonify, render_template, session, redirect
from .minigames_manager import minigames_manager
from maintenance_service import maintenance_service

logger = logging.getLogger(__name__)

minigames_bp = Blueprint('minigames', __name__, url_prefix='/minigames')

@minigames_bp.route('/')
def minigames_home():
    """Minigames dashboard"""
    wallet = session.get('wallet') or session.get('wallet_address')
    verified = session.get('verified') or session.get('ubi_verified')

    if not wallet or not verified:
        return redirect('/')

    # Check maintenance mode from database
    maintenance_status = maintenance_service.get_maintenance_status('minigames')
    if maintenance_status.get('is_maintenance', False):
        maintenance_message = maintenance_status.get('message', 'Minigames are temporarily under maintenance. Please check back later.')
        return render_template('minigames.html', wallet=wallet, maintenance_mode=True, maintenance_message=maintenance_message)

    return render_template('minigames.html', wallet=wallet, maintenance_mode=False)

@minigames_bp.route('/api/check-limit/<game_type>')
def check_game_limit(game_type):
    """Check if user can play a game"""
    # Check maintenance mode from database
    maintenance_status = maintenance_service.get_maintenance_status('minigames')
    if maintenance_status.get('is_maintenance', False):
        return jsonify({'error': maintenance_status.get('message', 'Minigames are temporarily under maintenance')}), 503

    try:
        wallet = session.get('wallet')
        if not wallet or not session.get('verified'):
            return jsonify({'error': 'Not authenticated'}), 401

        # Removed coin_flip game type check
        if game_type == 'coin_flip':
            return jsonify({'success': False, 'error': 'Coin flip game is not available'}), 404

        limit_check = minigames_manager.check_daily_limit(wallet, game_type)

        return jsonify({
            'success': True,
            'limit_check': limit_check
        })

    except Exception as e:
        logger.error(f"❌ Error checking game limit: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@minigames_bp.route('/api/start-game', methods=['POST'])
def start_game():
    """Start a new minigame session"""
    # Check maintenance mode from database
    maintenance_status = maintenance_service.get_maintenance_status('minigames')
    if maintenance_status.get('is_maintenance', False):
        return jsonify({'error': maintenance_status.get('message', 'Minigames are temporarily under maintenance')}), 503

    try:
        wallet_address = session.get('wallet_address')
        if not wallet_address:
            return jsonify({'success': False, 'error': 'Not authenticated'}), 401

        data = request.json
        game_type = data.get('game_type')
        bet_amount = data.get('bet_amount', 0)

        if not game_type:
            return jsonify({'success': False, 'error': 'Game type required'}), 400

        # Removed coin_flip game type check
        if game_type == 'coin_flip':
            return jsonify({'success': False, 'error': 'Coin flip game is not available'}), 404

        # Validate bet amount for crash game
        if game_type == 'crash_game':
            if bet_amount < 10:
                return jsonify({'success': False, 'error': 'Minimum bet is 10 G$'}), 400

            # Check user has sufficient balance
            balance_info = minigames_manager.get_deposit_balance(wallet_address)
            if not balance_info.get('success'):
                return jsonify({'success': False, 'error': 'Failed to check balance'}), 500

            available_balance = balance_info.get('available_balance', 0)
            if bet_amount > available_balance:
                return jsonify({'success': False, 'error': f'Insufficient balance! You have {available_balance:.2f} G$ but need {bet_amount:.2f} G$'}), 400

        result = minigames_manager.start_game_session(wallet_address, game_type, bet_amount)
        return jsonify(result)

    except Exception as e:
        logger.error(f"❌ Error starting game: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@minigames_bp.route('/api/complete-game', methods=['POST'])
def complete_game():
    """Complete a game session"""
    try:
        wallet = session.get('wallet')
        if not wallet or not session.get('verified'):
            return jsonify({'error': 'Not authenticated'}), 401

        data = request.get_json()
        session_id = data.get('session_id')
        score = data.get('score', 0)
        game_data = data.get('game_data', {})

        if not session_id:
            return jsonify({'success': False, 'error': 'Session ID required'}), 400

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(
                minigames_manager.complete_game_session(session_id, score, game_data)
            )
        finally:
            loop.close()

        return jsonify(result)

    except Exception as e:
        logger.error(f"❌ Error completing game: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@minigames_bp.route('/api/balance')
def get_balance():
    """Get user's deposit balance and available winnings"""
    try:
        wallet = session.get('wallet')
        if not wallet or not session.get('verified'):
            return jsonify({'success': False, 'error': 'Not authenticated'}), 401

        # Balance is already cached in minigames_manager for 2 minutes
        balance_info = minigames_manager.get_deposit_balance(wallet)

        response = jsonify({
            'success': True,
            'available_balance': balance_info.get('available_balance', 0)
        })

        # Add cache headers to reduce client requests
        response.headers['Cache-Control'] = 'private, max-age=60'

        return response

    except Exception as e:
        logger.error(f"❌ Error getting balance: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@minigames_bp.route('/api/user-stats')
def get_user_stats():
    """Get user game statistics with total virtual tokens across all games"""
    try:
        wallet = session.get('wallet')
        if not wallet or not session.get('verified'):
            logger.warning("⚠️ Unauthenticated request to /api/user-stats")
            return jsonify({'success': False, 'error': 'Not authenticated'}), 401

        logger.info(f"📊 Getting user stats for {wallet[:8]}...")
        result = minigames_manager.get_user_stats(wallet)

        # Always ensure we have a valid response structure
        stats = result.get('stats', [])
        logger.info(f"📊 Retrieved {len(stats)} game stats for {wallet[:8]}...")

        total_tokens = sum(stat.get('virtual_tokens', 0) for stat in stats)

        logger.info(f"💰 Total tokens across all games for {wallet[:8]}...: {total_tokens}")

        # Log individual game tokens for debugging
        if stats:
            for stat in stats:
                game_type = stat.get('game_type', 'unknown')
                tokens = stat.get('virtual_tokens', 0)
                plays = stat.get('total_plays', 0)
                logger.info(f"   {game_type}: {tokens} tokens ({plays} plays)")
        else:
            logger.info(f"   No game stats found - user hasn't played any games yet")

        # Always return success with proper data structure
        response_data = {
            'success': True,
            'stats': stats,
            'total_virtual_tokens': total_tokens
        }

        logger.info(f"✅ Returning response: {response_data}")

        return jsonify(response_data)

    except Exception as e:
        logger.error(f"❌ Error getting user stats: {e}")
        import traceback
        logger.error(f"🔍 Traceback: {traceback.format_exc()}")
        # Return error with proper structure
        return jsonify({
            'success': False,
            'stats': [],
            'total_virtual_tokens': 0,
            'error': str(e)
        }), 500

@minigames_bp.route('/api/quiz-questions')
def get_quiz_questions():
    """Get quiz questions"""
    try:
        wallet = session.get('wallet')
        if not wallet or not session.get('verified'):
            return jsonify({'error': 'Not authenticated'}), 401

        difficulty = request.args.get('difficulty')
        questions = minigames_manager.get_quiz_questions(difficulty)

        return jsonify({
            'success': True,
            'questions': questions
        })

    except Exception as e:
        logger.error(f"❌ Error getting quiz questions: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@minigames_bp.route('/api/withdraw-winnings', methods=['POST'])
def withdraw_winnings():
    """Withdraw accumulated winnings"""
    try:
        wallet = session.get('wallet') or session.get('wallet_address')

        if not wallet:
            return jsonify({'success': False, 'error': 'Not logged in'})

        result = asyncio.run(minigames_manager.withdraw_winnings(wallet))
        return jsonify(result)

    except Exception as e:
        logger.error(f"❌ Withdrawal error: {e}")
        return jsonify({'success': False, 'error': str(e)})

@minigames_bp.route('/api/transaction-history')
def get_transaction_history():
    """Get minigames transaction history (withdrawals and rewards)"""
    try:
        wallet = session.get('wallet')
        if not wallet or not session.get('verified'):
            return jsonify({'error': 'Not authenticated'}), 401

        # Get transaction history from rewards log
        history = minigames_manager.supabase.table('minigame_rewards_log')\
            .select('*')\
            .eq('wallet_address', wallet)\
            .order('created_at', desc=True)\
            .limit(50)\
            .execute()

        return jsonify({
            'success': True,
            'transactions': history.data or []
        })

    except Exception as e:
        logger.error(f"❌ Error getting transaction history: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@minigames_bp.route('/api/merchant-address')
def get_merchant_address():
    """Get MERCHANT_ADDRESS wallet address for deposits"""
    try:
        import os
        from minigames.blockchain import minigames_blockchain

        # Get merchant address from blockchain service
        merchant_address = minigames_blockchain.merchant_address

        if not merchant_address:
            logger.error("❌ MERCHANT_ADDRESS not configured in blockchain service")
            return jsonify({'success': False, 'error': 'MERCHANT_ADDRESS not configured'}), 500

        logger.info(f"✅ Returning MERCHANT_ADDRESS: {merchant_address}")

        return jsonify({
            'success': True,
            'merchant_address': merchant_address
        })

    except Exception as e:
        logger.error(f"❌ Error getting MERCHANT_ADDRESS: {e}")
        import traceback
        logger.error(f"🔍 Traceback: {traceback.format_exc()}")
        return jsonify({'success': False, 'error': str(e)}), 500

@minigames_bp.route('/api/auto-verify-deposits', methods=['POST'])
def auto_verify_deposits():
    """Automatically verify pending deposits for user (similar to P2P trading)"""
    try:
        wallet = session.get('wallet')
        if not wallet or not session.get('verified'):
            return jsonify({'error': 'Not authenticated'}), 401

        logger.info(f"🔄 Auto-verifying deposits for {wallet[:8]}...")

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(
                minigames_manager.auto_verify_pending_deposits(wallet)
            )
        finally:
            loop.close()

        return jsonify(result)

    except Exception as e:
        logger.error(f"❌ Error auto-verifying deposits: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@minigames_bp.route('/api/game-logs')
def get_game_logs():
    """Get user's game play history with win/loss details, deposits, and withdrawals"""
    try:
        from flask import session

        wallet = session.get('wallet')
        if not wallet or not session.get('verified'):
            return jsonify({'error': 'Not authenticated'}), 401

        # Get game sessions
        game_sessions = minigames_manager.supabase.table('minigame_sessions')\
            .select('*')\
            .eq('wallet_address', wallet)\
            .eq('game_type', 'crash_game')\
            .order('completed_at', desc=True)\
            .limit(50)\
            .execute()

        game_logs = []
        for game_session in (game_sessions.data or []):
            game_data = game_session.get('game_data', {})
            bet_amount = game_session.get('bet_amount', 0)
            winnings = game_session.get('g_dollar_earned', 0)

            game_logs.append({
                'session_id': game_session.get('session_id'),
                'date': game_session.get('completed_at') or game_session.get('started_at'),
                'bet_amount': bet_amount,
                'multiplier': game_data.get('multiplier', '0.00'),
                'result': 'WIN' if winnings > 0 else 'LOSS',
                'winnings': winnings,
                'profit_loss': winnings - bet_amount,
                'cashed_out': game_data.get('cashed_out', False),
                'crashed': game_data.get('crashed', False)
            })

        # Get deposit history
        deposits = minigames_manager.supabase.table('minigame_deposits_log')\
            .select('*')\
            .eq('wallet_address', wallet)\
            .order('created_at', desc=True)\
            .limit(50)\
            .execute()

        deposit_logs = []
        for deposit in (deposits.data or []):
            deposit_logs.append({
                'date': deposit.get('created_at'),
                'amount': deposit.get('amount', 0),
                'tx_hash': deposit.get('tx_hash'),
                'type': 'deposit'
            })

        # Get withdrawal history
        withdrawals = minigames_manager.supabase.table('minigame_withdrawals_log')\
            .select('*')\
            .eq('wallet_address', wallet)\
            .order('created_at', desc=True)\
            .limit(50)\
            .execute()

        withdrawal_logs = []
        for withdrawal in (withdrawals.data or []):
            withdrawal_logs.append({
                'date': withdrawal.get('created_at'),
                'amount': withdrawal.get('amount', 0),
                'tx_hash': withdrawal.get('tx_hash'),
                'type': 'withdrawal'
            })

        return jsonify({
            'success': True,
            'game_logs': game_logs,
            'deposit_logs': deposit_logs,
            'withdrawal_logs': withdrawal_logs,
            'total_games': len(game_logs),
            'total_deposits': len(deposit_logs),
            'total_withdrawals': len(withdrawal_logs)
        })

    except Exception as e:
        logger.error(f"❌ Error getting game logs: {e}")
        import traceback
        logger.error(f"🔍 Traceback: {traceback.format_exc()}")
        return jsonify({'success': False, 'error': str(e)}), 500

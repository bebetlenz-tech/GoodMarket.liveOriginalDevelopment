
import logging
from flask import Blueprint, request, jsonify, session, render_template, redirect
from .garden_manager import garden_manager

logger = logging.getLogger(__name__)

garden_bp = Blueprint('garden', __name__, url_prefix='/minigames/garden')

@garden_bp.route('/')
def garden_home():
    """Garden game home page"""
    try:
        wallet = session.get('wallet')
        if not wallet or not session.get('verified'):
            return redirect('/')
        
        return render_template('garden.html', wallet=wallet)
    except Exception as e:
        logger.error(f"❌ Error rendering garden home: {e}")
        return redirect('/minigames')

@garden_bp.route('/state')
def get_garden_state():
    """Get user's garden state"""
    try:
        wallet = session.get('wallet')
        if not wallet or not session.get('verified'):
            return jsonify({'success': False, 'error': 'Not authenticated'}), 401
        
        result = garden_manager.get_garden_state(wallet)
        
        # Log balance info for debugging
        if result.get('success') and result.get('balance'):
            logger.info(f"🌾 Garden state for {wallet[:8]}... - Balance: {result['balance']}")
        
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"❌ Error getting garden state: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@garden_bp.route('/balance')
def get_balance():
    """Get user's garden balance"""
    try:
        wallet = session.get('wallet')
        if not wallet or not session.get('verified'):
            return jsonify({'success': False, 'error': 'Not authenticated'}), 401
        
        balance = garden_manager.get_garden_balance(wallet)
        return jsonify({
            'success': True,
            'balance': balance
        })
        
    except Exception as e:
        logger.error(f"❌ Error getting garden balance: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@garden_bp.route('/withdraw', methods=['POST'])
def withdraw_balance():
    """Withdraw garden balance to user's wallet"""
    try:
        wallet = session.get('wallet')
        if not wallet or not session.get('verified'):
            return jsonify({'success': False, 'error': 'Not authenticated'}), 401
        
        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(
                garden_manager.withdraw_garden_balance(wallet)
            )
        finally:
            loop.close()
        
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"❌ Error withdrawing garden balance: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@garden_bp.route('/plant', methods=['POST'])
def plant_crop():
    """Plant a crop"""
    try:
        wallet = session.get('wallet')
        if not wallet or not session.get('verified'):
            return jsonify({'success': False, 'error': 'Not authenticated'}), 401
        
        data = request.json
        plot_id = data.get('plot_id')
        crop_type = data.get('crop_type')
        
        if plot_id is None or not crop_type:
            return jsonify({'success': False, 'error': 'Missing plot_id or crop_type'}), 400
        
        result = garden_manager.plant_crop(wallet, plot_id, crop_type)
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"❌ Error planting crop: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@garden_bp.route('/harvest', methods=['POST'])
def harvest_crop():
    """Harvest a crop"""
    try:
        wallet = session.get('wallet')
        if not wallet or not session.get('verified'):
            return jsonify({'success': False, 'error': 'Not authenticated'}), 401
        
        data = request.json
        plot_id = data.get('plot_id')
        
        if plot_id is None:
            return jsonify({'success': False, 'error': 'Missing plot_id'}), 400
        
        result = garden_manager.harvest_crop(wallet, plot_id)
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"❌ Error harvesting crop: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@garden_bp.route('/hire-helper', methods=['POST'])
def hire_helper():
    """Hire an AI helper"""
    try:
        wallet = session.get('wallet')
        if not wallet or not session.get('verified'):
            return jsonify({'success': False, 'error': 'Not authenticated'}), 401
        
        data = request.json
        helper_type = data.get('helper_type')
        
        if not helper_type:
            return jsonify({'success': False, 'error': 'Missing helper_type'}), 400
        
        result = garden_manager.hire_ai_helper(wallet, helper_type)
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"❌ Error hiring helper: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@garden_bp.route('/sync-balance', methods=['POST'])
def sync_balance():
    """Manually sync balance from minigames_transactions (for fixing existing users)"""
    try:
        wallet = session.get('wallet')
        if not wallet or not session.get('verified'):
            return jsonify({'success': False, 'error': 'Not authenticated'}), 401
        
        from supabase_client import get_supabase_client
        supabase = get_supabase_client()
        
        # Get all garden harvest transactions for this user
        transactions = supabase.table('minigames_transactions')\
            .select('*')\
            .eq('wallet_address', wallet)\
            .eq('transaction_type', 'garden_harvest')\
            .execute()
        
        if not transactions.data:
            return jsonify({'success': False, 'error': 'No harvest history found'}), 404
        
        # Calculate total from transactions
        total_earned = sum(float(tx['reward_amount']) for tx in transactions.data)
        
        # Get current balance
        balance = garden_manager.get_garden_balance(wallet)
        
        # Update or create balance record
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).isoformat()
        
        if balance['total_earned'] > 0:
            # Update existing
            supabase.table('garden_balance')\
                .update({
                    'total_earned': total_earned,
                    'available_balance': total_earned - balance['total_withdrawn'],
                    'updated_at': now
                })\
                .eq('wallet_address', wallet)\
                .execute()
        else:
            # Create new
            supabase.table('garden_balance').insert({
                'wallet_address': wallet,
                'total_earned': total_earned,
                'available_balance': total_earned,
                'total_withdrawn': 0,
                'last_harvest_at': now,
                'created_at': now,
                'updated_at': now
            }).execute()
        
        logger.info(f"✅ Synced balance for {wallet[:8]}... - Total: {total_earned} G$")
        
        return jsonify({
            'success': True,
            'message': f'Balance synced! Total earned: {total_earned} G$',
            'total_earned': total_earned,
            'available_balance': total_earned
        })
        
    except Exception as e:
        logger.error(f"❌ Error syncing balance: {e}")
        import traceback
        logger.error(f"❌ Traceback: {traceback.format_exc()}")
        return jsonify({'success': False, 'error': str(e)}), 500

@garden_bp.route('/withdrawal-history')
def get_withdrawal_history():
    """Get user's garden withdrawal history"""
    try:
        wallet = session.get('wallet')
        if not wallet or not session.get('verified'):
            return jsonify({'success': False, 'error': 'Not authenticated'}), 401
        
        from supabase_client import get_supabase_client
        supabase = get_supabase_client()
        
        # Get withdrawal history - fixed table name
        withdrawals = supabase.table('garden_withdrawals')\
            .select('*')\
            .eq('wallet_address', wallet)\
            .order('created_at', desc=True)\
            .limit(50)\
            .execute()
        
        # Return success even if no withdrawals (empty array is valid)
        return jsonify({
            'success': True,
            'withdrawals': withdrawals.data or []
        })
        
    except Exception as e:
        logger.error(f"❌ Error getting withdrawal history: {e}")
        # Return success with empty array on error (user-friendly)
        logger.warning(f"⚠️ Returning empty withdrawal history due to error")
        return jsonify({
            'success': True,
            'withdrawals': [],
            'warning': 'Could not load withdrawal history'
        }), 200

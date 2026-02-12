
import os
import logging
from datetime import datetime, timedelta, timezone
from supabase_client import get_supabase_client
from .garden_blockchain import garden_blockchain_service

logger = logging.getLogger(__name__)

class GardenManager:
    """Manage Garden minigame state and operations"""

    def __init__(self):
        self.supabase = get_supabase_client()
        logger.info("🌱 Garden Manager initialized")

    def get_garden_state(self, wallet_address: str) -> dict:
        """Get complete garden state for a user"""
        try:
            if not self.supabase:
                return {
                    'success': True,
                    'plots': [],
                    'harvests_today': 0,
                    'ai_helpers': [],
                    'balance': {
                        'total_earned': 0.0,
                        'total_withdrawn': 0.0,
                        'available_balance': 0.0
                    }
                }

            # Get plots
            plots_response = self.supabase.table('garden_plots')\
                .select('*')\
                .eq('wallet_address', wallet_address)\
                .execute()

            # Get today's harvests
            today = datetime.now(timezone.utc).date().isoformat()
            harvests_response = self.supabase.table('garden_harvests')\
                .select('*')\
                .eq('wallet_address', wallet_address)\
                .eq('harvest_date', today)\
                .execute()

            # Get AI helpers
            helpers_response = self.supabase.table('garden_ai_helpers')\
                .select('*')\
                .eq('wallet_address', wallet_address)\
                .eq('active', True)\
                .execute()

            # Get balance
            balance = self.get_garden_balance(wallet_address)

            harvests_today = harvests_response.data[0]['harvests_today'] if harvests_response.data else 0

            return {
                'success': True,
                'plots': plots_response.data or [],
                'harvests_today': harvests_today,
                'ai_helpers': helpers_response.data or [],
                'balance': balance
            }

        except Exception as e:
            logger.error(f"❌ Error getting garden state: {e}")
            return {'success': False, 'error': str(e)}

    def get_garden_balance(self, wallet_address: str) -> dict:
        """Get user's garden balance from Supabase (forced real-time)"""
        try:
            if not self.supabase:
                return {
                    'total_earned': 0.0,
                    'total_withdrawn': 0.0,
                    'available_balance': 0.0
                }
            
            # Query the database
            response = self.supabase.table('garden_balance')\
                .select('*')\
                .eq('wallet_address', wallet_address)\
                .execute()

            if response.data and len(response.data) > 0:
                balance_data = response.data[0]
                logger.info(f"💰 Supabase Balance Found for {wallet_address[:8]}: {balance_data['available_balance']}")
                return {
                    'total_earned': float(balance_data.get('total_earned', 0)),
                    'total_withdrawn': float(balance_data.get('total_withdrawn', 0)),
                    'available_balance': float(balance_data.get('available_balance', 0))
                }
            else:
                logger.warning(f"⚠️ No balance record in Supabase for {wallet_address[:8]}")
                return {
                    'total_earned': 0.0,
                    'total_withdrawn': 0.0,
                    'available_balance': 0.0
                }

        except Exception as e:
            logger.error(f"❌ Error getting garden balance: {e}")
            return {
                'total_earned': 0.0,
                'total_withdrawn': 0.0,
                'available_balance': 0.0
            }

    async def withdraw_garden_balance(self, wallet_address: str) -> dict:
        """Withdraw garden balance to user's wallet"""
        try:
            balance = self.get_garden_balance(wallet_address)
            available = balance['available_balance']

            if available < 200:
                return {
                    'success': False,
                    'error': 'Minimum withdrawal is 200 G$',
                    'available_balance': available
                }

            # Disburse via blockchain
            result = await garden_blockchain_service.disburse_garden_reward(
                wallet_address,
                available
            )

            if result['success']:
                # Update balance in database
                now = datetime.now(timezone.utc).isoformat()
                self.supabase.table('garden_balance')\
                    .update({
                        'total_withdrawn': balance['total_withdrawn'] + available,
                        'available_balance': 0.0,
                        'updated_at': now
                    })\
                    .eq('wallet_address', wallet_address)\
                    .execute()

                logger.info(f"✅ Garden withdrawal successful: {available} G$ to {wallet_address[:8]}...")

                return {
                    'success': True,
                    'amount': available,
                    'tx_hash': result['tx_hash'],
                    'message': f'Successfully withdrew {available} G$!'
                }
            else:
                return result

        except Exception as e:
            logger.error(f"❌ Error withdrawing garden balance: {e}")
            return {'success': False, 'error': str(e)}

    def plant_crop(self, wallet_address: str, plot_id: int, crop_type: str) -> dict:
        """Plant a crop on a plot"""
        try:
            now = datetime.now(timezone.utc).isoformat()

            # Check if plot exists
            existing = self.supabase.table('garden_plots')\
                .select('*')\
                .eq('wallet_address', wallet_address)\
                .eq('plot_id', plot_id)\
                .execute()

            if existing.data and existing.data[0]['status'] != 'empty':
                return {'success': False, 'error': 'Plot is not empty'}

            # Plant crop
            if existing.data:
                self.supabase.table('garden_plots')\
                    .update({
                        'crop_type': crop_type,
                        'planted_at': now,
                        'growth_percent': 0,
                        'status': 'growing',
                        'updated_at': now
                    })\
                    .eq('wallet_address', wallet_address)\
                    .eq('plot_id', plot_id)\
                    .execute()
            else:
                self.supabase.table('garden_plots')\
                    .insert({
                        'wallet_address': wallet_address,
                        'plot_id': plot_id,
                        'crop_type': crop_type,
                        'planted_at': now,
                        'growth_percent': 0,
                        'status': 'growing'
                    })\
                    .execute()

            logger.info(f"🌱 Planted {crop_type} on plot {plot_id} for {wallet_address[:8]}...")

            return {
                'success': True,
                'message': f'Successfully planted {crop_type}!'
            }

        except Exception as e:
            logger.error(f"❌ Error planting crop: {e}")
            return {'success': False, 'error': str(e)}

    def harvest_crop(self, wallet_address: str, plot_id: int) -> dict:
        """Harvest a crop from a plot"""
        try:
            # Check daily harvest limit
            today = datetime.now(timezone.utc).date().isoformat()
            harvests_response = self.supabase.table('garden_harvests')\
                .select('*')\
                .eq('wallet_address', wallet_address)\
                .eq('harvest_date', today)\
                .execute()

            harvests_today = harvests_response.data[0]['harvests_today'] if harvests_response.data else 0

            if harvests_today >= 5:
                return {
                    'success': False,
                    'error': 'Daily harvest limit reached (5/5)'
                }

            # Get plot
            plot_response = self.supabase.table('garden_plots')\
                .select('*')\
                .eq('wallet_address', wallet_address)\
                .eq('plot_id', plot_id)\
                .execute()

            if not plot_response.data:
                return {'success': False, 'error': 'Plot not found'}

            plot = plot_response.data[0]

            if plot['status'] != 'growing':
                return {'success': False, 'error': 'No crop to harvest'}

            # Calculate growth
            planted_at = datetime.fromisoformat(plot['planted_at'].replace('Z', '+00:00'))
            now = datetime.now(timezone.utc)
            time_elapsed = (now - planted_at).total_seconds()
            growth_time = 60  # 1 minute growth time
            growth_percent = min(100, (time_elapsed / growth_time) * 100)

            if growth_percent < 100:
                return {
                    'success': False,
                    'error': f'Crop not ready yet ({int(growth_percent)}% grown)'
                }

            # Award reward
            crop_rewards = {
                'tomato': 5.0,
                'corn': 25.0,
                'carrot': 150.0
            }
            reward = float(crop_rewards.get(plot.get('crop_type', 'tomato').lower(), 50.0))

            # Update harvest count
            now_iso = now.isoformat()
            if harvests_response.data:
                self.supabase.table('garden_harvests')\
                    .update({
                        'harvests_today': harvests_today + 1,
                        'total_earned': float(harvests_response.data[0]['total_earned']) + reward
                    })\
                    .eq('wallet_address', wallet_address)\
                    .eq('harvest_date', today)\
                    .execute()
            else:
                self.supabase.table('garden_harvests')\
                    .insert({
                        'wallet_address': wallet_address,
                        'harvest_date': today,
                        'harvests_today': 1,
                        'total_earned': reward
                    })\
                    .execute()

            # Update balance
            balance = self.get_garden_balance(wallet_address)
            new_total = balance['total_earned'] + reward
            new_available = balance['available_balance'] + reward

            balance_response = self.supabase.table('garden_balance')\
                .select('*')\
                .eq('wallet_address', wallet_address)\
                .execute()

            if balance_response.data:
                self.supabase.table('garden_balance')\
                    .update({
                        'total_earned': new_total,
                        'available_balance': new_available,
                        'updated_at': now_iso
                    })\
                    .eq('wallet_address', wallet_address)\
                    .execute()
            else:
                self.supabase.table('garden_balance')\
                    .insert({
                        'wallet_address': wallet_address,
                        'total_earned': new_total,
                        'total_withdrawn': 0.0,
                        'available_balance': new_available
                    })\
                    .execute()

            # Record transaction
            self.supabase.table('minigames_transactions')\
                .insert({
                    'wallet_address': wallet_address,
                    'transaction_type': 'garden_harvest',
                    'reward_amount': reward,
                    'transaction_date': now_iso
                })\
                .execute()

            # Clear plot
            self.supabase.table('garden_plots')\
                .update({
                    'crop_type': None,
                    'planted_at': None,
                    'growth_percent': 0,
                    'status': 'empty',
                    'updated_at': now_iso
                })\
                .eq('wallet_address', wallet_address)\
                .eq('plot_id', plot_id)\
                .execute()

            logger.info(f"🌾 Harvested plot {plot_id} for {wallet_address[:8]}... - Reward: {reward} G$")

            return {
                'success': True,
                'message': f'Harvested {plot["crop_type"]}! Earned {reward} G$',
                'reward': reward,
                'harvests_today': harvests_today + 1
            }

        except Exception as e:
            logger.error(f"❌ Error harvesting crop: {e}")
            return {'success': False, 'error': str(e)}

    def hire_ai_helper(self, wallet_address: str, helper_type: str) -> dict:
        """Hire an AI helper"""
        try:
            # Check if already hired
            existing = self.supabase.table('garden_ai_helpers')\
                .select('*')\
                .eq('wallet_address', wallet_address)\
                .eq('helper_type', helper_type)\
                .execute()

            if existing.data:
                return {'success': False, 'error': 'Helper already hired'}

            # Hire helper
            now = datetime.now(timezone.utc).isoformat()
            self.supabase.table('garden_ai_helpers')\
                .insert({
                    'wallet_address': wallet_address,
                    'helper_type': helper_type,
                    'hired_at': now,
                    'active': True
                })\
                .execute()

            logger.info(f"🤖 Hired {helper_type} for {wallet_address[:8]}...")

            return {
                'success': True,
                'message': f'Successfully hired {helper_type}!'
            }

        except Exception as e:
            logger.error(f"❌ Error hiring helper: {e}")
            return {'success': False, 'error': str(e)}


# Global instance
garden_manager = GardenManager()

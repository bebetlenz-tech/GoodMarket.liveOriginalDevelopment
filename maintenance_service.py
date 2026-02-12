from datetime import datetime
import logging
import json
from supabase_client import get_supabase_client

logger = logging.getLogger(__name__)

class MaintenanceService:
    """Service for managing maintenance mode"""

    def __init__(self):
        self.supabase = get_supabase_client()
        logger.info("🔧 Maintenance Service initialized")

    def get_maintenance_status(self, feature_name: str) -> dict:
        """Get maintenance status for a feature"""
        try:
            if not self.supabase:
                self.supabase = get_supabase_client()
            
            if not self.supabase:
                return {'success': True, 'is_maintenance': False, 'message': ''}

            result = self.supabase.table('maintenance_settings')\
                .select('*')\
                .eq('feature_name', feature_name)\
                .execute()

            if result.data and len(result.data) > 0:
                return {
                    'success': True,
                    'is_maintenance': result.data[0].get('is_maintenance', False),
                    'message': result.data[0].get('maintenance_message', 'Feature under maintenance')
                }
            else:
                return {
                    'success': True,
                    'is_maintenance': False,
                    'message': ''
                }
        except Exception as e:
            logger.error(f"❌ Error getting maintenance status: {e}")
            return {'success': False, 'is_maintenance': False, 'message': ''}

    def set_maintenance_status(self, feature_name: str, is_maintenance: bool, message: str, admin_wallet: str) -> dict:
        """Set maintenance status for a feature"""
        try:
            if not self.supabase:
                self.supabase = get_supabase_client()
            
            if not self.supabase:
                return {'success': False, 'error': 'Database connection not available'}

            # First, check if the record exists
            check = self.supabase.table('maintenance_settings')\
                .select('id')\
                .eq('feature_name', feature_name)\
                .execute()
            
            if not check.data:
                # Insert if not exists
                result = self.supabase.table('maintenance_settings')\
                    .insert({
                        'feature_name': feature_name,
                        'is_maintenance': is_maintenance,
                        'maintenance_message': message,
                        'updated_by': admin_wallet
                    })\
                    .execute()
            else:
                # Update if exists
                result = self.supabase.table('maintenance_settings')\
                    .update({
                        'is_maintenance': is_maintenance,
                        'maintenance_message': message,
                        'updated_by': admin_wallet,
                        'updated_at': datetime.now().isoformat()
                    }) \
                .eq('feature_name', feature_name) \
                .execute()

            if result.data:
                logger.info(f"✅ Maintenance mode {'enabled' if is_maintenance else 'disabled'} for {feature_name}")
                return {
                    'success': True,
                    'message': f"Maintenance mode {'enabled' if is_maintenance else 'disabled'} successfully"
                }
            else:
                return {
                    'success': False,
                    'error': 'Failed to update maintenance status'
                }
        except Exception as e:
            logger.error(f"❌ Error setting maintenance status: {e}")
            return {'success': False, 'error': str(e)}

    def get_all_maintenance_settings(self) -> dict:
        """Get all maintenance settings"""
        try:
            if not self.supabase:
                self.supabase = get_supabase_client()
                
            if not self.supabase:
                return {'success': False, 'settings': []}

            result = self.supabase.table('maintenance_settings')\
                .select('*')\
                .execute()

            return {
                'success': True,
                'settings': result.data or []
            }
        except Exception as e:
            logger.error(f"❌ Error getting all maintenance settings: {e}")
            return {'success': False, 'settings': []}

# Global instance
maintenance_service = MaintenanceService()

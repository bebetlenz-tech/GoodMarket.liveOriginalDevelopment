import os
import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Optional
from supabase_client import get_supabase_client

logger = logging.getLogger(__name__)

class FacebookTaskService:
    def __init__(self):
        self.supabase = get_supabase_client()
        self.task_reward = 100.0  # 100 G$ reward
        self.cooldown_hours = 24  # 24 hour cooldown

        # Custom messages for Facebook posts
        self.custom_messages = self._generate_custom_messages()

        logger.info("📘 Facebook Task Service initialized")
        logger.info(f"💰 Reward: {self.task_reward} G$")
        logger.info(f"⏰ Cooldown: {self.cooldown_hours} hours")
        logger.info(f"💬 Custom Messages: {len(self.custom_messages)} unique variations")

    def _generate_custom_messages(self):
        """Generate 1000 unique custom messages for Facebook (10 sentences each)"""
        import random
        messages = []
        
        opening_phrases = [
            "GoodMarket is more than tasks — it’s your gateway to learning, earning, and contributing to the GoodDollar ecosystem.",
            "Join the financial revolution with GoodMarket! It's your personal gateway to the GoodDollar ecosystem.",
            "Unlock the potential of Web3 with GoodMarket, your bridge to the GoodDollar universal basic income.",
            "Experience a new way to earn and learn! GoodMarket is the premier hub for the GoodDollar community.",
            "Step into the future of finance! GoodMarket connects you directly to the GoodDollar ecosystem.",
            "Empower yourself with GoodMarket! Start your journey of earning and contributing to GoodDollar today.",
            "GoodMarket: Where education meets rewards in the thriving GoodDollar ecosystem.",
            "Ready to earn? GoodMarket is your official gateway to the GoodDollar universal basic income mission.",
            "Discover a world of opportunities! GoodMarket is the ultimate portal for GoodDollar enthusiasts.",
            "Join thousands earning G$ daily! GoodMarket is your essential gateway to the GoodDollar ecosystem."
        ]

        middle_phrases = [
            "Visit goodmarket.live today and discover daily tasks, learning opportunities, and ways to earn G$ 💙",
            "Head over to https://goodmarket.live right now to explore exciting tasks and start your G$ earning journey.",
            "Check out https://goodmarket.live and find a wealth of daily opportunities to support the GoodDollar mission.",
            "Go to https://goodmarket.live and start completing simple tasks to earn real G$ rewards every single day.",
            "Access https://goodmarket.live and dive into a variety of ways to contribute and earn within our community.",
            "Your journey starts at https://goodmarket.live – discover interactive quizzes and tasks that reward you in G$.",
            "Visit https://goodmarket.live to find out how easy it is to earn G$ while learning about financial inclusion.",
            "Explore https://goodmarket.live today and join the movement for a more equitable global financial system.",
            "Start your daily earning routine at https://goodmarket.live with our fun and educational task modules.",
            "Navigate to https://goodmarket.live and unlock multiple pathways to earn G$ and support universal basic income."
        ]

        closing_phrases = [
            "New to GoodDollar? Start your journey today 👇\n👉 Create your GoodWallet here: https://goodwallet.xyz/",
            "Ready to join? Set up your wallet and start earning 👇\n👉 Get your GoodWallet: https://goodwallet.xyz/",
            "Begin your crypto journey now! Everything you need is right here 👇\n👉 Sign up for GoodWallet: https://goodwallet.xyz/",
            "Don't wait to start earning! Join the GoodDollar family today 👇\n👉 Create your GoodWallet: https://goodwallet.xyz/",
            "Take the first step towards financial freedom! Get started here 👇\n👉 Secure your GoodWallet: https://goodwallet.xyz/",
            "Your future in crypto starts today! Join the revolution 👇\n👉 Launch your GoodWallet: https://goodwallet.xyz/",
            "Start receiving your universal basic income now! 👇\n👉 Register for GoodWallet: https://goodwallet.xyz/",
            "Empower your financial future with GoodDollar! 👇\n👉 Get started with GoodWallet: https://goodwallet.xyz/",
            "Joining is fast and simple! Start your journey here 👇\n👉 Claim your GoodWallet: https://goodwallet.xyz/",
            "Be part of a global community! Your journey begins now 👇\n👉 Set up your GoodWallet: https://goodwallet.xyz/"
        ]

        filler_sentences = [
            "Every contribution you make helps strengthen the global universal basic income network.",
            "Financial inclusion is a right, not a privilege, and we're building it together.",
            "Learning about blockchain has never been this rewarding or this accessible for everyone.",
            "Join a community of thousands dedicated to creating a fairer financial world for all.",
            "Your daily G$ claim is just the beginning of what you can achieve in this ecosystem.",
            "Interactive quizzes make it fun to learn while you grow your digital asset portfolio.",
            "We are proud to support the mission of making crypto useful for real people everywhere.",
            "The GoodDollar revolution is powered by users like you who believe in financial equity.",
            "Stay active and keep earning as we expand the possibilities of decentralized finance.",
            "Thank you for being a vital part of the most inclusive crypto project on the planet."
        ]

        for i in range(1000):
            # Pick sentences based on index to ensure variety
            s1 = opening_phrases[i % len(opening_phrases)]
            s2 = middle_phrases[(i // 10) % len(middle_phrases)]
            
            # Select 6 filler sentences to make it 10 sentences total (Opening + Middle + 6 fillers + 2 sentences in closing)
            fillers = []
            for j in range(6):
                fillers.append(filler_sentences[(i + j * 13) % len(filler_sentences)])
            
            closing = closing_phrases[(i // 100) % len(closing_phrases)]
            
            # Combine all parts with proper spacing
            msg = f"🌟 {s1}\n\n{s2}\n\n" + "\n\n".join(fillers) + f"\n\n{closing}"
            messages.append(msg)
        
        return messages

    def get_custom_message_for_user(self, wallet_address: str) -> str:
        """Get custom message for the user - wallet-based rotation"""
        import hashlib
        from datetime import timezone
        
        # Normalize wallet address to lowercase
        wallet_normalized = wallet_address.lower().strip()
        
        # Hash wallet address to get consistent index
        wallet_hash = int(hashlib.sha256(wallet_normalized.encode()).hexdigest(), 16)
        
        # Get current UTC time for rotation
        now_utc = datetime.now(timezone.utc)
        day_of_year = now_utc.timetuple().tm_yday
        hour_of_day = now_utc.hour
        
        # Use multiple factors for better distribution
        last_4_chars = int(wallet_normalized[-4:], 16) if len(wallet_normalized) >= 4 else 0
        
        # Combine all factors for unique message index
        message_index = (
            wallet_hash + 
            (day_of_year * 37) +  # Prime number multiplier
            (hour_of_day * 17) +   # Prime number multiplier
            (last_4_chars * 7)     # Prime number multiplier
        ) % len(self.custom_messages)

        return self.custom_messages[message_index]

    def _validate_facebook_url(self, facebook_url: str) -> Dict[str, Any]:
        """Validate Facebook post URL"""
        try:
            facebook_url = facebook_url.strip()

            if not facebook_url:
                return {"valid": False, "error": "Facebook post URL is required"}

            # Accept various Facebook URL formats
            valid_prefixes = [
                "https://www.facebook.com/",
                "https://facebook.com/",
                "https://m.facebook.com/",
                "https://fb.com/"
            ]

            if not any(facebook_url.startswith(prefix) for prefix in valid_prefixes):
                return {"valid": False, "error": "Please provide a valid Facebook post URL"}

            # Check if it's a post (contains /posts/ or /permalink/ or story_fbid or /share/)
            post_indicators = ["/posts/", "/permalink/", "story_fbid=", "/photo", "/video", "/share/"]
            if not any(indicator in facebook_url for indicator in post_indicators):
                return {"valid": False, "error": "URL must be a direct link to your Facebook post"}

            # Basic validation passed - admin will verify manually
            logger.info(f"✅ Facebook URL format validated: {facebook_url[:50]}...")

            return {"valid": True, "facebook_url": facebook_url}

        except Exception as e:
            logger.error(f"❌ Facebook URL validation error: {e}")
            return {"valid": False, "error": "Validation failed. Please try again."}

    async def check_eligibility(self, wallet_address: str) -> Dict[str, Any]:
        """Check if user can claim Facebook task reward"""
        try:
            if not self.supabase:
                return {'can_claim': True, 'reason': 'Database not available'}

            # Check for pending submission
            pending_check = self.supabase.table('facebook_task_log')\
                .select('created_at, status')\
                .eq('wallet_address', wallet_address)\
                .eq('status', 'pending')\
                .order('created_at', desc=True)\
                .limit(1)\
                .execute()

            if pending_check.data:
                pending_time = datetime.fromisoformat(pending_check.data[0]['created_at'].replace('Z', '+00:00'))
                next_claim_time = pending_time + timedelta(hours=self.cooldown_hours)

                return {
                    'can_claim': False,
                    'has_pending_submission': True,
                    'reason': 'Waiting for admin approval',
                    'status': 'pending',
                    'next_claim_time': next_claim_time.isoformat()
                }

            # Check last completed claim
            cutoff_time = datetime.now(timezone.utc) - timedelta(hours=self.cooldown_hours)
            last_claim = self.supabase.table('facebook_task_log')\
                .select('created_at, status')\
                .eq('wallet_address', wallet_address)\
                .in_('status', ['completed', 'rejected'])\
                .gte('created_at', cutoff_time.isoformat())\
                .order('created_at', desc=True)\
                .limit(1)\
                .execute()

            if last_claim.data:
                last_status = last_claim.data[0]['status']

                if last_status == 'rejected':
                    return {'can_claim': True, 'reward_amount': self.task_reward}

                if last_status == 'completed':
                    last_claim_time = datetime.fromisoformat(last_claim.data[0]['created_at'].replace('Z', '+00:00'))
                    next_claim_time = last_claim_time + timedelta(hours=self.cooldown_hours)

                    return {
                        'can_claim': False,
                        'reason': 'Already claimed today',
                        'next_claim_time': next_claim_time.isoformat()
                    }

            return {'can_claim': True, 'reward_amount': self.task_reward}

        except Exception as e:
            logger.error(f"❌ Error checking eligibility: {e}")
            return {'can_claim': True, 'reason': 'Error checking eligibility'}

    async def claim_task_reward(self, wallet_address: str, facebook_url: str) -> Dict[str, Any]:
        """Submit Facebook task for admin approval"""
        try:
            # Validate URL
            validation = self._validate_facebook_url(facebook_url)
            if not validation.get('valid'):
                return {'success': False, 'error': validation.get('error')}

            # Check eligibility
            eligibility = await self.check_eligibility(wallet_address)
            if not eligibility.get('can_claim'):
                return {'success': False, 'error': eligibility.get('reason', 'Cannot claim at this time')}

            # Check for duplicate URL
            if self.supabase:
                url_check = self.supabase.table('facebook_task_log')\
                    .select('wallet_address, status')\
                    .eq('facebook_url', facebook_url)\
                    .execute()

                if url_check.data:
                    previous_wallet = url_check.data[0].get('wallet_address')
                    if previous_wallet == wallet_address:
                        return {'success': False, 'error': 'You already submitted this post'}
                    else:
                        return {'success': False, 'error': 'This post has already been used by another user'}

            # Submit for admin approval
            if self.supabase:
                self.supabase.table('facebook_task_log').insert({
                    'wallet_address': wallet_address,
                    'facebook_url': facebook_url,
                    'reward_amount': self.task_reward,
                    'status': 'pending',
                    'transaction_hash': None,
                    'created_at': datetime.now(timezone.utc).isoformat()
                }).execute()

                return {
                    'success': True,
                    'pending': True,
                    'message': '✅ Submission successful! Your post is waiting for admin approval.',
                    'status': 'pending_approval'
                }

            return {'success': False, 'error': 'Database not available'}

        except Exception as e:
            logger.error(f"❌ Submission error: {e}")
            return {'success': False, 'error': str(e)}

    async def approve_submission(self, submission_id: int, admin_wallet: str) -> Dict[str, Any]:
        """Admin approves a submission and disburses reward"""
        try:
            if not self.supabase:
                return {'success': False, 'error': 'Database not available'}

            submission = self.supabase.table('facebook_task_log')\
                .select('*')\
                .eq('id', submission_id)\
                .eq('status', 'pending')\
                .execute()

            if not submission.data:
                return {'success': False, 'error': 'Submission not found'}

            wallet_address = submission.data[0]['wallet_address']

            # Disburse reward
            from facebook_task.blockchain import facebook_blockchain_service

            disbursement = facebook_blockchain_service.disburse_facebook_reward_sync(
                wallet_address=wallet_address,
                amount=self.task_reward
            )

            if disbursement.get('success'):
                self.supabase.table('facebook_task_log').update({
                    'status': 'completed',
                    'transaction_hash': disbursement.get('tx_hash'),
                    'approved_by': admin_wallet,
                    'approved_at': datetime.now(timezone.utc).isoformat()
                }).eq('id', submission_id).execute()

                return {
                    'success': True,
                    'tx_hash': disbursement.get('tx_hash'),
                    'message': f'Approved! {self.task_reward} G$ disbursed to user.'
                }
            else:
                self.supabase.table('facebook_task_log').update({
                    'status': 'failed',
                    'error_message': disbursement.get('error')
                }).eq('id', submission_id).execute()

                return {'success': False, 'error': disbursement.get('error')}

        except Exception as e:
            logger.error(f"❌ Approval error: {e}")
            return {'success': False, 'error': str(e)}

    async def reject_submission(self, submission_id: int, admin_wallet: str, reason: str = '') -> Dict[str, Any]:
        """Admin rejects a submission"""
        try:
            if not self.supabase:
                return {'success': False, 'error': 'Database not available'}

            self.supabase.table('facebook_task_log').update({
                'status': 'rejected',
                'rejected_by': admin_wallet,
                'rejected_at': datetime.now(timezone.utc).isoformat(),
                'rejection_reason': reason
            }).eq('id', submission_id).eq('status', 'pending').execute()

            return {
                'success': True,
                'message': 'Submission rejected. User can resubmit immediately.'
            }

        except Exception as e:
            logger.error(f"❌ Rejection error: {e}")
            return {'success': False, 'error': str(e)}

    def get_transaction_history(self, wallet_address: str, limit: int = 50) -> Dict[str, Any]:
        """Get user's Facebook task transaction history"""
        try:
            if not self.supabase:
                return {'success': True, 'transactions': [], 'total_count': 0}

            history = self.supabase.table('facebook_task_log')\
                .select('*')\
                .eq('wallet_address', wallet_address)\
                .order('created_at', desc=True)\
                .limit(limit)\
                .execute()

            transactions = []
            total_earned = 0

            if history.data:
                for record in history.data:
                    reward = float(record.get('reward_amount', 0))
                    total_earned += reward

                    transactions.append({
                        'id': record.get('id'),
                        'reward_amount': reward,
                        'transaction_hash': record.get('transaction_hash'),
                        'facebook_url': record.get('facebook_url'),
                        'status': record.get('status'),
                        'created_at': record.get('created_at'),
                        'explorer_url': f"https://explorer.celo.org/mainnet/tx/{record.get('transaction_hash')}" if record.get('transaction_hash') else None,
                        'rejection_reason': record.get('rejection_reason')
                    })

            return {
                'success': True,
                'transactions': transactions,
                'total_count': len(transactions),
                'total_earned': total_earned
            }

        except Exception as e:
            logger.error(f"❌ History error: {e}")
            return {'success': False, 'transactions': [], 'total_count': 0}

# Global instance
facebook_task_service = FacebookTaskService()

def init_facebook_task(app):
    """Initialize Facebook Task system with Flask app"""
    try:
        logger.info("📘 Initializing Facebook Task system...")
        from flask import session, request, jsonify

        @app.route('/api/facebook-task/status', methods=['GET'])
        def get_facebook_task_status():
            wallet_address = session.get('wallet_address') or session.get('wallet')
            if not wallet_address or not session.get('verified'):
                return jsonify({'error': 'Not authenticated'}), 401

            import asyncio
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                eligibility = loop.run_until_complete(
                    facebook_task_service.check_eligibility(wallet_address)
                )
            finally:
                loop.close()

            return jsonify(eligibility), 200

        @app.route('/api/facebook-task/custom-message', methods=['GET'])
        def get_facebook_custom_message():
            wallet_address = session.get('wallet_address') or session.get('wallet')
            if not wallet_address or not session.get('verified'):
                return jsonify({'error': 'Not authenticated'}), 401

            custom_message = facebook_task_service.get_custom_message_for_user(wallet_address)
            return jsonify({'success': True, 'custom_message': custom_message})

        @app.route('/api/facebook-task/claim', methods=['POST'])
        def claim_facebook_task():
            wallet_address = session.get('wallet_address') or session.get('wallet')
            if not wallet_address or not session.get('verified'):
                return jsonify({'error': 'Not authenticated'}), 401

            data = request.get_json()
            facebook_url = data.get('facebook_url', '').strip()

            if not facebook_url:
                return jsonify({'success': False, 'error': 'Facebook post URL is required'}), 400

            import asyncio
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                result = loop.run_until_complete(
                    facebook_task_service.claim_task_reward(wallet_address, facebook_url)
                )
            finally:
                loop.close()

            if result.get('success'):
                return jsonify(result), 200
            else:
                return jsonify(result), 400

        @app.route('/api/facebook-task/history', methods=['GET'])
        def get_facebook_task_history():
            wallet_address = session.get('wallet_address') or session.get('wallet')
            if not wallet_address or not session.get('verified'):
                return jsonify({'error': 'Not authenticated'}), 401

            limit = int(request.args.get('limit', 50))
            history = facebook_task_service.get_transaction_history(wallet_address, limit)

            return jsonify(history), 200

        logger.info("✅ Facebook Task system initialized successfully")
        return True

    except Exception as e:
        logger.error(f"❌ Failed to initialize Facebook Task: {e}")
        return False

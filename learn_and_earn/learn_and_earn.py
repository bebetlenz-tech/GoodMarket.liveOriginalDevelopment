import os
import json
import logging
import asyncio
from datetime import datetime, timedelta
from functools import wraps
from flask import Blueprint, request, jsonify, render_template, session
from .blockchain import learn_blockchain_service
# Contract integration removed - using direct private key disbursement only
from supabase_client import get_supabase_client
import random
from typing import Dict, Any

logger = logging.getLogger(__name__)

# Create Learn & Earn Blueprint
learn_earn_bp = Blueprint('learn_earn', __name__, url_prefix='/learn-earn')

class LearnEarnQuizManager:
    def __init__(self):
        self.questions_per_quiz = 10
        self.time_per_question = 20
        self.max_reward_per_quiz = 2000
        self.max_retries = 3
        self.cooldown_hours = 120

        self.load_quiz_settings()

    @property
    def reward_per_correct(self):
        return self.max_reward_per_quiz / self.questions_per_quiz

    def load_quiz_settings(self):
        try:
            supabase = get_supabase_client()
            if not supabase:
                logger.warning("⚠️ Supabase not available - using default quiz settings")
                return

            result = supabase.table('quiz_settings').select('*').limit(1).execute()

            if result.data and len(result.data) > 0:
                settings = result.data[0]
                self.questions_per_quiz = settings.get('questions_per_quiz', 10)
                self.time_per_question = settings.get('time_per_question', 20)
                self.max_reward_per_quiz = settings.get('max_reward_per_quiz', 2000)
                logger.info(f"✅ Loaded quiz settings: {self.questions_per_quiz} questions, {self.time_per_question}s per question, {self.max_reward_per_quiz} G$ max reward")
            else:
                # Create default settings if none exist
                default_settings = {
                    'questions_per_quiz': 10,
                    'time_per_question': 20,
                    'max_reward_per_quiz': 2000
                }
                supabase.table('quiz_settings').insert(default_settings).execute()
                logger.info("✅ Created default quiz settings in database")
        except Exception as e:
            logger.error(f"❌ Error loading quiz settings: {e}")

    def get_quiz_settings(self):
        return {
            'questions_per_quiz': self.questions_per_quiz,
            'time_per_question': self.time_per_question,
            'max_reward_per_quiz': self.max_reward_per_quiz,
            'reward_per_correct': self.reward_per_correct
        }

    def update_quiz_settings(self, questions_per_quiz=None, time_per_question=None, max_reward_per_quiz=None):
        try:
            supabase = get_supabase_client()
            if not supabase:
                return {'success': False, 'error': 'Database not available'}

            update_data = {}
            if questions_per_quiz is not None:
                update_data['questions_per_quiz'] = questions_per_quiz
                self.questions_per_quiz = questions_per_quiz
            if time_per_question is not None:
                update_data['time_per_question'] = time_per_question
                self.time_per_question = time_per_question
            if max_reward_per_quiz is not None:
                update_data['max_reward_per_quiz'] = max_reward_per_quiz
                self.max_reward_per_quiz = max_reward_per_quiz

            if not update_data:
                return {'success': False, 'error': 'No settings to update'}

            # Update or insert settings
            result = supabase.table('quiz_settings').select('*').limit(1).execute()

            if result.data and len(result.data) > 0:
                # Update existing settings
                supabase.table('quiz_settings').update(update_data).eq('id', result.data[0]['id']).execute()
            else:
                # Insert new settings
                supabase.table('quiz_settings').insert(update_data).execute()

            logger.info(f"✅ Updated quiz settings: {update_data}")
            return {'success': True, 'settings': self.get_quiz_settings()}
        except Exception as e:
            logger.error(f"❌ Error updating quiz settings: {e}")
            return {'success': False, 'error': str(e)}

    async def initialize_sample_questions(self):
        try:
            supabase = get_supabase_client()

            if supabase is None:
                logger.warning("⚠️ Supabase not configured - skipping question initialization")
                return

            # Check if questions exist
            existing_result = supabase.table('quiz_questions').select('*').limit(1).execute()

            if len(existing_result.data) > 0:
                logger.info("📚 Learn questions already exist in Supabase")
                return

            # Create sample questions (removed category and difficulty columns)
            sample_questions = [
                {
                    'question_id': 'Q001',
                    'question': 'What is GoodDollar (G$)?',
                    'answer_a': 'A cryptocurrency for universal basic income',
                    'answer_b': 'A regular bank currency',
                    'answer_c': 'A credit card company',
                    'answer_d': 'A shopping website',
                    'correct': 'A',
                    'created_at': datetime.utcnow().isoformat() + 'Z'  # Use UTC with Z suffix
                },
                {
                    'question_id': 'Q002',
                    'question': 'How often can you claim UBI with GoodDollar?',
                    'answer_a': 'Once per month',
                    'answer_b': 'Daily',
                    'answer_c': 'Once per year',
                    'answer_d': 'Only once',
                    'correct': 'B',
                    'created_at': datetime.utcnow().isoformat() + 'Z'  # Use UTC with Z suffix
                },
                {
                    'question_id': 'Q003',
                    'question': 'What blockchain network does GoodDollar use?',
                    'answer_a': 'Bitcoin',
                    'answer_b': 'Ethereum',
                    'answer_c': 'Celo',
                    'answer_d': 'Binance Smart Chain',
                    'correct': 'C',
                    'created_at': datetime.utcnow().isoformat() + 'Z'  # Use UTC with Z suffix
                },
                {
                    'question_id': 'Q004',
                    'question': 'What is the main goal of GoodDollar?',
                    'answer_a': 'Make money for investors',
                    'answer_b': 'Provide universal basic income',
                    'answer_c': 'Replace all banks',
                    'answer_d': 'Create a gaming platform',
                    'correct': 'B',
                    'created_at': datetime.utcnow().isoformat() + 'Z'  # Use UTC with Z suffix
                },
                {
                    'question_id': 'Q005',
                    'question': 'Where can you claim your GoodDollar UBI?',
                    'answer_a': 'goodmarket.com',
                    'answer_b': 'goodwallet.xyz',
                    'answer_c': 'facebook.com',
                    'answer_d': 'google.com',
                    'correct': 'B',
                    'created_at': datetime.utcnow().isoformat() + 'Z'  # Use UTC with Z suffix
                },
                {
                    'question_id': 'Q006',
                    'question': 'What happens if you don\'t claim UBI for 7+ days?',
                    'answer_a': 'Nothing changes',
                    'answer_b': 'You lose access to Learn & Earn rewards',
                    'answer_c': 'Your wallet gets deleted',
                    'answer_d': 'You get bonus rewards',
                    'correct': 'B',
                    'created_at': datetime.utcnow().isoformat() + 'Z'  # Use UTC with Z suffix
                },
                {
                    'question_id': 'Q007',
                    'question': 'How many G$ do you earn per correct answer in Learn & Earn?',
                    'answer_a': '100 G$',
                    'answer_b': '200 G$',
                    'answer_c': '300 G$',
                    'answer_d': '500 G$',
                    'correct': 'B',
                    'created_at': datetime.utcnow().isoformat() + 'Z'  # Use UTC with Z suffix
                },
                {
                    'question_id': 'Q008',
                    'question': 'What is the Celo network chain ID?',
                    'answer_a': '1',
                    'answer_b': '56',
                    'answer_c': '42220',
                    'answer_d': '137',
                    'correct': 'C',
                    'created_at': datetime.utcnow().isoformat() + 'Z'  # Use UTC with Z suffix
                },
                {
                    'question_id': 'Q009',
                    'question': 'How many questions are in each Learn & Earn quiz?',
                    'answer_a': '5 questions',
                    'answer_b': '10 questions',
                    'answer_c': '15 questions',
                    'answer_d': '20 questions',
                    'correct': 'B',
                    'created_at': datetime.utcnow().isoformat() + 'Z'  # Use UTC with Z suffix
                },
                {
                    'question_id': 'Q010',
                    'question': 'How long do you have to answer each question?',
                    'answer_a': '10 seconds',
                    'answer_b': '20 seconds',
                    'answer_c': '30 seconds',
                    'answer_d': '1 minute',
                    'correct': 'B',
                    'created_at': datetime.utcnow().isoformat() + 'Z'  # Use UTC with Z suffix
                },
                {
                    'question_id': 'Q011',
                    'question': 'What is financial inclusion?',
                    'answer_a': 'Only rich people can use money',
                    'answer_b': 'Everyone has access to financial services',
                    'answer_c': 'Banks control all money',
                    'answer_d': 'Cryptocurrency is illegal',
                    'correct': 'B',
                    'created_at': datetime.utcnow().isoformat() + 'Z'  # Use UTC with Z suffix
                },
                {
                    'question_id': 'Q012',
                    'question': 'What makes GoodDollar different from Bitcoin?',
                    'answer_a': 'GoodDollar is for universal basic income',
                    'answer_b': 'Bitcoin is faster',
                    'answer_c': 'GoodDollar uses more energy',
                    'answer_d': 'Bitcoin is free',
                    'correct': 'A',
                    'created_at': datetime.utcnow().isoformat() + 'Z'  # Use UTC with Z suffix
                }
            ]

            # Save questions to Supabase one by one to handle any individual failures
            for question in sample_questions:
                try:
                    result = supabase.table('quiz_questions').insert(question).execute()
                    logger.info(f"✅ Added question {question['question_id']}")
                except Exception as e:
                    logger.error(f"❌ Failed to add question {question['question_id']}: {e}")

            logger.info(f"✅ Initialized {len(sample_questions)} sample questions in Supabase")

        except Exception as e:
            logger.error(f"❌ Error initializing sample questions: {e}")

    async def get_random_questions(self, count=10):
        try:
            supabase = get_supabase_client()

            if supabase is None:
                logger.warning("⚠️ Supabase not configured - returning empty questions")
                return []

            # Get all questions
            result = supabase.table('quiz_questions').select('*').execute()
            all_questions = result.data

            if len(all_questions) < count:
                logger.warning(f"⚠️ Not enough questions in database: {len(all_questions)} < {count}")
                # Initialize questions if none exist
                if len(all_questions) == 0:
                    await self.initialize_sample_questions()
                    # Retry getting questions
                    result = supabase.table('quiz_questions').select('*').execute()
                    all_questions = result.data
                selected_questions = all_questions
            else:
                # Randomly select questions
                selected_questions = random.sample(all_questions, count)

            # Format questions for quiz
            quiz_questions = []
            for i, question in enumerate(selected_questions):
                quiz_questions.append({
                    'question_number': i + 1,
                    'question_id': question['question_id'],
                    'question': question['question'],
                    'options': [question['answer_a'], question['answer_b'], question['answer_c'], question['answer_d']],
                    'correct_answer': ord(question['correct']) - ord('A'),  # Convert A,B,C,D to 0,1,2,3
                    'category': 'general',  # Default category since column doesn't exist
                    'difficulty': 'medium'  # Default difficulty since column doesn't exist
                })

            logger.info(f"📚 Selected {len(quiz_questions)} questions for quiz")
            return quiz_questions

        except Exception as e:
            logger.error(f"❌ Error getting random questions: {e}")
            return []

    def mask_wallet_address(self, wallet_address: str) -> str:
        if not wallet_address.startswith("0x") or len(wallet_address) < 10:
            return wallet_address
        return wallet_address[:6] + "..." + wallet_address[-4:]

    async def get_next_quiz_time(self, wallet_address: str) -> Dict[str, Any]:
        """Get the timestamp of the last quiz attempt for a user"""
        try:
            supabase = get_supabase_client()
            masked_address = self.mask_wallet_address(wallet_address)

            # Fetch the most recent quiz attempt for the user
            result = supabase.table('learnearn_log')\
                .select('timestamp')\
                .eq('wallet_address', masked_address)\
                .order('timestamp', desc=True)\
                .limit(1)\
                .execute()

            if result.data:
                last_attempt_str = result.data[0]['timestamp']

                # Handle timezone-aware datetime from Supabase - ensure UTC parsing
                try:
                    # Parse as UTC datetime consistently
                    if last_attempt_str.endswith('Z'):
                        # Already UTC with Z suffix - parse directly
                        last_attempt_time = datetime.fromisoformat(last_attempt_str.replace('Z', '+00:00')).replace(tzinfo=None)
                    elif '+' in last_attempt_str or '-' in last_attempt_str[-6:]:
                        # Has timezone offset - convert to UTC
                        dt_with_tz = datetime.fromisoformat(last_attempt_str)
                        last_attempt_time = dt_with_tz.utctimetuple()
                        last_attempt_time = datetime(*last_attempt_time[:6])  # Convert to naive UTC
                    else:
                        # Assume naive UTC datetime from Supabase
                        last_attempt_time = datetime.fromisoformat(last_attempt_str)
                except Exception as parse_error:
                    logger.error(f"❌ Error parsing UTC timestamp in next quiz time check: {parse_error}")
                    logger.error(f"Original timestamp: {last_attempt_str}")
                    # If parsing fails, assume user can take quiz
                    return {
                        'next_quiz_time': None,
                        'can_take_now': True
                    }

                # Use the configured cooldown hours (120 hours = 5 days)
                next_quiz_time = last_attempt_time + timedelta(hours=self.cooldown_hours)
                current_utc_time = datetime.utcnow() # Use UTC time
                can_take_now = current_utc_time >= next_quiz_time

                logger.info(f"🕐 Next quiz time check for {masked_address} (UTC):")
                logger.info(f"📅 Last attempt: {last_attempt_time}")
                logger.info(f"📅 Next quiz time: {next_quiz_time}")
                logger.info(f"📅 Current time: {current_utc_time}")
                logger.info(f"⏰ Cooldown: {self.cooldown_hours} hours")
                logger.info(f"✅ Can take now: {can_take_now}")

                return {
                    'next_quiz_time': next_quiz_time.isoformat(),
                    'can_take_now': can_take_now
                }
            else:
                # No previous attempts, user can take quiz immediately
                return {
                    'next_quiz_time': None,
                    'can_take_now': True
                }
        except Exception as e:
            logger.error(f"❌ Error getting next quiz time for {wallet_address}: {e}")
            # Assume user can take quiz if error occurs during retrieval
            return {
                'next_quiz_time': None,
                'can_take_now': True
            }

    async def save_quiz_attempt(self, user_wallet, questions, user_answers, total_reward, ubi_verification, retry_count=0):
        """Save quiz attempt to Supabase with retry logic - ONLY when reward is successfully sent"""
        try:
            supabase = get_supabase_client()
            quiz_id = f"QUIZ_{user_wallet.lower()}_{datetime.utcnow().isoformat()}"

            # Calculate results
            correct_answers = 0
            answer_details = []

            for i, question in enumerate(questions):
                user_answer = user_answers[i]
                is_correct = user_answer == question['correct_answer']
                if is_correct:
                    correct_answers += 1

                answer_details.append({
                    'question_number': i + 1,
                    'question_id': question['question_id'],
                    'question': question['question'],
                    'user_answer': user_answer,
                    'correct_answer': question['correct_answer'],
                    'is_correct': is_correct,
                    'category': question.get('category', 'general')
                })

            # Create quiz log entry with timezone-naive timestamp
            current_time = datetime.utcnow()
            quiz_log = {
                'quiz_id': quiz_id,
                'wallet_address': self.mask_wallet_address(user_wallet),
                'timestamp': current_time.isoformat() + 'Z',  # Use UTC with Z suffix
                'score': correct_answers,
                'total_questions': len(questions),
                'amount_g$': total_reward,
                'status': True,
                'answers': json.dumps(answer_details),  # Store as JSON string
                'ubi_verification': json.dumps(ubi_verification),
                'blocked': ubi_verification.get('blocked', False)
            }

            # Save to Supabase
            result = supabase.table('learnearn_log').insert(quiz_log).execute()

            logger.info(f"✅ Quiz attempt saved: {quiz_id} - Score: {correct_answers}/{len(questions)} - Timestamp: {current_time.isoformat()}")
            return quiz_log

        except Exception as e:
            logger.error(f"❌ Error saving quiz attempt (attempt {retry_count + 1}): {e}")

            # Retry logic
            if retry_count < self.max_retries:
                logger.info(f"🔄 Retrying quiz save... ({retry_count + 1}/{self.max_retries})")
                await asyncio.sleep(2 ** retry_count)
                return await self.save_quiz_attempt(user_wallet, questions, user_answers, total_reward, ubi_verification, retry_count + 1)
            else:
                logger.error(f"❌ Quiz save failed after {retry_count + 1} attempts")
                return None

    def check_user_eligibility(self, wallet_address: str) -> bool:
        """Check user eligibility based on last quiz attempt timestamp.
           Returns True if eligible, False otherwise."""
        try:
            supabase = get_supabase_client()
            masked_address = self.mask_wallet_address(wallet_address)

            # Fetch the most recent quiz attempt for the user
            result = supabase.table('learnearn_log')\
                .select('timestamp')\
                .eq('wallet_address', masked_address)\
                .order('timestamp', desc=True)\
                .limit(1)\
                .execute()

            if result.data:
                last_attempt_str = result.data[0]['timestamp']

                # Handle timezone-aware datetime from Supabase - ensure UTC parsing
                try:
                    # Parse as UTC datetime consistently
                    if last_attempt_str.endswith('Z'):
                        # Already UTC with Z suffix - parse directly
                        last_attempt_time = datetime.fromisoformat(last_attempt_str.replace('Z', '+00:00')).replace(tzinfo=None)
                    elif '+' in last_attempt_str or '-' in last_attempt_str[-6:]:
                        # Has timezone offset - convert to UTC
                        dt_with_tz = datetime.fromisoformat(last_attempt_str)
                        last_attempt_time = dt_with_tz.utctimetuple()
                        last_attempt_time = datetime(*last_attempt_time[:6])  # Convert to naive UTC
                    else:
                        # Assume naive UTC datetime from Supabase
                        last_attempt_time = datetime.fromisoformat(last_attempt_str)
                except Exception as parse_error:
                    logger.error(f"❌ Error parsing UTC timestamp in eligibility check: {parse_error}")
                    logger.error(f"Original timestamp: {last_attempt_str}")
                    # If parsing fails, assume user can take quiz
                    return True

                # Calculate using UTC time consistently
                next_quiz_time = last_attempt_time + timedelta(hours=self.cooldown_hours)
                current_utc_time = datetime.utcnow()
                can_take_now = current_utc_time >= next_quiz_time

                if can_take_now:
                    logger.info(f"✅ User {masked_address} is eligible for quiz (UTC check).")
                else:
                    logger.warning(f"⚠️ User {masked_address} is not eligible for quiz. UTC cooldown active until {next_quiz_time}")

                logger.info(f"🕐 UTC Eligibility Check - Last: {last_attempt_time}, Next: {next_quiz_time}, Current: {current_utc_time}")

                return can_take_now
            else:
                # No previous attempts, user can take quiz immediately
                logger.info(f"✅ User {masked_address} is eligible for quiz (first time).")
                return True

        except Exception as e:
            logger.error(f"❌ Failed to check eligibility for {wallet_address}: {e}")
            # Default to eligible if there's an error during checking
            return True

    async def check_quiz_eligibility(self, wallet_address: str) -> Dict[str, Any]:
        """Check if user is eligible for Learn & Earn quiz (24-hour cooldown only)"""
        try:
            # Check maintenance mode first
            try:
                from maintenance_service import maintenance_service
                maintenance_status = maintenance_service.get_maintenance_status('learn_earn')

                if maintenance_status.get('is_maintenance'):
                    logger.info(f"⚠️ Learn & Earn is under maintenance")
                    return {
                        'eligible': False,
                        'blocked': True,
                        'reason': 'maintenance_mode',
                        'message': maintenance_status.get('message', 'Learn & Earn is currently under maintenance. Please try again later.'),
                        'can_take_now': False,
                        'feature_available': False,
                        'maintenance': True
                    }
            except Exception as maint_error:
                logger.warning(f"⚠️ Maintenance check failed: {maint_error}")
                # Continue with eligibility check even if maintenance check fails

            # Check using sync method like hour_bonus
            try:
                eligible = self.check_user_eligibility(wallet_address)
            except Exception as elig_error:
                logger.error(f"❌ Eligibility check error: {elig_error}")
                # Default to eligible if check fails
                eligible = True

            # Get next quiz time for consistent data
            try:
                next_quiz_info = await self.get_next_quiz_time(wallet_address)
                can_take_now = next_quiz_info.get('can_take_now', eligible)
            except Exception as time_error:
                logger.error(f"❌ Next quiz time check error: {time_error}")
                # Default to using eligibility result
                next_quiz_info = {'can_take_now': eligible, 'next_quiz_time': None}
                can_take_now = eligible

            if not eligible or not can_take_now:
                return {
                    'eligible': False,
                    'blocked': True,
                    'reason': '5-day cooldown active',
                    'message': 'You have already completed a quiz in the last 5 days. Please wait before taking another quiz.',
                    'next_quiz_time': next_quiz_info.get('next_quiz_time'),
                    'can_take_now': False,
                    'cooldown_hours': 120,
                    'feature_available': True  # Feature is available, just on cooldown
                }

            # User is eligible and can take quiz now
            logger.info(f"✅ User {wallet_address} is eligible for Learn & Earn quiz")
            return {
                'eligible': True,
                'blocked': False,
                'reason': 'No recent quiz completion found',
                'message': f'You can take the quiz and earn up to {quiz_manager.questions_per_quiz * quiz_manager.reward_per_correct} G$!',
                'max_reward': quiz_manager.questions_per_quiz * quiz_manager.reward_per_correct,
                'can_take_now': True,
                'cooldown_hours': 120,
                'feature_available': True
            }

        except Exception as e:
            logger.error(f"❌ Error checking Learn & Earn quiz eligibility: {e}")
            import traceback
            logger.error(f"❌ Traceback: {traceback.format_exc()}")
            return {
                'eligible': True,  # Default to eligible if check fails
                'blocked': False,
                'reason': 'Eligibility check bypassed due to error',
                'message': f'Learn & Earn available - you can take the quiz and earn up to {quiz_manager.questions_per_quiz * quiz_manager.reward_per_correct} G$!',
                'feature_available': True,
                'max_reward': quiz_manager.questions_per_quiz * quiz_manager.reward_per_correct,
                'can_take_now': True,
                'cooldown_hours': 120,
                'error': str(e)  # Include error for debugging
            }

    def get_quiz_history(self, wallet_address, limit=500):
        """Get user's quiz history - OPTIMIZED single query with OR filter"""
        try:
            supabase = get_supabase_client()

            wallet_normalized = wallet_address.lower()
            masked_address = self.mask_wallet_address(wallet_address)

            logger.info(f"🔍 Optimized quiz history fetch for: {wallet_address[:10]}...")

            result = supabase.table('learnearn_log')\
                .select('*')\
                .or_(f"wallet_address.eq.{masked_address},wallet_address.eq.{wallet_normalized},wallet_address.eq.{wallet_address}")\
                .order('timestamp', desc=True)\
                .limit(limit)\
                .execute()

            seen_quiz_ids = set()
            unique_history = []

            for quiz in (result.data or []):
                quiz_id = quiz.get('quiz_id')
                if quiz_id and quiz_id not in seen_quiz_ids:
                    seen_quiz_ids.add(quiz_id)
                    # Add explorer_url for each quiz
                    quiz_with_url = quiz.copy()
                    if quiz.get('transaction_hash'):
                        quiz_with_url['explorer_url'] = f"https://celoscan.io/tx/{quiz['transaction_hash']}"
                    unique_history.append(quiz_with_url)

            logger.info(f"✅ Found {len(unique_history)} unique quiz history records")

            if unique_history:
                newest_date = unique_history[0].get('timestamp', 'Unknown')
                oldest_date = unique_history[-1].get('timestamp', 'Unknown')
                logger.info(f"📅 Date range: {newest_date} (newest) to {oldest_date} (oldest)")

                # Log summary by month
                from collections import defaultdict
                monthly_counts = defaultdict(int)
                for quiz in unique_history:
                    timestamp = quiz.get('timestamp', '')
                    if timestamp:
                        month = timestamp[:7]  # YYYY-MM
                        monthly_counts[month] += 1

                logger.info(f"📊 Quiz history by month:")
                for month in sorted(monthly_counts.keys()):
                    logger.info(f"   {month}: {monthly_counts[month]} quizzes")

            return unique_history

        except Exception as e:
            logger.error(f"❌ Failed to get quiz history: {e}")
            import traceback
            logger.error(f"🔍 Traceback: {traceback.format_exc()}")
            return []

    def create_quiz_session(self, user_wallet, questions):
        """Creates a new quiz session and stores it in database for production reliability."""
        import json
        session_id = f"QUIZ_SESSION_{user_wallet.lower()}_{random.randint(1000, 9999)}_{int(datetime.utcnow().timestamp())}"

        # Store session data in database for production reliability (works with multiple workers)
        try:
            from supabase_client import get_supabase_client, safe_supabase_operation
            supabase = get_supabase_client()
            
            if supabase:
                # Delete any old sessions for this user (cleanup)
                safe_supabase_operation(
                    lambda: supabase.table('quiz_sessions').delete().eq('wallet_address', user_wallet.lower()).execute(),
                    fallback_result=None,
                    operation_name="cleanup old quiz sessions"
                )
                
                # Insert new session
                session_data = {
                    'session_id': session_id,
                    'wallet_address': user_wallet.lower(),
                    'questions': json.dumps(questions),
                    'started_at': datetime.utcnow().isoformat() + 'Z',
                    'expires_at': (datetime.utcnow() + timedelta(hours=1)).isoformat() + 'Z'
                }
                
                result = safe_supabase_operation(
                    lambda: supabase.table('quiz_sessions').insert(session_data).execute(),
                    fallback_result=None,
                    operation_name="create quiz session in database"
                )
                
                if result:
                    logger.info(f"✅ Created quiz session in database: {session_id} for {user_wallet}")
                else:
                    logger.warning(f"⚠️ Failed to store session in database, using in-memory fallback")
                    # Fallback to in-memory
                    if not hasattr(self, '_quiz_sessions'):
                        self._quiz_sessions = {}
                    self._quiz_sessions[session_id] = {
                        'questions': questions,
                        'wallet': user_wallet,
                        'started_at': datetime.utcnow().isoformat() + 'Z'
                    }
            else:
                # Fallback to in-memory if no database
                if not hasattr(self, '_quiz_sessions'):
                    self._quiz_sessions = {}
                self._quiz_sessions[session_id] = {
                    'questions': questions,
                    'wallet': user_wallet,
                    'started_at': datetime.utcnow().isoformat() + 'Z'
                }
                logger.info(f"✅ Created quiz session in memory: {session_id} for {user_wallet}")
        except Exception as e:
            logger.error(f"❌ Error creating quiz session: {e}")
            # Fallback to in-memory
            if not hasattr(self, '_quiz_sessions'):
                self._quiz_sessions = {}
            self._quiz_sessions[session_id] = {
                'questions': questions,
                'wallet': user_wallet,
                'started_at': datetime.utcnow().isoformat() + 'Z'
            }

        return {'session_id': session_id}

    def validate_and_score_quiz(self, quiz_session_id, user_answers):
        """Validates quiz session, scores answers, and returns the result."""
        import json
        
        if not hasattr(self, '_quiz_sessions'):
            self._quiz_sessions = {}

        quiz_session_id = str(quiz_session_id)
        session_data = self._quiz_sessions.get(quiz_session_id)

        # If not in memory, try to get from database (production reliability)
        if not session_data:
            logger.info(f"🔍 Session not in memory, checking database for: {quiz_session_id}")
            try:
                from supabase_client import get_supabase_client, safe_supabase_operation
                supabase = get_supabase_client()
                
                if supabase:
                    result = safe_supabase_operation(
                        lambda: supabase.table('quiz_sessions').select('*').eq('session_id', quiz_session_id).execute(),
                        fallback_result=None,
                        operation_name="get quiz session from database"
                    )
                    
                    if result and result.data and len(result.data) > 0:
                        db_session = result.data[0]
                        session_data = {
                            'questions': json.loads(db_session['questions']),
                            'wallet': db_session['wallet_address'],
                            'started_at': db_session['started_at']
                        }
                        logger.info(f"✅ Retrieved session from database: {quiz_session_id}")
                        
                        # Clean up from database after retrieval
                        safe_supabase_operation(
                            lambda: supabase.table('quiz_sessions').delete().eq('session_id', quiz_session_id).execute(),
                            fallback_result=None,
                            operation_name="cleanup quiz session from database"
                        )
            except Exception as e:
                logger.error(f"❌ Error retrieving session from database: {e}")

        if not session_data:
            logger.error(f"❌ Session {quiz_session_id} not found in memory or database")
            return {'valid': False, 'message': 'Quiz session expired or not found. Please start a new quiz.'}

        stored_questions = session_data.get('questions')

        if not stored_questions:
            return {'valid': False, 'message': 'Quiz questions not found in session.'}

        if len(user_answers) != len(stored_questions):
            return {'valid': False, 'message': f'Incorrect number of answers submitted. Expected {len(stored_questions)}, received {len(user_answers)}.'}

        correct_answers = 0
        answer_details = []

        for i, question in enumerate(stored_questions):
            user_answer = user_answers[i]
            is_correct = user_answer == question['correct_answer']
            if is_correct:
                correct_answers += 1
            answer_details.append({
                'question_number': i + 1,
                'question_id': question['question_id'],
                'user_answer': user_answer,
                'correct_answer': question['correct_answer'],
                'is_correct': is_correct,
                'category': question.get('category', 'general')
            })

        score = correct_answers
        total_questions = len(stored_questions)
        raw_reward = correct_answers * self.reward_per_correct
        reward_amount = round(min(raw_reward, self.max_reward_per_quiz), 2)

        # Clean up session after scoring
        if quiz_session_id in self._quiz_sessions:
            del self._quiz_sessions[quiz_session_id]

        return {
            'valid': True,
            'score': score,
            'total_questions': total_questions,
            'correct_answers': correct_answers,
            'reward_amount': reward_amount,
            'answers_details': answer_details,
            'questions': stored_questions  # Include questions for further processing
        }

    def log_quiz_attempt(self, user_wallet, score, total_questions, reward_amount, quiz_session_id):
        """Logs a quiz attempt to Supabase."""
        try:
            supabase = get_supabase_client()
            log_id = f"LOG_{user_wallet.lower()}_{datetime.utcnow().isoformat()}"

            quiz_log_data = {
                'quiz_id': log_id,
                'wallet_address': self.mask_wallet_address(user_wallet),
                'timestamp': datetime.utcnow().isoformat() + 'Z', # Use UTC with Z suffix
                'score': score,
                'total_questions': total_questions,
                'amount_g$': reward_amount,
                'status': True, # Assuming successful logging for now, status updated on reward/failure
                'answers': json.dumps([]), # Placeholder, actual answers might be stored elsewhere or not needed for log
                'ubi_verification': json.dumps({}), # Placeholder
                'blocked': False, # Placeholder
                'session_id': quiz_session_id # Link to the session
            }

            result = supabase.table('learnearn_log').insert(quiz_log_data).execute()
            logger.info(f"✅ Quiz attempt logged: {log_id} for {user_wallet}")
            return {'success': True, 'log_id': log_id}

        except Exception as e:
            logger.error(f"❌ Error logging quiz attempt: {e}")
            return {'success': False, 'error': str(e)}

    def update_quiz_log_with_transaction(self, log_id, transaction_hash):
        """Updates the quiz log with transaction details."""
        try:
            supabase = get_supabase_client()
            update_result = supabase.table('learnearn_log')\
                .update({
                    'transaction_hash': transaction_hash,
                    'reward_status': 'sent',
                    'sent_at': datetime.utcnow().isoformat() + 'Z' # Use UTC with Z suffix
                })\
                .eq('quiz_id', log_id)\
                .execute()
            logger.info(f"✅ Updated quiz log {log_id} with transaction hash: {transaction_hash}")
            return True
        except Exception as e:
            logger.error(f"❌ Error updating quiz log {log_id} with transaction: {e}")
            return False

    def get_module_links(self):
        """Get active module links for Learn & Earn with automatic content scraping"""
        try:
            from supabase_client import get_supabase_client
            supabase = get_supabase_client()

            if not supabase:
                logger.error("❌ Supabase client not available for module links")
                return []

            # Get active module links
            result = supabase.table('learn_earn_module_links')\
                .select('id, title, url, description, content, reading_time_minutes, display_order')\
                .eq('is_active', True)\
                .order('display_order', desc=False)\
                .execute()

            if result.data and len(result.data) > 0:
                logger.info(f"✅ Retrieved {len(result.data)} module links")

                # Auto-scrape missing content
                for link in result.data:
                    has_content = bool(link.get('content') and link.get('content').strip())
                    has_url = bool(link.get('url') and link.get('url').strip())

                    # If no content but has URL, auto-scrape
                    if not has_content and has_url:
                        logger.info(f"🔍 Auto-scraping content for '{link.get('title')}' from {link.get('url')}")
                        try:
                            import requests
                            from bs4 import BeautifulSoup

                            # Fetch webpage
                            response = requests.get(link.get('url'), timeout=10, headers={
                                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                            })
                            response.raise_for_status()

                            # Parse HTML
                            soup = BeautifulSoup(response.content, 'html.parser')

                            # Remove unwanted elements
                            for element in soup(['script', 'style', 'nav', 'footer', 'header', 'aside']):
                                element.decompose()

                            # Extract main content
                            main_content = (
                                soup.find('article') or
                                soup.find('main') or
                                soup.find('div', class_='content') or
                                soup.find('div', class_='article') or
                                soup.find('body')
                            )

                            if main_content:
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

                                # Auto-calculate reading time
                                word_count = len(content.split())
                                reading_time = max(1, round(word_count / 200))

                                # Update database with scraped content
                                supabase.table('learn_earn_module_links')\
                                    .update({
                                        'content': content,
                                        'reading_time_minutes': reading_time
                                    })\
                                    .eq('id', link.get('id'))\
                                    .execute()

                                # Update in-memory link data
                                link['content'] = content
                                link['reading_time_minutes'] = reading_time

                                logger.info(f"✅ Auto-scraped {len(content)} chars, {word_count} words, ~{reading_time} min read")
                            else:
                                logger.warning(f"⚠️ Could not find main content in {link.get('url')}")

                        except Exception as scrape_error:
                            logger.error(f"❌ Auto-scrape failed for '{link.get('title')}': {scrape_error}")

                    # Log final status
                    has_content = bool(link.get('content') and link.get('content').strip())
                    logger.info(f"   Module '{link.get('title')}': has_content={has_content}, reading_time={link.get('reading_time_minutes')}min")

                return result.data
            else:
                logger.warning("⚠️ No active module links found in database")
                return []

        except Exception as e:
            logger.error(f"❌ Error getting module links: {e}")
            import traceback
            logger.error(f"❌ Traceback: {traceback.format_exc()}")
            return []

    def get_username_from_db(self, wallet_address: str):
        """Get username for wallet address from user_data table"""
        try:
            supabase = get_supabase_client()
            if not supabase:
                return None

            # Query user_data table for username
            result = supabase.table("user_data")\
                .select("username")\
                .eq("wallet_address", wallet_address)\
                .execute()

            if result.data and len(result.data) > 0:
                username = result.data[0].get("username")
                if username and username.strip():
                    logger.info(f"✅ Retrieved username from user_data: {username} for {wallet_address[:8]}...")
                    return username.strip()

            logger.info(f"ℹ️ No username found in user_data for {wallet_address[:8]}...")
            return None

        except Exception as e:
            logger.error(f"❌ Error getting username from user_data: {e}")
            return None

    def get_daily_ranking(self, wallet_address: str, quiz_date: str = None):
        """Get user's ranking for a specific date from database"""
        try:
            from datetime import datetime
            supabase = get_supabase_client()
            if not supabase:
                return {'position': 1, 'badge': '🎯 PARTICIPANT'}

            # Use provided date or today
            if not quiz_date:
                quiz_date = datetime.utcnow().strftime('%Y-%m-%d')

            # Query all quizzes for this date, ordered by timestamp (earliest first)
            start_datetime = f"{quiz_date}T00:00:00Z"
            end_datetime = f"{quiz_date}T23:59:59Z"

            logger.info(f"📊 Getting daily ranking for {wallet_address[:8]}... on {quiz_date}")

            result = supabase.table('learnearn_log')\
                .select('wallet_address, timestamp, quiz_id')\
                .gte('timestamp', start_datetime)\
                .lte('timestamp', end_datetime)\
                .eq('status', True)\
                .order('timestamp', desc=False)\
                .execute()

            if not result.data:
                # First participant of the day
                return {'position': 1, 'badge': '🥇 FIRST PLACE'}

            # Find user's position
            masked_address = self.mask_wallet_address(wallet_address)
            position = 0

            for idx, quiz in enumerate(result.data, start=1):
                if quiz['wallet_address'] == masked_address:
                    position = idx
                    break

            # If user not found, they will be next participant
            if position == 0:
                position = len(result.data) + 1

            # Determine badge
            if position == 1:
                badge = '🥇 FIRST PLACE'
            elif position == 2:
                badge = '🥈 SECOND PLACE'
            elif position == 3:
                badge = '🥉 THIRD PLACE'
            elif position <= 10:
                badge = f'⭐ TOP {position}'
            else:
                badge = f'🎯 RANK #{position}'

            logger.info(f"✅ User ranking: Position {position}, Badge: {badge}")

            return {'position': position, 'badge': badge}

        except Exception as e:
            logger.error(f"❌ Error getting daily ranking: {e}")
            return {'position': 1, 'badge': '🎯 PARTICIPANT'}


# Initialize Quiz Manager
quiz_manager = LearnEarnQuizManager()

def learn_earn_token_required(f):
    """Token validation for Learn & Earn endpoints"""
    @wraps(f)
    def decorated(*args, **kwargs):
        wallet_address = session.get('wallet')
        verified = session.get('verified')

        logger.info(f"🔐 Learn & Earn Auth Check: wallet={wallet_address is not None}, verified={verified}")

        if not wallet_address:
            logger.warning("❌ No wallet address in session")
            return jsonify({
                'success': False,
                'error': 'No wallet address found. Please log in again.',
                'auth_required': True
            }), 401

        if not verified:
            logger.warning("❌ User not verified")
            return jsonify({
                'success': False,
                'error': 'User not verified. Please complete UBI verification first.',
                'verification_required': True
            }), 401

        logger.info(f"✅ Authentication successful for {wallet_address}")
        return f(wallet_address, *args, **kwargs)
    return decorated

# Learn & Earn Routes

@learn_earn_bp.route('/')
def learn_earn_dashboard():
    """Learn & Earn main dashboard"""
    from flask import render_template, session, redirect, url_for

    # Check if user is authenticated
    if not session.get('verified') or not session.get('wallet'):
        return redirect(url_for('routes.index'))

    wallet = session.get('wallet')

    # Track page visit
    try:
        from analytics_service import analytics
        analytics.track_page_view(wallet, 'learn_earn')
    except Exception as e:
        logger.error(f"❌ Error tracking analytics: {e}")

    return render_template('learn_and_earn.html', wallet=wallet)

@learn_earn_bp.route('/start-quiz', methods=['POST'])
@learn_earn_token_required
def start_quiz(current_user):
    """Start a new Learn & Earn quiz"""
    try:
        logger.info(f"🎯 Starting quiz for user: {current_user}")

        # NOTE: Session clearing moved to AFTER validation passes
        # This prevents losing valid quiz session if validation fails

        # Check if reward system is configured (safe check without exposing private key)
        if not learn_blockchain_service.is_configured:
            logger.error(f"❌ Reward system not configured")
            return jsonify({
                'success': False,
                'error': 'Learn wallet not configured',
                'show_notification': True,
                'notification_type': 'wallet_not_configured',
                'notification_message': 'Contact GIMT team to remind them to refill the token rewards',
                'voice_message': 'Contact GIMT team to remind them to refill the token rewards',
                'feature_status': 'wallet_not_configured'
            }), 400

        # Check Learn wallet balance before allowing quiz
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            learn_balance = loop.run_until_complete(learn_blockchain_service.get_learn_wallet_balance())
        finally:
            loop.close()

        # Check if Learn wallet has sufficient balance (at least 2000 G$ for full quiz rewards)
        min_required_balance = quiz_manager.questions_per_quiz * quiz_manager.reward_per_correct
        # Use tolerance to avoid floating point precision issues (e.g., 1000.0 vs 1000.0000000000001)
        balance_tolerance = 0.01  # Allow 0.01 G$ tolerance
        if learn_balance < (min_required_balance - balance_tolerance):
            logger.warning(f"⚠️ Learn wallet balance too low: {learn_balance} < {min_required_balance}")

            # Get custom message from database
            from supabase_client import get_supabase_client, safe_supabase_operation
            supabase = get_supabase_client()
            custom_message = 'G$ funds have been depleted. Please try to contact us at t.me/GoodDollarX'

            if supabase:
                msg_result = safe_supabase_operation(
                    lambda: supabase.table('maintenance_settings')\
                        .select('custom_message')\
                        .eq('feature_name', 'learn_earn_insufficient_balance')\
                        .execute(),
                    fallback_result=type('obj', (object,), {'data': []})(),
                    operation_name="get insufficient balance custom message"
                )
                if msg_result.data and len(msg_result.data) > 0:
                    db_message = msg_result.data[0].get('custom_message')
                    if db_message:
                        custom_message = db_message

            return jsonify({
                'success': False,
                'error': custom_message,
                'show_notification': True,
                'notification_type': 'insufficient_balance',
                'notification_message': custom_message,
                'voice_message': 'G$ funds depleted. Contact us at t.me/GoodDollarX',
                'learn_balance': learn_balance,
                'required_balance': min_required_balance,
                'feature_status': 'insufficient_balance'
            }), 400

        # Check user eligibility using sync method like hour_bonus
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            eligibility_info = loop.run_until_complete(quiz_manager.check_quiz_eligibility(current_user))
        finally:
            loop.close()

        if eligibility_info.get('blocked'):
            return jsonify({
                'success': False,
                'blocked': True,
                'reason': eligibility_info.get('reason'),
                'message': eligibility_info.get('message'),
                'next_quiz_time': eligibility_info.get('next_quiz_time'),
                'can_take_now': eligibility_info.get('can_take_now', False),
                'feature_status': 'cooldown_active'
            }), 403

        # Get random questions using sync method like hour_bonus
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            questions = loop.run_until_complete(quiz_manager.get_random_questions(quiz_manager.questions_per_quiz))
        finally:
            loop.close()

        if not questions:
            return jsonify({
                'success': False,
                'error': 'No questions available. Please try again later.'
            }), 500

        # Get module links BEFORE creating quiz session
        module_links = quiz_manager.get_module_links()
        logger.info(f"📚 Retrieved {len(module_links)} module links for quiz session")

        # Filter out module links without content
        valid_module_links = []
        if module_links:
            for idx, link in enumerate(module_links):
                content = link.get('content')

                # Skip if content is None or empty
                if content is None or content == '':
                    logger.warning(f"   ⚠️ Module {idx + 1}: '{link.get('title')}' - content is NULL or empty in database (SKIPPED)")
                    continue

                # Convert to string and check if it has actual content
                content_str = str(content).strip()
                if not content_str:
                    logger.warning(f"   ⚠️ Module {idx + 1}: '{link.get('title')}' - content is whitespace only (SKIPPED)")
                    continue

                # Valid content found
                logger.info(f"   ✅ Module {idx + 1}: '{link.get('title')}' - valid content ({len(content_str)} chars, {link.get('reading_time_minutes', 5)} min reading time)")
                valid_module_links.append(link)

        logger.info(f"📚 {len(valid_module_links)} module links with valid content will be shown")

        # Clear any existing quiz session data ONLY after all validations pass
        # This prevents losing a valid quiz session if validation fails
        session.pop('quiz_questions', None)
        session.pop('quiz_session_id', None)
        session.pop('quiz_started_at', None)
        logger.info(f"🧹 Cleared previous quiz session data for {current_user}")

        # Create quiz session
        quiz_session = quiz_manager.create_quiz_session(current_user, questions)

        logger.info(f"📝 Created quiz session: {quiz_session['session_id']}")

        # Store questions in session for submit-quiz endpoint
        session['quiz_questions'] = questions
        session['quiz_session_id'] = quiz_session['session_id']
        session['quiz_started_at'] = datetime.utcnow().isoformat() + 'Z'

        # Make session permanent FIRST before setting data
        session.permanent = True
        session.modified = True  # Force session to save

        # Verify session data was stored correctly
        logger.info(f"✅ Session data stored - Questions: {len(session.get('quiz_questions', []))}, Session ID: {session.get('quiz_session_id')}")
        logger.info(f"🔒 Session permanent: {session.permanent}, Modified: {session.modified}")

        # Prepare quiz questions for response (remove correct answers)
        quiz_questions_for_response = []
        for q in questions:
            quiz_questions_for_response.append({
                'question_number': q['question_number'],
                'question_id': q['question_id'],
                'question': q['question'],
                'options': q['options'],
                'category': q.get('category'),
                'difficulty': q.get('difficulty')
            })

        return jsonify({
            'success': True,
            'quiz_session': {
                'session_id': quiz_session['session_id'],
                'started_at': session['quiz_started_at'],
                'questions': quiz_questions_for_response,
                'quiz_info': {
                    'total_questions': len(quiz_questions_for_response),
                    'time_per_question': quiz_manager.time_per_question,
                    'reward_per_correct': quiz_manager.reward_per_correct,
                    'max_reward': len(quiz_questions_for_response) * quiz_manager.reward_per_correct
                },
                'module_links': valid_module_links
            },
            'feature_status': 'available',
            'learn_balance': learn_balance
        }), 200

    except Exception as e:
        logger.error(f"❌ Error starting quiz for {current_user}: {e}")
        return jsonify({
            'success': False,
            'error': 'Failed to start quiz. Please try again.'
        }), 500

@learn_earn_bp.route('/submit-quiz', methods=['POST'])
@learn_earn_token_required
def submit_quiz(current_user):
    """Submit quiz answers and process rewards"""
    try:
        data = request.get_json()
        user_answers = data.get('answers', [])
        quiz_session_id = data.get('quiz_session_id')

        logger.info(f"📝 Quiz submission from {current_user} for session {quiz_session_id}")

        # First, try to retrieve from session
        stored_questions = session.get('quiz_questions')
        stored_session_id = session.get('quiz_session_id')

        logger.info(f"📋 Submit Quiz Debug - Current User: {current_user}")
        logger.info(f"📋 Session ID from request: {quiz_session_id}")
        logger.info(f"📋 Session ID from session: {stored_session_id}")
        logger.info(f"✅ Session has questions: {stored_questions is not None}")
        logger.info(f"✅ Session ID match: {stored_session_id == quiz_session_id}")
        logger.info(f"📊 Questions count: {len(stored_questions) if stored_questions else 0}")

        # If session data is missing, try to retrieve from quiz_manager's temporary storage
        if not stored_questions or str(stored_session_id) != str(quiz_session_id):
            logger.warning(f"⚠️ Session data missing or mismatch (Session: {stored_session_id}, Request: {quiz_session_id}), trying quiz_manager storage...")

            # Check if quiz_manager has the session
            quiz_session_id_str = str(quiz_session_id)
            if hasattr(quiz_manager, '_quiz_sessions') and quiz_session_id_str in quiz_manager._quiz_sessions:
                session_data = quiz_manager._quiz_sessions[quiz_session_id_str]
                stored_questions = session_data.get('questions')
                logger.info(f"✅ Retrieved questions from quiz_manager for session {quiz_session_id_str}")
            else:
                logger.error(f"❌ No questions found in session or quiz_manager for {current_user}")
                # Fallback: if session has questions and current_user matches, maybe it's just a session ID mismatch but valid session
                if stored_questions and session.get('wallet') == current_user:
                    logger.info(f"💡 Found questions in session for user {current_user}, proceeding despite ID mismatch")
                else:
                    return jsonify({
                        'success': False,
                        'message': 'Quiz session expired or not found. Please start a new quiz.',
                        'feature_status': 'session_expired',
                        'debug_info': {
                            'has_questions': False,
                            'session_id_match': str(stored_session_id) == str(quiz_session_id),
                            'wallet': current_user,
                            'session_id_provided': quiz_session_id,
                            'session_id_stored': stored_session_id
                        }
                    }), 400

        # Validate and score quiz
        quiz_result = quiz_manager.validate_and_score_quiz(quiz_session_id, user_answers)

        if not quiz_result.get('valid'):
            return jsonify({
                'success': False,
                'message': quiz_result.get('message', 'Invalid quiz submission')
            }), 400

        score = quiz_result['score']
        total_questions = quiz_result['total_questions']
        reward_amount = quiz_result['reward_amount']

        logger.info(f"📊 Quiz results: {score}/{total_questions} correct, {reward_amount} G$ earned")

        # Create feature status info for logging
        # Check eligibility for logging purposes, though submission is allowed regardless
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            eligibility_info_for_log = loop.run_until_complete(quiz_manager.check_quiz_eligibility(current_user))
        finally:
            loop.close()

        feature_info_for_log = {
            'feature_available': True,
            'access_granted': True,
            'blocked': eligibility_info_for_log.get('blocked', False),
            'feature_type': 'learn_and_earn',
            'submission_allowed': True # Submission is always allowed, reward is conditional
        }

        # Process rewards first - before saving quiz attempt to database
        transaction_hash = None
        disbursement_success = False
        is_fake_transaction = False
        insufficient_balance = False
        should_block_user = False
        quiz_log = None
        error_message = None

        # Check eligibility using sync method to avoid event loop issues
        eligible = quiz_manager.check_user_eligibility(current_user)

        if eligible and reward_amount > 0:
            # Prepare quiz result summary for reward disbursement
            quiz_result_summary = {
                'correct': quiz_result.get('correct_answers'),
                'total': total_questions,
                'score_percentage': round((score / total_questions) * 100, 1) if total_questions > 0 else 0
            }

            # Direct private key disbursement
            logger.info(f"💰 Processing direct reward disbursement for {current_user}")
            logger.info(f"💰 Reward amount: {reward_amount} G$")
            logger.info(f"📊 Quiz score: {score}/{total_questions} ({quiz_result_summary['score_percentage']}%)")

            # Check if reward system is configured before attempting disbursement
            if not learn_blockchain_service.is_configured:
                logger.error(f"❌ Reward system not configured - cannot disburse rewards")
                error_message = "Learn & Earn wallet not configured. Please contact the GIMT team to set up the reward system."
                transaction_hash = None
                disbursement_success = False
                is_fake_transaction = False
                should_block_user = False
                insufficient_balance = False
            else:
                # Check Learn wallet balance before attempting disbursement
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    learn_balance = loop.run_until_complete(learn_blockchain_service.get_learn_wallet_balance())

                    if learn_balance < reward_amount:
                        logger.error(f"❌ Learn wallet insufficient balance: {learn_balance} G$ < {reward_amount} G$")
                        error_message = "Learn & Earn rewards are temporarily unavailable due to high demand. The reward wallet is being refilled by the GIMT Team. Please try again later."
                        transaction_hash = None
                        disbursement_success = False
                        is_fake_transaction = False
                        should_block_user = False
                        insufficient_balance = True
                    else:
                        # Attempt reward disbursement
                        reward_result = loop.run_until_complete(
                            learn_blockchain_service.send_g_reward(current_user, reward_amount, quiz_result_summary)
                        )

                        if reward_result.get('success'):
                            transaction_hash = reward_result.get('tx_hash')
                            disbursement_success = True
                            is_fake_transaction = reward_result.get('fake_transaction', False)
                            should_block_user = True

                            logger.info(f"✅ Direct reward disbursement successful: {transaction_hash}")
                            logger.info(f"🔗 Block: {reward_result.get('block_number')}")
                            logger.info(f"⛽ Gas used: {reward_result.get('gas_used')}")
                        else:
                            # Reward disbursement failed
                            error_message = reward_result.get('error', 'Unknown blockchain error')
                            logger.error(f"❌ Reward disbursement failed: {error_message}")
                            logger.error(f"💳 Wallet: {current_user}")
                            logger.error(f"💰 Amount: {reward_amount} G$")

                            transaction_hash = None
                            disbursement_success = False
                            is_fake_transaction = False
                            should_block_user = False
                            insufficient_balance = 'insufficient balance' in error_message.lower() or reward_result.get('insufficient_balance', False)
                finally:
                    loop.close()

        # Only save quiz attempt to database if reward was actually sent OR if user wasn't eligible
        if should_block_user or not eligible:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                quiz_log = loop.run_until_complete(quiz_manager.save_quiz_attempt(
                    current_user,
                    stored_questions, # Pass the actual questions object from session
                    user_answers,
                    reward_amount,
                    feature_info_for_log
                ))
            finally:
                loop.close()

            if not quiz_log and should_block_user:
                logger.error(f"❌ Failed to save quiz attempt but reward was sent - this may cause sync issues")

            # Update quiz log with transaction details if reward was sent
            if quiz_log and transaction_hash and disbursement_success:
                try:
                    supabase = get_supabase_client()
                    supabase.table('learnearn_log')\
                        .update({
                            'transaction_hash': transaction_hash,
                            'reward_status': 'sent',
                            'sent_at': datetime.utcnow().isoformat() + 'Z' # Use UTC with Z suffix
                        })\
                        .eq('quiz_id', quiz_log['quiz_id'])\
                        .execute()
                    logger.info(f"✅ Quiz log updated with transaction hash: {transaction_hash}")
                except Exception as update_error:
                    logger.error(f"❌ Failed to update quiz log with transaction: {update_error}")
        else:
            logger.info(f"📝 Quiz completed but not saved to database - reward failed and user remains eligible for retry")

        # Clear quiz session
        session.pop('quiz_questions', None)
        session.pop('quiz_session_id', None)
        session.pop('quiz_started_at', None)

        # Determine message and notification based on transaction result
        if disbursement_success and not is_fake_transaction:
            message = f'Quiz completed! You earned {reward_amount} G$ successfully'
            notification_data = {
                'show_notification': True,
                'notification_type': 'success',
                'notification_message': message
            }
        elif insufficient_balance:
            message = 'Learn & Earn rewards are temporarily unavailable due to high demand. The reward wallet is being refilled by the GIMT Team. Please try again later.'
            notification_data = {
                'show_notification': True,
                'notification_type': 'insufficient_balance',
                'notification_message': message,
                'voice_message': 'Learn & Earn rewards temporarily unavailable due to high demand. Please try again later.',
                'high_demand': True
            }
        elif not should_block_user and reward_amount > 0 and error_message:
            message = f'Quiz completed but reward processing failed: {error_message}. You can try again immediately.'
            notification_data = {
                'show_notification': True,
                'notification_type': 'retry_available',
                'notification_message': message,
                'can_retry_immediately': True,
                'error_details': error_message
            }
        elif not should_block_user and reward_amount > 0:
            message = 'Quiz completed but reward processing failed - you can try again immediately'
            notification_data = {
                'show_notification': True,
                'notification_type': 'retry_available',
                'notification_message': 'Quiz completed but reward processing failed. You can take the quiz again immediately.',
                'can_retry_immediately': True
            }
        else:
            message = 'Quiz completed successfully'
            notification_data = {
                'show_notification': True,
                'notification_type': 'success',
                'notification_message': message
            }

        logger.info(f"📊 Quiz completed - showing results without ranking/username complexity")

        # Add processing notification to response
        response_data = {
            'success': True,
            'score': score,
            'total_questions': total_questions,
            'rewards': reward_amount,
            'transaction_hash': transaction_hash,
            'disbursement_success': disbursement_success,
            'is_fake_transaction': is_fake_transaction,
            'insufficient_balance': insufficient_balance,
            'message': message,
            'feature_status': 'completed_successfully' if disbursement_success else 'completed_pending_reward',
            'blocked_for_24h': should_block_user,  # Only block if reward was actually sent
            'can_retry_immediately': not should_block_user,  # Allow immediate retry if reward failed
            **notification_data  # Include notification data
        }

        # Include processing notification if reward processing occurred
        if eligible and reward_amount > 0:
            response_data['processing_notification'] = {
                'show_processing': True,
                'processing_message': 'The GIMT team are processing your request, please wait a few seconds...',
                'processing_type': 'reward_disbursement'
            }

        return jsonify(response_data), 200

    except Exception as e:
        logger.error(f"❌ Error submitting quiz for {current_user}: {e}")
        # Clear session on error to prevent retries with stale data
        session.pop('quiz_questions', None)
        session.pop('quiz_session_id', None)
        session.pop('quiz_started_at', None)
        return jsonify({
            'success': False,
            'error': 'Failed to submit quiz. Please try again.'
        }), 500

@learn_earn_bp.route('/get-daily-ranking', methods=['GET'])
@learn_earn_token_required
def get_daily_ranking(current_user):
    """Get user's ranking for a specific date"""
    try:
        from datetime import datetime
        from flask import request

        quiz_date = request.args.get('date', datetime.utcnow().strftime('%Y-%m-%d'))

        # Get all quizzes for this date, ordered by timestamp (earliest first)
        supabase = get_supabase_client()
        if not supabase:
            return jsonify({'success': False, 'error': 'Database not available'}), 500

        # Get all participants for this date
        start_datetime = f"{quiz_date}T00:00:00Z"
        end_datetime = f"{quiz_date}T23:59:59Z"

        result = supabase.table('learnearn_log')\
            .select('wallet_address, timestamp, quiz_id, score, total_questions')\
            .gte('timestamp', start_datetime)\
            .lte('timestamp', end_datetime)\
            .eq('status', True)\
            .order('timestamp', desc=False)\
            .execute()

        if not result.data:
            # First participant of the day
            return jsonify({
                'success': True,
                'rank': 1,
                'badge': '🥇 FIRST PLACE',
                'total_participants': 1,
                'date': quiz_date,
                'is_first': True
            })

        # Find user's rank (based on who took quiz first)
        masked_address = quiz_manager.mask_wallet_address(current_user)
        user_rank = 0

        # Check if user already has a quiz today
        for idx, quiz in enumerate(result.data, start=1):
            if quiz['wallet_address'] == masked_address:
                user_rank = idx
                break

        # If user not found in results, they will be the next participant
        if user_rank == 0:
            user_rank = len(result.data) + 1

        # Determine badge
        badge = ''
        if user_rank == 1:
            badge = '🥇 FIRST PLACE'
        elif user_rank == 2:
            badge = '🥈 SECOND PLACE'
        elif user_rank == 3:
            badge = '🥉 THIRD PLACE'
        elif user_rank <= 10:
            badge = f'⭐ TOP {user_rank}'
        else:
            badge = f'🎯 RANK #{user_rank}'

        return jsonify({
            'success': True,
            'rank': user_rank,
            'badge': badge,
            'total_participants': len(result.data) if user_rank <= len(result.data) else user_rank,
            'date': quiz_date
        })

    except Exception as e:
        logger.error(f"❌ Error getting daily ranking: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@learn_earn_bp.route('/eligibility', methods=['GET'])
@learn_earn_token_required
def check_eligibility(current_user):
    """Check user eligibility for Learn & Earn quiz"""
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            eligibility_info = loop.run_until_complete(quiz_manager.check_quiz_eligibility(current_user))
        except Exception as async_error:
            logger.error(f"❌ Async eligibility check error: {async_error}")
            # Return a safe default response
            eligibility_info = {
                'eligible': True,
                'blocked': False,
                'reason': 'Check bypassed due to error',
                'message': 'Quiz is available - you can take it now!',
                'can_take_now': True,
                'feature_available': True,
                'error': str(async_error)
            }
        finally:
            loop.close()

        return jsonify({
            'success': True,
            'eligible': eligibility_info.get('eligible', False),
            'blocked': eligibility_info.get('blocked', False),
            'reason': eligibility_info.get('reason'),
            'message': eligibility_info.get('message'),
            'next_quiz_time': eligibility_info.get('next_quiz_time'),
            'can_take_now': eligibility_info.get('can_take_now', False),
            'ubi_verification': eligibility_info # Contains all info, including cooldown details
        }), 200

    except Exception as e:
        logger.error(f"❌ Error checking eligibility for {current_user}: {e}")
        import traceback
        logger.error(f"❌ Traceback: {traceback.format_exc()}")
        # Return a safe fallback response instead of 500 error
        return jsonify({
            'success': True,
            'eligible': True,
            'blocked': False,
            'reason': 'Check bypassed due to error',
            'message': 'Quiz is available - you can take it now!',
            'can_take_now': True,
            'error': str(e)
        }), 200

@learn_earn_bp.route('/sell-achievement-card', methods=['POST'])
@learn_earn_token_required
def sell_achievement_card(current_user):
    """Sell achievement card for G$ based on quiz score"""
    try:
        data = request.get_json()
        quiz_id = data.get('quiz_id')
        score = int(data.get('score', 0))
        total_questions = int(data.get('total_questions', 10))
        original_reward = float(data.get('original_reward', 0))
        sell_price = int(data.get('sell_price', 0))
        quiz_timestamp = data.get('quiz_timestamp')

        logger.info(f"💰 Achievement card sale request from {current_user}")
        logger.info(f"📊 Quiz ID: {quiz_id}, Score: {score}/{total_questions}, Sell Price: {sell_price} G$")

        # Check if selling is available (starts May 10, 2026)
        from datetime import datetime
        selling_start_date = datetime(2026, 5, 10, 0, 0, 0)
        current_date = datetime.utcnow()

        if current_date < selling_start_date:
            days_until_available = (selling_start_date - current_date).days
            logger.warning(f"⚠️ Achievement card selling not yet available. Available on: {selling_start_date.strftime('%B %d, %Y')}")
            return jsonify({
                'success': False,
                'error': 'Achievement card selling will be available on May 10, 2026',
                'selling_available': False,
                'available_date': selling_start_date.strftime('%B %d, %Y'),
                'days_until_available': days_until_available
            }), 403

        # Validate sell price calculation
        expected_price = round((score / total_questions) * 1000)
        if sell_price != expected_price:
            logger.error(f"❌ Invalid sell price: {sell_price} != {expected_price}")
            return jsonify({
                'success': False,
                'error': 'Invalid sell price calculation'
            }), 400

        supabase = get_supabase_client()
        if not supabase:
            return jsonify({
                'success': False,
                'error': 'Database not available'
            }), 500

        # Check if THIS SPECIFIC card was already sold (by quiz_id)
        existing_sale = supabase.table('achievement_card_sales')\
            .select('*')\
            .eq('wallet_address', current_user)\
            .eq('quiz_id', quiz_id)\
            .execute()

        if existing_sale.data and len(existing_sale.data) > 0:
            logger.warning(f"⚠️ User {current_user[:8]}... already sold this specific card (Quiz ID: {quiz_id})")
            return jsonify({
                'success': False,
                'error': 'This achievement card has already been sold!'
            }), 400

        # Process blockchain disbursement
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            disbursement_result = loop.run_until_complete(
                learn_blockchain_service.send_g_reward(
                    current_user,
                    sell_price,
                    {'action': 'sell_achievement_card', 'quiz_id': quiz_id, 'score': score, 'total': total_questions}
                )
            )
        finally:
            loop.close()

        if not disbursement_result.get('success'):
            logger.error(f"❌ Card sale disbursement failed: {disbursement_result.get('error')}")
            return jsonify({
                'success': False,
                'error': disbursement_result.get('error', 'Failed to process card sale')
            }), 500

        # Log card sale to database with quiz_id
        card_sale_data = {
            'wallet_address': current_user,
            'quiz_id': quiz_id,
            'quiz_timestamp': quiz_timestamp,
            'score': score,
            'total_questions': total_questions,
            'original_reward': original_reward,
            'sell_price': sell_price,
            'transaction_hash': disbursement_result.get('tx_hash'),
            'created_at': datetime.utcnow().isoformat() + 'Z'
        }

        supabase.table('achievement_card_sales').insert(card_sale_data).execute()

        logger.info(f"✅ Achievement card sold successfully!")
        logger.info(f"💰 User received: {sell_price} G$")
        logger.info(f"📜 TX: {disbursement_result.get('tx_hash')}")

        # Create notification for the sale
        try:
            from notifications_service import notification_service
            notification_service.create_achievement_sale_notification(
                wallet_address=current_user,
                score=score,
                total_questions=total_questions,
                sell_price=sell_price,
                transaction_hash=disbursement_result.get('tx_hash')
            )
            logger.info(f"✅ Created achievement sale notification for {current_user[:8]}...")
        except Exception as notif_error:
            logger.error(f"⚠️ Failed to create notification: {notif_error}")

        return jsonify({
            'success': True,
            'message': f'Achievement card sold for {sell_price} G$!',
            'sell_price': sell_price,
            'transaction_hash': disbursement_result.get('tx_hash'),
            'explorer_url': f"https://celoscan.io/tx/{disbursement_result.get('tx_hash')}"
        }), 200

    except Exception as e:
        logger.error(f"❌ Error selling achievement card: {e}")
        import traceback
        logger.error(f"🔍 Traceback: {traceback.format_exc()}")
        return jsonify({
            'success': False,
            'error': f'Failed to sell achievement card: {str(e)}'
        }), 500

@learn_earn_bp.route('/quiz-history', methods=['GET'])
@learn_earn_token_required
def get_quiz_history_endpoint(current_user):
    """Get user's quiz history"""
    try:
        limit = int(request.args.get('limit', 500))
        quiz_history = quiz_manager.get_quiz_history(current_user, limit)

        # Calculate total earned
        total_earned = sum(quiz.get('amount_g$', 0) for quiz in quiz_history)

        return jsonify({
            'success': True,
            'quiz_history': quiz_history,
            'total_earned': total_earned,
            'quiz_count': len(quiz_history)
        })
    except Exception as e:
        logger.error(f"❌ Error getting quiz history: {e}")
        return jsonify({
            'success': False,
            'error': str(e),
            'quiz_history': [],
            'total_earned': 0,
            'quiz_count': 0
        }), 500

@learn_earn_bp.route('/check-card-sold', methods=['POST'])
@learn_earn_token_required
def check_card_sold(current_user):
    """Check if an achievement card was already sold"""
    try:
        data = request.get_json()
        quiz_id = data.get('quiz_id')
        score = data.get('score')
        total_questions = data.get('total_questions')
        timestamp = data.get('timestamp')

        supabase = get_supabase_client()
        if not supabase:
            return jsonify({'success': False, 'error': 'Database not available'}), 500

        # Check if selling is available (starts May 10, 2026)
        from datetime import datetime
        selling_start_date = datetime(2026, 5, 10, 0, 0, 0)
        current_date = datetime.utcnow()
        selling_available = current_date >= selling_start_date
        days_until_available = (selling_start_date - current_date).days if not selling_available else 0

        # Check if this specific card was sold using quiz_id
        result = supabase.table('achievement_card_sales')\
            .select('*')\
            .eq('wallet_address', current_user)\
            .eq('quiz_id', quiz_id)\
            .order('created_at', desc=True)\
            .limit(1)\
            .execute()

        if result.data and len(result.data) > 0:
            sale = result.data[0]
            return jsonify({
                'success': True,
                'already_sold': True,
                'sell_price': sale.get('sell_price'),
                'transaction_hash': sale.get('transaction_hash'),
                'sold_at': sale.get('created_at'),
                'selling_available': selling_available,
                'available_date': selling_start_date.strftime('%B %d, %Y'),
                'days_until_available': days_until_available
            })
        else:
            return jsonify({
                'success': True,
                'already_sold': False,
                'selling_available': selling_available,
                'available_date': selling_start_date.strftime('%B %d, %Y'),
                'days_until_available': days_until_available
            })

    except Exception as e:
        logger.error(f"❌ Error checking card sold status: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@learn_earn_bp.route('/stats', methods=['GET'])
@learn_earn_token_required
def get_learn_earn_stats(current_user):
    """Get Learn & Earn system stats"""
    try:
        # Get Learn wallet balance
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            learn_balance = loop.run_until_complete(learn_blockchain_service.get_learn_wallet_balance())
            eligibility_info = loop.run_until_complete(quiz_manager.check_quiz_eligibility(current_user))
        finally:
            loop.close()

        # Get total questions available
        supabase = get_supabase_client()
        questions_result = supabase.table('quiz_questions').select('*').execute()
        total_questions = len(questions_result.data)

        # Smart contract integration will be added here
        contract_info = {'error': 'Contract integration disabled - using direct disbursement'}
        user_contract_stats = {}

        return jsonify({
            'success': True,
            'system_stats': {
                'learn_wallet_balance': learn_balance,
                'total_questions_available': total_questions,
                'questions_per_quiz': quiz_manager.questions_per_quiz,
                'reward_per_correct': quiz_manager.reward_per_correct,
                'max_reward_per_quiz': quiz_manager.questions_per_quiz * quiz_manager.reward_per_correct
            },
            'contract_info': contract_info,
            'user_contract_stats': user_contract_stats,
            'user_status': {
                'wallet_address': current_user,
                'can_take_quiz': eligibility_info.get('eligible', False),
                'ubi_verification': eligibility_info, # Consistent naming
                'eligible': eligibility_info.get('eligible', False)
            }
        }), 200

    except Exception as e:
        logger.error(f"❌ Error getting stats for {current_user}: {e}")
        return jsonify({
            'success': False,
            'error': 'Failed to get stats'
        }), 500

@learn_earn_bp.route('/contract-info', methods=['GET'])
def get_contract_info():
    """Get smart contract information"""
    try:
        # Smart contract integration will be added here
        contract_info = {
            'error': 'Contract integration disabled - using direct private key disbursement',
            'disbursement_method': 'direct_private_key'
        }

        return jsonify({
            'success': True,
            'contract_deployed': False,
            'contract_info': contract_info
        }), 200

    except Exception as e:
        logger.error(f"❌ Error getting contract info: {e}")
        return jsonify({
            'success': False,
            'error': 'Failed to get contract info'
        }), 500

@learn_earn_bp.route('/deposit-tokens', methods=['POST'])
@learn_earn_token_required
def deposit_tokens(current_user):
    """Deposit tokens to contract (admin only for now)"""
    try:
        # Smart contract integration will be added here
        return jsonify({
            'success': False,
            'error': 'Contract deposit not available - using direct private key disbursement',
            'disbursement_method': 'direct_private_key'
        }), 400

    except Exception as e:
        logger.error(f"❌ Error depositing tokens: {e}")
        return jsonify({
            'success': False,
            'error': 'Failed to deposit tokens'
        }), 500

def init_learn_and_earn(app):
    """Initialize Learn & Earn module with Flask app"""
    try:
        logger.info("🎓 Initializing Learn & Earn module...")

        # Register Blueprint
        app.register_blueprint(learn_earn_bp)

        # Initialize sample questions synchronously like hour_bonus
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(quiz_manager.initialize_sample_questions())
            loop.close()
            logger.info("✅ Learn & Earn questions initialized")
        except Exception as init_error:
            logger.error(f"❌ Error initializing questions: {init_error}")

        logger.info("✅ Learn & Earn module initialized successfully")
        logger.info("📚 Available endpoints:")
        logger.info("   GET  /learn-earn/ - Dashboard")
        logger.info("   GET  /learn-earn/eligibility - Check user eligibility")
        logger.info("   POST /learn-earn/start-quiz - Start new quiz")
        logger.info("   POST /learn-earn/submit-quiz - Submit quiz answers")
        logger.info("   GET  /learn-earn/quiz-history - Get quiz history")
        logger.info("   GET  /learn-earn/stats - Get system stats")

        return True

    except Exception as e:
        logger.error(f"❌ Failed to initialize Learn & Earn module: {e}")
        return False

# Legacy functions for backward compatibility
def get_random_questions(count=10):
    """Legacy function for backward compatibility - now calls async method"""
    # This needs to run in an async context or manage its own loop.
    # For simplicity in a legacy context, we might assume it's called where an event loop is available.
    # If not, a new loop would need to be created and managed, which can be problematic.
    # A better approach would be to refactor calls to use the async version.
    # For now, let's assume a loop is available or create one if necessary.
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError: # No running loop
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    try:
        return loop.run_until_complete(quiz_manager.get_random_questions(count))
    finally:
        # Avoid closing the loop if it was already running
        if loop.is_running():
            pass
        else:
            loop.close()

def calculate_score(user_answers):
    """Legacy function for backward compatibility - uses session data"""
    try:
        from flask import session
        questions = session.get('quiz_questions', [])
        if not questions:
            # If session data is missing, we cannot calculate score.
            # Consider logging an error or returning a specific error indicator.
            logger.error("Legacy calculate_score called without active quiz session.")
            return 0, 0

        correct_count = 0
        for i, user_answer in enumerate(user_answers):
            # Ensure we don't go out of bounds if user_answers is shorter/longer than expected
            if i < len(questions) and user_answer == questions[i].get('correct_answer'):
                correct_count += 1

        total_rewards = correct_count * quiz_manager.reward_per_correct
        return correct_count, total_rewards
    except RuntimeError:
        # Working outside of request context
        logger.error("Legacy calculate_score called outside Flask request context.")
        return 0, 0

def check_user_eligibility(wallet_address):
    """Legacy function for backward compatibility - now calls sync method"""
    try:
        # Use the sync method from quiz_manager instance
        return quiz_manager.check_user_eligibility(wallet_address)
    except Exception as e:
        logger.error(f"Error in legacy check_user_eligibility: {e}")
        return True # Default to True on error

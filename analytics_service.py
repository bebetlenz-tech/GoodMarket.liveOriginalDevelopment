import logging
import json
from supabase_client import supabase_logger
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

class AnalyticsService:
    def __init__(self):
        self.user_sessions = {}
        self.verification_attempts = {}
        self.dashboard_metrics = {
            "total_users": 0,
            "successful_verifications": 0,
            "failed_verifications": 0,
            "active_sessions": 0
        }
        self.supabase_logger = supabase_logger
        self._cache = {}
        self._cache_times = {}

    def track_verification_attempt(self, wallet_address: str, success: bool):
        """Track verification attempts for analytics"""
        if wallet_address not in self.verification_attempts:
            self.verification_attempts[wallet_address] = {
                "attempts": 0,
                "successes": 0,
                "last_attempt": None
            }

        self.verification_attempts[wallet_address]["attempts"] += 1
        if success:
            self.verification_attempts[wallet_address]["successes"] += 1
            self.dashboard_metrics["successful_verifications"] += 1
        else:
            self.dashboard_metrics["failed_verifications"] += 1

        self.verification_attempts[wallet_address]["last_attempt"] = self._get_timestamp()

        # Log to Supabase using new structure (with null check)
        if self.supabase_logger:
            self.supabase_logger.log_verification_attempt(
                wallet_address,
                success,
                {"attempts": self.verification_attempts[wallet_address]["attempts"], "disbursement_method": "direct_private_key"}
            )

    def track_user_session(self, wallet_address: str):
        """Track active user sessions"""
        if wallet_address not in self.user_sessions:
            self.dashboard_metrics["total_users"] += 1

        session_data = {
            "login_time": self._get_timestamp(),
            "last_activity": self._get_timestamp(),
            "page_views": 1
        }

        self.user_sessions[wallet_address] = session_data
        self.dashboard_metrics["active_sessions"] += 1

        # Log to Supabase using new structure (with null check)
        if self.supabase_logger:
            self.supabase_logger.log_login(wallet_address, session_data)

    def track_page_view(self, wallet_address: str, page: str):
        """Track page views for user engagement"""
        if wallet_address in self.user_sessions:
            self.user_sessions[wallet_address]["last_activity"] = self._get_timestamp()
            self.user_sessions[wallet_address]["page_views"] += 1

            if "pages_visited" not in self.user_sessions[wallet_address]:
                self.user_sessions[wallet_address]["pages_visited"] = []

            page_data = {
                "page": page,
                "timestamp": self._get_timestamp()
            }

            self.user_sessions[wallet_address]["pages_visited"].append(page_data)

            # Log to Supabase (with null check)
            if self.supabase_logger:
                self.supabase_logger.log_page_view(wallet_address, page, page_data)

    def get_user_analytics(self, wallet_address: str):
        """Get analytics data for a specific user"""
        user_data = {
            "wallet": wallet_address,
            "session_data": self.user_sessions.get(wallet_address, {}),
            "verification_history": self.verification_attempts.get(wallet_address, {}),
            "engagement_score": self._calculate_engagement_score(wallet_address)
        }
        return user_data

    def get_global_analytics(self):
        """Get global platform analytics synced from Supabase"""
        # Get comprehensive data from Supabase
        supabase_stats = self.supabase_logger.get_analytics_summary()

        # Get Learn & Earn specific data
        learn_earn_stats = self._get_learn_earn_stats()

        # Get total disbursements data
        disbursements_stats = self._get_total_disbursements_stats()

        # Combine all data sources
        total_users = supabase_stats.get("total_users", 0)
        verified_users = supabase_stats.get("verified_users", 0)
        total_page_views = supabase_stats.get("total_page_views", 0)

        # Get telegram task stats
        telegram_task_stats = self._get_telegram_task_stats()

        return {
            "metrics": {
                "total_users": total_users,
                "successful_verifications": verified_users,
                "failed_verifications": self.dashboard_metrics["failed_verifications"],
                "active_sessions": len(self.user_sessions),
                "learn_earn_users": learn_earn_stats.get("total_quiz_takers", 0),
                "telegram_task_users": telegram_task_stats.get("total_claimers", 0)
            },
            "user_activity": {
                "active_users_count": total_users,
                "total_page_views": total_page_views,
                "average_session_length": self._calculate_avg_session_length(),
                "learn_earn_completions": learn_earn_stats.get("total_quizzes", 0)
            },
            "verification_stats": {
                "success_rate": supabase_stats.get("verification_rate", self._calculate_success_rate()),
                "unique_wallets_attempted": total_users
            },
            "disbursement_analytics": {
                "total_g_disbursed": disbursements_stats.get("total_g_disbursed", 0),
                "total_g_disbursed_formatted": disbursements_stats.get("total_g_disbursed_formatted", "0 G$"),
                "breakdown": disbursements_stats.get("breakdown", {}),
                "breakdown_formatted": disbursements_stats.get("breakdown_formatted", {}),
                "platform_breakdown": {
                    "learn_earn": disbursements_stats.get("learn_earn_total", 0),
                    "forum_rewards": disbursements_stats.get("forum_rewards_total", 0),
                    "task_completion": disbursements_stats.get("task_completion_total", 0),
                    "p2p_volume": disbursements_stats.get("p2p_trading_volume", 0)
                }
            }
        }

    def _get_learn_earn_stats(self):
        """Get Learn & Earn statistics from Supabase"""
        try:
            from supabase_client import supabase, supabase_enabled

            if not supabase_enabled:
                return {"total_quiz_takers": 0, "total_quizzes": 0}

            # Get unique quiz takers
            quiz_users = supabase.table('learnearn_log').select('wallet_address').execute()
            unique_quiz_takers = len(set(user['wallet_address'] for user in quiz_users.data)) if quiz_users.data else 0

            # Get total completed quizzes
            total_quizzes = len(quiz_users.data) if quiz_users.data else 0

            return {
                "total_quiz_takers": unique_quiz_takers,
                "total_quizzes": total_quizzes
            }

        except Exception as e:
            print(f"❌ Error getting Learn & Earn stats: {e}")
            return {"total_quiz_takers": 0, "total_quizzes": 0}


    def _get_telegram_task_stats(self):
        """Get Telegram Task statistics from Supabase"""
        try:
            from supabase_client import supabase, supabase_enabled

            if not supabase_enabled:
                return {"total_claimers": 0, "total_claims": 0, "total_amount": 0}

            # Get all Telegram Task claims
            task_logs = supabase.table('telegram_task_log')\
                .select('wallet_address, reward_amount, created_at')\
                .eq('status', 'completed')\
                .execute()

            if not task_logs.data:
                return {"total_claimers": 0, "total_claims": 0, "total_amount": 0}

            # Get unique task claimers
            unique_claimers = len(set(user['wallet_address'] for user in task_logs.data))

            # Get total task claims
            total_claims = len(task_logs.data)

            # Calculate total amount disbursed
            total_amount = sum(float(log.get('reward_amount', 0)) for log in task_logs.data)

            logger.info(f"📊 Telegram Task Stats:")
            logger.info(f"   Total Unique Claimers: {unique_claimers}")
            logger.info(f"   Total Claims: {total_claims}")
            logger.info(f"   Total Amount Disbursed: {total_amount} G$")

            return {
                "total_claimers": unique_claimers,
                "total_claims": total_claims,
                "total_amount": total_amount
            }

        except Exception as e:
            logger.error(f"❌ Error getting Telegram Task stats: {e}")
            return {"total_claimers": 0, "total_claims": 0, "total_amount": 0}

    def get_gooddollar_insights(self):
        """Generate GoodDollar-specific insights from real data"""
        # Get real data from Supabase
        real_stats = self.supabase_logger.get_ubi_statistics()

        # Get additional platform stats
        learn_earn_stats = self._get_learn_earn_stats()

        # Get total G$ disbursements across all platforms
        total_disbursements_stats = self._get_total_disbursements_stats()

        insights = {
            "network_status": "🟢 Active",
            "estimated_users": real_stats.get("total_verified_users", "Loading..."),
            "daily_claims": real_stats.get("daily_ubi_claims", "Loading..."),
            "community_growth": real_stats.get("growth_rate", "Loading..."),
            "top_countries": real_stats.get("top_countries", ["Loading..."]),
            "platform_features": {
                "learn_earn_users": learn_earn_stats.get("total_quiz_takers", 0),
                "total_feature_users": learn_earn_stats.get("total_quiz_takers", 0)
            },
            "total_disbursements": total_disbursements_stats
        }
        return insights

    def _get_cached(self, key, ttl_seconds=60):
        """Get value from cache if it exists and hasn't expired"""
        if key in self._cache:
            cache_time = self._cache_times.get(key)
            if cache_time and (datetime.now() - cache_time).total_seconds() < ttl_seconds:
                return self._cache[key]
        return None

    def _set_cache(self, key, value):
        """Store value in cache with current timestamp"""
        self._cache[key] = value
        self._cache_times[key] = datetime.now()

    def get_dashboard_stats(self, wallet_address: str = None):
        """Get stats for dashboard display with Supabase sync"""
        cache_key = f"dashboard_stats_{wallet_address}" if wallet_address else "dashboard_stats_guest"
        cached = self._get_cached(cache_key, ttl_seconds=30)
        if cached:
            return cached

        if wallet_address:
            # Get user stats from Supabase
            supabase_user_stats = self.supabase_logger.get_user_stats(wallet_address)
            user_info = supabase_user_stats.get("user_info", {})

            # Fallback to local data if Supabase is unavailable
            local_user_stats = self.get_user_analytics(wallet_address)

            # Get user's Learn & Earn and hourly bonus participation
            user_feature_stats = self._get_user_feature_participation(wallet_address)

            # Get contract balance info
            contract_balance_info = self._get_contract_balance_info(wallet_address)

            # Get platform disbursements stats
            platform_stats = self.get_global_analytics()

            # Get disbursement analytics directly
            disbursement_analytics = self._get_total_disbursements_stats()

            logger.info(f"🔍 get_dashboard_stats - disbursement_analytics keys: {list(disbursement_analytics.keys()) if disbursement_analytics else 'None'}")
            logger.info(f"🔍 get_dashboard_stats - breakdown_formatted present: {'breakdown_formatted' in disbursement_analytics if disbursement_analytics else False}")

            result = {
                "user_stats": {
                    "sessions": user_info.get("total_sessions", len(local_user_stats["session_data"])),
                    "page_views": user_info.get("total_page_views", local_user_stats["session_data"].get("page_views", 0)),
                    "engagement": local_user_stats["engagement_score"],
                    "member_since": user_info.get("first_login", local_user_stats["session_data"].get("login_time", "Today")),
                    "learn_earn_quizzes": user_feature_stats.get("learn_earn_quizzes", 0),
                    "total_rewards_earned": user_feature_stats.get("total_rewards", 0)
                },
                "gooddollar_info": self.get_gooddollar_insights(),
                "platform_stats": platform_stats,
                "contract_balance": contract_balance_info,
                "disbursement_analytics": disbursement_analytics
            }
            self._set_cache(cache_key, result)
            return result
        else:
            # Support guest users (when wallet_address is None)
            # Return default stats for guests
            result = {
                "user_stats": {
                    "page_views": 0,
                    "learn_earn_quizzes": 0,
                    "telegram_task_claims": 0,
                    "total_rewards_earned": "0 G$",
                    "member_since": "Guest"
                },
                "platform_stats": self._get_platform_stats(),
                "gooddollar_info": self._get_gooddollar_info(),
                "disbursement_analytics": self._get_total_disbursements_stats()
            }
            self._set_cache(cache_key, result)
            return result


    def _get_total_disbursements_stats(self):
        """Get total G$ disbursements across all platform tables"""
        try:
            from supabase_client import supabase, supabase_enabled
            from datetime import datetime, timedelta
            import time

            # Cache results for 15 minutes
            cache_key = '_disbursement_stats_cache'
            cache_duration = 900  # 15 minutes (increased from 5)

            if hasattr(self, cache_key):
                cached_data, cached_time = getattr(self, cache_key)
                if time.time() - cached_time < cache_duration:
                    logger.info("📦 Using cached disbursement stats")
                    return cached_data

            logger.info("🔍 Starting _get_total_disbursements_stats...")

            if not supabase_enabled:
                logger.warning("⚠️ Supabase not enabled, returning fallback data")
                fallback_breakdown = {
                    "Learn & Earn Rewards": "0.0 G$",
                    "Telegram Task Rewards": "0.0 G$",
                    "Twitter Task Rewards": "0.0 G$",
                    "Community Stories Rewards": "0.0 G$",
                    "Minigames Withdrawals": "0.0 G$",
                    "Forum Rewards Disbursed": "0.0 G$",
                    "Task Completion Rewards": "0.0 G$",
                    "P2P Trading Volume": "0.0 G$"
                }
                return {
                    "total_g_disbursed": 0,
                    "total_g_disbursed_formatted": "0.0 G$",
                    "learn_earn_total": 0,
                    "telegram_task_total": 0,
                    "twitter_task_total": 0,
                    "community_stories_total": 0,
                    "minigames_total": 0,
                    "forum_rewards_total": 0,
                    "task_completion_total": 0,
                    "p2p_trading_volume": 0,
                    "breakdown": {
                        "learn_earn": 0,
                        "telegram_task": 0,
                        "twitter_task": 0,
                        "community_stories": 0,
                        "minigames_withdrawals": 0,
                        "forum_disbursed": 0,
                        "task_completion": 0,
                        "p2p_volume": 0
                    },
                    "breakdown_formatted": fallback_breakdown,
                    "weekly_breakdown": {
                        "learn_earn": 0,
                        "telegram_task": 0,
                        "twitter_task": 0,
                        "community_stories": 0
                    },
                    "weekly_breakdown_formatted": {
                        "learn_earn": "0.0 G$",
                        "telegram_task": "0.0 G$",
                        "twitter_task": "0.0 G$",
                        "community_stories": "0.0 G$"
                    },
                    "weekly_date_range": {
                        "start_date": "N/A",
                        "end_date": "N/A"
                    },
                    "monthly_breakdown": {
                        "learn_earn": 0,
                        "telegram_task": 0,
                        "twitter_task": 0,
                        "community_stories": 0
                    },
                    "monthly_breakdown_formatted": {
                        "learn_earn": "0.0 G$",
                        "telegram_task": "0.0 G$",
                        "twitter_task": "0.0 G$",
                        "community_stories": "0.0 G$"
                    },
                    "monthly_date_range": {
                        "start_date": "N/A",
                        "end_date": "N/A"
                    }
                }

            # Calculate date range for disbursements
            end_date = datetime.utcnow()

            # Monthly: November 1 to current date
            start_date_monthly = datetime(2024, 11, 1)

            # Weekly: Last 7 days from current date
            start_date_weekly = end_date - timedelta(days=7)

            # Format with time to ensure we capture full day ranges
            start_date_weekly_str = start_date_weekly.strftime('%Y-%m-%d 00:00:00')
            start_date_monthly_str = start_date_monthly.strftime('%Y-%m-%d 00:00:00')
            end_date_str = end_date.strftime('%Y-%m-%d 23:59:59')

            # Initialize totals
            total_disbursements = 0
            breakdown = {}

            # 1. Learn & Earn disbursements (learnearn_log) - ALL RECORDS (includes old and new)
            learn_earn_result = supabase.table('learnearn_log')\
                .select('amount_g$, status')\
                .execute()

            logger.info(f"📊 Learn & Earn Query: Found {len(learn_earn_result.data) if learn_earn_result.data else 0} records")
            if learn_earn_result.data:
                logger.info(f"   Sample records: {learn_earn_result.data[:3]}")

            # Sum ALL records - convert to float safely, handle None values
            learn_earn_total = 0
            if learn_earn_result.data:
                for record in learn_earn_result.data:
                    amount = record.get('amount_g$', 0)
                    if amount is not None and amount != '':
                        try:
                            learn_earn_total += float(amount)
                        except (ValueError, TypeError):
                            logger.warning(f"⚠️ Invalid amount in learnearn_log: {amount}")

            breakdown['learn_earn'] = learn_earn_total
            total_disbursements += learn_earn_total
            logger.info(f"   Total: {learn_earn_total} G$")

            # 2. Forum rewards disbursements (forum_reward_transactions) - ALL RECORDS
            forum_disbursed_result = supabase.table('forum_reward_transactions')\
                .select('amount_disbursed, status')\
                .execute()

            logger.info(f"📊 Forum Rewards Query: Found {len(forum_disbursed_result.data) if forum_disbursed_result.data else 0} records")

            forum_disbursed_total = 0
            if forum_disbursed_result.data:
                for record in forum_disbursed_result.data:
                    amount = record.get('amount_disbursed', 0)
                    if amount is not None and amount != '':
                        try:
                            forum_disbursed_total += float(amount)
                        except (ValueError, TypeError):
                            logger.warning(f"⚠️ Invalid amount in forum_reward_transactions: {amount}")

            breakdown['forum_disbursed'] = forum_disbursed_total
            total_disbursements += forum_disbursed_total
            logger.info(f"   Total: {forum_disbursed_total} G$")

            # 3. Task completion disbursements (task_completion_log) - ALL RECORDS
            # Handle case where table might not exist yet
            task_completion_total = 0
            try:
                task_completion_result = supabase.table('task_completion_log')\
                    .select('reward_amount, status')\
                    .execute()

                logger.info(f"📊 Task Completion Query: Found {len(task_completion_result.data) if task_completion_result.data else 0} records")

                if task_completion_result.data:
                    for record in task_completion_result.data:
                        amount = record.get('reward_amount', 0)
                        if amount is not None and amount != '':
                            try:
                                task_completion_total += float(amount)
                            except (ValueError, TypeError):
                                logger.warning(f"⚠️ Invalid amount in task_completion_log: {amount}")
            except Exception as e:
                # Table doesn't exist yet - this is expected if it hasn't been created
                logger.info(f"ℹ️ Task completion table not available yet (table will be created when first task is completed)")

            breakdown['task_completion'] = task_completion_total
            total_disbursements += task_completion_total
            logger.info(f"   Total: {task_completion_total} G$")

            # 5. Telegram Task disbursements (telegram_task_log) - ALL RECORDS
            telegram_task_total = 0
            try:
                telegram_task_result = supabase.table('telegram_task_log')\
                    .select('reward_amount, status')\
                    .execute()

                logger.info(f"📊 Telegram Task Query: Found {len(telegram_task_result.data) if telegram_task_result.data else 0} records")
                if telegram_task_result.data:
                    logger.info(f"   Sample records: {telegram_task_result.data[:3]}")

                if telegram_task_result.data:
                    for record in telegram_task_result.data:
                        amount = record.get('reward_amount', 0)
                        if amount is not None and amount != '':
                            try:
                                telegram_task_total += float(amount)
                            except (ValueError, TypeError):
                                logger.warning(f"⚠️ Invalid amount in telegram_task_log: {amount}")
            except Exception as e:
                logger.warning(f"⚠️ Telegram task table query failed: {e}")

            breakdown['telegram_task'] = telegram_task_total
            total_disbursements += telegram_task_total
            logger.info(f"   Total: {telegram_task_total} G$")

            # 5b. Twitter Task disbursements (twitter_task_log) - ALL RECORDS
            twitter_task_total = 0
            try:
                twitter_task_result = supabase.table('twitter_task_log')\
                    .select('reward_amount, status')\
                    .execute()

                logger.info(f"📊 Twitter Task Query: Found {len(twitter_task_result.data) if twitter_task_result.data else 0} records")
                if twitter_task_result.data:
                    logger.info(f"   Sample records: {twitter_task_result.data[:3]}")

                if twitter_task_result.data:
                    for record in twitter_task_result.data:
                        amount = record.get('reward_amount', 0)
                        if amount is not None and amount != '':
                            try:
                                twitter_task_total += float(amount)
                            except (ValueError, TypeError):
                                logger.warning(f"⚠️ Invalid amount in twitter_task_log: {amount}")
            except Exception as e:
                logger.warning(f"⚠️ Twitter task table query failed: {e}")

            breakdown['twitter_task'] = twitter_task_total
            total_disbursements += twitter_task_total
            logger.info(f"   Total: {twitter_task_total} G$")

            # 5c. Minigames withdrawals (minigame_rewards_log) - ALL token_withdrawal records
            minigames_total = 0
            try:
                minigames_result = supabase.table('minigame_rewards_log')\
                    .select('reward_amount, reward_type')\
                    .execute()

                logger.info(f"📊 Minigames Query: Found {len(minigames_result.data) if minigames_result.data else 0} records")
                if minigames_result.data:
                    logger.info(f"   Sample records: {minigames_result.data[:3]}")

                # Only count token_withdrawal records
                if minigames_result.data:
                    for record in minigames_result.data:
                        if record.get('reward_type') == 'token_withdrawal':
                            amount = record.get('reward_amount', 0)
                            if amount is not None and amount != '':
                                try:
                                    minigames_total += float(amount)
                                except (ValueError, TypeError):
                                    logger.warning(f"⚠️ Invalid amount in minigame_rewards_log: {amount}")
            except Exception as e:
                logger.warning(f"⚠️ Minigames table query failed: {e}")

            breakdown['minigames_withdrawals'] = minigames_total
            total_disbursements += minigames_total
            logger.info(f"   Total: {minigames_total} G$")

            # 5d. Community Stories disbursements (community_stories_submissions) - ALL approved records
            community_stories_total = 0
            try:
                # Fetch ALL approved Community Stories without date filtering
                community_stories_result = supabase.table('community_stories_submissions')\
                    .select('reward_amount, status, reviewed_at, wallet_address')\
                    .in_('status', ['approved', 'approved_low', 'approved_high'])\
                    .order('reviewed_at', desc=False)\
                    .execute()

                logger.info(f"📊 Community Stories Query (ALL TIME): Found {len(community_stories_result.data) if community_stories_result.data else 0} records")
                if community_stories_result.data:
                    logger.info(f"   Sample records (oldest to newest): {community_stories_result.data[:3]}")
                    logger.info(f"   Date range: {community_stories_result.data[0].get('reviewed_at')} (oldest) to {community_stories_result.data[-1].get('reviewed_at')} (newest)")

                if community_stories_result.data:
                    for record in community_stories_result.data:
                        amount = record.get('reward_amount', 0)
                        if amount is not None and amount != '':
                            try:
                                community_stories_total += float(amount)
                                logger.info(f"   Adding {float(amount)} G$ from {record.get('status')} - {record.get('wallet_address', 'unknown')[:8]}...")
                            except (ValueError, TypeError):
                                logger.warning(f"⚠️ Invalid amount in community_stories_submissions: {amount}")
            except Exception as e:
                logger.error(f"❌ Community Stories table query failed: {e}")
                import traceback
                logger.error(f"🔍 Traceback: {traceback.format_exc()}")

            breakdown['community_stories'] = community_stories_total
            total_disbursements += community_stories_total
            logger.info(f"   Total Community Stories (ALL TIME): {community_stories_total} G$")

            # 6. P2P Trading volume (p2p_trades) - ALL RECORDS
            p2p_volume = 0
            try:
                p2p_trades_result = supabase.table('p2p_trades')\
                    .select('g_dollar_amount, status')\
                    .execute()

                logger.info(f"📊 P2P Trades Query: Found {len(p2p_trades_result.data) if p2p_trades_result.data else 0} records")

                if p2p_trades_result.data:
                    for record in p2p_trades_result.data:
                        amount = record.get('g_dollar_amount', 0)
                        if amount is not None and amount != '':
                            try:
                                p2p_volume += float(amount)
                            except (ValueError, TypeError):
                                logger.warning(f"⚠️ Invalid amount in p2p_trades: {amount}")
            except Exception as e:
                logger.warning(f"⚠️ P2P trades table query failed: {e}")

            breakdown['p2p_volume'] = p2p_volume
            logger.info(f"   Total: {p2p_volume} G$")

            # Get weekly disbursements (last 7 days)
            logger.info(f"📅 Calculating weekly disbursements from {start_date_weekly_str} to {end_date_str}...")

            # Weekly Learn & Earn
            logger.info(f"🔍 Querying Learn & Earn (weekly) from {start_date_weekly_str} to {end_date_str}")
            weekly_learn_earn_result = supabase.table('learnearn_log')\
                .select('amount_g$, timestamp')\
                .gte('timestamp', start_date_weekly_str)\
                .lte('timestamp', end_date_str)\
                .eq('status', True)\
                .execute()

            weekly_learn_earn_total = 0
            if weekly_learn_earn_result.data:
                for record in weekly_learn_earn_result.data:
                    amount = record.get('amount_g$', 0)
                    if amount is not None and amount != '':
                        try:
                            weekly_learn_earn_total += float(amount)
                        except (ValueError, TypeError):
                            pass

            # Weekly Telegram Task
            logger.info(f"🔍 Querying Telegram Task (weekly) from {start_date_weekly_str} to {end_date_str}")
            weekly_telegram_result = supabase.table('telegram_task_log')\
                .select('reward_amount, created_at')\
                .gte('created_at', start_date_weekly_str)\
                .lte('created_at', end_date_str)\
                .execute()

            weekly_telegram_total = 0
            if weekly_telegram_result.data:
                for record in weekly_telegram_result.data:
                    amount = record.get('reward_amount', 0)
                    if amount is not None and amount != '':
                        try:
                            weekly_telegram_total += float(amount)
                        except (ValueError, TypeError):
                            pass

            # Weekly Twitter Task
            logger.info(f"🔍 Querying Twitter Task (weekly) from {start_date_weekly_str} to {end_date_str}")
            weekly_twitter_result = supabase.table('twitter_task_log')\
                .select('reward_amount, created_at')\
                .gte('created_at', start_date_weekly_str)\
                .lte('created_at', end_date_str)\
                .execute()

            weekly_twitter_total = 0
            if weekly_twitter_result.data:
                for record in weekly_twitter_result.data:
                    amount = record.get('reward_amount', 0)
                    if amount is not None and amount != '':
                        try:
                            weekly_twitter_total += float(amount)
                        except (ValueError, TypeError):
                            pass

            # Weekly Community Stories
            logger.info(f"🔍 Querying Community Stories (weekly) from {start_date_weekly_str} to {end_date_str}")
            weekly_community_result = supabase.table('community_stories_submissions')\
                .select('reward_amount, reviewed_at, status')\
                .in_('status', ['approved', 'approved_low', 'approved_high'])\
                .gte('reviewed_at', start_date_weekly_str)\
                .lte('reviewed_at', end_date_str)\
                .execute()

            logger.info(f"📊 Weekly Community Stories Query Result: {len(weekly_community_result.data) if weekly_community_result.data else 0} records")
            if weekly_community_result.data:
                logger.info(f"   Sample records: {weekly_community_result.data[:3]}")

            weekly_community_total = 0
            if weekly_community_result.data:
                for record in weekly_community_result.data:
                    amount = record.get('reward_amount', 0)
                    if amount is not None and amount != '':
                        try:
                            weekly_community_total += float(amount)
                            logger.info(f"   Adding {float(amount)} G$ from {record.get('status')} submission")
                        except (ValueError, TypeError):
                            logger.warning(f"   Invalid amount: {amount}")

            logger.info(f"📅 Weekly Telegram Task: {weekly_telegram_total} G$")
            logger.info(f"📅 Weekly Twitter Task: {weekly_twitter_total} G$")
            logger.info(f"📅 Weekly Community Stories: {weekly_community_total} G$")

            # Get monthly disbursements (last 30 days)
            logger.info(f"📅 Calculating monthly disbursements from {start_date_monthly_str} to {end_date_str}...")

            # Monthly Learn & Earn
            logger.info(f"🔍 Querying Learn & Earn (monthly) from {start_date_monthly_str} to {end_date_str}")
            monthly_learn_earn_result = supabase.table('learnearn_log')\
                .select('amount_g$, timestamp')\
                .gte('timestamp', start_date_monthly_str)\
                .lte('timestamp', end_date_str)\
                .eq('status', True)\
                .execute()

            monthly_learn_earn_total = 0
            if monthly_learn_earn_result.data:
                for record in monthly_learn_earn_result.data:
                    amount = record.get('amount_g$', 0)
                    if amount is not None and amount != '':
                        try:
                            monthly_learn_earn_total += float(amount)
                        except (ValueError, TypeError):
                            pass

            # Monthly Telegram Task
            logger.info(f"🔍 Querying Telegram Task (monthly) from {start_date_monthly_str} to {end_date_str}")
            monthly_telegram_result = supabase.table('telegram_task_log')\
                .select('reward_amount, created_at')\
                .gte('created_at', start_date_monthly_str)\
                .lte('created_at', end_date_str)\
                .execute()

            monthly_telegram_total = 0
            if monthly_telegram_result.data:
                for record in monthly_telegram_result.data:
                    amount = record.get('reward_amount', 0)
                    if amount is not None and amount != '':
                        try:
                            monthly_telegram_total += float(amount)
                        except (ValueError, TypeError):
                            pass

            # Monthly Twitter Task
            logger.info(f"🔍 Querying Twitter Task (monthly) from {start_date_monthly_str} to {end_date_str}")
            monthly_twitter_result = supabase.table('twitter_task_log')\
                .select('reward_amount, created_at')\
                .gte('created_at', start_date_monthly_str)\
                .lte('created_at', end_date_str)\
                .execute()

            monthly_twitter_total = 0
            if monthly_twitter_result.data:
                for record in monthly_twitter_result.data:
                    amount = record.get('reward_amount', 0)
                    if amount is not None and amount != '':
                        try:
                            monthly_twitter_total += float(amount)
                        except (ValueError, TypeError):
                            pass

            # Monthly Community Stories
            logger.info(f"🔍 Querying Community Stories (monthly) from {start_date_monthly_str} to {end_date_str}")
            try:
                monthly_community_result = supabase.table('community_stories_submissions')\
                    .select('reward_amount, reviewed_at, status')\
                    .in_('status', ['approved', 'approved_low', 'approved_high'])\
                    .gte('reviewed_at', start_date_monthly_str)\
                    .lte('reviewed_at', end_date_str)\
                    .execute()

                logger.info(f"📊 Monthly Community Stories Query Result: {len(monthly_community_result.data) if monthly_community_result.data else 0} records")
                if monthly_community_result.data:
                    logger.info(f"   Sample records: {monthly_community_result.data[:3]}")

                monthly_community_total = 0
                if monthly_community_result.data:
                    for record in monthly_community_result.data:
                        amount = record.get('reward_amount', 0)
                        if amount is not None and amount != '':
                            try:
                                monthly_community_total += float(amount)
                                logger.info(f"   Adding {float(amount)} G$ from {record.get('status')} submission")
                            except (ValueError, TypeError):
                                logger.warning(f"   Invalid amount: {amount}")
            except Exception as e:
                logger.error(f"❌ Error querying monthly Community Stories: {e}")
                monthly_community_total = 0

            logger.info(f"📅 Monthly Learn & Earn: {monthly_learn_earn_total} G$")
            logger.info(f"📅 Monthly Telegram Task: {monthly_telegram_total} G$")
            logger.info(f"📅 Monthly Twitter Task: {monthly_twitter_total} G$")
            logger.info(f"📅 Monthly Community Stories: {monthly_community_total} G$")

            # Format breakdown for display
            breakdown_formatted = {
                "Learn & Earn Rewards": f"{learn_earn_total:,.1f} G$",
                "Telegram Task Rewards": f"{telegram_task_total:,.1f} G$",
                "Twitter Task Rewards": f"{twitter_task_total:,.1f} G$",
                "Community Stories Rewards": f"{community_stories_total:,.1f} G$",
                "Minigames Withdrawals": f"{minigames_total:,.1f} G$",
                "Forum Rewards Disbursed": f"{forum_disbursed_total:,.1f} G$",
                "Task Completion Rewards": f"{task_completion_total:,.1f} G$",
                "P2P Trading Volume": f"{p2p_volume:,.1f} G$"
            }

            logger.info(f"📊 Breakdown formatted includes Community Stories: {community_stories_total:,.1f} G$")

            weekly_breakdown = {
                "learn_earn": weekly_learn_earn_total,
                "telegram_task": weekly_telegram_total,
                "twitter_task": weekly_twitter_total,
                "community_stories": weekly_community_total
            }

            weekly_breakdown_formatted = {
                "learn_earn": f"{weekly_learn_earn_total:,.1f} G$",
                "telegram_task": f"{weekly_telegram_total:,.1f} G$",
                "twitter_task": f"{weekly_twitter_total:,.1f} G$",
                "community_stories": f"{weekly_community_total:,.1f} G$"
            }

            weekly_date_range = {
                "start_date": start_date_weekly.strftime('%b %d, %Y'),  # Nov 04, 2025
                "end_date": end_date.strftime('%b %d, %Y')       # Nov 11, 2025
            }

            monthly_breakdown = {
                "learn_earn": monthly_learn_earn_total,
                "telegram_task": monthly_telegram_total,
                "twitter_task": monthly_twitter_total,
                "community_stories": monthly_community_total
            }

            monthly_breakdown_formatted = {
                "learn_earn": f"{monthly_learn_earn_total:,.1f} G$",
                "telegram_task": f"{monthly_telegram_total:,.1f} G$",
                "twitter_task": f"{monthly_twitter_total:,.1f} G$",
                "community_stories": f"{monthly_community_total:,.1f} G$"
            }

            monthly_date_range = {
                "start_date": start_date_monthly.strftime('%b %d, %Y'),  # Oct 12, 2025
                "end_date": end_date.strftime('%b %d, %Y')       # Nov 11, 2025
            }

            logger.info(f"📊 Formatted breakdown: {breakdown_formatted}")

            logger.info(f"📊 Total G$ Disbursements Analysis:")
            logger.info(f"   Learn & Earn: {learn_earn_total:,.1f} G$")
            logger.info(f"   Telegram Task: {telegram_task_total:,.1f} G$")
            logger.info(f"   Twitter Task: {twitter_task_total:,.1f} G$")
            logger.info(f"   Community Stories: {community_stories_total:,.1f} G$")
            logger.info(f"   Minigames Withdrawals: {minigames_total:,.1f} G$")
            logger.info(f"   Forum Disbursed: {forum_disbursed_total:,.1f} G$")
            logger.info(f"   Task Completion: {task_completion_total:,.1f} G$")
            logger.info(f"   P2P Volume: {p2p_volume:,.1f} G$")
            logger.info(f"   TOTAL DISBURSED: {total_disbursements:,.1f} G$")

            logger.info(f"✅ Returning disbursement data with {len(breakdown_formatted)} categories")
            logger.info(f"🔍 breakdown_formatted type: {type(breakdown_formatted)}")
            logger.info(f"🔍 breakdown_formatted content: {json.dumps(breakdown_formatted, indent=2)}")

            result = {
                'total_g_disbursed': total_disbursements,
                'total_g_disbursed_formatted': f"{total_disbursements:,.2f} G$",
                'learn_earn_total': learn_earn_total,
                'telegram_task_total': telegram_task_total,
                'twitter_task_total': twitter_task_total,
                'community_stories_total': community_stories_total,
                'minigames_total': minigames_total,
                'forum_rewards_total': forum_disbursed_total,
                'task_completion_total': task_completion_total,
                'p2p_trading_volume': p2p_volume,
                'breakdown': breakdown,
                'breakdown_formatted': breakdown_formatted,
                'weekly_breakdown': weekly_breakdown,
                'weekly_breakdown_formatted': weekly_breakdown_formatted,
                'weekly_date_range': weekly_date_range,
                'monthly_breakdown': monthly_breakdown,
                'monthly_breakdown_formatted': monthly_breakdown_formatted,
                'monthly_date_range': monthly_date_range
            }

            logger.info(f"🔍 FINAL RESULT - breakdown_formatted in result: {'breakdown_formatted' in result}")
            logger.info(f"🔍 FINAL RESULT keys: {list(result.keys())}")

            # Cache the result
            setattr(self, '_disbursement_stats_cache', (result, time.time()))

            return result

        except Exception as e:
            logger.error(f"❌ Error calculating total disbursements: {e}")
            import traceback
            logger.error(f"📊 Full error traceback: {traceback.format_exc()}")

            # Provide fallback data with proper structure - MUST include Task Completion
            fallback_breakdown = {
                "Learn & Earn Rewards": "0.0 G$",
                "Telegram Task Rewards": "0.0 G$",
                "Twitter Task Rewards": "0.0 G$",
                "Community Stories Rewards": "0.0 G$",
                "Minigames Withdrawals": "0.0 G$",
                "Forum Rewards Disbursed": "0.0 G$",
                "Task Completion Rewards": "0.0 G$",
                "P2P Trading Volume": "0.0 G$"
            }
            logger.error(f"📊 Using fallback breakdown: {fallback_breakdown}")
            
            fallback_result = {
                "total_g_disbursed": 0,
                "total_g_disbursed_formatted": "0.0 G$",
                "learn_earn_total": 0,
                "telegram_task_total": 0,
                "twitter_task_total": 0,
                "community_stories_total": 0,
                "minigames_total": 0,
                "forum_rewards_total": 0,
                "task_completion_total": 0,
                "p2p_trading_volume": 0,
                "breakdown": {
                    "learn_earn": 0,
                    "telegram_task": 0,
                    "twitter_task": 0,
                    "community_stories": 0,
                    "minigames_withdrawals": 0,
                    "forum_disbursed": 0,
                    "task_completion": 0,
                    "p2p_volume": 0
                },
                "breakdown_formatted": fallback_breakdown,
                "weekly_breakdown": {
                    "learn_earn": 0,
                    "telegram_task": 0,
                    "twitter_task": 0,
                    "community_stories": 0
                },
                "weekly_breakdown_formatted": {
                    "learn_earn": "0.0 G$",
                    "telegram_task": "0.0 G$",
                    "twitter_task": "0.0 G$",
                    "community_stories": "0.0 G$"
                },
                "weekly_date_range": {
                    "start_date": "N/A",
                    "end_date": "N/A"
                },
                "monthly_breakdown": {
                    "learn_earn": 0,
                    "telegram_task": 0,
                    "twitter_task": 0,
                    "community_stories": 0
                },
                "monthly_breakdown_formatted": {
                    "learn_earn": "0.0 G$",
                    "telegram_task": "0.0 G$",
                    "twitter_task": "0.0 G$",
                    "community_stories": "0.0 G$"
                },
                "monthly_date_range": {
                    "start_date": "N/A",
                    "end_date": "N/A"
                }
            }
            
            logger.error(f"📊 Returning complete fallback structure with {len(fallback_breakdown)} breakdown categories")
            return fallback_result

    def _get_user_feature_participation(self, wallet_address: str):
        """Get user's participation in Learn & Earn and Telegram Task - includes ALL historical claims"""
        try:
            from supabase_client import supabase, supabase_enabled
            from learn_and_earn.learn_and_earn import quiz_manager

            if not supabase_enabled:
                return {"learn_earn_quizzes": 0, "telegram_task_claims": 0, "total_rewards": 0}

            # Mask wallet address for database lookup
            masked_address = quiz_manager.mask_wallet_address(wallet_address)

            # Get Learn & Earn data
            learn_earn_data = supabase.table('learnearn_log')\
                .select('*')\
                .eq('wallet_address', masked_address)\
                .eq('status', True)\
                .execute()

            # Get Telegram Task data
            telegram_task_data = supabase.table('telegram_task_log')\
                .select('*')\
                .eq('wallet_address', wallet_address)\
                .eq('status', 'completed')\
                .execute()

            # Calculate totals
            learn_earn_quizzes = len(learn_earn_data.data) if learn_earn_data.data else 0
            telegram_task_claims = len(telegram_task_data.data) if telegram_task_data.data else 0

            # Calculate total rewards from ALL historical logs
            learn_earn_rewards = sum(float(quiz.get('amount_g$', 0)) for quiz in learn_earn_data.data) if learn_earn_data.data else 0
            telegram_task_rewards = sum(float(task.get('reward_amount', 0)) for task in telegram_task_data.data) if telegram_task_data.data else 0
            total_rewards = learn_earn_rewards + telegram_task_rewards

            logger.info(f"📊 User Feature Participation for {masked_address}:")
            logger.info(f"   Learn & Earn Quizzes: {learn_earn_quizzes} (Total: {learn_earn_rewards} G$)")
            logger.info(f"   Telegram Task Claims: {telegram_task_claims} (Total: {telegram_task_rewards} G$)")
            logger.info(f"   Total Rewards: {total_rewards} G$")

            return {
                "learn_earn_quizzes": learn_earn_quizzes,
                "telegram_task_claims": telegram_task_claims,
                "total_rewards": total_rewards
            }

        except Exception as e:
            logger.error(f"❌ Error getting user feature participation: {e}")
            return {"learn_earn_quizzes": 0, "telegram_task_claims": 0, "total_rewards": 0}

    def _get_timestamp(self):
        """Get current timestamp"""
        from datetime import datetime
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def _calculate_engagement_score(self, wallet_address: str):
        """Calculate user engagement score (0-100)"""
        if wallet_address not in self.user_sessions:
            return 0

        session = self.user_sessions[wallet_address]
        page_views = session.get("page_views", 0)

        # Simple engagement calculation
        score = min(100, page_views * 10 + 20)  # Base 20, +10 per page view
        return score

    def _calculate_avg_session_length(self):
        """Calculate average session length in minutes"""
        if not self.user_sessions:
            return 0

        # Mock calculation - in real app would calculate from login to last activity
        return "12 minutes"  # Placeholder

    def _get_contract_balance_info(self, wallet_address: str):
        """Get contract balance information for dashboard display"""
        try:
            # Import blockchain service from main
            from blockchain import get_gooddollar_balance

            balance_result = get_gooddollar_balance(wallet_address)

            return {
                "user_balance": balance_result.get("balance", 0),
                "user_balance_formatted": balance_result.get("balance_formatted", "0.00 G$"),
                "contract_address": balance_result.get("contract", ""),
                "success": balance_result.get("success", False)
            }

        except Exception as e:
            print(f"❌ Error getting contract balance info: {e}")
            return {
                "user_balance": 0,
                "user_balance_formatted": "Error loading",
                "contract_address": "",
                "success": False
            }

    def _calculate_success_rate(self):
        """Calculate verification success rate"""
        total_attempts = self.dashboard_metrics["successful_verifications"] + self.dashboard_metrics["failed_verifications"]
        if total_attempts == 0:
            return "N/A"

        success_rate = (self.dashboard_metrics["successful_verifications"] / total_attempts) * 100
        return f"{success_rate:.1f}%"

    def _get_platform_stats(self):
        """Get platform-level statistics for guest users."""
        # Get real platform statistics using get_global_analytics
        return self.get_global_analytics()

    def _get_gooddollar_info(self):
        """Get general GoodDollar information for guest users."""
        # Returns real GoodDollar insights
        return self.get_gooddollar_insights()


# Global analytics instance
analytics = AnalyticsService()

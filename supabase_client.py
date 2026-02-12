import os
import logging
import time
from supabase import create_client, Client
from datetime import datetime
import json
from functools import wraps

# Configure logging
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# Supabase configuration
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_ANON_KEY")

# Initialize Supabase client with error handling
supabase: Client = None
supabase_enabled = False

def retry_on_connection_error(max_retries=3, delay=1):
    """Decorator to retry database operations on connection errors"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None

            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    error_msg = str(e).lower()

                    # Check if it's a connection-related error
                    if any(keyword in error_msg for keyword in ['server disconnected', 'connection', 'timeout', 'network']):
                        if attempt < max_retries - 1:
                            logger.warning(f"⚠️ Connection error on attempt {attempt + 1}/{max_retries}: {e}")
                            time.sleep(delay * (attempt + 1))  # Exponential backoff
                            continue
                        else:
                            logger.error(f"❌ All {max_retries} connection attempts failed: {e}")
                    else:
                        # Not a connection error, don't retry
                        raise e

            # If we get here, all retries failed
            raise last_exception
        return wrapper
    return decorator

def get_supabase_client():
    """Get Supabase client instance with retry logic for initialization"""
    global supabase, supabase_enabled

    if not SUPABASE_URL or not SUPABASE_KEY or SUPABASE_URL == "your-supabase-url":
        logger.error("❌ SUPABASE NOT CONFIGURED!")
        logger.error(f"   SUPABASE_URL exists: {bool(SUPABASE_URL)}")
        logger.error(f"   SUPABASE_KEY exists: {bool(SUPABASE_KEY)}")
        logger.warning("⚠️ Supabase not configured - using local analytics only")
        logger.info("💡 Set SUPABASE_URL and SUPABASE_ANON_KEY environment variables to enable Supabase logging")
        return None

    # Attempt to create client, with retries for initial connection
    for attempt in range(3): # Initial connection retries
        try:
            supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
            # Test connection by performing a simple query
            supabase.table("user_data").select("id").limit(1).execute()
            supabase_enabled = True
            logger.info("✅ Supabase client initialized successfully")
            return supabase
        except Exception as e:
            logger.error(f"❌ Supabase initialization failed on attempt {attempt + 1}: {e}")
            if attempt < 2:
                time.sleep(2) # Wait before retrying initialization
            else:
                logger.error("💡 Check your Supabase URL and API key in environment variables")
                supabase_enabled = False
                return None
    return None # Should not be reached if logic is sound

# Initialize the client
supabase = get_supabase_client()

# SQL COMMANDS TO RUN IN YOUR SUPABASE SQL EDITOR:
# Copy and run these commands one by one in your Supabase SQL Editor

"""
-- 0. IMPORTANT: Allow NULL transaction_hash for pending Telegram task submissions
-- Run this FIRST to fix the approval workflow:
ALTER TABLE telegram_task_log ALTER COLUMN transaction_hash DROP NOT NULL;

-- 1. Create user_data table for user storage and counting
CREATE TABLE IF NOT EXISTS user_data (
    id SERIAL PRIMARY KEY,
    wallet_address VARCHAR(42) UNIQUE NOT NULL,
    first_login TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    last_login TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    total_logins INTEGER DEFAULT 1,
    total_sessions INTEGER DEFAULT 0,
    ubi_verified BOOLEAN DEFAULT FALSE,
    verification_timestamp TIMESTAMP WITH TIME ZONE,
    total_page_views INTEGER DEFAULT 0,
    user_agent TEXT,
    ip_address INET,
    username VARCHAR(50) UNIQUE,
    username_set_at TIMESTAMP WITH TIME ZONE,
    username_edited BOOLEAN DEFAULT FALSE,
    username_last_edited TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 1.1 Create news_articles table for news feed system
CREATE TABLE IF NOT EXISTS news_articles (
    id SERIAL PRIMARY KEY,
    title VARCHAR(200) NOT NULL,
    content TEXT NOT NULL,
    category VARCHAR(50) DEFAULT 'announcement',
    priority VARCHAR(20) DEFAULT 'medium', -- 'low', 'medium', 'high'
    author VARCHAR(100) DEFAULT 'Admin',
    published BOOLEAN DEFAULT TRUE,
    featured BOOLEAN DEFAULT FALSE,
    image_url TEXT,
    url TEXT, -- External link URL (optional)
    view_count INTEGER DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 2. Create user_sessions table for all activities and session tracking
CREATE TABLE IF NOT EXISTS user_sessions (
    id SERIAL PRIMARY KEY,
    wallet_address VARCHAR(42) NOT NULL,
    activity_type VARCHAR(50) NOT NULL, -- 'login', 'logout', 'page_view', 'verification_attempt', 'ubi_activity'
    session_id VARCHAR(100),
    page VARCHAR(100),
    success BOOLEAN,
    details JSONB,
    ip_address INET,
    user_agent TEXT,
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    -- Foreign key reference
    CONSTRAINT fk_user_sessions_wallet 
        FOREIGN KEY (wallet_address) 
        REFERENCES user_data(wallet_address) 
        ON DELETE CASCADE
);

-- 3. Create indexes for better performance
CREATE INDEX IF NOT EXISTS idx_user_data_wallet ON user_data(wallet_address);
CREATE INDEX IF NOT EXISTS idx_user_data_verified ON user_data(ubi_verified);
CREATE INDEX IF NOT EXISTS idx_user_sessions_wallet ON user_sessions(wallet_address);
CREATE INDEX IF NOT EXISTS idx_user_sessions_activity ON user_sessions(activity_type);
CREATE INDEX IF NOT EXISTS idx_user_sessions_timestamp ON user_sessions(timestamp);
CREATE INDEX IF NOT EXISTS idx_user_sessions_session_id ON user_sessions(session_id);

-- 3.1 Create indexes for news_articles table
CREATE INDEX IF NOT EXISTS idx_news_articles_published ON news_articles(published);
CREATE INDEX IF NOT EXISTS idx_news_articles_featured ON news_articles(featured);
CREATE INDEX IF NOT EXISTS idx_news_articles_category ON news_articles(category);
CREATE INDEX IF NOT EXISTS idx_news_articles_created_at ON news_articles(created_at);
CREATE INDEX IF NOT EXISTS idx_news_articles_priority ON news_articles(priority);

-- 3.2 Create reloadly_orders table for mobile top-up transactions
CREATE TABLE IF NOT EXISTS reloadly_orders (
    id SERIAL PRIMARY KEY,
    order_id VARCHAR(50) UNIQUE NOT NULL,
    wallet_address VARCHAR(42) NOT NULL,
    phone_number VARCHAR(20) NOT NULL,
    operator_id INTEGER NOT NULL,
    product_id VARCHAR(100),
    local_amount DECIMAL(10,2) NOT NULL,
    local_currency VARCHAR(10) NOT NULL,
    g_dollar_amount DECIMAL(18,8) NOT NULL,
    amount DECIMAL(18,8), -- backward compatibility
    status VARCHAR(50) DEFAULT 'pending_payment',
    merchant_address VARCHAR(42),
    payment_timeout TIMESTAMP WITH TIME ZONE,
    transaction_hash VARCHAR(66),
    reloadly_transaction_id VARCHAR(100),
    payment_confirmed_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 3.3 Create indexes for reloadly_orders table
CREATE INDEX IF NOT EXISTS idx_reloadly_orders_wallet ON reloadly_orders(wallet_address);
CREATE INDEX IF NOT EXISTS idx_reloadly_orders_order_id ON reloadly_orders(order_id);
CREATE INDEX IF NOT EXISTS idx_reloadly_orders_status ON reloadly_orders(status);
CREATE INDEX IF NOT EXISTS idx_reloadly_orders_created_at ON reloadly_orders(created_at);

-- Referral tables removedH TIME ZONE DEFAULT NOW()
);

-- Referral indexes and policies removedds_log FOR ALL USING (true);

-- Create forum_rewards_log table for tracking post rewards
CREATE TABLE IF NOT EXISTS forum_rewards_log (
    id SERIAL PRIMARY KEY,
    transaction_hash VARCHAR(66) NOT NULL,
    post_id INTEGER NOT NULL,
    author_wallet VARCHAR(42) NOT NULL,
    reward_amount DECIMAL(18,8) NOT NULL,
    new_likes_rewarded INTEGER NOT NULL,
    rewarded_likes INTEGER NOT NULL,  -- Total likes rewarded so far
    reward_type VARCHAR(50) DEFAULT 'post_like',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Create forum_like_rewards_log table for tracking like giver rewards
CREATE TABLE IF NOT EXISTS forum_like_rewards_log (
    id SERIAL PRIMARY KEY,
    transaction_hash VARCHAR(66) NOT NULL,
    post_id INTEGER NOT NULL,
    liker_wallet VARCHAR(42) NOT NULL,
    reward_amount DECIMAL(18,8) NOT NULL,
    reward_type VARCHAR(50) DEFAULT 'like_given',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Create indexes for forum_rewards_log table
CREATE INDEX IF NOT EXISTS idx_forum_rewards_log_author ON forum_rewards_log(author_wallet);
CREATE INDEX IF NOT EXISTS idx_forum_rewards_log_post ON forum_rewards_log(post_id);
CREATE INDEX IF NOT EXISTS idx_forum_rewards_log_created_at ON forum_rewards_log(created_at);

-- Create indexes for forum_like_rewards_log table
CREATE INDEX IF NOT EXISTS idx_forum_like_rewards_log_liker ON forum_like_rewards_log(liker_wallet);
CREATE INDEX IF NOT EXISTS idx_forum_like_rewards_log_post ON forum_like_rewards_log(post_id);
CREATE INDEX IF NOT EXISTS idx_forum_like_rewards_log_created_at ON forum_like_rewards_log(created_at);

-- Enable RLS and create policies for forum_rewards_log
ALTER TABLE forum_rewards_log ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Allow all operations on forum_rewards_log" ON forum_rewards_log FOR ALL USING (true);

-- Enable RLS and create policies for forum_like_rewards_log
ALTER TABLE forum_like_rewards_log ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Allow all operations on forum_like_rewards_log" ON forum_like_rewards_log FOR ALL USING (true);

-- Create forum_comment_rewards_log table for tracking comment rewards
CREATE TABLE IF NOT EXISTS forum_comment_rewards_log (
    id SERIAL PRIMARY KEY,
    transaction_hash VARCHAR(66) NOT NULL,
    comment_id INTEGER NOT NULL,
    post_id INTEGER NOT NULL,
    commenter_wallet VARCHAR(42) NOT NULL,
    reward_amount DECIMAL(18,8) NOT NULL,
    reward_type VARCHAR(50) DEFAULT 'comment_made',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Create forum_pending_rewards table for accumulating rewards before disbursement
CREATE TABLE IF NOT EXISTS forum_pending_rewards (
    id SERIAL PRIMARY KEY,
    wallet_address VARCHAR(42) NOT NULL,
    pending_amount DECIMAL(18,8) DEFAULT 0,
    total_earned DECIMAL(18,8) DEFAULT 0,
    last_updated TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(wallet_address)
);

-- Create forum_reward_transactions table for tracking disbursements
CREATE TABLE IF NOT EXISTS forum_reward_transactions (
    id SERIAL PRIMARY KEY,
    wallet_address VARCHAR(42) NOT NULL,
    transaction_hash VARCHAR(66) NOT NULL,
    amount_disbursed DECIMAL(18,8) NOT NULL,
    transaction_type VARCHAR(50) DEFAULT 'auto_disbursement', -- 'auto_disbursement', 'manual_withdrawal'
    status VARCHAR(50) DEFAULT 'completed',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Create indexes for forum_comment_rewards_log table
CREATE INDEX IF NOT EXISTS idx_forum_comment_rewards_log_commenter ON forum_comment_rewards_log(commenter_wallet);
CREATE INDEX IF NOT EXISTS idx_forum_comment_rewards_log_comment ON forum_comment_rewards_log(comment_id);
CREATE INDEX IF NOT EXISTS idx_forum_comment_rewards_log_post ON forum_comment_rewards_log(post_id);
CREATE INDEX IF NOT EXISTS idx_forum_comment_rewards_log_created_at ON forum_comment_rewards_log(created_at);

-- Enable RLS and create policies for forum_comment_rewards_log
ALTER TABLE forum_comment_rewards_log ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Allow all operations on forum_comment_rewards_log" ON forum_comment_rewards_log FOR ALL USING (true);

-- Create indexes for forum_pending_rewards table
CREATE INDEX IF NOT EXISTS idx_forum_pending_rewards_wallet ON forum_pending_rewards(wallet_address);
CREATE INDEX IF NOT EXISTS idx_forum_pending_rewards_pending_amount ON forum_pending_rewards(pending_amount);
CREATE INDEX IF NOT EXISTS idx_forum_pending_rewards_last_updated ON forum_pending_rewards(last_updated);

-- Create indexes for forum_reward_transactions table
CREATE INDEX IF NOT EXISTS idx_forum_reward_transactions_wallet ON forum_reward_transactions(wallet_address);
CREATE INDEX IF NOT EXISTS idx_forum_reward_transactions_created_at ON forum_reward_transactions(created_at);
CREATE INDEX IF NOT EXISTS idx_forum_reward_transactions_status ON forum_reward_transactions(status);

-- Create community_screenshots table for community stories requirement examples
CREATE TABLE IF NOT EXISTS community_screenshots (
    id SERIAL PRIMARY KEY,
    screenshot_url TEXT NOT NULL,
    wallet_address VARCHAR(42) DEFAULT 'admin_requirement',
    title VARCHAR(200),
    image_type VARCHAR(50) DEFAULT 'requirement', -- 'requirement', 'user_submission'
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Create indexes for community_screenshots table
CREATE INDEX IF NOT EXISTS idx_community_screenshots_image_type ON community_screenshots(image_type);
CREATE INDEX IF NOT EXISTS idx_community_screenshots_wallet ON community_screenshots(wallet_address);
CREATE INDEX IF NOT EXISTS idx_community_screenshots_created_at ON community_screenshots(created_at);

-- Enable RLS and create policies for community_screenshots
ALTER TABLE community_screenshots ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Allow all operations on community_screenshots" ON community_screenshots FOR ALL USING (true);

-- Create forum_images table for storing uploaded images
CREATE TABLE IF NOT EXISTS forum_images (
    id SERIAL PRIMARY KEY,
    post_id INTEGER NOT NULL,
    image_url TEXT NOT NULL,
    uploaded_by VARCHAR(42) NOT NULL,
    upload_source VARCHAR(50) DEFAULT 'url', -- 'imgbb', 'url', 'other'
    image_size_bytes INTEGER,
    image_width INTEGER,
    image_height INTEGER,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    -- Foreign key reference
    CONSTRAINT fk_forum_images_post 
        FOREIGN KEY (post_id) 
        REFERENCES forum_posts(id) 
        ON DELETE CASCADE
);

-- Create indexes for forum_images table
CREATE INDEX IF NOT EXISTS idx_forum_images_post_id ON forum_images(post_id);
CREATE INDEX IF NOT EXISTS idx_forum_images_uploaded_by ON forum_images(uploaded_by);
CREATE INDEX IF NOT EXISTS idx_forum_images_created_at ON forum_images(created_at);

-- Enable RLS and create policies for forum_images
ALTER TABLE forum_images ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Allow all operations on forum_images" ON forum_images FOR ALL USING (true);

-- Create admin_broadcast_messages table for admin announcements
CREATE TABLE IF NOT EXISTS admin_broadcast_messages (
    id SERIAL PRIMARY KEY,
    title VARCHAR(200) NOT NULL,
    message TEXT NOT NULL,
    sender_wallet VARCHAR(42) NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Create indexes for admin_broadcast_messages table
CREATE INDEX IF NOT EXISTS idx_admin_broadcast_messages_active ON admin_broadcast_messages(is_active);
CREATE INDEX IF NOT EXISTS idx_admin_broadcast_messages_created_at ON admin_broadcast_messages(created_at);
CREATE INDEX IF NOT EXISTS idx_admin_broadcast_messages_sender ON admin_broadcast_messages(sender_wallet);

-- Enable RLS and create policies for admin_broadcast_messages
ALTER TABLE admin_broadcast_messages ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Allow all operations on admin_broadcast_messages" ON admin_broadcast_messages FOR ALL USING (true);

-- Create trigger for auto-updating updated_at on admin_broadcast_messages
CREATE TRIGGER update_admin_broadcast_messages_updated_at 
    BEFORE UPDATE ON admin_broadcast_messages 
    FOR EACH ROW 
    EXECUTE FUNCTION update_updated_at_column();

-- Enable RLS and create policies for new forum tables
ALTER TABLE forum_pending_rewards ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Allow all operations on forum_pending_rewards" ON forum_pending_rewards FOR ALL USING (true);

ALTER TABLE forum_reward_transactions ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Allow all operations on forum_reward_transactions" ON forum_reward_transactions FOR ALL USING (true);

-- Task Completion System Tables
CREATE TABLE IF NOT EXISTS task_completion_log (
    id SERIAL PRIMARY KEY,
    transaction_hash VARCHAR(66) NOT NULL,
    wallet_address VARCHAR(42) NOT NULL,
    task_id VARCHAR(50) NOT NULL,
    task_type VARCHAR(50) NOT NULL,
    reward_amount DECIMAL(18,8) NOT NULL,
    status VARCHAR(20) DEFAULT 'completed',
    verification_method VARCHAR(50),
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- User task progress table
CREATE TABLE IF NOT EXISTS user_task_progress (
    id SERIAL PRIMARY KEY,
    wallet_address VARCHAR(42) NOT NULL,
    task_id VARCHAR(50) NOT NULL,
    progress JSONB DEFAULT '{}',
    completed_at TIMESTAMP WITH TIME ZONE,
    last_attempt TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    streak_count INTEGER DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(wallet_address, task_id)
);

-- Create indexes for task completion system
CREATE INDEX IF NOT EXISTS idx_task_completion_log_wallet ON task_completion_log(wallet_address);
CREATE INDEX IF NOT EXISTS idx_task_completion_log_task_id ON task_completion_log(task_id);
CREATE INDEX IF NOT EXISTS idx_task_completion_log_timestamp ON task_completion_log(timestamp);
CREATE INDEX IF NOT EXISTS idx_user_task_progress_wallet ON user_task_progress(wallet_address);
CREATE INDEX IF NOT EXISTS idx_user_task_progress_task_id ON user_task_progress(task_id);

-- Enable RLS for task completion system
ALTER TABLE task_completion_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_task_progress ENABLE ROW LEVEL SECURITY;

-- Create policies for task completion system
CREATE POLICY "Allow all operations on task_completion_log" ON task_completion_log FOR ALL USING (true);
CREATE POLICY "Allow all operations on user_task_progress" ON user_task_progress FOR ALL USING (true);

-- 4. Enable Row Level Security (optional but recommended)
ALTER TABLE user_data ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE news_articles ENABLE ROW LEVEL SECURITY;
ALTER TABLE reloadly_orders ENABLE ROW LEVEL SECURITY;

-- 5. Create policies to allow read/write access (adjust as needed)
CREATE POLICY "Allow all operations on user_data" ON user_data FOR ALL USING (true);
CREATE POLICY "Allow all operations on user_sessions" ON user_sessions FOR ALL USING (true);
CREATE POLICY "Allow all operations on news_articles" ON news_articles FOR ALL USING (true);
CREATE POLICY "Allow all operations on reloadly_orders" ON reloadly_orders FOR ALL USING (true);

-- 6. Create function to auto-update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

-- 7. Create trigger for auto-updating updated_at
CREATE TRIGGER update_user_data_updated_at 
    BEFORE UPDATE ON user_data 
    FOR EACH ROW 
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_news_articles_updated_at 
    BEFORE UPDATE ON news_articles 
    FOR EACH ROW 
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_reloadly_orders_updated_at 
    BEFORE UPDATE ON reloadly_orders 
    FOR EACH ROW 
    EXECUTE FUNCTION update_updated_at_column();
"""

class SupabaseLogger:
    def __init__(self):
        self.client = supabase
        self.enabled = supabase_enabled

    def mask_wallet_address(self, wallet_address: str) -> str:
        """Mask wallet address for logging"""
        if not wallet_address or len(wallet_address) < 10:
            return wallet_address
        return wallet_address[:6] + "..." + wallet_address[-4:]

    def create_or_update_user(self, wallet_address: str, session_data: dict = None):
        """Create or update user in user_data table"""
        if not self.enabled:
            logger.warning("⚠️ Supabase not enabled - skipping user logging")
            return None

        try:
            # Check if user exists
            existing_user = self.client.table("user_data")\
                .select("*")\
                .eq("wallet_address", wallet_address)\
                .execute()

            if existing_user.data:
                # Update existing user
                user_id = existing_user.data[0]["id"]
                current_logins = existing_user.data[0].get("total_logins", 0)
                current_sessions = existing_user.data[0].get("total_sessions", 0)

                result = self.client.table("user_data")\
                    .update({
                        "last_login": datetime.now().isoformat(),
                        "total_logins": current_logins + 1,
                        "total_sessions": current_sessions + 1,
                        "user_agent": session_data.get("user_agent") if session_data else None,
                        "ip_address": session_data.get("ip_address") if session_data else None
                    })\
                    .eq("id", user_id)\
                    .execute()

                logger.info(f"✅ Updated user login #{current_logins + 1} for wallet: {wallet_address}")
            else:
                # Create new user
                user_record = {
                    "wallet_address": wallet_address,
                    "first_login": datetime.now().isoformat(),
                    "last_login": datetime.now().isoformat(),
                    "total_logins": 1,
                    "total_sessions": 1,
                    "ubi_verified": False,
                    "total_page_views": 0,
                    "user_agent": session_data.get("user_agent") if session_data else None,
                    "ip_address": session_data.get("ip_address") if session_data else None
                }

                result = self.client.table("user_data").insert(user_record).execute()
                logger.info(f"✅ Created new user for wallet: {wallet_address}")

            return result

        except Exception as e:
            logger.error(f"❌ Error creating/updating user: {e}")
            return None

    def log_activity(self, wallet_address: str, activity_type: str, session_id: str = None, 
                    page: str = None, success: bool = None, details: dict = None, 
                    session_data: dict = None):
        """Log any activity to user_sessions table"""
        if not self.enabled:
            return None

        try:
            # Ensure user exists in user_data before logging activity
            existing_user = self.client.table("user_data")\
                .select("wallet_address")\
                .eq("wallet_address", wallet_address)\
                .execute()

            if not existing_user.data:
                logger.warning(f"⚠️ User {wallet_address} not found in user_data, creating...")
                self.create_or_update_user(wallet_address, session_data)

            activity_record = {
                "wallet_address": wallet_address,
                "activity_type": activity_type,
                "session_id": session_id,
                "page": page,
                "success": success,
                "details": details or {},
                "ip_address": session_data.get("ip_address") if session_data else None,
                "user_agent": session_data.get("user_agent") if session_data else None,
                "timestamp": datetime.now().isoformat()
            }

            result = self.client.table("user_sessions").insert(activity_record).execute()
            logger.info(f"✅ Logged {activity_type} for wallet: {wallet_address}")
            return result

        except Exception as e:
            logger.error(f"❌ Error logging activity: {e}")
            return None

    def log_login(self, wallet_address: str, session_data: dict = None):
        """Log user login - combines user_data update and session logging"""
        session_id = f"session_{wallet_address}_{int(datetime.now().timestamp())}"

        # Update user data
        self.create_or_update_user(wallet_address, session_data)

        # Log login activity
        return self.log_activity(
            wallet_address=wallet_address,
            activity_type="login",
            session_id=session_id,
            success=True,
            details={"action": "user_login"},
            session_data=session_data
        )

    def log_verification_attempt(self, wallet_address: str, success: bool, details: dict = None):
        """Log UBI verification attempt"""
        # Ensure user exists before logging activity
        if success:
            self.create_or_update_user(wallet_address)

        result = self.log_activity(
            wallet_address=wallet_address,
            activity_type="verification_attempt",
            success=success,
            details=details or {}
        )

        # If verification successful, update user_data
        if success and self.enabled:
            try:
                self.client.table("user_data")\
                    .update({
                        "ubi_verified": True,
                        "verification_timestamp": datetime.now().isoformat()
                    })\
                    .eq("wallet_address", wallet_address)\
                    .execute()

                logger.info(f"✅ Updated UBI verification status for wallet: {wallet_address}")
            except Exception as e:
                logger.error(f"❌ Error updating verification status: {e}")

        return result

    def log_page_view(self, wallet_address: str, page: str, session_data: dict = None):
        """Log page view and update user_data page view count"""
        result = self.log_activity(
            wallet_address=wallet_address,
            activity_type="page_view",
            page=page,
            details={"page_accessed": page},
            session_data=session_data
        )

        # Update user_data page view count
        if self.enabled:
            try:
                user_data = self.client.table("user_data")\
                    .select("total_page_views")\
                    .eq("wallet_address", wallet_address)\
                    .execute()

                if user_data.data:
                    current_views = user_data.data[0].get("total_page_views", 0)
                    self.client.table("user_data")\
                        .update({"total_page_views": current_views + 1})\
                        .eq("wallet_address", wallet_address)\
                        .execute()
            except Exception as e:
                logger.error(f"❌ Error updating page view count: {e}")

        return result

    def log_logout(self, wallet_address: str, session_data: dict = None):
        """Log user logout"""
        return self.log_activity(
            wallet_address=wallet_address,
            activity_type="logout",
            details={"action": "user_logout"},
            session_data=session_data
        )

    def log_ubi_activity(self, wallet_address: str, ubi_details: dict = None):
        """Log UBI-related activity"""
        return self.log_activity(
            wallet_address=wallet_address,
            activity_type="ubi_activity",
            success=True,
            details=ubi_details or {}
        )

    def get_user_stats(self, wallet_address: str):
        """Get comprehensive user statistics"""
        if not self.enabled:
            return {}

        try:
            # Get user data
            user_result = self.client.table("user_data")\
                .select("*")\
                .eq("wallet_address", wallet_address)\
                .execute()

            # Get recent sessions
            sessions_result = self.client.table("user_sessions")\
                .select("*")\
                .eq("wallet_address", wallet_address)\
                .order("timestamp", desc=True)\
                .limit(20)\
                .execute()

            user_data = user_result.data[0] if user_result.data else {}
            sessions_data = sessions_result.data

            return {
                "user_info": user_data,
                "recent_activities": sessions_data,
                "activity_counts": self._count_activities(sessions_data)
            }

        except Exception as e:
            logger.error(f"❌ Error getting user stats: {e}")
            return {}

    def get_analytics_summary(self):
        """Get comprehensive analytics summary from Supabase data"""
        try:
            # Get total count of users using count query (more efficient)
            count_response = self.client.table("user_data").select("*", count="exact").execute()
            total_users = count_response.count if hasattr(count_response, 'count') else 0

            # Get verified users count
            verified_response = self.client.table("user_data").select("*", count="exact").eq("ubi_verified", True).execute()
            verified_users = verified_response.count if hasattr(verified_response, 'count') else 0

            # Calculate verification rate
            verification_rate = f"{(verified_users / total_users * 100):.1f}%" if total_users > 0 else "0%"

            # Get total page views by summing from all users
            # Use aggregation query if available, otherwise fetch all and sum
            try:
                # Fetch all users to calculate total page views (we need the actual data for this)
                all_users_response = self.client.table("user_data").select("total_page_views").execute()
                total_page_views = sum(user.get("total_page_views", 0) for user in all_users_response.data) if all_users_response.data else 0
            except Exception as pv_error:
                logger.warning(f"⚠️ Could not calculate total page views: {pv_error}")
                total_page_views = 0

            logger.info(f"📊 Analytics Summary: {total_users} total users, {verified_users} verified ({verification_rate})")

            return {
                "total_users": total_users,
                "verified_users": verified_users,
                "total_page_views": total_page_views,
                "verification_rate": verification_rate
            }
        except Exception as e:
            logger.error(f"❌ Error getting analytics summary: {e}")
            return {
                "total_users": 0,
                "verified_users": 0,
                "total_page_views": 0,
                "verification_rate": "0%"
            }

    def get_ubi_statistics(self):
        """Get real UBI statistics from Supabase data"""
        try:
            from datetime import datetime, timedelta

            # Get total verified users count more efficiently
            verified_response = self.client.table("user_data").select("*", count="exact").eq("ubi_verified", True).execute()
            total_verified = verified_response.count if hasattr(verified_response, 'count') else (len(verified_response.data) if verified_response.data else 0)

            # Get today's logins as proxy for active claims
            today = datetime.now().strftime("%Y-%m-%d")
            today_sessions_response = self.client.table("user_sessions").select("*", count="exact").gte("timestamp", today).execute()
            daily_activity = today_sessions_response.count if hasattr(today_sessions_response, 'count') else (len(today_sessions_response.data) if today_sessions_response.data else 0)

            # Calculate growth (compare with week ago)
            week_ago = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
            week_sessions_response = self.client.table("user_sessions").select("*", count="exact").gte("timestamp", week_ago).execute()
            weekly_activity = week_sessions_response.count if hasattr(week_sessions_response, 'count') else (len(week_sessions_response.data) if week_sessions_response.data else 0)

            growth_rate = f"+{((daily_activity / max(weekly_activity/7, 1) - 1) * 100):.0f}% this week" if weekly_activity > 0 else "New platform"

            # Estimate daily pool based on verified users (typical UBI is ~100 G$ per user)
            estimated_daily_pool = total_verified * 100
            avg_claim = 100  # Typical G$ UBI amount

            return {
                "total_verified_users": f"{total_verified:,}",
                "daily_ubi_claims": f"~{daily_activity}",
                "growth_rate": growth_rate,
                "top_countries": ["Philippines", "Nigeria", "Brazil", "India", "Kenya"],  # This would need geo data
                "daily_pool_g": f"{estimated_daily_pool:,} G$",
                "avg_claim_amount": f"{avg_claim} G$",
                "claims_today": str(daily_activity)
            }
        except Exception as e:
            logger.error(f"❌ Error getting UBI statistics: {e}")
            return {
                "total_verified_users": "Error loading",
                "daily_ubi_claims": "Error loading", 
                "growth_rate": "Error loading",
                "top_countries": ["Error loading"],
                "daily_pool_g": "Error loading",
                "avg_claim_amount": "Error loading",
                "claims_today": "Error loading"
            }

    def _count_activities(self, sessions_data: list):
        """Helper function to count different activity types"""
        counts = {}
        for session in sessions_data:
            activity_type = session.get("activity_type", "unknown")
            counts[activity_type] = counts.get(activity_type, 0) + 1
        return counts

    def get_learn_earn_earnings(self, wallet_address: str) -> float:
        """Get total Learn & Earn earnings for a user"""
        try:
            if not self.enabled:
                return 0.0

            masked_wallet = self.mask_wallet_address(wallet_address)
            logger.info(f"🔍 Fetching Learn & Earn earnings for wallet: {masked_wallet}")

            # Fetch total earnings from the forum_pending_rewards table
            # The 'total_earned' column in this table should store the cumulative earnings.
            response = self.client.table("forum_pending_rewards")\
                .select("total_earned")\
                .eq("wallet_address", wallet_address)\
                .execute()

            if response.data and len(response.data) > 0:
                earnings = response.data[0].get("total_earned", 0.0)
                logger.info(f"✅ Found Learn & Earn earnings for {masked_wallet}: {earnings}")
                return float(earnings)
            else:
                logger.info(f"ℹ️ No Learn & Earn earnings found for {masked_wallet}. Assuming 0.")
                return 0.0

        except Exception as e:
            masked_wallet = self.mask_wallet_address(wallet_address) if wallet_address else "unknown"
            logger.error(f"❌ Error fetching Learn & Earn earnings for {masked_wallet}: {e}")
            return 0.0

def safe_supabase_operation(operation, fallback_result=None, operation_name="database operation"):
    """
    Safely execute a Supabase operation with error handling

    Args:
        operation: Lambda function containing the Supabase operation
        fallback_result: Value to return if operation fails
        operation_name: Name of the operation for logging

    Returns:
        Result of operation or fallback_result if it fails
    """
    try:
        return operation()
    except Exception as e:
        logger.error(f"❌ Error in {operation_name}: {e}")
        return fallback_result

def get_supabase_client(retries=3):
    """Get Supabase client instance with retry logic"""
    global supabase_enabled
    if supabase_enabled and supabase:
        return supabase

    # If client failed to initialize, try to reconnect
    if retries > 0 and SUPABASE_URL and SUPABASE_KEY:
        try:
            time.sleep(1)  # Brief delay before retry
            # Re-initialize the client
            return get_supabase_client(retries - 1)
        except:
            pass

    return None

def log_admin_action(admin_wallet: str, action_type: str, action_details: dict = None, target_wallet: str = None):
    """Log admin actions to database"""
    try:
        supabase = get_supabase_client()
        if not supabase:
            return

        from datetime import datetime
        action_data = {
            'admin_wallet': admin_wallet,
            'action_type': action_type,
            'action_details': action_details or {},
            'target_wallet': target_wallet,
            'created_at': datetime.utcnow().isoformat()
        }

        supabase.table('admin_actions_log').insert(action_data).execute()
        logger.info(f"✅ Logged admin action: {action_type} by {admin_wallet[:8]}...")
    except Exception as e:
        logger.error(f"❌ Error logging admin action: {e}")

def is_admin(wallet_address: str) -> bool:
    """Check if wallet address is an admin"""
    try:
        supabase = get_supabase_client()
        if not supabase:
            return False

        result = supabase.table('user_data')\
            .select('is_admin')\
            .eq('wallet_address', wallet_address)\
            .execute()

        if result.data and len(result.data) > 0:
            return result.data[0].get('is_admin', False)

        return False
    except Exception as e:
        logger.error(f"❌ Error checking admin status: {e}")
        return False

def set_admin_status(wallet_address: str, is_admin_status: bool) -> dict:
    """Set admin status for a user"""
    try:
        supabase = get_supabase_client()
        if not supabase:
            return {"success": False, "error": "Database not available"}

        result = supabase.table('user_data')\
            .update({'is_admin': is_admin_status})\
            .eq('wallet_address', wallet_address)\
            .execute()

        if result.data:
            logger.info(f"✅ Admin status set for {wallet_address[:8]}...: {is_admin_status}")
            return {"success": True}
        else:
            return {"success": False, "error": "User not found"}
    except Exception as e:
        logger.error(f"❌ Error setting admin status: {e}")
        return {"success": False, "error": str(e)}

# Global logger instance
supabase_logger = SupabaseLogger()

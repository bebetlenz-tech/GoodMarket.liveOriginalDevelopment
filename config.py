

"""
Application Configuration
"""
import os

# Production domain configuration
PRODUCTION_DOMAIN = os.getenv('PRODUCTION_DOMAIN', 'https://goodmarket.live')

# Use production domain for external links (referrals, shares, etc.)
# Use local domain for internal API calls
def get_share_url_base():
    """Get base URL for shareable links (referrals, invites, etc.)"""
    return PRODUCTION_DOMAIN

def get_api_url_base():
    """Get base URL for API calls (always use current origin)"""
    return ''  # Empty string uses relative URLs

# ============================
# Community Stories Settings
# ============================
COMMUNITY_STORIES_CONFIG = {
    # Reward amounts (in G$)
    'LOW_REWARD': 2000.0,  # Text post
    'HIGH_REWARD': 5000.0,  # Video post (min. 30 seconds)

    # Requirements
    'REQUIRED_MENTIONS': '@gooddollarorg @GoodDollarTeam',
    'MIN_VIDEO_DURATION': 30,  # seconds

    # Participation window
    'WINDOW_START_DAY': 26,  # Day of month (1-31)
    'WINDOW_END_DAY': 30,    # Day of month (1-31)
    'WINDOW_START_HOUR': 0,  # UTC hour (0-23)
    'WINDOW_START_MINUTE': 0,
    'WINDOW_END_HOUR': 23,
    'WINDOW_END_MINUTE': 59,

    # Rules
    'DESCRIPTION': {
        'earn_title': '💰 Earn G$ by sharing our story:',
        'requirements_title': '📋 Requirements:',
        'schedule_title': '📅 Participation Schedule:',
        'requirements': [
            'Must use hashtags: @gooddollarorg @GoodDollarTeam',
            'Post must be public',
            'Original content only'
        ],
        'schedule_notes': [
            'Opens: 26th of each month at 12:00 AM UTC',
            'Closes: 30th of each month at 11:59 PM UTC',
            'Duration: 5 days only each month',
            'After reward: Blocked until next 26th'
        ],
        'warning': '⚠️ Late submissions after 30th are NOT accepted!'
    }
}

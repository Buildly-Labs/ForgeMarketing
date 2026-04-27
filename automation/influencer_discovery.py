#!/usr/bin/env python3
"""
Social Media Influencer Discovery System
========================================

Comprehensive influencer discovery across all major social platforms:
- YouTube, TikTok, Instagram, Twitter/X, Bluesky, LinkedIn
- Brand-specific targeting based on keywords and engagement
- Automated profile creation with reach metrics
- Multi-platform link discovery and verification
- Filterable reports with outreach recommendations

Features:
- Platform-specific search strategies
- Engagement rate calculation
- Audience size estimation  
- Content analysis for brand alignment
- Contact information extraction
- Outreach template generation
"""

import asyncio
import aiohttp
import sqlite3
import json
import logging
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Set, Any, Tuple
from dataclasses import dataclass, asdict
from urllib.parse import urlparse, urljoin
import sys

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@dataclass
class SocialMediaProfile:
    """Social media profile data"""
    platform: str
    username: str
    display_name: str
    profile_url: str
    verified: bool = False
    followers: int = 0
    following: int = 0
    posts_count: int = 0
    engagement_rate: float = 0.0
    bio: str = ""
    location: str = ""
    website: str = ""
    email: str = ""

@dataclass
class PodcastProfile:
    """Podcast-specific profile data"""
    name: str
    host_name: str
    description: str
    rss_feed: str
    website: str = ""
    email: str = ""
    guest_application_url: str = ""
    episode_count: int = 0
    average_rating: float = 0.0
    total_reviews: int = 0
    categories: List[str] = None
    release_frequency: str = ""  # weekly, daily, etc.
    youtube_channel: str = ""
    spotify_url: str = ""
    apple_podcasts_url: str = ""
    social_links: Dict[str, str] = None
    last_episode_date: str = ""
    
    def __post_init__(self):
        if self.categories is None:
            self.categories = []
        if self.social_links is None:
            self.social_links = {}

@dataclass 
class InfluencerProfile:
    """Complete influencer profile across platforms"""
    name: str
    primary_platform: str
    niche: str
    brand_alignment_score: float
    total_reach: int
    avg_engagement_rate: float
    contact_email: str = ""
    website: str = ""
    location: str = ""
    bio_summary: str = ""
    content_themes: List[str] = None
    social_profiles: Dict[str, SocialMediaProfile] = None
    podcast_profile: PodcastProfile = None
    outreach_notes: str = ""
    discovery_date: str = ""
    last_updated: str = ""
    
    def __post_init__(self):
        if self.content_themes is None:
            self.content_themes = []
        if self.social_profiles is None:
            self.social_profiles = {}

# Brand-specific influencer search strategies
BRAND_INFLUENCER_STRATEGIES = {
    'foundry': {
        'name': 'First City Foundry',
        'focus': 'startup incubation, entrepreneurship, business growth',
        'target_niches': ['entrepreneurship', 'startup', 'business', 'innovation', 'leadership'],
        'keywords': [
            'startup founder', 'entrepreneur', 'business coach', 'startup mentor',
            'venture capital', 'startup tips', 'business growth', 'innovation',
            'startup journey', 'founder story', 'business advice', 'entrepreneurship'
        ],
        'hashtags': [
            '#entrepreneur', '#startup', '#founder', '#business', '#innovation',
            '#startuplife', '#entrepreneurship', '#businesstips', '#startupadvice'
        ],
        'podcast_keywords': [
            'entrepreneur podcast', 'startup podcast', 'business podcast', 'founder interview',
            'entrepreneurship show', 'business leaders', 'startup stories', 'venture capital podcast'
        ],
        'bluesky_keywords': [
            'startup founder', 'entrepreneurship', 'business growth', 'venture capital', 'startup mentor'
        ],
        'mastodon_hashtags': [
            '#Entrepreneur', '#Startup', '#Founder', '#Business', '#Innovation', '#VentureCapital'
        ],
        'min_followers': 100,  # Lowered from 1000 to find smaller engaged creators
        'target_engagement': 2.0
    },
    'buildly': {
        'name': 'Buildly',
        'focus': 'low-code platforms, automation, digital transformation',
        'target_niches': ['nocode', 'lowcode', 'automation', 'productivity', 'saas'],
        'keywords': [
            'no code', 'low code', 'automation', 'workflow', 'productivity tools',
            'digital transformation', 'business automation', 'app builder',
            'workflow automation', 'process optimization', 'saas tools'
        ],
        'hashtags': [
            '#nocode', '#lowcode', '#automation', '#productivity', '#saas',
            '#digitaltransformation', '#workflow', '#businessautomation'
        ],
        'podcast_keywords': [
            'no code podcast', 'automation podcast', 'productivity podcast', 'saas podcast',
            'digital transformation show', 'workflow automation', 'business automation podcast'
        ],
        'bluesky_keywords': [
            'no-code', 'automation', 'productivity', 'workflow tools', 'digital transformation'
        ],
        'mastodon_hashtags': [
            '#NoCode', '#LowCode', '#Automation', '#ProductivityTools', '#DigitalTransformation'
        ],
        'min_followers': 100,  # Lowered from 500 to find smaller engaged creators
        'target_engagement': 3.0
    },
    'openbuild': {
        'name': 'Open Build',
        'focus': 'developer education, coding, open source',
        'target_niches': ['programming', 'coding', 'development', 'opensource', 'tech'],
        'keywords': [
            'coding', 'programming', 'developer', 'software development',
            'web development', 'open source', 'coding tutorial', 'programming tips',
            'learn to code', 'developer tools', 'coding bootcamp', 'tech education'
        ],
        'hashtags': [
            '#coding', '#programming', '#developer', '#webdev', '#opensource',
            '#javascript', '#python', '#react', '#nodejs', '#github'
        ],
        'podcast_keywords': [
            'programming podcast', 'coding podcast', 'developer podcast', 'tech podcast',
            'software development show', 'web development podcast', 'open source podcast'
        ],
        'min_followers': 100,  # Lowered from 1000 to find smaller engaged creators  
        'target_engagement': 4.0
    },
    'open_build': {
        'name': 'Open Build',
        'focus': 'developer education, coding, open source',
        'target_niches': ['programming', 'coding', 'development', 'opensource', 'tech'],
        'keywords': [
            'coding', 'programming', 'developer', 'software development',
            'web development', 'open source', 'coding tutorial', 'programming tips',
            'learn to code', 'developer tools', 'coding bootcamp', 'tech education'
        ],
        'hashtags': [
            '#coding', '#programming', '#developer', '#webdev', '#opensource',
            '#javascript', '#python', '#react', '#nodejs', '#github'
        ],
        'bluesky_keywords': [
            'programming', 'coding', 'web development', 'open source', 'developer tools'
        ],
        'mastodon_hashtags': [
            '#Programming', '#Coding', '#WebDev', '#OpenSource', '#JavaScript', '#Python'
        ],
        'podcast_keywords': [
            'programming podcast', 'coding podcast', 'developer podcast', 'tech podcast',
            'software development show', 'web development podcast', 'open source podcast'
        ],
        'min_followers': 100,  # Lowered from 1000 to find smaller engaged creators
        'target_engagement': 4.0
    },
    'radical_therapy': {
        'name': 'Radical Therapy for Software Teams',
        'focus': 'software development process innovation, remote team management, developer mental health, team collaboration',
        'description': 'A new process for software development and remote team management focusing on psychological safety, transparent communication, and sustainable development practices',
        'target_niches': [
            'software development', 'remote work', 'team management', 'developer experience', 
            'agile methodology', 'team collaboration', 'developer mental health', 'software processes',
            'remote teams', 'software leadership', 'engineering culture', 'developer productivity'
        ],
        'keywords': [
            'software development process', 'remote team management', 'developer experience',
            'agile methodology', 'team collaboration', 'software leadership', 'engineering culture',
            'developer mental health', 'software teams', 'remote work', 'development workflow',
            'team dynamics', 'software process improvement', 'developer productivity', 
            'engineering management', 'software team culture', 'remote software teams',
            'development practices', 'team communication', 'software project management'
        ],
        'hashtags': [
            '#SoftwareDevelopment', '#RemoteWork', '#TeamManagement', '#DeveloperExperience',
            '#AgileMethodology', '#EngineeringCulture', '#SoftwareLeadership', '#RemoteTeams',
            '#DeveloperProductivity', '#SoftwareProcess', '#TeamCollaboration', '#DevLife'
        ],
        'bluesky_keywords': [
            'software development process', 'remote team management', 'developer experience', 
            'engineering leadership', 'software team culture', 'remote software development',
            'agile methodology', 'developer productivity', 'software process innovation'
        ],
        'mastodon_hashtags': [
            '#SoftwareDevelopment', '#RemoteWork', '#TeamManagement', '#DeveloperExperience',
            '#EngineeringCulture', '#SoftwareLeadership', '#AgileMethodology', '#RemoteTeams'
        ],
        'podcast_keywords': [
            'software development podcast', 'remote work podcast', 'engineering leadership podcast',
            'developer experience podcast', 'team management podcast', 'software process podcast',
            'remote teams podcast', 'engineering culture podcast', 'software leadership show',
            'developer productivity podcast', 'agile methodology podcast', 'software team podcast'
        ],
        'min_followers': 50,  # Lower threshold to find engaged micro-influencers
        'target_engagement': 3.0
    },
    'oregonsoftware': {
        'name': 'Oregon Software',
        'focus': 'custom software development, consulting, regional business',
        'target_niches': ['webdevelopment', 'software', 'consulting', 'business', 'technology'],
        'keywords': [
            'web development', 'software development', 'custom software',
            'business technology', 'software consulting', 'app development',
            'digital solutions', 'tech consulting', 'software agency'
        ],
        'hashtags': [
            '#webdevelopment', '#softwaredevelopment', '#consulting', '#technology',
            '#customsoftware', '#webdesign', '#appdevelopment', '#digitalsolutions'
        ],
        'bluesky_keywords': [
            'software consulting', 'web development', 'custom software solutions', 'business technology', 'digital transformation'
        ],
        'mastodon_hashtags': [
            '#WebDevelopment', '#SoftwareDevelopment', '#Consulting', '#Technology', '#CustomSoftware'
        ],
        'podcast_keywords': [
            'software development podcast', 'web development podcast', 'tech consulting show',
            'business technology podcast', 'custom software podcast', 'digital solutions podcast'
        ],
        'min_followers': 50,  # Lowered from 250 to find smaller engaged creators
        'target_engagement': 3.0
    }
}

def add_brand_strategy(brand_key: str, brand_config: Dict[str, Any]) -> None:
    """
    Add or update a brand strategy configuration
    
    Usage:
        add_brand_strategy('my_brand', {
            'name': 'My Brand Name',
            'focus': 'What the brand focuses on',
            'description': 'Detailed description of the brand and its mission',
            'target_niches': ['niche1', 'niche2'],
            'keywords': ['keyword1', 'keyword2'],
            'hashtags': ['#hashtag1', '#hashtag2'],
            'podcast_keywords': ['podcast search terms'],
            'bluesky_keywords': ['bluesky search terms'],
            'mastodon_hashtags': ['#mastodon', '#hashtags'],
            'min_followers': 100,
            'target_engagement': 3.0
        })
    """
    BRAND_INFLUENCER_STRATEGIES[brand_key] = brand_config
    logger.info(f"✅ Added/updated brand strategy for '{brand_key}': {brand_config['name']}")

def list_brand_strategies() -> Dict[str, str]:
    """List all configured brand strategies"""
    return {key: config['name'] for key, config in BRAND_INFLUENCER_STRATEGIES.items()}


_BRAND_KEYWORD_STOPWORDS = {
    'and', 'for', 'the', 'with', 'from', 'that', 'this', 'into', 'your',
    'our', 'their', 'about', 'brand', 'company', 'business', 'services',
    'service', 'platform', 'startup', 'solution', 'solutions'
}


def _normalize_brand_key(value: str) -> str:
    """Normalize brand identifiers for resilient matching."""
    if not value:
        return ''
    normalized = re.sub(r'[^a-z0-9]+', '_', value.lower().strip())
    return normalized.strip('_')


def _load_dashboard_brand(brand_key: str) -> Optional[Dict[str, str]]:
    """Load a dashboard brand directly from the SQLite brand catalog."""
    db_path = project_root / 'data' / 'marketing_dashboard.db'
    if not db_path.exists():
        return None

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT name, display_name, description, website_url
            FROM brands
            WHERE is_active = 1
            """
        ).fetchall()

        requested_raw = (brand_key or '').strip().lower()
        requested_normalized = _normalize_brand_key(brand_key)

        for row in rows:
            row_dict = dict(row)
            row_name = (row_dict.get('name') or '').strip()
            row_display = (row_dict.get('display_name') or '').strip()

            candidates = {
                row_name.lower(),
                row_display.lower(),
                _normalize_brand_key(row_name),
                _normalize_brand_key(row_display),
            }

            if requested_raw in candidates or requested_normalized in candidates:
                return row_dict

        return None
    finally:
        conn.close()


def _build_dashboard_brand_keywords(brand_row: Dict[str, str]) -> List[str]:
    """Create a small keyword set for brands added through the dashboard."""
    parts = [
        brand_row.get('display_name', ''),
        brand_row.get('name', '').replace('_', ' '),
        brand_row.get('description', ''),
    ]

    website_url = brand_row.get('website_url', '')
    if website_url:
        hostname = urlparse(website_url).netloc.lower().replace('www.', '')
        parts.extend(re.split(r'[^a-z0-9]+', hostname))

    keywords: List[str] = []
    seen: Set[str] = set()
    for token in re.findall(r'[a-zA-Z][a-zA-Z0-9\-]{2,}', ' '.join(parts).lower()):
        if token in _BRAND_KEYWORD_STOPWORDS or token in seen:
            continue
        seen.add(token)
        keywords.append(token)

    display_name = brand_row.get('display_name', '').strip()
    if display_name and display_name.lower() not in seen:
        keywords.insert(0, display_name.lower())

    brand_name = brand_row.get('name', '').replace('_', ' ').strip()
    if brand_name and brand_name.lower() not in seen:
        keywords.insert(1, brand_name.lower())

    return keywords[:12] or [brand_row.get('name', 'brand')]


def ensure_brand_strategy(brand_key: str) -> Optional[Dict[str, Any]]:
    """Return an existing strategy or synthesize one from dashboard brand data."""
    brand_key_normalized = _normalize_brand_key(brand_key)
    strategy = BRAND_INFLUENCER_STRATEGIES.get(brand_key)
    if not strategy and brand_key_normalized:
        strategy = BRAND_INFLUENCER_STRATEGIES.get(brand_key_normalized)
    if strategy:
        return strategy

    brand_row = _load_dashboard_brand(brand_key)
    if not brand_row:
        return None

    keywords = _build_dashboard_brand_keywords(brand_row)
    hashtags = [
        f"#{re.sub(r'[^a-zA-Z0-9]', '', keyword.title())}"
        for keyword in keywords[:8]
        if keyword
    ]
    brand_config = {
        'name': brand_row.get('display_name') or brand_key.replace('_', ' ').title(),
        'focus': brand_row.get('description') or f"Growth and discovery for {brand_key}",
        'description': brand_row.get('description') or '',
        'target_niches': keywords[:6],
        'keywords': keywords,
        'hashtags': hashtags,
        'bluesky_keywords': keywords[:6],
        'mastodon_hashtags': hashtags[:5],
        'podcast_keywords': [f"{keyword} podcast" for keyword in keywords[:6]],
        'min_followers': 50,
        'target_engagement': 2.0,
    }
    canonical_brand_key = _normalize_brand_key(brand_row.get('name') or brand_key)
    add_brand_strategy(canonical_brand_key, brand_config)
    if brand_key and brand_key != canonical_brand_key:
        add_brand_strategy(brand_key, brand_config)
    if brand_key_normalized and brand_key_normalized != canonical_brand_key:
        add_brand_strategy(brand_key_normalized, brand_config)
    return brand_config

class InfluencerDatabase:
    """Database manager for influencer profiles"""
    
    def __init__(self, db_path: str = "data/influencer_discovery.db"):
        self.db_path = Path(project_root) / db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.init_database()
    
    def init_database(self):
        """Initialize influencer database schema"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Influencers table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS influencers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                primary_platform TEXT NOT NULL,
                niche TEXT NOT NULL,
                brand TEXT NOT NULL,
                brand_alignment_score REAL DEFAULT 0.0,
                total_reach INTEGER DEFAULT 0,
                avg_engagement_rate REAL DEFAULT 0.0,
                contact_email TEXT,
                website TEXT,
                location TEXT,
                bio_summary TEXT,
                content_themes TEXT,  -- JSON array
                outreach_notes TEXT,
                discovery_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                contacted BOOLEAN DEFAULT FALSE,
                response_received BOOLEAN DEFAULT FALSE,
                deleted BOOLEAN DEFAULT FALSE,
                UNIQUE(name, primary_platform, brand)
            )
        """)
        
        # Add deleted column to existing table if it doesn't exist
        try:
            cursor.execute("ALTER TABLE influencers ADD COLUMN deleted BOOLEAN DEFAULT FALSE")
        except sqlite3.OperationalError:
            # Column already exists
            pass
        
        # Social profiles table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS social_profiles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                influencer_id INTEGER,
                platform TEXT NOT NULL,
                username TEXT NOT NULL,
                display_name TEXT,
                profile_url TEXT NOT NULL,
                verified BOOLEAN DEFAULT FALSE,
                followers INTEGER DEFAULT 0,
                following INTEGER DEFAULT 0,
                posts_count INTEGER DEFAULT 0,
                engagement_rate REAL DEFAULT 0.0,
                bio TEXT,
                location TEXT,
                website TEXT,
                email TEXT,
                last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (influencer_id) REFERENCES influencers (id),
                UNIQUE(influencer_id, platform)
            )
        """)
        
        # Discovery sessions table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS discovery_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                brand TEXT NOT NULL,
                platform TEXT NOT NULL,
                search_query TEXT,
                results_count INTEGER DEFAULT 0,
                session_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                duration_seconds INTEGER DEFAULT 0,
                success BOOLEAN DEFAULT TRUE,
                error_message TEXT
            )
        """)
        
        # Outreach tracking table  
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS influencer_outreach (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                influencer_id INTEGER,
                brand TEXT NOT NULL,
                outreach_type TEXT,  -- email, dm, comment, etc.
                platform TEXT,
                message_template TEXT,
                sent_date TIMESTAMP,
                response_date TIMESTAMP,
                response_type TEXT,  -- positive, negative, no_response
                notes TEXT,
                FOREIGN KEY (influencer_id) REFERENCES influencers (id)
            )
        """)
        
        # Podcast-specific information table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS podcast_profiles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                influencer_id INTEGER,
                rss_feed TEXT,
                guest_application_url TEXT,
                episode_count INTEGER DEFAULT 0,
                average_rating REAL DEFAULT 0.0,
                total_reviews INTEGER DEFAULT 0,
                categories TEXT,  -- JSON array of categories
                release_frequency TEXT,
                youtube_channel TEXT,
                spotify_url TEXT,
                apple_podcasts_url TEXT,
                social_links TEXT,  -- JSON object of social links
                last_episode_date TEXT,
                accepts_guests BOOLEAN DEFAULT 1,
                created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (influencer_id) REFERENCES influencers (id)
            )
        """)
        
        conn.commit()
        conn.close()
        logger.info("✅ Influencer discovery database initialized")

class PlatformSearcher:
    """Base class for platform-specific influencer discovery"""
    
    def __init__(self, platform_name: str):
        self.platform = platform_name
        self.session = None
    
    async def __aenter__(self):
        import ssl
        # Create SSL context that doesn't verify certificates (for development)
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE
        
        connector = aiohttp.TCPConnector(ssl=ssl_context)
        self.session = aiohttp.ClientSession(
            connector=connector,
            timeout=aiohttp.ClientTimeout(total=30),
            headers={'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'}
        )
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
    
    async def search_influencers(self, brand: str, keywords: List[str], max_results: int = 10) -> List[SocialMediaProfile]:
        """Search for influencers on this platform - to be implemented by subclasses"""
        raise NotImplementedError
    
    def extract_profile_data(self, profile_html: str) -> Dict[str, Any]:
        """Extract profile data from HTML - to be implemented by subclasses"""
        raise NotImplementedError

class YouTubeSearcher(PlatformSearcher):
    """YouTube influencer discovery"""
    
    def __init__(self):
        super().__init__("youtube")
    
    async def search_influencers(self, brand: str, keywords: List[str], max_results: int = 50) -> List[SocialMediaProfile]:
        """Search YouTube for real influencers using YouTube Data API and web scraping"""
        profiles = []
        strategy = BRAND_INFLUENCER_STRATEGIES.get(brand, {})
        
        logger.info(f"🔍 Searching YouTube for {brand} influencers...")
        
        # Method 1: Try YouTube Data API (if API key available)  
        youtube_profiles = await self._search_youtube_api(keywords, max_results)
        
        # Method 2: If API fails, fall back to RSS/public data scraping
        if not youtube_profiles:
            youtube_profiles = await self._search_youtube_rss(keywords, max_results)
        
        # Method 3: If both fail, search via Google for YouTube channels
        if not youtube_profiles:
            youtube_profiles = await self._search_youtube_via_google(keywords, max_results)
        
        # Method 4: DISABLED - GitHub method produces inaccurate subscriber estimates  
        # The GitHub developer method creates fake YouTube profiles with inflated subscriber counts
        # (up to 50k subscribers) based on GitHub followers, not real YouTube data
        # if not youtube_profiles and any(tech_keyword in ' '.join(keywords).lower() for tech_keyword in ['code', 'developer', 'programming', 'tech', 'software']):
        #     youtube_profiles = await self._search_github_developers_with_youtube(keywords, max_results)
        
        for channel_data in youtube_profiles[:max_results]:
            # Check if channel aligns with brand keywords
            if self._check_brand_alignment(channel_data, keywords, strategy):
                profile = SocialMediaProfile(
                    platform="youtube",
                    username=channel_data.get('username', channel_data.get('channel_id', '')),
                    display_name=channel_data.get('name', channel_data.get('title', 'Unknown')),
                    profile_url=channel_data.get('url', f"https://youtube.com/@{channel_data.get('username', '')}"),
                    verified=channel_data.get('verified', False),
                    followers=channel_data.get('subscribers', 0),
                    posts_count=channel_data.get('videos', 0),
                    engagement_rate=self._estimate_engagement_rate(channel_data.get('subscribers', 0)),
                    bio=channel_data.get('description', '')
                )
                profiles.append(profile)
        
        logger.info(f"✅ Found {len(profiles)} YouTube influencers for {brand}")
        return profiles
    
    async def _search_youtube_api(self, keywords: List[str], max_results: int) -> List[Dict]:
        """Search using YouTube Data API (if API key available)"""
        import os
        api_key = os.getenv('YOUTUBE_API_KEY')
        if not api_key:
            logger.info("📝 No YouTube API key found, skipping API search")
            return []
        
        try:
            search_query = ' OR '.join(keywords[:3])  # Use top 3 keywords
            url = f"https://www.googleapis.com/youtube/v3/search"
            params = {
                'key': api_key,
                'part': 'snippet',
                'type': 'channel',
                'q': search_query,
                'maxResults': max_results,
                'order': 'relevance'
            }
            
            async with self.session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    channels = []
                    
                    for item in data.get('items', []):
                        channel_id = item['snippet']['channelId']
                        
                        # Get channel details
                        channel_details = await self._get_youtube_channel_details(channel_id, api_key)
                        if channel_details:
                            channels.append(channel_details)
                    
                    logger.info(f"🎯 YouTube API found {len(channels)} channels")
                    return channels
                else:
                    logger.warning(f"YouTube API error: {response.status}")
        except Exception as e:
            logger.warning(f"YouTube API search failed: {e}")
        
        return []
    
    async def _get_youtube_channel_details(self, channel_id: str, api_key: str) -> Dict:
        """Get detailed channel information"""
        try:
            url = f"https://www.googleapis.com/youtube/v3/channels"
            params = {
                'key': api_key,
                'part': 'snippet,statistics',
                'id': channel_id
            }
            
            async with self.session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    if data.get('items'):
                        item = data['items'][0]
                        snippet = item['snippet']
                        stats = item['statistics']
                        
                        return {
                            'channel_id': channel_id,
                            'name': snippet['title'],
                            'username': snippet.get('customUrl', '').replace('@', ''),
                            'description': snippet.get('description', ''),
                            'subscribers': int(stats.get('subscriberCount', 0)),
                            'videos': int(stats.get('videoCount', 0)),
                            'views': int(stats.get('viewCount', 0)),
                            'url': f"https://youtube.com/channel/{channel_id}",
                            'verified': snippet.get('badges', []) != []
                        }
        except Exception as e:
            logger.warning(f"Failed to get YouTube channel details for {channel_id}: {e}")
        
        return None
    
    async def _search_youtube_rss(self, keywords: List[str], max_results: int) -> List[Dict]:
        """Search YouTube using RSS feeds and public data"""
        channels = []
        
        # Search via Google for YouTube channels
        try:
            for keyword in keywords[:3]:  # Limit to avoid rate limiting
                search_query = f"site:youtube.com/c/ OR site:youtube.com/user/ {keyword}"
                url = f"https://www.google.com/search"
                params = {
                    'q': search_query,
                    'num': 5,  # Limit results per keyword
                }
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
                }
                
                async with self.session.get(url, params=params, headers=headers) as response:
                    if response.status == 200:
                        html = await response.text()
                        # Extract YouTube channel URLs from search results
                        import re
                        channel_urls = re.findall(r'https://www\.youtube\.com/(?:c/|user/|channel/)([^/"&\s]+)', html)
                        
                        for url in channel_urls[:2]:  # Limit per keyword
                            channel_data = await self._scrape_youtube_channel_public_data(url)
                            if channel_data and len(channels) < max_results:
                                channels.append(channel_data)
                
                await asyncio.sleep(2)  # Rate limiting
                
        except Exception as e:
            logger.warning(f"YouTube RSS search failed: {e}")
        
        logger.info(f"🔍 RSS search found {len(channels)} YouTube channels")
        return channels
    
    async def _search_youtube_via_google(self, keywords: List[str], max_results: int) -> List[Dict]:
        """Search for YouTube channels via Google search"""
        channels = []
        
        try:
            search_query = f"YouTube channel {' '.join(keywords[:2])}"
            url = "https://www.google.com/search"
            params = {
                'q': search_query,
                'num': max_results * 2,  # Get more to filter
            }
            headers = {
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
            }
            
            async with self.session.get(url, params=params, headers=headers) as response:
                if response.status == 200:
                    html = await response.text()
                    # Parse search results for YouTube links
                    import re
                    from urllib.parse import unquote
                    
                    # Extract YouTube channel links from Google results
                    youtube_pattern = r'/url\?q=(https://www\.youtube\.com/[^&]+)'
                    matches = re.findall(youtube_pattern, html)
                    
                    for match in matches:
                        url = unquote(match)
                        if '/channel/' in url or '/c/' in url or '/@' in url:
                            channel_data = await self._extract_youtube_metadata_from_url(url)
                            if channel_data and len(channels) < max_results:
                                channels.append(channel_data)
                        
                        await asyncio.sleep(1)  # Rate limiting
                        
        except Exception as e:
            logger.warning(f"Google YouTube search failed: {e}")
        
        logger.info(f"🌐 Google search found {len(channels)} YouTube channels")
        return channels
    
    async def _scrape_youtube_channel_public_data(self, channel_identifier: str) -> Dict:
        """Scrape public YouTube channel data"""
        try:
            # Try different URL formats
            possible_urls = [
                f"https://www.youtube.com/c/{channel_identifier}",
                f"https://www.youtube.com/@{channel_identifier}",
                f"https://www.youtube.com/channel/{channel_identifier}",
                f"https://www.youtube.com/user/{channel_identifier}"
            ]
            
            for url in possible_urls:
                try:
                    async with self.session.get(url) as response:
                        if response.status == 200:
                            html = await response.text()
                            return self._parse_youtube_page(html, url)
                except:
                    continue
                    
        except Exception as e:
            logger.warning(f"Failed to scrape YouTube channel {channel_identifier}: {e}")
        
        return None
    
    async def _extract_youtube_metadata_from_url(self, url: str) -> Dict:
        """Extract YouTube channel metadata from URL"""
        try:
            async with self.session.get(url) as response:
                if response.status == 200:
                    html = await response.text()
                    return self._parse_youtube_page(html, url)
        except Exception as e:
            logger.warning(f"Failed to extract YouTube metadata from {url}: {e}")
        
        return None
    
    def _parse_youtube_page(self, html: str, url: str) -> Dict:
        """Parse YouTube channel page HTML for metadata"""
        try:
            import re
            import json
            
            # Extract channel name from title
            title_match = re.search(r'<title>([^<]+)', html)
            name = title_match.group(1).replace(' - YouTube', '') if title_match else 'Unknown'
            
            # Extract subscriber count (various formats)
            sub_patterns = [
                r'(\d+(?:\.\d+)?[KMB]?)\s*subscribers?',  # "123 subscribers" or "1.2K subscribers"
                r'"subscriberCountText":{"simpleText":"([^"]+)"',  # YouTube JSON data
                r'"subscriberCountText":{"runs":\[{"text":"([^"]+)"',  # Alternative JSON format
                r'(\d+(?:\.\d+)?[KMB]?)\s*subscriber',  # Without 's' at end
                r'content="([^"]*subscriber[^"]*)"',  # Meta content
                r'(\d+(?:,\d{3})*)\s*subscribers?'  # Full numbers with commas
            ]
            
            subscribers = 0
            sub_text_found = ""
            for i, pattern in enumerate(sub_patterns):
                match = re.search(pattern, html, re.IGNORECASE)
                if match:
                    sub_text = match.group(1)
                    subscribers = self._parse_subscriber_count(sub_text)
                    sub_text_found = f"Pattern {i+1}: '{sub_text}' -> {subscribers}"
                    if subscribers > 0:  # Only break if we got a valid count
                        break
            
            # Only log if we couldn't find subscribers and name is not empty  
            if subscribers == 0 and name and name != 'Unknown':
                logger.warning(f"No subscriber count found for YouTube channel: {name}")
            
            # Extract description/about
            desc_patterns = [
                r'"description":{"simpleText":"([^"]+)"',
                r'<meta name="description" content="([^"]*)"',
                r'"content":"([^"]+)","target"'
            ]
            
            description = ''
            for pattern in desc_patterns:
                match = re.search(pattern, html)
                if match:
                    description = match.group(1)
                    break
            
            # Extract username from URL or page
            username = ''
            if '/@' in url:
                username = url.split('/@')[-1].split('?')[0]
            elif '/c/' in url:
                username = url.split('/c/')[-1].split('?')[0]
            
            return {
                'name': name,
                'username': username,
                'description': description,
                'subscribers': subscribers,
                'url': url,
                'verified': 'verified' in html.lower() or 'checkmark' in html.lower(),
                'videos': self._extract_video_count(html)
            }
            
        except Exception as e:
            logger.warning(f"Failed to parse YouTube page: {e}")
            return None
    
    def _parse_subscriber_count(self, sub_text: str) -> int:
        """Convert subscriber text to number with improved parsing"""
        try:
            if not sub_text:
                return 0
                
            # Clean the text
            sub_text = str(sub_text).strip()
            sub_text = re.sub(r'\s*subscribers?\s*', '', sub_text, flags=re.IGNORECASE)
            sub_text = sub_text.replace(',', '').replace(' ', '')
            
            # Handle different formats
            sub_text_upper = sub_text.upper()
            
            if 'K' in sub_text_upper:
                num_str = sub_text_upper.replace('K', '')
                return int(float(num_str) * 1000)
            elif 'M' in sub_text_upper:
                num_str = sub_text_upper.replace('M', '')
                return int(float(num_str) * 1000000)
            elif 'B' in sub_text_upper:
                num_str = sub_text_upper.replace('B', '')
                return int(float(num_str) * 1000000000)
            else:
                # Try to extract just the number
                num_match = re.search(r'(\d+)', sub_text)
                if num_match:
                    return int(num_match.group(1))
                return 0
        except Exception as e:
            logger.warning(f"Failed to parse subscriber count '{sub_text}': {e}")
            return 0
    
    def _extract_video_count(self, html: str) -> int:
        """Extract video count from YouTube page"""
        try:
            import re
            patterns = [
                r'"videoCountText":{"runs":\[{"text":"([^"]+)"',
                r'(\d+) videos',
                r'"videoCount":"(\d+)"'
            ]
            
            for pattern in patterns:
                match = re.search(pattern, html)
                if match:
                    count_text = match.group(1).replace(',', '')
                    if count_text.isdigit():
                        return int(count_text)
            return 0
        except:
            return 0
    
    def _check_brand_alignment(self, channel_data: Dict, keywords: List[str], strategy: Dict) -> bool:
        """Check if channel aligns with brand strategy"""
        if not channel_data:
            return False
        
        # Minimum subscriber threshold
        min_followers = strategy.get('min_followers', 1000)
        if channel_data.get('subscribers', 0) < min_followers:
            return False
        
        # Check keyword alignment in description or name
        text_to_check = f"{channel_data.get('description', '')} {channel_data.get('name', '')}".lower()
        
        # Must match at least one keyword
        keyword_matches = sum(1 for keyword in keywords if keyword.lower() in text_to_check)
        return keyword_matches > 0
    
    async def _search_github_developers_with_youtube(self, keywords: List[str], max_results: int) -> List[Dict]:
        """Search GitHub for developers and find their YouTube channels"""
        channels = []
        
        try:
            # Search GitHub for developers with relevant skills
            for keyword in keywords[:2]:
                url = f"https://api.github.com/search/users"
                params = {
                    'q': f'{keyword} followers:>100',
                    'sort': 'followers',
                    'order': 'desc',
                    'per_page': 5
                }
                
                async with self.session.get(url, params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        
                        for user in data.get('items', []):
                            if len(channels) >= max_results:
                                break
                                
                            # Get user details to find social links
                            user_url = user['url']
                            async with self.session.get(user_url) as user_response:
                                if user_response.status == 200:
                                    user_data = await user_response.json()
                                    
                                    # Check if they have a blog/website that might link to YouTube
                                    blog = user_data.get('blog', '')
                                    bio = user_data.get('bio', '')
                                    
                                    # Create a profile based on GitHub data
                                    if user_data.get('followers', 0) > 100:  # Minimum threshold
                                        youtube_channel = self._create_youtube_profile_from_github(user_data, keyword)
                                        if youtube_channel:
                                            channels.append(youtube_channel)
                        
                        await asyncio.sleep(1)  # Rate limiting for GitHub API
                        
        except Exception as e:
            logger.warning(f"GitHub developer search failed: {e}")
        
        logger.info(f"🐙 Found {len(channels)} potential YouTube channels from GitHub developers")
        return channels
    
    def _create_youtube_profile_from_github(self, github_user: dict, keyword: str) -> dict:
        """Create a potential YouTube profile from GitHub developer data"""
        try:
            # Estimate potential YouTube metrics based on GitHub following
            github_followers = github_user.get('followers', 0)
            estimated_subscribers = min(github_followers * 2, 50000)  # Conservative estimate
            
            return {
                'name': github_user.get('name') or github_user.get('login'),
                'username': github_user.get('login'),
                'subscribers': estimated_subscribers,
                'description': f"Developer content creator • {github_user.get('bio', keyword)} • GitHub: {github_followers} followers",
                'url': f"https://youtube.com/@{github_user.get('login')}",  # Potential channel
                'verified': github_followers > 1000,
                'videos': max(20, github_followers // 100)  # Estimate based on activity
            }
        except:
            return None
    
    def _estimate_engagement_rate(self, subscribers: int) -> float:
        """Estimate engagement rate based on subscriber count"""
        if subscribers < 1000:
            return 8.0
        elif subscribers < 10000:
            return 6.0
        elif subscribers < 100000:
            return 4.0
        else:
            return 2.0

class InstagramSearcher(PlatformSearcher):
    """Instagram influencer discovery"""
    
    def __init__(self):
        super().__init__("instagram")
    
    async def search_influencers(self, brand: str, keywords: List[str], max_results: int = 50) -> List[SocialMediaProfile]:
        """Search Instagram for real influencers using multiple methods"""
        profiles = []
        strategy = BRAND_INFLUENCER_STRATEGIES.get(brand, {})
        
        logger.info(f"🔍 Searching Instagram for {brand} influencers...")
        
        # Method 1: Search via Google for Instagram profiles
        instagram_profiles = await self._search_instagram_via_google(keywords, max_results)
        
        # Method 2: Search Dev.to for tech content creators (for tech brands)
        if not instagram_profiles and any(tech_keyword in ' '.join(keywords).lower() for tech_keyword in ['code', 'developer', 'programming', 'tech', 'software']):
            instagram_profiles = await self._search_devto_creators(keywords, max_results)
        
        # Method 3: Search via hashtag analysis (if previous methods fail)
        if not instagram_profiles:
            instagram_profiles = await self._search_instagram_hashtags(keywords, max_results)
        
        # Method 3: Use Instagram Basic Display API (if available)
        if not instagram_profiles:
            instagram_profiles = await self._search_instagram_api(keywords, max_results)
        
        for profile_data in instagram_profiles[:max_results]:
            # Check alignment with brand
            if any(keyword.lower() in profile_data['bio'].lower() for keyword in keywords):
                profile = SocialMediaProfile(
                    platform="instagram",
                    username=profile_data['username'],
                    display_name=profile_data['display_name'],
                    profile_url=f"https://instagram.com/{profile_data['username']}",
                    verified=profile_data['verified'],
                    followers=profile_data['followers'],
                    following=profile_data['following'],
                    posts_count=profile_data['posts'],
                    engagement_rate=self._calculate_engagement_rate(profile_data['followers'], profile_data['posts']),
                    bio=profile_data['bio']
                )
                profiles.append(profile)
        
        logger.info(f"✅ Found {len(profiles)} Instagram influencers for {brand}")
        return profiles
    
    def _calculate_engagement_rate(self, followers: int, posts: int) -> float:
        """Calculate estimated engagement rate"""
        if followers < 1000:
            return 7.5
        elif followers < 10000:
            return 5.2
        elif followers < 100000:
            return 3.1
        else:
            return 1.8
    
    async def _search_instagram_via_google(self, keywords: List[str], max_results: int) -> List[Dict]:
        """Search for Instagram profiles via Google"""
        profiles = []
        
        try:
            for keyword in keywords[:2]:  # Limit to avoid rate limits
                search_query = f"site:instagram.com {keyword} influencer OR creator"
                url = "https://www.google.com/search"
                params = {
                    'q': search_query,
                    'num': max_results,
                }
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
                }
                
                async with self.session.get(url, params=params, headers=headers) as response:
                    if response.status == 200:
                        html = await response.text()
                        # Extract Instagram profile URLs
                        import re
                        from urllib.parse import unquote
                        
                        # Find Instagram profile URLs in search results
                        pattern = r'/url\?q=(https://www\.instagram\.com/[^/&\s]+)'
                        matches = re.findall(pattern, html)
                        
                        for match in matches:
                            url = unquote(match)
                            username = url.split('instagram.com/')[-1].split('?')[0]
                            if username and len(profiles) < max_results:
                                profile_data = await self._get_instagram_public_data(username)
                                if profile_data:
                                    profiles.append(profile_data)
                
                await asyncio.sleep(2)  # Rate limiting
                
        except Exception as e:
            logger.warning(f"Instagram Google search failed: {e}")
        
        logger.info(f"🌐 Found {len(profiles)} Instagram profiles via Google")
        return profiles
    
    async def _search_instagram_hashtags(self, keywords: List[str], max_results: int) -> List[Dict]:
        """Search Instagram via hashtag exploration"""
        profiles = []
        
        try:
            # Use hashtag-based discovery
            for keyword in keywords[:2]:
                hashtag = f"#{keyword.replace(' ', '').lower()}"
                # Search for posts with hashtags and extract profile links
                search_query = f"site:instagram.com/p/ {hashtag}"
                url = "https://www.google.com/search"
                params = {'q': search_query, 'num': 10}
                
                async with self.session.get(url, params=params) as response:
                    if response.status == 200:
                        html = await response.text()
                        # Extract usernames from post URLs
                        import re
                        
                        post_urls = re.findall(r'https://www\.instagram\.com/p/([^/\s"]+)', html)
                        # For each post, we'd need to get the author, but this is complex
                        # For now, we'll use a different approach
                        
                await asyncio.sleep(2)
                
        except Exception as e:
            logger.warning(f"Instagram hashtag search failed: {e}")
        
        return profiles
    
    async def _search_instagram_api(self, keywords: List[str], max_results: int) -> List[Dict]:
        """Search using Instagram Basic Display API (if available)"""
        import os
        access_token = os.getenv('INSTAGRAM_ACCESS_TOKEN')
        if not access_token:
            logger.info("📝 No Instagram API token found, skipping API search")
            return []
        
        # Instagram Basic Display API has very limited search capabilities
        # This is mainly for demonstration - real implementation would need Instagram Graph API
        return []
    
    async def _get_instagram_public_data(self, username: str) -> Dict:
        """Get public Instagram profile data"""
        try:
            url = f"https://www.instagram.com/{username}/"
            headers = {
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
            }
            
            async with self.session.get(url, headers=headers) as response:
                if response.status == 200:
                    html = await response.text()
                    return self._parse_instagram_profile(html, username)
                    
        except Exception as e:
            logger.warning(f"Failed to get Instagram data for @{username}: {e}")
        
        return None
    
    def _parse_instagram_profile(self, html: str, username: str) -> Dict:
        """Parse Instagram profile page for public data"""
        try:
            import re
            import json
            
            # Extract JSON data from page
            json_pattern = r'window\._sharedData = ({.*?});'
            match = re.search(json_pattern, html)
            
            if match:
                try:
                    data = json.loads(match.group(1))
                    user_data = data.get('entry_data', {}).get('ProfilePage', [{}])[0].get('graphql', {}).get('user', {})
                    
                    return {
                        'username': username,
                        'display_name': user_data.get('full_name', username),
                        'followers': user_data.get('edge_followed_by', {}).get('count', 0),
                        'following': user_data.get('edge_follow', {}).get('count', 0),
                        'posts': user_data.get('edge_owner_to_timeline_media', {}).get('count', 0),
                        'bio': user_data.get('biography', ''),
                        'verified': user_data.get('is_verified', False),
                        'url': f"https://instagram.com/{username}"
                    }
                except json.JSONDecodeError:
                    pass
            
            # Fallback: extract basic data from HTML
            title_match = re.search(r'<title>([^<]+)</title>', html)
            name = 'Unknown'
            if title_match:
                title_parts = title_match.group(1).split('(')
                if len(title_parts) > 1:
                    name = title_parts[0].strip()
            
            # Extract follower count from meta tags
            followers = 0
            follower_patterns = [
                r'(\d+(?:,\d+)*)\s+Followers',
                r'"edge_followed_by":{"count":(\d+)',
                r'followers_count":(\d+)'
            ]
            
            for pattern in follower_patterns:
                match = re.search(pattern, html)
                if match:
                    followers = int(match.group(1).replace(',', ''))
                    break
            
            return {
                'username': username,
                'display_name': name,
                'followers': followers,
                'bio': '',
                'verified': 'verified' in html.lower(),
                'url': f"https://instagram.com/{username}"
            }
            
        except Exception as e:
            logger.warning(f"Failed to parse Instagram profile {username}: {e}")
            return None
    
    async def _search_devto_creators(self, keywords: List[str], max_results: int) -> List[Dict]:
        """Search Dev.to for tech content creators — returns only profiles with verified Instagram links"""
        profiles = []
        
        try:
            for keyword in keywords[:2]:
                url = "https://dev.to/api/articles"
                params = {
                    'tag': keyword,
                    'top': 7,
                    'per_page': 10
                }
                
                async with self.session.get(url, params=params) as response:
                    if response.status == 200:
                        articles = await response.json()
                        
                        authors_seen = set()
                        
                        for article in articles:
                            if len(profiles) >= max_results:
                                break
                                
                            user = article.get('user', {})
                            username = user.get('username')
                            
                            if username and username not in authors_seen:
                                authors_seen.add(username)
                                
                                # Try to find their real Instagram profile via their website
                                website = user.get('website_url', '')
                                if website:
                                    instagram_handle = await self._find_instagram_from_website(website)
                                    if instagram_handle:
                                        profile_data = await self._get_instagram_public_data(instagram_handle)
                                        if profile_data:
                                            profiles.append(profile_data)
                
                await asyncio.sleep(1)
                
        except Exception as e:
            logger.warning(f"Dev.to search failed: {e}")
        
        logger.info(f"👩‍💻 Found {len(profiles)} verified Instagram profiles from Dev.to creators")
        return profiles
    
    async def _find_instagram_from_website(self, website_url: str) -> Optional[str]:
        """Check a website for Instagram links and return the handle if found"""
        try:
            async with self.session.get(website_url) as response:
                if response.status == 200:
                    html = await response.text()
                    import re
                    match = re.search(r'instagram\.com/([a-zA-Z0-9_.]+)', html)
                    if match:
                        return match.group(1)
        except Exception:
            pass
        return None

class LinkedInSearcher(PlatformSearcher):
    """LinkedIn influencer discovery via Google search"""
    
    def __init__(self):
        super().__init__("linkedin")
    
    async def search_influencers(self, brand: str, keywords: List[str], max_results: int = 50) -> List[SocialMediaProfile]:
        """Search LinkedIn for real thought leaders via Google"""
        profiles = []
        strategy = BRAND_INFLUENCER_STRATEGIES.get(brand, {})
        
        logger.info(f"🔍 Searching LinkedIn for {brand} thought leaders...")
        
        # Method 1: Search via Google for LinkedIn profiles
        linkedin_profiles = await self._search_linkedin_via_google(keywords, max_results)
        
        for profile_data in linkedin_profiles[:max_results]:
            # Check alignment with brand
            headline = profile_data.get('headline', '')
            if any(keyword.lower() in headline.lower() for keyword in keywords):
                profile = SocialMediaProfile(
                    platform="linkedin",
                    username=profile_data.get('username', ''),
                    display_name=profile_data.get('name', ''),
                    profile_url=profile_data.get('url', ''),
                    verified=False,
                    followers=profile_data.get('connections', 0),
                    posts_count=profile_data.get('posts', 0),
                    engagement_rate=self._estimate_linkedin_engagement(profile_data.get('connections', 0)),
                    bio=headline,
                    location=profile_data.get('location', '')
                )
                profiles.append(profile)
        
        if not profiles:
            logger.info(f"📝 No LinkedIn profiles found via search for {brand}")
        
        logger.info(f"✅ Found {len(profiles)} LinkedIn thought leaders for {brand}")
        return profiles
    
    async def _search_linkedin_via_google(self, keywords: List[str], max_results: int) -> List[Dict]:
        """Search for real LinkedIn profiles via Google"""
        profiles = []
        
        try:
            for keyword in keywords[:3]:
                search_query = f'site:linkedin.com/in/ "{keyword}"'
                url = "https://www.google.com/search"
                params = {
                    'q': search_query,
                    'num': max_results,
                }
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
                }
                
                async with self.session.get(url, params=params, headers=headers) as response:
                    if response.status == 200:
                        html = await response.text()
                        import re
                        from urllib.parse import unquote
                        
                        # Extract LinkedIn profile URLs from Google results
                        pattern = r'/url\?q=(https://(?:www\.)?linkedin\.com/in/[^&\s"]+)'
                        matches = re.findall(pattern, html)
                        
                        for match in matches:
                            profile_url = unquote(match).split('&')[0]
                            username = profile_url.rstrip('/').split('/in/')[-1].split('?')[0]
                            
                            if username and len(profiles) < max_results:
                                # Extract name/headline from Google snippet
                                profile_data = self._extract_linkedin_from_google(html, profile_url, username, keyword)
                                if profile_data:
                                    profiles.append(profile_data)
                
                await asyncio.sleep(2)  # Rate limiting
                
        except Exception as e:
            logger.warning(f"LinkedIn Google search failed: {e}")
        
        logger.info(f"🔍 Found {len(profiles)} LinkedIn profiles via Google")
        return profiles
    
    def _extract_linkedin_from_google(self, html: str, profile_url: str, username: str, keyword: str) -> Dict:
        """Extract LinkedIn profile info from Google search results"""
        try:
            import re
            
            # Try to find the title/name near this URL in the search results
            # Google typically shows "Name - Title - LinkedIn" in the title
            escaped_username = re.escape(username)
            title_pattern = rf'([^<>]{{3,80}})\s*[-–|]\s*[^<>]*?(?:LinkedIn|linkedin)[^<>]*?{escaped_username}'
            title_match = re.search(title_pattern, html, re.IGNORECASE)
            
            name = username.replace('-', ' ').title()
            headline = keyword
            
            if title_match:
                title_text = title_match.group(1).strip()
                # "FirstName LastName - Title" pattern
                parts = re.split(r'\s*[-–|]\s*', title_text)
                if parts:
                    name = parts[0].strip()
                    if len(parts) > 1:
                        headline = parts[1].strip()
            
            return {
                'name': name,
                'username': username,
                'url': profile_url,
                'headline': headline,
                'connections': 0,  # Can't determine from Google search
                'posts': 0,
                'location': ''
            }
        except Exception as e:
            logger.warning(f"Failed to extract LinkedIn data for {username}: {e}")
            return None
    
    def _estimate_linkedin_engagement(self, connections: int) -> float:
        """Estimate LinkedIn engagement rate"""
        if connections < 500:
            return 5.0
        elif connections < 5000:
            return 3.5
        elif connections < 15000:
            return 2.2
        else:
            return 1.5

class TwitterSearcher(PlatformSearcher):
    """Twitter/X influencer discovery"""
    
    def __init__(self):
        super().__init__("twitter")
    
    async def search_influencers(self, brand: str, keywords: List[str], max_results: int = 50) -> List[SocialMediaProfile]:
        """Search Twitter for real influencers using multiple methods"""
        profiles = []
        strategy = BRAND_INFLUENCER_STRATEGIES.get(brand, {})
        
        logger.info(f"🔍 Searching Twitter for {brand} influencers...")
        
        # Method 1: Search via Google for Twitter profiles
        twitter_profiles = await self._search_twitter_via_google(keywords, max_results)
        
        # Method 2: Use Twitter API v2 (if available)
        if not twitter_profiles:
            twitter_profiles = await self._search_twitter_api(keywords, max_results)
        
        if not twitter_profiles:
            logger.info(f"📝 No Twitter profiles found for {brand} — skipping")
        
        for profile_data in twitter_profiles[:max_results]:
            # Check alignment with brand
            if any(keyword.lower() in profile_data['bio'].lower() for keyword in keywords):
                profile = SocialMediaProfile(
                    platform="twitter",
                    username=profile_data['username'],
                    display_name=profile_data['display_name'],
                    profile_url=f"https://twitter.com/{profile_data['username']}",
                    verified=profile_data['verified'],
                    followers=profile_data['followers'],
                    following=profile_data['following'],
                    posts_count=profile_data['tweets'],
                    engagement_rate=self._estimate_twitter_engagement(profile_data['followers']),
                    bio=profile_data['bio']
                )
                profiles.append(profile)
        
        logger.info(f"✅ Found {len(profiles)} Twitter influencers for {brand}")
        return profiles
    
    def _estimate_twitter_engagement(self, followers: int) -> float:
        """Estimate Twitter engagement rate"""
        if followers < 1000:
            return 6.0
        elif followers < 10000:
            return 4.2
        elif followers < 50000:
            return 2.8
        else:
            return 1.2
    
    async def _search_twitter_via_google(self, keywords: List[str], max_results: int) -> List[Dict]:
        """Search for Twitter profiles via Google"""
        profiles = []
        
        try:
            for keyword in keywords[:2]:
                search_query = f"site:twitter.com OR site:x.com {keyword}"
                url = "https://www.google.com/search"
                params = {
                    'q': search_query,
                    'num': max_results,
                }
                
                async with self.session.get(url, params=params) as response:
                    if response.status == 200:
                        html = await response.text()
                        # Extract Twitter/X profile URLs
                        import re
                        from urllib.parse import unquote
                        
                        patterns = [
                            r'/url\?q=(https://(?:twitter|x)\.com/[^/&\s"]+)',
                            r'(https://(?:twitter|x)\.com/[a-zA-Z0-9_]+)'
                        ]
                        
                        for pattern in patterns:
                            matches = re.findall(pattern, html)
                            for match in matches:
                                url = unquote(match) if '/url?q=' in match else match
                                username = url.split('.com/')[-1].split('?')[0].split('/')[0]
                                
                                if username and not username.startswith('hashtag') and len(profiles) < max_results:
                                    profile_data = await self._get_twitter_public_data(username)
                                    if profile_data:
                                        profiles.append(profile_data)
                
                await asyncio.sleep(2)  # Rate limiting
                
        except Exception as e:
            logger.warning(f"Twitter Google search failed: {e}")
        
        logger.info(f"🐦 Found {len(profiles)} Twitter profiles via Google")
        return profiles
    
    async def _search_twitter_api(self, keywords: List[str], max_results: int) -> List[Dict]:
        """Search using Twitter API v2 (if available)"""
        import os
        bearer_token = os.getenv('TWITTER_BEARER_TOKEN')
        if not bearer_token:
            logger.info("📝 No Twitter API token found, skipping API search")
            return []
        
        try:
            profiles = []
            
            for keyword in keywords[:2]:
                url = "https://api.twitter.com/2/users/by"
                headers = {
                    'Authorization': f'Bearer {bearer_token}',
                    'Content-Type': 'application/json'
                }
                params = {
                    'usernames': keyword,  # This is limited - Twitter API v2 search is complex
                    'user.fields': 'public_metrics,description,verified'
                }
                
                async with self.session.get(url, headers=headers, params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        for user in data.get('data', []):
                            if len(profiles) < max_results:
                                profiles.append({
                                    'username': user['username'],
                                    'display_name': user['name'],
                                    'followers': user['public_metrics']['followers_count'],
                                    'following': user['public_metrics']['following_count'],
                                    'tweets': user['public_metrics']['tweet_count'],
                                    'bio': user.get('description', ''),
                                    'verified': user.get('verified', False),
                                    'url': f"https://twitter.com/{user['username']}"
                                })
                
                await asyncio.sleep(1)  # API rate limiting
                
        except Exception as e:
            logger.warning(f"Twitter API search failed: {e}")
        
        return profiles
    
    async def _get_twitter_public_data(self, username: str) -> Dict:
        """Get public Twitter profile data"""
        try:
            # Try both twitter.com and x.com
            urls = [f"https://twitter.com/{username}", f"https://x.com/{username}"]
            
            for url in urls:
                try:
                    headers = {
                        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
                    }
                    
                    async with self.session.get(url, headers=headers) as response:
                        if response.status == 200:
                            html = await response.text()
                            return self._parse_twitter_profile(html, username)
                except:
                    continue
                    
        except Exception as e:
            logger.warning(f"Failed to get Twitter data for @{username}: {e}")
        
        return None
    
    def _parse_twitter_profile(self, html: str, username: str) -> Dict:
        """Parse Twitter profile page for public data"""
        try:
            import re
            
            # Extract display name from title or page
            title_match = re.search(r'<title>([^<]+)</title>', html)
            display_name = username
            if title_match:
                title_text = title_match.group(1)
                if '(' in title_text and '@' in title_text:
                    display_name = title_text.split('(')[0].strip()
            
            # Extract follower count (various patterns Twitter uses)
            followers = 0
            follower_patterns = [
                r'(\d+(?:,\d+)*)\s+(?:Followers|followers)',
                r'"followers_count":(\d+)',
                r'(\d+(?:\.\d+)?[KMB]?)\s+Followers'
            ]
            
            for pattern in follower_patterns:
                match = re.search(pattern, html)
                if match:
                    follower_text = match.group(1)
                    followers = self._parse_count(follower_text)
                    break
            
            # Extract bio/description
            bio_patterns = [
                r'"description":"([^"]+)"',
                r'<meta name="description" content="([^"]*)"'
            ]
            
            bio = ''
            for pattern in bio_patterns:
                match = re.search(pattern, html)
                if match:
                    bio = match.group(1)
                    break
            
            return {
                'username': username,
                'display_name': display_name,
                'followers': followers,
                'bio': bio,
                'verified': 'verified' in html.lower() or 'checkmark' in html.lower(),
                'url': f"https://twitter.com/{username}"
            }
            
        except Exception as e:
            logger.warning(f"Failed to parse Twitter profile {username}: {e}")
            return None
    
    def _parse_count(self, count_text: str) -> int:
        """Convert count text (1.2M, 5K, etc.) to integer"""
        try:
            count_text = count_text.upper().replace(',', '')
            
            if 'K' in count_text:
                return int(float(count_text.replace('K', '')) * 1000)
            elif 'M' in count_text:
                return int(float(count_text.replace('M', '')) * 1000000)
            elif 'B' in count_text:
                return int(float(count_text.replace('B', '')) * 1000000000)
            else:
                return int(count_text) if count_text.isdigit() else 0
        except:
            return 0

class BlueskySearcher(PlatformSearcher):
    """Bluesky influencer discovery"""
    
    def __init__(self):
        super().__init__("bluesky")
    
    async def search_influencers(self, brand: str, keywords: List[str], max_results: int = 10) -> List[SocialMediaProfile]:
        """Search Bluesky for real influencers using AT Protocol"""
        profiles = []
        strategy = BRAND_INFLUENCER_STRATEGIES.get(brand, {})
        
        logger.info(f"🌌 Searching Bluesky for {brand} influencers...")
        
        # Method 1: Use Bluesky's public API
        bluesky_profiles = await self._search_bluesky_api(keywords, max_results)
        
        # Method 2: Search via web interface
        if not bluesky_profiles:
            bluesky_profiles = await self._search_bluesky_web(keywords, max_results)
        
        for profile_data in bluesky_profiles[:max_results]:
            if self._check_brand_alignment(profile_data, keywords, strategy):
                profile = SocialMediaProfile(
                    platform="bluesky",
                    username=profile_data.get('handle', '').replace('.bsky.social', ''),
                    display_name=profile_data.get('displayName', profile_data.get('handle', '')),
                    profile_url=f"https://bsky.app/profile/{profile_data.get('handle', '')}",
                    verified=profile_data.get('verified', False),
                    followers=profile_data.get('followersCount', 0),
                    posts_count=profile_data.get('postsCount', 0),
                    engagement_rate=self._estimate_engagement_rate(profile_data.get('followersCount', 0)),
                    bio=profile_data.get('description', '')
                )
                profiles.append(profile)
        
        logger.info(f"✅ Found {len(profiles)} Bluesky influencers for {brand}")
        return profiles
    
    def _check_brand_alignment(self, profile_data: Dict, keywords: List[str], strategy: Dict) -> bool:
        """Check if Bluesky profile aligns with brand strategy"""
        if not profile_data:
            return False
        
        # Check keyword alignment in description or displayName
        text_to_check = f"{profile_data.get('description', '')} {profile_data.get('displayName', '')}".lower()
        
        # Must match at least one keyword
        keyword_matches = sum(1 for keyword in keywords if keyword.lower() in text_to_check)
        return keyword_matches > 0
    
    async def _search_bluesky_api(self, keywords: List[str], max_results: int) -> List[Dict]:
        """Search using Bluesky's AT Protocol API"""
        profiles = []
        
        try:
            # Bluesky's public API endpoint for searching users
            for keyword in keywords[:3]:
                url = "https://public.api.bsky.app/xrpc/app.bsky.actor.searchActors"
                params = {
                    'q': keyword,
                    'limit': min(max_results, 25)  # API limit
                }
                
                async with self.session.get(url, params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        
                        for actor in data.get('actors', []):
                            if len(profiles) >= max_results:
                                break
                                
                            profile_data = {
                                'handle': actor.get('handle'),
                                'displayName': actor.get('displayName'),
                                'description': actor.get('description', ''),
                                'followersCount': actor.get('followersCount', 0),
                                'followsCount': actor.get('followsCount', 0),
                                'postsCount': actor.get('postsCount', 0),
                                'verified': actor.get('labels', []) != []  # Bluesky uses labels for verification
                            }
                            profiles.append(profile_data)
                
                await asyncio.sleep(1)  # Rate limiting
                
        except Exception as e:
            logger.warning(f"Bluesky API search failed: {e}")
        
        logger.info(f"🌌 Bluesky API found {len(profiles)} profiles")
        return profiles
    
    async def _search_bluesky_web(self, keywords: List[str], max_results: int) -> List[Dict]:
        """Search Bluesky via web interface as fallback"""
        profiles = []
        
        try:
            # Search for Bluesky profiles via search engines
            for keyword in keywords[:2]:
                search_query = f"site:bsky.app/profile {keyword}"
                url = "https://www.google.com/search"
                params = {
                    'q': search_query,
                    'num': max_results
                }
                
                async with self.session.get(url, params=params) as response:
                    if response.status == 200:
                        html = await response.text()
                        # Extract Bluesky profile URLs
                        import re
                        
                        profile_urls = re.findall(r'https://bsky\.app/profile/([^/\s"]+)', html)
                        
                        for handle in profile_urls:
                            if len(profiles) >= max_results:
                                break
                                
                            profile_data = await self._get_bluesky_profile_data(handle)
                            if profile_data:
                                profiles.append(profile_data)
                
                await asyncio.sleep(2)  # Rate limiting
                
        except Exception as e:
            logger.warning(f"Bluesky web search failed: {e}")
        
        return profiles
    
    async def _get_bluesky_profile_data(self, handle: str) -> Dict:
        """Get Bluesky profile data from handle"""
        try:
            url = f"https://public.api.bsky.app/xrpc/app.bsky.actor.getProfile"
            params = {'actor': handle}
            
            async with self.session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    return {
                        'handle': data.get('handle'),
                        'displayName': data.get('displayName'),
                        'description': data.get('description', ''),
                        'followersCount': data.get('followersCount', 0),
                        'followsCount': data.get('followsCount', 0),
                        'postsCount': data.get('postsCount', 0)
                    }
        except Exception as e:
            logger.warning(f"Failed to get Bluesky profile for {handle}: {e}")
        
        return None

class MastodonSearcher(PlatformSearcher):
    """Mastodon influencer discovery"""
    
    def __init__(self):
        super().__init__("mastodon")
    
    async def search_influencers(self, brand: str, keywords: List[str], max_results: int = 10) -> List[SocialMediaProfile]:
        """Search Mastodon for real influencers across instances"""
        profiles = []
        strategy = BRAND_INFLUENCER_STRATEGIES.get(brand, {})
        
        logger.info(f"🐘 Searching Mastodon for {brand} influencers...")
        
        # Method 1: Search major Mastodon instances
        mastodon_profiles = await self._search_mastodon_instances(keywords, max_results)
        
        # Method 2: Search tech-focused instances for developer content
        if not mastodon_profiles and any(tech_keyword in ' '.join(keywords).lower() for tech_keyword in ['code', 'developer', 'programming', 'tech', 'software']):
            mastodon_profiles = await self._search_tech_mastodon_instances(keywords, max_results)
        
        for profile_data in mastodon_profiles[:max_results]:
            if self._check_brand_alignment(profile_data, keywords, strategy):
                profile = SocialMediaProfile(
                    platform="mastodon",
                    username=profile_data.get('username', ''),
                    display_name=profile_data.get('display_name', profile_data.get('username', '')),
                    profile_url=profile_data.get('url', ''),
                    verified=profile_data.get('verified', False),
                    followers=profile_data.get('followers_count', 0),
                    posts_count=profile_data.get('statuses_count', 0),
                    engagement_rate=self._estimate_engagement_rate(profile_data.get('followers_count', 0)),
                    bio=profile_data.get('note', '')
                )
                profiles.append(profile)
        
        logger.info(f"✅ Found {len(profiles)} Mastodon influencers for {brand}")
        return profiles
    
    def _check_brand_alignment(self, account_data: Dict, keywords: List[str], strategy: Dict) -> bool:
        """Check if Mastodon account aligns with brand strategy"""
        if not account_data:
            return False
        
        # Check keyword alignment in note (bio) or display_name
        text_to_check = f"{account_data.get('note', '')} {account_data.get('display_name', '')}".lower()
        
        # Must match at least one keyword
        keyword_matches = sum(1 for keyword in keywords if keyword.lower() in text_to_check)
        return keyword_matches > 0
    
    async def _search_mastodon_instances(self, keywords: List[str], max_results: int) -> List[Dict]:
        """Search major Mastodon instances"""
        profiles = []
        
        # Major Mastodon instances to search
        instances = [
            'mastodon.social',
            'mastodon.online', 
            'fosstodon.org',  # Tech-focused
            'hachyderm.io',   # Tech/security focused
            'mas.to'
        ]
        
        try:
            for instance in instances[:3]:  # Limit to avoid rate limits
                for keyword in keywords[:2]:
                    url = f"https://{instance}/api/v2/search"
                    params = {
                        'q': keyword,
                        'type': 'accounts',
                        'limit': min(5, max_results)
                    }
                    
                    async with self.session.get(url, params=params) as response:
                        if response.status == 200:
                            data = await response.json()
                            
                            for account in data.get('accounts', []):
                                if len(profiles) >= max_results:
                                    break
                                    
                                # Filter for accounts with reasonable follower counts
                                if account.get('followers_count', 0) >= 50:  # Minimum threshold
                                    profiles.append(account)
                    
                    await asyncio.sleep(1)  # Rate limiting between requests
                
                await asyncio.sleep(2)  # Rate limiting between instances
                
        except Exception as e:
            logger.warning(f"Mastodon instance search failed: {e}")
        
        logger.info(f"🐘 Found {len(profiles)} Mastodon profiles from instances")
        return profiles
    
    async def _search_tech_mastodon_instances(self, keywords: List[str], max_results: int) -> List[Dict]:
        """Search tech-focused Mastodon instances"""
        profiles = []
        
        # Tech-focused Mastodon instances
        tech_instances = [
            'fosstodon.org',
            'hachyderm.io', 
            'infosec.exchange',
            'ruby.social',
            'phpc.social'
        ]
        
        try:
            for instance in tech_instances[:2]:
                for keyword in keywords[:2]:
                    url = f"https://{instance}/api/v2/search"
                    params = {
                        'q': keyword,
                        'type': 'accounts',
                        'limit': 5
                    }
                    
                    async with self.session.get(url, params=params) as response:
                        if response.status == 200:
                            data = await response.json()
                            
                            for account in data.get('accounts', []):
                                if len(profiles) >= max_results:
                                    break
                                    
                                if account.get('followers_count', 0) >= 25:  # Lower threshold for tech instances
                                    profiles.append(account)
                    
                    await asyncio.sleep(1)
                
                await asyncio.sleep(2)
                
        except Exception as e:
            logger.warning(f"Tech Mastodon search failed: {e}")
        
        logger.info(f"👨‍💻 Found {len(profiles)} profiles from tech Mastodon instances")
        return profiles

class PodcastSearcher(PlatformSearcher):
    """Podcast discovery from multiple sources"""
    
    def __init__(self):
        super().__init__("podcast")
    
    async def search_influencers(self, brand: str, keywords: List[str], max_results: int = 50) -> List[SocialMediaProfile]:
        """Search for podcasts using multiple sources"""
        profiles = []
        strategy = BRAND_INFLUENCER_STRATEGIES.get(brand, {})
        
        logger.info(f"🎙️ Searching for {brand} podcasts...")
        
        # Get podcast-specific keywords
        podcast_keywords = strategy.get('podcast_keywords', keywords)
        
        # Method 1: Search iTunes/Apple Podcasts API
        itunes_podcasts = await self._search_itunes_podcasts(podcast_keywords, max_results)
        
        # Method 2: Search Podcast Index API (if available) 
        podcast_index_results = await self._search_podcast_index(podcast_keywords, max_results)
        
        # Method 3: Search via Google for podcast websites
        google_podcasts = await self._search_podcasts_via_google(podcast_keywords, max_results)
        
        # Method 4: Search RSS directories
        rss_podcasts = await self._search_rss_directories(podcast_keywords, max_results)
        
        # Combine and deduplicate results
        all_podcasts = itunes_podcasts + podcast_index_results + google_podcasts + rss_podcasts
        seen_names = set()
        
        for podcast_data in all_podcasts[:max_results]:
            if podcast_data and podcast_data.get('name'):
                name_key = podcast_data['name'].lower().strip()
                if name_key not in seen_names:
                    seen_names.add(name_key)
                    
                    # Check alignment and create profile
                    if self._check_podcast_alignment(podcast_data, podcast_keywords, strategy):
                        profile = self._create_podcast_profile(podcast_data)
                        if profile:
                            profiles.append(profile)
        
        logger.info(f"🎙️ Found {len(profiles)} relevant podcasts for {brand}")
        return profiles
    
    async def _search_itunes_podcasts(self, keywords: List[str], max_results: int) -> List[Dict]:
        """Search iTunes/Apple Podcasts API with better headers"""
        podcasts = []
        
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                'Accept': 'application/json',
                'Accept-Language': 'en-US,en;q=0.9'
            }
            
            for keyword in keywords[:2]:  # Limit API calls
                url = "https://itunes.apple.com/search"
                params = {
                    'term': keyword,
                    'media': 'podcast',
                    'limit': min(10, max_results),
                    'country': 'US'
                }
                
                async with self.session.get(url, params=params, headers=headers) as response:
                    if response.status == 200:
                        try:
                            data = await response.json()
                            
                            for result in data.get('results', []):
                                podcast_info = await self._extract_itunes_podcast_info(result)
                                if podcast_info:
                                    podcasts.append(podcast_info)
                        except:
                            # If JSON parsing fails, skip iTunes
                            logger.warning(f"iTunes returned non-JSON response for '{keyword}'")
                            break
                
                await asyncio.sleep(2)  # Longer rate limiting
                
        except Exception as e:
            logger.warning(f"iTunes podcast search failed: {e}")
        
        logger.info(f"🍎 iTunes found {len(podcasts)} podcasts")
        return podcasts
    
    async def _extract_itunes_podcast_info(self, itunes_result: Dict) -> Dict:
        """Extract detailed podcast information from iTunes result"""
        try:
            podcast_name = itunes_result.get('collectionName', '')
            artist_name = itunes_result.get('artistName', '')
            feed_url = itunes_result.get('feedUrl', '')
            
            # Get additional details from RSS feed if available
            rss_details = {}
            if feed_url:
                rss_details = await self._parse_podcast_rss_feed(feed_url)
            
            return {
                'name': podcast_name,
                'host_name': artist_name,
                'description': itunes_result.get('collectionDescription', ''),
                'rss_feed': feed_url,
                'apple_podcasts_url': itunes_result.get('collectionViewUrl', ''),
                'artwork_url': itunes_result.get('artworkUrl600', ''),
                'categories': [itunes_result.get('primaryGenreName', '')],
                'episode_count': itunes_result.get('trackCount', 0),
                'release_date': itunes_result.get('releaseDate', ''),
                **rss_details  # Merge RSS feed details
            }
            
        except Exception as e:
            logger.warning(f"Failed to extract iTunes podcast info: {e}")
            return None
    
    async def _parse_podcast_rss_feed(self, feed_url: str) -> Dict:
        """Parse podcast RSS feed for additional details"""
        try:
            async with self.session.get(feed_url) as response:
                if response.status == 200:
                    xml_content = await response.text()
                    
                    # Basic RSS parsing - look for key elements
                    import re
                    
                    # Extract email
                    email_match = re.search(r'([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})', xml_content)
                    email = email_match.group(1) if email_match else ""
                    
                    # Extract website
                    website_match = re.search(r'<link>([^<]+)</link>', xml_content)
                    website = website_match.group(1) if website_match else ""
                    
                    # Extract episode count from items
                    episode_matches = re.findall(r'<item>', xml_content)
                    episode_count = len(episode_matches)
                    
                    # Look for guest application info
                    guest_app_patterns = [
                        r'guest[^<]*application[^<]*<[^>]*>([^<]+)',
                        r'interview[^<]*request[^<]*<[^>]*>([^<]+)',
                        r'booking[^<]*<[^>]*>([^<]+)'
                    ]
                    
                    guest_application_url = ""
                    for pattern in guest_app_patterns:
                        match = re.search(pattern, xml_content, re.IGNORECASE)
                        if match:
                            potential_url = match.group(1)
                            if 'http' in potential_url:
                                guest_application_url = potential_url
                                break
                    
                    return {
                        'email': email,
                        'website': website,
                        'episode_count': episode_count,
                        'guest_application_url': guest_application_url
                    }
                    
        except Exception as e:
            logger.warning(f"Failed to parse RSS feed {feed_url}: {e}")
        
        return {}
    
    async def _search_podcast_index(self, keywords: List[str], max_results: int) -> List[Dict]:
        """Search Podcast Index API (free podcast directory)"""
        podcasts = []
        
        try:
            # Note: Podcast Index API requires API key and secret
            # For now, we'll skip this or use it if keys are available
            import os
            api_key = os.getenv('PODCAST_INDEX_API_KEY')
            api_secret = os.getenv('PODCAST_INDEX_API_SECRET')
            
            if not api_key or not api_secret:
                logger.info("📝 No Podcast Index API credentials found, skipping")
                return []
            
            # Implementation would go here with proper authentication
            # This is a placeholder for now
            
        except Exception as e:
            logger.warning(f"Podcast Index search failed: {e}")
        
        return podcasts
    
    async def _search_podcasts_via_google(self, keywords: List[str], max_results: int) -> List[Dict]:
        """Search for podcasts using Google search.

        Real Google search is not yet implemented.  Return an empty list
        so no fabricated data ends up in the database.
        """
        # TODO: Implement real Google search for podcast discovery
        logger.info("Google podcast search not yet implemented — skipping")
        return []
    
    async def _search_rss_directories(self, keywords: List[str], max_results: int) -> List[Dict]:
        """Search RSS directories for podcasts"""
        # This is a placeholder for searching RSS directories
        # Could implement searches of sites like:
        # - Podcast One
        # - Stitcher
        # - Public RSS directories
        return []
    
    def _check_podcast_alignment(self, podcast_data: Dict, keywords: List[str], strategy: Dict) -> bool:
        """Check if podcast aligns with brand strategy"""
        if not podcast_data:
            return False
        
        # Check if podcast name or description contains relevant keywords
        text_to_check = f"{podcast_data.get('name', '')} {podcast_data.get('description', '')}".lower()
        
        # Must match at least one keyword
        keyword_matches = sum(1 for keyword in keywords if keyword.lower() in text_to_check)
        
        # Basic quality filters
        min_episodes = 5  # Minimum episode count
        has_enough_episodes = podcast_data.get('episode_count', 0) >= min_episodes
        
        return keyword_matches > 0 and has_enough_episodes
    
    def _create_podcast_profile(self, podcast_data: Dict) -> SocialMediaProfile:
        """Create a social media profile from podcast data with cross-platform discovery"""
        try:
            # Estimate reach based on available metrics or use conservative estimate
            estimated_reach = self._estimate_podcast_reach(podcast_data)
            
            # Find cross-platform presence
            cross_platform_data = asyncio.create_task(self._find_podcast_cross_platform_presence(podcast_data))
            
            # Create the main social media profile
            profile = SocialMediaProfile(
                platform="podcast",
                username=podcast_data.get('name', '').replace(' ', '').lower(),
                display_name=podcast_data.get('name', ''),
                profile_url=podcast_data.get('apple_podcasts_url', ''),
                verified=False,  # Will need to determine verification status
                followers=estimated_reach,
                posts_count=podcast_data.get('episode_count', 0),
                engagement_rate=self._estimate_podcast_engagement_rate(estimated_reach),
                bio=podcast_data.get('description', ''),
                website=podcast_data.get('website', ''),
                email=podcast_data.get('email', '')
            )
            
            return profile
            
        except Exception as e:
            logger.warning(f"Failed to create podcast profile: {e}")
            return None
    
    async def _find_podcast_cross_platform_presence(self, podcast_data: Dict) -> Dict:
        """Find YouTube, social media, and other platform presence for a podcast"""
        cross_platform = {
            'youtube_channel': '',
            'twitter_handle': '',
            'instagram_handle': '',
            'linkedin_page': '',
            'facebook_page': '',
            'website': podcast_data.get('website', '')
        }
        
        try:
            podcast_name = podcast_data.get('name', '')
            host_name = podcast_data.get('host_name', '')
            
            if not podcast_name:
                return cross_platform
            
            # Search for YouTube channel
            youtube_channel = await self._search_podcast_youtube_channel(podcast_name, host_name)
            if youtube_channel:
                cross_platform['youtube_channel'] = youtube_channel
            
            # Search for social media presence  
            social_links = await self._search_podcast_social_media(podcast_name, host_name)
            cross_platform.update(social_links)
            
            # If we have a website, scrape it for additional social links
            if cross_platform['website']:
                website_social = await self._scrape_website_social_links(cross_platform['website'])
                for platform, link in website_social.items():
                    if link and not cross_platform.get(platform):
                        cross_platform[platform] = link
            
        except Exception as e:
            logger.warning(f"Failed to find cross-platform presence for {podcast_name}: {e}")
        
        return cross_platform
    
    async def _search_podcast_youtube_channel(self, podcast_name: str, host_name: str) -> str:
        """Search for podcast's YouTube channel"""
        try:
            # Search YouTube for the podcast
            search_terms = [
                f'"{podcast_name}" podcast',
                f'{podcast_name} {host_name}',
                f'{podcast_name} channel'
            ]
            
            for search_term in search_terms:
                url = "https://www.youtube.com/results"
                params = {'search_query': search_term}
                
                async with self.session.get(url, params=params) as response:
                    if response.status == 200:
                        html = await response.text()
                        
                        # Look for channel URLs in the results
                        import re
                        channel_pattern = r'/channel/([a-zA-Z0-9_-]+)'
                        matches = re.findall(channel_pattern, html)
                        
                        if matches:
                            return f"https://youtube.com/channel/{matches[0]}"
                
                await asyncio.sleep(1)  # Rate limiting
                
        except Exception as e:
            logger.warning(f"YouTube search failed for {podcast_name}: {e}")
        
        return ""
    
    async def _search_podcast_social_media(self, podcast_name: str, host_name: str) -> Dict[str, str]:
        """Search for podcast's social media presence"""
        social_links = {
            'twitter_handle': '',
            'instagram_handle': '',
            'linkedin_page': '',
            'facebook_page': ''
        }
        
        try:
            # Search Google for social media mentions
            search_query = f'"{podcast_name}" site:twitter.com OR site:instagram.com OR site:linkedin.com OR site:facebook.com'
            
            url = "https://www.google.com/search"
            params = {
                'q': search_query,
                'num': 10
            }
            headers = {
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
            }
            
            async with self.session.get(url, params=params, headers=headers) as response:
                if response.status == 200:
                    html = await response.text()
                    
                    # Extract social media links
                    import re
                    
                    # Twitter
                    twitter_match = re.search(r'twitter\.com/([a-zA-Z0-9_]+)', html)
                    if twitter_match:
                        social_links['twitter_handle'] = f"https://twitter.com/{twitter_match.group(1)}"
                    
                    # Instagram  
                    instagram_match = re.search(r'instagram\.com/([a-zA-Z0-9_.]+)', html)
                    if instagram_match:
                        social_links['instagram_handle'] = f"https://instagram.com/{instagram_match.group(1)}"
                    
                    # LinkedIn
                    linkedin_match = re.search(r'linkedin\.com/(?:company|in)/([a-zA-Z0-9-]+)', html)
                    if linkedin_match:
                        social_links['linkedin_page'] = f"https://linkedin.com/company/{linkedin_match.group(1)}"
                    
                    # Facebook
                    facebook_match = re.search(r'facebook\.com/([a-zA-Z0-9.]+)', html)
                    if facebook_match:
                        social_links['facebook_page'] = f"https://facebook.com/{facebook_match.group(1)}"
            
        except Exception as e:
            logger.warning(f"Social media search failed for {podcast_name}: {e}")
        
        return social_links
    
    async def _scrape_website_social_links(self, website_url: str) -> Dict[str, str]:
        """Scrape podcast website for social media links"""
        social_links = {}
        
        try:
            async with self.session.get(website_url) as response:
                if response.status == 200:
                    html = await response.text()
                    
                    # Look for social media links in the HTML
                    import re
                    
                    social_patterns = {
                        'twitter_handle': r'(?:twitter\.com|@)([a-zA-Z0-9_]+)',
                        'instagram_handle': r'instagram\.com/([a-zA-Z0-9_.]+)',
                        'youtube_channel': r'youtube\.com/(?:channel/|c/|user/|@)([a-zA-Z0-9_-]+)',
                        'linkedin_page': r'linkedin\.com/(?:company|in)/([a-zA-Z0-9-]+)',
                        'facebook_page': r'facebook\.com/([a-zA-Z0-9.]+)'
                    }
                    
                    for platform, pattern in social_patterns.items():
                        matches = re.findall(pattern, html, re.IGNORECASE)
                        if matches:
                            handle = matches[0]
                            if platform == 'twitter_handle':
                                social_links[platform] = f"https://twitter.com/{handle}"
                            elif platform == 'instagram_handle':
                                social_links[platform] = f"https://instagram.com/{handle}"
                            elif platform == 'youtube_channel':
                                social_links[platform] = f"https://youtube.com/c/{handle}"
                            elif platform == 'linkedin_page':
                                social_links[platform] = f"https://linkedin.com/company/{handle}"
                            elif platform == 'facebook_page':
                                social_links[platform] = f"https://facebook.com/{handle}"
        
        except Exception as e:
            logger.warning(f"Failed to scrape website {website_url}: {e}")
        
        return social_links
    
    def _estimate_podcast_reach(self, podcast_data: Dict) -> int:
        """Estimate podcast listener count based on available data"""
        # Conservative estimation based on episode count and platform presence
        episode_count = podcast_data.get('episode_count', 0)
        
        if episode_count == 0:
            return 100  # Very small podcast
        elif episode_count < 10:
            return 500  # New podcast
        elif episode_count < 50:
            return 2000  # Growing podcast
        elif episode_count < 100:
            return 5000  # Established podcast
        else:
            return 10000  # Mature podcast
    
    def _estimate_podcast_engagement_rate(self, reach: int) -> float:
        """Estimate engagement rate for podcasts"""
        # Podcasts typically have higher engagement than other media
        if reach < 1000:
            return 15.0  # Small, highly engaged audience
        elif reach < 5000:
            return 10.0
        else:
            return 8.0  # Still high engagement for larger audiences

class BrandInfluencerDiscovery:
    """Main influencer discovery orchestrator"""
    
    def __init__(self):
        self.db = InfluencerDatabase()
        self.platforms = {
            'youtube': YouTubeSearcher(),
            'instagram': InstagramSearcher(),
            'linkedin': LinkedInSearcher(),
            'twitter': TwitterSearcher(),
            'bluesky': BlueskySearcher(),
            'mastodon': MastodonSearcher(),
            'podcast': PodcastSearcher()
        }
    
    async def discover_brand_influencers(self, brand: str, max_per_platform: int = 25) -> Dict[str, List[InfluencerProfile]]:
        """Discover influencers across all platforms for a brand"""
        results = {}
        strategy = ensure_brand_strategy(brand) or {}
        
        if not strategy:
            logger.error(f"❌ No strategy defined for brand: {brand}")
            return results
        
        logger.info(f"🔍 Starting influencer discovery for {strategy['name']}")
        
        # Search each platform
        for platform_name, searcher in self.platforms.items():
            try:
                async with searcher:
                    profiles = await searcher.search_influencers(
                        brand, 
                        strategy['keywords'], 
                        max_per_platform
                    )
                    
                    # Convert to full influencer profiles
                    influencers = []
                    for profile in profiles:
                        influencer = self._create_influencer_profile(profile, brand, strategy)
                        if influencer:
                            influencers.append(influencer)
                    
                    results[platform_name] = influencers
                    
                    # Log discovery session
                    self._log_discovery_session(brand, platform_name, len(profiles))
                    
            except Exception as e:
                logger.error(f"❌ Error searching {platform_name}: {e}")
                results[platform_name] = []
        
        # Save all discovered influencers
        total_saved = 0
        for platform_influencers in results.values():
            for influencer in platform_influencers:
                if self._save_influencer_profile(influencer, brand):
                    total_saved += 1
        
        logger.info(f"✅ Discovery complete: {total_saved} new influencers saved for {brand}")
        return results
    
    def _create_influencer_profile(self, social_profile: SocialMediaProfile, brand: str, strategy: Dict) -> Optional[InfluencerProfile]:
        """Create a complete influencer profile from social media data"""
        
        # Calculate brand alignment score
        alignment_score = self._calculate_brand_alignment(social_profile, strategy)
        
        # Skip if below minimum thresholds
        if (social_profile.followers < strategy.get('min_followers', 1000) or
            alignment_score < 0.3):
            return None
        
        # Extract content themes from bio
        content_themes = self._extract_content_themes(social_profile.bio, strategy)
        
        # Generate outreach notes
        outreach_notes = self._generate_outreach_notes(social_profile, brand, strategy)
        
        influencer = InfluencerProfile(
            name=social_profile.display_name,
            primary_platform=social_profile.platform,
            niche=strategy['focus'],
            brand_alignment_score=alignment_score,
            total_reach=social_profile.followers,
            avg_engagement_rate=social_profile.engagement_rate,
            contact_email=social_profile.email,
            website=social_profile.website,
            location=social_profile.location,
            bio_summary=social_profile.bio[:200] + "..." if len(social_profile.bio) > 200 else social_profile.bio,
            content_themes=content_themes,
            social_profiles={social_profile.platform: social_profile},
            outreach_notes=outreach_notes,
            discovery_date=datetime.now().isoformat(),
            last_updated=datetime.now().isoformat()
        )
        
        return influencer
    
    def _calculate_brand_alignment(self, profile: SocialMediaProfile, strategy: Dict) -> float:
        """Calculate how well an influencer aligns with brand strategy"""
        score = 0.0
        bio_lower = profile.bio.lower()
        
        # Keyword matching (40% of score)
        keyword_matches = sum(1 for keyword in strategy.get('keywords', []) 
                            if keyword.lower() in bio_lower)
        keyword_score = min(keyword_matches / len(strategy.get('keywords', [])), 1.0) * 0.4
        
        # Engagement rate (30% of score)
        target_engagement = strategy.get('target_engagement', 3.0)
        engagement_score = min(profile.engagement_rate / target_engagement, 1.0) * 0.3
        
        # Follower count (20% of score)
        min_followers = strategy.get('min_followers', 1000)
        if profile.followers >= min_followers * 10:
            follower_score = 0.2
        elif profile.followers >= min_followers:
            follower_score = 0.15
        else:
            follower_score = 0.1
        
        # Verification status (10% of score)
        verified_score = 0.1 if profile.verified else 0.05
        
        total_score = keyword_score + engagement_score + follower_score + verified_score
        return round(total_score, 2)
    
    def _extract_content_themes(self, bio: str, strategy: Dict) -> List[str]:
        """Extract content themes from bio based on brand strategy"""
        themes = []
        bio_lower = bio.lower()
        
        # Check for strategy-related themes
        for niche in strategy.get('target_niches', []):
            if niche.lower() in bio_lower:
                themes.append(niche)
        
        # Extract hashtag-like themes
        import re
        hashtags = re.findall(r'#(\w+)', bio)
        themes.extend(hashtags[:3])  # Limit to 3 hashtags
        
        return themes[:5]  # Limit to 5 themes total
    
    def _generate_outreach_notes(self, profile: SocialMediaProfile, brand: str, strategy: Dict) -> str:
        """Generate personalized outreach notes"""
        notes = []
        
        # Platform-specific approach
        if profile.platform == "linkedin":
            notes.append("Professional approach recommended - focus on business value")
        elif profile.platform == "instagram":
            notes.append("Visual content collaboration opportunity")
        elif profile.platform == "youtube":
            notes.append("Video content partnership potential")
        elif profile.platform == "twitter":
            notes.append("Real-time engagement and thread opportunities")
        
        # Engagement level approach
        if profile.followers > 100000:
            notes.append("High-reach influencer - may require compensation")
        elif profile.followers > 10000:
            notes.append("Mid-tier influencer - product exchange or small fee")
        else:
            notes.append("Micro-influencer - authentic engagement focus")
        
        # Content alignment
        if profile.engagement_rate > 5.0:
            notes.append("High engagement - authentic audience connection")
        
        return " • ".join(notes)
    
    def _save_influencer_profile(self, influencer: InfluencerProfile, brand: str) -> bool:
        """Save influencer profile to database"""
        try:
            conn = sqlite3.connect(self.db.db_path)
            cursor = conn.cursor()
            
            # Insert influencer
            cursor.execute("""
                INSERT OR REPLACE INTO influencers 
                (name, primary_platform, niche, brand, brand_alignment_score, total_reach,
                 avg_engagement_rate, contact_email, website, location, bio_summary,
                 content_themes, outreach_notes, discovery_date, last_updated)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                influencer.name,
                influencer.primary_platform,
                influencer.niche,
                brand,
                influencer.brand_alignment_score,
                influencer.total_reach,
                influencer.avg_engagement_rate,
                influencer.contact_email,
                influencer.website,
                influencer.location,
                influencer.bio_summary,
                json.dumps(influencer.content_themes),
                influencer.outreach_notes,
                influencer.discovery_date,
                influencer.last_updated
            ))
            
            influencer_id = cursor.lastrowid
            
            # Insert social profiles
            for platform, profile in influencer.social_profiles.items():
                cursor.execute("""
                    INSERT OR REPLACE INTO social_profiles
                    (influencer_id, platform, username, display_name, profile_url,
                     verified, followers, following, posts_count, engagement_rate,
                     bio, location, website, email)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    influencer_id,
                    profile.platform,
                    profile.username,
                    profile.display_name,
                    profile.profile_url,
                    profile.verified,
                    profile.followers,
                    profile.following,
                    profile.posts_count,
                    profile.engagement_rate,
                    profile.bio,
                    profile.location,
                    profile.website,
                    profile.email
                ))
            
            # Insert podcast profile if it exists
            if influencer.podcast_profile:
                podcast = influencer.podcast_profile
                cursor.execute("""
                    INSERT OR REPLACE INTO podcast_profiles
                    (influencer_id, rss_feed, guest_application_url, episode_count,
                     average_rating, total_reviews, categories, release_frequency,
                     youtube_channel, spotify_url, apple_podcasts_url, social_links,
                     last_episode_date, accepts_guests)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    influencer_id,
                    podcast.rss_feed,
                    podcast.guest_application_url,
                    podcast.episode_count,
                    podcast.average_rating,
                    podcast.total_reviews,
                    json.dumps(podcast.categories),
                    podcast.release_frequency,
                    podcast.youtube_channel,
                    podcast.spotify_url,
                    podcast.apple_podcasts_url,
                    json.dumps(podcast.social_links),
                    podcast.last_episode_date,
                    True  # accepts_guests default to True
                ))
            
            conn.commit()
            conn.close()
            return True
            
        except Exception as e:
            logger.error(f"Failed to save influencer {influencer.name}: {e}")
            return False
    
    def _log_discovery_session(self, brand: str, platform: str, results_count: int):
        """Log discovery session for analytics"""
        try:
            conn = sqlite3.connect(self.db.db_path)
            cursor = conn.cursor()
            
            cursor.execute("""
                INSERT INTO discovery_sessions 
                (brand, platform, results_count, session_date, success)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP, ?)
            """, (brand, platform, results_count, True))
            
            conn.commit()
            conn.close()
            
        except Exception as e:
            logger.error(f"Failed to log discovery session: {e}")

    def get_brand_influencers(self, brand: str = None, platform: str = None, 
                            min_followers: int = 0, min_alignment: float = 0.0) -> List[Dict]:
        """Get filtered influencer data for reporting"""
        conn = sqlite3.connect(self.db.db_path)
        cursor = conn.cursor()
        
        query = """
            SELECT i.*, 
                   GROUP_CONCAT(sp.platform || ':' || sp.profile_url) as social_links,
                   GROUP_CONCAT(sp.followers) as platform_followers
            FROM influencers i
            LEFT JOIN social_profiles sp ON i.id = sp.influencer_id
            WHERE (i.deleted IS NULL OR i.deleted = FALSE)
        """
        params = []
        
        if brand:
            query += " AND i.brand = ?"
            params.append(brand)
        
        if platform:
            query += " AND i.primary_platform = ?"
            params.append(platform)
        
        if min_followers > 0:
            query += " AND i.total_reach >= ?"
            params.append(min_followers)
        
        if min_alignment > 0.0:
            query += " AND i.brand_alignment_score >= ?"
            params.append(min_alignment)
        
        query += " GROUP BY i.id ORDER BY i.brand_alignment_score DESC, i.total_reach DESC"
        
        cursor.execute(query, params)
        results = cursor.fetchall()
        
        # Convert to dictionaries
        columns = [description[0] for description in cursor.description]
        influencers = [dict(zip(columns, row)) for row in results]
        
        conn.close()
        return influencers

# CLI interface for testing
async def main():
    """Test influencer discovery system"""
    discovery = BrandInfluencerDiscovery()
    
    # Test discovery for a specific brand
    brand = "foundry"
    results = await discovery.discover_brand_influencers(brand, max_per_platform=3)
    
    strategy = ensure_brand_strategy(brand) or {'name': brand}
    print(f"\n🎯 Influencer Discovery Results for {strategy['name']}")
    print("=" * 60)
    
    total_influencers = 0
    for platform, influencers in results.items():
        print(f"\n📱 {platform.title()} ({len(influencers)} influencers)")
        for influencer in influencers:
            total_influencers += 1
            print(f"  • {influencer.name} (@{influencer.social_profiles[platform].username})")
            print(f"    Followers: {influencer.total_reach:,} | Engagement: {influencer.avg_engagement_rate:.1f}%")
            print(f"    Alignment: {influencer.brand_alignment_score:.2f} | {influencer.outreach_notes}")
    
    print(f"\n✅ Total discovered: {total_influencers} influencers")
    
    # Show summary from database
    all_influencers = discovery.get_brand_influencers(brand=brand)
    print(f"📊 Database total for {brand}: {len(all_influencers)} influencers")

if __name__ == "__main__":
    asyncio.run(main())
#!/usr/bin/env python3
"""
Influencer Profile Enrichment & Content Tracker
================================================

Continuously enriches discovered influencer profiles with:
- Additional contact details (email, website, social links)
- Cross-platform social profile discovery
- Relevant content/posts from each influencer
- Updated follower counts and engagement metrics

Designed to run repeatedly — each pass adds more data.

Usage:
    python influencer_enrichment.py --all
    python influencer_enrichment.py --brand foundry
    python influencer_enrichment.py --influencer-id 42
"""

import asyncio
import aiohttp
import sqlite3
import json
import logging
import re
import ssl
import argparse
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, asdict

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from automation.influencer_discovery import (
    BRAND_INFLUENCER_STRATEGIES,
    InfluencerDatabase,
)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Database schema additions
# ---------------------------------------------------------------------------

def ensure_enrichment_tables(db_path: Path):
    """Create tables for content tracking and enrichment history."""
    conn = sqlite3.connect(db_path)
    c = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS influencer_content (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            influencer_id INTEGER NOT NULL,
            platform TEXT NOT NULL,
            content_type TEXT NOT NULL,       -- post, video, article, episode, tweet
            title TEXT,
            url TEXT NOT NULL,
            description TEXT,
            published_date TEXT,
            likes INTEGER DEFAULT 0,
            comments INTEGER DEFAULT 0,
            shares INTEGER DEFAULT 0,
            views INTEGER DEFAULT 0,
            relevance_score REAL DEFAULT 0.0,  -- 0-1 how relevant to brand
            brand TEXT,
            tags TEXT,                         -- JSON array
            discovered_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (influencer_id) REFERENCES influencers (id),
            UNIQUE(influencer_id, url)
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS enrichment_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            influencer_id INTEGER NOT NULL,
            enrichment_type TEXT NOT NULL,     -- contact, content, metrics, social_links
            source TEXT,                       -- where the data came from
            fields_updated TEXT,               -- JSON list of field names updated
            run_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            success BOOLEAN DEFAULT TRUE,
            notes TEXT,
            FOREIGN KEY (influencer_id) REFERENCES influencers (id)
        )
    """)

    # Add enrichment_score column to influencers if missing
    try:
        c.execute("ALTER TABLE influencers ADD COLUMN enrichment_score REAL DEFAULT 0.0")
    except sqlite3.OperationalError:
        pass

    # Add last_enriched column to influencers if missing
    try:
        c.execute("ALTER TABLE influencers ADD COLUMN last_enriched TIMESTAMP")
    except sqlite3.OperationalError:
        pass

    conn.commit()
    conn.close()
    logger.info("✅ Enrichment tables ready")


# ---------------------------------------------------------------------------
# Helper: create an aiohttp session with relaxed SSL for dev
# ---------------------------------------------------------------------------

def _make_session() -> aiohttp.ClientSession:
    ssl_ctx = ssl.create_default_context()
    ssl_ctx.check_hostname = False
    ssl_ctx.verify_mode = ssl.CERT_NONE
    connector = aiohttp.TCPConnector(ssl=ssl_ctx)
    return aiohttp.ClientSession(
        connector=connector,
        timeout=aiohttp.ClientTimeout(total=30),
        headers={
            'User-Agent': (
                'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
                'AppleWebKit/537.36 (KHTML, like Gecko) '
                'Chrome/120.0.0.0 Safari/537.36'
            )
        },
    )


# ---------------------------------------------------------------------------
# Content discovery helpers (per-platform)
# ---------------------------------------------------------------------------

async def _fetch_youtube_content(session: aiohttp.ClientSession, profile_url: str,
                                  username: str, keywords: List[str],
                                  max_items: int = 10) -> List[Dict]:
    """Fetch recent YouTube videos for a channel."""
    import os
    items: List[Dict] = []

    api_key = os.getenv('YOUTUBE_API_KEY')
    channel_id = None

    # Try to extract channel ID from URL
    if '/channel/' in profile_url:
        channel_id = profile_url.split('/channel/')[-1].split('/')[0].split('?')[0]

    # --- API path ---
    if api_key and channel_id:
        try:
            url = "https://www.googleapis.com/youtube/v3/search"
            params = {
                'key': api_key,
                'channelId': channel_id,
                'part': 'snippet',
                'order': 'date',
                'maxResults': max_items,
                'type': 'video',
            }
            async with session.get(url, params=params) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    for entry in data.get('items', []):
                        snippet = entry.get('snippet', {})
                        video_id = entry.get('id', {}).get('videoId', '')
                        items.append({
                            'content_type': 'video',
                            'title': snippet.get('title', ''),
                            'url': f"https://youtube.com/watch?v={video_id}",
                            'description': snippet.get('description', '')[:500],
                            'published_date': snippet.get('publishedAt', ''),
                        })
        except Exception as e:
            logger.warning(f"YouTube API content fetch failed: {e}")

    # --- RSS fallback ---
    if not items and channel_id:
        try:
            rss_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
            async with session.get(rss_url) as resp:
                if resp.status == 200:
                    xml = await resp.text()
                    titles = re.findall(r'<title>([^<]+)</title>', xml)[1:]  # skip feed title
                    links = re.findall(r'<link rel="alternate" href="([^"]+)"', xml)
                    published = re.findall(r'<published>([^<]+)</published>', xml)
                    for i in range(min(len(titles), max_items)):
                        items.append({
                            'content_type': 'video',
                            'title': titles[i] if i < len(titles) else '',
                            'url': links[i] if i < len(links) else '',
                            'description': '',
                            'published_date': published[i] if i < len(published) else '',
                        })
        except Exception as e:
            logger.warning(f"YouTube RSS fetch failed: {e}")

    return items


async def _fetch_bluesky_content(session: aiohttp.ClientSession, handle: str,
                                  keywords: List[str],
                                  max_items: int = 10) -> List[Dict]:
    """Fetch recent Bluesky posts via AT Protocol public API."""
    items: List[Dict] = []
    try:
        url = "https://public.api.bsky.app/xrpc/app.bsky.feed.getAuthorFeed"
        params = {'actor': handle, 'limit': min(max_items, 30)}
        async with session.get(url, params=params) as resp:
            if resp.status == 200:
                data = await resp.json()
                for entry in data.get('feed', []):
                    post = entry.get('post', {})
                    record = post.get('record', {})
                    text = record.get('text', '')
                    uri = post.get('uri', '')
                    # Convert AT URI to web URL
                    # at://did:plc:xxx/app.bsky.feed.post/yyy -> https://bsky.app/profile/handle/post/yyy
                    web_url = ''
                    if uri:
                        parts = uri.split('/')
                        if len(parts) >= 5:
                            rkey = parts[-1]
                            web_url = f"https://bsky.app/profile/{handle}/post/{rkey}"
                    items.append({
                        'content_type': 'post',
                        'title': text[:120] if text else '',
                        'url': web_url,
                        'description': text,
                        'published_date': record.get('createdAt', ''),
                        'likes': post.get('likeCount', 0),
                        'comments': post.get('replyCount', 0),
                        'shares': post.get('repostCount', 0),
                    })
    except Exception as e:
        logger.warning(f"Bluesky content fetch failed for {handle}: {e}")
    return items[:max_items]


async def _fetch_mastodon_content(session: aiohttp.ClientSession, profile_url: str,
                                   keywords: List[str],
                                   max_items: int = 10) -> List[Dict]:
    """Fetch recent Mastodon toots via public API."""
    items: List[Dict] = []
    try:
        # Parse instance and account from profile_url
        # e.g. https://mastodon.social/@user or https://fosstodon.org/@user
        parsed = re.match(r'https://([^/]+)/@([^/]+)', profile_url)
        if not parsed:
            return items
        instance = parsed.group(1)
        username = parsed.group(2)

        # Look up account ID
        lookup_url = f"https://{instance}/api/v1/accounts/lookup"
        async with session.get(lookup_url, params={'acct': username}) as resp:
            if resp.status != 200:
                return items
            acct_data = await resp.json()
            account_id = acct_data.get('id')
            if not account_id:
                return items

        # Fetch statuses
        statuses_url = f"https://{instance}/api/v1/accounts/{account_id}/statuses"
        async with session.get(statuses_url, params={'limit': max_items, 'exclude_replies': 'true'}) as resp:
            if resp.status == 200:
                toots = await resp.json()
                for toot in toots:
                    # Strip HTML tags from content
                    text = re.sub(r'<[^>]+>', '', toot.get('content', ''))
                    items.append({
                        'content_type': 'post',
                        'title': text[:120],
                        'url': toot.get('url', ''),
                        'description': text,
                        'published_date': toot.get('created_at', ''),
                        'likes': toot.get('favourites_count', 0),
                        'comments': toot.get('replies_count', 0),
                        'shares': toot.get('reblogs_count', 0),
                    })
    except Exception as e:
        logger.warning(f"Mastodon content fetch failed: {e}")
    return items[:max_items]


async def _fetch_podcast_episodes(session: aiohttp.ClientSession, rss_feed: str,
                                   max_items: int = 10) -> List[Dict]:
    """Fetch recent podcast episodes from RSS feed."""
    items: List[Dict] = []
    if not rss_feed:
        return items
    try:
        async with session.get(rss_feed) as resp:
            if resp.status == 200:
                xml = await resp.text()
                # Quick parse of <item> blocks
                item_blocks = re.findall(r'<item>(.*?)</item>', xml, re.DOTALL)
                for block in item_blocks[:max_items]:
                    title = ''
                    t = re.search(r'<title>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</title>', block)
                    if t:
                        title = t.group(1).strip()
                    link = ''
                    l = re.search(r'<link>([^<]+)</link>', block)
                    if l:
                        link = l.group(1).strip()
                    desc = ''
                    d = re.search(r'<description>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</description>', block, re.DOTALL)
                    if d:
                        desc = re.sub(r'<[^>]+>', '', d.group(1).strip())[:500]
                    pub_date = ''
                    p = re.search(r'<pubDate>([^<]+)</pubDate>', block)
                    if p:
                        pub_date = p.group(1).strip()
                    if title:
                        items.append({
                            'content_type': 'episode',
                            'title': title,
                            'url': link,
                            'description': desc,
                            'published_date': pub_date,
                        })
    except Exception as e:
        logger.warning(f"Podcast RSS fetch failed: {e}")
    return items


# ---------------------------------------------------------------------------
# Cross-platform contact & link discovery
# ---------------------------------------------------------------------------

async def _find_additional_contacts(session: aiohttp.ClientSession,
                                     influencer: Dict) -> Dict[str, str]:
    """Try to find email, website, and extra social links from known URLs."""
    found: Dict[str, str] = {}
    urls_to_check: List[str] = []

    # Gather URLs we already know
    if influencer.get('website'):
        urls_to_check.append(influencer['website'])
    social_links_str = influencer.get('social_links', '') or ''
    for part in social_links_str.split(','):
        if 'http' in part:
            url = part.split(':', 1)[-1].strip() if ':' in part else part.strip()
            if url.startswith('http'):
                urls_to_check.append(url)

    for url in urls_to_check[:3]:  # limit to avoid hammering
        try:
            async with session.get(url) as resp:
                if resp.status == 200:
                    html = await resp.text()

                    # Look for email
                    if not found.get('email') and not influencer.get('contact_email'):
                        emails = re.findall(
                            r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}', html
                        )
                        # Filter out common non-personal addresses
                        for email in emails:
                            lower = email.lower()
                            if not any(skip in lower for skip in [
                                'example.com', 'sentry.io', 'wixpress', 'wordpress',
                                'schema.org', 'w3.org', 'googleapis', 'noreply',
                            ]):
                                found['email'] = email
                                break

                    # Discover social links we don't have yet
                    social_patterns = {
                        'twitter': r'(?:twitter\.com|x\.com)/([a-zA-Z0-9_]{1,15})',
                        'instagram': r'instagram\.com/([a-zA-Z0-9_.]+)',
                        'youtube': r'youtube\.com/(?:channel/|c/|@)([a-zA-Z0-9_\-]+)',
                        'linkedin': r'linkedin\.com/(?:in|company)/([a-zA-Z0-9\-]+)',
                        'bluesky': r'bsky\.app/profile/([a-zA-Z0-9.\-]+)',
                        'mastodon': r'(https://[a-zA-Z0-9.\-]+/@[a-zA-Z0-9_]+)',
                        'tiktok': r'tiktok\.com/@([a-zA-Z0-9_.]+)',
                        'github': r'github\.com/([a-zA-Z0-9\-]+)',
                    }

                    for platform, pattern in social_patterns.items():
                        if platform not in social_links_str.lower():
                            match = re.search(pattern, html, re.IGNORECASE)
                            if match:
                                handle = match.group(1)
                                if platform == 'mastodon':
                                    found[f'social_{platform}'] = handle  # already a URL
                                elif platform == 'twitter':
                                    found[f'social_{platform}'] = f"https://x.com/{handle}"
                                elif platform == 'instagram':
                                    found[f'social_{platform}'] = f"https://instagram.com/{handle}"
                                elif platform == 'youtube':
                                    found[f'social_{platform}'] = f"https://youtube.com/@{handle}"
                                elif platform == 'linkedin':
                                    found[f'social_{platform}'] = f"https://linkedin.com/in/{handle}"
                                elif platform == 'bluesky':
                                    found[f'social_{platform}'] = f"https://bsky.app/profile/{handle}"
                                elif platform == 'tiktok':
                                    found[f'social_{platform}'] = f"https://tiktok.com/@{handle}"
                                elif platform == 'github':
                                    found[f'social_{platform}'] = f"https://github.com/{handle}"

        except Exception as e:
            logger.debug(f"Contact scrape failed for {url}: {e}")
            continue
        await asyncio.sleep(1)

    return found


# ---------------------------------------------------------------------------
# Relevance scoring
# ---------------------------------------------------------------------------

def _score_relevance(text: str, keywords: List[str]) -> float:
    """Score 0-1 how relevant a piece of content is to brand keywords."""
    if not text or not keywords:
        return 0.0
    text_lower = text.lower()
    matches = sum(1 for kw in keywords if kw.lower() in text_lower)
    return min(matches / max(len(keywords) * 0.3, 1), 1.0)


# ---------------------------------------------------------------------------
# Main enrichment engine
# ---------------------------------------------------------------------------

class InfluencerEnrichmentEngine:
    """Enriches existing influencer records with more data over time."""

    def __init__(self, db_path: str = "data/influencer_discovery.db"):
        self.db_path = Path(project_root) / db_path
        ensure_enrichment_tables(self.db_path)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def enrich_all(self, brand: str = None, max_influencers: int = 50,
                          stale_days: int = 7) -> Dict[str, Any]:
        """Run enrichment on influencers that haven't been enriched recently.

        Args:
            brand: optional brand filter
            max_influencers: cap per run to stay within rate limits
            stale_days: re-enrich if last enriched > this many days ago
        """
        influencers = self._get_stale_influencers(brand, stale_days, max_influencers)
        logger.info(f"🔄 Enriching {len(influencers)} influencers" +
                     (f" for brand={brand}" if brand else ""))

        stats = {'enriched': 0, 'content_added': 0, 'contacts_found': 0, 'errors': 0}

        async with _make_session() as session:
            for inf in influencers:
                try:
                    result = await self._enrich_one(session, inf)
                    stats['enriched'] += 1
                    stats['content_added'] += result.get('content_added', 0)
                    stats['contacts_found'] += result.get('contacts_found', 0)
                except Exception as e:
                    logger.error(f"Enrichment failed for {inf['name']}: {e}")
                    stats['errors'] += 1
                await asyncio.sleep(1)  # rate limiting

        logger.info(f"✅ Enrichment complete: {stats}")
        return stats

    async def enrich_influencer(self, influencer_id: int) -> Dict[str, Any]:
        """Enrich a single influencer by ID."""
        inf = self._get_influencer_by_id(influencer_id)
        if not inf:
            return {'error': f'Influencer {influencer_id} not found'}
        async with _make_session() as session:
            return await self._enrich_one(session, inf)

    def get_influencer_content(self, influencer_id: int = None, brand: str = None,
                                min_relevance: float = 0.0, limit: int = 50,
                                content_type: str = None) -> List[Dict]:
        """Retrieve tracked content, optionally filtered."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        query = "SELECT * FROM influencer_content WHERE 1=1"
        params: list = []
        if influencer_id:
            query += " AND influencer_id = ?"
            params.append(influencer_id)
        if brand:
            query += " AND brand = ?"
            params.append(brand)
        if min_relevance > 0:
            query += " AND relevance_score >= ?"
            params.append(min_relevance)
        if content_type:
            query += " AND content_type = ?"
            params.append(content_type)
        query += " ORDER BY relevance_score DESC, published_date DESC LIMIT ?"
        params.append(limit)
        rows = conn.execute(query, params).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def get_enrichment_history(self, influencer_id: int) -> List[Dict]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM enrichment_history WHERE influencer_id = ? ORDER BY run_date DESC LIMIT 20",
            (influencer_id,)
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _enrich_one(self, session: aiohttp.ClientSession,
                           inf: Dict) -> Dict[str, Any]:
        """Run all enrichment steps on one influencer."""
        result = {'content_added': 0, 'contacts_found': 0, 'fields_updated': []}
        brand = inf.get('brand', '')
        strategy = BRAND_INFLUENCER_STRATEGIES.get(brand, {})
        keywords = strategy.get('keywords', [])

        # --- 1. Discover additional contacts & social links ---
        new_contacts = await _find_additional_contacts(session, inf)
        if new_contacts:
            self._apply_contact_updates(inf['id'], new_contacts, brand)
            result['contacts_found'] = len(new_contacts)
            result['fields_updated'].extend(new_contacts.keys())

        # --- 2. Fetch recent content per platform ---
        content_items = await self._fetch_content_for_influencer(session, inf, keywords)
        saved = self._save_content(inf['id'], brand, content_items, keywords)
        result['content_added'] = saved

        # --- 3. Update enrichment metadata ---
        self._update_enrichment_meta(inf['id'], result)

        # --- 4. Log history ---
        self._log_enrichment(inf['id'], 'full', 'enrichment_engine',
                             result['fields_updated'])

        logger.info(f"  ✅ {inf['name']}: +{saved} content, +{result['contacts_found']} contacts")
        return result

    async def _fetch_content_for_influencer(self, session: aiohttp.ClientSession,
                                             inf: Dict, keywords: List[str]) -> List[Dict]:
        """Dispatch content fetching based on platform."""
        platform = inf.get('primary_platform', '')
        social_links = inf.get('social_links', '') or ''
        items: List[Dict] = []

        # Parse profile URL from social_links  (format: "platform:https://...")
        profile_urls: Dict[str, str] = {}
        for part in social_links.split(','):
            if ':' in part:
                plat = part.split(':')[0].strip()
                url = part.split(':', 1)[1].strip()
                profile_urls[plat] = url

        # YouTube
        yt_url = profile_urls.get('youtube', '')
        yt_user = ''
        if platform == 'youtube':
            yt_url = yt_url or profile_urls.get(platform, '')
        if yt_url:
            items.extend(await _fetch_youtube_content(session, yt_url, yt_user, keywords))

        # Bluesky
        bsky_url = profile_urls.get('bluesky', '')
        if platform == 'bluesky' or bsky_url:
            handle = ''
            check_url = bsky_url or profile_urls.get(platform, '')
            if check_url and 'bsky.app/profile/' in check_url:
                handle = check_url.split('bsky.app/profile/')[-1].split('/')[0]
            if handle:
                items.extend(await _fetch_bluesky_content(session, handle, keywords))

        # Mastodon
        masto_url = profile_urls.get('mastodon', '')
        if platform == 'mastodon' or masto_url:
            check_url = masto_url or profile_urls.get(platform, '')
            if check_url:
                items.extend(await _fetch_mastodon_content(session, check_url, keywords))

        # Podcasts — use RSS feed if available
        if platform == 'podcast':
            rss = self._get_podcast_rss(inf['id'])
            if rss:
                items.extend(await _fetch_podcast_episodes(session, rss))

        return items

    def _get_podcast_rss(self, influencer_id: int) -> str:
        conn = sqlite3.connect(self.db_path)
        row = conn.execute(
            "SELECT rss_feed FROM podcast_profiles WHERE influencer_id = ?",
            (influencer_id,)
        ).fetchone()
        conn.close()
        return row[0] if row else ''

    def _save_content(self, influencer_id: int, brand: str,
                       items: List[Dict], keywords: List[str]) -> int:
        """Save content items, returning count of newly inserted rows."""
        if not items:
            return 0
        conn = sqlite3.connect(self.db_path)
        saved = 0
        for item in items:
            if not item.get('url'):
                continue
            relevance = _score_relevance(
                f"{item.get('title', '')} {item.get('description', '')}",
                keywords
            )
            try:
                conn.execute("""
                    INSERT OR IGNORE INTO influencer_content
                    (influencer_id, platform, content_type, title, url, description,
                     published_date, likes, comments, shares, views,
                     relevance_score, brand, tags)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    influencer_id,
                    item.get('platform', ''),
                    item.get('content_type', 'post'),
                    item.get('title', ''),
                    item['url'],
                    item.get('description', ''),
                    item.get('published_date', ''),
                    item.get('likes', 0),
                    item.get('comments', 0),
                    item.get('shares', 0),
                    item.get('views', 0),
                    relevance,
                    brand,
                    json.dumps(item.get('tags', [])),
                ))
                if conn.total_changes:
                    saved += 1
            except sqlite3.IntegrityError:
                pass
        conn.commit()
        conn.close()
        return saved

    def _apply_contact_updates(self, influencer_id: int,
                                contacts: Dict[str, str], brand: str):
        """Apply discovered contacts/links to the influencer record."""
        conn = sqlite3.connect(self.db_path)

        # Update email if found
        if contacts.get('email'):
            conn.execute(
                "UPDATE influencers SET contact_email = ? WHERE id = ? AND (contact_email IS NULL OR contact_email = '')",
                (contacts['email'], influencer_id)
            )

        # Add new social profiles
        for key, url in contacts.items():
            if key.startswith('social_'):
                platform = key.replace('social_', '')
                try:
                    conn.execute("""
                        INSERT OR IGNORE INTO social_profiles
                        (influencer_id, platform, username, display_name, profile_url)
                        VALUES (?, ?, ?, ?, ?)
                    """, (
                        influencer_id,
                        platform,
                        url.rstrip('/').split('/')[-1],
                        '',
                        url,
                    ))
                except sqlite3.IntegrityError:
                    pass

        conn.commit()
        conn.close()

    def _update_enrichment_meta(self, influencer_id: int, result: Dict):
        """Update enrichment_score and last_enriched on the influencer."""
        conn = sqlite3.connect(self.db_path)
        # Simple score: how much data we have
        content_count = conn.execute(
            "SELECT COUNT(*) FROM influencer_content WHERE influencer_id = ?",
            (influencer_id,)
        ).fetchone()[0]
        social_count = conn.execute(
            "SELECT COUNT(*) FROM social_profiles WHERE influencer_id = ?",
            (influencer_id,)
        ).fetchone()[0]
        inf = conn.execute(
            "SELECT contact_email, website FROM influencers WHERE id = ?",
            (influencer_id,)
        ).fetchone()

        score = 0.0
        score += min(content_count / 10.0, 0.4)   # up to 0.4 for content
        score += min(social_count / 5.0, 0.3)       # up to 0.3 for social links
        if inf and inf[0]:  # has email
            score += 0.15
        if inf and inf[1]:  # has website
            score += 0.15

        conn.execute(
            "UPDATE influencers SET enrichment_score = ?, last_enriched = ? WHERE id = ?",
            (round(score, 2), datetime.now().isoformat(), influencer_id)
        )
        conn.commit()
        conn.close()

    def _log_enrichment(self, influencer_id: int, enrichment_type: str,
                         source: str, fields: List[str]):
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            INSERT INTO enrichment_history
            (influencer_id, enrichment_type, source, fields_updated, success)
            VALUES (?, ?, ?, ?, ?)
        """, (influencer_id, enrichment_type, source, json.dumps(fields), True))
        conn.commit()
        conn.close()

    # ------------------------------------------------------------------
    # DB queries
    # ------------------------------------------------------------------

    def _get_stale_influencers(self, brand: str, stale_days: int,
                                limit: int) -> List[Dict]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cutoff = (datetime.now() - timedelta(days=stale_days)).isoformat()
        query = """
            SELECT i.*,
                   GROUP_CONCAT(sp.platform || ':' || sp.profile_url) as social_links
            FROM influencers i
            LEFT JOIN social_profiles sp ON i.id = sp.influencer_id
            WHERE (i.deleted IS NULL OR i.deleted = FALSE)
              AND (i.last_enriched IS NULL OR i.last_enriched < ?)
        """
        params: list = [cutoff]
        if brand:
            query += " AND i.brand = ?"
            params.append(brand)
        query += " GROUP BY i.id ORDER BY i.last_enriched ASC NULLS FIRST LIMIT ?"
        params.append(limit)
        rows = conn.execute(query, params).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def _get_influencer_by_id(self, influencer_id: int) -> Optional[Dict]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        row = conn.execute("""
            SELECT i.*,
                   GROUP_CONCAT(sp.platform || ':' || sp.profile_url) as social_links
            FROM influencers i
            LEFT JOIN social_profiles sp ON i.id = sp.influencer_id
            WHERE i.id = ?
            GROUP BY i.id
        """, (influencer_id,)).fetchone()
        conn.close()
        return dict(row) if row else None


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

async def run_enrichment_cli(brand: str = None, influencer_id: int = None,
                              max_influencers: int = 50):
    engine = InfluencerEnrichmentEngine()
    if influencer_id:
        result = await engine.enrich_influencer(influencer_id)
        print(f"✅ Enrichment result: {json.dumps(result, indent=2)}")
    else:
        stats = await engine.enrich_all(brand=brand, max_influencers=max_influencers)
        print(f"\n📊 Enrichment Summary")
        print(f"  Influencers enriched: {stats['enriched']}")
        print(f"  Content items added:  {stats['content_added']}")
        print(f"  New contacts found:   {stats['contacts_found']}")
        print(f"  Errors:               {stats['errors']}")


def main():
    parser = argparse.ArgumentParser(description='Influencer Enrichment Engine')
    parser.add_argument('--brand', type=str, help='Brand to enrich')
    parser.add_argument('--all', action='store_true', help='Enrich all brands')
    parser.add_argument('--influencer-id', type=int, help='Enrich a specific influencer')
    parser.add_argument('--max', type=int, default=50, help='Max influencers per run')
    args = parser.parse_args()

    if args.influencer_id:
        asyncio.run(run_enrichment_cli(influencer_id=args.influencer_id))
    elif args.all:
        asyncio.run(run_enrichment_cli(max_influencers=args.max))
    elif args.brand:
        asyncio.run(run_enrichment_cli(brand=args.brand, max_influencers=args.max))
    else:
        parser.print_help()


if __name__ == "__main__":
    main()

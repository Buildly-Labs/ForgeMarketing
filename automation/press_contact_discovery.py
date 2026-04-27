#!/usr/bin/env python3
"""Discover press contacts for dashboard-managed brands."""

import argparse
import logging
import re
import sqlite3
import sys
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import quote, urljoin, urlparse

import requests

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def _normalize_brand_key(value: str) -> str:
    """Normalize brand identifiers for resilient matching."""
    if not value:
        return ''
    normalized = re.sub(r'[^a-z0-9]+', '_', value.lower().strip())
    return normalized.strip('_')


class PressContactDiscovery:
    """Discover real publication contact emails from newsroom and press pages."""

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = Path(db_path or (project_root / 'data' / 'marketing_dashboard.db'))
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': (
                'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
                'AppleWebKit/537.36 (KHTML, like Gecko) '
                'Chrome/124.0.0.0 Safari/537.36'
            )
        })

    def discover_contacts(self, brand_name: str, scope: str = 'all', max_results: int = 12) -> Dict[str, object]:
        brand = self._get_brand(brand_name)
        if not brand:
            raise ValueError(f'Unknown brand: {brand_name}')

        scopes = ['local', 'national', 'international'] if scope == 'all' else [scope]
        contacts: List[Dict[str, str]] = []
        seen = set()

        for current_scope in scopes:
            for query in self._build_queries(brand, current_scope):
                for item in self._search_news(query, max_results=max_results):
                    email = self._discover_outlet_email(item.get('source_url') or item.get('article_url'))
                    if not email:
                        continue

                    dedupe_key = email.lower()
                    if dedupe_key in seen:
                        continue
                    seen.add(dedupe_key)

                    contacts.append({
                        'name': f"{item['outlet']} News Desk",
                        'outlet': item['outlet'],
                        'email': email,
                        'title': 'Editorial Desk',
                        'beat': self._infer_beat(brand),
                        'scope': current_scope,
                        'region': brand.get('display_name', '') if current_scope == 'local' else '',
                        'website': item.get('source_url', ''),
                        'notes': (
                            f"Discovered for {brand['display_name']} from Google News search. "
                            f"Headline: {item.get('title', '')}"
                        ),
                    })
                    if len(contacts) >= max_results:
                        break
                if len(contacts) >= max_results:
                    break
            if len(contacts) >= max_results:
                break

        saved_count = self._save_contacts(contacts)
        return {
            'brand': brand.get('name', brand_name),
            'brand_display_name': brand.get('display_name', brand_name),
            'scope': scope,
            'discovered_count': len(contacts),
            'saved_count': saved_count,
            'contacts': contacts,
        }

    def _get_brand(self, brand_name: str) -> Optional[Dict[str, str]]:
        if not self.db_path.exists():
            return None

        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(
                "SELECT id, name, display_name, description, website_url FROM brands WHERE is_active = 1"
            ).fetchall()

            requested_raw = (brand_name or '').strip().lower()
            requested_normalized = _normalize_brand_key(brand_name)

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

    def _build_queries(self, brand: Dict[str, str], scope: str) -> List[str]:
        display_name = brand.get('display_name', brand['name'])
        description = (brand.get('description') or '').strip()
        keyword = description.split('.')[0][:80] if description else display_name
        queries = {
            'local': [
                f'"{display_name}" local business journal newsroom contact email',
                f'"{display_name}" regional news press contact',
            ],
            'national': [
                f'"{display_name}" technology business publication newsroom email',
                f'"{display_name}" startup press contact {keyword}',
            ],
            'international': [
                f'"{display_name}" global technology publication editorial contact',
                f'"{display_name}" international business news press email',
            ],
        }
        return queries.get(scope, [f'"{display_name}" press contact'])

    def _search_news(self, query: str, max_results: int = 10) -> List[Dict[str, str]]:
        rss_url = f'https://news.google.com/rss/search?q={quote(query)}&hl=en-US&gl=US&ceid=US:en'
        try:
            response = self.session.get(rss_url, timeout=20)
            response.raise_for_status()
            root = ET.fromstring(response.content)
        except Exception as exc:
            logger.warning('News RSS fetch failed for %s: %s', query, exc)
            return []

        items: List[Dict[str, str]] = []
        for item in root.findall('.//item')[:max_results]:
            source_node = item.find('source')
            source_url = source_node.attrib.get('url', '') if source_node is not None else ''
            outlet = (source_node.text or '').strip() if source_node is not None and source_node.text else ''
            article_url = (item.findtext('link') or '').strip()
            title = (item.findtext('title') or '').strip()
            if not outlet and source_url:
                outlet = urlparse(source_url).netloc.replace('www.', '')
            if not outlet:
                continue
            items.append({
                'title': title,
                'article_url': article_url,
                'outlet': outlet,
                'source_url': source_url,
            })
        return items

    def _discover_outlet_email(self, source_url: str) -> Optional[str]:
        if not source_url:
            return None

        parsed = urlparse(source_url)
        base_url = f'{parsed.scheme or "https"}://{parsed.netloc}'
        candidates = [
            base_url,
            urljoin(base_url, '/contact'),
            urljoin(base_url, '/contact-us'),
            urljoin(base_url, '/about'),
            urljoin(base_url, '/newsroom'),
            urljoin(base_url, '/press'),
        ]

        for candidate in candidates:
            try:
                response = self.session.get(candidate, timeout=15)
                if response.status_code != 200:
                    continue
                emails = re.findall(
                    r'[A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,}',
                    response.text,
                    flags=re.IGNORECASE,
                )
                for email in emails:
                    lower = email.lower()
                    if any(token in lower for token in ['noreply', 'example.com', 'wixpress', 'wordpress']):
                        continue
                    return email
            except Exception:
                continue
        return None

    def _infer_beat(self, brand: Dict[str, str]) -> str:
        description = (brand.get('description') or '').lower()
        if any(token in description for token in ['software', 'tech', 'ai', 'digital', 'platform']):
            return 'technology'
        if any(token in description for token in ['health', 'therapy', 'wellness']):
            return 'health'
        return 'business'

    def _save_contacts(self, contacts: List[Dict[str, str]]) -> int:
        if not contacts:
            return 0

        conn = sqlite3.connect(self.db_path)
        saved = 0
        try:
            for contact in contacts:
                existing = conn.execute(
                    'SELECT id FROM press_contacts WHERE lower(email) = lower(?)',
                    (contact['email'],),
                ).fetchone()
                if existing:
                    continue
                now = datetime.utcnow().isoformat()
                conn.execute(
                    """
                    INSERT INTO press_contacts
                    (name, outlet, email, title, beat, scope, region, website, notes, is_active, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
                    """,
                    (
                        contact['name'],
                        contact['outlet'],
                        contact['email'],
                        contact.get('title', ''),
                        contact.get('beat', ''),
                        contact.get('scope', 'national'),
                        contact.get('region', ''),
                        contact.get('website', ''),
                        contact.get('notes', ''),
                        now,
                        now,
                    ),
                )
                saved += 1
            conn.commit()
            return saved
        finally:
            conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description='Discover press contacts for a brand')
    parser.add_argument('--brand', required=True, help='Dashboard brand name')
    parser.add_argument('--scope', default='all', choices=['all', 'local', 'national', 'international'])
    parser.add_argument('--max', type=int, default=12, help='Maximum contacts to save')
    args = parser.parse_args()

    discovery = PressContactDiscovery()
    result = discovery.discover_contacts(args.brand, scope=args.scope, max_results=args.max)
    print(result)


if __name__ == '__main__':
    main()
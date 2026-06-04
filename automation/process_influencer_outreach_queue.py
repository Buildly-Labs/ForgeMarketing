#!/usr/bin/env python3
"""Process queued influencer outreach touches into actionable outreach items."""

import argparse
import sqlite3
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

project_root = Path(__file__).parent.parent
DB_PATH = project_root / 'data' / 'unified_contacts.db'


def _now_iso() -> str:
    return datetime.utcnow().isoformat(timespec='seconds')


class InfluencerOutreachQueueProcessor:
    """Prepare and process queued influencer outreach touches."""

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or DB_PATH

    def _fetch_queue_items(
        self,
        brand: Optional[str] = None,
        platform: Optional[str] = None,
        status: str = 'queued',
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        query = """
            SELECT
                ct.id AS touch_id,
                ct.contact_id,
                ct.subject,
                ct.message,
                ct.platform AS touch_platform,
                ct.status,
                ct.created_at,
                c.name,
                c.email,
                c.brand,
                c.platform AS contact_platform,
                c.linkedin_url,
                c.twitter_handle,
                c.instagram_handle,
                c.bluesky_handle,
                c.tiktok_handle,
                c.youtube_channel,
                c.website_url,
                c.notes
            FROM contact_touches ct
            JOIN contacts c ON c.id = ct.contact_id
            WHERE c.contact_type = 'influencer'
              AND ct.touch_type = 'social_dm'
              AND ct.touch_direction = 'outbound'
              AND ct.status = ?
        """
        params: List[Any] = [status]

        if brand:
            query += " AND c.brand = ?"
            params.append(brand)

        if platform and platform != 'all':
            query += " AND (ct.platform = ? OR c.platform = ?)"
            params.extend([platform, platform])

        query += " ORDER BY ct.created_at ASC LIMIT ?"
        params.append(limit)

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(query, params).fetchall()
            return [dict(row) for row in rows]

    def _resolve_target(self, item: Dict[str, Any]) -> Dict[str, str]:
        platform = (item.get('touch_platform') or item.get('contact_platform') or '').lower()

        if platform == 'linkedin' and item.get('linkedin_url'):
            return {'channel': 'linkedin', 'target': item['linkedin_url']}
        if platform == 'twitter' and item.get('twitter_handle'):
            return {'channel': 'twitter', 'target': item['twitter_handle']}
        if platform == 'instagram' and item.get('instagram_handle'):
            return {'channel': 'instagram', 'target': item['instagram_handle']}
        if platform == 'bluesky' and item.get('bluesky_handle'):
            return {'channel': 'bluesky', 'target': item['bluesky_handle']}
        if platform == 'tiktok' and item.get('tiktok_handle'):
            return {'channel': 'tiktok', 'target': item['tiktok_handle']}
        if platform == 'youtube' and item.get('youtube_channel'):
            return {'channel': 'youtube', 'target': item['youtube_channel']}

        # Fallback preference by available profile fields.
        if item.get('linkedin_url'):
            return {'channel': 'linkedin', 'target': item['linkedin_url']}
        if item.get('twitter_handle'):
            return {'channel': 'twitter', 'target': item['twitter_handle']}
        if item.get('instagram_handle'):
            return {'channel': 'instagram', 'target': item['instagram_handle']}
        if item.get('bluesky_handle'):
            return {'channel': 'bluesky', 'target': item['bluesky_handle']}
        if item.get('tiktok_handle'):
            return {'channel': 'tiktok', 'target': item['tiktok_handle']}
        if item.get('youtube_channel'):
            return {'channel': 'youtube', 'target': item['youtube_channel']}
        if item.get('email'):
            return {'channel': 'email', 'target': item['email']}
        if item.get('website_url'):
            return {'channel': 'website', 'target': item['website_url']}

        notes = item.get('notes') or ''
        # Try to recover any social URL from notes if structured fields are missing.
        for pattern, channel in [
            (r'https?://(?:www\.)?linkedin\.com/[^\s]+', 'linkedin'),
            (r'https?://(?:www\.)?(?:twitter|x)\.com/[^\s]+', 'twitter'),
            (r'https?://(?:www\.)?instagram\.com/[^\s]+', 'instagram'),
            (r'https?://(?:www\.)?bsky\.app/profile/[^\s]+', 'bluesky'),
            (r'https?://(?:www\.)?(?:mastodon\.[^\s/]+|fosstodon\.org|hachyderm\.io)/[^\s]+', 'mastodon'),
            (r'https?://(?:www\.)?youtube\.com/[^\s]+', 'youtube'),
        ]:
            match = re.search(pattern, notes)
            if match:
                return {'channel': channel, 'target': match.group(0)}

        return {'channel': 'unknown', 'target': ''}

    def _prepare_message(self, item: Dict[str, Any], target: Dict[str, str]) -> str:
        base = (item.get('message') or '').strip()
        if not base:
            base = f"Hi {item.get('name', 'there')}, we'd love to explore a collaboration with {item.get('brand', 'our team')}."

        prep_suffix = (
            f"\n\n[Prepared {_now_iso()} UTC]"
            f"\nChannel: {target.get('channel', 'unknown')}"
            f"\nTarget: {target.get('target', 'n/a')}"
        )

        if '[Prepared ' in base:
            return base
        return base + prep_suffix

    def process(
        self,
        brand: Optional[str] = None,
        platform: Optional[str] = None,
        limit: int = 100,
        status: str = 'queued',
        dry_run: bool = False,
        auto_mark_sent: bool = False,
    ) -> Dict[str, Any]:
        items = self._fetch_queue_items(
            brand=brand,
            platform=platform,
            status=status,
            limit=limit,
        )

        processed = 0
        failed = 0
        ready = 0
        sent = 0
        details: List[Dict[str, Any]] = []

        with sqlite3.connect(self.db_path) as conn:
            for item in items:
                touch_id = item['touch_id']
                target = self._resolve_target(item)

                if not target.get('target'):
                    # Keep flow moving: push to manual-ready instead of hard failure.
                    next_status = 'ready'
                    prepared_message = self._prepare_message(item, {'channel': 'manual_review', 'target': 'n/a'})
                    details.append({
                        'touch_id': touch_id,
                        'contact_id': item['contact_id'],
                        'name': item.get('name'),
                        'status': next_status,
                        'reason': 'No direct target available; requires manual review',
                        'target_channel': 'manual_review',
                        'target': 'n/a',
                    })
                    processed += 1
                    ready += 1
                    if not dry_run:
                        conn.execute(
                            "UPDATE contact_touches SET status = ?, message = ?, response_text = ? WHERE id = ?",
                            (
                                next_status,
                                prepared_message,
                                'No direct target available; queued for manual review',
                                touch_id,
                            ),
                        )
                    continue

                next_status = 'sent' if auto_mark_sent else 'ready'
                prepared_message = self._prepare_message(item, target)

                details.append({
                    'touch_id': touch_id,
                    'contact_id': item['contact_id'],
                    'name': item.get('name'),
                    'status': next_status,
                    'target_channel': target.get('channel'),
                    'target': target.get('target'),
                })

                processed += 1
                if next_status == 'sent':
                    sent += 1
                else:
                    ready += 1

                if not dry_run:
                    conn.execute(
                        """
                        UPDATE contact_touches
                        SET status = ?, message = ?, response_text = ?
                        WHERE id = ?
                        """,
                        (
                            next_status,
                            prepared_message,
                            f"Prepared at {_now_iso()} UTC for {target.get('channel')}:{target.get('target')}",
                            touch_id,
                        ),
                    )

            if not dry_run:
                conn.commit()

        return {
            'success': True,
            'dry_run': dry_run,
            'auto_mark_sent': auto_mark_sent,
            'source_status': status,
            'requested': len(items),
            'processed': processed,
            'ready': ready,
            'sent': sent,
            'failed': failed,
            'details': details[:200],
        }


def main() -> int:
    parser = argparse.ArgumentParser(description='Process influencer outreach queue')
    parser.add_argument('--brand', default=None)
    parser.add_argument('--platform', default=None)
    parser.add_argument('--limit', type=int, default=100)
    parser.add_argument('--status', default='queued')
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--auto-mark-sent', action='store_true')
    args = parser.parse_args()

    processor = InfluencerOutreachQueueProcessor()
    result = processor.process(
        brand=args.brand,
        platform=args.platform,
        limit=args.limit,
        status=args.status,
        dry_run=args.dry_run,
        auto_mark_sent=args.auto_mark_sent,
    )
    print(result)
    return 0 if result.get('success') else 1


if __name__ == '__main__':
    raise SystemExit(main())

#!/usr/bin/env python3
"""Provider-backed social outreach dispatchers with webhook fallback."""

import sqlite3
from pathlib import Path
from typing import Any, Dict, Optional
import os
import requests

project_root = Path(__file__).parent.parent
DB_PATH = project_root / 'data' / 'marketing_dashboard.db'


class SocialOutreachDispatcher:
    """Dispatch outreach messages to supported social channels."""

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or DB_PATH
        self._config_cache: Dict[str, str] = {}

    def _load_system_config(self, key: str) -> Optional[str]:
        if key in self._config_cache:
            return self._config_cache[key] or None

        value: Optional[str] = os.getenv(key)
        if value:
            self._config_cache[key] = value
            return value

        try:
            with sqlite3.connect(self.db_path) as conn:
                row = conn.execute(
                    "SELECT value FROM system_configs WHERE key = ? LIMIT 1",
                    (key,),
                ).fetchone()
                if row and row[0]:
                    self._config_cache[key] = str(row[0])
                    return self._config_cache[key]
        except Exception:
            pass

        self._config_cache[key] = ''
        return None

    def _dispatch_via_webhook(self, webhook_url: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        try:
            response = requests.post(webhook_url, json=payload, timeout=20)
            if 200 <= response.status_code < 300:
                return {
                    'success': True,
                    'provider': 'webhook',
                    'status_code': response.status_code,
                    'response': response.text[:500],
                }
            return {
                'success': False,
                'provider': 'webhook',
                'status_code': response.status_code,
                'error': response.text[:500],
            }
        except Exception as exc:
            return {'success': False, 'provider': 'webhook', 'error': str(exc)}

    def _dispatch_twitter_dm(self, target: str, message: str, metadata: Dict[str, Any]) -> Dict[str, Any]:
        token = self._load_system_config('TWITTER_BEARER_TOKEN')
        if not token:
            return {'success': False, 'provider': 'twitter', 'error': 'TWITTER_BEARER_TOKEN not configured'}

        handle = (target or '').strip().lstrip('@')
        if not handle:
            return {'success': False, 'provider': 'twitter', 'error': 'Missing target handle'}

        headers = {
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json',
        }

        try:
            user_lookup = requests.get(
                f'https://api.twitter.com/2/users/by/username/{handle}',
                headers=headers,
                timeout=20,
            )
            if user_lookup.status_code != 200:
                return {
                    'success': False,
                    'provider': 'twitter',
                    'status_code': user_lookup.status_code,
                    'error': f'User lookup failed: {user_lookup.text[:500]}',
                }

            user_data = user_lookup.json().get('data') or {}
            participant_id = user_data.get('id')
            if not participant_id:
                return {'success': False, 'provider': 'twitter', 'error': 'Could not resolve user id'}

            dm_payload = {'text': message}
            dm_resp = requests.post(
                f'https://api.twitter.com/2/dm_conversations/with/{participant_id}/messages',
                headers=headers,
                json=dm_payload,
                timeout=20,
            )
            if 200 <= dm_resp.status_code < 300:
                return {
                    'success': True,
                    'provider': 'twitter',
                    'status_code': dm_resp.status_code,
                    'response': dm_resp.text[:500],
                }
            return {
                'success': False,
                'provider': 'twitter',
                'status_code': dm_resp.status_code,
                'error': dm_resp.text[:500],
            }
        except Exception as exc:
            return {'success': False, 'provider': 'twitter', 'error': str(exc)}

    def _dispatch_linkedin_message(self, target: str, message: str, metadata: Dict[str, Any]) -> Dict[str, Any]:
        access_token = self._load_system_config('LINKEDIN_ACCESS_TOKEN')
        author_urn = self._load_system_config('LINKEDIN_AUTHOR_URN')
        if not access_token or not author_urn:
            return {
                'success': False,
                'provider': 'linkedin',
                'error': 'LINKEDIN_ACCESS_TOKEN or LINKEDIN_AUTHOR_URN not configured',
            }

        headers = {
            'Authorization': f'Bearer {access_token}',
            'X-Restli-Protocol-Version': '2.0.0',
            'Content-Type': 'application/json',
        }

        payload = {
            'author': author_urn,
            'lifecycleState': 'PUBLISHED',
            'specificContent': {
                'com.linkedin.ugc.ShareContent': {
                    'shareCommentary': {'text': message},
                    'shareMediaCategory': 'NONE',
                }
            },
            'visibility': {'com.linkedin.ugc.MemberNetworkVisibility': 'PUBLIC'},
        }

        try:
            resp = requests.post('https://api.linkedin.com/v2/ugcPosts', headers=headers, json=payload, timeout=20)
            if 200 <= resp.status_code < 300:
                return {
                    'success': True,
                    'provider': 'linkedin',
                    'status_code': resp.status_code,
                    'response': resp.text[:500],
                }
            return {
                'success': False,
                'provider': 'linkedin',
                'status_code': resp.status_code,
                'error': resp.text[:500],
            }
        except Exception as exc:
            return {'success': False, 'provider': 'linkedin', 'error': str(exc)}

    def dispatch(self, channel: str, target: str, message: str, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        metadata = metadata or {}
        channel = (channel or '').strip().lower()

        if channel == 'twitter':
            result = self._dispatch_twitter_dm(target, message, metadata)
            if result.get('success'):
                return result
            webhook = self._load_system_config('TWITTER_OUTREACH_WEBHOOK_URL')
            if webhook:
                return self._dispatch_via_webhook(webhook, {
                    'channel': channel,
                    'target': target,
                    'message': message,
                    'metadata': metadata,
                    'fallback_from': 'twitter_api',
                })
            return result

        if channel == 'linkedin':
            result = self._dispatch_linkedin_message(target, message, metadata)
            if result.get('success'):
                return result
            webhook = self._load_system_config('LINKEDIN_OUTREACH_WEBHOOK_URL')
            if webhook:
                return self._dispatch_via_webhook(webhook, {
                    'channel': channel,
                    'target': target,
                    'message': message,
                    'metadata': metadata,
                    'fallback_from': 'linkedin_api',
                })
            return result

        # For all other channels, use generic webhook if configured.
        webhook = self._load_system_config('SOCIAL_OUTREACH_WEBHOOK_URL')
        if webhook:
            return self._dispatch_via_webhook(webhook, {
                'channel': channel,
                'target': target,
                'message': message,
                'metadata': metadata,
            })

        return {
            'success': False,
            'provider': channel or 'unknown',
            'error': 'No dispatcher configured for this channel',
        }

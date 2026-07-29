#!/usr/bin/env python3
"""
Twitter Ad / Content Scheduler
Posts brand-safe content to Twitter/X with explicit opt-in.

Safe defaults:
- No posting without `--run`
- No infinite loop without `--count` or `--hours`
- Brand-aware tweet templates from `data/tweet_templates.json`
"""

import argparse
import json
import logging
import os
import random
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    import requests
    from requests_oauthlib import OAuth1Session
except ImportError:  # pragma: no cover - optional dep
    requests = None  # type: ignore
    OAuth1Session = None  # type: ignore

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

logger = logging.getLogger('tweet_scheduler')


def setup_logging(verbose: bool = False) -> None:
    level = logging.INFO if not verbose else logging.DEBUG
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    )


def brand_templates_path() -> Path:
    return PROJECT_ROOT / 'data' / 'tweet_templates.json'


def load_brand_templates(path: Path) -> Dict[str, List[str]]:
    if not path.exists():
        logger.warning('Tweet templates file not found: %s', path)
        return {}
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        if isinstance(data, dict):
            return {str(k): [str(item) for item in v if str(item).strip()] for k, v in data.items() if isinstance(v, list)}
    except Exception as exc:
        logger.error('Failed to load tweet templates from %s: %s', path, exc)
    return {}


def pick_brand_text(brand: str, templates: Dict[str, List[str]]) -> Optional[str]:
    if not templates:
        return None
    options = templates.get(brand.lower()) or templates.get('default') or []
    if not options:
        return None
    text = random.choice(options)
    return text.replace('{brand}', brand.replace('_', ' ').replace('-', ' ').title())


def build_oauth_session() -> 'OAuth1Session':
    if OAuth1Session is None:
        raise RuntimeError('requests-oauthlib is required for OAuth1 posting')
    consumer_key = os.environ.get('TWITTER_CONSUMER_KEY', '')
    consumer_secret = os.environ.get('TWITTER_CONSUMER_SECRET', '')
    access_token = os.environ.get('TWITTER_ACCESS_TOKEN', '')
    access_token_secret = os.environ.get('TWITTER_ACCESS_TOKEN_SECRET', '')
    if not all([consumer_key, consumer_secret, access_token, access_token_secret]):
        raise RuntimeError('Twitter OAuth1 credentials are not fully configured')
    return OAuth1Session(
        consumer_key,
        client_secret=consumer_secret,
        resource_owner_key=access_token,
        resource_owner_secret=access_token_secret,
    )


def post_tweet(text: str, session: Optional['OAuth1Session'] = None) -> Dict[str, Any]:
    """
    Posts a tweet. Requires a valid OAuth1 session.
    Returns a dict with at least `success` and either `tweet_id` or `error`.
    """
    if requests is None:
        raise RuntimeError('requests is required for posting')
    if session is None:
        raise RuntimeError('A twitter session is required to post')

    response = session.post(
        'https://api.twitter.com/2/tweets',
        json={'text': text},
    )
    if response.status_code == 201:
        data = response.json() or {}
        return {
            'success': True,
            'tweet_id': data.get('data', {}).get('id'),
            'response': data,
        }
    body = response.text
    try:
        body_json = response.json()
        body = json.dumps(body_json)
    except Exception:
        pass
    return {'success': False, 'status_code': response.status_code, 'body': body}


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Twitter content scheduler')
    parser.add_argument('--templates', type=Path, default=brand_templates_path(), help='JSON file with brand tweet templates')
    parser.add_argument('--brand', type=str, default='', help='Brand key for template-aware posting')
    parser.add_argument('--count', type=int, default=0, help='Number of posts; 0 disables looped posting')
    parser.add_argument('--interval', type=int, default=3600, help='Seconds between posts when count > 1')
    parser.add_argument('--text', type=str, default='', help='Post a single tweet and exit')
    parser.add_argument('--run', action='store_true', help='Explicit opt-in to actually post')
    parser.add_argument('--dry-run', action='store_true', help='Log actions without posting')
    parser.add_argument('--verbose', action='store_true', help='Enable debug logging')
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    setup_logging(verbose=args.verbose)

    templates = load_brand_templates(args.templates)
    if not templates:
        logger.error('Missing tweet templates; add entries to %s or pass --templates', args.templates)
        return 1

    if args.text:
        texts = [args.text]
    elif args.brand:
        text = pick_brand_text(args.brand, templates)
        if not text:
            logger.error('No templates found for brand: %s', args.brand)
            return 1
        texts = [text]
    else:
        texts = [t for values in templates.values() for t in values if str(t).strip()]
    if not texts:
        logger.error('No tweet content available in %s', args.templates)
        return 1

    if not args.run and not args.dry_run:
        logger.error('Refusing to post without --run or --dry-run')
        return 2

    if args.count < 0:
        logger.error('--count must be >= 0')
        return 2

    session = None
    if args.run:
        try:
            session = build_oauth_session()
        except RuntimeError as exc:
            logger.error('Cannot post: %s', exc)
            return 2

    iterations = args.count if args.count > 0 else 1
    success_count = 0
    failure_count = 0

    for index in range(iterations):
        text = random.choice(texts)
        logger.info('[%s] %s', datetime.now().isoformat(timespec='seconds'), text)
        if args.run:
            try:
                result = post_tweet(text, session=session)
                if result.get('success'):
                    logger.info('Posted tweet id=%s', result.get('tweet_id'))
                    success_count += 1
                else:
                    logger.error('Post failed: %s', result)
                    failure_count += 1
            except Exception as exc:
                logger.error('Post exception: %s', exc)
                failure_count += 1
        elif args.dry_run:
            logger.info('Dry run: would post')
            success_count += 1

        if index < iterations - 1 and args.interval > 0:
            time.sleep(args.interval)

    logger.info('Completed: %d success, %d failure', success_count, failure_count)
    return 0 if failure_count == 0 else 1


if __name__ == '__main__':
    raise SystemExit(main())

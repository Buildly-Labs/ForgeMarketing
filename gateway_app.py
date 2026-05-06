#!/usr/bin/env python3
"""
Buildly Gateway — unified login + app launcher.
Shares the same database and User model with ForgeMarketing.
"""

import os
import sys
import uuid
import base64
import hashlib
import hmac
import json
import time
from pathlib import Path
from urllib.parse import quote

# Ensure ForgeMarketing is on the path so we can reuse its models
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

import boto3
from flask import Flask, jsonify, render_template, redirect, request, session, g
from flask_login import LoginManager, current_user, login_required

# Load .env
try:
    from dotenv import load_dotenv
    load_dotenv(PROJECT_ROOT / '.env')
except ImportError:
    pass

app = Flask(__name__, template_folder='gateway/templates', static_folder='gateway/static')
app.secret_key = os.getenv('FLASK_SECRET_KEY', 'marketing-automation-dashboard-2025')

AUTH_COOKIE_NAME = 'forge_auth'
SHARED_SECRET = os.getenv('SHARED_AUTH_SECRET', 'forge-shared-auth-2025')
MAX_AGE_SECONDS = 60 * 60 * 24 * 14


def _spaces_config():
    bucket = os.getenv('AWS_STORAGE_BUCKET_NAME', 'cms-static')
    endpoint = os.getenv('AWS_S3_ENDPOINT_URL', 'https://cms-static.nyc3.digitaloceanspaces.com')
    custom_domain = os.getenv('AWS_S3_CUSTOM_DOMAIN', 'cms-static.nyc3.digitaloceanspaces.com')
    return {
        'bucket': bucket,
        'endpoint': endpoint,
        'region': os.getenv('AWS_REGION', 'nyc3'),
        'key': os.getenv('AWS_ACCESS_KEY_ID', 'DO00MW9V6QPPJKVCGHYA'),
        'secret': os.getenv('SPACES_SECRET', ''),
        'custom_domain': custom_domain,
    }


def _spaces_client():
    cfg = _spaces_config()
    session = boto3.session.Session()
    return session.client(
        's3',
        region_name=cfg['region'],
        endpoint_url=cfg['endpoint'],
        aws_access_key_id=cfg['key'],
        aws_secret_access_key=cfg['secret'],
    )


def _public_url(key: str) -> str:
    cfg = _spaces_config()
    return f"https://{cfg['custom_domain'].rstrip('/')}/{quote(key)}"


def _verify_gateway_token(token: str):
    """Verify the shared forge_auth cookie without requiring database access."""
    if not token or '.' not in token:
        return None
    try:
        encoded_payload, sig = token.rsplit('.', 1)
        # base64 urlsafe decode with missing padding support
        padding = '=' * (-len(encoded_payload) % 4)
        payload_bytes = base64.urlsafe_b64decode(encoded_payload + padding)
        expected_sig = hmac.new(
            SHARED_SECRET.encode(), payload_bytes, hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(sig, expected_sig):
            return None
        data = json.loads(payload_bytes)
        if time.time() - data.get('ts', 0) > MAX_AGE_SECONDS:
            return None
        return data
    except Exception:
        return None

# ── Database (same URI as ForgeMarketing) ────────────────────
def _build_database_url():
    """Resolve database URL from environment, with fallbacks."""
    url = os.getenv('DATABASE_URL', '')
    # Strip query params that can break SQLAlchemy (e.g. ?ssl-mode=REQUIRED)
    url = url.split('?')[0] if url else ''
    # Rewrite schemes
    if url.startswith('postgres://'):
        url = url.replace('postgres://', 'postgresql://', 1)
    elif url.startswith('mysql://'):
        url = url.replace('mysql://', 'mysql+mysqldb://', 1)
    # Validate it looks like a real URL (not an unresolved ${...} reference)
    if url and '://' in url and not url.startswith('$'):
        return url
    # Fallback: build from individual env vars
    db_host = os.getenv('DATABASE_HOST') or os.getenv('DB_HOST')
    if db_host:
        db_user = os.getenv('DATABASE_USER') or os.getenv('DB_USER', 'root')
        db_pass = os.getenv('DATABASE_PASSWORD') or os.getenv('DB_PASSWORD', '')
        db_port = os.getenv('DATABASE_PORT') or os.getenv('DB_PORT', '25060')
        db_name = os.getenv('DATABASE_NAME') or os.getenv('DB_NAME', 'defaultdb')
        db_engine = os.getenv('DATABASE_ENGINE', 'mysql+mysqldb')
        return f"{db_engine}://{db_user}:{db_pass}@{db_host}:{db_port}/{db_name}"
    # Final fallback: local SQLite
    return 'sqlite:///' + os.path.join(PROJECT_ROOT, 'data', 'marketing_dashboard.db')

_database_url = _build_database_url()
print(f"[gateway] DB URL scheme: {_database_url.split('://')[0] if '://' in _database_url else 'UNKNOWN'}")
app.config['SQLALCHEMY_DATABASE_URI'] = _database_url
if not _database_url.startswith('sqlite'):
    app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
        'pool_size': 10,
        'pool_recycle': 300,
        'pool_pre_ping': True,
    }
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

from dashboard.models import db, User, Brand, BrandTheme
db.init_app(app)

# ── Flask-Login (shared with ForgeMarketing) ─────────────────
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'auth.login'

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# ── Auth routes (reuse auth blueprint) ───────────────────────
from dashboard.auth import auth_bp
app.register_blueprint(auth_bp)

# ── Ensure DB tables + seed admin ────────────────────────────
@app.before_request
def ensure_db():
    # Keep direct upload URL generation path lightweight and independent from DB.
    if request.path in ('/upload/presign', '/health'):
        return

    if not hasattr(app, '_db_ready'):
        from dashboard.database import DatabaseManager
        db_manager = DatabaseManager(app)
        db_manager.init_db()
        app._db_ready = True

# ── Landing page ─────────────────────────────────────────────
MARKETING_URL = os.getenv('MARKETING_URL', '/marketing/')
PRODUCER_URL = os.getenv('PRODUCER_URL', '/producer/ledger/')

@app.route('/')
@login_required
def index():
    return render_template('landing.html',
                           marketing_url=MARKETING_URL,
                           producer_url=PRODUCER_URL,
                           user=current_user)

@app.route('/health')
def health():
    return 'ok', 200


@app.route('/upload/presign', methods=['POST'])
def upload_presign():
    """Return a short-lived presigned POST policy for direct browser upload."""
    token = request.cookies.get(AUTH_COOKIE_NAME)
    payload = _verify_gateway_token(token)
    if not payload:
        return jsonify({'detail': 'Authentication required.'}), 401

    body = request.get_json(silent=True) or {}
    filename = os.path.basename((body.get('filename') or 'upload.bin').strip())
    episode_id = (body.get('episode_id') or '').strip()
    org_uuid = (body.get('organization_uuid') or '').strip()

    if not episode_id or not org_uuid:
        return jsonify({'detail': 'episode_id and organization_uuid are required.'}), 400

    key = f"foundry/producer/{org_uuid}/episodes/{episode_id}/media/{uuid.uuid4().hex[:8]}_{filename}"
    expires = 3600
    cfg = _spaces_config()

    try:
        post = _spaces_client().generate_presigned_post(
            Bucket=cfg['bucket'],
            Key=key,
            ExpiresIn=expires,
        )
    except Exception as exc:
        return jsonify({'detail': f'Could not generate upload URL: {exc}'}), 500

    return jsonify({
        'url': post['url'],
        'fields': post['fields'],
        'key': key,
        'public_url': _public_url(key),
        'expires_in': expires,
    }), 200

if __name__ == '__main__':
    port = int(os.getenv('GATEWAY_PORT', 5000))
    print(f"🚀 Buildly Gateway running on http://localhost:{port}")
    app.run(host='0.0.0.0', port=port, debug=True)

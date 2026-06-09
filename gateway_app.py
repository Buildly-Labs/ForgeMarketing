#!/usr/bin/env python3
"""
Buildly Gateway — unified login + app launcher.
Shares the same database and User model with ForgeMarketing.
"""

import os
import sys
from pathlib import Path

# Ensure ForgeMarketing is on the path so we can reuse its models
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

from flask import Flask, render_template, redirect, session, g, request
from flask import make_response
from flask_login import LoginManager, current_user, login_required

# Load .env
try:
    from dotenv import load_dotenv
    load_dotenv(PROJECT_ROOT / '.env')
except ImportError:
    pass

app = Flask(__name__, template_folder='gateway/templates', static_folder='gateway/static')
app.secret_key = os.getenv('FLASK_SECRET_KEY', 'marketing-automation-dashboard-2025')

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
    if not hasattr(app, '_db_ready'):
        from dashboard.database import DatabaseManager
        db_manager = DatabaseManager(app)
        db_manager.init_db()
        app._db_ready = True

# ── Landing page ─────────────────────────────────────────────
MARKETING_URL = os.getenv('MARKETING_URL', '/marketing/')
PRODUCER_URL = os.getenv('PRODUCER_URL', '/producer/')

# Route prefixes owned by the marketing app. If these are hit at gateway root,
# redirect into the configured marketing base path to avoid 404 deep links.
MARKETING_ROUTE_PREFIXES = {
    'activity',
    'admin',
    'analytics',
    'api',
    'automation',
    'brands',
    'campaigns',
    'change-password',
    'contacts',
    'content-calendar',
    'email-reports',
    'engagement-report',
    'generate',
    'google-ads',
    'influencers',
    'lead-radar',
    'leads',
    'login',
    'logout',
    'marketing-calendar',
    'onboarding',
    'outreach',
    'reports',
    'schedule',
    'settings',
    'the-index',
}


def _normalize_base_path(path_value: str) -> str:
    path = (path_value or '/marketing/').strip()
    if not path.startswith('/'):
        path = '/' + path
    return path.rstrip('/')


def _is_marketing_owned_path(subpath: str) -> bool:
    first_segment = (subpath or '').split('/', 1)[0]
    return first_segment in MARKETING_ROUTE_PREFIXES

@app.route('/')
@login_required
def index():
    return render_template('landing.html',
                           marketing_url=MARKETING_URL,
                           producer_url=PRODUCER_URL,
                           user=current_user)


@app.route('/<path:subpath>', methods=['GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'OPTIONS'])
def marketing_deep_link_redirect(subpath):
    """Redirect top-level marketing deep links into /marketing/... namespace."""
    if not _is_marketing_owned_path(subpath):
        return 'Not Found', 404

    if request.method == 'OPTIONS':
        response = make_response('', 204)
        response.headers['Allow'] = 'GET, HEAD, POST, PUT, PATCH, DELETE, OPTIONS'
        response.headers['Access-Control-Allow-Methods'] = 'GET, HEAD, POST, PUT, PATCH, DELETE, OPTIONS'
        response.headers['Access-Control-Allow-Headers'] = request.headers.get('Access-Control-Request-Headers', 'Content-Type, X-Request-ID')
        response.headers['Access-Control-Allow-Origin'] = request.headers.get('Origin', '*')
        response.headers['Vary'] = 'Origin'
        return response

    marketing_base = _normalize_base_path(MARKETING_URL)
    target = f"{marketing_base}/{subpath}"

    query_string = request.query_string.decode('utf-8')
    if query_string:
        target = f"{target}?{query_string}"

    # Preserve method and request body for API form posts and webhooks.
    redirect_code = 302 if request.method in {'GET', 'HEAD'} else 307
    return redirect(target, code=redirect_code)

@app.route('/health')
def health():
    return 'ok', 200


@app.errorhandler(404)
def not_found_gateway(e):
    if request.path.startswith('/api/'):
        return {'error': 'Not found', 'path': request.path}, 404
    marketing_base = _normalize_base_path(MARKETING_URL)
    login_url = f"{marketing_base}/login"
    return render_template('404.html', login_url=login_url, marketing_url=MARKETING_URL), 404


@app.errorhandler(500)
def server_error_gateway(e):
    try:
        from error_issue_reporter import report_server_error

        report_server_error(e, request.path, request.method, component='gateway')
    except Exception:
        pass

    if request.path.startswith('/api/'):
        return {'error': 'Internal server error'}, 500
    marketing_base = _normalize_base_path(MARKETING_URL)
    login_url = f"{marketing_base}/login"
    return render_template('404.html', login_url=login_url, marketing_url=MARKETING_URL, is_500=True), 500

if __name__ == '__main__':
    port = int(os.getenv('GATEWAY_PORT', 5000))
    print(f"🚀 Buildly Gateway running on http://localhost:{port}")
    app.run(host='0.0.0.0', port=port, debug=True)

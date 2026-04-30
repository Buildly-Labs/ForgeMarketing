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

from flask import Flask, render_template, redirect, session, g
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

if __name__ == '__main__':
    port = int(os.getenv('GATEWAY_PORT', 5000))
    print(f"🚀 Buildly Gateway running on http://localhost:{port}")
    app.run(host='0.0.0.0', port=port, debug=True)

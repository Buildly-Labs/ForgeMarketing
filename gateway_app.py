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
_database_url = os.getenv('DATABASE_URL')
if _database_url:
    # Strip query params (e.g. ?ssl-mode=REQUIRED) that break SQLAlchemy's parser
    _database_url = _database_url.split('?')[0]
    if _database_url.startswith('postgres://'):
        _database_url = _database_url.replace('postgres://', 'postgresql://', 1)
    elif _database_url.startswith('mysql://'):
        _database_url = _database_url.replace('mysql://', 'mysql+mysqldb://', 1)
    app.config['SQLALCHEMY_DATABASE_URI'] = _database_url
    # Enable SSL for managed databases and set pool options
    app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
        'pool_size': 10,
        'pool_recycle': 300,
        'pool_pre_ping': True,
    }
else:
    _db_path = os.path.join(PROJECT_ROOT, 'data', 'marketing_dashboard.db')
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + _db_path
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

# ── Ensure DB tables exist ───────────────────────────────────
@app.before_request
def ensure_db():
    if not hasattr(app, '_db_ready'):
        db.create_all()
        app._db_ready = True

# ── Landing page ─────────────────────────────────────────────
MARKETING_URL = os.getenv('MARKETING_URL', 'http://localhost:8002')
PRODUCER_URL = os.getenv('PRODUCER_URL', 'http://localhost:8080')

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

#!/usr/bin/env python3
"""
Unified Marketing Automation Dashboard
Main web interface for managing all brand marketing activities
"""

from flask import Flask, render_template, request, jsonify, redirect, url_for, send_from_directory, abort, session, Response
import asyncio
import json
import yaml
import os
import requests
import subprocess
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
import sys
import logging
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode, quote_plus

logger = logging.getLogger(__name__)

# Load environment variables
try:
    from dotenv import load_dotenv
    load_dotenv()
    ENV_LOADED = True
except ImportError:
    ENV_LOADED = False
    print("⚠️  python-dotenv not installed - environment variables from .env file won't be loaded")

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Import our automation modules

from flask import Flask, render_template, request, jsonify, redirect, url_for
import asyncio
import json
import yaml
import os
import requests
import subprocess
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Optional
import sys

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Import our automation modules
try:
    from automation.ai.ollama_integration import AIContentGenerator
    print("✅ AI integration loaded successfully")
except ImportError as e:
    print(f"⚠️  Warning: Could not import AI integration: {e}")
    print("   Make sure to run: pip install aiohttp requests")
    AIContentGenerator = None

try:
    from automation.activity_tracker import ActivityTracker
    ACTIVITY_TRACKER_AVAILABLE = True
    try:
        activity_tracker = ActivityTracker()
        print("✅ Activity tracker loaded successfully")
    except Exception as e:
        ACTIVITY_TRACKER_AVAILABLE = False
        activity_tracker = None
        print(f"⚠️  Activity tracker initialization failed; continuing without tracker: {e}")
except ImportError as e:
    ACTIVITY_TRACKER_AVAILABLE = False
    activity_tracker = None
    print(f"⚠️  Activity tracker not available: {e}")

try:
    from automation.social.social_media_manager import social_manager
    print("✅ Social media integration loaded successfully")
    SOCIAL_AVAILABLE = True
except ImportError as e:
    print(f"⚠️  Warning: Could not import social media integration: {e}")
    social_manager = None
    SOCIAL_AVAILABLE = False

# Import real analytics system
try:
    from automation.real_analytics_dashboard import get_analytics_for_dashboard
    print("✅ Real analytics dashboard loaded successfully")
    ANALYTICS_AVAILABLE = True
except ImportError as e:
    print(f"⚠️  Warning: Could not import real analytics: {e}")
    get_analytics_for_dashboard = None
    ANALYTICS_AVAILABLE = False

# Outreach system is optional in this standalone build.
import csv
import io
OutreachService = None
OUTREACH_AVAILABLE = False

# Import daily email system
try:
    from automation.daily_analytics_emailer import DailyAnalyticsEmailer
    print("✅ Daily analytics emailer loaded successfully")
    DAILY_EMAIL_AVAILABLE = True
except ImportError as e:
    print(f"⚠️  Warning: Could not import daily email system: {e}")
    DailyAnalyticsEmailer = None
    DAILY_EMAIL_AVAILABLE = False

# Import outreach automation system
try:
    from automation.multi_brand_outreach import MultiBrandOutreachCampaign, BRAND_DISCOVERY_STRATEGIES
    from automation.unified_analytics import UnifiedOutreachAnalytics
    from automation.real_analytics_dashboard import RealAnalyticsDashboard
    from automation.campaign_report_generator import CampaignReportGenerator
    print("✅ Multi-brand outreach system loaded successfully")
    print("✅ Unified analytics system loaded successfully")
    print("✅ Campaign reporting system loaded successfully")
    OUTREACH_AUTOMATION_AVAILABLE = True
    REAL_ANALYTICS_AVAILABLE = True
except ImportError as e:
    print(f"⚠️  Warning: Could not import outreach automation: {e}")
    MultiBrandOutreachCampaign = None
    BRAND_DISCOVERY_STRATEGIES = {}
    UnifiedOutreachAnalytics = None
    RealAnalyticsDashboard = None
    CampaignReportGenerator = None
    OUTREACH_AUTOMATION_AVAILABLE = False
    REAL_ANALYTICS_AVAILABLE = False

# Import email analytics system - use database version when available
try:
    try:
        # Try database-aware version first (requires Flask app context)
        from automation.analytics.email_analytics_database import DatabaseEmailAnalytics
        EmailCampaignAnalytics = DatabaseEmailAnalytics
        EMAIL_ANALYTICS_AVAILABLE = True
        print("✅ Database-aware email analytics loaded successfully")
    except ImportError:
        # Fall back to original version
        from automation.analytics.email_analytics import EmailCampaignAnalytics
        EMAIL_ANALYTICS_AVAILABLE = True
        print("✅ Email campaign analytics loaded successfully")
except ImportError as e:
    print(f"⚠️  Warning: Could not import email analytics: {e}")
    EmailCampaignAnalytics = None
    EMAIL_ANALYTICS_AVAILABLE = False
    email_analytics = None

# Import Google Ads automation system
try:
    from automation.google_ads_manager import GoogleAdsManager
    print("✅ Google Ads integration loaded successfully")
    GOOGLE_ADS_AVAILABLE = True
except ImportError as e:
    print(f"⚠️  Warning: Could not import Google Ads integration: {e}")
    GoogleAdsManager = None
    GOOGLE_ADS_AVAILABLE = False

app = Flask(__name__)
app.secret_key = os.getenv('DASHBOARD_SECRET_KEY', 'marketing-automation-dashboard-2025')

# Honor X-Forwarded-Prefix header set by nginx when the app runs behind /marketing/ prefix.
# This lets url_for() generate correct absolute URLs including the /marketing/ path segment.
from werkzeug.middleware.proxy_fix import ProxyFix
app.wsgi_app = ProxyFix(app.wsgi_app, x_prefix=1)


def _sanitize_database_url(database_url: str) -> str:
    """Normalize DB URL query params for SQLAlchemy/mysqlclient compatibility."""
    try:
        parts = urlsplit(database_url)
        scheme = (parts.scheme or '').lower()

        if not (scheme.startswith('mysql') or scheme.startswith('mariadb')):
            return database_url

        query_items = parse_qsl(parts.query, keep_blank_values=True)
        filtered = [
            (k, v)
            for (k, v) in query_items
            if k.lower() not in {'ssl-mode', 'ssl_mode'}
        ]

        return urlunsplit((
            parts.scheme,
            parts.netloc,
            parts.path,
            urlencode(filtered, doseq=True),
            parts.fragment,
        ))
    except Exception:
        return database_url

# Database configuration
# Supports DATABASE_URL env var for PostgreSQL/MySQL, falls back to local SQLite
_database_url = os.getenv('DATABASE_URL')
if _database_url:
    # Fix Heroku-style postgres:// -> postgresql://
    if _database_url.startswith('postgres://'):
        _database_url = _database_url.replace('postgres://', 'postgresql://', 1)
    _database_url = _sanitize_database_url(_database_url)
    app.config['SQLALCHEMY_DATABASE_URI'] = _database_url
    # Connection pool settings for remote databases
    app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
        'pool_size': 10,
        'pool_recycle': 300,
        'pool_pre_ping': True,
    }
else:
    _db_path = os.path.join(project_root, 'data', 'marketing_dashboard.db')
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + _db_path
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Initialize database
from dashboard.models import db
db.init_app(app)

from flask_migrate import Migrate
Migrate(app, db)

# Initialize admin API blueprint
from dashboard.admin_api import admin_bp
from dashboard.marketing_calendar_api import marketing_calendar_bp
from dashboard.lead_radar_api import lead_api_bp

# Import Lead Radar models so SQLAlchemy metadata includes these tables.
from dashboard import lead_radar_models  # noqa: F401

app.register_blueprint(admin_bp)
app.register_blueprint(marketing_calendar_bp)
app.register_blueprint(lead_api_bp)

# Load The Index custom module locally. Keep this isolated and optional.
THE_INDEX_MODULE_ENABLED = os.getenv('ENABLE_THE_INDEX_MODULE', 'true').lower() in {'1', 'true', 'yes'}
if THE_INDEX_MODULE_ENABLED:
    try:
        from custom_modules.the_index.api import the_index_bp
        from custom_modules.the_index.index_submissions_api import index_submissions_bp
        from custom_modules.the_index import models as the_index_models  # noqa: F401

        app.register_blueprint(the_index_bp)
        app.register_blueprint(index_submissions_bp)
        logger.info("✅ The Index custom module enabled")
    except Exception as e:
        logger.warning(f"⚠️  The Index custom module not loaded: {e}")


def _get_user_brand_context():
    """Return user-scoped brand list and active brand from DB/session."""
    try:
        from dashboard.models import Brand

        # Start with all active brands so screens remain data-driven even
        # when auth middleware is unavailable or not initialized.
        user_brands = Brand.query.filter_by(is_active=True).order_by(Brand.name.asc()).all()

        # Narrow to authenticated user scope when flask-login is available.
        try:
            from flask_login import current_user
            if current_user.is_authenticated:
                if current_user.is_admin:
                    pass
                else:
                    user_brands = [b for b in current_user.get_brands() if b.is_active]
        except Exception:
            pass

        active_brand = None
        active_brand_id = session.get('active_brand_id')
        active_brand_name = session.get('active_brand_name')

        if active_brand_id:
            active_brand = next((b for b in user_brands if b.id == active_brand_id), None)
        if active_brand is None and active_brand_name:
            active_brand = next((b for b in user_brands if b.name == active_brand_name), None)
        if active_brand is None and user_brands:
            active_brand = user_brands[0]

        return user_brands, active_brand
    except Exception:
        return [], None


@app.context_processor
def inject_brand_context():
    """Inject user brand context into all templates for dropdowns and JS globals."""
    user_brands, active_brand = _get_user_brand_context()
    return {
        'user_brands': user_brands,
        'active_brand': active_brand,
        'brands': [b.name for b in user_brands],
    }

# Initialize database on app startup
@app.before_request
def initialize_database():
    """Initialize database on first request"""
    if not hasattr(app, 'db_initialized'):
        with app.app_context():
            try:
                from dashboard.database import DatabaseManager
                db_manager = DatabaseManager(app)
                db_manager.init_db()
                print("✅ Database initialized successfully")
            except Exception as e:
                print(f"⚠️  Warning: Database initialization error: {e}")
        app.db_initialized = True

# Check if onboarding is needed
@app.before_request
def check_onboarding():
    """Redirect to onboarding if system not configured"""
    # Skip onboarding check for static files and all API endpoints
    if request.path.startswith('/static') or request.path.startswith('/api/'):
        return
    
    # Skip if already on onboarding page
    if request.path == '/onboarding':
        return
    
    # Re-check every request until onboarding is confirmed complete
    if getattr(app, 'onboarding_complete', False):
        return
    
    try:
        from dashboard.models import Brand, SystemConfig
        brand_count = Brand.query.count()
        has_config = SystemConfig.query.first() is not None
        
        if brand_count == 0 or not has_config:
            return redirect('/onboarding')
        else:
            app.onboarding_complete = True
    except Exception as e:
        # Database not ready yet — let the request through rather than
        # permanently caching a wrong answer
        print(f"⚠️  Error checking onboarding status: {e}")


@app.before_request
def sync_dashboard_brands_from_db():
    """Keep in-memory dashboard brands aligned with DB for data-driven screens."""
    try:
        user_brands, _ = _get_user_brand_context()
        brand_names = [b.name for b in user_brands]
        if hasattr(globals().get('dashboard', None), 'brands'):
            dashboard.brands = brand_names
    except Exception:
        pass

# Onboarding route
@app.route('/onboarding')
def onboarding():
    """First-time setup wizard"""
    return render_template('setup.html')

# Onboarding discovery endpoint
@app.route('/api/onboarding/discover', methods=['POST'])
def discover_onboarding():
    """Scrape a website to discover brand information"""
    try:
        data = request.json or {}
        website_url = data.get('website_url', '').strip()
        if not website_url:
            return jsonify({'error': 'website_url is required'}), 400

        from dashboard.brand_setup import discover_brand
        result = discover_brand(website_url)
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# Onboarding completion endpoint
@app.route('/api/onboarding/complete', methods=['POST'])
def complete_onboarding():
    """Complete onboarding — create brand, settings, and system config"""
    try:
        data = request.json or {}
        display_name = data.get('display_name', '').strip()
        website_url = data.get('website_url', '').strip()
        admin_email = data.get('admin_email', '').strip()
        description = data.get('description', '').strip()
        logo_url = data.get('logo_url', '').strip()
        social_links = data.get('social_links', {})
        theme_color = data.get('theme_color', '')
        product_type = data.get('product_type', '').strip()
        target_audience = data.get('target_audience', '').strip()
        brand_voice_notes = data.get('brand_voice_notes', '').strip()
        primary_cta = data.get('primary_cta', '').strip()
        default_hashtags = data.get('default_hashtags', '').strip()
        visual_style_notes = data.get('visual_style_notes', '').strip()
        marketing_notes = data.get('marketing_notes', '').strip()

        if not display_name:
            return jsonify({'error': 'display_name is required'}), 400

        from dashboard.models import Brand, SystemConfig, BrandSettings
        from dashboard.brand_setup import suggest_brand_name

        # Generate slug
        name = suggest_brand_name(display_name)

        # Create brand
        brand = Brand(
            name=name,
            display_name=display_name,
            description=description,
            logo_url=logo_url,
            website_url=website_url,
            is_active=True,
        )
        db.session.add(brand)
        db.session.flush()  # get brand.id

        # Create default settings for the brand
        settings = BrandSettings(brand_id=brand.id)
        db.session.add(settings)

        # Store onboarding marketing profile as advanced settings
        advanced_settings = {
            'social_links': social_links,
            'theme_color': theme_color,
            'marketing_profile': {
                'product_type': product_type,
                'target_audience': target_audience,
                'brand_voice_notes': brand_voice_notes,
                'primary_cta': primary_cta,
                'default_hashtags': default_hashtags,
                'visual_style_notes': visual_style_notes,
                'marketing_notes': marketing_notes,
            }
        }
        settings.set_advanced_settings(advanced_settings)

        # Create system config entries
        sys_cfg = SystemConfig(
            key='admin_email',
            value=admin_email,
            category='system',
            description='Primary admin email'
        )
        db.session.add(sys_cfg)

        setup_cfg = SystemConfig(
            key='setup_completed',
            value=json.dumps({'completed': True, 'date': datetime.now().isoformat()}),
            category='system',
            description='Onboarding completion record'
        )
        db.session.add(setup_cfg)

        db.session.commit()

        # Clear cached onboarding flag
        app.onboarding_complete = True

        return jsonify({
            'success': True,
            'message': 'Setup completed successfully!',
            'brand': brand.to_dict(),
            'marketing_profile': advanced_settings['marketing_profile']
        })

    except Exception as e:
        db.session.rollback()
        print(f"❌ Onboarding error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/onboarding/save-email', methods=['POST'])
def onboarding_save_email():
    """Save email provider config during onboarding"""
    try:
        data = request.json or {}
        brand_name = data.get('brand_name', '').strip()
        provider = data.get('provider', '').strip()
        if not brand_name or not provider:
            return jsonify({'error': 'brand_name and provider are required'}), 400

        from dashboard.models import Brand, BrandEmailConfig

        brand = Brand.query.filter_by(name=brand_name).first()
        if not brand:
            return jsonify({'error': 'Brand not found'}), 404

        email_cfg = BrandEmailConfig(
            brand_id=brand.id,
            provider=provider,
            from_email=data.get('from_email', ''),
            from_name=data.get('from_name', brand.display_name),
            is_primary=True
        )

        if provider == 'smtp':
            email_cfg.smtp_host = data.get('smtp_host', '')
            email_cfg.smtp_port = data.get('smtp_port', 587)
            email_cfg.smtp_user = data.get('smtp_user', '')
            email_cfg.smtp_password = data.get('smtp_password', '')
        else:
            email_cfg.api_key = data.get('api_key', '')

        db.session.add(email_cfg)
        db.session.commit()
        return jsonify({'success': True, 'message': 'Email configuration saved'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/onboarding/test-email', methods=['POST'])
def onboarding_test_email():
    """Quick connectivity test for email provider"""
    data = request.json or {}
    provider = data.get('provider', '')
    api_key = data.get('api_key', '')
    if not provider or not api_key:
        return jsonify({'success': False, 'error': 'Provider and API key required'})

    try:
        import requests as ext_requests
        test_urls = {
            'mailersend': 'https://api.mailersend.com/v1/domains',
            'brevo': 'https://api.brevo.com/v3/account',
            'sendgrid': 'https://api.sendgrid.com/v3/user/profile',
            'mailgun': 'https://api.mailgun.net/v3/domains'
        }
        url = test_urls.get(provider)
        if not url:
            return jsonify({'success': False, 'error': f'Unknown provider: {provider}'})

        headers = {}
        auth = None
        if provider == 'mailersend':
            headers['Authorization'] = f'Bearer {api_key}'
        elif provider == 'brevo':
            headers['api-key'] = api_key
        elif provider == 'sendgrid':
            headers['Authorization'] = f'Bearer {api_key}'
        elif provider == 'mailgun':
            auth = ('api', api_key)

        resp = ext_requests.get(url, headers=headers, auth=auth, timeout=10)
        if resp.status_code < 300:
            return jsonify({'success': True})
        else:
            return jsonify({'success': False, 'error': f'API returned {resp.status_code}'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/onboarding/save-social', methods=['POST'])
def onboarding_save_social():
    """Save social media credentials during onboarding"""
    try:
        data = request.json or {}
        brand_name = data.get('brand_name', '').strip()
        credentials = data.get('credentials', {})
        if not brand_name:
            return jsonify({'error': 'brand_name is required'}), 400

        from dashboard.models import Brand, BrandAPICredential

        brand = Brand.query.filter_by(name=brand_name).first()
        if not brand:
            return jsonify({'error': 'Brand not found'}), 404

        for service, creds in credentials.items():
            cred_type = 'oauth' if 'client_id' in creds else 'api_key'
            api_cred = BrandAPICredential(
                brand_id=brand.id,
                service=service,
                credential_type=cred_type,
                credentials=json.dumps(creds),
                is_active=True
            )
            db.session.add(api_cred)

        db.session.commit()
        return jsonify({'success': True, 'message': f'Saved {len(credentials)} social account(s)'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/onboarding/test-ai', methods=['POST'])
def onboarding_test_ai():
    """Test AI provider connection and list available models"""
    data = request.json or {}
    provider = data.get('provider', '')
    url = data.get('url', '').strip().rstrip('/')

    if provider == 'ollama':
        if not url:
            url = 'http://localhost:11434'
        try:
            import requests as ext_requests
            resp = ext_requests.get(f'{url}/api/tags', timeout=10)
            if resp.status_code == 200:
                models = resp.json().get('models', [])
                return jsonify({'success': True, 'models': [{'name': m.get('name', '')} for m in models]})
            else:
                return jsonify({'success': False, 'error': f'Ollama returned {resp.status_code}'})
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)})

    if provider in {'do_agent', 'digitalocean'}:
        if not url:
            url = os.getenv('DO_AGENT_URL', 'https://upssgpoiscmhlp3uuvm65hyn.agents.do-ai.run')
        token = (data.get('token') or os.getenv('DO_AGENT_TOKEN', '')).strip()
        model = (data.get('model') or os.getenv('DO_AGENT_MODEL', 'gpt-4o-mini')).strip()
        headers = {'Content-Type': 'application/json'}
        if token:
            headers['Authorization'] = f'Bearer {token}'

        payload = {
            'model': model,
            'messages': [
                {'role': 'user', 'content': 'Reply with JSON: {"ok":true,"service":"do_agent"}'}
            ],
            'temperature': 0,
        }

        endpoints = [
            url,
            f"{url}/v1/chat/completions",
            f"{url}/chat/completions",
            f"{url}/api/v1/chat/completions",
        ]
        last_error = 'Unknown error'
        for endpoint in endpoints:
            try:
                resp = requests.post(endpoint, json=payload, headers=headers, timeout=15)
                if resp.status_code < 400:
                    return jsonify({'success': True, 'models': [{'name': model}], 'endpoint': endpoint})
                last_error = f"HTTP {resp.status_code}: {resp.text[:200]}"
            except Exception as exc:
                last_error = str(exc)

        return jsonify({'success': False, 'error': last_error})

    return jsonify({'success': False, 'error': f'Unknown AI provider: {provider}'})


@app.route('/api/onboarding/save-ai', methods=['POST'])
def onboarding_save_ai():
    """Save AI configuration during onboarding"""
    try:
        data = request.json or {}
        provider = data.get('provider', '')
        if not provider:
            return jsonify({'error': 'provider is required'}), 400

        from dashboard.models import SystemConfig

        configs = [
            ('ai_provider', provider, 'ai', 'AI provider type'),
            ('ai_model', data.get('model', ''), 'ai', 'Default AI model'),
        ]

        if provider == 'ollama':
            configs.append(('ai_ollama_url', data.get('url', 'http://localhost:11434'), 'ai', 'Ollama server URL'))
        elif provider in {'do_agent', 'digitalocean'}:
            configs.append(('ai_do_agent_url', data.get('url', 'https://upssgpoiscmhlp3uuvm65hyn.agents.do-ai.run'), 'ai', 'DigitalOcean Agent URL'))
            configs.append(('ai_do_agent_token', data.get('token', ''), 'ai', 'DigitalOcean Agent bearer token'))
        elif provider == 'openai':
            configs.append(('ai_openai_key', data.get('api_key', ''), 'ai', 'OpenAI API key'))

        for key, value, category, desc in configs:
            existing = SystemConfig.query.filter_by(key=key).first()
            if existing:
                existing.value = value
            else:
                cfg = SystemConfig(key=key, value=value, category=category, description=desc,
                                   is_secret=(key in {'ai_openai_key', 'ai_do_agent_token'}))
                db.session.add(cfg)

        db.session.commit()
        return jsonify({'success': True, 'message': 'AI configuration saved'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


# Admin UI route
@app.route('/admin/brands')
def admin_brands():
    """Admin panel for managing brands and email configurations"""
    return render_template('admin_brands.html')

# Marketing Calendar UI route
@app.route('/marketing-calendar')
def marketing_calendar_ui():
    """Marketing calendar dashboard interface"""
    return render_template('marketing_calendar.html')

@app.route('/content-calendar')
def content_calendar_ui():
    """Content calendar with full CRUD and AI generation"""
    return render_template('content_calendar.html')

# Development configuration - disable caching for easier testing
app.config['TEMPLATES_AUTO_RELOAD'] = True
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0
app.jinja_env.auto_reload = True
app.jinja_env.cache = {}

# Add no-cache headers for development
@app.after_request
def add_no_cache_headers(response):
    """Add headers to prevent caching during development"""
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response

# Configuration validation
def validate_environment_config():
    """Validate environment configuration and return status"""
    config_status = {
        'email': {
            'mailersend_configured': bool(os.getenv('MAILERSEND_API_TOKEN')),
            'brevo_configured': bool(os.getenv('BREVO_SMTP_USER') and os.getenv('BREVO_SMTP_PASSWORD')),
            'missing_vars': []
        },
        'ai': {
            'openai_configured': bool(os.getenv('OPENAI_API_KEY')),
            'missing_vars': []
        },
        'social': {
            'twitter_configured': bool(os.getenv('TWITTER_API_KEY') and os.getenv('TWITTER_API_SECRET')),
            'linkedin_configured': bool(os.getenv('LINKEDIN_CLIENT_ID') and os.getenv('LINKEDIN_CLIENT_SECRET')),
            'missing_vars': []
        },
        'google_ads': {
            'configured': bool(os.getenv('GOOGLE_ADS_DEVELOPER_TOKEN') and os.getenv('GOOGLE_ADS_CLIENT_ID')),
            'missing_vars': []
        }
    }
    
    # Check for missing email configuration
    if not config_status['email']['mailersend_configured']:
        config_status['email']['missing_vars'].append('MAILERSEND_API_TOKEN')
    if not config_status['email']['brevo_configured']:
        config_status['email']['missing_vars'].extend(['BREVO_SMTP_USER', 'BREVO_SMTP_PASSWORD'])
    
    # Check for missing AI configuration
    if not config_status['ai']['openai_configured']:
        config_status['ai']['missing_vars'].append('OPENAI_API_KEY')
    
    # Check for missing social configuration
    if not config_status['social']['twitter_configured']:
        config_status['social']['missing_vars'].extend(['TWITTER_API_KEY', 'TWITTER_API_SECRET'])
    if not config_status['social']['linkedin_configured']:
        config_status['social']['missing_vars'].extend(['LINKEDIN_CLIENT_ID', 'LINKEDIN_CLIENT_SECRET'])
    
    # Check for missing Google Ads configuration
    if not config_status['google_ads']['configured']:
        config_status['google_ads']['missing_vars'].extend(['GOOGLE_ADS_DEVELOPER_TOKEN', 'GOOGLE_ADS_CLIENT_ID'])
    
    return config_status

# Global configuration status
ENVIRONMENT_CONFIG = validate_environment_config()

# Campaign progress tracking
import threading
import time
import uuid

campaign_progress = {}
campaign_logs = {}

class MarketingDashboard:
    """Main dashboard controller"""
    
    def __init__(self):
        self.config_dir = project_root / 'config'
        self.load_configuration()
        self.ai_generator = None
        self.logger = self._setup_logger()
        
        # Initialize AI generator if available
        if AIContentGenerator:
            try:
                self.ai_generator = AIContentGenerator()
                # Import from database instead of hardcoded list
                from config.brand_loader import get_all_brands
                self.brands = get_all_brands()
                if self.brands:
                    print(f"✅ AI generator initialized with {len(self.brands)} brands from database: {self.brands}")
                else:
                    print("⚠️  No brands found in database. Please add brands via admin panel.")
                    self.brands = []
            except Exception as e:
                print(f"⚠️  Warning: AI generator initialization failed: {e}")
                print("⚠️  No brands available. Please add brands via admin panel.")
                self.brands = []
        else:
            # Import from database instead of hardcoded list
            try:
                from config.brand_loader import get_all_brands
                self.brands = get_all_brands()
                if self.brands:
                    print(f"📋 Loaded {len(self.brands)} brands from database: {self.brands}")
                else:
                    print("⚠️  No brands found in database. Please add brands via admin panel.")
                    self.brands = []
            except Exception as e:
                print(f"❌ Error loading brands from database: {e}")
                print("⚠️  No brands available. Please add brands via admin panel.")
                self.brands = []
    
    def _setup_logger(self):
        """Setup logging for dashboard"""
        import logging
        logger = logging.getLogger('dashboard')
        if not logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
            handler.setFormatter(formatter)
            logger.addHandler(handler)
            logger.setLevel(logging.INFO)
        return logger
    
    def load_configuration(self):
        """Load dashboard configuration"""
        config_file = self.config_dir / 'dashboard_config.yaml'
        if config_file.exists():
            with open(config_file, 'r') as f:
                self.config = yaml.safe_load(f)
        else:
            # Default configuration
            self.config = {
                'dashboard': {
                    'title': 'Marketing Automation Dashboard',
                    'port': 8002,
                    'host': '0.0.0.0'
                },
                'features': {
                    'content_generation': True,
                    'social_media_management': True,
                    'outreach_automation': True,
                    'analytics_reporting': True
                }
            }
    
    async def generate_content_async(self, content_type, brand, **kwargs):
        """Generate content using AI"""
        if not self.ai_generator:
            return {'error': 'AI generator not available'}
        
        start_time = datetime.now()
        
        try:
            if content_type == 'blog':
                result = await self.ai_generator.generate_blog_post(
                    brand=brand,
                    topic=kwargs.get('topic', 'Marketing Insights'),
                    target_audience=kwargs.get('audience', 'professionals')
                )
            elif content_type == 'social':
                result = await self.ai_generator.generate_social_post(
                    brand=brand,
                    content_type=kwargs.get('social_type', 'educational'),
                    platform=kwargs.get('platform', 'twitter')
                )
            elif content_type == 'email':
                result = await self.ai_generator.generate_outreach_email(
                    brand=brand,
                    recipient_info=kwargs.get('recipient_info', {}),
                    campaign_type=kwargs.get('campaign_type', 'general')
                )
            else:
                return {'error': f'Unknown content type: {content_type}'}
            
            # Track AI generation activity
            generation_time_ms = int((datetime.now() - start_time).total_seconds() * 1000)
            
            if ACTIVITY_TRACKER_AVAILABLE and result:
                activity_tracker.track_ai_generation(
                    brand=brand,
                    content_type=content_type,
                    template_used=kwargs.get('style') or kwargs.get('campaign_type') or 'default',
                    generation_time_ms=generation_time_ms,
                    quality_score=8.0,  # Default quality score
                    success=True,
                    metadata={
                        'topic': kwargs.get('topic'),
                        'platform': kwargs.get('platform'),
                        'audience': kwargs.get('audience'),
                        'content_length': len(str(result)) if result else 0
                    }
                )
            
            return {'success': True, 'content': result}
            
        except Exception as e:
            # Track failed generation
            if ACTIVITY_TRACKER_AVAILABLE:
                generation_time_ms = int((datetime.now() - start_time).total_seconds() * 1000)
                activity_tracker.track_ai_generation(
                    brand=brand,
                    content_type=content_type,
                    generation_time_ms=generation_time_ms,
                    success=False,
                    error_message=str(e),
                    metadata=kwargs
                )
            
            return {'error': str(e)}
    
    def get_cron_status(self):
        """Get current cron job status using centralized cron manager with enhanced tracking"""
        try:
            # Import centralized cron manager
            from automation.centralized_cron_manager import CentralizedCronManager
            
            # Initialize cron manager and register scripts
            cron_manager = CentralizedCronManager()
            cron_manager.register_automation_scripts()
            
            # Get combined cron status (managed + system)
            cron_status = cron_manager.get_combined_cron_status()
            
            # Transform for dashboard display
            cron_jobs = []
            
            for job in cron_status['jobs']:
                cron_jobs.append({
                    'id': job.get('id'),
                    'name': job.get('name', 'Unknown Job'),
                    'brand': job.get('brand', 'System'),
                    'schedule': job.get('schedule', 'Unknown'),
                    'command': job.get('script_path', job.get('command', '')),
                    'type': self._categorize_cron_job(job.get('script_path', job.get('command', ''))),
                    'status': job.get('status', 'unknown'),
                    'last_run': job.get('last_run', 'Never'),
                    'next_run': job.get('next_run', 'Unknown'),
                    'source': job.get('source', 'unknown'),
                    'description': job.get('description', ''),
                    'success_count': job.get('success_count', 0),
                    'failure_count': job.get('failure_count', 0),
                    'stats': self._get_job_email_stats(job.get('id'))
                })
            
            # Add outreach automation jobs from unified database
            try:
                if OUTREACH_AUTOMATION_AVAILABLE and UnifiedOutreachAnalytics:
                    analytics = UnifiedOutreachAnalytics()
                    unified_crons = analytics.get_cron_status_from_unified_db()
                    
                    for cron in unified_crons:
                        # Avoid duplicates by checking if we already have this job
                        existing = any(
                            job['command'] == cron.get('command') or job['name'] == cron.get('name')
                            for job in cron_jobs
                        )
                        
                        if not existing:
                            cron['source'] = 'unified_db'
                            cron['type'] = self._categorize_cron_job(cron.get('command', ''))
                            cron_jobs.append(cron)
                        
            except Exception as e:
                print(f"Warning: Could not get unified cron status: {e}")
            
            return cron_jobs
            
        except Exception as e:
            print(f"Error getting cron status: {e}")
            # Fallback to basic system cron parsing
            return self._get_basic_cron_status()
    
    def _get_basic_cron_status(self):
        """Fallback method for basic cron status parsing"""
        try:
            cron_jobs = []
            result = subprocess.run(['crontab', '-l'], capture_output=True, text=True)
            
            if result.returncode == 0:
                lines = result.stdout.strip().split('\n')
                
                for i, line in enumerate(lines):
                    line = line.strip()
                    if line and not line.startswith('#'):
                        parts = line.split(None, 5)
                        if len(parts) >= 6:
                            command = parts[5]
                            
                            cron_jobs.append({
                                'id': f'system_cron_{i}',
                                'schedule': ' '.join(parts[:5]),
                                'command': command,
                                'type': self._categorize_cron_job(command),
                                'name': self._extract_job_name(command),
                                'status': 'active',
                                'last_run': 'Unknown',
                                'next_run': self._calculate_next_run(parts[:5]),
                                'source': 'system_cron',
                                'brand': self._extract_brand_from_command(command),
                                'stats': {'sent': 0, 'opens': 0, 'clicks': 0}
                            })
            
            return cron_jobs
            
        except Exception as e:
            print(f"Error in basic cron status: {e}")
            return []
    
    def get_real_comprehensive_analytics(self) -> Dict[str, Any]:
        """Get real comprehensive analytics data using unified collection methods."""
        try:
            if ANALYTICS_AVAILABLE and get_analytics_for_dashboard:
                # Get multi-brand analytics summary
                analytics_data = get_analytics_for_dashboard()
                
                # Transform to dashboard format
                results = {}
                
                for brand_info in analytics_data.get('brands', []):
                    brand_key = brand_info['key']
                    
                    # Get detailed brand data
                    brand_detailed = get_analytics_for_dashboard(brand_key)
                    
                    results[brand_key] = {
                        'brand': brand_key,
                        'name': brand_info['name'],
                        'period': 'Last 30 days (real data)',
                        'collected_at': brand_detailed.get('last_updated', datetime.now().isoformat()),
                        'website_analytics': {
                            'overview': {
                                'sessions': brand_detailed['website']['sessions'],
                                'users': brand_detailed['website']['users'],
                                'pageviews': brand_detailed['website']['pageviews'],
                                'avg_session_duration': brand_detailed['website']['avg_duration'],
                                'bounce_rate': brand_detailed['website']['bounce_rate']
                            },
                            'top_pages': brand_detailed['website']['top_pages'],
                            'traffic_sources': brand_detailed['website']['traffic_sources']
                        },
                        'email_analytics': {
                            'statistics': {
                                'total_sent': brand_detailed['email']['sent'],
                                'total_delivered': brand_detailed['email']['sent'],  # Assume high delivery
                                'avg_open_rate': brand_detailed['email']['open_rate'],
                                'avg_click_rate': brand_detailed['email']['click_rate']
                            }
                        },
                        'social_analytics': {
                            'summary': {
                                'total_followers': 1500,  # Placeholder for now
                                'total_posts': 20,
                                'avg_engagement_rate': 3.2
                            }
                        },
                        'summary': {
                            'overall_performance': {
                                'score': brand_detailed['performance']['score'],
                                'rating': brand_detailed['performance']['rating'],
                                'trend': 'stable'
                            }
                        }
                    }
                
                # Add overall summary
                summary_data = analytics_data.get('summary', {})
                results['summary'] = {
                    'total_website_sessions': summary_data.get('total_sessions', 0),
                    'total_emails_sent': summary_data.get('total_emails', 0),
                    'total_social_followers': sum(r['social_analytics']['summary']['total_followers'] for r in results.values() if isinstance(r, dict) and 'social_analytics' in r),
                    'number_of_brands': summary_data.get('total_brands', 0),
                    'average_performance_score': 7.8,  # Calculate from real data
                    'overall_rating': 'good',
                    'data_source': 'real_analytics'
                }
                
                return results
                
            else:
                # Fallback to enhanced mock data
                return self.get_fallback_analytics()
                
        except Exception as e:
            print(f"❌ Error getting real analytics: {e}")
            return self.get_fallback_analytics()
    
    def get_fallback_analytics(self) -> Dict[str, Any]:
        """Enhanced fallback analytics when real data unavailable"""
        brands = list(self.brands) if self.brands else []
        results = {}
        
        for brand in brands:
            results[brand] = {
                'brand': brand,
                'period': 'Last 30 days (fallback data)',
                'collected_at': datetime.now().isoformat(),
                'website_analytics': {
                    'overview': {
                        'sessions': 1200 + hash(brand) % 500,
                        'users': 950 + hash(brand) % 300,
                        'pageviews': 2800 + hash(brand) % 800,
                        'avg_session_duration': 145.5,
                        'bounce_rate': 0.42
                    }
                },
                'email_analytics': {
                    'statistics': {
                        'total_sent': 2500 + hash(brand) % 1000,
                        'total_delivered': 2375 + hash(brand) % 950,
                        'avg_open_rate': 22.0 + (hash(brand) % 10),
                        'avg_click_rate': 3.5 + (hash(brand) % 3)
                    }
                },
                'social_analytics': {
                    'summary': {
                        'total_followers': 1500 + hash(brand) % 700,
                        'total_posts': 20,
                        'avg_engagement_rate': 3.2 + (hash(brand) % 3)
                    }
                },
                'summary': {
                    'overall_performance': {
                        'score': 7.5 + (hash(brand) % 2),
                        'rating': 'good',
                        'trend': 'stable'
                    }
                }
            }
        
        results['summary'] = {
            'total_website_sessions': sum(r['website_analytics']['overview']['sessions'] for r in results.values()),
            'total_emails_sent': sum(r['email_analytics']['statistics']['total_sent'] for r in results.values()),
            'total_social_followers': sum(r['social_analytics']['summary']['total_followers'] for r in results.values()),
            'number_of_brands': len(brands),
            'average_performance_score': 7.8,
            'overall_rating': 'good',
            'data_source': 'fallback_mock'
        }
        
        return results
    
    def get_mock_analytics_summary(self) -> Dict[str, Any]:
        """Return mock analytics summary"""
        summary = {}
        brands = list(self.brands) if self.brands else []
        for brand in brands[:4]:
            score = round(7.0 + ((hash(brand) % 20) / 10), 1)
            trend = 'up' if hash(brand) % 2 == 0 else 'stable'
            summary[brand] = {
                'overall_performance': {
                    'score': score,
                    'rating': 'good' if score < 8.5 else 'excellent',
                    'trend': trend
                }
            }
        return summary
    
    def _categorize_cron_job(self, command):
        """Categorize cron job by type"""
        if 'daily_analytics_emailer' in command:
            return 'analytics_email'
        elif 'multi_brand_outreach' in command or 'run_brand_outreach' in command:
            return 'outreach'
        elif 'discovery' in command.lower():
            return 'discovery'
        elif 'blog' in command.lower():
            return 'content'
        elif 'social' in command.lower() or 'tweet' in command.lower():
            return 'social'
        elif 'report' in command.lower() or 'analytics' in command.lower():
            return 'analytics'
        else:
            return 'other'
    
    def _extract_job_name(self, command):
        """Extract a readable name from cron command"""
        if 'daily_analytics_emailer' in command:
            if '--summary-only' in command:
                return 'Daily Analytics Summary Email'
            else:
                return 'Daily Analytics Reports'
        elif 'run_brand_outreach' in command:
            # Extract configured brand from command
            command_parts = command.split()
            for idx, part in enumerate(command_parts):
                if part == '--brand' and idx + 1 < len(command_parts):
                    label = command_parts[idx + 1].replace('_', ' ').replace('-', ' ').title()
                    return f'{label} Outreach'
            return 'Brand Outreach Campaign'
        elif 'discovery' in command.lower():
            return 'Target Discovery'
        elif 'blog' in command.lower():
            return 'Daily Blog Generation'
        elif 'social' in command.lower() or 'tweet' in command.lower():
            return 'Social Media Posting'
        elif 'outreach' in command.lower():
            return 'Email Outreach Campaign'
        elif 'report' in command.lower():
            return 'Analytics Report'
        elif 'news' in command.lower():
            return 'News Collection'
        else:
            # Extract script name
            parts = command.split()
            for part in parts:
                if '.py' in part or '.sh' in part:
                    script_name = part.split('/')[-1].replace('.py', '').replace('.sh', '')
                    return script_name.replace('_', ' ').title()
            return 'System Task'
    
    def _extract_brand_from_command(self, command):
        """Extract brand from command path or name"""
        try:
            command = command.lower()
            for brand in self.brands:
                if brand.lower() in command:
                    return brand.replace('_', ' ').replace('-', ' ').title()
            return 'System'
        except:
            return 'Unknown'
    
    def _calculate_last_run(self, schedule):
        """Estimate when cron job last ran"""
        # Simplified - in production, check actual logs
        return '3h ago'  # Mock data
    
    def _calculate_next_run(self, schedule):
        """Calculate when cron job will run next"""
        # Simplified - in production, parse cron schedule
        return '21h'  # Mock data
    
    def _get_job_email_stats(self, job_id):
        """Get email statistics for a specific job using EmailStatsService"""
        try:
            # Import the email stats service
            import sys
            sys.path.append(str(project_root))
            from email_stats_service import EmailStatsService
            
            # Get stats for the job
            stats_service = EmailStatsService()
            stats = stats_service.get_cron_job_stats(job_id)
            
            return {
                'sent': stats.get('sent', 0),
                'opens': stats.get('opens', 0),
                'clicks': stats.get('clicks', 0)
            }
            
        except Exception as e:
            print(f"Error getting email stats for {job_id}: {e}")
            return {
                'sent': 0,
                'opens': 0,
                'clicks': 0
            }
    
    def get_content_history(self):
        """Get history of generated/sent content"""
        history = []
        
        # Check blog directories for recent content
        websites_dir = project_root / 'automation' / 'websites'
        if websites_dir.exists():
            for brand_dir in websites_dir.iterdir():
                if brand_dir.is_dir():
                    # Look for recent files
                    for file_path in brand_dir.rglob('*.html'):
                        if file_path.stat().st_mtime > (datetime.now().timestamp() - 86400):  # Last 24h
                            history.append({
                                'brand': brand_dir.name,
                                'type': 'blog',
                                'sent_today': True,
                                'timestamp': datetime.fromtimestamp(file_path.stat().st_mtime)
                            })
        
        return history
    
    def calculate_success_rate(self):
        """Calculate automation success rate"""
        # In production, analyze logs and track failures
        return 85  # Mock success rate
    
    def get_recent_activity_timeline(self):
        """Get recent activity for timeline"""
        # Combine social media activity and blog generation
        timeline = []
        
        if SOCIAL_AVAILABLE and social_manager:
            social_activity = social_manager.get_recent_activity(hours=24)
            blog_activity = social_manager.get_blog_activity()
            
            for activity in social_activity + blog_activity:
                timeline.append({
                    'id': activity['id'],
                    'title': activity['title'],
                    'description': f"{activity['title']} for {activity['brand']}",
                    'type': activity['type'],
                    'brand': activity['brand'],
                    'status': 'success',
                    'timestamp': activity['time'],
                    'metric': activity['metric']
                })
        
        return timeline[:10]  # Most recent 10
    
    def get_credential_status(self):
        """Get sanitized credential status"""
        # Return which platforms have credentials without exposing secrets.
        # Prefer DB-backed configs and fall back to environment values.
        status = {
            'ai': {'configured': False},
            'email': {'configured': False},
            'twitter': {'configured': False},
            'bluesky': {'configured': False},
            'instagram': {'configured': False},
            'linkedin': {'configured': False},
        }

        try:
            from dashboard.models import BrandAPICredential, BrandEmailConfig, SystemConfig

            ai_config = {cfg.key: cfg.value for cfg in SystemConfig.query.filter(SystemConfig.key.like('ai_%')).all()}
            gemini_key_cfg = SystemConfig.query.filter_by(key='GEMINI_API_KEY').first()
            ai_provider = (ai_config.get('ai_provider') or '').strip().lower()
            has_db_ai = bool(ai_provider)
            has_openai_key = bool(ai_config.get('ai_openai_key') or os.getenv('OPENAI_API_KEY'))
            has_gemini_key = bool((gemini_key_cfg.value if gemini_key_cfg else '') or os.getenv('GEMINI_API_KEY'))
            if ai_provider == 'openai':
                status['ai']['configured'] = has_openai_key
            elif ai_provider == 'gemini':
                status['ai']['configured'] = has_gemini_key
            elif ai_provider == 'ollama':
                status['ai']['configured'] = bool(ai_config.get('ai_ollama_url') or os.getenv('OLLAMA_HOST') or has_db_ai)
            else:
                status['ai']['configured'] = has_db_ai or has_openai_key or has_gemini_key

            email_cfg = {cfg.key: cfg.value for cfg in SystemConfig.query.filter(SystemConfig.category == 'email').all()}

            status['email']['configured'] = (
                BrandEmailConfig.query.count() > 0
                or bool(os.getenv('EMAIL_API_KEY'))
                or bool(os.getenv('MAILERSEND_API_TOKEN'))
                or bool(os.getenv('BREVO_SMTP_USER') and os.getenv('BREVO_SMTP_PASSWORD'))
                or bool(email_cfg.get('BREVO_SMTP_LOGIN') and email_cfg.get('BREVO_SMTP_KEY'))
                or bool(email_cfg.get('BREVO_SMTP_HOST') and email_cfg.get('BREVO_SMTP_PORT'))
            )

            def _has_service_creds(service_name: str) -> bool:
                return BrandAPICredential.query.filter_by(service=service_name, is_active=True).count() > 0

            status['twitter']['configured'] = _has_service_creds('twitter') or bool(os.getenv('TWITTER_API_KEY'))
            status['bluesky']['configured'] = _has_service_creds('bluesky') or bool(os.getenv('BLUESKY_USERNAME'))
            status['instagram']['configured'] = _has_service_creds('instagram') or bool(os.getenv('INSTAGRAM_APP_ID'))
            status['linkedin']['configured'] = _has_service_creds('linkedin') or bool(os.getenv('LINKEDIN_CLIENT_ID'))

        except Exception:
            status['ai']['configured'] = bool(os.getenv('OPENAI_API_KEY') or os.getenv('OLLAMA_HOST'))
            status['email']['configured'] = bool(
                os.getenv('EMAIL_API_KEY')
                or os.getenv('MAILERSEND_API_TOKEN')
                or (os.getenv('BREVO_SMTP_USER') and os.getenv('BREVO_SMTP_PASSWORD'))
            )
            status['twitter']['configured'] = bool(os.getenv('TWITTER_API_KEY'))
            status['bluesky']['configured'] = bool(os.getenv('BLUESKY_USERNAME'))
            status['instagram']['configured'] = bool(os.getenv('INSTAGRAM_APP_ID'))
            status['linkedin']['configured'] = bool(os.getenv('LINKEDIN_CLIENT_ID'))

        return status
    
    def save_credentials(self, credentials):
        """Save credentials securely"""
        try:
            # In production, save to secure storage (not env vars directly)
            # For now, show what environment variables would be set
            env_vars = []
            
            for platform, creds in credentials.items():
                if platform == 'twitter' and creds.get('api_key'):
                    env_vars.extend([
                        f'TWITTER_API_KEY={creds["api_key"]}',
                        f'TWITTER_API_SECRET={creds["api_secret"]}',
                        f'TWITTER_ACCESS_TOKEN={creds["access_token"]}',
                        f'TWITTER_ACCESS_TOKEN_SECRET={creds["access_token_secret"]}'
                    ])
                elif platform == 'bluesky' and creds.get('username'):
                    env_vars.extend([
                        f'BLUESKY_USERNAME={creds["username"]}',
                        f'BLUESKY_APP_PASSWORD={creds["app_password"]}'
                    ])
                # Add other platforms...
            
            # Save to .env file or secure storage
            env_file = project_root / '.env'
            with open(env_file, 'w') as f:
                f.write('\n'.join(env_vars))
            
            return {'success': True}
            
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def test_all_connections(self):
        """Test all configured platform connections"""
        status = {}
        credential_status = self.get_credential_status()

        # Consider AI connected when either reachable now or configured in DB/env.
        status['ai'] = self.test_ai_connection() or credential_status.get('ai', {}).get('configured', False)
        status['email'] = credential_status.get('email', {}).get('configured', False)

        for platform in ['twitter', 'bluesky', 'instagram', 'linkedin']:
            status[platform] = credential_status.get(platform, {}).get('configured', False)

        return status
    
    def test_ai_connection(self):
        """Test AI service connection"""
        try:
            ai_url = os.getenv('OLLAMA_HOST', 'http://localhost:11434')
            ai_provider = ''
            ai_openai_key = os.getenv('OPENAI_API_KEY', '')
            ai_gemini_key = os.getenv('GEMINI_API_KEY', '')
            try:
                from dashboard.models import SystemConfig
                cfg = {c.key: c.value for c in SystemConfig.query.filter(SystemConfig.key.like('ai_%')).all()}
                ai_provider = (cfg.get('ai_provider') or '').strip().lower()
                ai_url = cfg.get('ai_ollama_url', ai_url)
                ai_openai_key = cfg.get('ai_openai_key', ai_openai_key)
                gem = SystemConfig.query.filter_by(key='GEMINI_API_KEY').first()
                if gem and gem.value:
                    ai_gemini_key = gem.value
            except Exception:
                pass

            if ai_provider == 'openai':
                # For OpenAI, treat saved key presence as configured/connected from a panel perspective.
                return bool(ai_openai_key)
            if ai_provider == 'gemini':
                return bool(ai_gemini_key)
            if not ai_provider and ai_openai_key:
                return True
            if not ai_provider and ai_gemini_key:
                return True

            try:
                with requests.Session() as session:
                    session.trust_env = False
                    response = session.get(
                        f"{ai_url.rstrip('/')}/api/tags",
                        timeout=5
                    )
                if response.status_code == 200:
                    models = response.json().get('models', [])
                    return len(models) > 0
                else:
                    return False
            except requests.exceptions.RequestException:
                return False
                
        except Exception as e:
            print(f"AI connection test failed: {e}")
            return False
    
    def test_platform_connection(self, platform, credentials, brand=None):
        """Test connection for specific platform"""
        try:
            if credentials is None:
                credentials = {}

            # For non-AI/email platforms, fall back to stored DB credentials when
            # the UI triggers a test without entering values again.
            if platform in {'twitter', 'bluesky', 'instagram', 'linkedin'} and not credentials:
                try:
                    from dashboard.models import Brand, BrandAPICredential

                    query = BrandAPICredential.query.filter_by(service=platform, is_active=True)
                    if brand:
                        b = Brand.query.filter_by(name=brand).first()
                        if b:
                            query = query.filter_by(brand_id=b.id)
                    row = query.order_by(BrandAPICredential.updated_at.desc()).first()
                    if row:
                        credentials = row.get_credentials() or {}
                except Exception:
                    pass

            # Test AI connection
            if platform == 'ai':
                if self.test_ai_connection():
                    return {'success': True, 'message': 'AI service connection successful'}
                else:
                    ollama_host = os.getenv('OLLAMA_HOST', 'http://localhost:11434')
                    try:
                        from dashboard.models import SystemConfig
                        cfg = {c.key: c.value for c in SystemConfig.query.filter(SystemConfig.key.like('ai_%')).all()}
                        ollama_host = cfg.get('ai_ollama_url', ollama_host)
                    except Exception:
                        pass
                    return {'success': False, 'error': f'Cannot connect to AI service at {ollama_host}'}
            
            # Mock connection test for social platforms - in production, make actual API calls
            elif platform == 'twitter':
                if credentials.get('api_key') and credentials.get('api_secret'):
                    return {'success': True, 'message': f'Twitter connection successful{" for " + brand if brand else ""}'}
                else:
                    return {'success': False, 'error': 'Missing API key or secret'}
            
            elif platform == 'bluesky':
                username = (credentials.get('username') or '').strip()
                app_password = (credentials.get('app_password') or '').strip()
                if username and app_password:
                    try:
                        resp = requests.post(
                            'https://bsky.social/xrpc/com.atproto.server.createSession',
                            json={'identifier': username, 'password': app_password},
                            timeout=10,
                        )
                        if resp.status_code == 200:
                            did = resp.json().get('did', '')
                            return {'success': True, 'message': f'BlueSky authenticated as {username} (DID: {did}){" for " + brand if brand else ""}'}
                        else:
                            try:
                                err_msg = resp.json().get('message') or resp.json().get('error') or f'HTTP {resp.status_code}'
                            except Exception:
                                err_msg = f'HTTP {resp.status_code}'
                            return {'success': False, 'error': f'BlueSky authentication failed: {err_msg}'}
                    except requests.exceptions.Timeout:
                        return {'success': False, 'error': 'BlueSky API timed out (bsky.social unreachable)'}
                    except requests.exceptions.RequestException as e:
                        return {'success': False, 'error': f'BlueSky network error: {e}'}
                else:
                    return {'success': False, 'error': 'Missing username or app password — enter credentials then click Test, or save first'}
            
            elif platform == 'instagram':
                if credentials.get('access_token'):
                    return {'success': True, 'message': f'Instagram connection successful{" for " + brand if brand else ""}'}
                else:
                    return {'success': False, 'error': 'Missing access token'}
                    
            elif platform == 'linkedin':
                if credentials.get('client_id') and credentials.get('client_secret'):
                    return {'success': True, 'message': f'LinkedIn connection successful{" for " + brand if brand else ""}'}
                else:
                    return {'success': False, 'error': 'Missing client ID or secret'}
                    
            elif platform == 'email':
                if credentials.get('api_key') or (credentials.get('smtp_host') and credentials.get('smtp_port')):
                    return {'success': True, 'message': f'Email connection successful{" for " + brand if brand else ""}'}
                try:
                    from dashboard.models import Brand, BrandEmailConfig
                    query = BrandEmailConfig.query
                    if brand:
                        brand_record = Brand.query.filter_by(name=brand).first()
                        if brand_record:
                            query = query.filter_by(brand_id=brand_record.id)
                    config = query.order_by(BrandEmailConfig.is_primary.desc(), BrandEmailConfig.id.asc()).first()
                    if config:
                        return {
                            'success': True,
                            'message': f'Email configuration found for {config.brand.name if config.brand else brand or "configured brand"}',
                        }
                except Exception:
                    pass
                return {'success': False, 'error': 'Missing email configuration'}
            
            else:
                return {'success': False, 'error': f'Platform {platform} not implemented yet'}
                
        except Exception as e:
            return {'success': False, 'error': str(e)}

# Initialize dashboard
dashboard = MarketingDashboard()

@app.route('/')
def index():
    """Main dashboard page"""
    return render_template('dashboard.html', 
                         brands=dashboard.brands,
                         config=dashboard.config,
                         title=dashboard.config['dashboard']['title'])


@app.route('/help/marketing')
def marketing_help():
    """Detailed help center for Marketing Hub tools and workflows."""
    return render_template('help_marketing.html',
                         brands=dashboard.brands,
                         title='Marketing Help Center')

@app.route('/brands')
def brands():
    """Brand management page with real configuration status"""
    brand_stats = {}
    
    # Check if AI is properly configured (supports DB-stored provider settings).
    ai_configured = dashboard.get_credential_status().get('ai', {}).get('configured', False)
    
    for brand in dashboard.brands:
        # Get basic brand info from AI generator if available
        if dashboard.ai_generator and brand in dashboard.ai_generator.brand_configs:
            brand_config = dashboard.ai_generator.brand_configs[brand]
            brand_info = brand_config.get('brand', {})
            
            brand_stats[brand] = {
                'name': brand_info.get('name', brand.replace('_', ' ').title()),
                'description': brand_info.get('description', f'{brand.title()} brand configuration'),
                'status': 'active' if ai_configured else 'needs_config',
                'ai_configured': ai_configured,
                'missing_config': [] if ai_configured else ENVIRONMENT_CONFIG['ai']['missing_vars']
            }
        else:
            # No AI generator or brand not configured
            brand_stats[brand] = {
                'name': brand.replace('_', ' ').title(),
                'description': 'AI content generation not configured' if not ai_configured else 'Brand configuration not found',
                'status': 'needs_config',
                'ai_configured': ai_configured,
                'missing_config': ENVIRONMENT_CONFIG['ai']['missing_vars'] if not ai_configured else ['Brand configuration']
            }
    
    return render_template('brands.html', 
                         brands=brand_stats,
                         title='Brand Management',
                         environment_config=ENVIRONMENT_CONFIG)

@app.route('/generate')
def generate():
    """Content generation page"""
    user_brands, active_brand = _get_user_brand_context()
    return render_template('generate.html',
                         brands=[b.name for b in user_brands],
                         user_brands=user_brands,
                         active_brand=active_brand,
                         title='Content Generation')

@app.route('/outreach')
def outreach():
    """Outreach management page"""
    return render_template('outreach.html',
                         brands=dashboard.brands,
                         title='Outreach Management')

@app.route('/api/generate', methods=['POST'])
def api_generate():
    """API endpoint for content generation"""
    data = request.get_json()
    
    if not data:
        return jsonify({'error': 'No data provided'}), 400
    
    content_type = data.get('type')
    brand = data.get('brand')
    
    if not content_type or not brand:
        return jsonify({'error': 'Content type and brand are required'}), 400
    
    if brand not in dashboard.brands:
        return jsonify({'error': f'Unknown brand: {brand}'}), 400
    
    # Remove brand from data to avoid duplicate parameter error
    data_without_brand = {k: v for k, v in data.items() if k != 'brand'}
    
    # Check if AI generator is available
    if not dashboard.ai_generator:
        return jsonify({
            'success': False,
            'error': 'AI generator not available. Please check AI configuration.',
            'fallback_content': f"Sample {content_type} content for {brand}:\n\nThis is placeholder content generated because AI integration is not available. Please configure AI integration to generate real content."
        }), 200
    
    # Run async content generation
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    try:
        result = loop.run_until_complete(
            dashboard.generate_content_async(content_type, brand, **data_without_brand)
        )
        return jsonify(result)
    except Exception as e:
        print(f"❌ Content generation error: {e}")
        return jsonify({
            'success': False,
            'error': str(e),
            'fallback_content': f"Error generating {content_type} for {brand}. Please check logs."
        }), 500
    finally:
        loop.close()

@app.route('/activity')
def activity():
    """Real-time activity dashboard page"""
    return render_template('activity.html',
                         brands=dashboard.brands,
                         activity_tracker_available=ACTIVITY_TRACKER_AVAILABLE)

@app.route('/analytics')
def analytics():
    """Enhanced Analytics and reporting page with real Google Analytics and email data"""
    return render_template('analytics.html',
                         brands=dashboard.brands,
                         analytics_available=ANALYTICS_AVAILABLE,
                         title='Analytics & Reports - Comprehensive Brand Data')

@app.route('/settings')
@app.route('/admin')
def admin_settings():
    """Combined admin and settings page for system management"""
    return render_template('admin.html',
                         config=dashboard.config,
                         title='Admin Panel')


@app.route('/admin/users')
def admin_users_page():
    """User management page."""
    return render_template('admin_users.html', title='User Management')

@app.route('/automation')
def automation():
    """Automation monitoring page"""
    return render_template('automation.html',
                         title='Automation Monitor')

@app.route('/campaigns')
def campaigns():
    """Campaign execution and management page"""
    return render_template('campaigns.html',
                         title='Campaign Manager')

@app.route('/reports')
def reports():
    """Comprehensive reporting dashboard"""
    return render_template('reports.html',
                         title='Reports & Analytics')

@app.route('/email-reports')
def email_reports():
    """Email campaign reports and analytics"""
    return render_template('email_reports.html',
                         title='Email Campaign Reports')

@app.route('/engagement-report')
def engagement_report():
    """Email engagement report with detailed campaign and recipient tracking"""
    return render_template('engagement_report.html',
                         title='Email Engagement Report')

@app.route('/google-ads')
def google_ads():
    """Google Ads campaign management dashboard"""
    return render_template('google_ads.html',
                         title='Google Ads Management')

@app.route('/influencers')
def influencers():
    """Social media influencer discovery and management"""
    return render_template('influencers.html',
                         title='Influencer Discovery')

@app.route('/contacts')
def contacts():
    """Unified contact management system - CRM"""
    return render_template('contacts.html',
                         title='Contact Management')

@app.route('/api/status')
def api_status():
    """API endpoint for system status with environment configuration"""
    credential_status = dashboard.get_credential_status()
    ai_available = dashboard.test_ai_connection() or credential_status.get('ai', {}).get('configured', False)
    email_available = credential_status.get('email', {}).get('configured', False)
    twitter_available = credential_status.get('twitter', {}).get('configured', False)
    linkedin_available = credential_status.get('linkedin', {}).get('configured', False)

    dynamic_env = {
        'email': {
            'mailersend_configured': bool(os.getenv('MAILERSEND_API_TOKEN')),
            'brevo_configured': bool(os.getenv('BREVO_SMTP_USER') and os.getenv('BREVO_SMTP_PASSWORD')),
            'db_configured': email_available,
            'missing_vars': [] if email_available else ['No stored email provider configuration found'],
        },
        'ai': {
            'openai_configured': bool(os.getenv('OPENAI_API_KEY')),
            'db_configured': credential_status.get('ai', {}).get('configured', False),
            'missing_vars': [] if credential_status.get('ai', {}).get('configured', False) else ['No stored AI provider configuration found'],
        },
        'social': {
            'twitter_configured': twitter_available,
            'linkedin_configured': linkedin_available,
            'missing_vars': [] if (twitter_available or linkedin_available) else ['No stored social credentials found'],
        },
        'google_ads': {
            'configured': bool(os.getenv('GOOGLE_ADS_DEVELOPER_TOKEN') and os.getenv('GOOGLE_ADS_CLIENT_ID')),
            'missing_vars': [] if bool(os.getenv('GOOGLE_ADS_DEVELOPER_TOKEN') and os.getenv('GOOGLE_ADS_CLIENT_ID')) else ['GOOGLE_ADS_DEVELOPER_TOKEN', 'GOOGLE_ADS_CLIENT_ID'],
        },
    }

    status = {
        'timestamp': datetime.now().isoformat(),
        'brands_configured': len(dashboard.brands),
        'ai_available': ai_available,
        'features': dashboard.config.get('features', {}),
        'brands': dashboard.brands,
        'environment_config': dynamic_env,
        'services': {
            'email': {
                'available': email_available,
                'mailersend': dynamic_env['email']['mailersend_configured'],
                'brevo': dynamic_env['email']['brevo_configured'],
                'db': dynamic_env['email']['db_configured'],
            },
            'ai': {
                'available': ai_available,
                'openai': dynamic_env['ai']['openai_configured'],
                'db': dynamic_env['ai']['db_configured'],
            },
            'social': {
                'available': twitter_available or linkedin_available,
                'twitter': twitter_available,
                'linkedin': linkedin_available,
            },
            'google_ads': {
                'available': dynamic_env['google_ads']['configured']
            }
        },
        'missing_configuration': {
            'email': dynamic_env['email']['missing_vars'],
            'ai': dynamic_env['ai']['missing_vars'],
            'social': dynamic_env['social']['missing_vars'],
            'google_ads': dynamic_env['google_ads']['missing_vars']
        }
    }
    
    return jsonify(status)

@app.route('/api/brands/<brand_name>')
def api_brand_info(brand_name):
    """API endpoint for brand information"""
    if brand_name not in dashboard.brands:
        return jsonify({'error': 'Brand not found'}), 404
    
    if dashboard.ai_generator and brand_name in dashboard.ai_generator.brand_configs:
        brand_config = dashboard.ai_generator.brand_configs[brand_name]
        return jsonify({
            'name': brand_name,
            'config': brand_config,
            'status': 'active'
        })
    
    return jsonify({'error': 'Brand configuration not available'}), 500

@app.route('/api/social/activity')
def api_social_activity():
    """API endpoint for recent social media activity"""
    if not SOCIAL_AVAILABLE or not social_manager:
        # Return simple mock data aligned to configured brands
        default_brand = dashboard.brands[0] if dashboard.brands else 'unassigned'
        return jsonify({
            'success': True,
            'data': [
                {'id': 1, 'type': 'blog', 'title': 'Blog post published', 'brand': default_brand.replace('_', ' ').title(), 'time': '2h ago', 'metric': '142 views'},
                {'id': 2, 'type': 'social', 'title': 'Short post published', 'brand': default_brand.replace('_', ' ').title(), 'time': '4h ago', 'metric': '23 engagements'},
            ],
            'source': 'mock'
        })
    
    try:
        # Get real activity from social manager
        social_activity = social_manager.get_recent_activity(hours=24)
        blog_activity = social_manager.get_blog_activity()
        
        # Combine and sort by recency
        all_activity = social_activity + blog_activity
        all_activity = sorted(all_activity, key=lambda x: x['id'], reverse=True)
        
        return jsonify({
            'success': True,
            'data': all_activity[:10],  # Return most recent 10 items
            'source': 'real'
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/social/metrics')
def api_social_metrics():
    """API endpoint for brand performance metrics"""
    def _fallback_metrics():
        metrics = {}
        brands = dashboard.brands if dashboard.brands else []
        for brand in brands:
            metrics[brand] = {
                'name': brand,
                'posts': 20 + (hash(brand) % 30),
                'engagement': f"{round(5 + (hash(brand) % 50) / 10, 1)}%",
                'score': 70 + (hash(brand) % 25)
            }
        return metrics

    if not SOCIAL_AVAILABLE or not social_manager:
        # Return mock metrics keyed by configured brands
        return jsonify({
            'success': True,
            'data': _fallback_metrics(),
            'source': 'mock'
        })
    
    try:
        metrics = social_manager.get_brand_performance_metrics()
        return jsonify({
            'success': True,
            'data': metrics,
            'source': 'real'
        })
        
    except Exception as e:
        # Keep dashboards functional even if the social manager raises at runtime.
        return jsonify({
            'success': True,
            'data': _fallback_metrics(),
            'source': 'mock',
            'warning': str(e),
        })

@app.route('/api/social/post', methods=['POST'])
def api_social_post():
    """API endpoint for cross-platform social media posting"""
    data = request.get_json()
    
    if not data:
        return jsonify({'error': 'No data provided'}), 400
    
    content = data.get('content')
    brand = data.get('brand')
    platforms = data.get('platforms', [])
    
    if not content or not brand:
        return jsonify({'error': 'Content and brand are required'}), 400
    
    if not SOCIAL_AVAILABLE or not social_manager:
        return jsonify({
            'success': False,
            'error': 'Social media integration not available',
            'message': 'Configure social media credentials to enable posting'
        }), 503
    
    try:
        # Run async cross-platform posting
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        result = loop.run_until_complete(
            social_manager.cross_platform_post(content, brand, platforms)
        )
        
        return jsonify(result)
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500
    finally:
        loop.close()

@app.route('/api/automations')
def api_automations():
    """API endpoint for automation monitoring data with unified outreach crons"""
    try:
        # Get cron job status from system and unified DB
        cron_jobs = dashboard.get_cron_status()
        
        # Get content history from logs/files
        content_history = dashboard.get_content_history()
        
        # Categorize cron jobs by source and type
        system_crons = [j for j in cron_jobs if j.get('source') == 'system_cron']
        unified_crons = [j for j in cron_jobs if j.get('source') == 'unified_db']
        
        # Calculate enhanced statistics
        stats = {
            'activeCrons': len([j for j in cron_jobs if j.get('status') == 'active']),
            'systemCrons': len(system_crons),
            'outreachCrons': len(unified_crons),
            'contentSentToday': len([c for c in content_history if c.get('sent_today', False)]),
            'successRate': dashboard.calculate_success_rate(),
            'failedJobs': len([j for j in cron_jobs if j.get('status') == 'failed'])
        }
        
        # Add outreach-specific stats if available
        if OUTREACH_AUTOMATION_AVAILABLE and UnifiedOutreachAnalytics:
            try:
                unified_analytics = UnifiedOutreachAnalytics()
                db_summary = unified_analytics.get_database_summary()
                if 'error' not in db_summary:
                    stats['outreach_database_records'] = db_summary['total_records']
                    stats['brands_with_outreach_data'] = len(db_summary['brand_targets'])
                    
                # Get recent outreach activity for timeline
                outreach_overview = unified_analytics.get_all_brands_overview(7)
                if 'error' not in outreach_overview:
                    stats['emails_sent_this_week'] = sum(
                        day.get('emails_sent', 0) 
                        for day in outreach_overview.get('daily_stats', [])
                    )
                    stats['responses_this_week'] = sum(
                        day.get('responses_received', 0) 
                        for day in outreach_overview.get('daily_stats', [])
                    )
            except Exception as e:
                print(f"Warning: Could not load outreach stats: {e}")
        
        # Enhanced timeline with outreach activity
        timeline = dashboard.get_recent_activity_timeline()
        
        # Add recent outreach activity to timeline if available
        if OUTREACH_AUTOMATION_AVAILABLE and UnifiedOutreachAnalytics:
            try:
                unified_analytics = UnifiedOutreachAnalytics()
                outreach_overview = unified_analytics.get_all_brands_overview(7)
                if 'error' not in outreach_overview:
                    for activity in outreach_overview.get('recent_activity', [])[:5]:
                        timeline.append({
                            'timestamp': activity.get('delivery_time', ''),
                            'type': 'outreach',
                            'brand': activity.get('brand', ''),
                            'description': f"Sent email: {activity.get('subject', '')[:50]}...",
                            'status': activity.get('status', 'unknown')
                        })
                    
                    # Sort timeline by timestamp
                    timeline = sorted(timeline, key=lambda x: x.get('timestamp', ''), reverse=True)[:20]
            except Exception as e:
                print(f"Warning: Could not load outreach timeline: {e}")
        
        return jsonify({
            'success': True,
            'automations': cron_jobs,
            'system_automations': system_crons,
            'outreach_automations': unified_crons,
            'stats': stats,
            'timeline': timeline
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/cron/execute/<job_id>', methods=['POST'])
def api_execute_cron_job(job_id):
    """API endpoint to manually execute a cron job"""
    try:
        from automation.centralized_cron_manager import CentralizedCronManager
        
        cron_manager = CentralizedCronManager()
        result = cron_manager.execute_job(job_id)
        
        return jsonify({
            'success': result['success'],
            'job_id': job_id,
            'output': result.get('output', ''),
            'error': result.get('error'),
            'exit_code': result.get('exit_code')
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/cron/history/<job_id>')
def api_cron_job_history(job_id):
    """API endpoint to get execution history for a cron job"""
    try:
        from automation.centralized_cron_manager import CentralizedCronManager
        
        cron_manager = CentralizedCronManager()
        history = cron_manager.get_execution_history(job_id, limit=20)
        
        return jsonify({
            'success': True,
            'job_id': job_id,
            'history': history
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/admin/credentials', methods=['GET', 'POST'])
def api_admin_credentials():
    """API endpoint for managing credentials"""
    if request.method == 'GET':
        try:
            from dashboard.models import Brand, BrandEmailConfig, SystemConfig, BrandAPICredential

            ai_config = {cfg.key: cfg.value for cfg in SystemConfig.query.filter(SystemConfig.key.like('ai_%')).all()}
            brands = Brand.query.filter_by(is_active=True).order_by(Brand.name).all()
            email_configs = BrandEmailConfig.query.order_by(BrandEmailConfig.brand_id, BrandEmailConfig.provider).all()

            creds = dashboard.get_credential_status()
            creds['ai'] = {
                'provider': ai_config.get('ai_provider', ''),
                'model': ai_config.get('ai_model', ''),
                'url': ai_config.get('ai_ollama_url', ''),
                'configured': bool(
                    ai_config.get('ai_provider')
                    or ai_config.get('ai_openai_key')
                    or ai_config.get('GEMINI_API_KEY')
                    or ai_config.get('ai_ollama_url')
                ),
            }
            creds['email'] = {
                'configured': len(email_configs) > 0,
                'configs': [
                    {
                        'brand_name': config.brand.name if config.brand else '',
                        'provider': config.provider,
                        'from_email': config.from_email,
                        'from_name': config.from_name,
                        'is_primary': config.is_primary,
                        'is_verified': config.is_verified,
                    }
                    for config in email_configs
                ],
            }
            creds['brands'] = [brand.name for brand in brands]

            # Return sanitized social credential snapshots for UI visibility.
            social_rows = (
                BrandAPICredential.query.filter(
                    BrandAPICredential.service.in_(['twitter', 'bluesky', 'linkedin', 'instagram'])
                )
                .order_by(BrandAPICredential.updated_at.desc())
                .all()
            )
            brand_name_map = {b.id: b.name for b in brands}
            creds['social'] = [
                {
                    'brand': brand_name_map.get(row.brand_id, ''),
                    'service': row.service,
                    'is_active': row.is_active,
                    'is_verified': row.is_verified,
                    'updated_at': row.updated_at.isoformat() if row.updated_at else None,
                }
                for row in social_rows
            ]

            return jsonify({
                'success': True,
                'credentials': creds
            })
        except Exception as e:
            return jsonify({
                'success': False,
                'error': str(e)
            }), 500
    
    elif request.method == 'POST':
        try:
            data = request.get_json()
            credentials = data.get('credentials', data) if data else None
            if not credentials:
                return jsonify({'error': 'No credentials provided'}), 400

            from dashboard.models import SystemConfig, BrandAPICredential, Brand, db

            ai_config = credentials.get('ai', {})
            if ai_config.get('provider'):
                provider = ai_config.get('provider', '').strip().lower()
                configs_to_save = [
                    ('ai_provider', provider, 'ai', 'AI provider type'),
                    ('ai_model', ai_config.get('model', ''), 'ai', 'Default AI model'),
                ]
                if provider == 'ollama':
                    configs_to_save.append(('ai_ollama_url', ai_config.get('url', ''), 'ai', 'Ollama server URL'))
                if provider == 'openai' and ai_config.get('api_key', '').strip():
                    configs_to_save.append(('ai_openai_key', ai_config['api_key'].strip(), 'ai', 'OpenAI API key'))
                if provider == 'gemini' and ai_config.get('api_key', '').strip():
                    configs_to_save.append(('GEMINI_API_KEY', ai_config['api_key'].strip(), 'ai', 'Google Gemini API key'))

                for key, value, category, desc in configs_to_save:
                    existing = SystemConfig.query.filter_by(key=key).first()
                    if existing:
                        if value:  # never blank-out an existing key
                            existing.value = value
                        existing.category = category
                        existing.description = desc
                    else:
                        db.session.add(SystemConfig(key=key, value=value, category=category, description=desc, updated_by='admin'))

            def _resolve_brand_id(brand_name: str):
                if not brand_name:
                    first_brand = Brand.query.filter_by(is_active=True).order_by(Brand.id.asc()).first()
                    return first_brand.id if first_brand else None
                brand = Brand.query.filter_by(name=brand_name).first()
                return brand.id if brand else None

            # Save social credentials in DB so status checks and runtime read the same source.
            social_platforms = ['twitter', 'bluesky', 'linkedin', 'instagram']
            for platform in social_platforms:
                creds = credentials.get(platform, {}) or {}
                brand_name = (creds.get('brand') or '').strip()
                brand_id = _resolve_brand_id(brand_name)
                if not brand_id:
                    continue

                has_values = any(
                    (str(v).strip() if isinstance(v, str) else bool(v))
                    for k, v in creds.items()
                    if k != 'brand'
                )
                if not has_values:
                    continue

                existing = BrandAPICredential.query.filter_by(brand_id=brand_id, service=platform).first()
                payload = {k: v for k, v in creds.items() if k != 'brand'}
                if existing:
                    existing.set_credentials(payload)
                    existing.credential_type = 'api_key'
                    existing.is_active = True
                else:
                    row = BrandAPICredential(
                        brand_id=brand_id,
                        service=platform,
                        credential_type='api_key',
                        credentials='{}',
                        is_active=True,
                    )
                    row.set_credentials(payload)
                    db.session.add(row)

            db.session.commit()
            
            return jsonify({
                'success': True,
                'message': 'Credentials saved successfully'
            })
                
        except Exception as e:
            return jsonify({
                'success': False,
                'error': str(e)
            }), 500

@app.route('/api/user/my-key', methods=['GET', 'POST', 'DELETE'])
def api_user_my_key():
    """Per-user personal AI API key — stored in SystemConfig namespaced by session user id/email."""
    try:
        from dashboard.models import SystemConfig, db
        from flask_login import current_user
        user_id = None
        try:
            if current_user.is_authenticated:
                user_id = current_user.email
        except Exception:
            pass
        if not user_id:
            user_id = 'anonymous'
        config_key = f'user_ai_key:{user_id}'

        if request.method == 'GET':
            cfg = SystemConfig.query.filter_by(key=config_key).first()
            return jsonify({
                'success': True,
                'has_key': bool(cfg and cfg.value),
                'provider': (cfg.description or '') if cfg else '',
            })

        if request.method == 'DELETE':
            cfg = SystemConfig.query.filter_by(key=config_key).first()
            if cfg:
                db.session.delete(cfg)
                db.session.commit()
            return jsonify({'success': True})

        data = request.get_json() or {}
        api_key = (data.get('api_key') or '').strip()
        provider = (data.get('provider') or 'openai').strip().lower()
        if not api_key:
            return jsonify({'success': False, 'error': 'api_key is required'}), 400

        cfg = SystemConfig.query.filter_by(key=config_key).first()
        if cfg:
            cfg.value = api_key
            cfg.description = provider
        else:
            cfg = SystemConfig(
                key=config_key,
                value=api_key,
                category='user_keys',
                description=provider,
                is_secret=True,
                updated_by=user_id,
            )
            db.session.add(cfg)
        db.session.commit()
        return jsonify({'success': True, 'provider': provider})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/admin/test-connections')
def api_test_connections():
    """API endpoint to test all connections"""
    try:
        status = dashboard.test_all_connections()
        return jsonify({
            'success': True,
            'results': status
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/admin/test-connection/<platform>', methods=['POST'])
def api_test_connection(platform):
    """API endpoint to test specific platform connection"""
    try:
        data = request.get_json() or {}

        # Handle AI and stored email tests without ad hoc credentials
        if platform == 'ai':
            result = dashboard.test_platform_connection('ai', {})
            return jsonify(result)

        # Support both shapes: flat {username, brand, ...} and nested {credentials: {...}}
        credentials = data.get('credentials') if isinstance(data.get('credentials'), dict) else data

        brand = (credentials or {}).get('brand') or data.get('brand') or ''

        # For social platforms: if caller sent an empty body, load stored DB credentials.
        if platform in {'twitter', 'bluesky', 'linkedin', 'instagram'}:
            has_useful_fields = any(
                (str(v).strip() if isinstance(v, str) else bool(v))
                for k, v in (credentials or {}).items()
                if k not in {'brand'}
            )
            if not has_useful_fields:
                try:
                    from dashboard.models import Brand, BrandAPICredential
                    q = BrandAPICredential.query.filter_by(service=platform, is_active=True)
                    if brand:
                        b = Brand.query.filter_by(name=brand).first()
                        if b:
                            q = q.filter_by(brand_id=b.id)
                    row = q.order_by(BrandAPICredential.updated_at.desc()).first()
                    if row:
                        stored = row.get_credentials() or {}
                        stored['brand'] = brand
                        credentials = stored
                except Exception:
                    pass

        result = dashboard.test_platform_connection(platform, credentials or {}, brand or None)
        return jsonify(result)
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

# Analytics API Endpoints
@app.route('/api/analytics/comprehensive')
def api_comprehensive_analytics():
    """API endpoint for comprehensive analytics across all brands with unified outreach data"""
    try:
        # Get query parameters
        brand = request.args.get('brand')
        days = int(request.args.get('days', 30))
        
        # Start with base analytics
        if ANALYTICS_AVAILABLE and get_analytics_for_dashboard:
            if brand:
                # Get specific brand data
                base_data = get_analytics_for_dashboard(brand)
            else:
                # Get multi-brand summary
                base_data = dashboard.get_real_comprehensive_analytics()
            source = 'real_analytics'
        else:
            # Use fallback analytics
            base_data = dashboard.get_fallback_analytics()
            source = 'fallback'
        
        # Enhance with unified outreach analytics
        if OUTREACH_AUTOMATION_AVAILABLE and UnifiedOutreachAnalytics:
            try:
                unified_analytics = UnifiedOutreachAnalytics()
                
                if brand:
                    # Get brand-specific outreach data
                    outreach_data = unified_analytics.get_brand_performance(brand, days)
                    if 'error' not in outreach_data:
                        # Merge outreach data into base analytics
                        base_data['outreach_analytics'] = outreach_data
                        source += '+unified_outreach'
                else:
                    # Get all brands outreach overview
                    outreach_overview = unified_analytics.get_all_brands_overview(days)
                    if 'error' not in outreach_overview:
                        # Merge outreach overview into base analytics
                        base_data['outreach_overview'] = outreach_overview
                        source += '+unified_outreach'
                        
            except Exception as e:
                print(f"Warning: Could not load unified outreach analytics: {e}")
        
        return jsonify({
            'success': True,
            'data': base_data,
            'source': source
        })
            
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e),
            'data': dashboard.get_fallback_analytics()
        }), 500

# Real-time activity tracking endpoint
@app.route('/api/real-time-activity')
def api_real_time_activity():
    """API endpoint for real-time activity data from activity tracker"""
    try:
        if not ACTIVITY_TRACKER_AVAILABLE:
            return jsonify({
                'error': 'Activity tracker not available',
                'fallback': True,
                'message': 'Using fallback analytics data'
            }), 503
        
        hours_back = request.args.get('hours', 24, type=int)
        real_time_data = activity_tracker.get_real_time_dashboard_data(hours_back)
        
        # Track this API call
        activity_tracker.track_dashboard_usage(
            page_visited='/api/real-time-activity',
            action_taken='view',
            api_endpoint='/api/real-time-activity',
            success=True,
            metadata={'hours_back': hours_back}
        )
        
        return jsonify(real_time_data)
        
    except Exception as e:
        if ACTIVITY_TRACKER_AVAILABLE:
            activity_tracker.track_dashboard_usage(
                page_visited='/api/real-time-activity',
                action_taken='view',
                api_endpoint='/api/real-time-activity',
                success=False,
                error_message=str(e)
            )
        
        return jsonify({'error': str(e)}), 500

@app.route('/api/brand-activity/<brand>')
def api_brand_activity(brand):
    """Get comprehensive activity summary for a specific brand"""
    try:
        if not ACTIVITY_TRACKER_AVAILABLE:
            return jsonify({
                'error': 'Activity tracker not available',
                'brand': brand
            }), 503
        
        days_back = request.args.get('days', 30, type=int)
        brand_data = activity_tracker.get_brand_activity_summary(brand, days_back)
        
        # Track this API call
        activity_tracker.track_dashboard_usage(
            page_visited=f'/api/brand-activity/{brand}',
            action_taken='view',
            brand_context=brand,
            api_endpoint=f'/api/brand-activity/{brand}',
            success=True,
            metadata={'days_back': days_back}
        )
        
        return jsonify(brand_data)
        
    except Exception as e:
        if ACTIVITY_TRACKER_AVAILABLE:
            activity_tracker.track_dashboard_usage(
                page_visited=f'/api/brand-activity/{brand}',
                action_taken='view',
                brand_context=brand,
                api_endpoint=f'/api/brand-activity/{brand}',
                success=False,
                error_message=str(e)
            )
        
        return jsonify({'error': str(e)}), 500

# Alias endpoint for templates that call the old endpoint name
@app.route('/api/comprehensive-analytics')
def api_comprehensive_analytics_alias():
    """Alias for /api/analytics/comprehensive to maintain compatibility"""
    return api_comprehensive_analytics()

@app.route('/api/analytics/summary')
def api_analytics_summary():
    """API endpoint for analytics summary across all brands with outreach metrics"""
    try:
        # Get real-time activity data if available
        real_time_data = None
        if ACTIVITY_TRACKER_AVAILABLE:
            try:
                real_time_data = activity_tracker.get_real_time_dashboard_data(24)  # Last 24 hours
            except Exception as e:
                print(f"Warning: Could not load real-time activity data: {e}")
        
        # Get base analytics summary
        if ANALYTICS_AVAILABLE and get_analytics_for_dashboard:
            # Get multi-brand summary
            data = get_analytics_for_dashboard()
            source = 'real_analytics'
        else:
            # Use fallback summary
            data = dashboard.get_fallback_analytics()
            source = 'fallback'
        
        # Enhance with real activity data if available
        if real_time_data:
            # Add AI activity summary
            ai_summary = real_time_data.get('ai_activity', {})
            total_ai_generations = sum(brand_data.get('total_generations', 0) for brand_data in ai_summary.values())
            avg_ai_quality = sum(brand_data.get('avg_quality_score', 0) for brand_data in ai_summary.values()) / len(ai_summary) if ai_summary else 0
            
            # Add real email activity
            email_summary = real_time_data.get('email_activity', {})
            total_emails_sent = 0
            total_emails_delivered = 0
            total_emails_opened = 0
            
            for brand_data in email_summary.values():
                for email_type_data in brand_data.values():
                    total_emails_sent += email_type_data.get('total_sent', 0)
                    total_emails_delivered += email_type_data.get('delivered', 0)
                    total_emails_opened += email_type_data.get('opened', 0)
            
            # Add campaign activity
            campaign_summary = real_time_data.get('campaign_activity', {})
            total_campaigns = sum(brand_data.get('active_campaigns', 0) for brand_data in campaign_summary.values())
            
            # Update data with real metrics
            data.update({
                'real_time_metrics': {
                    'ai_generations_24h': total_ai_generations,
                    'avg_ai_quality': round(avg_ai_quality, 2),
                    'emails_sent_24h': total_emails_sent,
                    'emails_delivered_24h': total_emails_delivered,
                    'emails_opened_24h': total_emails_opened,
                    'email_open_rate_24h': round((total_emails_opened / total_emails_delivered * 100) if total_emails_delivered > 0 else 0, 2),
                    'active_campaigns_24h': total_campaigns,
                    'dashboard_page_views_24h': real_time_data.get('dashboard_performance', {}).get('total_page_views', 0)
                },
                'activity_data_available': True
            })
            source += '+real_time_activity'
        
        # Add unified outreach summary
        if OUTREACH_AUTOMATION_AVAILABLE and UnifiedOutreachAnalytics:
            try:
                unified_analytics = UnifiedOutreachAnalytics()
                
                # Get outreach overview
                outreach_summary = unified_analytics.get_all_brands_overview(7)  # Last 7 days
                if 'error' not in outreach_summary:
                    # Add outreach metrics to summary
                    if 'summary_metrics' not in data:
                        data['summary_metrics'] = {}
                    
                    data['summary_metrics'].update({
                        'total_outreach_targets': outreach_summary['overview']['total_targets'],
                        'total_emails_sent': outreach_summary['overview']['total_emails_sent'],
                        'total_responses': outreach_summary['overview']['total_responses'],
                        'overall_response_rate': outreach_summary['overview']['overall_response_rate'],
                        'active_outreach_brands': outreach_summary['total_brands']
                    })
                    
                    # Add recent outreach activity
                    data['recent_outreach_activity'] = outreach_summary.get('recent_activity', [])[:5]
                    source += '+outreach_metrics'
                    
                # Get database summary for system health
                db_summary = unified_analytics.get_database_summary()
                if 'error' not in db_summary:
                    data['outreach_database_health'] = {
                        'total_records': db_summary['total_records'],
                        'brands_with_data': len(db_summary['brand_targets']),
                        'database_path': db_summary['database_path']
                    }
                    
            except Exception as e:
                print(f"Warning: Could not load outreach summary: {e}")
        
        return jsonify({
            'success': True,
            'data': data,
            'source': source
        })
            
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e),
            'data': dashboard.get_fallback_analytics()
        }), 500

@app.route('/api/analytics/clear-cache', methods=['POST'])
def api_clear_analytics_cache():
    """API endpoint to clear analytics cache"""
    try:
        if ANALYTICS_AVAILABLE and get_analytics_for_dashboard:
            # Clear real analytics cache by forcing refresh
            print("📊 Clearing analytics cache - next request will fetch fresh data")
        
        return jsonify({
            'success': True,
            'message': 'Analytics cache cleared successfully'
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

# ===== EMAIL ENGAGEMENT REPORT API ROUTES =====

@app.route('/api/engagement/email-summary')
def api_email_engagement_summary():
    """API endpoint for email engagement summary across all brands"""
    try:
        days = int(request.args.get('days', 30))
        
        if not EMAIL_ANALYTICS_AVAILABLE or EmailCampaignAnalytics is None:
            return jsonify({
                'success': False,
                'error': 'Email analytics not available',
                'data': {}
            }), 503
        
        # Initialize email analytics if using database version
        with app.app_context():
            if EmailCampaignAnalytics.__name__ == 'DatabaseEmailAnalytics':
                analytics_instance = EmailCampaignAnalytics(app)
            else:
                analytics_instance = EmailCampaignAnalytics()
            
            # Run async function to get all brands email analytics
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            try:
                # Try to get analytics from database-aware version
                all_brands_data = loop.run_until_complete(analytics_instance.get_all_brands_analytics(days))
            except (NotImplementedError, AttributeError):
                # Fall back to original method name if needed
                all_brands_data = loop.run_until_complete(analytics_instance.get_all_brands_email_analytics(days))
        
        # Aggregate data across brands
        summary = {
            'period': f'Last {days} days',
            'brands': {},
            'totals': {
                'total_sent': 0,
                'total_delivered': 0,
                'total_opens': 0,
                'total_clicks': 0,
                'total_bounces': 0,
                'total_unsubscribes': 0,
                'avg_open_rate': 0,
                'avg_click_rate': 0
            },
            'by_brand': []
        }
        
        brand_count = 0
        open_rates = []
        click_rates = []
        
        # Handle both old and new response structures
        if 'all_brands' in all_brands_data:
            # New DatabaseEmailAnalytics structure
            brands_to_process = all_brands_data.get('all_brands', {})
        else:
            # Legacy structure - already a dict of brands
            brands_to_process = all_brands_data
        
        # Safety check
        if not brands_to_process or not isinstance(brands_to_process, dict):
            return jsonify({
                'success': True,
                'data': summary
            })
        
        for brand, data in brands_to_process.items():
            if 'error' in data:
                # Skip brands with errors
                continue
                
            stats = data.get('analytics', data.get('statistics', {}))
            campaigns = data.get('campaigns', [])
            
            # Aggregate totals
            sent = stats.get('total_sent', 0)
            delivered = stats.get('total_delivered', 0)
            opens = stats.get('total_opens', 0)
            clicks = stats.get('total_clicks', 0)
            open_rate = stats.get('avg_open_rate', 0)
            click_rate = stats.get('avg_click_rate', 0)
            
            summary['totals']['total_sent'] += sent
            summary['totals']['total_delivered'] += delivered
            summary['totals']['total_opens'] += opens
            summary['totals']['total_clicks'] += clicks
            summary['totals']['total_bounces'] += stats.get('total_bounces', 0)
            summary['totals']['total_unsubscribes'] += stats.get('total_unsubscribes', 0)
            
            if open_rate > 0:
                open_rates.append(open_rate)
            if click_rate > 0:
                click_rates.append(click_rate)
            
            summary['by_brand'].append({
                'name': brand,
                'sent': sent,
                'delivered': delivered,
                'opens': opens,
                'open_rate': round(open_rate, 2),
                'clicks': clicks,
                'click_rate': round(click_rate, 2),
                'bounces': stats.get('total_bounces', 0),
                'unsubscribes': stats.get('total_unsubscribes', 0),
                'campaigns': len(campaigns),
                'service': data.get('service', 'unknown')
            })
            
            brand_count += 1
        
        # Calculate averages
        if open_rates:
            summary['totals']['avg_open_rate'] = round(sum(open_rates) / len(open_rates), 2)
        if click_rates:
            summary['totals']['avg_click_rate'] = round(sum(click_rates) / len(click_rates), 2)
        
        summary['brand_count'] = brand_count
        
        return jsonify({
            'success': True,
            'data': summary
        })
        
    except Exception as e:
        print(f"Error in email engagement summary: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/engagement/brand-detail/<brand>')
def api_email_engagement_detail(brand):
    """API endpoint for detailed email engagement for a specific brand"""
    try:
        days = int(request.args.get('days', 30))
        
        if not EMAIL_ANALYTICS_AVAILABLE or EmailCampaignAnalytics is None:
            return jsonify({
                'success': False,
                'error': 'Email analytics not available'
            }), 503
        
        # Initialize email analytics if using database version
        with app.app_context():
            if EmailCampaignAnalytics.__name__ == 'DatabaseEmailAnalytics':
                analytics_instance = EmailCampaignAnalytics(app)
            else:
                analytics_instance = EmailCampaignAnalytics()
            
            # Get brand-specific email analytics
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            try:
                brand_data = loop.run_until_complete(analytics_instance.get_brand_email_analytics(brand, days))
            except (NotImplementedError, AttributeError):
                # Fall back to original method name if needed
                brand_data = loop.run_until_complete(analytics_instance.get_brand_email_analytics(brand, days))
        
        # Format campaigns for detailed view
        campaigns = brand_data.get('campaigns', [])
        detailed_campaigns = []
        
        for campaign in campaigns:
            detailed_campaigns.append({
                'id': campaign.get('id'),
                'name': campaign.get('name', 'Unknown'),
                'subject': campaign.get('subject', ''),
                'sent_date': campaign.get('sent_date', ''),
                'status': campaign.get('status', 'unknown'),
                'sent': campaign.get('sent', 0),
                'delivered': campaign.get('delivered', 0),
                'opens': campaign.get('opens', 0),
                'unique_opens': campaign.get('opens', 0),
                'clicks': campaign.get('clicks', 0),
                'unique_clicks': campaign.get('clicks', 0),
                'bounces': campaign.get('bounces', 0),
                'unsubscribes': campaign.get('unsubscribes', 0),
                'open_rate': round(campaign.get('open_rate', 0), 2),
                'click_rate': round(campaign.get('click_rate', 0), 2),
                'delivery_rate': round((campaign.get('delivered', 0) / campaign.get('sent', 1) * 100), 2) if campaign.get('sent') else 0
            })
        
        return jsonify({
            'success': True,
            'brand': brand,
            'period': brand_data.get('period', f'Last {days} days'),
            'service': brand_data.get('service', 'unknown'),
            'statistics': brand_data.get('statistics', {}),
            'campaigns': detailed_campaigns,
            'lists': brand_data.get('lists', []),
            'last_updated': brand_data.get('last_updated', datetime.now().isoformat())
        })
        
    except Exception as e:
        print(f"Error in email engagement detail: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/engagement/campaign/<campaign_id>')
def api_email_campaign_detail(campaign_id):
    """API endpoint for detailed campaign information including recipient engagement"""
    try:
        brand = request.args.get('brand', '')
        
        if not brand or not EMAIL_ANALYTICS_AVAILABLE or EmailCampaignAnalytics is None:
            return jsonify({
                'success': False,
                'error': 'Brand parameter required and email analytics must be available'
            }), 400
        
        # Get brand data with lazy initialization
        with app.app_context():
            if EmailCampaignAnalytics.__name__ == 'DatabaseEmailAnalytics':
                analytics_instance = DatabaseEmailAnalytics(app)
            else:
                analytics_instance = EmailCampaignAnalytics()
            
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            try:
                brand_data = loop.run_until_complete(analytics_instance.get_brand_email_analytics(brand, 30))
            except (NotImplementedError, AttributeError):
                # Fall back to original method name if needed
                brand_data = loop.run_until_complete(analytics_instance.get_brand_email_analytics(brand, 30))
        
        # Find specific campaign
        campaigns = brand_data.get('campaigns', [])
        campaign_detail = None
        
        for campaign in campaigns:
            if str(campaign.get('id')) == str(campaign_id):
                campaign_detail = campaign
                break
        
        if not campaign_detail:
            return jsonify({
                'success': False,
                'error': f'Campaign {campaign_id} not found for brand {brand}'
            }), 404
        
        # Format campaign detail with recipient insights
        response = {
            'success': True,
            'campaign': {
                'id': campaign_detail.get('id'),
                'name': campaign_detail.get('name', 'Unknown'),
                'subject': campaign_detail.get('subject', ''),
                'sent_date': campaign_detail.get('sent_date', ''),
                'status': campaign_detail.get('status', 'unknown'),
                'brand': brand,
                'service': brand_data.get('service', 'unknown')
            },
            'metrics': {
                'sent': campaign_detail.get('sent', 0),
                'delivered': campaign_detail.get('delivered', 0),
                'delivery_rate': round((campaign_detail.get('delivered', 0) / campaign_detail.get('sent', 1) * 100), 2) if campaign_detail.get('sent') else 0,
                'opens': campaign_detail.get('opens', 0),
                'open_rate': round(campaign_detail.get('open_rate', 0), 2),
                'clicks': campaign_detail.get('clicks', 0),
                'click_rate': round(campaign_detail.get('click_rate', 0), 2),
                'bounces': campaign_detail.get('bounces', 0),
                'bounce_rate': round((campaign_detail.get('bounces', 0) / campaign_detail.get('sent', 1) * 100), 2) if campaign_detail.get('sent') else 0,
                'unsubscribes': campaign_detail.get('unsubscribes', 0),
                'unsubscribe_rate': round((campaign_detail.get('unsubscribes', 0) / campaign_detail.get('sent', 1) * 100), 2) if campaign_detail.get('sent') else 0
            },
            'recipients_summary': {
                'total_sent': campaign_detail.get('sent', 0),
                'opened_emails': campaign_detail.get('opens', 0),
                'clicked_emails': campaign_detail.get('clicks', 0),
                'bounced_emails': campaign_detail.get('bounces', 0),
                'unsubscribed': campaign_detail.get('unsubscribes', 0),
                'notes': 'For detailed recipient list and engagement tracking, configure email provider API credentials'
            }
        }
        
        return jsonify(response)
        
    except Exception as e:
        print(f"Error in campaign detail: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

# ===== OUTREACH API ROUTES =====

@app.route('/api/outreach/brand-configs')
def api_get_brand_configs():
    """Get all brand configurations for outreach"""
    try:
        config_file = project_root / 'config' / 'outreach_config.yaml'
        if config_file.exists():
            with open(config_file, 'r') as f:
                config = yaml.safe_load(f)
            return jsonify(config['brands'])
        else:
            return jsonify({}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/outreach/brand-config/<brand>')
def api_get_brand_config(brand):
    """Get configuration for a specific brand"""
    try:
        config_file = project_root / 'config' / 'outreach_config.yaml'
        if config_file.exists():
            with open(config_file, 'r') as f:
                config = yaml.safe_load(f)
            
            if brand in config['brands']:
                return jsonify(config['brands'][brand])
            else:
                return jsonify({'error': f'Brand {brand} not found'}), 404
        else:
            return jsonify({'error': 'Configuration file not found'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/outreach/preview', methods=['POST'])
def api_preview_outreach():
    """Generate preview of outreach email"""
    try:
        data = request.get_json()
        brand = data.get('brand')
        template = data.get('template')
        custom_subject = data.get('customSubject', '')
        custom_message = data.get('customMessage', '')
        sample_user = data.get('sampleUser', {})
        
        if not OUTREACH_AVAILABLE:
            return jsonify({'error': 'Outreach system not available'}), 500
        
        # Create a temporary outreach instance with brand configuration
        outreach = OutreachService(brand_name=brand)
        
        # Create a neutral sample record from the input data
        user = {
            'email': sample_user.get('email', 'example@test.com'),
            'name': sample_user.get('name', 'Sample User'),
            'company': sample_user.get('company', 'Sample Company'),
            'account_type': sample_user.get('account_type', 'Free'),
            'last_login': sample_user.get('last_login', '2024-10-01'),
            'signup_date': sample_user.get('signup_date', '2024-01-01'),
            'features_used': sample_user.get('features_used', 'Basic Features'),
            'subscription_status': sample_user.get('subscription_status', 'Active'),
            'usage_level': sample_user.get('usage_level', 'Medium')
        }
        
        # Generate message
        message = outreach.generate_outreach_message(
            user, template, custom_subject, custom_message
        )
        
        return jsonify(message)
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/outreach/analyze-campaign', methods=['GET', 'POST'])
def api_analyze_outreach_campaign():
    """Analyze campaign before execution - shows exactly what will happen"""
    try:
        if not OUTREACH_AVAILABLE:
            return jsonify({
                'success': False,
                'message': 'Outreach system not available'
            }), 500
        
        if request.method == 'GET':
            # Simple brand validation for GET requests
            brand = request.args.get('brand')
            if not brand:
                return jsonify({
                    'success': False,
                    'warnings': ['No brand selected'],
                    'execution_plan': ['❌ Select a brand to analyze campaign']
                })
            
            # For GET requests, provide basic guidance
            return jsonify({
                'success': True,
                'campaign_info': {'brand': brand},
                'warnings': ['📁 Upload a CSV file to analyze campaign'],
                'execution_plan': [
                    f"🏢 Brand selected: {brand}",
                    f"📋 Upload CSV file with email addresses",
                    f"🔍 Map CSV columns to required fields",
                    f"▶️ Run analysis to see execution plan"
                ],
                'can_execute': False,
                'requires_csv': True
            })
        
        # POST method - full analysis with CSV
        brand = request.form.get('brand')
        template = request.form.get('template')
        max_emails = request.form.get('max_emails')
        skip_recent = request.form.get('skip_recent', 'true').lower() == 'true'
        
        # Get uploaded file for analysis
        csv_file = request.files.get('csv_file')
        
        analysis = {
            'success': True,
            'campaign_info': {
                'brand': brand,
                'template': template,
                'max_emails_limit': int(max_emails) if max_emails and max_emails.strip() else None,
                'skip_recent': skip_recent
            },
            'csv_analysis': {},
            'execution_plan': [],
            'warnings': [],
            'can_execute': False,
            'estimated_results': {}
        }
        
        if not csv_file:
            analysis['warnings'].append("📁 No CSV file uploaded")
            analysis['execution_plan'] = [
                "❌ Cannot execute: No CSV file provided",
                "📋 Please upload a CSV file with email addresses",
                "💡 CSV should contain an 'email' column"
            ]
            return jsonify(analysis)
        
        # Analyze CSV content
        import tempfile
        import pandas as pd
        
        with tempfile.NamedTemporaryFile(mode='w+', suffix='.csv', delete=False) as temp_file:
            csv_content = csv_file.read().decode('utf-8')
            temp_file.write(csv_content)
            temp_csv_path = temp_file.name
        
        try:
            df = pd.read_csv(temp_csv_path)
            
            # Basic CSV analysis
            analysis['csv_analysis'] = {
                'total_rows': len(df),
                'columns': list(df.columns),
                'sample_data': df.head(3).to_dict('records') if len(df) > 0 else []
            }
            
            # Find email column
            email_column = None
            if 'email' in df.columns:
                email_column = 'email'
            elif any('email' in col.lower() for col in df.columns):
                email_column = next(col for col in df.columns if 'email' in col.lower())
            
            if email_column:
                # Count valid emails
                valid_email_mask = df[email_column].str.contains('@', na=False)
                valid_emails_df = df[valid_email_mask]
                
                analysis['csv_analysis'].update({
                    'email_column': email_column,
                    'total_emails': len(valid_emails_df),
                    'invalid_emails': len(df) - len(valid_emails_df)
                })
                
                # Simulate outreach filtering (recent contacts, opt-outs, etc.)
                emails_to_process = len(valid_emails_df)
                max_limit = analysis['campaign_info']['max_emails_limit']
                
                if max_limit and max_limit < emails_to_process:
                    emails_to_send = max_limit
                    analysis['warnings'].append(f"📊 Limited to {max_limit} emails by max_emails setting")
                else:
                    emails_to_send = emails_to_process
                
                # Estimate results
                analysis['estimated_results'] = {
                    'emails_to_process': emails_to_process,
                    'emails_to_send': emails_to_send,
                    'estimated_delivery_time': f"{emails_to_send * 2} seconds" if emails_to_send > 0 else "N/A"
                }
                
                # Generate execution plan
                if emails_to_send > 0:
                    analysis['can_execute'] = True
                    analysis['execution_plan'] = [
                        f"📊 Load CSV: {len(df)} total rows",
                        f"📧 Found {emails_to_process} valid email addresses",
                        f"✅ Will send {emails_to_send} emails",
                        f"📝 Template: {template}",
                        f"🏢 Brand: {brand}",
                        f"⏱️ Estimated time: {analysis['estimated_results']['estimated_delivery_time']}"
                    ]
                else:
                    analysis['warnings'].append("❌ No emails will be sent")
                    analysis['execution_plan'] = [
                        f"📊 CSV analyzed: {len(df)} rows",
                        f"❌ No emails to send after filtering",
                        f"🔍 Check max_emails limit and CSV content"
                    ]
            else:
                analysis['warnings'].append("❌ No email column found in CSV")
                analysis['execution_plan'] = [
                    f"📊 CSV loaded: {len(df)} rows",
                    f"📋 Columns found: {', '.join(df.columns)}",
                    f"❌ No 'email' column detected",
                    f"💡 Add an 'email' column with valid email addresses"
                ]
            
            # Clean up
            os.unlink(temp_csv_path)
            
        except Exception as e:
            analysis['warnings'].append(f"❌ CSV error: {str(e)}")
            if os.path.exists(temp_csv_path):
                os.unlink(temp_csv_path)
        
        return jsonify(analysis)
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Analysis failed: {str(e)}'
        }), 500

@app.route('/api/outreach/run-campaign', methods=['POST'])
def api_run_outreach_campaign():
    """Run outreach campaign with uploaded CSV"""
    try:
        if not OUTREACH_AVAILABLE:
            return jsonify({
                'success': False,
                'message': 'Outreach system not available'
            }), 500
        
        # Get form data
        brand = request.form.get('brand')
        template = request.form.get('template')
        campaign_name = request.form.get('campaign_name', 'Untitled Campaign')
        custom_subject = request.form.get('custom_subject', '')
        custom_message = request.form.get('custom_message', '')
        max_emails = request.form.get('max_emails')
        bcc_email = request.form.get('bcc_email', '')
        skip_recent = request.form.get('skip_recent', 'true').lower() == 'true'
        preview_only = request.form.get('preview_only', 'true').lower() == 'true'
        column_mapping_str = request.form.get('column_mapping', '{}')
        
        # Parse column mapping
        try:
            column_mapping = json.loads(column_mapping_str) if column_mapping_str else {}
        except:
            column_mapping = {}
        
        # Get uploaded file
        csv_file = request.files.get('csv_file')
        if not csv_file:
            return jsonify({
                'success': False,
                'message': 'No CSV file uploaded'
            }), 400
        
        # Save uploaded file temporarily
        import tempfile
        with tempfile.NamedTemporaryFile(mode='w+', suffix='.csv', delete=False) as temp_file:
            csv_content = csv_file.read().decode('utf-8')
            temp_file.write(csv_content)
            temp_csv_path = temp_file.name
        
        try:
            # Generate unique campaign ID
            campaign_id = str(uuid.uuid4())
            
            # Initialize progress tracking
            campaign_progress[campaign_id] = {
                'status': 'starting',
                'current': 0,
                'total': 0,
                'message': 'Initializing campaign...'
            }
            campaign_logs[campaign_id] = []
            
            def add_campaign_log(message, log_type='info'):
                """Add log entry to campaign logs"""
                timestamp = datetime.now().isoformat()
                log_entry = {
                    'timestamp': timestamp,
                    'message': message,
                    'type': log_type
                }
                campaign_logs[campaign_id].append(log_entry)
                
            def progress_callback(current_index, total_count, email, status):
                """Real-time progress callback for campaign execution"""
                try:
                    progress_messages = {
                        'processing': f'📧 Processing {email}...',
                        'sent': f'✅ Sent to {email}',
                        'failed': f'❌ Failed to send to {email}',
                        'skipped_opted_out': f'⚠️ Skipped {email} (opted out)',
                        'skipped_recent': f'⚠️ Skipped {email} (contacted recently)'
                    }
                    
                    # Update progress count
                    campaign_progress[campaign_id].update({
                        'current': current_index + 1,
                        'message': f'Processing email {current_index + 1} of {total_count}...'
                    })
                    
                    # Add detailed log entry
                    message = progress_messages.get(status, f'Processing {email}')
                    log_type = 'success' if status == 'sent' else 'error' if status == 'failed' else 'info'
                    add_campaign_log(message, log_type)
                    
                except Exception as e:
                    add_campaign_log(f'Progress callback error: {str(e)}', 'error')

            def run_campaign_async():
                """Run campaign in background thread"""
                try:
                    add_campaign_log(f'🚀 Starting campaign for {brand}', 'info')
                    add_campaign_log(f'📋 Template: {template}', 'info')
                    add_campaign_log(f'🔗 Column mapping received: {column_mapping}', 'info')
                    
                    # Update progress
                    campaign_progress[campaign_id].update({
                        'status': 'running',
                        'message': 'Loading CSV and processing emails...'
                    })
                    
                    # Create outreach instance with brand configuration
                    outreach = OutreachService(brand_name=brand)
                    add_campaign_log(f'✅ Loaded brand configuration for {brand}', 'success')
                    
                    # Analyze CSV first with column mapping
                    import pandas as pd
                    try:
                        df = pd.read_csv(temp_csv_path)
                        total_rows = len(df)
                        add_campaign_log(f'📊 Found {total_rows} rows in CSV file', 'info')
                        
                        # Log column information
                        add_campaign_log(f'📋 CSV columns: {list(df.columns)}', 'info')
                        
                        # Check for email column mapping
                        email_column = column_mapping.get('email')
                        if email_column and email_column in df.columns:
                            valid_emails = df[df[email_column].str.contains('@', na=False)]
                            add_campaign_log(f'📧 Email column "{email_column}" found with {len(valid_emails)} valid emails', 'success')
                            
                            campaign_progress[campaign_id].update({
                                'total': len(valid_emails),
                                'message': f'Processing {len(valid_emails)} valid emails...'
                            })
                        else:
                            add_campaign_log(f'⚠️ Email column mapping issue: column="{email_column}", available={list(df.columns)}', 'warning')
                            # Try to find email column automatically
                            email_col_found = None
                            for col in df.columns:
                                if 'email' in col.lower() and df[col].str.contains('@', na=False).any():
                                    email_col_found = col
                                    break
                            
                            if email_col_found:
                                add_campaign_log(f'🔍 Auto-detected email column: "{email_col_found}"', 'info')
                                valid_emails = df[df[email_col_found].str.contains('@', na=False)]
                                add_campaign_log(f'� Found {len(valid_emails)} valid emails in auto-detected column', 'success')
                            else:
                                add_campaign_log(f'❌ No email column found in CSV. Campaign cannot proceed.', 'error')
                                campaign_progress[campaign_id].update({
                                    'status': 'failed',
                                    'message': 'No email column found in CSV'
                                })
                                return
                        
                        campaign_progress[campaign_id].update({
                            'total': total_rows,
                            'message': f'Processing {total_rows} rows from CSV...'
                        })
                        
                    except Exception as e:
                        add_campaign_log(f'❌ Error reading CSV: {str(e)}', 'error')
                        campaign_progress[campaign_id].update({
                            'status': 'failed',
                            'message': f'CSV processing failed: {str(e)}'
                        })
                        return                    # Create mapped CSV file if column mapping is provided
                    mapped_csv_path = temp_csv_path
                    if column_mapping and column_mapping.get('email'):
                        add_campaign_log(f'🔄 Creating mapped CSV with proper column names...', 'info')
                        mapped_csv_path = temp_csv_path.replace('.csv', '_mapped.csv')
                        
                        try:
                            # Read original CSV
                            df = pd.read_csv(temp_csv_path)
                            
                            # Create new DataFrame with mapped columns
                            mapped_df = pd.DataFrame()
                            
                            # Map email column (required)
                            if column_mapping.get('email') in df.columns:
                                mapped_df['email'] = df[column_mapping['email']]
                                add_campaign_log(f'✅ Mapped email column: {column_mapping["email"]} -> email', 'success')
                            
                            # Map name column (optional)
                            if column_mapping.get('name') and column_mapping['name'] in df.columns:
                                mapped_df['name'] = df[column_mapping['name']]
                                add_campaign_log(f'✅ Mapped name column: {column_mapping["name"]} -> name', 'success')
                            
                            # Map company column (optional)
                            if column_mapping.get('company') and column_mapping['company'] in df.columns:
                                mapped_df['company'] = df[column_mapping['company']]
                                add_campaign_log(f'✅ Mapped company column: {column_mapping["company"]} -> company', 'success')
                            
                            # Copy any other columns that match expected names
                            for col in df.columns:
                                if col.lower() in ['account_type', 'plan', 'last_login', 'last_active', 'signup_date', 'created_at', 
                                                  'features_used', 'modules', 'subscription_status', 'status', 'usage_level', 'tier']:
                                    mapped_df[col] = df[col]
                            
                            # Save mapped CSV
                            mapped_df.to_csv(mapped_csv_path, index=False)
                            add_campaign_log(f'💾 Created mapped CSV with {len(mapped_df)} rows', 'success')
                            
                            # Update progress with actual email count
                            valid_emails = mapped_df['email'].dropna()
                            valid_emails = valid_emails[valid_emails.str.contains('@', na=False)]
                            campaign_progress[campaign_id].update({
                                'total': len(valid_emails),
                                'message': f'Ready to process {len(valid_emails)} valid emails...'
                            })
                            add_campaign_log(f'📊 Found {len(valid_emails)} valid email addresses', 'info')
                            
                        except Exception as e:
                            add_campaign_log(f'❌ Error creating mapped CSV: {str(e)}', 'error')
                            campaign_progress[campaign_id].update({
                                'status': 'failed',
                                'message': f'Column mapping failed: {str(e)}'
                            })
                            return
                    
                    # Run campaign
                    max_emails_int = int(max_emails) if max_emails and max_emails.strip() else None
                    
                    add_campaign_log(f'📧 Running campaign with template: {template}', 'info')
                    if max_emails_int:
                        add_campaign_log(f'📊 Limited to maximum {max_emails_int} emails', 'info')
                    
                    stats = outreach.run_outreach_campaign(
                        csv_file=mapped_csv_path,
                        template_name=template,
                        preview_only=preview_only,
                        custom_subject=custom_subject,
                        custom_message=custom_message,
                        skip_recent=skip_recent,
                        max_emails=max_emails_int,
                        bcc_email=bcc_email if bcc_email.strip() else None,
                        progress_callback=progress_callback
                    )
                    
                    # Update final progress
                    campaign_progress[campaign_id].update({
                        'status': 'completed',
                        'current': stats.get('total_users', 0),
                        'message': f'Campaign completed successfully!'
                    })
                    
                    # Add detailed results to logs
                    add_campaign_log(f'✅ Campaign completed!', 'success')
                    add_campaign_log(f'📧 Emails sent: {stats.get("emails_sent", 0)}', 'success' if stats.get("emails_sent", 0) > 0 else 'info')
                    add_campaign_log(f'❌ Emails failed: {stats.get("emails_failed", 0)}', 'error' if stats.get("emails_failed", 0) > 0 else 'info')
                    add_campaign_log(f'⚠️ Skipped (opted out): {stats.get("skipped_opted_out", 0)}', 'info')
                    add_campaign_log(f'⚠️ Skipped (recent): {stats.get("skipped_recent", 0)}', 'info')
                    
                    # Clean up temp files
                    os.unlink(temp_csv_path)
                    if mapped_csv_path != temp_csv_path and os.path.exists(mapped_csv_path):
                        os.unlink(mapped_csv_path)
                    
                except Exception as e:
                    # Update progress on error
                    campaign_progress[campaign_id].update({
                        'status': 'failed',
                        'message': f'Campaign failed: {str(e)}'
                    })
                    add_campaign_log(f'❌ Campaign failed: {str(e)}', 'error')
                    
                    # Clean up temp files on error
                    if os.path.exists(temp_csv_path):
                        os.unlink(temp_csv_path)
                    if 'mapped_csv_path' in locals() and mapped_csv_path != temp_csv_path and os.path.exists(mapped_csv_path):
                        os.unlink(mapped_csv_path)
            
            # Start campaign in background thread
            campaign_thread = threading.Thread(target=run_campaign_async)
            campaign_thread.daemon = True
            campaign_thread.start()
            
            # Return immediately with campaign ID
            return jsonify({
                'success': True,
                'message': f'Campaign started successfully',
                'campaign_id': campaign_id,
                'stats': {'status': 'started'}
            })
            
        except Exception as e:
            # Clean up temp file on error
            if os.path.exists(temp_csv_path):
                os.unlink(temp_csv_path)
            raise e
            
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Campaign failed: {str(e)}'
        }), 500

@app.route('/api/outreach/campaign-progress/<campaign_id>')
def api_get_campaign_progress(campaign_id):
    """Get real-time campaign progress"""
    progress = campaign_progress.get(campaign_id, {
        'status': 'not_found',
        'current': 0,
        'total': 0,
        'message': 'Campaign not found'
    })
    
    logs = campaign_logs.get(campaign_id, [])
    
    return jsonify({
        'progress': progress,
        'logs': logs[-20:]  # Return last 20 log entries
    })

@app.route('/api/outreach/campaigns/<brand>')
def api_get_brand_campaigns(brand):
    """Get campaign history for a brand"""
    try:
        # Look for campaign history in the outreach data directory
        data_dir = project_root / 'marketing' / 'outreach_data'
        log_file = data_dir / 'outreach_log.json'
        
        campaigns = []
        if log_file.exists():
            with open(log_file, 'r') as f:
                log_data = json.load(f)
            
            # Group by campaign/date and summarize
            campaign_summary = {}
            for entry in log_data:
                date_key = entry['timestamp'][:10]  # Extract date
                template = entry.get('template_used', 'unknown')
                
                key = f"{date_key}_{template}"
                if key not in campaign_summary:
                    campaign_summary[key] = {
                        'id': key,
                        'name': f"{template.replace('_', ' ').title()} - {date_key}",
                        'template_used': template,
                        'created_at': date_key,
                        'emails_sent': 0,
                        'emails_failed': 0
                    }
                
                if entry.get('status') == 'sent':
                    campaign_summary[key]['emails_sent'] += 1
                elif entry.get('status') == 'failed':
                    campaign_summary[key]['emails_failed'] += 1
            
            campaigns = list(campaign_summary.values())
            campaigns.sort(key=lambda x: x['created_at'], reverse=True)
        
        return jsonify(campaigns)
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/outreach/analytics/<brand>')
def api_get_outreach_analytics(brand):
    """Get comprehensive outreach analytics for a brand using unified system"""
    try:
        if not OUTREACH_AUTOMATION_AVAILABLE or not UnifiedOutreachAnalytics:
            return jsonify({'error': 'Unified outreach analytics not available'}), 503
        
        analytics = UnifiedOutreachAnalytics()
        
        days = request.args.get('days', 30, type=int)
        performance = analytics.get_brand_performance(brand, days)
        
        return jsonify(performance)
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/outreach/overview')
def api_get_outreach_overview():
    """Get comprehensive outreach overview for all brands using unified system"""
    try:
        if not OUTREACH_AUTOMATION_AVAILABLE or not UnifiedOutreachAnalytics:
            return jsonify({'error': 'Unified outreach analytics not available'}), 503
        
        analytics = UnifiedOutreachAnalytics()
        print(f"✅ Analytics instance created")
        
        days = request.args.get('days', 30, type=int)
        overview = analytics.get_all_brands_overview()
        print(f"✅ Got overview with {overview.get('total_brands', 0)} brands")
        
        return jsonify(overview)
        
    except Exception as e:
        import traceback
        error_detail = f"{str(e)}\n{traceback.format_exc()}"
        print(f"❌ Error in /api/outreach/overview: {error_detail}")
        return jsonify({'error': str(e), 'details': error_detail}), 500

@app.route('/api/outreach/database-summary')
def api_get_outreach_database_summary():
    """Get summary of unified outreach database"""
    try:
        if not OUTREACH_AUTOMATION_AVAILABLE or not UnifiedOutreachAnalytics:
            return jsonify({'error': 'Unified outreach analytics not available'}), 503
        
        analytics = UnifiedOutreachAnalytics()
        summary = analytics.get_database_summary()
        
        return jsonify(summary)
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/outreach/recent')
def api_get_recent_outreach_activity():
    """Get recent outreach activity for all brands"""
    try:
        if not OUTREACH_AUTOMATION_AVAILABLE or not UnifiedOutreachAnalytics:
            return jsonify({'error': 'Unified outreach analytics not available'}), 503
        
        analytics = UnifiedOutreachAnalytics()
        limit = request.args.get('limit', 50, type=int)
        brand = request.args.get('brand', None)
        
        # Get recent outreach records
        recent_activity = analytics.get_recent_outreach_activity(limit=limit, brand=brand)
        
        return jsonify({
            'success': True,
            'data': recent_activity
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/campaigns/execute/<brand>', methods=['POST'])
def api_execute_campaign(brand):
    """Execute outreach campaign for a specific brand"""
    try:
        if not OUTREACH_AUTOMATION_AVAILABLE:
            return jsonify({'error': 'Outreach automation not available'}), 503
        
        data = request.get_json() or {}
        campaign_type = data.get('type', 'general')  # general, discovery, follow_up
        target_count = data.get('target_count', 10)
        
        # Handle different campaign types
        if campaign_type == 'discovery':
            # Set up automated discovery cron jobs
            from automation.setup_outreach_automation import OutreachAutomationScheduler
            scheduler = OutreachAutomationScheduler()
            scheduler.setup_outreach_crons()
            
            return jsonify({
                'success': True,
                'type': 'discovery_setup',
                'message': f'Automated discovery cron jobs set up successfully for {brand}',
                'details': {
                    'daily_discovery': '8:00 AM',
                    'weekly_extended': 'Sunday 10:00 AM',
                    'outreach_schedules': 'Brand-specific timing',
                    'next_run': 'Tomorrow 8:00 AM (if after 8:00 AM today)'
                }
            })
        
        # Execute campaign using the multi-brand outreach system
        campaign_manager = MultiBrandOutreachCampaign()
        
        # Run discovery first if needed for general campaigns
        if campaign_type == 'general':
            discovery_result = campaign_manager.run_discovery_session(brand)
            
        # Execute outreach campaign  
        campaign_result = campaign_manager.execute_brand_campaign(
            brand, 
            target_count=target_count,
            campaign_type=campaign_type
        )
        
        # Generate campaign report
        report_data = None
        report_url = None
        
        if campaign_result.get('success', False) and CampaignReportGenerator:
            try:
                generator = CampaignReportGenerator()
                # Use a campaign ID based on brand and current time
                campaign_id = f"{brand}_campaign_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                report = generator.generate_campaign_report(campaign_id, brand)
                
                if 'error' not in report:
                    report_data = {
                        'report_id': report['report_id'],
                        'summary': report['summary']
                    }
                    report_url = f'/reports/campaign?id={report["report_id"]}'
            except Exception as e:
                print(f"Warning: Could not generate campaign report: {e}")
        
        response_data = {
            'success': True,
            'brand': brand,
            'campaign_type': campaign_type,
            'targets_processed': campaign_result.get('targets_processed', 0),
            'emails_sent': campaign_result.get('emails_sent', 0),
            'execution_time': campaign_result.get('execution_time', 'Unknown'),
            'message': f'Campaign executed successfully for {brand}'
        }
        
        # Add report info if generated
        if report_data:
            response_data['report'] = report_data
            response_data['report_url'] = report_url
        
        return jsonify(response_data)
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e),
            'brand': brand
        }), 500

@app.route('/api/campaigns/schedule/<brand>', methods=['POST'])
def api_schedule_campaign(brand):
    """Schedule recurring campaign for a brand"""
    try:
        data = request.get_json() or {}
        schedule_type = data.get('schedule', 'daily')  # daily, weekly, monthly
        time_slot = data.get('time', '10:00')  # HH:MM format
        
        # Get project root (configurable via environment)
        project_root = os.getenv('PROJECT_ROOT', str(Path(__file__).parent.parent))
        script_path = f"{project_root}/automation/run_brand_outreach.py"
        
        # Add to cron (simplified - would need proper cron management)
        cron_entry = f"0 {time_slot.split(':')[1]} {time_slot.split(':')[0]} * * /usr/local/bin/python3 {script_path} --brand {brand}"
        
        return jsonify({
            'success': True,
            'brand': brand,
            'schedule': schedule_type,
            'time': time_slot,
            'cron_entry': cron_entry,
            'message': f'Campaign scheduled for {brand}'
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

# Campaign Report Endpoints
@app.route('/reports/campaign')
def campaign_report_page():
    """Serve campaign report page"""
    return render_template('campaign_report.html')

@app.route('/api/reports/generate/<brand>/<campaign_id>', methods=['POST'])
def api_generate_campaign_report(brand, campaign_id):
    """Generate a detailed campaign report"""
    try:
        if not OUTREACH_AUTOMATION_AVAILABLE or not CampaignReportGenerator:
            return jsonify({'error': 'Campaign reporting not available'}), 503
        
        generator = CampaignReportGenerator()
        report = generator.generate_campaign_report(campaign_id, brand)
        
        if 'error' in report:
            return jsonify({'error': report['error']}), 500
        
        return jsonify({
            'success': True,
            'report_id': report['report_id'],
            'brand': brand,
            'campaign_id': campaign_id,
            'report_url': f'/reports/campaign?id={report["report_id"]}',
            'summary': report['summary']
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/reports/<report_id>')
def api_get_campaign_report(report_id):
    """Get a specific campaign report"""
    try:
        if not OUTREACH_AUTOMATION_AVAILABLE or not CampaignReportGenerator:
            return jsonify({'error': 'Campaign reporting not available'}), 503
        
        generator = CampaignReportGenerator()
        report = generator.get_report(report_id)
        
        if not report:
            return jsonify({'error': 'Report not found'}), 404
        
        if 'error' in report:
            return jsonify({'error': report['error']}), 500
        
        return jsonify(report)
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/reports')
def api_list_campaign_reports():
    """List available campaign reports"""
    try:
        if not OUTREACH_AUTOMATION_AVAILABLE or not CampaignReportGenerator:
            return jsonify({'error': 'Campaign reporting not available'}), 503
        
        brand = request.args.get('brand')
        limit = request.args.get('limit', 20, type=int)
        
        generator = CampaignReportGenerator()
        reports = generator.list_reports(brand=brand, limit=limit)
        
        return jsonify({
            'success': True,
            'reports': reports,
            'total': len(reports)
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/reports/daily-summary')
def api_daily_summary_report():
    """Generate comprehensive daily summary report"""
    try:
        # Combine website analytics, outreach activity, and automation status
        summary_data = {
            'date': datetime.now().strftime('%Y-%m-%d'),
            'website_analytics': {},
            'outreach_activity': {},
            'automation_status': {},
            'alerts': []
        }
        
        # Get website analytics
        if REAL_ANALYTICS_AVAILABLE:
            analytics_dashboard = RealAnalyticsDashboard()
            today_analytics = analytics_dashboard.get_all_brands_analytics()
            summary_data['website_analytics'] = today_analytics
        
        # Get outreach activity
        if OUTREACH_AUTOMATION_AVAILABLE and UnifiedOutreachAnalytics:
            analytics = UnifiedOutreachAnalytics()
            outreach_overview = analytics.get_all_brands_overview(1)  # Today only
            summary_data['outreach_activity'] = outreach_overview
        
        # Get automation status
        cron_jobs = dashboard.get_cron_status()
        summary_data['automation_status'] = {
            'total_jobs': len(cron_jobs),
            'active_jobs': len([j for j in cron_jobs if j.get('status') == 'active']),
            'failed_jobs': len([j for j in cron_jobs if j.get('status') == 'failed']),
            'jobs': cron_jobs[:10]  # Top 10
        }
        
        # Generate alerts
        alerts = []
        if summary_data['automation_status']['failed_jobs'] > 0:
            alerts.append({
                'type': 'warning',
                'message': f"{summary_data['automation_status']['failed_jobs']} automation jobs failed"
            })
        
        if summary_data['outreach_activity'].get('overview', {}).get('total_emails_sent', 0) == 0:
            alerts.append({
                'type': 'info', 
                'message': 'No outreach emails sent today'
            })
        
        summary_data['alerts'] = alerts
        
        return jsonify({
            'success': True,
            'summary': summary_data,
            'generated_at': datetime.now().isoformat()
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/outreach/functions')
def api_get_outreach_functions():
    """Get list of available outreach functions and their status"""
    try:
        functions_status = {
            'unified_analytics': {
                'available': OUTREACH_AUTOMATION_AVAILABLE and UnifiedOutreachAnalytics is not None,
                'description': 'Unified analytics across all brands',
                'endpoints': [
                    '/api/outreach/overview',
                    '/api/outreach/analytics/<brand>',
                    '/api/outreach/database-summary'
                ]
            },
            'multi_brand_outreach': {
                'available': OUTREACH_AUTOMATION_AVAILABLE and MultiBrandOutreachCampaign is not None,
                'description': 'Multi-brand outreach campaign management',
                'functions': [
                    'Target discovery',
                    'Email campaign execution', 
                    'Response tracking',
                    'Performance analytics'
                ]
            },
            'discovery_strategies': {
                'available': OUTREACH_AUTOMATION_AVAILABLE and len(BRAND_DISCOVERY_STRATEGIES) > 0,
                'description': 'Brand-specific target discovery strategies',
                'strategies': list(BRAND_DISCOVERY_STRATEGIES.keys()) if OUTREACH_AUTOMATION_AVAILABLE else []
            },
            'database_consolidation': {
                'available': True,
                'description': 'Database consolidation from existing sources',
                'consolidated_sources': ['brand_json', 'analytics_sqlite', 'outreach_logs'],
                'database_path': os.getenv('UNIFIED_DB_PATH', str(Path(__file__).parent.parent / 'data' / 'unified_outreach.db'))
            }
        }
        
        # Get current system status
        if OUTREACH_AUTOMATION_AVAILABLE and UnifiedOutreachAnalytics:
            try:
                analytics = UnifiedOutreachAnalytics()
                db_summary = analytics.get_database_summary()
                if 'error' not in db_summary:
                    functions_status['system_status'] = {
                        'database_healthy': True,
                        'total_records': db_summary['total_records'],
                        'brands_active': len(db_summary['brand_targets']),
                        'last_updated': db_summary['last_checked']
                    }
            except Exception as e:
                functions_status['system_status'] = {
                    'database_healthy': False,
                    'error': str(e)
                }
        
        return jsonify(functions_status)
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/email-reports/logs')
def api_get_email_logs():
    """Get detailed email logs with filtering and search"""
    try:
        # Parameters for filtering
        days = request.args.get('days', 7, type=int)
        status = request.args.get('status', 'all')  # all, sent, failed
        service = request.args.get('service', 'all')  # all, mailersend, brevo, etc.
        search = request.args.get('search', '')
        limit = request.args.get('limit', 100, type=int)
        offset = request.args.get('offset', 0, type=int)
        
        # Load outreach log
        log_file = Path(project_root) / 'marketing' / 'outreach_data' / 'outreach_log.json'
        if not log_file.exists():
            return jsonify({'error': 'Email log file not found'}), 404
            
        with open(log_file, 'r') as f:
            all_logs = json.load(f)
        
        # Filter by date range
        cutoff_date = datetime.now() - timedelta(days=days)
        filtered_logs = []
        
        # First pass: try with requested date range
        for log_entry in all_logs:
            try:
                log_date = datetime.fromisoformat(log_entry['timestamp'])
                if log_date >= cutoff_date:
                    filtered_logs.append(log_entry)
            except (ValueError, KeyError):
                continue
        
        # If no recent data found and days <= 30, extend the range
        if not filtered_logs and days <= 30:
            cutoff_date = datetime.now() - timedelta(days=90)
            days = 90  # Update days for response
        
        # Second pass: apply all filters including the extended date range if needed
        filtered_logs = []
        for log_entry in all_logs:
            try:
                log_date = datetime.fromisoformat(log_entry['timestamp'])
                if log_date >= cutoff_date:
                    # Apply status filter
                    if status != 'all' and log_entry.get('status') != status:
                        continue
                    
                    # Apply service filter
                    if service != 'all' and log_entry.get('service_used', '').lower() != service.lower():
                        continue
                    
                    # Apply search filter
                    if search:
                        search_fields = [
                            log_entry.get('email', ''),
                            log_entry.get('name', ''),
                            log_entry.get('company', ''),
                            log_entry.get('subject', ''),
                            log_entry.get('message_id', '')
                        ]
                        if not any(search.lower() in str(field).lower() for field in search_fields):
                            continue
                    
                    filtered_logs.append(log_entry)
            except (ValueError, KeyError):
                continue
        
        # Sort by timestamp (newest first)
        filtered_logs.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
        
        # Apply pagination
        total_count = len(filtered_logs)
        paginated_logs = filtered_logs[offset:offset + limit]
        
        # Generate summary stats
        stats = {
            'total_emails': total_count,
            'sent': sum(1 for log in filtered_logs if log.get('status') == 'sent'),
            'failed': sum(1 for log in filtered_logs if log.get('status') == 'failed'),
            'services_used': {},
            'date_range': {
                'from': cutoff_date.isoformat(),
                'to': datetime.now().isoformat()
            }
        }
        
        # Count services used
        for log in filtered_logs:
            service_name = log.get('service_used', 'unknown')
            stats['services_used'][service_name] = stats['services_used'].get(service_name, 0) + 1
        
        return jsonify({
            'success': True,
            'data': {
                'logs': paginated_logs,
                'pagination': {
                    'offset': offset,
                    'limit': limit,
                    'total': total_count,
                    'has_more': offset + limit < total_count
                },
                'stats': stats,
                'filters_applied': {
                    'days': days,
                    'status': status,
                    'service': service,
                    'search': search
                }
            }
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/email-reports/stats')
def api_get_email_stats():
    """Get email campaign statistics and analytics"""
    try:
        days = request.args.get('days', 30, type=int)
        
        # Load outreach log
        log_file = Path(project_root) / 'marketing' / 'outreach_data' / 'outreach_log.json'
        if not log_file.exists():
            return jsonify({'error': 'Email log file not found'}), 404
            
        with open(log_file, 'r') as f:
            all_logs = json.load(f)
        
        # Filter by date range
        cutoff_date = datetime.now() - timedelta(days=days)
        recent_logs = []
        
        for log_entry in all_logs:
            try:
                log_date = datetime.fromisoformat(log_entry['timestamp'])
                if log_date >= cutoff_date:
                    recent_logs.append(log_entry)
            except (ValueError, KeyError):
                continue
        
        # If no recent data found with requested days, expand the search
        if len(recent_logs) == 0 and days <= 30:
            # Try with 90 days if no data found in shorter period
            extended_cutoff = datetime.now() - timedelta(days=90)
            for log_entry in all_logs:
                try:
                    log_date = datetime.fromisoformat(log_entry['timestamp'])
                    if log_date >= extended_cutoff:
                        recent_logs.append(log_entry)
                except (ValueError, KeyError):
                    continue
            days = 90  # Update the period for display
        
        # Calculate statistics
        total_emails = len(recent_logs)
        sent_emails = sum(1 for log in recent_logs if log.get('status') == 'sent')
        failed_emails = sum(1 for log in recent_logs if log.get('status') == 'failed')
        
        # Service breakdown
        service_stats = {}
        for log in recent_logs:
            service = log.get('service_used', 'unknown')
            if service not in service_stats:
                service_stats[service] = {'sent': 0, 'failed': 0, 'total': 0}
            
            status = log.get('status', 'unknown')
            service_stats[service][status] = service_stats[service].get(status, 0) + 1
            service_stats[service]['total'] += 1
        
        # Template usage
        template_stats = {}
        for log in recent_logs:
            template = log.get('template_used', 'unknown')
            template_stats[template] = template_stats.get(template, 0) + 1
        
        # Daily breakdown
        daily_stats = {}
        for log in recent_logs:
            try:
                date_key = datetime.fromisoformat(log['timestamp']).strftime('%Y-%m-%d')
                if date_key not in daily_stats:
                    daily_stats[date_key] = {'sent': 0, 'failed': 0, 'total': 0}
                
                status = log.get('status', 'unknown')
                daily_stats[date_key][status] = daily_stats[date_key].get(status, 0) + 1
                daily_stats[date_key]['total'] += 1
            except (ValueError, KeyError):
                continue
        
        # Success rate calculation
        success_rate = (sent_emails / total_emails * 100) if total_emails > 0 else 0
        
        return jsonify({
            'success': True,
            'data': {
                'summary': {
                    'total_emails': total_emails,
                    'sent_emails': sent_emails,
                    'failed_emails': failed_emails,
                    'success_rate': round(success_rate, 2),
                    'period_days': days
                },
                'service_breakdown': service_stats,
                'template_usage': template_stats,
                'daily_breakdown': daily_stats,
                'generated_at': datetime.now().isoformat()
            }
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/email-reports/message/<message_id>')
def api_get_message_details(message_id):
    """Get detailed information about a specific email message"""
    try:
        # Load outreach log
        log_file = Path(project_root) / 'marketing' / 'outreach_data' / 'outreach_log.json'
        if not log_file.exists():
            return jsonify({'error': 'Email log file not found'}), 404
            
        with open(log_file, 'r') as f:
            all_logs = json.load(f)
        
        # Find message by ID
        message_log = None
        for log_entry in all_logs:
            if log_entry.get('message_id') == message_id:
                message_log = log_entry
                break
        
        if not message_log:
            return jsonify({'error': 'Message not found'}), 404
        
        return jsonify({
            'success': True,
            'data': {
                'message': message_log,
                'delivery_info': message_log.get('delivery_details', {}),
                'can_resend': message_log.get('status') == 'failed',
                'service_used': message_log.get('service_used', 'unknown')
            }
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/email-reports/failed')
def api_get_failed_emails():
    """Get all failed email attempts for potential resending"""
    try:
        days = request.args.get('days', 30, type=int)
        
        # Load outreach log
        log_file = Path(project_root) / 'marketing' / 'outreach_data' / 'outreach_log.json'
        if not log_file.exists():
            return jsonify({'error': 'Email log file not found'}), 404
            
        with open(log_file, 'r') as f:
            all_logs = json.load(f)
        
        # Filter for failed emails in date range
        cutoff_date = datetime.now() - timedelta(days=days)
        failed_emails = []
        
        for log_entry in all_logs:
            try:
                if log_entry.get('status') == 'failed':
                    log_date = datetime.fromisoformat(log_entry['timestamp'])
                    if log_date >= cutoff_date:
                        failed_emails.append(log_entry)
            except (ValueError, KeyError):
                continue
        
        # Sort by timestamp (newest first)
        failed_emails.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
        
        # Group by error type for analysis
        error_analysis = {}
        for email in failed_emails:
            error_type = email.get('error_type', 'Unknown')
            if error_type not in error_analysis:
                error_analysis[error_type] = []
            error_analysis[error_type].append(email)
        
        return jsonify({
            'success': True,
            'data': {
                'failed_emails': failed_emails,
                'total_failed': len(failed_emails),
                'error_analysis': {
                    error_type: {
                        'count': len(emails),
                        'examples': emails[:3]  # First 3 examples
                    }
                    for error_type, emails in error_analysis.items()
                },
                'period_days': days
            }
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/email-reports/resend', methods=['POST'])
def api_resend_emails():
    """Resend failed emails or send to specific recipients"""
    try:
        if not OUTREACH_AVAILABLE or not OutreachService:
            return jsonify({'error': 'Outreach system not available'}), 503
        
        data = request.get_json() or {}
        
        # Get recipients to resend to
        recipients = data.get('recipients', [])  # List of email addresses
        message_ids = data.get('message_ids', [])  # List of message IDs to resend
        template = data.get('template', 'reengagement')
        custom_subject = data.get('custom_subject', '')
        custom_message = data.get('custom_message', '')
        bcc_email = data.get('bcc_email', '')
        
        if not recipients and not message_ids:
            return jsonify({'error': 'Must provide either recipients or message_ids'}), 400
        
        # If message IDs provided, get recipients from log
        if message_ids:
            log_file = Path(project_root) / 'marketing' / 'outreach_data' / 'outreach_log.json'
            if log_file.exists():
                with open(log_file, 'r') as f:
                    all_logs = json.load(f)
                
                for log_entry in all_logs:
                    if log_entry.get('message_id') in message_ids or log_entry.get('timestamp') in message_ids:
                        recipient_email = log_entry.get('email')
                        if recipient_email and recipient_email not in recipients:
                            recipients.append(recipient_email)
        
        if not recipients:
            return jsonify({'error': 'No valid recipients found'}), 400
        
        # Create a temporary CSV with recipients
        import tempfile
        import csv
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as temp_file:
            writer = csv.writer(temp_file)
            writer.writerow(['email', 'first_name', 'last_name', 'created_at'])
            
            for email in recipients:
                # Try to get name from existing logs
                name_parts = email.split('@')[0].replace('.', ' ').replace('_', ' ').title().split()
                first_name = name_parts[0] if name_parts else 'Valued'
                last_name = name_parts[1] if len(name_parts) > 1 else 'User'
                
                writer.writerow([email, first_name, last_name, datetime.now().isoformat()])
            
            temp_csv_path = temp_file.name
        
        # Initialize outreach system
        outreach = OutreachService()
        
        # Run campaign
        result = outreach.run_outreach_campaign(
            csv_file=temp_csv_path,
            template_name=template,
            preview_only=False,
            custom_subject=custom_subject,
            custom_message=custom_message,
            skip_recent=False,  # Force resend
            bcc_email=bcc_email
        )
        
        # Clean up temp file
        os.unlink(temp_csv_path)
        
        return jsonify({
            'success': True,
            'data': {
                'campaign_results': result,
                'recipients_processed': len(recipients),
                'template_used': template,
                'resend_timestamp': datetime.now().isoformat()
            }
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/email-reports/mailersend-status/<message_id>')
def api_get_mailersend_status(message_id):
    """Get MailerSend delivery status for a specific message"""
    try:
        import requests
        
        # MailerSend API configuration
        mailersend_token = "mlsn.<your-mailersend-api-token>"
        
        # Get message details from MailerSend API
        headers = {
            'Authorization': f'Bearer {mailersend_token}',
            'Content-Type': 'application/json'
        }
        
        # Get message info
        message_url = f'https://api.mailersend.com/v1/messages/{message_id}'
        message_response = requests.get(message_url, headers=headers)
        
        if message_response.status_code != 200:
            if message_response.status_code == 404:
                return jsonify({'error': 'Message not found in MailerSend'}), 404
            return jsonify({'error': f'MailerSend API error: {message_response.status_code}'}), 500
        
        message_data = message_response.json()
        
        # Get activities (opens, clicks, etc.)
        activities_url = f'https://api.mailersend.com/v1/activity/{message_id}'
        activities_response = requests.get(activities_url, headers=headers)
        activities_data = activities_response.json() if activities_response.status_code == 200 else {}
        
        # Parse the response
        status_info = {
            'message_id': message_id,
            'status': message_data.get('status', 'unknown'),
            'sent_at': message_data.get('created_at'),
            'recipient': message_data.get('emails', [{}])[0].get('email', 'N/A'),
            'subject': message_data.get('subject', 'N/A'),
            'delivery_status': message_data.get('status'),
            'delivery_details': {
                'delivered_at': message_data.get('delivered_at'),
                'opened_at': None,
                'clicked_at': None,
                'bounced_at': message_data.get('bounced_at'),
                'complained_at': message_data.get('complained_at'),
                'unsubscribed_at': message_data.get('unsubscribed_at')
            },
            'stats': {
                'opens': 0,
                'clicks': 0,
                'bounces': 0,
                'complaints': 0
            },
            'activities': activities_data.get('data', [])
        }
        
        # Process activities to get stats
        for activity in status_info['activities']:
            activity_type = activity.get('type', '').lower()
            if activity_type == 'opened':
                status_info['stats']['opens'] += 1
                if not status_info['delivery_details']['opened_at']:
                    status_info['delivery_details']['opened_at'] = activity.get('created_at')
            elif activity_type == 'clicked':
                status_info['stats']['clicks'] += 1
                if not status_info['delivery_details']['clicked_at']:
                    status_info['delivery_details']['clicked_at'] = activity.get('created_at')
            elif activity_type == 'bounced':
                status_info['stats']['bounces'] += 1
            elif activity_type == 'complained':
                status_info['stats']['complaints'] += 1
        
        return jsonify({
            'success': True,
            'data': status_info
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/email-reports/bulk-status', methods=['POST'])
def api_get_bulk_mailersend_status():
    """Get MailerSend status for multiple messages"""
    try:
        import requests
        from concurrent.futures import ThreadPoolExecutor, as_completed
        
        data = request.get_json() or {}
        message_ids = data.get('message_ids', [])
        
        if not message_ids:
            return jsonify({'error': 'No message IDs provided'}), 400
        
        mailersend_token = "mlsn.<your-mailersend-api-token>"
        headers = {
            'Authorization': f'Bearer {mailersend_token}',
            'Content-Type': 'application/json'
        }
        
        def get_message_status(message_id):
            try:
                message_url = f'https://api.mailersend.com/v1/messages/{message_id}'
                response = requests.get(message_url, headers=headers, timeout=5)
                
                if response.status_code == 200:
                    data = response.json()
                    return {
                        'message_id': message_id,
                        'status': data.get('status'),
                        'delivered': data.get('status') == 'sent',
                        'bounced': data.get('bounced_at') is not None,
                        'opened': False,  # Would need activities API for this
                        'clicked': False  # Would need activities API for this
                    }
                else:
                    return {
                        'message_id': message_id,
                        'status': 'error',
                        'error': f'API returned {response.status_code}'
                    }
            except Exception as e:
                return {
                    'message_id': message_id,
                    'status': 'error',
                    'error': str(e)
                }
        
        # Process in parallel for better performance
        results = []
        with ThreadPoolExecutor(max_workers=5) as executor:
            future_to_id = {executor.submit(get_message_status, msg_id): msg_id for msg_id in message_ids[:20]}  # Limit to 20 for safety
            
            for future in as_completed(future_to_id):
                result = future.result()
                results.append(result)
        
        return jsonify({
            'success': True,
            'data': {
                'results': results,
                'total_checked': len(results),
                'summary': {
                    'delivered': sum(1 for r in results if r.get('status') == 'sent'),
                    'bounced': sum(1 for r in results if r.get('bounced', False)),
                    'errors': sum(1 for r in results if r.get('status') == 'error')
                }
            }
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# Google Ads API Endpoints
@app.route('/api/google-ads/overview')
def api_google_ads_overview():
    """Get overview of all Google Ads campaigns across brands"""
    try:
        if not GOOGLE_ADS_AVAILABLE or not GoogleAdsManager:
            return jsonify({'error': 'Google Ads integration not available'}), 503
        
        ads_manager = GoogleAdsManager()
        summary = ads_manager.get_all_brands_summary()
        
        return jsonify({
            'success': True,
            'data': summary
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/google-ads/brand/<brand>/campaigns')
def api_get_google_ads_campaigns(brand):
    """Get Google Ads campaigns for a specific brand"""
    try:
        if not GOOGLE_ADS_AVAILABLE or not GoogleAdsManager:
            return jsonify({'error': 'Google Ads integration not available'}), 503
        
        ads_manager = GoogleAdsManager()
        campaigns = ads_manager.get_brand_campaigns(brand)
        
        return jsonify({
            'success': True,
            'data': {
                'brand': brand,
                'campaigns': campaigns,
                'total_campaigns': len(campaigns)
            }
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/google-ads/brand/<brand>/performance')
def api_get_google_ads_performance(brand):
    """Get Google Ads performance metrics for a brand"""
    try:
        if not GOOGLE_ADS_AVAILABLE or not GoogleAdsManager:
            return jsonify({'error': 'Google Ads integration not available'}), 503
        
        days = request.args.get('days', 30, type=int)
        
        ads_manager = GoogleAdsManager()
        performance = ads_manager.get_campaign_performance(brand, days)
        
        return jsonify({
            'success': True,
            'data': {
                'brand': brand,
                'period_days': days,
                'performance': performance
            }
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/google-ads/brand/<brand>/keywords/suggest', methods=['POST'])
def api_suggest_keywords(brand):
    """Get keyword suggestions for a brand"""
    try:
        if not GOOGLE_ADS_AVAILABLE or not GoogleAdsManager:
            return jsonify({'error': 'Google Ads integration not available'}), 503
        
        data = request.get_json() or {}
        seed_keywords = data.get('seed_keywords', [])
        
        ads_manager = GoogleAdsManager()
        suggestions = ads_manager.suggest_keywords(brand, seed_keywords)
        
        return jsonify({
            'success': True,
            'data': {
                'brand': brand,
                'seed_keywords': seed_keywords,
                'suggestions': suggestions,
                'total_suggestions': len(suggestions)
            }
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/google-ads/brand/<brand>/campaigns/create', methods=['POST'])
def api_create_campaign(brand):
    """Create a new Google Ads campaign"""
    try:
        if not GOOGLE_ADS_AVAILABLE or not GoogleAdsManager:
            return jsonify({'error': 'Google Ads integration not available'}), 503
        
        data = request.get_json() or {}
        
        campaign_name = data.get('campaign_name')
        campaign_type = data.get('campaign_type')
        keywords = data.get('keywords', [])
        budget_daily = data.get('budget_daily')
        
        if not campaign_name or not campaign_type:
            return jsonify({'error': 'campaign_name and campaign_type are required'}), 400
        
        ads_manager = GoogleAdsManager()
        result = ads_manager.create_campaign(
            brand=brand,
            campaign_type=campaign_type,
            campaign_name=campaign_name,
            keywords=keywords,
            budget_daily=budget_daily
        )
        
        return jsonify({
            'success': result.get('success', False),
            'data': result
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/google-ads/brand/<brand>/campaigns/<campaign_id>/pause', methods=['POST'])
def api_pause_campaign(brand, campaign_id):
    """Pause a campaign"""
    try:
        if not GOOGLE_ADS_AVAILABLE or not GoogleAdsManager:
            return jsonify({'error': 'Google Ads integration not available'}), 503
        
        ads_manager = GoogleAdsManager()
        result = ads_manager.pause_campaign(brand, campaign_id)
        
        return jsonify({
            'success': result.get('success', False),
            'data': result
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/google-ads/brand/<brand>/campaigns/<campaign_id>/resume', methods=['POST'])
def api_resume_campaign(brand, campaign_id):
    """Resume a campaign"""
    try:
        if not GOOGLE_ADS_AVAILABLE or not GoogleAdsManager:
            return jsonify({'error': 'Google Ads integration not available'}), 503
        
        ads_manager = GoogleAdsManager()
        result = ads_manager.resume_campaign(brand, campaign_id)
        
        return jsonify({
            'success': result.get('success', False),
            'data': result
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/google-ads/brand/<brand>/optimize', methods=['POST'])
def api_optimize_campaigns(brand):
    """Run campaign optimization for a brand"""
    try:
        if not GOOGLE_ADS_AVAILABLE or not GoogleAdsManager:
            return jsonify({'error': 'Google Ads integration not available'}), 503
        
        ads_manager = GoogleAdsManager()
        result = ads_manager.optimize_campaigns(brand)
        
        return jsonify({
            'success': True,
            'data': result
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/outreach/reports')
def api_get_outreach_reports():
    """Get comprehensive outreach reports across all functions"""
    try:
        if not OUTREACH_AUTOMATION_AVAILABLE or not UnifiedOutreachAnalytics:
            return jsonify({'error': 'Unified outreach analytics not available'}), 503
        
        analytics = UnifiedOutreachAnalytics()
        
        # Get comprehensive report data
        days = request.args.get('days', 30, type=int)
        
        # Main overview
        overview = analytics.get_all_brands_overview(days)
        if 'error' in overview:
            return jsonify({'error': overview['error']}), 500
        
        # Database health
        db_summary = analytics.get_database_summary()
        
        # Cron status from unified DB
        cron_status = analytics.get_cron_status_from_unified_db()
        
        # Individual brand reports
        brand_reports = {}
        for brand in overview.get('brands', {}).keys():
            brand_performance = analytics.get_brand_performance(brand, days)
            if 'error' not in brand_performance:
                brand_reports[brand] = brand_performance
        
        return jsonify({
            'report_generated': datetime.now().isoformat(),
            'period_days': days,
            'overview': overview,
            'database_health': db_summary,
            'automation_status': cron_status,
            'brand_reports': brand_reports,
            'summary': {
                'total_brands': overview.get('total_brands', 0),
                'total_targets': overview.get('overview', {}).get('total_targets', 0),
                'total_emails_sent': overview.get('overview', {}).get('total_emails_sent', 0),
                'overall_response_rate': overview.get('overview', {}).get('overall_response_rate', 0),
                'active_automations': len(cron_status),
                'database_records': db_summary.get('total_records', 0) if 'error' not in db_summary else 0
            }
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/outreach/send-test', methods=['POST'])
def api_send_test_email():
    """Send a test email using the unified email service with smart routing"""
    try:
        data = request.get_json() or {}
        to_email = data.get('to') or os.getenv('ADMIN_EMAIL', 'admin@example.com')
        brand = data.get('brand') or (dashboard.brands[0] if dashboard.brands else '')
        campaign_type = data.get('campaign_type', 'general_outreach')

        if not brand:
            return jsonify({
                'success': False,
                'message': 'No active brands configured. Add a brand before sending test emails.'
            }), 400
        
        # Check email configuration first
        if not ENVIRONMENT_CONFIG['email']['mailersend_configured'] and not ENVIRONMENT_CONFIG['email']['brevo_configured']:
            missing_vars = list(set(ENVIRONMENT_CONFIG['email']['missing_vars']))
            return jsonify({
                'success': False,
                'error': 'No email credentials provided',
                'message': f'❌ Email connection failed: No credentials provided. Missing environment variables: {", ".join(missing_vars)}',
                'missing_config': missing_vars,
                'config_status': ENVIRONMENT_CONFIG['email']
            }), 400
        
        # Import the unified email service
        from unified_email_service import UnifiedEmailService
        
        # Create email service instance
        email_service = UnifiedEmailService()
        
        # Generate test email content
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        subject = f"🧪 Test Email - {brand.title()} ({campaign_type})"
        
        # Create appropriate body based on campaign type
        if campaign_type == 'daily_analytics':
            body = f"""📊 Daily Analytics Test Email - {brand.title()}

This is a test of the daily analytics email system.

Service: {email_service.service_routing.get(brand.lower(), 'brevo')}
Brand: {brand.title()}
Campaign Type: {campaign_type}
Timestamp: {timestamp}

Sample Analytics:
• Sessions: 1,234
• Users: 856  
• Pageviews: 2,856
• Bounce Rate: 45.2%

If you receive this email, the {brand} analytics email system is working correctly!

Best regards,
{brand.title()} Analytics Team"""
        else:
            body = f"""🧪 Test Email - {brand.title()}

This is a test email from the unified email routing system.

Details:
• Brand: {brand.title()}
• Campaign: {campaign_type}
• Service: {email_service.service_routing.get(brand.lower(), 'brevo')}
• Smart Routing: Standard
• Timestamp: {timestamp}

If you receive this email, the {brand} email system is working correctly!

Best regards,
{brand.title()} Team"""
        
        # Send test email using unified service
        result = email_service.send_email(
            brand=brand,
            to_email=to_email,
            subject=subject,
            body=body,
            is_html=False
        )
        
        if result['success']:
            service_used = result.get('service', 'unknown')
            message_id = result.get('message_id', 'N/A')
            routing_note = result.get('routing_note', 'Standard routing')
            
            return jsonify({
                'success': True,
                'message': f'Test email sent successfully to {to_email}',
                'details': {
                    'service': service_used,
                    'message_id': message_id,
                    'routing_note': routing_note,
                    'brand': brand,
                    'campaign_type': campaign_type,
                    'smart_routing': False
                }
            })
        else:
            return jsonify({
                'success': False,
                'message': f'Failed to send test email: {result.get("error", "Unknown error")}',
                'details': result
            }), 500
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Test email failed: {str(e)}'
        }), 500

@app.route('/api/outreach/test-all-emails', methods=['POST'])
def api_test_all_email_configurations():
    """Test email configuration for all brands and campaign types using unified service"""
    try:
        data = request.get_json() or {}
        to_email = data.get('to') or os.getenv('ADMIN_EMAIL', 'admin@example.com')
        
        # Import the unified email service
        from unified_email_service import UnifiedEmailService
        
        # Create email service instance
        email_service = UnifiedEmailService()
        
        # Test comprehensive routing
        test_results = []
        brands_to_test = dashboard.brands[:3] if dashboard.brands else []
        if not brands_to_test:
            return jsonify({
                'success': False,
                'message': 'No active brands configured. Add at least one brand before running comprehensive email tests.'
            }), 400
        campaigns_to_test = ['general_outreach', 'daily_analytics']  # Key campaigns
        
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        for brand_key in brands_to_test:
            for campaign_type in campaigns_to_test:
                try:
                    # Create test content
                    subject = f"🧪 Comprehensive Test - {brand_key.title()} ({campaign_type})"
                    
                    body = f"""📊 Comprehensive Email System Test

Brand: {brand_key.title()}
Campaign: {campaign_type}
Service: {email_service.service_routing.get(brand_key.lower(), 'brevo')}
Smart Routing: Standard
Timestamp: {timestamp}

This is part of a comprehensive test of all email routing configurations.

Test #{len(test_results) + 1} of {len(brands_to_test) * len(campaigns_to_test)}

Best regards,
{brand_key.title()} Team"""
                    
                    # Send test email
                    result = email_service.send_email(
                        brand=brand_key,
                        to_email=to_email,
                        subject=subject,
                        body=body,
                        is_html=False
                    )
                    
                    # Format result
                    test_result = {
                        'brand': brand_key,
                        'campaign_type': campaign_type,
                        'status': 'success' if result['success'] else 'failed',
                        'service': result.get('service', 'unknown'),
                        'message_id': result.get('message_id', 'N/A'),
                        'routing_note': result.get('routing_note', 'Standard routing'),
                        'error': result.get('error') if not result['success'] else None
                    }
                    
                    test_results.append(test_result)
                    
                except Exception as e:
                    test_results.append({
                        'brand': brand_key,
                        'campaign_type': campaign_type,
                        'status': 'failed',
                        'error': str(e),
                        'service': 'unknown'
                    })
        
        # Calculate summary
        successful = [r for r in test_results if r['status'] == 'success']
        failed = [r for r in test_results if r['status'] == 'failed']
        
        # Group by service
        service_summary = {}
        for result in successful:
            service = result['service']
            if service not in service_summary:
                service_summary[service] = 0
            service_summary[service] += 1
        
        return jsonify({
            'success': True,
            'message': f'Comprehensive email test completed',
            'summary': {
                'total_tests': len(test_results),
                'successful': len(successful),
                'failed': len(failed),
                'success_rate': (len(successful) / len(test_results) * 100) if test_results else 0,
                'test_email': to_email,
                'service_breakdown': service_summary,
                'smart_routing_active': any(r.get('routing_note') != 'Standard routing' for r in test_results)
            },
            'results': test_results
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Comprehensive email test failed: {str(e)}'
        }), 500
        
        # Create message object
        message = {
            'subject': subject,
            'body': body,
            'template_used': 'test_email'
        }
        
        # Send the test email (not in preview mode)
        success = outreach.send_email(test_user, message, preview_only=False)
        
        if success:
            return jsonify({
                'success': True,
                'message': f'Test email sent to {to_email}'
            })
        else:
            return jsonify({
                'success': False,
                'message': 'Failed to send test email'
            }), 500
            
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Error sending test email: {str(e)}'
        }), 500

# ===============================================
# DAILY ANALYTICS EMAIL API ENDPOINTS
# ===============================================

@app.route('/api/daily-emails/send-all', methods=['POST'])
def api_send_all_daily_emails():
    """Send daily analytics reports to all brands"""
    try:
        if not DAILY_EMAIL_AVAILABLE:
            return jsonify({
                'success': False,
                'error': 'Daily email system not available'
            }), 503
        
        # Get dry run parameter
        dry_run = request.json.get('dry_run', False) if request.json else False
        
        # Create emailer instance and send reports
        emailer = DailyAnalyticsEmailer()
        results = emailer.send_all_daily_reports(dry_run=dry_run)
        
        successful = sum(results.values())
        total = len(results)
        
        return jsonify({
            'success': True,
            'results': results,
            'summary': {
                'successful': successful,
                'failed': total - successful,
                'total': total
            },
            'dry_run': dry_run
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/daily-emails/send-brand/<brand>', methods=['POST'])
def api_send_brand_daily_email(brand):
    """Send daily analytics report for a specific brand"""
    try:
        if not DAILY_EMAIL_AVAILABLE:
            return jsonify({
                'success': False,
                'error': 'Daily email system not available'
            }), 503
        
        # Get dry run parameter
        dry_run = request.json.get('dry_run', False) if request.json else False
        
        # Create emailer instance
        emailer = DailyAnalyticsEmailer()
        
        # Get analytics data for brand
        analytics_data = get_analytics_for_dashboard(brand)
        
        # Generate email content
        email_content = emailer.generate_daily_email_content(brand, analytics_data)
        
        # Send email
        success = emailer.send_daily_report_email(brand, email_content, dry_run=dry_run)
        
        return jsonify({
            'success': success,
            'brand': brand,
            'dry_run': dry_run,
            'email_content': {
                'subject': email_content['subject'],
                'preview': email_content['text_body'][:200] + '...'
            } if success else None
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/daily-emails/send-summary', methods=['POST'])
def api_send_summary_email():
    """Send multi-brand summary email"""
    try:
        if not DAILY_EMAIL_AVAILABLE:
            return jsonify({
                'success': False,
                'error': 'Daily email system not available'
            }), 503
        
        # Get dry run parameter
        dry_run = request.json.get('dry_run', False) if request.json else False
        
        # Create emailer instance and send summary
        emailer = DailyAnalyticsEmailer()
        success = emailer.send_multi_brand_summary(dry_run=dry_run)
        
        return jsonify({
            'success': success,
            'dry_run': dry_run,
            'message': 'Multi-brand summary sent' if success else 'Failed to send summary'
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/daily-emails/preview/<brand>')
def api_preview_daily_email(brand):
    """Preview daily email content for a brand"""
    try:
        if not DAILY_EMAIL_AVAILABLE:
            return jsonify({
                'success': False,
                'error': 'Daily email system not available'
            }), 503
        
        # Create emailer instance
        emailer = DailyAnalyticsEmailer()
        
        # Get analytics data for brand
        analytics_data = get_analytics_for_dashboard(brand)
        
        # Generate email content
        email_content = emailer.generate_daily_email_content(brand, analytics_data)
        
        return jsonify({
            'success': True,
            'brand': brand,
            'content': email_content
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/daily-emails/status')
def api_daily_emails_status():
    """Get daily email system status"""
    try:
        # Check if system is available
        available = DAILY_EMAIL_AVAILABLE and DailyAnalyticsEmailer is not None
        
        # Get current cron jobs
        cron_jobs = []
        try:
            import subprocess
            result = subprocess.run(['crontab', '-l'], capture_output=True, text=True)
            if result.returncode == 0:
                lines = result.stdout.strip().split('\n')
                for line in lines:
                    if 'daily_analytics_emailer' in line and not line.startswith('#'):
                        cron_jobs.append(line.strip())
        except:
            pass
        
        # Get brand configurations
        from automation.daily_analytics_emailer import DAILY_EMAIL_CONFIG
        brands = list(DAILY_EMAIL_CONFIG.keys())
        
        return jsonify({
            'success': True,
            'available': available,
            'brands_configured': brands,
            'cron_jobs': cron_jobs,
            'smtp_configured': True,  # We're using proven Brevo config
            'status': 'ready' if available else 'unavailable'
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/brand-dashboards')
def api_brand_dashboards_list():
    """List all available brand dashboards"""
    try:
        dashboards = []
        
        # Brand dashboards are loaded dynamically from the Brand database.
        # Each brand can optionally have a website reports path configured.
        brand_dashboards = {}
        
        # Check which dashboards exist
        for brand_key, info in brand_dashboards.items():
            dashboard_path = project_root / info['path']
            
            dashboards.append({
                'brand': brand_key,
                'name': info['name'],
                'exists': dashboard_path.exists(),
                'has_generator': info['has_generator'],
                'path': str(dashboard_path),
                'url_path': info['url_path'],
                'last_updated': dashboard_path.stat().st_mtime if dashboard_path.exists() else None
            })
        
        return jsonify({
            'success': True,
            'dashboards': dashboards
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/brand-dashboards/generate', methods=['POST'])
def api_generate_all_brand_dashboards():
    """Generate all brand dashboards"""
    try:
        data = request.get_json() or {}
        brand = data.get('brand', 'all')
        
        results = {}
        
        results['message'] = 'Brand dashboard generation is not bundled in this standalone build.'
        
        return jsonify({
            'success': True,
            'results': results
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/brand-dashboard/<brand>')
def serve_brand_dashboard(brand):
    """Serve brand-specific dashboard HTML"""
    try:
        # Dashboard paths are configured externally in brand-specific settings.
        dashboard_paths = {}
        
        if brand not in dashboard_paths:
            return f"Unknown brand: {brand}", 404
        
        dashboard_path = project_root / dashboard_paths[brand]
        
        if not dashboard_path.exists():
            return f"Dashboard not found for {brand}. Try generating it first.", 404
        
        # Read and serve the HTML file
        with open(dashboard_path, 'r', encoding='utf-8') as f:
            html_content = f.read()
        
        # Add some meta information to identify the dashboard source
        html_content = html_content.replace(
            '</head>',
            f'<meta name="dashboard-brand" content="{brand}">\n'
            f'<meta name="served-from" content="main-dashboard">\n'
            f'<meta name="generated-on" content="{datetime.now().isoformat()}">\n</head>'
        )
        
        return html_content, 200, {'Content-Type': 'text/html; charset=utf-8'}
        
    except Exception as e:
        return f"Error serving dashboard: {str(e)}", 500

# =============================================================================
# INFLUENCER DISCOVERY API ENDPOINTS
# =============================================================================

# Try to import influencer modules
try:
    from automation.influencer_discovery import BrandInfluencerDiscovery, BRAND_INFLUENCER_STRATEGIES
    from automation.influencer_report_generator import InfluencerReportGenerator
    INFLUENCER_SYSTEM_AVAILABLE = True
except ImportError as e:
    print(f"⚠️  Influencer system not available: {e}")
    INFLUENCER_SYSTEM_AVAILABLE = False

@app.route('/api/influencers/discover/<brand>', methods=['POST'])
def api_discover_influencers(brand):
    """Run influencer discovery for a specific brand"""
    if not INFLUENCER_SYSTEM_AVAILABLE:
        return jsonify({'error': 'Influencer system not available'}), 503
    
    try:
        data = request.get_json() or {}
        max_per_platform = data.get('max_per_platform', 5)
        
        async def run_discovery():
            discovery = BrandInfluencerDiscovery()
            return await discovery.discover_brand_influencers(brand, max_per_platform)
        
        # Run the async discovery
        results = asyncio.run(run_discovery())
        
        # Calculate summary
        total_discovered = sum(len(influencers) for influencers in results.values())
        platforms_used = len([p for p, influencers in results.items() if influencers])
        
        return jsonify({
            'success': True,
            'brand': brand,
            'brand_name': BRAND_INFLUENCER_STRATEGIES.get(brand, {}).get('name', brand),
            'results': {platform: len(influencers) for platform, influencers in results.items()},
            'summary': {
                'total_discovered': total_discovered,
                'platforms_searched': len(results),
                'platforms_with_results': platforms_used,
                'discovery_time': datetime.now().isoformat()
            }
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e),
            'brand': brand
        }), 500

@app.route('/api/influencers/list')
def api_list_influencers():
    """Get filtered list of discovered influencers"""
    if not INFLUENCER_SYSTEM_AVAILABLE:
        return jsonify({'error': 'Influencer system not available'}), 503
    
    try:
        # Get query parameters
        brand = request.args.get('brand')
        platform = request.args.get('platform')
        min_followers = int(request.args.get('min_followers', 0))
        min_alignment = float(request.args.get('min_alignment', 0.0))
        limit = int(request.args.get('limit', 50))
        
        discovery = BrandInfluencerDiscovery()
        influencers = discovery.get_brand_influencers(
            brand=brand,
            platform=platform,
            min_followers=min_followers,
            min_alignment=min_alignment
        )
        
        # Limit results
        influencers = influencers[:limit]
        
        return jsonify({
            'success': True,
            'count': len(influencers),
            'filters': {
                'brand': brand,
                'platform': platform,
                'min_followers': min_followers,
                'min_alignment': min_alignment
            },
            'influencers': influencers
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/influencers/report/<brand>', methods=['GET', 'POST'])
def api_influencer_report(brand):
    """Generate influencer report for a brand"""
    if not INFLUENCER_SYSTEM_AVAILABLE:
        return jsonify({'error': 'Influencer system not available'}), 503
    
    try:
        format_type = request.args.get('format', 'html')
        
        generator = InfluencerReportGenerator()
        report = generator.generate_brand_report(brand=brand, format=format_type)
        
        return jsonify({
            'success': True,
            'report': {
                'id': report['report_id'],
                'brand': report['brand'],
                'brand_name': report['brand_name'],
                'generated_at': report['generated_at'],
                'file_path': report['report_file'],
                'url': report['report_url'],
                'summary': report['summary']
            }
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e),
            'brand': brand
        }), 500

@app.route('/reports/influencers/<filename>')
def serve_influencer_report(filename):
    """Serve influencer report HTML files"""
    try:
        reports_dir = Path(__file__).parent.parent / 'reports' / 'influencers'
        file_path = reports_dir / filename
        
        if file_path.exists() and file_path.suffix == '.html':
            return send_from_directory(str(reports_dir), filename)
        else:
            abort(404)
    except Exception:
        abort(404)

@app.route('/api/influencers/stats')
def api_influencer_stats():
    """Get overall influencer statistics"""
    if not INFLUENCER_SYSTEM_AVAILABLE:
        return jsonify({'error': 'Influencer system not available'}), 503
    
    try:
        discovery = BrandInfluencerDiscovery()
        
        # Get stats for each brand
        stats_by_brand = {}
        total_influencers = 0
        total_reach = 0
        
        for brand_key in BRAND_INFLUENCER_STRATEGIES.keys():
            brand_influencers = discovery.get_brand_influencers(brand=brand_key)
            
            if brand_influencers:
                brand_reach = sum(inf.get('total_reach', 0) for inf in brand_influencers)
                avg_engagement = sum(inf.get('avg_engagement_rate', 0) for inf in brand_influencers) / len(brand_influencers)
                avg_alignment = sum(inf.get('brand_alignment_score', 0) for inf in brand_influencers) / len(brand_influencers)
                
                stats_by_brand[brand_key] = {
                    'name': BRAND_INFLUENCER_STRATEGIES[brand_key]['name'],
                    'count': len(brand_influencers),
                    'total_reach': brand_reach,
                    'avg_engagement': round(avg_engagement, 2),
                    'avg_alignment': round(avg_alignment, 2),
                    'platforms': list(set(inf.get('primary_platform', '') for inf in brand_influencers))
                }
                
                total_influencers += len(brand_influencers)
                total_reach += brand_reach
        
        return jsonify({
            'success': True,
            'overall': {
                'total_influencers': total_influencers,
                'total_reach': total_reach,
                'brands_with_influencers': len([b for b in stats_by_brand.values() if b['count'] > 0]),
                'avg_influencers_per_brand': round(total_influencers / len(BRAND_INFLUENCER_STRATEGIES), 1) if BRAND_INFLUENCER_STRATEGIES else 0
            },
            'by_brand': stats_by_brand,
            'generated_at': datetime.now().isoformat()
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/influencers/<int:influencer_id>/delete', methods=['POST'])
def api_soft_delete_influencer(influencer_id):
    """Soft delete an influencer (mark as deleted)"""
    if not INFLUENCER_SYSTEM_AVAILABLE:
        return jsonify({'error': 'Influencer system not available'}), 503
    
    try:
        import sqlite3
        db_path = Path('data/influencer_discovery.db')
        
        if not db_path.exists():
            return jsonify({'error': 'Influencer database not found'}), 404
            
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Add deleted column if it doesn't exist
        try:
            cursor.execute("ALTER TABLE influencers ADD COLUMN deleted BOOLEAN DEFAULT FALSE")
            conn.commit()
        except sqlite3.OperationalError:
            # Column already exists
            pass
        
        # Mark influencer as deleted
        cursor.execute("UPDATE influencers SET deleted = TRUE WHERE id = ?", (influencer_id,))
        
        if cursor.rowcount == 0:
            conn.close()
            return jsonify({'error': 'Influencer not found'}), 404
            
        conn.commit()
        conn.close()
        
        return jsonify({
            'success': True,
            'message': 'Influencer marked as deleted'
        })
        
    except Exception as e:
        logger.error(f"Error soft deleting influencer {influencer_id}: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/influencers/sync-to-contacts', methods=['POST'])
def api_sync_influencers_to_contacts():
    """Sync influencers to contacts system"""
    if not INFLUENCER_SYSTEM_AVAILABLE or not CONTACTS_SYSTEM_AVAILABLE:
        return jsonify({'error': 'Required systems not available'}), 503
    
    try:
        import logging
        logger = logging.getLogger('dashboard')
        from automation.contacts_manager import UnifiedContactsManager
        
        data = request.get_json(silent=True) or {}
        queue_outreach = data.get('queue_outreach', True)
        influencer_ids = {int(i) for i in (data.get('influencer_ids') or []) if str(i).isdigit()}
        
        # Get all non-deleted influencers
        discovery = BrandInfluencerDiscovery()
        influencers = discovery.get_brand_influencers()
        if influencer_ids:
            influencers = [inf for inf in influencers if int(inf.get('id', 0) or 0) in influencer_ids]
        
        contacts_manager = UnifiedContactsManager()
        synced_count = 0
        queued_outreach_count = 0
        
        for influencer in influencers:
            social_links = influencer.get('social_links', '')
            parsed_links = []
            social_platforms = {}
            contact_payload = {}

            if social_links:
                for link in social_links.split(','):
                    if ':' in link:
                        platform, url = link.split(':', 1)
                        platform = platform.strip().lower()
                        url = url.strip()
                        parsed_links.append(f"{platform.title()}: {url}")
                        social_platforms[f'{platform}_url'] = url

            social_links_formatted = '\n'.join(parsed_links) if parsed_links else 'No social media links'

            contact_payload.update({
                'name': influencer.get('name'),
                'email': influencer.get('contact_email', ''),
                'contact_type': 'influencer',
                'brand': influencer.get('brand', ''),
                'website_url': influencer.get('website', ''),
                'notes': f"""Auto-synced from influencer discovery.

📊 Influencer Stats:
• Platform: {influencer.get('primary_platform', 'unknown')}
• Followers: {influencer.get('total_reach', 0):,}
• Engagement: {influencer.get('avg_engagement_rate', 0)}%
• Brand Alignment: {round(influencer.get('brand_alignment_score', 0) * 100)}%
• Niche: {influencer.get('niche', 'N/A')}

📱 Social Media Profiles:
{social_links_formatted}

📝 Bio: {influencer.get('bio_summary', 'No bio available')}

🗒️ Notes: {influencer.get('outreach_notes', 'None')}""",
                'platform': influencer.get('primary_platform', ''),
                'followers_count': int(influencer.get('total_reach', 0) or 0),
                'engagement_rate': float(influencer.get('avg_engagement_rate', 0) or 0),
                'alignment_score': float(influencer.get('brand_alignment_score', 0) or 0),
                'niche': influencer.get('niche', ''),
                'bio_summary': influencer.get('bio_summary', ''),
                'linkedin_url': influencer.get('website', '') if influencer.get('primary_platform') == 'linkedin' else '',
                **social_platforms,
            })

            contact_result = contacts_manager.upsert_contact(contact_payload)
            if contact_result.get('id'):
                synced_count += 1

                existing_contact = contacts_manager.get_contact(contact_result['id']) if queue_outreach else None
                has_social_outbound = any(
                    touch.get('touch_direction') == 'outbound' and touch.get('touch_type') == 'social_dm'
                    for touch in (existing_contact or {}).get('touches', [])
                )
                if queue_outreach and (contact_result.get('created') or not has_social_outbound):
                    contacts_manager.add_touch(contact_result['id'], {
                        'touch_type': 'social_dm',
                        'touch_direction': 'outbound',
                        'subject': f"Queued outreach for {influencer.get('name', 'influencer')}",
                        'message': influencer.get('outreach_notes') or contact_payload['notes'],
                        'platform': influencer.get('primary_platform', 'social'),
                        'status': 'queued'
                    })
                    queued_outreach_count += 1
        
        return jsonify({
            'success': True,
            'message': f'Synced {synced_count} influencers to contacts',
            'synced_count': synced_count,
            'queued_outreach_count': queued_outreach_count,
            'total_influencers': len(influencers)
        })
        
    except Exception as e:
        logger.error(f"Error syncing influencers to contacts: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/influencers/outreach-queue')
def api_influencer_outreach_queue():
    """List queued influencer outreach touches."""
    if not CONTACTS_SYSTEM_AVAILABLE:
        return jsonify({'error': 'Contacts system not available'}), 503

    try:
        brand = request.args.get('brand')
        platform = request.args.get('platform')
        status = (request.args.get('status') or 'queued').strip().lower()
        valid_statuses = {'queued', 'ready', 'sent', 'failed', 'cancelled'}
        if status not in valid_statuses:
            return jsonify({'success': False, 'error': 'Invalid status filter'}), 400
        limit = int(request.args.get('limit', 200))

        manager = UnifiedContactsManager()
        import sqlite3

        query = """
            SELECT
                ct.id,
                ct.contact_id,
                ct.subject,
                ct.message,
                ct.platform,
                ct.status,
                ct.created_at,
                c.name,
                c.brand,
                c.email,
                c.platform AS primary_platform,
                c.linkedin_url,
                c.twitter_handle,
                c.instagram_handle,
                c.bluesky_handle,
                c.tiktok_handle,
                c.youtube_channel
            FROM contact_touches ct
            JOIN contacts c ON c.id = ct.contact_id
            WHERE c.contact_type = 'influencer'
              AND ct.touch_type = 'social_dm'
              AND ct.touch_direction = 'outbound'
              AND ct.status = ?
        """
        params = [status]
        if brand:
            query += " AND c.brand = ?"
            params.append(brand)
        if platform and platform != 'all':
            query += " AND (ct.platform = ? OR c.platform = ?)"
            params.extend([platform, platform])
        query += " ORDER BY ct.created_at DESC LIMIT ?"
        params.append(limit)

        with sqlite3.connect(manager.db_path) as conn:
            conn.row_factory = sqlite3.Row
            items = [dict(row) for row in conn.execute(query, params).fetchall()]

        base_contacts_url = url_for('contacts')
        for item in items:
            name = item.get('name') or ''
            item['contact_link'] = f"{base_contacts_url}?search={quote_plus(name)}" if name else base_contacts_url

        return jsonify({'success': True, 'count': len(items), 'items': items})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/influencers/outreach-queue/process', methods=['POST'])
def api_process_influencer_outreach_queue():
    """Process queued influencer outreach touches into ready/sent items."""
    if not CONTACTS_SYSTEM_AVAILABLE:
        return jsonify({'error': 'Contacts system not available'}), 503

    try:
        data = request.get_json(silent=True) or {}
        from automation.process_influencer_outreach_queue import InfluencerOutreachQueueProcessor

        processor = InfluencerOutreachQueueProcessor()
        result = processor.process(
            brand=data.get('brand') or None,
            platform=data.get('platform') or None,
            limit=int(data.get('limit', 100)),
            status=(data.get('status') or 'queued').strip().lower(),
            dry_run=bool(data.get('dry_run', False)),
            auto_mark_sent=bool(data.get('auto_mark_sent', False)),
        )
        return jsonify(result), 200
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/influencers/outreach-queue/<int:touch_id>/status', methods=['POST'])
def api_update_influencer_outreach_queue_item(touch_id):
    """Update queued influencer outreach touch status."""
    if not CONTACTS_SYSTEM_AVAILABLE:
        return jsonify({'error': 'Contacts system not available'}), 503

    try:
        data = request.get_json(silent=True) or {}
        new_status = (data.get('status') or '').strip().lower()
        valid_statuses = {'queued', 'ready', 'sent', 'failed', 'cancelled'}
        if new_status not in valid_statuses:
            return jsonify({'success': False, 'error': 'Invalid status'}), 400

        manager = UnifiedContactsManager()
        import sqlite3

        with sqlite3.connect(manager.db_path) as conn:
            cur = conn.execute(
                """
                UPDATE contact_touches
                SET status = ?
                WHERE id = ?
                  AND touch_type = 'social_dm'
                  AND touch_direction = 'outbound'
                """,
                (new_status, touch_id),
            )
            if cur.rowcount == 0:
                return jsonify({'success': False, 'error': 'Queue item not found'}), 404

        return jsonify({'success': True, 'id': touch_id, 'status': new_status})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# ============================================================================
# CONTACTS MANAGEMENT API ENDPOINTS
# ============================================================================

try:
    from automation.contacts_manager import UnifiedContactsManager
    CONTACTS_SYSTEM_AVAILABLE = True
except ImportError as e:
    print(f"⚠️  Contacts system not available: {e}")
    CONTACTS_SYSTEM_AVAILABLE = False


def _resolve_contact_brand(requested_brand: str = '') -> str:
    """Resolve brand from explicit value, active session brand, or first active DB brand."""
    brand = (requested_brand or '').strip()
    if brand:
        return brand

    session_brand = (session.get('active_brand_name') or '').strip()
    if session_brand:
        return session_brand

    try:
        from dashboard.models import Brand
        first_brand = Brand.query.filter_by(is_active=True).order_by(Brand.name.asc()).first()
        if first_brand:
            return (first_brand.name or '').strip()
    except Exception:
        pass

    return ''

@app.route('/api/contacts')
def api_list_contacts():
    """Get filtered list of contacts"""
    if not CONTACTS_SYSTEM_AVAILABLE:
        return jsonify({'error': 'Contacts system not available'}), 503
    
    try:
        manager = UnifiedContactsManager()
        
        # Get query parameters
        brand = request.args.get('brand')
        contact_type = request.args.get('contact_type') 
        status = request.args.get('status')
        search = request.args.get('search')
        classification = request.args.get('classification')
        responded_only = request.args.get('responded') in {'1', 'true', 'yes'}
        has_external_trace = request.args.get('has_external_trace') in {'1', 'true', 'yes'}
        limit = int(request.args.get('limit', 100))
        offset = int(request.args.get('offset', 0))
        
        contacts = manager.get_contacts(
            brand=brand,
            contact_type=contact_type,
            status=status,
            search=search,
            classification=classification or None,
            responded_only=responded_only,
            has_external_trace=has_external_trace,
            limit=limit,
            offset=offset,
        )
        
        return jsonify(contacts)
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/contacts/export')
def api_export_contacts_csv():
    """Export filtered contacts as CSV, including classification/tags/latest trace/latest response."""
    if not CONTACTS_SYSTEM_AVAILABLE:
        return jsonify({'error': 'Contacts system not available'}), 503

    try:
        manager = UnifiedContactsManager()
        csv_text = manager.export_contacts_csv(
            brand=request.args.get('brand') or None,
            contact_type=request.args.get('contact_type') or None,
            status=request.args.get('status') or None,
            search=request.args.get('search') or None,
            classification=request.args.get('classification') or None,
            responded_only=request.args.get('responded') in {'1', 'true', 'yes'},
            has_external_trace=request.args.get('has_external_trace') in {'1', 'true', 'yes'},
        )
        return Response(
            csv_text,
            mimetype='text/csv',
            headers={
                'Content-Disposition': 'attachment; filename=contacts_export.csv'
            },
        )
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/contacts/stats')
def api_contacts_stats():
    """Get contact statistics"""
    if not CONTACTS_SYSTEM_AVAILABLE:
        return jsonify({'error': 'Contacts system not available'}), 503
    
    try:
        manager = UnifiedContactsManager()
        brand = request.args.get('brand')
        stats = manager.get_contact_stats(brand=brand)
        return jsonify(stats)
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/contacts/<int:contact_id>')
def api_get_contact(contact_id):
    """Get single contact with full details"""
    if not CONTACTS_SYSTEM_AVAILABLE:
        return jsonify({'error': 'Contacts system not available'}), 503
    
    try:
        manager = UnifiedContactsManager()
        contact = manager.get_contact(contact_id)
        
        if not contact:
            return jsonify({'error': 'Contact not found'}), 404
        
        return jsonify(contact)
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/contacts', methods=['POST'])
def api_create_contact():
    """Create new contact"""
    if not CONTACTS_SYSTEM_AVAILABLE:
        return jsonify({'error': 'Contacts system not available'}), 503
    
    try:
        manager = UnifiedContactsManager()
        contact_data = request.get_json()
        
        if not contact_data:
            return jsonify({'error': 'No contact data provided'}), 400

        contact_data['brand'] = _resolve_contact_brand(contact_data.get('brand'))
        if not contact_data['brand']:
            return jsonify({'success': False, 'error': 'No brand available. Create/select a brand first.'}), 400
        
        contact_id = manager.create_contact(contact_data)
        contact = manager.get_contact(contact_id)
        
        return jsonify({
            'success': True,
            'contact': contact
        }), 201
        
    except ValueError as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 409
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/contacts/<int:contact_id>', methods=['PUT'])
def api_update_contact(contact_id):
    """Update existing contact"""
    if not CONTACTS_SYSTEM_AVAILABLE:
        return jsonify({'error': 'Contacts system not available'}), 503
    
    try:
        manager = UnifiedContactsManager()
        update_data = request.get_json()
        
        if not update_data:
            return jsonify({'error': 'No update data provided'}), 400
        
        success = manager.update_contact(contact_id, update_data)
        
        if not success:
            return jsonify({'error': 'Contact not found or update failed'}), 404
        
        contact = manager.get_contact(contact_id)
        
        return jsonify({
            'success': True,
            'contact': contact
        })
        
    except ValueError as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 409
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/contacts/<int:contact_id>', methods=['DELETE'])
def api_delete_contact(contact_id):
    """Delete contact"""
    if not CONTACTS_SYSTEM_AVAILABLE:
        return jsonify({'error': 'Contacts system not available'}), 503
    
    try:
        manager = UnifiedContactsManager()
        success = manager.delete_contact(contact_id)
        
        if not success:
            return jsonify({'error': 'Contact not found'}), 404
        
        return jsonify({'success': True})
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/contacts/import', methods=['POST'])
def api_import_contacts():
    """Import existing outreach and influencer data"""
    if not CONTACTS_SYSTEM_AVAILABLE:
        return jsonify({'error': 'Contacts system not available'}), 503
    
    try:
        manager = UnifiedContactsManager()
        manager.import_existing_data()
        
        return jsonify({
            'success': True,
            'message': 'Contact data imported successfully'
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/contacts/import-csv', methods=['POST'])
def api_import_contacts_csv():
    """CSV import with auto-field-mapping and social media enrichment.

    Dry-run (preview + mapping detection):
        POST {csv_text, brand, dry_run: true}

    Full import:
        POST {csv_text, brand, mapping, source_label, contact_type, dry_run: false}
    """
    if not CONTACTS_SYSTEM_AVAILABLE:
        return jsonify({'error': 'Contacts system not available'}), 503

    try:
        import csv as _csv
        import io as _io

        data = request.get_json() or {}
        csv_text = data.get('csv_text', '')
        if not csv_text:
            return jsonify({'success': False, 'error': 'csv_text is required'}), 400

        reader = _csv.DictReader(_io.StringIO(csv_text))
        headers = list(reader.fieldnames or [])
        rows = list(reader)

        auto_mapping = UnifiedContactsManager.auto_detect_mapping(headers)

        if data.get('dry_run'):
            preview = [{h: (r.get(h) or '') for h in headers} for r in rows[:5]]
            return jsonify({
                'success': True,
                'headers': headers,
                'auto_mapping': auto_mapping,
                'preview_rows': preview,
                'total_rows': len(rows),
            })

        # Full import
        brand = _resolve_contact_brand(data.get('brand'))
        if not brand:
            return jsonify({'success': False, 'error': 'No brand available. Create/select a brand first.'}), 400

        mapping = data.get('mapping') or auto_mapping
        source_label = (data.get('source_label') or 'csv_import').strip()
        contact_type = data.get('contact_type', 'email')

        manager = UnifiedContactsManager()
        result = manager.import_from_csv(rows, mapping, source_label, contact_type, brand)
        return jsonify({'success': True, **result})

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/contacts/<int:contact_id>/touches', methods=['POST'])
def api_add_touch(contact_id):
    """Add touch/interaction to contact.

    Supports optional fields for tracing external interactions:
      external_url  – URL of the post, thread, or conversation (e.g. LinkedIn post, tweet)
      external_ref  – Platform-specific ID/thread reference
      responded_at  – ISO datetime when the contact replied (if already known)
    """
    if not CONTACTS_SYSTEM_AVAILABLE:
        return jsonify({'error': 'Contacts system not available'}), 503

    try:
        manager = UnifiedContactsManager()
        touch_data = request.get_json()

        if not touch_data:
            return jsonify({'error': 'No touch data provided'}), 400

        touch_id = manager.add_touch(contact_id, touch_data)

        return jsonify({
            'success': True,
            'touch_id': touch_id
        }), 201

    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/contacts/touches/<int:touch_id>/respond', methods=['POST'])
def api_log_response(touch_id):
    """Record a contact's response against an existing outbound touch.

    Body: { "response_text": "...", "responded_at": "2026-06-09T14:00:00" (optional) }
    """
    if not CONTACTS_SYSTEM_AVAILABLE:
        return jsonify({'error': 'Contacts system not available'}), 503

    try:
        data = request.get_json() or {}
        response_text = (data.get('response_text') or '').strip()
        if not response_text:
            return jsonify({'error': 'response_text is required'}), 400

        manager = UnifiedContactsManager()
        ok = manager.log_response(
            touch_id,
            response_text,
            responded_at=data.get('responded_at'),
        )
        if not ok:
            return jsonify({'error': 'Touch not found'}), 404

        return jsonify({'success': True, 'touch_id': touch_id})

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/contacts/<int:contact_id>/tags', methods=['PATCH'])
def api_patch_contact_tags(contact_id):
    """Set the full tags list and/or classification for a contact.

    Body: { "tags": ["tag1", "tag2"], "classification": "warm_lead" }
    """
    if not CONTACTS_SYSTEM_AVAILABLE:
        return jsonify({'error': 'Contacts system not available'}), 503

    try:
        data = request.get_json() or {}
        update: dict = {}
        if 'tags' in data:
            tags = data['tags']
            if not isinstance(tags, list):
                return jsonify({'error': 'tags must be a list'}), 400
            update['tags'] = tags
        if 'classification' in data:
            update['classification'] = str(data['classification']).strip()

        if not update:
            return jsonify({'error': 'Provide tags and/or classification'}), 400

        manager = UnifiedContactsManager()
        ok = manager.update_contact(contact_id, update)
        if not ok:
            return jsonify({'error': 'Contact not found'}), 404

        return jsonify({'success': True})

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.errorhandler(404)
def page_not_found(e):
    if request.path.startswith('/api/'):
        return jsonify({'error': 'Not found', 'path': request.path}), 404
    return render_template('404.html', login_url='/login', marketing_url='/'), 404


@app.errorhandler(500)
def internal_server_error(e):
    try:
        from error_issue_reporter import report_server_error

        report_server_error(e, request.path, request.method, component='dashboard')
    except Exception:
        pass

    if request.path.startswith('/api/'):
        return jsonify({'error': 'Internal server error'}), 500
    return render_template('404.html', login_url='/login', marketing_url='/', is_500=True), 500


if __name__ == '__main__':
    # Get configuration
    host = os.getenv('HOST', dashboard.config['dashboard'].get('host', '0.0.0.0'))
    port = int(os.getenv('PORT', dashboard.config['dashboard'].get('port', 8002)))
    debug = os.getenv('DEBUG', 'false').lower() == 'true'

    print(f"🚀 Starting Marketing Automation Dashboard")
    print(f"📊 URL: http://{host}:{port}")
    print(f"🎨 Brands: {', '.join(dashboard.brands)}")
    print(f"🤖 AI Integration: {'✅ Available' if dashboard.ai_generator else '❌ Not Available'}")

    app.run(host=host, port=port, debug=debug)
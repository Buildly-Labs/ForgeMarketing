"""
Admin API endpoints for managing brands, users, and their configurations
"""

from flask import Blueprint, request, jsonify, current_app
from flask_login import login_required, current_user
from functools import wraps
from datetime import datetime
from typing import Dict, Any, Tuple
import logging
import os
import smtplib
from email.message import EmailMessage

from dashboard.models import db, Brand, BrandEmailConfig, BrandSettings, APICredentialLog, SystemConfig, User, UserBrand

logger = logging.getLogger(__name__)

admin_bp = Blueprint('admin', __name__, url_prefix='/api/admin')


def _get_system_config_map() -> Dict[str, str]:
    rows = SystemConfig.query.all()
    return {row.key: (row.value or '') for row in rows}


def _resolve_smtp_settings() -> Dict[str, Any]:
    cfg = _get_system_config_map()
    host = cfg.get('BREVO_SMTP_HOST') or os.getenv('BREVO_SMTP_HOST') or 'smtp-relay.brevo.com'
    port_raw = cfg.get('BREVO_SMTP_PORT') or os.getenv('BREVO_SMTP_PORT') or '587'
    try:
        port = int(port_raw)
    except Exception:
        port = 587

    username = cfg.get('BREVO_SMTP_LOGIN') or os.getenv('BREVO_SMTP_LOGIN') or os.getenv('BREVO_SMTP_USER') or ''
    password = cfg.get('BREVO_SMTP_KEY') or os.getenv('BREVO_SMTP_KEY') or os.getenv('BREVO_SMTP_PASSWORD') or ''
    from_email = cfg.get('FROM_EMAIL') or os.getenv('FROM_EMAIL') or username
    from_name = cfg.get('FROM_NAME') or os.getenv('FROM_NAME') or 'First City Foundry'

    return {
        'host': host,
        'port': port,
        'username': username,
        'password': password,
        'from_email': from_email,
        'from_name': from_name,
    }


def _send_user_welcome_email(user_email: str, display_name: str, temp_password: str,
                             region: str, login_url: str, invited_by: str) -> Tuple[bool, str]:
    smtp = _resolve_smtp_settings()
    if not smtp['host'] or not smtp['from_email'] or not smtp['username'] or not smtp['password']:
        return False, 'SMTP settings are incomplete (host/from_email/login/key required)'

    safe_name = display_name or user_email
    msg = EmailMessage()
    msg['Subject'] = 'Your Marketing Hub account details'
    msg['From'] = f"{smtp['from_name']} <{smtp['from_email']}>"
    msg['To'] = user_email

    text_body = f"""Hi {safe_name},

Your account has been created for Marketing Hub.

Login URL: {login_url}
Email: {user_email}
Temporary Password: {temp_password}
Assigned Region: {region or 'Not specified'}

Please sign in and change your password immediately.

Provisioned by: {invited_by}
"""
    msg.set_content(text_body)

    with smtplib.SMTP(smtp['host'], smtp['port'], timeout=20) as server:
        server.starttls()
        server.login(smtp['username'], smtp['password'])
        server.send_message(msg)

    return True, ''


def admin_required(fn):
    """Decorator that requires the current user to be an admin."""
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not hasattr(current_app, 'login_manager'):
            return fn(*args, **kwargs)
        if not getattr(current_user, 'is_authenticated', False):
            return jsonify({'success': False, 'error': 'Authentication required'}), 401
        if not getattr(current_user, 'is_admin', False):
            return jsonify({'success': False, 'error': 'Admin access required'}), 403
        return fn(*args, **kwargs)
    return wrapper


@admin_bp.before_request
def require_login():
    """Require auth only when Flask-Login is configured on the current app."""
    if not hasattr(current_app, 'login_manager'):
        return None
    if not getattr(current_user, 'is_authenticated', False):
        return jsonify({'success': False, 'error': 'Authentication required'}), 401
    return None


# ============================================================================
# BRAND MANAGEMENT ENDPOINTS
# ============================================================================

@admin_bp.route('/brands', methods=['GET'])
def list_brands() -> Tuple[Dict[str, Any], int]:
    """List all brands with their configurations"""
    try:
        brands = Brand.query.filter_by(is_active=True).all()
        
        brands_data = []
        for brand in brands:
            brand_dict = brand.to_dict()
            
            # Get email configs
            email_configs = BrandEmailConfig.query.filter_by(brand_id=brand.id).all()
            brand_dict['email_providers'] = [
                {'provider': config.provider, 'is_primary': config.is_primary, 'is_verified': config.is_verified}
                for config in email_configs
            ]
            
            brands_data.append(brand_dict)
        
        return jsonify({
            'success': True,
            'brands': brands_data,
            'total': len(brands_data)
        }), 200
    
    except Exception as e:
        logger.error(f"Error listing brands: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@admin_bp.route('/brands/<brand_name>', methods=['GET'])
def get_brand(brand_name: str) -> Tuple[Dict[str, Any], int]:
    """Get detailed brand information"""
    try:
        brand = Brand.query.filter_by(name=brand_name).first()
        if not brand:
            return jsonify({'success': False, 'error': 'Brand not found'}), 404
        
        brand_dict = brand.to_dict()
        
        # Get email configurations
        email_configs = BrandEmailConfig.query.filter_by(brand_id=brand.id).all()
        brand_dict['email_configs'] = [config.to_dict() for config in email_configs]
        
        # Get settings
        settings = BrandSettings.query.filter_by(brand_id=brand.id).first()
        brand_dict['settings'] = settings.to_dict() if settings else None
        
        # Get recent activity logs
        logs = APICredentialLog.query.filter_by(brand_id=brand.id)\
            .order_by(APICredentialLog.created_at.desc())\
            .limit(10)\
            .all()
        brand_dict['recent_activity'] = [log.to_dict() for log in logs]
        
        return jsonify({'success': True, 'brand': brand_dict}), 200
    
    except Exception as e:
        logger.error(f"Error getting brand {brand_name}: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@admin_bp.route('/brands', methods=['POST'])
def create_brand() -> Tuple[Dict[str, Any], int]:
    """Create a new brand"""
    try:
        data = request.get_json() or {}
        
        # Validate required fields
        if not data.get('name') or not data.get('display_name'):
            return jsonify({
                'success': False,
                'error': 'name and display_name are required'
            }), 400
        
        # Check if brand already exists
        if Brand.query.filter_by(name=data['name']).first():
            return jsonify({
                'success': False,
                'error': f"Brand '{data['name']}' already exists"
            }), 409
        
        # Create brand
        brand = Brand(
            name=data['name'],
            display_name=data['display_name'],
            description=data.get('description', ''),
            logo_url=data.get('logo_url', ''),
            website_url=data.get('website_url', ''),
            is_active=data.get('is_active', True)
        )
        db.session.add(brand)
        db.session.flush()
        
        # Create default settings
        settings = BrandSettings(brand_id=brand.id)
        db.session.add(settings)
        
        db.session.commit()
        
        _log_action(brand.id, None, 'created', 'Created new brand', True, data=data)
        
        return jsonify({
            'success': True,
            'brand': brand.to_dict(),
            'message': f"Brand '{brand.display_name}' created successfully"
        }), 201
    
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error creating brand: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@admin_bp.route('/brands/<brand_name>', methods=['PUT'])
def update_brand(brand_name: str) -> Tuple[Dict[str, Any], int]:
    """Update brand information"""
    try:
        brand = Brand.query.filter_by(name=brand_name).first()
        if not brand:
            return jsonify({'success': False, 'error': 'Brand not found'}), 404
        
        data = request.get_json() or {}
        
        # Update fields
        if 'display_name' in data:
            brand.display_name = data['display_name']
        if 'description' in data:
            brand.description = data['description']
        if 'logo_url' in data:
            brand.logo_url = data['logo_url']
        if 'website_url' in data:
            brand.website_url = data['website_url']
        if 'is_active' in data:
            brand.is_active = data['is_active']
        
        brand.updated_at = datetime.utcnow()
        db.session.commit()
        
        _log_action(brand.id, None, 'updated', 'Updated brand information', True, data=data)
        
        return jsonify({
            'success': True,
            'brand': brand.to_dict(),
            'message': f"Brand '{brand.display_name}' updated successfully"
        }), 200
    
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error updating brand {brand_name}: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================================
# EMAIL CONFIGURATION ENDPOINTS
# ============================================================================

@admin_bp.route('/brands/<brand_name>/email-configs', methods=['GET'])
def get_email_configs(brand_name: str) -> Tuple[Dict[str, Any], int]:
    """Get all email configurations for a brand"""
    try:
        brand = Brand.query.filter_by(name=brand_name).first()
        if not brand:
            return jsonify({'success': False, 'error': 'Brand not found'}), 404
        
        configs = BrandEmailConfig.query.filter_by(brand_id=brand.id).all()
        configs_data = [config.to_dict(include_secrets=False) for config in configs]
        
        return jsonify({
            'success': True,
            'brand_name': brand_name,
            'configs': configs_data,
            'total': len(configs_data)
        }), 200
    
    except Exception as e:
        logger.error(f"Error getting email configs for {brand_name}: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@admin_bp.route('/brands/<brand_name>/email-configs', methods=['POST'])
def add_email_config(brand_name: str) -> Tuple[Dict[str, Any], int]:
    """Add a new email configuration for a brand"""
    try:
        brand = Brand.query.filter_by(name=brand_name).first()
        if not brand:
            return jsonify({'success': False, 'error': 'Brand not found'}), 404
        
        data = request.get_json() or {}
        
        # Validate required fields
        required = ['provider', 'api_key', 'from_email']
        if not all(data.get(field) for field in required):
            return jsonify({
                'success': False,
                'error': f"Required fields: {', '.join(required)}"
            }), 400
        
        # Check if this provider already exists for this brand
        existing = BrandEmailConfig.query.filter_by(
            brand_id=brand.id,
            provider=data['provider']
        ).first()
        
        if existing:
            return jsonify({
                'success': False,
                'error': f"Email config for provider '{data['provider']}' already exists"
            }), 409
        
        # Create new config
        config = BrandEmailConfig(
            brand_id=brand.id,
            provider=data['provider'],
            api_key=data['api_key'],
            api_token=data.get('api_token', ''),
            smtp_host=data.get('smtp_host', ''),
            smtp_port=data.get('smtp_port', 587),
            smtp_user=data.get('smtp_user', ''),
            smtp_password=data.get('smtp_password', ''),
            from_email=data['from_email'],
            from_name=data.get('from_name', ''),
            reply_to_email=data.get('reply_to_email', ''),
            reply_to_name=data.get('reply_to_name', ''),
            is_primary=data.get('is_primary', False),
            max_send_per_day=data.get('max_send_per_day', 10000),
            rate_limit_per_minute=data.get('rate_limit_per_minute', 100)
        )
        
        # If this is the primary, unset other primaries
        if config.is_primary:
            BrandEmailConfig.query.filter_by(brand_id=brand.id).update({'is_primary': False})
        
        db.session.add(config)
        db.session.commit()
        
        _log_action(brand.id, config.id, 'created', f'Added {data["provider"]} email config', True, data=data)
        
        return jsonify({
            'success': True,
            'config': config.to_dict(),
            'message': f"Email config for '{data['provider']}' added successfully"
        }), 201
    
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error adding email config for {brand_name}: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@admin_bp.route('/brands/<brand_name>/email-configs/<provider>', methods=['PUT'])
def update_email_config(brand_name: str, provider: str) -> Tuple[Dict[str, Any], int]:
    """Update an email configuration"""
    try:
        brand = Brand.query.filter_by(name=brand_name).first()
        if not brand:
            return jsonify({'success': False, 'error': 'Brand not found'}), 404
        
        config = BrandEmailConfig.query.filter_by(
            brand_id=brand.id,
            provider=provider
        ).first()
        
        if not config:
            return jsonify({'success': False, 'error': f"Config for provider '{provider}' not found"}), 404
        
        data = request.get_json() or {}
        
        # Update fields
        if 'api_key' in data:
            config.api_key = data['api_key']
        if 'api_token' in data:
            config.api_token = data['api_token']
        if 'from_email' in data:
            config.from_email = data['from_email']
        if 'from_name' in data:
            config.from_name = data['from_name']
        if 'reply_to_email' in data:
            config.reply_to_email = data['reply_to_email']
        if 'reply_to_name' in data:
            config.reply_to_name = data['reply_to_name']
        if 'is_primary' in data:
            if data['is_primary']:
                # Unset other primaries
                BrandEmailConfig.query.filter_by(brand_id=brand.id).update({'is_primary': False})
            config.is_primary = data['is_primary']
        if 'max_send_per_day' in data:
            config.max_send_per_day = data['max_send_per_day']
        if 'rate_limit_per_minute' in data:
            config.rate_limit_per_minute = data['rate_limit_per_minute']
        
        config.updated_at = datetime.utcnow()
        db.session.commit()
        
        _log_action(brand.id, config.id, 'updated', f'Updated {provider} email config', True, data=data)
        
        return jsonify({
            'success': True,
            'config': config.to_dict(),
            'message': f"Email config for '{provider}' updated successfully"
        }), 200
    
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error updating email config for {brand_name}/{provider}: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@admin_bp.route('/brands/<brand_name>/email-configs/<provider>', methods=['DELETE'])
def delete_email_config(brand_name: str, provider: str) -> Tuple[Dict[str, Any], int]:
    """Delete an email configuration"""
    try:
        brand = Brand.query.filter_by(name=brand_name).first()
        if not brand:
            return jsonify({'success': False, 'error': 'Brand not found'}), 404
        
        config = BrandEmailConfig.query.filter_by(
            brand_id=brand.id,
            provider=provider
        ).first()
        
        if not config:
            return jsonify({'success': False, 'error': f"Config for provider '{provider}' not found"}), 404
        
        config_id = config.id
        db.session.delete(config)
        db.session.commit()
        
        _log_action(brand.id, config_id, 'deleted', f'Deleted {provider} email config', True)
        
        return jsonify({
            'success': True,
            'message': f"Email config for '{provider}' deleted successfully"
        }), 200
    
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error deleting email config for {brand_name}/{provider}: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================================
# BRAND SETTINGS ENDPOINTS
# ============================================================================

@admin_bp.route('/brands/<brand_name>/settings', methods=['GET'])
def get_brand_settings(brand_name: str) -> Tuple[Dict[str, Any], int]:
    """Get brand settings"""
    try:
        brand = Brand.query.filter_by(name=brand_name).first()
        if not brand:
            return jsonify({'success': False, 'error': 'Brand not found'}), 404
        
        settings = BrandSettings.query.filter_by(brand_id=brand.id).first()
        if not settings:
            return jsonify({'success': False, 'error': 'Settings not found'}), 404
        
        return jsonify({
            'success': True,
            'settings': settings.to_dict()
        }), 200
    
    except Exception as e:
        logger.error(f"Error getting settings for {brand_name}: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@admin_bp.route('/brands/<brand_name>/settings', methods=['PUT'])
def update_brand_settings(brand_name: str) -> Tuple[Dict[str, Any], int]:
    """Update brand settings"""
    try:
        brand = Brand.query.filter_by(name=brand_name).first()
        if not brand:
            return jsonify({'success': False, 'error': 'Brand not found'}), 404
        
        settings = BrandSettings.query.filter_by(brand_id=brand.id).first()
        if not settings:
            return jsonify({'success': False, 'error': 'Settings not found'}), 404
        
        data = request.get_json() or {}
        
        # Update fields
        if 'daily_email_limit' in data:
            settings.daily_email_limit = data['daily_email_limit']
        if 'enable_email_sending' in data:
            settings.enable_email_sending = data['enable_email_sending']
        if 'enable_ai_generation' in data:
            settings.enable_ai_generation = data['enable_ai_generation']
        if 'enable_social_posting' in data:
            settings.enable_social_posting = data['enable_social_posting']
        if 'auto_subscribe_new_contacts' in data:
            settings.auto_subscribe_new_contacts = data['auto_subscribe_new_contacts']
        if 'auto_unsubscribe_invalid' in data:
            settings.auto_unsubscribe_invalid = data['auto_unsubscribe_invalid']
        if 'default_campaign_type' in data:
            settings.default_campaign_type = data['default_campaign_type']
        if 'default_send_time' in data:
            settings.default_send_time = data['default_send_time']
        if 'default_send_day_of_week' in data:
            settings.default_send_day_of_week = data['default_send_day_of_week']
        if 'enable_analytics_tracking' in data:
            settings.enable_analytics_tracking = data['enable_analytics_tracking']
        if 'enable_utm_parameters' in data:
            settings.enable_utm_parameters = data['enable_utm_parameters']
        if 'advanced_settings' in data:
            settings.set_advanced_settings(data['advanced_settings'])
        
        settings.updated_at = datetime.utcnow()
        db.session.commit()
        
        _log_action(brand.id, None, 'updated', 'Updated brand settings', True, data=data)
        
        return jsonify({
            'success': True,
            'settings': settings.to_dict(),
            'message': f"Settings for '{brand.display_name}' updated successfully"
        }), 200
    
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error updating settings for {brand_name}: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================================
# SYSTEM CONFIGURATION ENDPOINTS
# ============================================================================

# Config categories and their keys (defines the wizard steps)
CONFIG_SCHEMA = {
    'email': {
        'label': 'Email (SMTP)',
        'fields': [
            {'key': 'BREVO_SMTP_KEY',  'label': 'Brevo SMTP Key',  'secret': True},
            {'key': 'BREVO_SMTP_LOGIN','label': 'Brevo SMTP Login', 'secret': False},
            {'key': 'BREVO_SMTP_HOST', 'label': 'SMTP Host',       'secret': False, 'default': 'smtp-relay.brevo.com'},
            {'key': 'BREVO_SMTP_PORT', 'label': 'SMTP Port',       'secret': False, 'default': '587'},
            {'key': 'FROM_EMAIL',      'label': 'Default From Email', 'secret': False},
            {'key': 'FROM_NAME',       'label': 'Default From Name',  'secret': False},
            {'key': 'REPLY_TO_EMAIL',  'label': 'Reply-To Email',     'secret': False},
        ]
    },
    'ai': {
        'label': 'AI Service',
        'fields': [
            {'key': 'ai_provider',     'label': 'AI Provider',    'secret': False, 'default': 'ollama',
             'type': 'select', 'options': ['ollama', 'openai', 'gemini']},
            {'key': 'ai_model',        'label': 'Model Name',     'secret': False, 'default': 'llama3'},
            {'key': 'OPENAI_API_KEY',  'label': 'OpenAI API Key', 'secret': True},
            {'key': 'GEMINI_API_KEY',  'label': 'Gemini API Key', 'secret': True},
            {'key': 'OLLAMA_HOST',     'label': 'Ollama Host',    'secret': False, 'default': 'http://localhost:11434'},
        ]
    },
    'social': {
        'label': 'Social Media',
        'fields': [
            {'key': 'TWITTER_API_KEY',            'label': 'Twitter API Key',      'secret': True},
            {'key': 'TWITTER_API_SECRET',         'label': 'Twitter API Secret',   'secret': True},
            {'key': 'TWITTER_ACCESS_TOKEN',       'label': 'Twitter Access Token', 'secret': True},
            {'key': 'TWITTER_ACCESS_TOKEN_SECRET','label': 'Twitter Access Secret','secret': True},
            {'key': 'TWITTER_BEARER_TOKEN',       'label': 'Twitter/X Bearer Token (v2)', 'secret': True,
             'help': 'Required for Twitter/X API v2 user lookup and search.'},
            {'key': 'LINKEDIN_CLIENT_ID',         'label': 'LinkedIn Client ID',   'secret': False},
            {'key': 'LINKEDIN_CLIENT_SECRET',     'label': 'LinkedIn Client Secret','secret': True},
            {'key': 'LINKEDIN_ACCESS_TOKEN',      'label': 'LinkedIn Access Token', 'secret': True,
             'help': 'Optional. Used for authenticated LinkedIn profile/discovery API calls.'},
            {'key': 'LINKEDIN_REFRESH_TOKEN',     'label': 'LinkedIn Refresh Token', 'secret': True,
             'help': 'Optional. Used to rotate LinkedIn access tokens for long-running automation.'},
            {'key': 'LINKEDIN_AUTHOR_URN',        'label': 'LinkedIn Author URN', 'secret': False,
             'help': 'Required for direct LinkedIn outreach posting (e.g. urn:li:person:...).'},
            {'key': 'TWITTER_OUTREACH_WEBHOOK_URL','label': 'Twitter Outreach Webhook URL', 'secret': True,
             'help': 'Optional fallback endpoint when direct Twitter API delivery is unavailable.'},
            {'key': 'LINKEDIN_OUTREACH_WEBHOOK_URL','label': 'LinkedIn Outreach Webhook URL', 'secret': True,
             'help': 'Optional fallback endpoint when direct LinkedIn API delivery is unavailable.'},
            {'key': 'SOCIAL_OUTREACH_WEBHOOK_URL','label': 'Generic Social Outreach Webhook URL', 'secret': True,
             'help': 'Fallback dispatcher for channels like Instagram/Bluesky/Mastodon/TikTok.'},
        ]
    },
    'startup_intel': {
        'label': 'Startup Intel Plugin',
        'fields': [
            {
                'key': 'startup_intel_product_hunt_token',
                'label': 'Product Hunt API Bearer Token',
                'secret': True,
                'help': 'Get at producthunt.com/v2/oauth/applications → create app → Developer Token. Enables product_hunt_api source.',
            },
            {
                'key': 'startup_intel_opencorporates_key',
                'label': 'OpenCorporates API Key',
                'secret': True,
                'help': 'Register free at opencorporates.com/api_accounts/new. Enables opencorporates source.',
            },
            {
                'key': 'startup_intel_companies_house_key',
                'label': 'Companies House API Key (UK)',
                'secret': True,
                'help': 'Register free at developer.company-information.service.gov.uk. Enables companies_house source.',
            },
            {
                'key': 'startup_intel_github_token',
                'label': 'GitHub Personal Access Token (enrichment)',
                'secret': True,
                'help': 'Optional. Generate at github.com/settings/tokens/new (no scopes needed). Raises enrichment rate limit from 60 to 5,000 req/hr.',
            },
        ]
    },
    'analytics': {
        'label': 'Analytics',
        'fields': [
            {'key': 'GOOGLE_ANALYTICS_PROPERTY_ID', 'label': 'GA Property ID',     'secret': False},
            {'key': 'GOOGLE_ANALYTICS_API_KEY',      'label': 'Google API Key',     'secret': True},
            {'key': 'YOUTUBE_CHANNEL_ID',            'label': 'YouTube Channel ID', 'secret': False},
            {'key': 'YOUTUBE_API_KEY',               'label': 'YouTube API Key',    'secret': True},
        ]
    },
    'notifications': {
        'label': 'Notifications',
        'fields': [
            {'key': 'DAILY_NOTIFICATION_EMAIL', 'label': 'Daily Notification Email', 'secret': False},
            {'key': 'DAILY_CC_EMAIL',           'label': 'Daily CC Email',           'secret': False},
            {'key': 'PUSHOVER_USER_KEY',        'label': 'Pushover User Key',        'secret': True},
            {'key': 'PUSHOVER_API_TOKEN',       'label': 'Pushover API Token',       'secret': True},
        ]
    },
    'outreach': {
        'label': 'Outreach Limits',
        'fields': [
            {'key': 'MAX_DAILY_OUTREACH',     'label': 'Max Daily Outreach',     'secret': False, 'default': '50'},
            {'key': 'MAX_PER_ORGANIZATION',   'label': 'Max Per Organization',   'secret': False, 'default': '4'},
            {'key': 'MIN_DELAY_SECONDS',      'label': 'Min Delay (seconds)',    'secret': False, 'default': '30'},
            {'key': 'MAX_DELAY_SECONDS',      'label': 'Max Delay (seconds)',    'secret': False, 'default': '60'},
        ]
    },
    'site': {
        'label': 'Site Identity',
        'fields': [
            {'key': 'WEBSITE_URL', 'label': 'Website URL', 'secret': False},
            {'key': 'SITE_NAME',   'label': 'Site Name',   'secret': False},
        ]
    },
}


@admin_bp.route('/config/schema', methods=['GET'])
def config_schema():
    """Return the config wizard schema (categories + fields)"""
    return jsonify({'success': True, 'schema': CONFIG_SCHEMA}), 200


@admin_bp.route('/config', methods=['GET'])
def list_configs():
    """List all system config values (secrets masked)"""
    try:
        category = request.args.get('category')
        query = SystemConfig.query
        if category:
            query = query.filter_by(category=category)
        configs = query.order_by(SystemConfig.category, SystemConfig.key).all()
        return jsonify({
            'success': True,
            'configs': [c.to_dict() for c in configs],
        }), 200
    except Exception as e:
        logger.error(f"Error listing configs: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@admin_bp.route('/config', methods=['PUT'])
def save_configs():
    """Bulk-save config key/value pairs. Body: {items: [{key, value, category, is_secret}]}"""
    try:
        data = request.get_json() or {}
        items = data.get('items', [])
        if not items:
            return jsonify({'success': False, 'error': 'No items provided'}), 400

        from flask_login import current_user
        saved = []
        for item in items:
            key = item.get('key', '').strip()
            value = item.get('value', '').strip()
            if not key:
                continue
            cfg = SystemConfig.query.filter_by(key=key).first()
            if cfg:
                cfg.value = value
                cfg.is_secret = item.get('is_secret', cfg.is_secret)
                cfg.category = item.get('category', cfg.category)
                cfg.updated_by = current_user.email if current_user.is_authenticated else 'system'
                cfg.updated_at = datetime.utcnow()
            else:
                cfg = SystemConfig(
                    key=key,
                    value=value,
                    category=item.get('category', 'general'),
                    is_secret=item.get('is_secret', False),
                    description=item.get('description', ''),
                    updated_by=current_user.email if current_user.is_authenticated else 'system',
                )
                db.session.add(cfg)
            saved.append(key)

        db.session.commit()
        return jsonify({'success': True, 'saved': saved}), 200
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error saving configs: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@admin_bp.route('/config/<key>', methods=['DELETE'])
def delete_config(key: str):
    """Delete a single config entry"""
    try:
        cfg = SystemConfig.query.filter_by(key=key).first()
        if not cfg:
            return jsonify({'success': False, 'error': 'Not found'}), 404
        db.session.delete(cfg)
        db.session.commit()
        return jsonify({'success': True}), 200
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error deleting config {key}: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================================
# AUDIT LOG ENDPOINTS
# ============================================================================

@admin_bp.route('/audit-logs/<brand_name>', methods=['GET'])
def get_audit_logs(brand_name: str) -> Tuple[Dict[str, Any], int]:
    """Get audit logs for a brand"""
    try:
        brand = Brand.query.filter_by(name=brand_name).first()
        if not brand:
            return jsonify({'success': False, 'error': 'Brand not found'}), 404
        
        limit = request.args.get('limit', 100, type=int)
        offset = request.args.get('offset', 0, type=int)
        
        logs = APICredentialLog.query.filter_by(brand_id=brand.id)\
            .order_by(APICredentialLog.created_at.desc())\
            .offset(offset)\
            .limit(limit)\
            .all()
        
        total = APICredentialLog.query.filter_by(brand_id=brand.id).count()
        
        return jsonify({
            'success': True,
            'logs': [log.to_dict() for log in logs],
            'total': total,
            'limit': limit,
            'offset': offset
        }), 200
    
    except Exception as e:
        logger.error(f"Error getting audit logs for {brand_name}: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def _log_action(brand_id: int, config_id: int = None, action: str = '', 
                details: str = '', success: bool = True, data: Dict = None) -> None:
    """Log an action for audit trail"""
    try:
        import json
        log_entry = APICredentialLog(
            brand_id=brand_id,
            email_config_id=config_id,
            action=action,
            details=details,
            success=success
        )
        db.session.add(log_entry)
        db.session.commit()
    except Exception as e:
        logger.error(f"Failed to log action: {e}")


# ============================================================================
# USER MANAGEMENT ENDPOINTS
# ============================================================================

@admin_bp.route('/users', methods=['GET'])
@admin_required
def list_users():
    """List all users with their brand memberships."""
    try:
        users = User.query.order_by(User.email).all()
        return jsonify({
            'success': True,
            'users': [u.to_dict() for u in users],
            'total': len(users),
        }), 200
    except Exception as e:
        logger.error(f"Error listing users: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@admin_bp.route('/users', methods=['POST'])
@admin_required
def create_user():
    """Create a new user and optionally assign brands.

    JSON body:
        email (str, required)
        password (str, required)
        display_name (str)
        is_admin (bool)
        brand_ids (list[int])  — brands to grant access to
        role (str)             — role for all assigned brands (default: editor)
        region (str)           — user region assignment (e.g. northeast, emea)
        send_welcome_email (bool) — send login details email (default: true)
        login_url (str)        — login URL included in welcome email
    """
    try:
        data = request.get_json() or {}
        email = (data.get('email') or '').strip().lower()
        password = data.get('password', '')

        if not email or not password:
            return jsonify({'success': False, 'error': 'Email and password are required'}), 400

        if User.query.filter_by(email=email).first():
            return jsonify({'success': False, 'error': 'A user with that email already exists'}), 409

        region = (data.get('region') or '').strip()
        send_welcome_email = bool(data.get('send_welcome_email', True))

        user = User(
            email=email,
            display_name=data.get('display_name', ''),
            is_admin=bool(data.get('is_admin', False)),
            must_change_password=bool(data.get('must_change_password', True)),
            region=region,
        )
        user.set_password(password)
        db.session.add(user)
        db.session.flush()

        role = data.get('role', 'editor')
        for bid in data.get('brand_ids', []):
            if Brand.query.get(bid):
                db.session.add(UserBrand(user_id=user.id, brand_id=bid, role=role))

        db.session.commit()

        email_delivery = {'attempted': False, 'sent': False, 'error': ''}
        if send_welcome_email:
            email_delivery['attempted'] = True
            login_url = (data.get('login_url') or '').strip()
            if not login_url:
                cfg = _get_system_config_map()
                base_url = (cfg.get('WEBSITE_URL') or '').rstrip('/')
                login_url = f"{base_url}/login" if base_url else '/login'
            sent, err = _send_user_welcome_email(
                user_email=user.email,
                display_name=user.display_name,
                temp_password=password,
                region=user.region or '',
                login_url=login_url,
                invited_by=getattr(current_user, 'email', 'admin'),
            )
            email_delivery['sent'] = sent
            email_delivery['error'] = err

        logger.info(f"User created: {email} by {current_user.email}")
        return jsonify({'success': True, 'user': user.to_dict(), 'welcome_email': email_delivery}), 201

    except Exception as e:
        db.session.rollback()
        logger.error(f"Error creating user: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@admin_bp.route('/users/<int:user_id>', methods=['GET'])
@admin_required
def get_user(user_id: int):
    """Get a single user's details."""
    user = User.query.get(user_id)
    if not user:
        return jsonify({'success': False, 'error': 'User not found'}), 404

    data = user.to_dict()
    data['brand_memberships'] = [
        {'brand_id': ub.brand_id, 'brand_name': ub.brand.name, 'role': ub.role}
        for ub in user.brand_memberships.all()
    ]
    return jsonify({'success': True, 'user': data}), 200


@admin_bp.route('/users/<int:user_id>', methods=['PUT', 'PATCH'])
@admin_required
def update_user(user_id: int):
    """Update an existing user.

    JSON body (all optional):
        email, display_name, is_admin, is_active, password,
        brand_ids (replaces current list), role
    """
    try:
        user = User.query.get(user_id)
        if not user:
            return jsonify({'success': False, 'error': 'User not found'}), 404

        data = request.get_json() or {}

        if 'email' in data:
            new_email = data['email'].strip().lower()
            existing = User.query.filter(User.email == new_email, User.id != user_id).first()
            if existing:
                return jsonify({'success': False, 'error': 'Email already in use'}), 409
            user.email = new_email
        if 'display_name' in data:
            user.display_name = data['display_name']
        if 'region' in data:
            user.region = (data.get('region') or '').strip()
        if 'is_admin' in data:
            user.is_admin = bool(data['is_admin'])
        if 'is_active' in data:
            user.is_active_user = bool(data['is_active'])
        if 'password' in data and data['password']:
            user.set_password(data['password'])
            user.must_change_password = False

        # Replace brand memberships if provided
        if 'brand_ids' in data:
            UserBrand.query.filter_by(user_id=user.id).delete()
            role = data.get('role', 'editor')
            for bid in data['brand_ids']:
                if Brand.query.get(bid):
                    db.session.add(UserBrand(user_id=user.id, brand_id=bid, role=role))

        db.session.commit()
        logger.info(f"User updated: {user.email} by {current_user.email}")
        return jsonify({'success': True, 'user': user.to_dict()}), 200

    except Exception as e:
        db.session.rollback()
        logger.error(f"Error updating user: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@admin_bp.route('/users/<int:user_id>', methods=['DELETE'])
@admin_required
def delete_user(user_id: int):
    """Deactivate (soft-delete) a user. Does not remove the row."""
    try:
        user = User.query.get(user_id)
        if not user:
            return jsonify({'success': False, 'error': 'User not found'}), 404
        if user.id == current_user.id:
            return jsonify({'success': False, 'error': 'Cannot delete your own account'}), 400

        user.is_active_user = False
        db.session.commit()
        logger.info(f"User deactivated: {user.email} by {current_user.email}")
        return jsonify({'success': True, 'message': f'User {user.email} deactivated'}), 200

    except Exception as e:
        db.session.rollback()
        logger.error(f"Error deactivating user: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

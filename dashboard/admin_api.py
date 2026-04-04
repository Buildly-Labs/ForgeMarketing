"""
Admin API endpoints for managing brands and their configurations
"""

from flask import Blueprint, request, jsonify
from flask_login import login_required
from datetime import datetime
from typing import Dict, Any, Tuple
import logging

from dashboard.models import db, Brand, BrandEmailConfig, BrandSettings, APICredentialLog

logger = logging.getLogger(__name__)

admin_bp = Blueprint('admin', __name__, url_prefix='/api/admin')


@admin_bp.before_request
@login_required
def require_login():
    """All admin API endpoints require authentication."""
    pass


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

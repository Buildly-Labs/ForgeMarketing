"""
Database models for the Marketing Automation Dashboard
Stores brand configurations, API credentials, and system settings
"""

from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime
from typing import Dict, Any, Optional, List
import json
import bcrypt

db = SQLAlchemy()


# ============================================================================
# USER & AUTH MODELS
# ============================================================================

class User(UserMixin, db.Model):
    """A user who can log in and manage one or more brands"""
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    display_name = db.Column(db.String(255), default='')
    is_admin = db.Column(db.Boolean, default=False)
    is_active_user = db.Column(db.Boolean, default=True)
    must_change_password = db.Column(db.Boolean, default=False)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_login_at = db.Column(db.DateTime, nullable=True)

    # Relationships
    brand_memberships = db.relationship('UserBrand', backref='user', lazy='dynamic', cascade='all, delete-orphan')

    def set_password(self, password: str) -> None:
        self.password_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

    def check_password(self, password: str) -> bool:
        return bcrypt.checkpw(password.encode('utf-8'), self.password_hash.encode('utf-8'))

    @property
    def is_active(self):
        return self.is_active_user

    def get_brands(self) -> list:
        """Return Brand objects this user may access"""
        return [ub.brand for ub in self.brand_memberships.all() if ub.brand.is_active]

    def has_brand_access(self, brand_id: int) -> bool:
        if self.is_admin:
            return True
        return self.brand_memberships.filter_by(brand_id=brand_id).first() is not None

    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'email': self.email,
            'display_name': self.display_name,
            'is_admin': self.is_admin,
            'is_active': self.is_active_user,
            'must_change_password': self.must_change_password,
            'brands': [ub.brand.name for ub in self.brand_memberships.all()],
            'last_login_at': self.last_login_at.isoformat() if self.last_login_at else None,
        }


class UserBrand(db.Model):
    """Links a user to one or more brands they can manage"""
    __tablename__ = 'user_brands'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    brand_id = db.Column(db.Integer, db.ForeignKey('brands.id'), nullable=False, index=True)
    role = db.Column(db.String(50), default='editor')  # owner, editor, viewer

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    brand = db.relationship('Brand', backref='user_memberships')

    __table_args__ = (
        db.UniqueConstraint('user_id', 'brand_id', name='unique_user_brand'),
    )


# ============================================================================
# BRAND THEME MODEL
# ============================================================================

class BrandTheme(db.Model):
    """Data-driven visual theme for each brand"""
    __tablename__ = 'brand_themes'

    id = db.Column(db.Integer, primary_key=True)
    brand_id = db.Column(db.Integer, db.ForeignKey('brands.id'), nullable=False, unique=True, index=True)

    primary_color = db.Column(db.String(7), default='#4A90D9')    # hex
    secondary_color = db.Column(db.String(7), default='#1E3A5F')
    accent_color = db.Column(db.String(7), default='#10B981')
    nav_gradient_from = db.Column(db.String(7), default='#667eea')
    nav_gradient_to = db.Column(db.String(7), default='#764ba2')
    logo_url = db.Column(db.String(500), default='')
    favicon_url = db.Column(db.String(500), default='')

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    brand = db.relationship('Brand', backref=db.backref('theme', uselist=False, cascade='all, delete-orphan'))

    def to_dict(self) -> Dict[str, Any]:
        return {
            'primary_color': self.primary_color,
            'secondary_color': self.secondary_color,
            'accent_color': self.accent_color,
            'nav_gradient_from': self.nav_gradient_from,
            'nav_gradient_to': self.nav_gradient_to,
            'logo_url': self.logo_url,
            'favicon_url': self.favicon_url,
        }


class Brand(db.Model):
    """Represents a brand managed in the system"""
    __tablename__ = 'brands'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), unique=True, nullable=False, index=True)  # buildly, foundry, openbuild, etc.
    display_name = db.Column(db.String(255), nullable=False)  # Buildly, Foundry, OpenBuild, etc.
    description = db.Column(db.Text, default='')
    logo_url = db.Column(db.String(500), default='')
    website_url = db.Column(db.String(500), default='')
    is_active = db.Column(db.Boolean, default=True, index=True)
    is_template = db.Column(db.Boolean, default=False)  # Template brands used for new brands
    
    # Relationships
    email_configs = db.relationship('BrandEmailConfig', backref='brand', lazy='dynamic', cascade='all, delete-orphan')
    settings = db.relationship('BrandSettings', backref='brand', uselist=False, cascade='all, delete-orphan')
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self) -> str:
        return f'<Brand {self.name}>'
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert brand to dictionary"""
        return {
            'id': self.id,
            'name': self.name,
            'display_name': self.display_name,
            'description': self.description,
            'logo_url': self.logo_url,
            'website_url': self.website_url,
            'is_active': self.is_active,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat(),
            'email_configs_count': self.email_configs.count(),
        }


class BrandEmailConfig(db.Model):
    """Email configuration for a specific brand and provider"""
    __tablename__ = 'brand_email_configs'
    
    id = db.Column(db.Integer, primary_key=True)
    brand_id = db.Column(db.Integer, db.ForeignKey('brands.id'), nullable=False, index=True)
    
    # Email provider: brevo, mailersend, sendgrid, mailgun
    provider = db.Column(db.String(50), nullable=False, default='brevo', index=True)
    
    # API credentials (encrypted in production)
    api_key = db.Column(db.String(1024), nullable=False)
    api_token = db.Column(db.String(1024), default='')  # Alternative for some providers
    
    # SMTP Configuration (if needed)
    smtp_host = db.Column(db.String(255), default='')
    smtp_port = db.Column(db.Integer, default=587)
    smtp_user = db.Column(db.String(255), default='')
    smtp_password = db.Column(db.String(1024), default='')
    
    # From email and name for this brand/provider combo
    from_email = db.Column(db.String(255), nullable=False)
    from_name = db.Column(db.String(255), default='')
    
    # Reply-to configuration
    reply_to_email = db.Column(db.String(255), default='')
    reply_to_name = db.Column(db.String(255), default='')
    
    # Contact lists / Segments (JSON format)
    contact_lists = db.Column(db.Text, default='{}')  # JSON
    
    # Features and limits
    is_primary = db.Column(db.Boolean, default=False)  # Primary provider for this brand
    max_send_per_day = db.Column(db.Integer, default=10000)
    rate_limit_per_minute = db.Column(db.Integer, default=100)
    
    # Status tracking
    is_verified = db.Column(db.Boolean, default=False)
    last_verified_at = db.Column(db.DateTime, nullable=True)
    verification_error = db.Column(db.Text, default='')
    
    # Rate limiting tracking
    emails_sent_today = db.Column(db.Integer, default=0)
    last_send_timestamp = db.Column(db.DateTime, nullable=True)
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    __table_args__ = (
        db.UniqueConstraint('brand_id', 'provider', name='unique_brand_provider'),
    )
    
    def __repr__(self) -> str:
        return f'<BrandEmailConfig {self.brand.name}/{self.provider}>'
    
    def get_contact_lists(self) -> List[Dict[str, Any]]:
        """Parse contact lists from JSON"""
        try:
            return json.loads(self.contact_lists) if self.contact_lists else []
        except (json.JSONDecodeError, TypeError):
            return []
    
    def set_contact_lists(self, lists: List[Dict[str, Any]]) -> None:
        """Store contact lists as JSON"""
        self.contact_lists = json.dumps(lists)
    
    def to_dict(self, include_secrets: bool = False) -> Dict[str, Any]:
        """Convert to dictionary"""
        data = {
            'id': self.id,
            'brand_id': self.brand_id,
            'provider': self.provider,
            'from_email': self.from_email,
            'from_name': self.from_name,
            'reply_to_email': self.reply_to_email,
            'reply_to_name': self.reply_to_name,
            'is_primary': self.is_primary,
            'is_verified': self.is_verified,
            'last_verified_at': self.last_verified_at.isoformat() if self.last_verified_at else None,
            'max_send_per_day': self.max_send_per_day,
            'rate_limit_per_minute': self.rate_limit_per_minute,
            'contact_lists': self.get_contact_lists(),
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat(),
        }
        
        if include_secrets:
            data.update({
                'api_key': self.api_key,
                'api_token': self.api_token,
                'smtp_host': self.smtp_host,
                'smtp_port': self.smtp_port,
                'smtp_user': self.smtp_user,
            })
        
        return data


class BrandSettings(db.Model):
    """Brand-specific settings and preferences"""
    __tablename__ = 'brand_settings'
    
    id = db.Column(db.Integer, primary_key=True)
    brand_id = db.Column(db.Integer, db.ForeignKey('brands.id'), nullable=False, unique=True, index=True)
    
    # Email preferences
    daily_email_limit = db.Column(db.Integer, default=5000)
    enable_email_sending = db.Column(db.Boolean, default=True)
    enable_ai_generation = db.Column(db.Boolean, default=True)
    enable_social_posting = db.Column(db.Boolean, default=True)
    
    # Contact list preferences
    auto_subscribe_new_contacts = db.Column(db.Boolean, default=True)
    auto_unsubscribe_invalid = db.Column(db.Boolean, default=True)
    
    # Campaign preferences
    default_campaign_type = db.Column(db.String(50), default='newsletter')  # newsletter, broadcast, drip, etc.
    default_send_time = db.Column(db.String(5), default='09:00')  # HH:MM format
    default_send_day_of_week = db.Column(db.Integer, default=1)  # 0=Monday, 6=Sunday
    
    # Analytics preferences
    enable_analytics_tracking = db.Column(db.Boolean, default=True)
    enable_utm_parameters = db.Column(db.Boolean, default=True)
    
    # Advanced settings (JSON)
    advanced_settings = db.Column(db.Text, default='{}')  # JSON for custom settings
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self) -> str:
        return f'<BrandSettings {self.brand.name}>'
    
    def get_advanced_settings(self) -> Dict[str, Any]:
        """Parse advanced settings from JSON"""
        try:
            return json.loads(self.advanced_settings) if self.advanced_settings else {}
        except (json.JSONDecodeError, TypeError):
            return {}
    
    def set_advanced_settings(self, settings: Dict[str, Any]) -> None:
        """Store advanced settings as JSON"""
        self.advanced_settings = json.dumps(settings)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            'id': self.id,
            'brand_id': self.brand_id,
            'daily_email_limit': self.daily_email_limit,
            'enable_email_sending': self.enable_email_sending,
            'enable_ai_generation': self.enable_ai_generation,
            'enable_social_posting': self.enable_social_posting,
            'auto_subscribe_new_contacts': self.auto_subscribe_new_contacts,
            'auto_unsubscribe_invalid': self.auto_unsubscribe_invalid,
            'default_campaign_type': self.default_campaign_type,
            'default_send_time': self.default_send_time,
            'default_send_day_of_week': self.default_send_day_of_week,
            'enable_analytics_tracking': self.enable_analytics_tracking,
            'enable_utm_parameters': self.enable_utm_parameters,
            'advanced_settings': self.get_advanced_settings(),
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat(),
        }


class SystemConfig(db.Model):
    """System-wide configuration settings"""
    __tablename__ = 'system_configs'
    
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(255), unique=True, nullable=False, index=True)
    value = db.Column(db.Text, nullable=False)
    description = db.Column(db.Text, default='')
    is_secret = db.Column(db.Boolean, default=False)  # If true, value is encrypted
    category = db.Column(db.String(100), default='general', index=True)  # ai, analytics, social, email, etc.
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    updated_by = db.Column(db.String(255), default='system')
    
    def __repr__(self) -> str:
        return f'<SystemConfig {self.key}>'
    
    def to_dict(self, include_secrets: bool = False) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            'id': self.id,
            'key': self.key,
            'value': '***' if (self.is_secret and not include_secrets) else self.value,
            'description': self.description,
            'is_secret': self.is_secret,
            'category': self.category,
            'updated_at': self.updated_at.isoformat(),
            'updated_by': self.updated_by,
        }


class BrandAPICredential(db.Model):
    """API credentials for external services (Twitter, Google Analytics, etc.)"""
    __tablename__ = 'brand_api_credentials'
    
    id = db.Column(db.Integer, primary_key=True)
    brand_id = db.Column(db.Integer, db.ForeignKey('brands.id'), nullable=False, index=True)
    
    service = db.Column(db.String(100), nullable=False, index=True)  # twitter, google_analytics, youtube, etc.
    credential_type = db.Column(db.String(50), nullable=False)  # api_key, oauth, bearer_token, etc.
    
    # Flexible credential storage (JSON for complex auth)
    credentials = db.Column(db.Text, nullable=False)  # Encrypted JSON with all credential fields
    
    # OAuth specific fields
    access_token = db.Column(db.String(1024), default='')
    refresh_token = db.Column(db.String(1024), default='')
    token_expires_at = db.Column(db.DateTime, nullable=True)
    
    # Service specific settings
    service_settings = db.Column(db.Text, default='{}')  # JSON for service-specific config
    
    is_active = db.Column(db.Boolean, default=True)
    is_verified = db.Column(db.Boolean, default=False)
    last_verified_at = db.Column(db.DateTime, nullable=True)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    __table_args__ = (
        db.UniqueConstraint('brand_id', 'service', name='unique_brand_service_credential'),
    )
    
    def __repr__(self) -> str:
        return f'<BrandAPICredential {self.brand_id}/{self.service}>'
    
    def get_credentials(self) -> Dict[str, Any]:
        """Parse credentials from JSON"""
        try:
            return json.loads(self.credentials) if self.credentials else {}
        except (json.JSONDecodeError, TypeError):
            return {}
    
    def set_credentials(self, creds: Dict[str, Any]) -> None:
        """Store credentials as JSON (should be encrypted in production)"""
        self.credentials = json.dumps(creds)
    
    def get_service_settings(self) -> Dict[str, Any]:
        """Parse service settings from JSON"""
        try:
            return json.loads(self.service_settings) if self.service_settings else {}
        except (json.JSONDecodeError, TypeError):
            return {}
    
    def set_service_settings(self, settings: Dict[str, Any]) -> None:
        """Store service settings as JSON"""
        self.service_settings = json.dumps(settings)
    
    def to_dict(self, include_secrets: bool = False) -> Dict[str, Any]:
        """Convert to dictionary"""
        data = {
            'id': self.id,
            'brand_id': self.brand_id,
            'service': self.service,
            'credential_type': self.credential_type,
            'is_active': self.is_active,
            'is_verified': self.is_verified,
            'last_verified_at': self.last_verified_at.isoformat() if self.last_verified_at else None,
            'service_settings': self.get_service_settings(),
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat(),
        }
        
        if include_secrets:
            data.update({
                'credentials': self.get_credentials(),
                'access_token': self.access_token,
                'refresh_token': self.refresh_token,
            })
        
        return data


class APICredentialLog(db.Model):
    """Audit log for API credential access and changes"""
    __tablename__ = 'api_credential_logs'
    
    id = db.Column(db.Integer, primary_key=True)
    brand_id = db.Column(db.Integer, db.ForeignKey('brands.id'), nullable=False, index=True)
    email_config_id = db.Column(db.Integer, db.ForeignKey('brand_email_configs.id'), nullable=True)
    api_credential_id = db.Column(db.Integer, db.ForeignKey('brand_api_credentials.id'), nullable=True)
    system_config_id = db.Column(db.Integer, db.ForeignKey('system_configs.id'), nullable=True)
    
    action = db.Column(db.String(50), nullable=False)  # created, updated, accessed, tested, rotated, deleted
    action_by = db.Column(db.String(255), default='system')  # User email or 'system'
    details = db.Column(db.Text, default='')  # Additional details as JSON
    
    ip_address = db.Column(db.String(45), default='')  # IPv4 or IPv6
    user_agent = db.Column(db.Text, default='')
    
    success = db.Column(db.Boolean, default=True)
    error_message = db.Column(db.Text, default='')
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    
    def __repr__(self) -> str:
        return f'<APICredentialLog {self.brand_id}/{self.action}>'
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            'id': self.id,
            'brand_id': self.brand_id,
            'email_config_id': self.email_config_id,
            'api_credential_id': self.api_credential_id,
            'system_config_id': self.system_config_id,
            'action': self.action,
            'action_by': self.action_by,
            'success': self.success,
            'error_message': self.error_message,
            'created_at': self.created_at.isoformat(),
        }


# ============================================================================
# SCHEDULED TASKS MODEL
# ============================================================================

class ScheduledTask(db.Model):
    """User-managed scheduled automation tasks stored in the database"""
    __tablename__ = 'scheduled_tasks'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text, default='')
    task_type = db.Column(db.String(100), nullable=False, index=True)  # outreach, discovery, analytics, social, report
    brand_id = db.Column(db.Integer, db.ForeignKey('brands.id'), nullable=True, index=True)

    # Cron schedule (e.g. "0 9 * * 1" = Monday 9am)
    cron_expression = db.Column(db.String(100), nullable=False)
    schedule_label = db.Column(db.String(100), default='')  # Human label e.g. "Every Monday at 9am"

    # Task parameters (JSON)
    parameters = db.Column(db.Text, default='{}')

    # Status
    is_enabled = db.Column(db.Boolean, default=True, index=True)
    last_run_at = db.Column(db.DateTime, nullable=True)
    next_run_at = db.Column(db.DateTime, nullable=True)
    run_count = db.Column(db.Integer, default=0)
    fail_count = db.Column(db.Integer, default=0)
    last_result = db.Column(db.Text, default='')

    created_by = db.Column(db.String(255), default='system')
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    brand = db.relationship('Brand', backref=db.backref('scheduled_tasks', lazy='dynamic'))

    def get_parameters(self) -> Dict[str, Any]:
        try:
            return json.loads(self.parameters) if self.parameters else {}
        except (json.JSONDecodeError, TypeError):
            return {}

    def set_parameters(self, params: Dict[str, Any]) -> None:
        self.parameters = json.dumps(params)

    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'task_type': self.task_type,
            'brand_id': self.brand_id,
            'brand_name': self.brand.name if self.brand else 'all',
            'brand_display_name': self.brand.display_name if self.brand else 'All Brands',
            'cron_expression': self.cron_expression,
            'schedule_label': self.schedule_label,
            'parameters': self.get_parameters(),
            'is_enabled': self.is_enabled,
            'last_run_at': self.last_run_at.isoformat() if self.last_run_at else None,
            'next_run_at': self.next_run_at.isoformat() if self.next_run_at else None,
            'run_count': self.run_count,
            'fail_count': self.fail_count,
            'last_result': self.last_result,
            'created_by': self.created_by,
            'created_at': self.created_at.isoformat(),
        }


# ============================================================================
# PRESS RELEASE MODEL
# ============================================================================

class PressRelease(db.Model):
    """Press releases created and managed in the system"""
    __tablename__ = 'press_releases'

    id = db.Column(db.Integer, primary_key=True)
    brand_id = db.Column(db.Integer, db.ForeignKey('brands.id'), nullable=False, index=True)

    title = db.Column(db.String(500), nullable=False)
    headline = db.Column(db.String(500), default='')
    subheadline = db.Column(db.String(500), default='')
    body = db.Column(db.Text, default='')
    boilerplate = db.Column(db.Text, default='')  # Standard "About" section
    contact_info = db.Column(db.Text, default='')  # JSON

    # News event context
    news_event = db.Column(db.Text, default='')  # User's description of the news
    target_scope = db.Column(db.String(50), default='all')  # local, national, international, all

    # Status
    status = db.Column(db.String(50), default='draft', index=True)  # draft, review, approved, distributed
    distributed_at = db.Column(db.DateTime, nullable=True)
    distribution_targets = db.Column(db.Text, default='[]')  # JSON list of press contact IDs

    created_by = db.Column(db.String(255), default='system')
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    brand = db.relationship('Brand', backref=db.backref('press_releases', lazy='dynamic'))

    def get_contact_info(self) -> Dict[str, Any]:
        try:
            return json.loads(self.contact_info) if self.contact_info else {}
        except (json.JSONDecodeError, TypeError):
            return {}

    def get_distribution_targets(self) -> List:
        try:
            return json.loads(self.distribution_targets) if self.distribution_targets else []
        except (json.JSONDecodeError, TypeError):
            return []

    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'brand_id': self.brand_id,
            'brand_name': self.brand.name if self.brand else '',
            'brand_display_name': self.brand.display_name if self.brand else '',
            'title': self.title,
            'headline': self.headline,
            'subheadline': self.subheadline,
            'body': self.body,
            'boilerplate': self.boilerplate,
            'contact_info': self.get_contact_info(),
            'news_event': self.news_event,
            'target_scope': self.target_scope,
            'status': self.status,
            'distributed_at': self.distributed_at.isoformat() if self.distributed_at else None,
            'distribution_targets': self.get_distribution_targets(),
            'created_by': self.created_by,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat(),
        }


# ============================================================================
# PRESS CONTACT MODEL
# ============================================================================

class PressContact(db.Model):
    """Press/media contacts for distribution"""
    __tablename__ = 'press_contacts'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    outlet = db.Column(db.String(255), default='')  # Publication/outlet name
    email = db.Column(db.String(255), nullable=False, index=True)
    phone = db.Column(db.String(50), default='')
    title = db.Column(db.String(255), default='')  # Job title at outlet
    beat = db.Column(db.String(255), default='')  # Coverage area (tech, business, etc.)
    scope = db.Column(db.String(50), default='national', index=True)  # local, national, international
    region = db.Column(db.String(255), default='')  # Geographic region for local contacts

    website = db.Column(db.String(500), default='')
    twitter_handle = db.Column(db.String(100), default='')
    notes = db.Column(db.Text, default='')

    is_active = db.Column(db.Boolean, default=True, index=True)
    last_contacted_at = db.Column(db.DateTime, nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'name': self.name,
            'outlet': self.outlet,
            'email': self.email,
            'phone': self.phone,
            'title': self.title,
            'beat': self.beat,
            'scope': self.scope,
            'region': self.region,
            'website': self.website,
            'twitter_handle': self.twitter_handle,
            'notes': self.notes,
            'is_active': self.is_active,
            'last_contacted_at': self.last_contacted_at.isoformat() if self.last_contacted_at else None,
        }

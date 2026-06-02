"""
Marketing Calendar Models for multi-brand campaign management.
Supports both automated and manually-assigned marketing tasks.
"""

from datetime import datetime, timedelta
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import JSON, Enum
import enum
from dashboard.models import db


class TaskStatus(enum.Enum):
    """Task status enumeration"""
    DRAFT = "draft"
    SCHEDULED = "scheduled"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TaskPriority(enum.Enum):
    """Task priority enumeration"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class TaskType(enum.Enum):
    """Type of marketing task"""
    SOCIAL_POST = "social_post"
    ARTICLE = "article"
    VIDEO = "video"
    EMAIL = "email"
    PAID_AD = "paid_ad"
    PRESS_RELEASE = "press_release"
    PODCAST = "podcast"
    WEBINAR = "webinar"
    EVENT = "event"
    CUSTOM = "custom"


class PlatformType(enum.Enum):
    """Social media and marketing platforms"""
    REDDIT = "reddit"
    HACKER_NEWS = "hacker_news"
    INDIE_HACKERS = "indie_hackers"
    LINKEDIN = "linkedin"
    DEVTO = "devto"
    TWITTER = "twitter"
    YOUTUBE = "youtube"
    TIKTOK = "tiktok"
    EMAIL = "email"
    WEBSITE = "website"
    PRODUCT_HUNT = "product_hunt"


class MarketingCalendar(db.Model):
    """Main marketing campaign calendar"""
    __tablename__ = 'marketing_calendar'
    
    id = db.Column(db.Integer, primary_key=True)
    brand_name = db.Column(db.String(255), db.ForeignKey('brands.name'), nullable=False)
    campaign_name = db.Column(db.String(255), nullable=False)
    campaign_slug = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text)
    goal = db.Column(db.String(255))
    target_metric = db.Column(db.String(255))  # e.g., "1000+ signups"
    start_date = db.Column(db.DateTime, nullable=False)
    end_date = db.Column(db.DateTime, nullable=False)
    budget = db.Column(db.Float, default=0)
    currency = db.Column(db.String(10), default='USD')
    status = db.Column(db.String(50), default='draft')
    owner = db.Column(db.String(255))  # Person responsible
    notes = db.Column(db.Text)
    meta_data = db.Column(JSON, default={})
    
    # Relationships
    brand = db.relationship('Brand', backref='marketing_campaigns')
    tasks = db.relationship('MarketingTask', cascade='all, delete-orphan',
                            overlaps='calendar,calendar_tasks')
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self):
        return f"<MarketingCalendar {self.campaign_name} ({self.brand_name})>"


class MarketingTask(db.Model):
    """Individual marketing tasks within a campaign"""
    __tablename__ = 'marketing_task'
    
    id = db.Column(db.Integer, primary_key=True)
    calendar_id = db.Column(db.Integer, db.ForeignKey('marketing_calendar.id'), nullable=False)
    brand_name = db.Column(db.String(255), db.ForeignKey('brands.name'), nullable=False)
    
    # Task basics
    task_name = db.Column(db.String(255), nullable=False)
    task_slug = db.Column(db.String(255))
    description = db.Column(db.Text)
    task_type = db.Column(db.Enum(TaskType), default=TaskType.SOCIAL_POST)
    platform = db.Column(db.Enum(PlatformType), nullable=False)
    
    # Scheduling
    scheduled_date = db.Column(db.DateTime, nullable=False)
    scheduled_time = db.Column(db.Time)  # HH:MM format
    duration_minutes = db.Column(db.Integer)  # Est. time to complete
    
    # Assignment & Status
    assigned_to = db.Column(db.String(255))  # Email or user ID
    status = db.Column(db.Enum(TaskStatus), default=TaskStatus.DRAFT)
    priority = db.Column(db.Enum(TaskPriority), default=TaskPriority.MEDIUM)
    is_automated = db.Column(db.Boolean, default=False)
    
    # Content
    title = db.Column(db.String(500))
    body = db.Column(db.Text)
    meta_data = db.Column(JSON, default={})  # Platform-specific settings
    
    # Execution tracking
    completed_at = db.Column(db.DateTime)
    executed_by = db.Column(db.String(255))
    execution_log = db.Column(db.Text)
    error_message = db.Column(db.Text)
    
    # Performance metrics
    performance_metrics = db.Column(JSON, default={})  # Views, clicks, engagement, etc.
    
    # Relationships
    brand = db.relationship('Brand', backref='marketing_tasks')
    calendar = db.relationship('MarketingCalendar', backref='calendar_tasks',
                               overlaps='tasks')
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self):
        return f"<MarketingTask {self.task_name} ({self.platform.value})>"


class ContentTemplate(db.Model):
    """Reusable content templates for campaigns"""
    __tablename__ = 'content_template'
    
    id = db.Column(db.Integer, primary_key=True)
    brand_name = db.Column(db.String(255), db.ForeignKey('brands.name'), nullable=False)
    
    template_name = db.Column(db.String(255), nullable=False)
    template_slug = db.Column(db.String(255), nullable=False)
    category = db.Column(db.String(100))  # e.g., "product_launch", "thought_leadership"
    platform = db.Column(db.Enum(PlatformType), nullable=False)
    task_type = db.Column(db.Enum(TaskType), nullable=False)
    
    # Template content
    title_template = db.Column(db.String(500))
    body_template = db.Column(db.Text)
    prompt_instructions = db.Column(db.Text)
    example_output = db.Column(db.Text)
    required_assets = db.Column(JSON, default=list)
    cta = db.Column(db.String(255))  # Call-to-action
    hashtags = db.Column(db.String(500))
    suggested_cta = db.Column(db.String(255))
    suggested_hashtags = db.Column(db.String(500))
    variables = db.Column(JSON, default={})  # {{variable}} placeholders
    
    # Meta
    description = db.Column(db.Text)
    usage_count = db.Column(db.Integer, default=0)
    performance_metrics = db.Column(JSON, default={})
    
    # Relationships
    brand = db.relationship('Brand', backref='content_templates')
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self):
        return f"<ContentTemplate {self.template_name} ({self.platform.value})>"


class MarketingWeekly(db.Model):
    """Weekly marketing performance tracking and rhythm"""
    __tablename__ = 'marketing_weekly'
    
    id = db.Column(db.Integer, primary_key=True)
    brand_name = db.Column(db.String(255), db.ForeignKey('brands.name'), nullable=False)
    calendar_id = db.Column(db.Integer, db.ForeignKey('marketing_calendar.id'))
    
    week_start = db.Column(db.DateTime, nullable=False)
    week_end = db.Column(db.DateTime, nullable=False)
    
    # Weekly metrics
    posts_published = db.Column(db.Integer, default=0)
    total_reach = db.Column(db.Integer, default=0)
    total_engagement = db.Column(db.Integer, default=0)
    total_clicks = db.Column(db.Integer, default=0)
    total_conversions = db.Column(db.Integer, default=0)
    signups = db.Column(db.Integer, default=0)
    
    # Performance by platform
    platform_metrics = db.Column(JSON, default={})  # {platform: {reach, engagement, etc}}
    
    # Notes and insights
    notes = db.Column(db.Text)
    top_performing_post = db.Column(db.String(255))
    insights = db.Column(db.Text)
    
    # Relationships
    brand = db.relationship('Brand', backref='marketing_weekly_reports')
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self):
        return f"<MarketingWeekly {self.brand_name} Week {self.week_start.strftime('%Y-%m-%d')}>"


class ContentPillar(db.Model):
    """Reusable content categories for planning consistency."""
    __tablename__ = 'content_pillar'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text)
    examples = db.Column(db.Text)
    brand_name = db.Column(db.String(255), db.ForeignKey('brands.name'), nullable=True)
    is_active = db.Column(db.Boolean, default=True)

    brand = db.relationship('Brand', backref='content_pillars')

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ContentIdea(db.Model):
    """Channel-agnostic idea before platform-specific drafting."""
    __tablename__ = 'content_idea'

    id = db.Column(db.Integer, primary_key=True)
    campaign_id = db.Column(db.Integer, db.ForeignKey('marketing_calendar.id'), nullable=False)
    title = db.Column(db.String(255), nullable=False)
    pillar_id = db.Column(db.Integer, db.ForeignKey('content_pillar.id'), nullable=True)
    audience = db.Column(db.String(255))
    message = db.Column(db.Text)
    cta = db.Column(db.String(255))
    source_notes = db.Column(db.Text)
    status = db.Column(db.String(50), default='idea', index=True)
    owner = db.Column(db.String(255))
    due_date = db.Column(db.DateTime)

    campaign = db.relationship('MarketingCalendar', backref='content_ideas')
    pillar = db.relationship('ContentPillar', backref='content_ideas')

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class SocialPostDraft(db.Model):
    """Platform-specific draft linked to a content idea."""
    __tablename__ = 'social_post_draft'

    id = db.Column(db.Integer, primary_key=True)
    content_idea_id = db.Column(db.Integer, db.ForeignKey('content_idea.id'), nullable=False)
    platform = db.Column(db.String(100), nullable=False, index=True)
    post_format = db.Column(db.String(100), nullable=False)
    caption_body = db.Column(db.Text)
    hashtags = db.Column(db.Text)
    cta = db.Column(db.String(255))
    link = db.Column(db.String(500))
    media_asset = db.Column(db.String(500))
    status = db.Column(db.String(50), default='draft', index=True)
    scheduled_datetime = db.Column(db.DateTime)
    external_scheduler_name = db.Column(db.String(100))
    external_scheduler_url = db.Column(db.String(500))
    posted_url = db.Column(db.String(500))
    notes = db.Column(db.Text)
    draft_origin = db.Column(db.String(50), default='human')  # human, ai_draft

    content_idea = db.relationship('ContentIdea', backref='social_post_drafts')

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ManualTask(db.Model):
    """Explicit human task for account setup, approvals, posting, and checks."""
    __tablename__ = 'manual_task'

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text)
    related_brand_name = db.Column(db.String(255), db.ForeignKey('brands.name'), nullable=True)
    related_campaign_id = db.Column(db.Integer, db.ForeignKey('marketing_calendar.id'), nullable=True)
    related_content_idea_id = db.Column(db.Integer, db.ForeignKey('content_idea.id'), nullable=True)
    related_social_post_id = db.Column(db.Integer, db.ForeignKey('social_post_draft.id'), nullable=True)
    platform = db.Column(db.String(100), nullable=True)
    task_type = db.Column(db.String(100), default='manual_posting', index=True)
    checklist_steps = db.Column(JSON, default=list)
    owner = db.Column(db.String(255))
    status = db.Column(db.String(50), default='not_started', index=True)
    due_date = db.Column(db.DateTime)
    completed_date = db.Column(db.DateTime)
    notes = db.Column(db.Text)
    reference_url = db.Column(db.String(500))

    related_brand = db.relationship('Brand', backref='manual_tasks')
    related_campaign = db.relationship('MarketingCalendar', backref='manual_tasks')
    related_content_idea = db.relationship('ContentIdea', backref='manual_tasks')
    related_social_post = db.relationship('SocialPostDraft', backref='manual_tasks')

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Asset(db.Model):
    """Reusable asset metadata and approval tracking."""
    __tablename__ = 'marketing_asset'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    asset_type = db.Column(db.String(100), nullable=False, index=True)
    file_or_url = db.Column(db.String(500), nullable=False)
    brand_name = db.Column(db.String(255), db.ForeignKey('brands.name'), nullable=True)
    usage_notes = db.Column(db.Text)
    alt_text = db.Column(db.Text)
    platform_suitability = db.Column(JSON, default=list)
    status = db.Column(db.String(50), default='draft', index=True)

    brand = db.relationship('Brand', backref='marketing_assets')

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class PerformanceSnapshot(db.Model):
    """Manual or imported post-performance check records."""
    __tablename__ = 'performance_snapshot'

    id = db.Column(db.Integer, primary_key=True)
    platform = db.Column(db.String(100), nullable=False, index=True)
    related_social_post_id = db.Column(db.Integer, db.ForeignKey('social_post_draft.id'), nullable=True)
    post_url = db.Column(db.String(500), nullable=False)
    date_checked = db.Column(db.DateTime, nullable=False, index=True)
    impressions_views = db.Column(db.Integer, default=0)
    likes = db.Column(db.Integer, default=0)
    comments = db.Column(db.Integer, default=0)
    shares_reposts = db.Column(db.Integer, default=0)
    saves = db.Column(db.Integer, default=0)
    clicks = db.Column(db.Integer, default=0)
    follows_subscribers = db.Column(db.Integer, default=0)
    notes = db.Column(db.Text)

    related_social_post = db.relationship('SocialPostDraft', backref='performance_snapshots')

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

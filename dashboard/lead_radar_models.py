"""
Lead Radar models for human-in-the-loop lead research and regional intelligence.

This module is intentionally configurable and multi-tenant:
- brand_name links to brands.name, but brands/regions/sources/rules are user-configurable
- Buildly-specific values are seeded as defaults only (optional)
- no automation path in this module can send outreach automatically
"""

from datetime import datetime
from dashboard.models import db


class RegionProfile(db.Model):
    __tablename__ = 'region_profiles'

    id = db.Column(db.Integer, primary_key=True)
    brand_name = db.Column(db.String(255), db.ForeignKey('brands.name'), nullable=False, index=True)
    name = db.Column(db.String(255), nullable=False)
    slug = db.Column(db.String(255), nullable=False, index=True)
    owner = db.Column(db.String(255), default='')
    countries = db.Column(db.JSON, default=list)
    timezone_notes = db.Column(db.Text, default='')
    primary_offer = db.Column(db.String(255), default='')
    entry_price_min = db.Column(db.Float, default=0)
    entry_price_max = db.Column(db.Float, default=0)
    currency = db.Column(db.String(10), default='USD')
    target_segments = db.Column(db.JSON, default=list)
    preferred_channels = db.Column(db.JSON, default=list)
    outreach_tone = db.Column(db.Text, default='')
    local_notes = db.Column(db.Text, default='')
    is_active = db.Column(db.Boolean, default=True, index=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint('brand_name', 'slug', name='uq_region_brand_slug'),
    )


class Lead(db.Model):
    __tablename__ = 'leads'

    id = db.Column(db.Integer, primary_key=True)
    brand_name = db.Column(db.String(255), db.ForeignKey('brands.name'), nullable=False, index=True)
    region_id = db.Column(db.Integer, db.ForeignKey('region_profiles.id'), nullable=True, index=True)
    calendar_id = db.Column(db.Integer, db.ForeignKey('marketing_calendar.id'), nullable=True, index=True)
    owner = db.Column(db.String(255), default='')

    first_name = db.Column(db.String(255), default='')
    last_name = db.Column(db.String(255), default='')
    title = db.Column(db.String(255), default='')
    company_name = db.Column(db.String(255), nullable=False, index=True)
    company_url = db.Column(db.String(500), default='')
    linkedin_url = db.Column(db.String(500), default='', index=True)
    email = db.Column(db.String(255), default='', index=True)
    country = db.Column(db.String(255), default='')
    city = db.Column(db.String(255), default='')
    company_stage = db.Column(db.String(100), default='')
    segment = db.Column(db.String(100), default='')
    source = db.Column(db.String(255), default='')

    pain_signals = db.Column(db.JSON, default=list)
    fit_score = db.Column(db.Integer, default=0, index=True)
    score_breakdown = db.Column(db.JSON, default=list)
    priority = db.Column(db.String(20), default='low', index=True)
    status = db.Column(db.String(50), default='researched', index=True)
    consent_status = db.Column(db.String(50), default='unknown')
    compliance_notes = db.Column(db.Text, default='')
    notes = db.Column(db.Text, default='')

    is_do_not_contact = db.Column(db.Boolean, default=False, index=True)
    next_action_date = db.Column(db.DateTime, nullable=True, index=True)
    archived_at = db.Column(db.DateTime, nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        db.Index('idx_lead_brand_region_status', 'brand_name', 'region_id', 'status'),
    )


class LeadActivity(db.Model):
    __tablename__ = 'lead_activities'

    id = db.Column(db.Integer, primary_key=True)
    lead_id = db.Column(db.Integer, db.ForeignKey('leads.id'), nullable=False, index=True)
    activity_type = db.Column(db.String(50), default='note', index=True)
    channel = db.Column(db.String(50), default='other', index=True)
    subject = db.Column(db.String(500), default='')
    body = db.Column(db.Text, default='')
    status = db.Column(db.String(50), default='draft', index=True)
    completed_by = db.Column(db.String(255), default='')
    completed_at = db.Column(db.DateTime, nullable=True)
    next_action_date = db.Column(db.DateTime, nullable=True)
    notes = db.Column(db.Text, default='')

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class OutreachTemplate(db.Model):
    __tablename__ = 'outreach_templates'

    id = db.Column(db.Integer, primary_key=True)
    brand_name = db.Column(db.String(255), db.ForeignKey('brands.name'), nullable=False, index=True)
    region_id = db.Column(db.Integer, db.ForeignKey('region_profiles.id'), nullable=True, index=True)
    segment = db.Column(db.String(100), default='', index=True)
    channel = db.Column(db.String(50), default='email', index=True)
    template_name = db.Column(db.String(255), nullable=False)
    subject_template = db.Column(db.String(500), default='')
    body_template = db.Column(db.Text, default='')
    cta = db.Column(db.String(255), default='')
    variables = db.Column(db.JSON, default=list)
    is_active = db.Column(db.Boolean, default=True, index=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class LeadSource(db.Model):
    __tablename__ = 'lead_sources'

    id = db.Column(db.Integer, primary_key=True)
    brand_name = db.Column(db.String(255), db.ForeignKey('brands.name'), nullable=False, index=True)
    region_id = db.Column(db.Integer, db.ForeignKey('region_profiles.id'), nullable=True, index=True)
    name = db.Column(db.String(255), nullable=False)
    source_type = db.Column(db.String(50), default='manual', index=True)
    url = db.Column(db.String(1000), default='')

    query_keywords = db.Column(db.JSON, default=list)
    negative_keywords = db.Column(db.JSON, default=list)
    region_filters = db.Column(db.JSON, default=list)
    segment_filters = db.Column(db.JSON, default=list)

    run_frequency = db.Column(db.String(20), default='manual')
    is_active = db.Column(db.Boolean, default=True, index=True)
    last_run_at = db.Column(db.DateTime, nullable=True)
    next_run_at = db.Column(db.DateTime, nullable=True)
    owner = db.Column(db.String(255), default='')
    notes = db.Column(db.Text, default='')
    compliance_notes = db.Column(db.Text, default='')

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ResearchJob(db.Model):
    __tablename__ = 'research_jobs'

    id = db.Column(db.Integer, primary_key=True)
    lead_source_id = db.Column(db.Integer, db.ForeignKey('lead_sources.id'), nullable=False, index=True)
    status = db.Column(db.String(20), default='queued', index=True)
    started_at = db.Column(db.DateTime, nullable=True)
    completed_at = db.Column(db.DateTime, nullable=True)
    results_count = db.Column(db.Integer, default=0)
    candidates_created = db.Column(db.Integer, default=0)
    error_message = db.Column(db.Text, default='')
    run_log = db.Column(db.Text, default='')

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class LeadCandidate(db.Model):
    __tablename__ = 'lead_candidates'

    id = db.Column(db.Integer, primary_key=True)
    brand_name = db.Column(db.String(255), db.ForeignKey('brands.name'), nullable=False, index=True)
    lead_source_id = db.Column(db.Integer, db.ForeignKey('lead_sources.id'), nullable=False, index=True)
    research_job_id = db.Column(db.Integer, db.ForeignKey('research_jobs.id'), nullable=True, index=True)
    region_id = db.Column(db.Integer, db.ForeignKey('region_profiles.id'), nullable=True, index=True)

    raw_name = db.Column(db.String(255), default='')
    raw_company = db.Column(db.String(255), default='', index=True)
    raw_title = db.Column(db.String(255), default='')
    raw_url = db.Column(db.String(1000), default='', index=True)
    raw_text = db.Column(db.Text, default='')
    signal_summary = db.Column(db.Text, default='')
    detected_keywords = db.Column(db.JSON, default=list)
    detected_region = db.Column(db.String(255), default='')
    detected_segment = db.Column(db.String(255), default='')
    confidence_score = db.Column(db.Integer, default=0)
    fit_score = db.Column(db.Integer, default=0, index=True)
    score_breakdown = db.Column(db.JSON, default=list)
    status = db.Column(db.String(30), default='new', index=True)
    reviewer = db.Column(db.String(255), default='')
    review_notes = db.Column(db.Text, default='')
    is_do_not_contact = db.Column(db.Boolean, default=False, index=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ScoringRule(db.Model):
    __tablename__ = 'scoring_rules'

    id = db.Column(db.Integer, primary_key=True)
    brand_name = db.Column(db.String(255), db.ForeignKey('brands.name'), nullable=False, index=True)
    region_id = db.Column(db.Integer, db.ForeignKey('region_profiles.id'), nullable=True, index=True)
    name = db.Column(db.String(255), nullable=False)
    rule_type = db.Column(db.String(50), nullable=False, index=True)
    match_value = db.Column(db.String(500), default='')
    score_delta = db.Column(db.Integer, default=0)
    is_active = db.Column(db.Boolean, default=True, index=True)
    notes = db.Column(db.Text, default='')

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class LeadFeedback(db.Model):
    __tablename__ = 'lead_feedback'

    id = db.Column(db.Integer, primary_key=True)
    lead_id = db.Column(db.Integer, db.ForeignKey('leads.id'), nullable=True, index=True)
    lead_candidate_id = db.Column(db.Integer, db.ForeignKey('lead_candidates.id'), nullable=True, index=True)
    user = db.Column(db.String(255), default='')
    feedback_type = db.Column(db.String(50), nullable=False, index=True)
    feedback_notes = db.Column(db.Text, default='')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class SourcePerformance(db.Model):
    __tablename__ = 'source_performance'

    id = db.Column(db.Integer, primary_key=True)
    brand_name = db.Column(db.String(255), db.ForeignKey('brands.name'), nullable=False, index=True)
    lead_source_id = db.Column(db.Integer, db.ForeignKey('lead_sources.id'), nullable=False, index=True)
    region_id = db.Column(db.Integer, db.ForeignKey('region_profiles.id'), nullable=True, index=True)
    period_start = db.Column(db.DateTime, nullable=False, index=True)
    period_end = db.Column(db.DateTime, nullable=False, index=True)

    candidates_found = db.Column(db.Integer, default=0)
    leads_approved = db.Column(db.Integer, default=0)
    leads_rejected = db.Column(db.Integer, default=0)
    outreach_tasks_created = db.Column(db.Integer, default=0)
    replies = db.Column(db.Integer, default=0)
    calls_booked = db.Column(db.Integer, default=0)
    proposals_sent = db.Column(db.Integer, default=0)
    won = db.Column(db.Integer, default=0)
    lost = db.Column(db.Integer, default=0)
    quality_score = db.Column(db.Float, default=0)
    notes = db.Column(db.Text, default='')

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class LeadRadarSetting(db.Model):
    __tablename__ = 'lead_radar_settings'

    id = db.Column(db.Integer, primary_key=True)
    brand_name = db.Column(db.String(255), db.ForeignKey('brands.name'), nullable=False, unique=True, index=True)
    settings_json = db.Column(db.JSON, default=dict)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

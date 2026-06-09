"""Database models for The Index custom module."""

from datetime import datetime
from dashboard.models import db


class IndexSubmission(db.Model):
    """Stores a raw submission and normalized/AI-enriched artifacts."""

    __tablename__ = "the_index_submissions"

    id = db.Column(db.Integer, primary_key=True)
    external_id = db.Column(db.String(255), index=True, default="")
    source = db.Column(db.String(100), nullable=False, default="json_api", index=True)
    submission_type = db.Column(db.String(100), nullable=False, default="general", index=True)

    submitter_name = db.Column(db.String(255), default="")
    submitter_email = db.Column(db.String(255), default="", index=True)
    organization = db.Column(db.String(255), default="")
    title = db.Column(db.String(255), default="")

    status = db.Column(db.String(50), nullable=False, default="received", index=True)
    priority = db.Column(db.String(20), nullable=False, default="normal", index=True)

    raw_payload = db.Column(db.JSON, default=dict)
    normalized_payload = db.Column(db.JSON, default=dict)
    ai_analysis = db.Column(db.JSON, default=dict)
    ai_summary = db.Column(db.Text, default="")
    report_flags = db.Column(db.JSON, default=list)

    received_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    analyzed_at = db.Column(db.DateTime, nullable=True, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class IndexReportSnapshot(db.Model):
    """Optional persisted snapshots of generated reports."""

    __tablename__ = "the_index_report_snapshots"

    id = db.Column(db.Integer, primary_key=True)
    report_type = db.Column(db.String(100), nullable=False, index=True)
    window_start = db.Column(db.DateTime, nullable=True, index=True)
    window_end = db.Column(db.DateTime, nullable=True, index=True)
    report_data = db.Column(db.JSON, default=dict)
    generated_by = db.Column(db.String(255), default="system")
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)


class IndexSurveySubmission(db.Model):
    """Stores firstcityfoundry.com registration/index submissions."""

    __tablename__ = "the_index_survey_submissions"

    id = db.Column(db.String(64), primary_key=True)
    submitted_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)
    source = db.Column(db.String(255), default="", index=True)
    submitted_page = db.Column(db.String(500), default="")
    contact_email = db.Column(db.String(255), default="", index=True)
    company_name = db.Column(db.String(255), default="")

    answers = db.Column(db.JSON, default=dict)
    reporting = db.Column(db.JSON, default=dict)
    request_meta = db.Column(db.JSON, default=dict)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

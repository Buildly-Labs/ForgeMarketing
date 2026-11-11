"""Persistence for the Quarterly Room problem/solution matching intake."""

from datetime import datetime

from dashboard.models import db


class MatchingIntake(db.Model):
    """One submission to POST /api/matching-intakes.

    Original wording, seat, category, bands, evidence, consent and source are
    stored as submitted. Match eligibility is *derived* at read time (see
    matching.py) so it is never stale and never stored as a score.
    """

    __tablename__ = "quarterly_room_matching_intakes"

    id = db.Column(db.String(64), primary_key=True)
    received_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)
    quarter_label = db.Column(db.String(10), nullable=False, index=True)  # e.g. 2026-Q4

    schema_version = db.Column(db.Integer, nullable=False, default=1)
    intake_type = db.Column(db.String(80), nullable=False)
    seat = db.Column(db.String(30), nullable=False, index=True)

    person_name = db.Column(db.String(255), nullable=False)
    person_email = db.Column(db.String(255), nullable=False, index=True)
    person_city = db.Column(db.String(255), default="")
    company = db.Column(db.String(255), default="")
    role = db.Column(db.String(255), default="")
    company_url = db.Column(db.String(500), default="")
    company_description = db.Column(db.Text, default="")

    revenue_bands = db.Column(db.JSON, default=list)
    people_bands = db.Column(db.JSON, default=list)

    problem_category = db.Column(db.String(40), default="", index=True)
    problem_statement = db.Column(db.Text, default="")  # verbatim, never rewritten
    event_skew = db.Column(db.JSON, default=None)
    problem_details = db.Column(db.JSON, default=dict)

    commitments = db.Column(db.JSON, default=list)
    no_pitch_acknowledged = db.Column(db.Boolean, nullable=False, default=False)
    contact_permission = db.Column(db.String(20), nullable=False, default="no")
    is_hold = db.Column(db.Boolean, nullable=False, default=False, index=True)

    source = db.Column(db.String(255), default="")
    submitted_page = db.Column(db.String(500), default="")
    reporting = db.Column(db.JSON, default=dict)
    raw_payload = db.Column(db.JSON, default=dict)
    request_meta = db.Column(db.JSON, default=dict)  # hashed fingerprint only, no raw IP

    review_status = db.Column(db.String(30), nullable=False, default="received", index=True)
    reviewer_notes = db.Column(db.Text, default="")
    reviewed_at = db.Column(db.DateTime, nullable=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

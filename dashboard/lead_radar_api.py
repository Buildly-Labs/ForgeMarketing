"""Lead Radar API and pages.

Human-in-the-loop regional lead intelligence. No auto-send behavior.
"""

from collections import Counter
from datetime import datetime, timedelta

from flask import Blueprint, jsonify, render_template, request

from dashboard.models import Brand, db
from dashboard.lead_radar_models import (
    Lead,
    LeadActivity,
    LeadCandidate,
    LeadFeedback,
    LeadRadarSetting,
    LeadSource,
    OutreachTemplate,
    ResearchJob,
    RegionProfile,
    ScoringRule,
)
from dashboard.lead_radar_service import (
    ALLOWED_SOURCE_TYPES,
    FEEDBACK_TYPES,
    LEAD_STATUSES,
    calculate_fit_score,
    capture_feedback,
    convert_candidate_to_lead,
    enrich_candidate,
    find_region_for_country,
    generate_draft_for_lead,
    get_dashboard_summary,
    parse_csv_to_leads,
    run_manual_research_job,
    run_source_research_job,
    run_due_source_research_jobs,
    seed_buildly_defaults_if_present,
    seed_sources_for_brand,
    seed_startup_sources_for_brand,
    update_source_performance,
    upsert_followup_task,
    validate_lead_payload,
)


lead_api_bp = Blueprint("lead_api", __name__)


def _dt(value):
    return value.isoformat() if value else None


def _lead_to_dict(lead: Lead):
    return {
        "id": lead.id,
        "brand_name": lead.brand_name,
        "region_id": lead.region_id,
        "calendar_id": lead.calendar_id,
        "owner": lead.owner,
        "first_name": lead.first_name,
        "last_name": lead.last_name,
        "title": lead.title,
        "company_name": lead.company_name,
        "company_url": lead.company_url,
        "linkedin_url": lead.linkedin_url,
        "email": lead.email,
        "country": lead.country,
        "city": lead.city,
        "company_stage": lead.company_stage,
        "segment": lead.segment,
        "source": lead.source,
        "pain_signals": lead.pain_signals or [],
        "fit_score": lead.fit_score,
        "score_breakdown": lead.score_breakdown or [],
        "priority": lead.priority,
        "status": lead.status,
        "consent_status": lead.consent_status,
        "compliance_notes": lead.compliance_notes,
        "notes": lead.notes,
        "next_action_date": _dt(lead.next_action_date),
        "is_do_not_contact": lead.is_do_not_contact,
        "created_at": _dt(lead.created_at),
        "updated_at": _dt(lead.updated_at),
    }


def _region_to_dict(region: RegionProfile):
    return {
        "id": region.id,
        "brand_name": region.brand_name,
        "name": region.name,
        "slug": region.slug,
        "owner": region.owner,
        "countries": region.countries or [],
        "timezone_notes": region.timezone_notes,
        "primary_offer": region.primary_offer,
        "entry_price_min": region.entry_price_min,
        "entry_price_max": region.entry_price_max,
        "currency": region.currency,
        "target_segments": region.target_segments or [],
        "preferred_channels": region.preferred_channels or [],
        "outreach_tone": region.outreach_tone,
        "local_notes": region.local_notes,
        "is_active": region.is_active,
        "created_at": _dt(region.created_at),
        "updated_at": _dt(region.updated_at),
    }


def _activity_to_dict(activity: LeadActivity):
    return {
        "id": activity.id,
        "lead_id": activity.lead_id,
        "activity_type": activity.activity_type,
        "channel": activity.channel,
        "subject": activity.subject,
        "body": activity.body,
        "status": activity.status,
        "completed_by": activity.completed_by,
        "completed_at": _dt(activity.completed_at),
        "next_action_date": _dt(activity.next_action_date),
        "notes": activity.notes,
        "created_at": _dt(activity.created_at),
        "updated_at": _dt(activity.updated_at),
    }


def _template_to_dict(template: OutreachTemplate):
    return {
        "id": template.id,
        "brand_name": template.brand_name,
        "region_id": template.region_id,
        "segment": template.segment,
        "channel": template.channel,
        "template_name": template.template_name,
        "subject_template": template.subject_template,
        "body_template": template.body_template,
        "cta": template.cta,
        "variables": template.variables or [],
        "is_active": template.is_active,
        "created_at": _dt(template.created_at),
        "updated_at": _dt(template.updated_at),
    }


def _source_to_dict(source: LeadSource):
    return {
        "id": source.id,
        "brand_name": source.brand_name,
        "region_id": source.region_id,
        "name": source.name,
        "source_type": source.source_type,
        "url": source.url,
        "query_keywords": source.query_keywords or [],
        "negative_keywords": source.negative_keywords or [],
        "region_filters": source.region_filters or [],
        "segment_filters": source.segment_filters or [],
        "run_frequency": source.run_frequency,
        "is_active": source.is_active,
        "last_run_at": _dt(source.last_run_at),
        "next_run_at": _dt(source.next_run_at),
        "owner": source.owner,
        "notes": source.notes,
        "compliance_notes": source.compliance_notes,
        "created_at": _dt(source.created_at),
        "updated_at": _dt(source.updated_at),
    }


def _candidate_to_dict(candidate: LeadCandidate):
    return {
        "id": candidate.id,
        "brand_name": candidate.brand_name,
        "lead_source_id": candidate.lead_source_id,
        "research_job_id": candidate.research_job_id,
        "region_id": candidate.region_id,
        "raw_name": candidate.raw_name,
        "raw_company": candidate.raw_company,
        "raw_title": candidate.raw_title,
        "raw_url": candidate.raw_url,
        "raw_text": candidate.raw_text,
        "signal_summary": candidate.signal_summary,
        "detected_keywords": candidate.detected_keywords or [],
        "detected_region": candidate.detected_region,
        "detected_segment": candidate.detected_segment,
        "confidence_score": candidate.confidence_score,
        "fit_score": candidate.fit_score,
        "score_breakdown": candidate.score_breakdown or [],
        "status": candidate.status,
        "reviewer": candidate.reviewer,
        "review_notes": candidate.review_notes,
        "is_do_not_contact": candidate.is_do_not_contact,
        "created_at": _dt(candidate.created_at),
        "updated_at": _dt(candidate.updated_at),
    }


def _research_job_to_dict(job: ResearchJob):
    source = LeadSource.query.get(job.lead_source_id)
    return {
        "id": job.id,
        "lead_source_id": job.lead_source_id,
        "source_name": source.name if source else "Unknown Source",
        "status": job.status,
        "results_count": job.results_count,
        "candidates_created": job.candidates_created,
        "error_message": job.error_message,
        "started_at": _dt(job.started_at),
        "completed_at": _dt(job.completed_at),
        "updated_at": _dt(job.updated_at),
    }


# Pages
@lead_api_bp.route("/lead-radar")
def lead_radar_home():
    return render_template("lead_radar_dashboard.html", title="Lead Radar")


@lead_api_bp.route("/lead-radar/sources")
def lead_radar_sources_page():
    return render_template("lead_radar_sources.html", title="Lead Radar Sources")


@lead_api_bp.route("/lead-radar/candidates")
def lead_radar_candidates_page():
    return render_template("lead_radar_candidates.html", title="Lead Radar Candidates")


@lead_api_bp.route("/lead-radar/rules")
def lead_radar_rules_page():
    return render_template("lead_radar_rules.html", title="Lead Radar Rules")


@lead_api_bp.route("/lead-radar/feedback")
def lead_radar_feedback_page():
    return render_template("lead_radar_feedback.html", title="Lead Radar Feedback")


@lead_api_bp.route("/lead-radar/settings")
def lead_radar_settings_page():
    return render_template("lead_radar_settings.html", title="Lead Radar Settings")


@lead_api_bp.route("/leads")
def leads_page():
    return render_template("leads.html", title="Leads")


@lead_api_bp.route("/leads/regions")
def leads_regions_page():
    return render_template("lead_regions.html", title="Lead Regions")


@lead_api_bp.route("/leads/<int:lead_id>")
def lead_detail_page(lead_id):
    lead = Lead.query.get_or_404(lead_id)
    return render_template("lead_detail.html", title=f"Lead {lead.company_name}", lead=lead)


@lead_api_bp.route("/leads/import")
def leads_import_page():
    return render_template("lead_import.html", title="Import Leads")


@lead_api_bp.route("/leads/dashboard")
def leads_dashboard_page():
    return render_template("lead_dashboard.html", title="Lead Dashboard")


# Required lead routes
@lead_api_bp.route("/api/leads/regions", methods=["GET"])
def get_regions():
    brand_name = request.args.get("brand_name")
    q = RegionProfile.query
    if brand_name:
        q = q.filter_by(brand_name=brand_name)
    return jsonify({"success": True, "data": [_region_to_dict(r) for r in q.order_by(RegionProfile.name.asc()).all()]})


@lead_api_bp.route("/api/leads/regions", methods=["POST"])
def create_region():
    data = request.get_json() or {}
    brand_name = data.get("brand_name")
    if not brand_name:
        return jsonify({"success": False, "error": "brand_name is required"}), 400

    if not Brand.query.filter_by(name=brand_name).first():
        return jsonify({"success": False, "error": "brand not found"}), 404

    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"success": False, "error": "name is required"}), 400

    slug = (data.get("slug") or name.lower().replace(" ", "-")).strip()
    existing = RegionProfile.query.filter_by(brand_name=brand_name, slug=slug).first()
    if existing:
        return jsonify({"success": False, "error": "region slug already exists"}), 409

    region = RegionProfile(
        brand_name=brand_name,
        name=name,
        slug=slug,
        owner=data.get("owner", ""),
        countries=data.get("countries") or [],
        timezone_notes=data.get("timezone_notes", ""),
        primary_offer=data.get("primary_offer", ""),
        entry_price_min=float(data.get("entry_price_min", 0) or 0),
        entry_price_max=float(data.get("entry_price_max", 0) or 0),
        currency=data.get("currency", "USD"),
        target_segments=data.get("target_segments") or [],
        preferred_channels=data.get("preferred_channels") or [],
        outreach_tone=data.get("outreach_tone", ""),
        local_notes=data.get("local_notes", ""),
        is_active=bool(data.get("is_active", True)),
    )
    db.session.add(region)
    db.session.commit()
    return jsonify({"success": True, "data": _region_to_dict(region)}), 201


@lead_api_bp.route("/api/leads/regions/<int:region_id>", methods=["PUT"])
def update_region(region_id):
    region = RegionProfile.query.get_or_404(region_id)
    data = request.get_json() or {}

    editable = [
        "name", "owner", "countries", "timezone_notes", "primary_offer",
        "entry_price_min", "entry_price_max", "currency", "target_segments",
        "preferred_channels", "outreach_tone", "local_notes", "is_active",
    ]
    for field in editable:
        if field in data:
            setattr(region, field, data[field])

    if "slug" in data:
        slug = (data.get("slug") or "").strip()
        if not slug:
            return jsonify({"success": False, "error": "slug cannot be empty"}), 400
        existing = RegionProfile.query.filter_by(brand_name=region.brand_name, slug=slug).first()
        if existing and existing.id != region.id:
            return jsonify({"success": False, "error": "region slug already exists"}), 409
        region.slug = slug

    db.session.commit()
    return jsonify({"success": True, "data": _region_to_dict(region)})


@lead_api_bp.route("/api/leads", methods=["GET"])
def get_leads():
    q = Lead.query.filter_by(archived_at=None)
    for field in ["brand_name", "owner", "status", "priority", "segment", "source"]:
        value = request.args.get(field)
        if value:
            q = q.filter(getattr(Lead, field) == value)
    region_id = request.args.get("region_id")
    if region_id:
        q = q.filter(Lead.region_id == int(region_id))
    return jsonify({"success": True, "data": [_lead_to_dict(l) for l in q.order_by(Lead.updated_at.desc()).all()]})


@lead_api_bp.route("/api/leads", methods=["POST"])
def create_lead():
    data = request.get_json() or {}
    valid, err = validate_lead_payload(data)
    if not valid:
        return jsonify({"success": False, "error": err}), 400

    # De-dup by linkedin/email when provided.
    if data.get("linkedin_url"):
        existing = Lead.query.filter_by(brand_name=data["brand_name"], linkedin_url=data.get("linkedin_url"), archived_at=None).first()
        if existing:
            return jsonify({"success": True, "data": _lead_to_dict(existing), "duplicate": True}), 200
    if data.get("email"):
        existing = Lead.query.filter_by(brand_name=data["brand_name"], email=data.get("email"), archived_at=None).first()
        if existing:
            return jsonify({"success": True, "data": _lead_to_dict(existing), "duplicate": True}), 200

    region_id = data.get("region_id")
    if not region_id:
        region = find_region_for_country(data["brand_name"], data.get("region") or data.get("country") or "")
        region_id = region.id if region else None

    score = calculate_fit_score(data, rules=ScoringRule.query.filter_by(brand_name=data["brand_name"], is_active=True).all())

    next_action = None
    if data.get("next_action_date"):
        try:
            next_action = datetime.fromisoformat(data["next_action_date"])
        except Exception:
            return jsonify({"success": False, "error": "invalid next_action_date"}), 400

    lead = Lead(
        brand_name=data["brand_name"],
        region_id=region_id,
        calendar_id=data.get("calendar_id"),
        owner=data.get("owner", ""),
        first_name=data.get("first_name", ""),
        last_name=data.get("last_name", ""),
        title=data.get("title", ""),
        company_name=data["company_name"],
        company_url=data.get("company_url", ""),
        linkedin_url=data.get("linkedin_url", ""),
        email=data.get("email", ""),
        country=data.get("country", ""),
        city=data.get("city", ""),
        company_stage=data.get("company_stage", ""),
        segment=data.get("segment", ""),
        source=data.get("source", "manual"),
        pain_signals=data.get("pain_signals") or [],
        fit_score=int(data.get("fit_score", score["fit_score"])),
        score_breakdown=data.get("score_breakdown") or score["score_breakdown"],
        priority=data.get("priority") if data.get("priority") else score["priority"],
        status=data.get("status", "researched") if data.get("status", "researched") in LEAD_STATUSES else "researched",
        consent_status=data.get("consent_status", "unknown"),
        compliance_notes=data.get("compliance_notes", ""),
        notes=data.get("notes", ""),
        next_action_date=next_action,
        is_do_not_contact=bool(data.get("is_do_not_contact", False)),
    )
    if lead.status == "do_not_contact":
        lead.is_do_not_contact = True

    db.session.add(lead)
    db.session.flush()
    if lead.next_action_date and not lead.is_do_not_contact:
        upsert_followup_task(lead)

    db.session.commit()
    return jsonify({"success": True, "data": _lead_to_dict(lead)}), 201


@lead_api_bp.route("/api/leads/<int:lead_id>", methods=["GET"])
def get_lead(lead_id):
    lead = Lead.query.get_or_404(lead_id)
    return jsonify({"success": True, "data": _lead_to_dict(lead)})


@lead_api_bp.route("/api/leads/<int:lead_id>", methods=["PUT"])
def update_lead(lead_id):
    lead = Lead.query.get_or_404(lead_id)
    data = request.get_json() or {}

    editable = [
        "owner", "first_name", "last_name", "title", "company_name", "company_url",
        "linkedin_url", "email", "country", "city", "company_stage", "segment", "source",
        "consent_status", "compliance_notes", "notes", "status", "priority",
    ]
    for field in editable:
        if field in data:
            setattr(lead, field, data[field])

    if "region_id" in data:
        lead.region_id = data.get("region_id")
    if "pain_signals" in data:
        lead.pain_signals = data.get("pain_signals") or []
    if "fit_score" in data:
        lead.fit_score = int(data["fit_score"])
    if "score_breakdown" in data:
        lead.score_breakdown = data["score_breakdown"]
    if "next_action_date" in data:
        lead.next_action_date = datetime.fromisoformat(data["next_action_date"]) if data.get("next_action_date") else None
    if "is_do_not_contact" in data:
        lead.is_do_not_contact = bool(data["is_do_not_contact"])
    if lead.status == "do_not_contact":
        lead.is_do_not_contact = True

    if lead.next_action_date and not lead.is_do_not_contact:
        upsert_followup_task(lead)

    db.session.commit()
    return jsonify({"success": True, "data": _lead_to_dict(lead)})


@lead_api_bp.route("/api/leads/<int:lead_id>", methods=["DELETE"])
def delete_lead(lead_id):
    lead = Lead.query.get_or_404(lead_id)
    lead.archived_at = datetime.utcnow()
    db.session.commit()
    return jsonify({"success": True, "mode": "archive"})


@lead_api_bp.route("/api/leads/import-csv", methods=["POST"])
def import_leads_csv():
    brand_name = request.form.get("brand_name") or request.args.get("brand_name")
    if not brand_name:
        data = request.get_json(silent=True) or {}
        brand_name = data.get("brand_name")
    if not brand_name:
        return jsonify({"success": False, "error": "brand_name is required"}), 400

    if "file" in request.files:
        result = parse_csv_to_leads(request.files["file"], brand_name=brand_name)
        return jsonify({"success": True, "data": result})

    data = request.get_json(silent=True) or {}
    csv_text = data.get("csv") or ""
    if not csv_text:
        return jsonify({"success": False, "error": "CSV file or csv text is required"}), 400

    class _MemFile:
        def __init__(self, text):
            self._text = text

        def read(self):
            return self._text.encode("utf-8")

    result = parse_csv_to_leads(_MemFile(csv_text), brand_name=brand_name)
    return jsonify({"success": True, "data": result})


@lead_api_bp.route("/api/leads/<int:lead_id>/score", methods=["POST"])
def score_lead(lead_id):
    lead = Lead.query.get_or_404(lead_id)
    payload = request.get_json(silent=True) or {}

    if payload.get("manual_override"):
        if "fit_score" in payload:
            lead.fit_score = int(payload["fit_score"])
        if "priority" in payload:
            lead.priority = payload["priority"]
        if "score_breakdown" in payload:
            lead.score_breakdown = payload["score_breakdown"]
        db.session.commit()
        return jsonify({"success": True, "data": _lead_to_dict(lead), "manual_override": True})

    scored = calculate_fit_score(
        {
            "title": lead.title,
            "segment": lead.segment,
            "company_stage": lead.company_stage,
            "source": lead.source,
            "notes": lead.notes,
            "pain_signals": lead.pain_signals,
            "region_id": lead.region_id,
        },
        rules=ScoringRule.query.filter_by(brand_name=lead.brand_name, is_active=True).all(),
    )
    lead.fit_score = scored["fit_score"]
    lead.priority = scored["priority"]
    lead.score_breakdown = scored["score_breakdown"]
    db.session.commit()
    return jsonify({"success": True, "data": _lead_to_dict(lead)})


@lead_api_bp.route("/api/leads/<int:lead_id>/activities", methods=["GET"])
def get_lead_activities(lead_id):
    Lead.query.get_or_404(lead_id)
    activities = LeadActivity.query.filter_by(lead_id=lead_id).order_by(LeadActivity.created_at.desc()).all()
    return jsonify({"success": True, "data": [_activity_to_dict(a) for a in activities]})


@lead_api_bp.route("/api/leads/<int:lead_id>/activities", methods=["POST"])
def create_lead_activity(lead_id):
    lead = Lead.query.get_or_404(lead_id)
    data = request.get_json() or {}

    activity = LeadActivity(
        lead_id=lead_id,
        activity_type=data.get("activity_type", "note"),
        channel=data.get("channel", "other"),
        subject=data.get("subject", ""),
        body=data.get("body", ""),
        status=data.get("status", "draft"),
        completed_by=data.get("completed_by", ""),
        completed_at=datetime.fromisoformat(data["completed_at"]) if data.get("completed_at") else None,
        next_action_date=datetime.fromisoformat(data["next_action_date"]) if data.get("next_action_date") else None,
        notes=data.get("notes", ""),
    )
    db.session.add(activity)

    if activity.next_action_date and not lead.is_do_not_contact:
        lead.next_action_date = activity.next_action_date
        upsert_followup_task(lead, summary=activity.subject or activity.notes or "Follow-up activity")

    db.session.commit()
    return jsonify({"success": True, "data": _activity_to_dict(activity)}), 201


@lead_api_bp.route("/api/leads/<int:lead_id>/generate-draft", methods=["POST"])
def generate_lead_draft(lead_id):
    lead = Lead.query.get_or_404(lead_id)
    data = request.get_json() or {}
    channel = data.get("channel", "email")
    template_id = data.get("template_id")

    try:
        draft = generate_draft_for_lead(lead, channel=channel, template_id=template_id)
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400

    return jsonify({"success": True, "data": draft})


@lead_api_bp.route("/api/leads/templates", methods=["GET"])
def get_templates():
    brand_name = request.args.get("brand_name")
    q = OutreachTemplate.query
    if brand_name:
        q = q.filter_by(brand_name=brand_name)
    return jsonify({"success": True, "data": [_template_to_dict(t) for t in q.order_by(OutreachTemplate.id.desc()).all()]})


@lead_api_bp.route("/api/leads/templates", methods=["POST"])
def create_template():
    data = request.get_json() or {}
    if not data.get("brand_name"):
        return jsonify({"success": False, "error": "brand_name is required"}), 400

    template = OutreachTemplate(
        brand_name=data["brand_name"],
        region_id=data.get("region_id"),
        segment=data.get("segment", ""),
        channel=data.get("channel", "email"),
        template_name=data.get("template_name", "Untitled Template"),
        subject_template=data.get("subject_template", ""),
        body_template=data.get("body_template", ""),
        cta=data.get("cta", ""),
        variables=data.get("variables") or [],
        is_active=bool(data.get("is_active", True)),
    )
    db.session.add(template)
    db.session.commit()
    return jsonify({"success": True, "data": _template_to_dict(template)}), 201


@lead_api_bp.route("/api/leads/dashboard-summary", methods=["GET"])
def lead_dashboard_summary():
    brand_name = request.args.get("brand_name")
    return jsonify({"success": True, "data": get_dashboard_summary(brand_name=brand_name)})


# Lead Radar configuration/workflow routes
@lead_api_bp.route("/api/lead-radar/sources", methods=["GET"])
def list_sources():
    brand_name = request.args.get("brand_name")
    q = LeadSource.query
    if brand_name:
        q = q.filter_by(brand_name=brand_name)
    return jsonify({"success": True, "data": [_source_to_dict(s) for s in q.order_by(LeadSource.updated_at.desc()).all()]})


@lead_api_bp.route("/api/lead-radar/sources", methods=["POST"])
def create_source():
    data = request.get_json() or {}
    brand_name = data.get("brand_name")
    if not brand_name:
        return jsonify({"success": False, "error": "brand_name is required"}), 400

    source_type = data.get("source_type", "manual")
    if source_type not in ALLOWED_SOURCE_TYPES:
        return jsonify({"success": False, "error": "invalid source_type"}), 400

    run_frequency = data.get("run_frequency", "manual")
    source = LeadSource(
        brand_name=brand_name,
        region_id=data.get("region_id"),
        name=data.get("name") or "Unnamed Source",
        source_type=source_type,
        url=data.get("url", ""),
        query_keywords=data.get("query_keywords") or [],
        negative_keywords=data.get("negative_keywords") or [],
        region_filters=data.get("region_filters") or [],
        segment_filters=data.get("segment_filters") or [],
        run_frequency=run_frequency,
        next_run_at=datetime.utcnow() if run_frequency in {"daily", "weekly", "monthly"} else None,
        is_active=bool(data.get("is_active", True)),
        owner=data.get("owner", ""),
        notes=data.get("notes", ""),
        compliance_notes=data.get("compliance_notes", ""),
    )
    db.session.add(source)
    db.session.commit()
    return jsonify({"success": True, "data": _source_to_dict(source)}), 201


@lead_api_bp.route("/api/lead-radar/sources/<int:source_id>", methods=["PUT"])
def update_source(source_id):
    source = LeadSource.query.get_or_404(source_id)
    data = request.get_json() or {}
    for field in [
        "region_id", "name", "source_type", "url", "query_keywords", "negative_keywords",
        "region_filters", "segment_filters", "run_frequency", "is_active", "owner", "notes", "compliance_notes",
    ]:
        if field in data:
            setattr(source, field, data[field])

    if source.run_frequency in {"daily", "weekly", "monthly"} and not source.next_run_at:
        source.next_run_at = datetime.utcnow()
    if source.run_frequency == "manual":
        source.next_run_at = None

    if bool(data.get("queue_now", False)):
        source.next_run_at = datetime.utcnow()

    db.session.commit()
    return jsonify({"success": True, "data": _source_to_dict(source)})


@lead_api_bp.route("/api/lead-radar/sources/<int:source_id>", methods=["DELETE"])
def delete_source(source_id):
    source = LeadSource.query.get_or_404(source_id)
    source.is_active = False
    db.session.commit()
    return jsonify({"success": True})


@lead_api_bp.route("/api/lead-radar/research-jobs/run", methods=["POST"])
def run_research_job():
    data = request.get_json() or {}
    source_id = data.get("lead_source_id")
    if not source_id:
        return jsonify({"success": False, "error": "lead_source_id is required"}), 400

    source = LeadSource.query.get_or_404(int(source_id))
    manual_items = data.get("manual_items") or []
    if manual_items:
        job = run_manual_research_job(source, manual_items)
        mode = "manual"
    else:
        job = run_source_research_job(source, payload=data)
        mode = "automatic"
    return jsonify({
        "success": True,
        "mode": mode,
        "data": {
            "id": job.id,
            "lead_source_id": job.lead_source_id,
            "status": job.status,
            "results_count": job.results_count,
            "candidates_created": job.candidates_created,
            "run_log": job.run_log,
            "started_at": _dt(job.started_at),
            "completed_at": _dt(job.completed_at),
        },
    })


@lead_api_bp.route("/api/lead-radar/research-jobs/run-due", methods=["POST"])
def run_due_research_jobs():
    data = request.get_json(silent=True) or {}
    summary = run_due_source_research_jobs(
        brand_name=data.get("brand_name"),
        source_id=data.get("lead_source_id"),
        limit=int(data.get("limit", 25) or 25),
    )

    # Build a source_id → name lookup for the jobs we ran
    source_ids = [j.lead_source_id for j in summary["jobs"]]
    source_names = {}
    if source_ids:
        from dashboard.lead_radar_models import LeadSource as _LS
        for src in _LS.query.filter(_LS.id.in_(source_ids)).all():
            source_names[src.id] = src.name

    return jsonify({
        "success": True,
        "data": {
            "run_at": summary["run_at"],
            "sources_considered": summary["sources_considered"],
            "jobs_completed": summary["jobs_completed"],
            "jobs_failed": summary["jobs_failed"],
            "total_items_processed": summary["total_items_processed"],
            "total_candidates_created": summary["total_candidates_created"],
            "jobs": [
                {
                    "id": j.id,
                    "lead_source_id": j.lead_source_id,
                    "source_name": source_names.get(j.lead_source_id, f"Source {j.lead_source_id}"),
                    "status": j.status,
                    "results_count": j.results_count,
                    "candidates_created": j.candidates_created,
                    "run_log": j.run_log,
                    "error_message": j.error_message,
                    "started_at": _dt(j.started_at),
                    "completed_at": _dt(j.completed_at),
                }
                for j in summary["jobs"]
            ],
        },
    })


@lead_api_bp.route("/api/lead-radar/candidates", methods=["GET"])
def list_candidates():
    q = LeadCandidate.query
    brand_name = request.args.get("brand_name")
    if brand_name:
        q = q.filter_by(brand_name=brand_name)
    status = request.args.get("status")
    if status:
        q = q.filter_by(status=status)
    reviewer = (request.args.get("reviewer") or "").strip()
    if reviewer:
        q = q.filter_by(reviewer=reviewer)
    return jsonify({"success": True, "data": [_candidate_to_dict(c) for c in q.order_by(LeadCandidate.updated_at.desc()).all()]})


@lead_api_bp.route("/api/lead-radar/candidates/<int:candidate_id>/review", methods=["POST"])
def review_candidate(candidate_id):
    candidate = LeadCandidate.query.get_or_404(candidate_id)
    data = request.get_json() or {}
    action = data.get("action")
    if action not in {"approve", "reject", "duplicate", "do_not_contact"}:
        return jsonify({"success": False, "error": "invalid action"}), 400

    candidate.reviewer = data.get("reviewer", "")
    candidate.review_notes = data.get("review_notes", "")

    if action == "approve":
        candidate.status = "approved"
    elif action == "reject":
        candidate.status = "rejected"
    elif action == "duplicate":
        candidate.status = "duplicate"
    elif action == "do_not_contact":
        candidate.status = "do_not_contact"
        candidate.is_do_not_contact = True

    update_source_performance(candidate.lead_source_id, candidate.brand_name, candidate.region_id)
    db.session.commit()
    return jsonify({"success": True, "data": _candidate_to_dict(candidate)})


@lead_api_bp.route("/api/lead-radar/candidates/<int:candidate_id>/assign", methods=["POST"])
def assign_candidate(candidate_id):
    candidate = LeadCandidate.query.get_or_404(candidate_id)
    data = request.get_json() or {}

    if "region_id" in data:
        candidate.region_id = data.get("region_id")
    if "reviewer" in data:
        candidate.reviewer = data.get("reviewer", "")
    if data.get("review_notes"):
        candidate.review_notes = data.get("review_notes")

    # Assigning a candidate moves it into a visible working queue unless already terminal.
    if candidate.status in {"new", "queued", "pending"}:
        candidate.status = "needs_review"

    db.session.commit()
    return jsonify({"success": True, "data": _candidate_to_dict(candidate)})


@lead_api_bp.route("/api/lead-radar/candidates/<int:candidate_id>/convert", methods=["POST"])
def convert_candidate(candidate_id):
    candidate = LeadCandidate.query.get_or_404(candidate_id)
    if candidate.is_do_not_contact or candidate.status == "do_not_contact":
        return jsonify({"success": False, "error": "candidate marked do_not_contact"}), 400

    data = request.get_json() or {}
    lead = convert_candidate_to_lead(candidate, owner=data.get("owner", ""), create_tasks=bool(data.get("create_tasks", True)))

    update_source_performance(candidate.lead_source_id, candidate.brand_name, candidate.region_id)
    db.session.commit()
    return jsonify({"success": True, "data": _lead_to_dict(lead)})


@lead_api_bp.route("/api/lead-radar/rules", methods=["GET"])
def list_rules():
    brand_name = request.args.get("brand_name")
    q = ScoringRule.query
    if brand_name:
        q = q.filter_by(brand_name=brand_name)
    data = [
        {
            "id": r.id,
            "brand_name": r.brand_name,
            "region_id": r.region_id,
            "name": r.name,
            "rule_type": r.rule_type,
            "match_value": r.match_value,
            "score_delta": r.score_delta,
            "is_active": r.is_active,
            "notes": r.notes,
            "created_at": _dt(r.created_at),
            "updated_at": _dt(r.updated_at),
        }
        for r in q.order_by(ScoringRule.updated_at.desc()).all()
    ]
    return jsonify({"success": True, "data": data})


@lead_api_bp.route("/api/lead-radar/rules", methods=["POST"])
def create_rule():
    data = request.get_json() or {}
    if not data.get("brand_name"):
        return jsonify({"success": False, "error": "brand_name is required"}), 400

    rule = ScoringRule(
        brand_name=data["brand_name"],
        region_id=data.get("region_id"),
        name=data.get("name", "Untitled Rule"),
        rule_type=data.get("rule_type", "custom"),
        match_value=data.get("match_value", ""),
        score_delta=int(data.get("score_delta", 0)),
        is_active=bool(data.get("is_active", True)),
        notes=data.get("notes", ""),
    )
    db.session.add(rule)
    db.session.commit()

    return jsonify({
        "success": True,
        "data": {
            "id": rule.id,
            "brand_name": rule.brand_name,
            "region_id": rule.region_id,
            "name": rule.name,
            "rule_type": rule.rule_type,
            "match_value": rule.match_value,
            "score_delta": rule.score_delta,
            "is_active": rule.is_active,
            "notes": rule.notes,
        },
    }), 201


@lead_api_bp.route("/api/lead-radar/feedback", methods=["GET"])
def list_feedback():
    brand_name = request.args.get("brand_name")
    q = LeadFeedback.query
    if brand_name:
        q = q.outerjoin(Lead, Lead.id == LeadFeedback.lead_id).outerjoin(LeadCandidate, LeadCandidate.id == LeadFeedback.lead_candidate_id)
        q = q.filter((Lead.brand_name == brand_name) | (LeadCandidate.brand_name == brand_name))

    data = [
        {
            "id": f.id,
            "lead_id": f.lead_id,
            "lead_candidate_id": f.lead_candidate_id,
            "user": f.user,
            "feedback_type": f.feedback_type,
            "feedback_notes": f.feedback_notes,
            "created_at": _dt(f.created_at),
        }
        for f in q.order_by(LeadFeedback.created_at.desc()).all()
    ]
    return jsonify({"success": True, "data": data})


@lead_api_bp.route("/api/lead-radar/feedback", methods=["POST"])
def create_feedback():
    data = request.get_json() or {}
    if data.get("feedback_type") not in FEEDBACK_TYPES:
        return jsonify({"success": False, "error": "invalid feedback_type"}), 400

    feedback = capture_feedback(
        feedback_type=data["feedback_type"],
        user=data.get("user", ""),
        lead_id=data.get("lead_id"),
        lead_candidate_id=data.get("lead_candidate_id"),
        feedback_notes=data.get("feedback_notes", ""),
    )
    return jsonify({
        "success": True,
        "data": {
            "id": feedback.id,
            "lead_id": feedback.lead_id,
            "lead_candidate_id": feedback.lead_candidate_id,
            "user": feedback.user,
            "feedback_type": feedback.feedback_type,
            "feedback_notes": feedback.feedback_notes,
            "created_at": _dt(feedback.created_at),
        },
    }), 201


@lead_api_bp.route("/api/lead-radar/settings", methods=["GET"])
def get_settings():
    brand_name = request.args.get("brand_name")
    if not brand_name:
        return jsonify({"success": False, "error": "brand_name is required"}), 400

    setting = LeadRadarSetting.query.filter_by(brand_name=brand_name).first()
    if not setting:
        setting = LeadRadarSetting(brand_name=brand_name, settings_json={})
        db.session.add(setting)
        db.session.commit()

    return jsonify({
        "success": True,
        "data": {
            "id": setting.id,
            "brand_name": setting.brand_name,
            "settings_json": setting.settings_json or {},
            "updated_at": _dt(setting.updated_at),
        },
    })


@lead_api_bp.route("/api/lead-radar/settings", methods=["POST"])
def update_settings():
    data = request.get_json() or {}
    brand_name = data.get("brand_name")
    if not brand_name:
        return jsonify({"success": False, "error": "brand_name is required"}), 400

    setting = LeadRadarSetting.query.filter_by(brand_name=brand_name).first()
    if not setting:
        setting = LeadRadarSetting(brand_name=brand_name, settings_json={})
        db.session.add(setting)

    setting.settings_json = data.get("settings_json") or setting.settings_json or {}
    db.session.commit()

    return jsonify({
        "success": True,
        "data": {
            "id": setting.id,
            "brand_name": setting.brand_name,
            "settings_json": setting.settings_json,
            "updated_at": _dt(setting.updated_at),
        },
    })


@lead_api_bp.route("/api/lead-radar/dashboard-summary", methods=["GET"])
def lead_radar_dashboard_summary():
    brand_name = request.args.get("brand_name")
    return jsonify({"success": True, "data": get_dashboard_summary(brand_name=brand_name)})


@lead_api_bp.route("/api/lead-radar/login-overview", methods=["GET"])
def lead_radar_login_overview():
    """Operational snapshot for login/dashboard visibility of lead generation flow."""
    requested_brand = request.args.get("brand_name", "").strip()
    owner_filter = (request.args.get("owner") or "").strip()
    mine_only = str(request.args.get("mine_only") or "").strip().lower() in {"1", "true", "yes", "on"}

    brand_rows = Brand.query.filter_by(is_active=True).order_by(Brand.name.asc()).all()
    brand_names = [b.name for b in brand_rows]
    active_brand = requested_brand if requested_brand in brand_names else (brand_names[0] if brand_names else "")

    leads_query = Lead.query.filter_by(archived_at=None)
    if active_brand:
        leads_query = leads_query.filter_by(brand_name=active_brand)
    if mine_only and owner_filter:
        leads_query = leads_query.filter_by(owner=owner_filter)

    leads = leads_query.order_by(Lead.updated_at.desc()).limit(8).all()

    candidates_query = LeadCandidate.query
    if active_brand:
        candidates_query = candidates_query.filter_by(brand_name=active_brand)
    if mine_only and owner_filter:
        candidates_query = candidates_query.filter_by(reviewer=owner_filter)
    recent_candidates = candidates_query.order_by(LeadCandidate.updated_at.desc()).limit(10).all()

    candidate_counts = Counter([c.status or "new" for c in recent_candidates])

    region_query = RegionProfile.query
    if active_brand:
        region_query = region_query.filter_by(brand_name=active_brand)
    regions = region_query.order_by(RegionProfile.name.asc()).all()

    source_query = LeadSource.query
    if active_brand:
        source_query = source_query.filter_by(brand_name=active_brand)
    sources = source_query.order_by(LeadSource.updated_at.desc()).all()

    source_ids = [s.id for s in sources]
    jobs = []
    if source_ids:
        jobs = ResearchJob.query.filter(ResearchJob.lead_source_id.in_(source_ids)).order_by(ResearchJob.updated_at.desc()).limit(25).all()

    now = datetime.utcnow()
    running_jobs = [j for j in jobs if j.status in {"queued", "running"}]
    recent_jobs = jobs[:8]
    due_sources = [
        s for s in sources
        if s.is_active and s.run_frequency in {"daily", "weekly", "monthly"}
        and (s.next_run_at is None or s.next_run_at <= now)
    ]
    upcoming_sources = [
        s for s in sources
        if s.is_active and s.run_frequency in {"daily", "weekly", "monthly"}
        and s.next_run_at is not None and now < s.next_run_at <= now + timedelta(hours=24)
    ]

    open_statuses = {"researched", "qualified", "contacted", "reply_received", "meeting_scheduled", "call_booked", "proposal_sent"}
    open_leads = [l for l in leads_query.limit(500).all() if (l.status or "") in open_statuses]
    workload = Counter([l.owner or "unassigned" for l in open_leads])

    setting_payload = {}
    if active_brand:
        setting = LeadRadarSetting.query.filter_by(brand_name=active_brand).first()
        setting_payload = (setting.settings_json or {}) if setting else {}

    return jsonify({
        "success": True,
        "data": {
            "timestamp": _dt(now),
            "brands": brand_names,
            "active_brand": active_brand,
            "scope": {
                "mine_only": mine_only,
                "owner": owner_filter,
            },
            "leads": [_lead_to_dict(l) for l in leads],
            "recent_candidates": [_candidate_to_dict(c) for c in recent_candidates],
            "candidate_counts": dict(candidate_counts),
            "regions": [_region_to_dict(r) for r in regions],
            "sources": [_source_to_dict(s) for s in sources[:20]],
            "running_jobs": [_research_job_to_dict(j) for j in running_jobs[:10]],
            "recent_jobs": [_research_job_to_dict(j) for j in recent_jobs],
            "due_sources": [_source_to_dict(s) for s in due_sources[:20]],
            "upcoming_sources": [_source_to_dict(s) for s in upcoming_sources[:20]],
            "owner_workload": dict(workload),
            "unassigned": {
                "regions_without_owner": len([r for r in regions if not (r.owner or "").strip()]),
                "sources_without_owner": len([s for s in sources if not (s.owner or "").strip()]),
                "sources_without_region": len([s for s in sources if not s.region_id]),
                "open_leads_without_owner": len([l for l in open_leads if not (l.owner or "").strip()]),
            },
            "settings": {
                "always_on_research": bool(setting_payload.get("always_on_research", True)),
                "auto_run_on_login": bool(setting_payload.get("auto_run_on_login", False)),
                "target_new_candidates_daily": int(setting_payload.get("target_new_candidates_daily", 10) or 10),
            },
        },
    })


@lead_api_bp.route("/api/lead-radar/seed-defaults", methods=["POST"])
def seed_defaults():
    result = seed_buildly_defaults_if_present()
    return jsonify({"success": True, "data": result})


@lead_api_bp.route("/api/lead-radar/seed-sources", methods=["POST"])
def seed_sources():
    """Auto-create starter research sources for a brand based on its profile."""
    data = request.get_json() or {}
    brand_name = (data.get("brand_name") or "").strip()
    if not brand_name:
        return jsonify({"success": False, "error": "brand_name is required"}), 400
    result = seed_sources_for_brand(brand_name)
    return jsonify({"success": True, "data": result})


# ── Startup Intel Plugin endpoints ─────────────────────────────────────────────

@lead_api_bp.route("/lead-radar/startup-intel")
def lead_radar_startup_intel_page():
    return render_template("lead_radar_startup_intel.html", title="Startup Intel")


@lead_api_bp.route("/api/lead-radar/startup-intel/status", methods=["GET"])
def startup_intel_status():
    """Plugin status + API key configuration summary."""
    from dashboard.models import SystemConfig
    from dashboard.lead_radar_startup_adapters import CONFIG_KEYS, SOURCE_TYPES, PLUGIN_DESCRIPTION
    key_status = {}
    for name, (db_key, _env) in CONFIG_KEYS.items():
        row = SystemConfig.query.filter_by(key=db_key).first()
        key_status[name] = bool(row and row.value)
    return jsonify({
        "success": True,
        "data": {
            "plugin_id": "startup_intel",
            "description": PLUGIN_DESCRIPTION,
            "source_types": sorted(SOURCE_TYPES),
            "free_sources": ["yc_companies", "sbir_awards", "nsf_awards", "sec_edgar"],
            "paid_sources": {
                "product_hunt_api": {
                    "label": "Product Hunt API v2",
                    "configured": key_status.get("product_hunt", False),
                    "get_key_url": "https://producthunt.com/v2/oauth/applications",
                    "instructions": "Create an application, generate a Bearer token under 'Developer Token'.",
                },
                "opencorporates": {
                    "label": "OpenCorporates",
                    "configured": key_status.get("opencorporates", False),
                    "get_key_url": "https://opencorporates.com/api_accounts/new",
                    "instructions": "Register for a free API account. Copy the API token.",
                },
                "companies_house": {
                    "label": "Companies House (UK)",
                    "configured": key_status.get("companies_house", False),
                    "get_key_url": "https://developer.company-information.service.gov.uk/",
                    "instructions": "Register, create an application, and use the API key for Basic Auth.",
                },
                "github": {
                    "label": "GitHub (rate-limit boost)",
                    "configured": key_status.get("github", False),
                    "get_key_url": "https://github.com/settings/tokens/new",
                    "instructions": "Generate a Personal Access Token (no scopes needed for public data). Raises rate limit from 60 to 5,000 req/hr.",
                },
            },
        },
    })


@lead_api_bp.route("/api/lead-radar/startup-intel/seed-sources", methods=["POST"])
def startup_intel_seed_sources():
    """Create Startup Intel sources for a brand."""
    data = request.get_json() or {}
    brand_name = (data.get("brand_name") or "").strip()
    if not brand_name:
        return jsonify({"success": False, "error": "brand_name is required"}), 400
    result = seed_startup_sources_for_brand(brand_name)
    return jsonify({"success": True, "data": result})


@lead_api_bp.route("/api/lead-radar/candidates/<int:candidate_id>/enrich", methods=["POST"])
def enrich_candidate_route(candidate_id):
    """Run the Startup Intel enricher on a single candidate."""
    result = enrich_candidate(candidate_id)
    if "error" in result:
        code = 404 if "not found" in result["error"].lower() else 500
        return jsonify({"success": False, "error": result["error"]}), code
    return jsonify({"success": True, "data": result})


@lead_api_bp.route("/api/lead-radar/startup-intel/candidates", methods=["GET"])
def startup_intel_candidates():
    """List candidates from startup intel source types."""
    from dashboard.lead_radar_startup_adapters import SOURCE_TYPES
    brand_name = request.args.get("brand_name", "").strip()
    status = request.args.get("status", "").strip()
    limit = int(request.args.get("limit", 50))

    q = (
        LeadCandidate.query
        .join(LeadSource, LeadSource.id == LeadCandidate.lead_source_id)
        .filter(LeadSource.source_type.in_(SOURCE_TYPES))
    )
    if brand_name:
        q = q.filter(LeadCandidate.brand_name == brand_name)
    if status:
        q = q.filter(LeadCandidate.status == status)

    candidates = q.order_by(LeadCandidate.updated_at.desc()).limit(limit).all()
    return jsonify({"success": True, "data": [_candidate_to_dict(c) for c in candidates]})

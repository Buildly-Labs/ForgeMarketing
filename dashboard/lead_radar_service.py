"""Lead Radar services: scoring, import, research jobs, feedback, and seed helpers."""

import csv
import io
from collections import Counter
from datetime import datetime, timedelta

from dashboard.models import Brand, db
from dashboard.marketing_calendar_models import (
    MarketingCalendar,
    MarketingTask,
    PlatformType,
    TaskPriority,
    TaskStatus,
    TaskType,
)
from dashboard.lead_radar_models import (
    Lead,
    LeadActivity,
    LeadCandidate,
    LeadFeedback,
    LeadRadarSetting,
    LeadSource,
    OutreachTemplate,
    RegionProfile,
    ResearchJob,
    ScoringRule,
    SourcePerformance,
)
from dashboard.lead_radar_adapters import get_adapter


ALLOWED_SOURCE_TYPES = {
    "google_search",
    "rss_feed",
    "website_directory",
    "event_page",
    "github",
    "product_hunt",
    "hacker_news",
    "reddit",
    "instagram_manual",
    "linkedin_manual",
    "podcast",
    "youtube",
    "newsletter",
    "csv_import",
    "manual",
    "other",
}

LEAD_STATUSES = {
    "researched",
    "ready_to_contact",
    "contacted",
    "replied",
    "call_booked",
    "proposal_sent",
    "won",
    "lost",
    "do_not_contact",
}

FEEDBACK_TYPES = {
    "good_fit",
    "bad_fit",
    "wrong_region",
    "wrong_segment",
    "too_early",
    "too_small",
    "strong_opportunity",
    "bad_source",
    "booked_call",
    "positive_reply",
    "no_response",
    "do_not_contact",
    "duplicate",
}


def _to_list(value):
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return []
        if "," in value:
            return [x.strip() for x in value.split(",") if x.strip()]
        return [value]
    return [str(value).strip()]


def validate_lead_payload(payload):
    if not payload.get("brand_name"):
        return False, "brand_name is required"
    if not payload.get("company_name"):
        return False, "company_name is required"
    if not any(payload.get(k) for k in ["first_name", "last_name", "linkedin_url", "email", "company_url"]):
        return False, "At least one contact field is required (name, linkedin_url, email, or company_url)"
    return True, ""


def _priority(score):
    if score >= 80:
        return "hot"
    if score >= 60:
        return "high"
    if score >= 40:
        return "medium"
    return "low"


def calculate_fit_score(payload, rules=None):
    title = (payload.get("title") or "").lower()
    segment = (payload.get("segment") or "").lower()
    stage = (payload.get("company_stage") or "").lower()
    source = (payload.get("source") or "").lower()
    notes = (payload.get("notes") or "").lower()
    pain = " ".join(_to_list(payload.get("pain_signals", []))).lower()

    score = 0
    breakdown = []

    def add(reason, delta):
        nonlocal score
        if delta:
            score += delta
            breakdown.append({"reason": reason, "delta": delta})

    if any(k in title for k in ["founder", "ceo", "coo", "vp product", "head of product"]):
        add("decision_maker_title", 15)
    if any(k in segment for k in ["startup", "smb", "saas", "scaleup"]):
        add("icp_segment", 15)
    if any(k in stage for k in ["seed", "series a", "growth", "mvp"]):
        add("company_stage_match", 10)
    if any(k in notes for k in ["funding", "launch", "hiring", "announcement"]):
        add("recent_business_signal", 15)
    if "cto" not in title and any(k in notes for k in ["technical leadership", "need cto", "technical partner"]):
        add("technical_leadership_gap", 15)
    if payload.get("region_id") or payload.get("region"):
        add("region_match", 10)
    if pain:
        add("pain_signal", 15)
    if any(k in (source + " " + notes) for k in ["referral", "warm", "mutual"]):
        add("warm_path", 15)
    if any(k in (title + " " + notes) for k in ["student", "job seeker", "vendor only"]):
        add("poor_fit", -20)
    if any(k in notes for k in ["unrelated", "not relevant"]):
        add("no_business_relevance", -30)

    rules = rules or []
    text = " ".join([title, segment, stage, source, notes, pain]).lower()
    for rule in rules:
        if not rule.is_active:
            continue
        needle = (rule.match_value or "").strip().lower()
        if not needle:
            continue
        hit = False
        if rule.rule_type in {"positive_keyword", "negative_keyword", "pain_signal", "custom", "warm_connection"}:
            hit = needle in text
        elif rule.rule_type == "title_match":
            hit = needle in title
        elif rule.rule_type == "segment_match":
            hit = needle in segment
        elif rule.rule_type == "company_stage":
            hit = needle in stage
        elif rule.rule_type == "source_quality":
            hit = needle in source
        if hit:
            add(f"rule:{rule.name}", int(rule.score_delta))

    score = max(0, min(100, score))
    return {"fit_score": score, "priority": _priority(score), "score_breakdown": breakdown}


def find_region_for_country(brand_name, country_or_region):
    value = (country_or_region or "").strip().lower()
    if not value:
        return None
    regions = RegionProfile.query.filter_by(brand_name=brand_name, is_active=True).all()
    for region in regions:
        if value in {(region.name or "").lower(), (region.slug or "").lower()}:
            return region
        if value in [str(c).strip().lower() for c in (region.countries or [])]:
            return region
    return None


def _lead_duplicate(brand_name, payload):
    if payload.get("linkedin_url"):
        dup = Lead.query.filter_by(brand_name=brand_name, linkedin_url=payload.get("linkedin_url"), archived_at=None).first()
        if dup:
            return dup
    if payload.get("email"):
        dup = Lead.query.filter_by(brand_name=brand_name, email=payload.get("email"), archived_at=None).first()
        if dup:
            return dup
    company = (payload.get("company_name") or "").strip().lower()
    first = (payload.get("first_name") or "").strip().lower()
    last = (payload.get("last_name") or "").strip().lower()
    if company and (first or last):
        dup = Lead.query.filter(
            Lead.brand_name == brand_name,
            Lead.archived_at == None,
            db.func.lower(Lead.company_name) == company,
            db.func.lower(Lead.first_name) == first,
            db.func.lower(Lead.last_name) == last,
        ).first()
        if dup:
            return dup
    return None


def parse_csv_to_leads(file_storage, brand_name, default_status="researched"):
    content = file_storage.read().decode("utf-8", errors="ignore")
    reader = csv.DictReader(io.StringIO(content))

    created = 0
    skipped = 0
    errors = []

    rules = ScoringRule.query.filter_by(brand_name=brand_name, is_active=True).all()

    for idx, row in enumerate(reader, start=2):
        payload = {
            "brand_name": brand_name,
            "first_name": (row.get("first_name") or "").strip(),
            "last_name": (row.get("last_name") or "").strip(),
            "title": (row.get("title") or "").strip(),
            "company_name": (row.get("company_name") or "").strip(),
            "company_url": (row.get("company_url") or "").strip(),
            "linkedin_url": (row.get("linkedin_url") or "").strip(),
            "email": (row.get("email") or "").strip().lower(),
            "country": (row.get("country") or "").strip(),
            "city": (row.get("city") or "").strip(),
            "company_stage": (row.get("company_stage") or "").strip(),
            "segment": (row.get("segment") or "").strip(),
            "source": (row.get("source") or "csv_import").strip() or "csv_import",
            "pain_signals": _to_list(row.get("pain_signals") or ""),
            "owner": (row.get("owner") or "").strip(),
            "notes": (row.get("notes") or "").strip(),
            "status": (row.get("status") or default_status).strip(),
        }

        valid, err = validate_lead_payload(payload)
        if not valid:
            skipped += 1
            errors.append(f"line {idx}: {err}")
            continue

        region = find_region_for_country(brand_name, (row.get("region") or row.get("country") or ""))
        region_id = region.id if region else None

        if _lead_duplicate(brand_name, payload):
            skipped += 1
            continue

        score = calculate_fit_score({**payload, "region_id": region_id}, rules=rules)
        lead = Lead(
            brand_name=brand_name,
            region_id=region_id,
            owner=payload["owner"],
            first_name=payload["first_name"],
            last_name=payload["last_name"],
            title=payload["title"],
            company_name=payload["company_name"],
            company_url=payload["company_url"],
            linkedin_url=payload["linkedin_url"],
            email=payload["email"],
            country=payload["country"],
            city=payload["city"],
            company_stage=payload["company_stage"],
            segment=payload["segment"],
            source=payload["source"],
            pain_signals=payload["pain_signals"],
            fit_score=score["fit_score"],
            score_breakdown=score["score_breakdown"],
            priority=score["priority"],
            status=payload["status"] if payload["status"] in LEAD_STATUSES else "researched",
            consent_status="unknown",
            notes=payload["notes"],
        )
        db.session.add(lead)
        created += 1

    db.session.commit()
    return {"created": created, "skipped": skipped, "errors": errors}


def upsert_followup_task(lead, summary=""):
    if not lead.next_action_date or lead.is_do_not_contact or lead.status == "do_not_contact":
        return None

    campaign = MarketingCalendar.query.filter_by(brand_name=lead.brand_name, campaign_slug="lead-follow-ups").first()
    if not campaign:
        now = datetime.utcnow()
        campaign = MarketingCalendar(
            brand_name=lead.brand_name,
            campaign_name="Lead Follow-ups",
            campaign_slug="lead-follow-ups",
            description="Manual follow-up workflow for lead management",
            goal="Maintain daily follow-up rhythm",
            start_date=now,
            end_date=now + timedelta(days=365),
            status="active",
            owner=lead.owner or "",
        )
        db.session.add(campaign)
        db.session.flush()

    channel = PlatformType.LINKEDIN if lead.linkedin_url else PlatformType.EMAIL
    task_name = f"Follow up with {lead.first_name or lead.company_name} at {lead.company_name}"

    existing = MarketingTask.query.filter_by(brand_name=lead.brand_name, calendar_id=campaign.id, task_name=task_name).filter(
        MarketingTask.status.in_([TaskStatus.DRAFT, TaskStatus.SCHEDULED, TaskStatus.IN_PROGRESS])
    ).first()

    body = summary or f"Lead status: {lead.status}. Priority: {lead.priority}. Notes: {lead.notes or ''}".strip()
    if existing:
        existing.scheduled_date = lead.next_action_date
        existing.assigned_to = lead.owner or existing.assigned_to
        existing.body = body
        existing.updated_at = datetime.utcnow()
        return existing

    task = MarketingTask(
        calendar_id=campaign.id,
        brand_name=lead.brand_name,
        task_name=task_name,
        task_slug=f"lead-followup-{lead.id}",
        description="Manual outreach follow-up task generated by Lead Radar",
        task_type=TaskType.CUSTOM,
        platform=channel,
        scheduled_date=lead.next_action_date,
        assigned_to=lead.owner or "",
        status=TaskStatus.SCHEDULED,
        priority=TaskPriority.HIGH if lead.priority in {"high", "hot"} else TaskPriority.MEDIUM,
        is_automated=False,
        title=task_name,
        body=body,
    )
    db.session.add(task)
    return task


def generate_draft_for_lead(lead, channel="email", template_id=None):
    if lead.is_do_not_contact or lead.status == "do_not_contact":
        raise ValueError("Lead is marked do_not_contact. Draft generation is disabled.")

    template = OutreachTemplate.query.get(template_id) if template_id else None
    if not template:
        template = OutreachTemplate.query.filter_by(brand_name=lead.brand_name, region_id=lead.region_id, channel=channel, is_active=True).first()
    if not template:
        template = OutreachTemplate.query.filter_by(brand_name=lead.brand_name, channel=channel, is_active=True).first()

    region = RegionProfile.query.get(lead.region_id) if lead.region_id else None
    context = {
        "first_name": lead.first_name or "there",
        "last_name": lead.last_name or "",
        "company_name": lead.company_name,
        "title": lead.title or "",
        "segment": lead.segment or "",
        "region_name": region.name if region else "your region",
        "primary_offer": region.primary_offer if region else "AI-native technical leadership",
        "price_min": int(region.entry_price_min) if region and region.entry_price_min else 0,
        "price_max": int(region.entry_price_max) if region and region.entry_price_max else 0,
        "currency": region.currency if region and region.currency else "USD",
    }

    if template:
        subject = (template.subject_template or "").format(**context)
        body = (template.body_template or "").format(**context)
        cta = template.cta or "Would you be open to a 30-minute call next week?"
    else:
        subject = "Technical leadership without a full-time CTO hire"
        body = (
            f"Hi {context['first_name']},\n\n"
            f"I noticed {context['company_name']} is building in a fast-moving environment. "
            f"We support teams with AI-native CTO guidance without requiring a full-time executive hire.\n\n"
            f"Support starts around {context['currency']} {context['price_min']}/month based on scope.\n\n"
            "If useful, I can share a short roadmap format we use for technical clarity and execution speed."
        )
        cta = "Would a 30-minute intro call be helpful?"

    full_body = (
        body.strip()
        + "\n\n"
        + cta.strip()
        + "\n\nWARNING: ForgeMarketing creates research notes and draft outreach only. Review all information manually and send only through approved channels in compliance with platform rules and applicable laws."
    )

    activity = LeadActivity(
        lead_id=lead.id,
        activity_type="email" if channel == "email" else "linkedin_message",
        channel=channel,
        subject=subject,
        body=full_body,
        status="draft",
        notes="Draft generated. Human review required before any manual sending.",
    )
    db.session.add(activity)
    db.session.commit()

    return {
        "subject": subject,
        "body": full_body,
        "activity_id": activity.id,
        "warning": "Human review and manual sending are required.",
    }


def _candidate_duplicate(brand_name, item):
    url = (item.get("raw_url") or item.get("url") or "").strip()
    company = (item.get("raw_company") or item.get("company") or "").strip().lower()
    name = (item.get("raw_name") or item.get("name") or "").strip().lower()

    q = LeadCandidate.query.filter_by(brand_name=brand_name)
    if url and q.filter(LeadCandidate.raw_url == url).first():
        return True
    if company and name and q.filter(db.func.lower(LeadCandidate.raw_company) == company, db.func.lower(LeadCandidate.raw_name) == name).first():
        return True
    return False


def seed_sources_for_brand(brand_name: str) -> dict:
    """Create a practical set of auto-research sources for a brand using its stored profile.

    Safe to call multiple times — skips sources that already exist by name.
    Returns {created: int, skipped: int, sources: list}.
    """
    brand = Brand.query.filter_by(name=brand_name).first()
    if not brand:
        return {"created": 0, "skipped": 0, "sources": [], "error": "Brand not found"}

    # Pull identity signals from brand settings / advanced settings
    description = (brand.description or "").strip()
    display_name = (brand.display_name or brand_name).strip()
    website_url = (brand.website_url or "").strip()

    # Derive keywords from brand name, description and website domain
    base_kw = [w for w in display_name.lower().split() if len(w) > 3 and w not in {"the","and","for","with","that","this"}]
    if website_url:
        from urllib.parse import urlparse
        domain = urlparse(website_url).netloc.replace("www.", "").split(".")[0]
        if domain and domain not in base_kw:
            base_kw.insert(0, domain)

    # Try to use brand advanced settings if present
    from dashboard.models import BrandSettings
    settings = BrandSettings.query.filter_by(brand_id=brand.id).first()
    target_audience = ""
    product_type = ""
    if settings:
        try:
            adv = settings.get_advanced_settings() or {}
            mp = adv.get("marketing_profile") or {}
            target_audience = mp.get("target_audience", "")
            product_type = mp.get("product_type", "")
        except Exception:
            pass

    audience_kw = [w.strip() for w in (target_audience + " " + product_type).split()
                   if len(w.strip()) > 3 and w.strip() not in {"that","this","with","and","for"}][:4]

    all_kw = base_kw[:3] + audience_kw[:3]
    if not all_kw:
        all_kw = [brand_name]

    templates = [
        {
            "name": f"{display_name} — Hacker News",
            "source_type": "hacker_news",
            "url": "",
            "query_keywords": all_kw,
            "run_frequency": "daily",
            "notes": "Search HN for mentions, job posts, and Show HN projects relevant to the brand.",
        },
        {
            "name": f"{display_name} — Reddit",
            "source_type": "reddit",
            "url": "",
            "query_keywords": all_kw,
            "run_frequency": "daily",
            "notes": "Search Reddit for users asking about problems your brand solves.",
        },
        {
            "name": f"{display_name} — GitHub",
            "source_type": "github",
            "url": "",
            "query_keywords": all_kw[:2],
            "run_frequency": "weekly",
            "notes": "Find developers building in your problem space.",
        },
        {
            "name": f"{display_name} — Product Hunt",
            "source_type": "product_hunt",
            "url": "https://www.producthunt.com/feed",
            "query_keywords": all_kw[:2],
            "run_frequency": "daily",
            "notes": "New products in your category — potential partners or customers.",
        },
        {
            "name": f"{display_name} — Web Search",
            "source_type": "google_search",
            "url": "",
            "query_keywords": all_kw,
            "run_frequency": "weekly",
            "notes": "DuckDuckGo web search for leads matching your keywords.",
        },
        {
            "name": f"{display_name} — Manual / Paste List",
            "source_type": "manual",
            "url": "",
            "query_keywords": [],
            "run_frequency": "manual",
            "notes": "Paste names/URLs directly from LinkedIn or conference lists.",
        },
    ]

    created = skipped = 0
    sources = []
    for tmpl in templates:
        existing = LeadSource.query.filter_by(brand_name=brand_name, name=tmpl["name"]).first()
        if existing:
            skipped += 1
            sources.append(_source_summary(existing))
            continue

        freq = tmpl["run_frequency"]
        src = LeadSource(
            brand_name=brand_name,
            name=tmpl["name"],
            source_type=tmpl["source_type"],
            url=tmpl["url"],
            query_keywords=tmpl["query_keywords"],
            run_frequency=freq,
            next_run_at=datetime.utcnow() if freq in {"daily", "weekly", "monthly"} else None,
            is_active=True,
            notes=tmpl["notes"],
        )
        db.session.add(src)
        db.session.flush()
        created += 1
        sources.append(_source_summary(src))

    db.session.commit()
    return {"created": created, "skipped": skipped, "sources": sources}


def _source_summary(source: LeadSource) -> dict:
    return {
        "id": source.id,
        "name": source.name,
        "source_type": source.source_type,
        "run_frequency": source.run_frequency,
        "query_keywords": source.query_keywords or [],
        "last_run_at": source.last_run_at.isoformat() if source.last_run_at else None,
        "next_run_at": source.next_run_at.isoformat() if source.next_run_at else None,
    }


def create_candidate_from_manual(lead_source, item, research_job_id=None):
    if _candidate_duplicate(lead_source.brand_name, item):
        return None

    raw_name = (item.get("raw_name") or item.get("name") or "").strip()
    raw_company = (item.get("raw_company") or item.get("company") or "").strip()
    raw_title = (item.get("raw_title") or item.get("title") or "").strip()
    raw_url = (item.get("raw_url") or item.get("url") or "").strip()
    raw_text = (item.get("raw_text") or item.get("text") or "").strip()

    if not raw_name and not raw_company:
        return None

    detected_segment = (item.get("detected_segment") or "").strip()
    detected_region = (item.get("detected_region") or "").strip()

    full_text = f"{raw_title} {raw_text} {raw_company}".lower()
    detected_keywords = [k for k in _to_list(lead_source.query_keywords) if k.lower() in full_text]

    score = calculate_fit_score(
        {
            "title": raw_title,
            "segment": detected_segment,
            "company_stage": item.get("company_stage", ""),
            "source": lead_source.source_type,
            "notes": raw_text,
            "pain_signals": detected_keywords,
            "region_id": lead_source.region_id,
        },
        rules=ScoringRule.query.filter_by(brand_name=lead_source.brand_name, is_active=True).all(),
    )

    candidate = LeadCandidate(
        brand_name=lead_source.brand_name,
        lead_source_id=lead_source.id,
        research_job_id=research_job_id,
        region_id=lead_source.region_id,
        raw_name=raw_name,
        raw_company=raw_company,
        raw_title=raw_title,
        raw_url=raw_url,
        raw_text=raw_text,
        signal_summary=(item.get("signal_summary") or raw_text[:280]).strip(),
        detected_keywords=detected_keywords,
        detected_region=detected_region,
        detected_segment=detected_segment,
        confidence_score=int(item.get("confidence_score", 60) or 60),
        fit_score=score["fit_score"],
        score_breakdown=score["score_breakdown"],
        status="needs_review",
    )
    db.session.add(candidate)
    return candidate


def _set_next_run_at(lead_source, now=None):
    now = now or datetime.utcnow()
    if lead_source.run_frequency == "daily":
        lead_source.next_run_at = now + timedelta(days=1)
    elif lead_source.run_frequency == "weekly":
        lead_source.next_run_at = now + timedelta(days=7)
    elif lead_source.run_frequency == "monthly":
        lead_source.next_run_at = now + timedelta(days=30)
    else:
        lead_source.next_run_at = None


def run_source_research_job(lead_source, payload=None):
    payload = payload or {}
    adapter = get_adapter(lead_source.source_type)
    job = ResearchJob(
        lead_source_id=lead_source.id,
        status="running",
        started_at=datetime.utcnow(),
        run_log=f"Source run started via adapter={adapter.source_type}",
    )
    db.session.add(job)
    db.session.flush()

    warnings = adapter.validate_config(lead_source)
    if warnings:
        job.run_log = f"{job.run_log}. Config warnings: {'; '.join(warnings)}"

    try:
        fetched_items = adapter.fetch_candidates(lead_source, payload=payload) or []
    except Exception as exc:
        fetched_items = []
        job.status = "failed"
        job.completed_at = datetime.utcnow()
        job.error_message = str(exc)
        job.run_log = f"{job.run_log}. Adapter error: {exc}"
        db.session.commit()
        return job

    normalized_items = [adapter.normalize_candidate(item) for item in fetched_items]
    created = 0
    for item in normalized_items:
        c = create_candidate_from_manual(lead_source, item, research_job_id=job.id)
        if c:
            created += 1

    lead_source.last_run_at = datetime.utcnow()
    _set_next_run_at(lead_source, now=lead_source.last_run_at)

    job.status = "completed"
    job.completed_at = datetime.utcnow()
    job.results_count = len(normalized_items)
    job.candidates_created = created
    job.run_log = f"Processed {len(normalized_items)} item(s). Created {created} candidate(s)."

    update_source_performance(lead_source.id, lead_source.brand_name, lead_source.region_id)

    db.session.commit()
    return job


def run_manual_research_job(lead_source, manual_items):
    return run_source_research_job(lead_source, payload={"manual_items": manual_items})


def run_due_source_research_jobs(brand_name=None, source_id=None, limit=25):
    now = datetime.utcnow()
    q = LeadSource.query.filter(LeadSource.is_active.is_(True))

    if brand_name:
        q = q.filter(LeadSource.brand_name == brand_name)
    if source_id:
        q = q.filter(LeadSource.id == int(source_id))
    else:
        q = q.filter(LeadSource.run_frequency.in_(["daily", "weekly", "monthly"]))
        q = q.filter(
            (LeadSource.next_run_at.is_(None))
            | (LeadSource.next_run_at <= now)
        )

    sources = q.order_by(LeadSource.next_run_at.asc().nullsfirst(), LeadSource.updated_at.desc()).limit(limit).all()

    jobs = []
    for source in sources:
        jobs.append(run_source_research_job(source, payload={}))

    return {
        "run_at": now.isoformat(),
        "sources_considered": len(sources),
        "jobs_completed": len([j for j in jobs if j.status == "completed"]),
        "jobs_failed": len([j for j in jobs if j.status == "failed"]),
        "total_items_processed": sum((j.results_count or 0) for j in jobs),
        "total_candidates_created": sum((j.candidates_created or 0) for j in jobs),
        "jobs": jobs,
    }


def convert_candidate_to_lead(candidate, owner="", create_tasks=True):
    if candidate.is_do_not_contact or candidate.status == "do_not_contact":
        raise ValueError("Candidate is marked do_not_contact")

    payload = {
        "brand_name": candidate.brand_name,
        "first_name": candidate.raw_name.split(" ")[0] if candidate.raw_name else "",
        "last_name": " ".join(candidate.raw_name.split(" ")[1:]) if candidate.raw_name else "",
        "title": candidate.raw_title,
        "company_name": candidate.raw_company or "Unknown Company",
        "company_url": candidate.raw_url,
        "source": f"source:{candidate.lead_source_id}",
        "segment": candidate.detected_segment,
        "notes": candidate.signal_summary,
        "pain_signals": candidate.detected_keywords,
        "region_id": candidate.region_id,
    }

    duplicate = _lead_duplicate(candidate.brand_name, payload)
    if duplicate:
        candidate.status = "duplicate"
        db.session.commit()
        return duplicate

    score = calculate_fit_score(payload, rules=ScoringRule.query.filter_by(brand_name=candidate.brand_name, is_active=True).all())

    lead = Lead(
        brand_name=candidate.brand_name,
        region_id=candidate.region_id,
        owner=owner or candidate.reviewer or "",
        first_name=payload["first_name"],
        last_name=payload["last_name"],
        title=payload["title"],
        company_name=payload["company_name"],
        company_url=payload["company_url"],
        source=payload["source"],
        segment=payload["segment"],
        notes=payload["notes"],
        pain_signals=payload["pain_signals"],
        fit_score=score["fit_score"],
        score_breakdown=score["score_breakdown"],
        priority=score["priority"],
        status="researched",
    )
    db.session.add(lead)
    db.session.flush()

    candidate.status = "converted_to_lead"

    if create_tasks:
        lead.next_action_date = datetime.utcnow() + timedelta(days=2)
        upsert_followup_task(lead, summary="Initial outreach follow-up from approved candidate")

    db.session.commit()
    return lead


def _compute_source_quality(source_id):
    feedback = LeadFeedback.query.join(LeadCandidate, LeadFeedback.lead_candidate_id == LeadCandidate.id, isouter=True).filter(LeadCandidate.lead_source_id == source_id).all()
    if not feedback:
        return 0.0

    score_map = {
        "good_fit": 2,
        "strong_opportunity": 3,
        "positive_reply": 3,
        "booked_call": 4,
        "bad_fit": -2,
        "bad_source": -3,
        "duplicate": -1,
        "wrong_region": -1,
        "wrong_segment": -1,
        "do_not_contact": -2,
        "no_response": -1,
    }
    total = sum(score_map.get(f.feedback_type, 0) for f in feedback)
    return max(0.0, min(100.0, 50.0 + (total * 2.0)))


def update_source_performance(lead_source_id, brand_name, region_id=None):
    now = datetime.utcnow()
    period_start = datetime(now.year, now.month, 1)
    period_end = now

    perf = SourcePerformance.query.filter_by(
        brand_name=brand_name,
        lead_source_id=lead_source_id,
        region_id=region_id,
        period_start=period_start,
    ).first()

    if not perf:
        perf = SourcePerformance(
            brand_name=brand_name,
            lead_source_id=lead_source_id,
            region_id=region_id,
            period_start=period_start,
            period_end=period_end,
        )
        db.session.add(perf)

    perf.period_end = period_end
    perf.candidates_found = LeadCandidate.query.filter_by(lead_source_id=lead_source_id).count()
    perf.leads_approved = LeadCandidate.query.filter_by(lead_source_id=lead_source_id, status="converted_to_lead").count()
    perf.leads_rejected = LeadCandidate.query.filter(
        LeadCandidate.lead_source_id == lead_source_id,
        LeadCandidate.status.in_(["rejected", "duplicate", "do_not_contact"]),
    ).count()
    perf.quality_score = _compute_source_quality(lead_source_id)

    return perf


def capture_feedback(feedback_type, user, lead_id=None, lead_candidate_id=None, feedback_notes=""):
    if feedback_type not in FEEDBACK_TYPES:
        raise ValueError("Unsupported feedback_type")

    feedback = LeadFeedback(
        lead_id=lead_id,
        lead_candidate_id=lead_candidate_id,
        user=user,
        feedback_type=feedback_type,
        feedback_notes=feedback_notes,
    )
    db.session.add(feedback)

    if lead_id:
        lead = Lead.query.get(lead_id)
        if lead and feedback_type == "do_not_contact":
            lead.is_do_not_contact = True
            lead.status = "do_not_contact"

    if lead_candidate_id:
        candidate = LeadCandidate.query.get(lead_candidate_id)
        if candidate:
            if feedback_type == "duplicate":
                candidate.status = "duplicate"
            if feedback_type in {"bad_fit", "bad_source", "wrong_region", "wrong_segment", "too_early", "too_small"}:
                candidate.status = "rejected"
            if feedback_type == "do_not_contact":
                candidate.status = "do_not_contact"
                candidate.is_do_not_contact = True
            update_source_performance(candidate.lead_source_id, candidate.brand_name, candidate.region_id)

    db.session.commit()
    return feedback


def get_dashboard_summary(brand_name=None):
    q = Lead.query.filter_by(archived_at=None)
    if brand_name:
        q = q.filter_by(brand_name=brand_name)

    leads = q.all()
    now = datetime.utcnow()
    week_end = now + timedelta(days=7)

    by_region = Counter()
    by_status = Counter()
    by_owner = Counter()
    by_priority = Counter()

    calls_booked = 0
    proposals_sent = 0
    won = 0
    lost = 0
    due_this_week = 0

    region_map = {r.id: r.name for r in RegionProfile.query.all()}

    for lead in leads:
        by_region[region_map.get(lead.region_id, "Unassigned")] += 1
        by_status[lead.status] += 1
        by_owner[lead.owner or "Unassigned"] += 1
        by_priority[lead.priority or "low"] += 1

        if lead.status == "call_booked":
            calls_booked += 1
        if lead.status == "proposal_sent":
            proposals_sent += 1
        if lead.status == "won":
            won += 1
        if lead.status == "lost":
            lost += 1
        if lead.next_action_date and now <= lead.next_action_date <= week_end and lead.status != "do_not_contact":
            due_this_week += 1

    candidates_q = LeadCandidate.query
    if brand_name:
        candidates_q = candidates_q.filter_by(brand_name=brand_name)
    awaiting_review = candidates_q.filter_by(status="needs_review").count()

    source_perf_q = SourcePerformance.query
    if brand_name:
        source_perf_q = source_perf_q.filter_by(brand_name=brand_name)

    source_perf = [
        {
            "lead_source_id": s.lead_source_id,
            "quality_score": s.quality_score,
            "candidates_found": s.candidates_found,
            "leads_approved": s.leads_approved,
            "leads_rejected": s.leads_rejected,
        }
        for s in source_perf_q.order_by(SourcePerformance.updated_at.desc()).limit(10).all()
    ]

    return {
        "counts_by_region": dict(by_region),
        "counts_by_status": dict(by_status),
        "counts_by_owner": dict(by_owner),
        "counts_by_priority": dict(by_priority),
        "calls_booked": calls_booked,
        "proposals_sent": proposals_sent,
        "won": won,
        "lost": lost,
        "next_actions_due_this_week": due_this_week,
        "candidates_awaiting_review": awaiting_review,
        "source_performance": source_perf,
    }


def _seed_default_region(brand_name, payload):
    existing = RegionProfile.query.filter_by(brand_name=brand_name, slug=payload["slug"]).first()
    if existing:
        return existing
    region = RegionProfile(brand_name=brand_name, **payload)
    db.session.add(region)
    db.session.flush()
    return region


def _seed_default_template(brand_name, region_id, segment, channel, name, subject, body, cta):
    existing = OutreachTemplate.query.filter_by(
        brand_name=brand_name,
        region_id=region_id,
        segment=segment,
        channel=channel,
        template_name=name,
    ).first()
    if existing:
        return existing
    tpl = OutreachTemplate(
        brand_name=brand_name,
        region_id=region_id,
        segment=segment,
        channel=channel,
        template_name=name,
        subject_template=subject,
        body_template=body,
        cta=cta,
        variables=["first_name", "company_name", "primary_offer", "price_min", "currency"],
        is_active=True,
    )
    db.session.add(tpl)
    return tpl


def seed_buildly_defaults_if_present():
    buildly = Brand.query.filter(Brand.name.in_(["buildly", "buildly-marketplace"])) .first()
    if not buildly:
        return {"regions": 0, "templates": 0, "sources": 0, "rules": 0, "settings": 0}

    created = {"regions": 0, "templates": 0, "sources": 0, "rules": 0, "settings": 0}

    default_regions = [
        {
            "name": "US West Coast",
            "slug": "us-west-coast",
            "owner": "Greg",
            "countries": ["California", "Oregon", "Washington", "British Columbia"],
            "timezone_notes": "Primary overlap: Pacific Time",
            "primary_offer": "Starter AI-Native CTO",
            "entry_price_min": 2000,
            "entry_price_max": 4000,
            "currency": "USD",
            "target_segments": ["startup", "smb", "saas"],
            "preferred_channels": ["linkedin", "email", "referral"],
            "outreach_tone": "Direct founder-to-founder, technical credibility, startup velocity",
            "local_notes": "Focus on execution speed and technical clarity",
            "is_active": True,
        },
        {
            "name": "US East Coast",
            "slug": "us-east-coast",
            "owner": "Greg",
            "countries": ["New York", "Massachusetts", "DC", "Georgia", "Florida", "North Carolina"],
            "timezone_notes": "Primary overlap: Eastern Time",
            "primary_offer": "Starter/Growth AI-Native CTO",
            "entry_price_min": 2000,
            "entry_price_max": 4000,
            "currency": "USD",
            "target_segments": ["startup", "smb", "fintech", "b2b saas"],
            "preferred_channels": ["linkedin", "email", "vc_referral"],
            "outreach_tone": "Business outcome, risk reduction, due-diligence readiness",
            "local_notes": "Position technical leadership as investor confidence enabler",
            "is_active": True,
        },
        {
            "name": "Southeast Asia",
            "slug": "southeast-asia",
            "owner": "Gina",
            "countries": ["Singapore", "Vietnam", "Philippines", "Indonesia", "Malaysia", "Thailand", "Cambodia"],
            "timezone_notes": "Primary overlap: SGT / ICT",
            "primary_offer": "Technical Clarity Session / CTO Advisory",
            "entry_price_min": 750,
            "entry_price_max": 4000,
            "currency": "USD",
            "target_segments": ["founder-led", "agency-transition", "startup"],
            "preferred_channels": ["email", "community", "linkedin"],
            "outreach_tone": "Partnership-first, educational, lower pressure",
            "local_notes": "Emphasize practical advisory and phased engagement",
            "is_active": True,
        },
        {
            "name": "Europe",
            "slug": "europe",
            "owner": "Greg",
            "countries": ["UK", "Germany", "Netherlands", "Portugal", "Spain", "Nordics", "France"],
            "timezone_notes": "Primary overlap: CET / GMT",
            "primary_offer": "AI-Native CTO Starter",
            "entry_price_min": 2000,
            "entry_price_max": 4000,
            "currency": "EUR",
            "target_segments": ["open-source", "saas", "seed"],
            "preferred_channels": ["email", "linkedin", "oss_community"],
            "outreach_tone": "Transparent, open-source, process-driven",
            "local_notes": "Highlight RAD process and open-source credibility",
            "is_active": True,
        },
    ]

    regions_by_slug = {}
    for payload in default_regions:
        before = RegionProfile.query.filter_by(brand_name=buildly.name, slug=payload["slug"]).first()
        region = _seed_default_region(buildly.name, payload)
        if before is None:
            created["regions"] += 1
        regions_by_slug[region.slug] = region

    templates_before = OutreachTemplate.query.filter_by(brand_name=buildly.name).count()
    _seed_default_template(
        buildly.name,
        regions_by_slug.get("us-west-coast").id if regions_by_slug.get("us-west-coast") else None,
        "founder",
        "email",
        "US Founder CTO Message",
        "Technical leadership without a full-time CTO hire",
        "Hi {first_name},\n\nI work with founder-led teams that need strong technical leadership without the delay and cost of a full-time CTO hire. Buildly supports product and engineering velocity with AI-native CTO support from {currency} {price_min}/month.\n\nIf useful, I can share how we structure the first 30 days for execution clarity at {company_name}.",
        "Open to a 30-minute call next week?",
    )
    _seed_default_template(
        buildly.name,
        regions_by_slug.get("southeast-asia").id if regions_by_slug.get("southeast-asia") else None,
        "founder",
        "email",
        "SEA Partner Founder Message",
        "A practical technical clarity session for your next build phase",
        "Hi {first_name},\n\nWe support teams with partnership-first technical advisory and AI-native CTO guidance. For SEA teams, we often start with a technical clarity session and advisory options below typical US pricing.\n\nIf you want, I can share a lightweight roadmap format we use with growing product teams.",
        "Would a short intro call be useful?",
    )
    _seed_default_template(
        buildly.name,
        regions_by_slug.get("europe").id if regions_by_slug.get("europe") else None,
        "founder",
        "email",
        "Europe Founder OSS Message",
        "Transparent, process-driven AI-native CTO support",
        "Hi {first_name},\n\nBuildly works with product teams that value transparent execution, open-source practices, and practical delivery systems. Our AI-native CTO support helps teams reduce technical drag and improve release confidence.\n\nHappy to share how the RAD process can fit {company_name}.",
        "Would you be open to a 30-minute working session?",
    )
    _seed_default_template(
        buildly.name,
        None,
        "vc_accelerator",
        "email",
        "VC Accelerator Resource Message",
        "Technical leadership support for portfolio companies",
        "Hi {first_name},\n\nWe help portfolio companies close technical leadership gaps through fractional AI-native CTO support, product leadership, and delivery structure. Useful when teams are between hires or preparing for next milestones.\n\nIf relevant, I can share a short partner brief.",
        "Would you like a one-page overview for your portfolio support toolkit?",
    )
    templates_after = OutreachTemplate.query.filter_by(brand_name=buildly.name).count()
    created["templates"] = max(0, templates_after - templates_before)

    sources_before = LeadSource.query.filter_by(brand_name=buildly.name).count()
    source_seeds = [
        ("US West Coast founder CTO search", "google_search", "https://www.google.com/search?q=fractional+cto+startup+california", "Greg", "us-west-coast"),
        ("US East Coast fractional CTO search", "google_search", "https://www.google.com/search?q=fractional+cto+new+york+startup", "Greg", "us-east-coast"),
        ("SEA founder accelerator research", "website_directory", "", "Gina", "southeast-asia"),
        ("Europe open-source CTO research", "github", "https://github.com/search?q=api+gateway+microservices", "Greg", "europe"),
        ("Product Hunt new SaaS launches", "product_hunt", "https://www.producthunt.com/", "Greg", None),
        ("Hacker News Show HN", "hacker_news", "https://news.ycombinator.com/show", "Greg", None),
        ("GitHub API gateway projects", "github", "https://github.com/search?q=api+gateway+microservices", "Greg", None),
        ("Manual social post capture", "linkedin_manual", "", "Gina", None),
    ]

    positive_keywords = [
        "looking for CTO", "need a CTO", "hiring CIO", "technical cofounder", "technical partner",
        "fractional CTO", "interim CTO", "agency failed", "need technical leadership", "product roadmap",
        "technical debt", "dev team stuck", "preparing for fundraising", "need to scale engineering",
        "API gateway", "microservices", "product management help", "release management",
    ]
    negative_keywords = [
        "job seeker", "student project", "unpaid only", "free help", "internship only",
        "crypto scam", "adult", "gambling", "unrelated recruiting",
    ]

    for name, source_type, url, owner, region_slug in source_seeds:
        region_id = regions_by_slug.get(region_slug).id if region_slug and regions_by_slug.get(region_slug) else None
        existing = LeadSource.query.filter_by(brand_name=buildly.name, name=name).first()
        if existing:
            continue
        db.session.add(
            LeadSource(
                brand_name=buildly.name,
                region_id=region_id,
                name=name,
                source_type=source_type,
                url=url,
                query_keywords=positive_keywords,
                negative_keywords=negative_keywords,
                run_frequency="weekly",
                is_active=True,
                owner=owner,
                compliance_notes="Public/manual research only. No scraping of private data or auto-messaging.",
            )
        )
    sources_after = LeadSource.query.filter_by(brand_name=buildly.name).count()
    created["sources"] = max(0, sources_after - sources_before)

    rules_before = ScoringRule.query.filter_by(brand_name=buildly.name).count()
    default_rules = [
        ("Founder title match", "title_match", "founder", 15),
        ("Fractional CTO intent", "positive_keyword", "fractional cto", 15),
        ("Technical debt signal", "pain_signal", "technical debt", 15),
        ("Warm introduction", "warm_connection", "referral", 15),
        ("Student project exclusion", "negative_keyword", "student project", -20),
        ("No business relevance", "negative_keyword", "unrelated", -30),
    ]
    for name, rule_type, match_value, delta in default_rules:
        existing = ScoringRule.query.filter_by(brand_name=buildly.name, name=name).first()
        if existing:
            continue
        db.session.add(
            ScoringRule(
                brand_name=buildly.name,
                region_id=None,
                name=name,
                rule_type=rule_type,
                match_value=match_value,
                score_delta=delta,
                is_active=True,
            )
        )
    rules_after = ScoringRule.query.filter_by(brand_name=buildly.name).count()
    created["rules"] = max(0, rules_after - rules_before)

    if not LeadRadarSetting.query.filter_by(brand_name=buildly.name).first():
        db.session.add(
            LeadRadarSetting(
                brand_name=buildly.name,
                settings_json={
                    "module_name": "Lead Radar",
                    "safety_warning": "ForgeMarketing creates research notes and draft outreach only. Review all information manually and send only through approved channels in compliance with platform rules and applicable laws.",
                    "allow_auto_outreach": False,
                    "require_human_review": True,
                },
            )
        )
        created["settings"] += 1

    db.session.commit()
    return created

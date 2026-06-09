"""Public The Index submission endpoints for firstcityfoundry.com."""

from __future__ import annotations

from collections import defaultdict, deque
from datetime import date, datetime, timezone
import hashlib
import logging
import os
from pathlib import Path
import json
import time
from threading import Lock
from typing import Any, Dict, Optional
from uuid import uuid4
import csv
import io
from functools import wraps

from flask import Blueprint, jsonify, make_response, request, Response

from dashboard.models import db
from custom_modules.the_index.models import IndexSurveySubmission


logger = logging.getLogger(__name__)

index_submissions_bp = Blueprint("index_submissions", __name__, url_prefix="/api")

ALLOWED_CORS_ORIGINS = {
    "https://www.firstcityfoundry.com",
    "https://firstcityfoundry.com",
    "http://localhost:3000",
    "http://localhost:5173",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:5173",
}

MAX_POST_BYTES = 512 * 1024
MAX_STRING_LENGTH = 4000
MAX_ANSWER_KEYS = 500
MAX_ARRAY_ITEMS = 200
MAX_JSON_DEPTH = 8

POST_RATE_LIMIT_PER_MINUTE = 60
_rate_lock = Lock()
_rate_windows: Dict[str, deque] = {}

STRICT_INDEX_VALIDATION = os.getenv("THE_INDEX_STRICT_VALIDATION", "false").lower() in {"1", "true", "yes"}

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_SPOOL_PATH = _PROJECT_ROOT / "data" / "the_index_spool.jsonl"

RESERVED_PAYLOAD_KEYS = {
    "source",
    "submitted_page",
    "turnstile_token",
    "contact_email",
    "company_name",
    "reporting",
}

INDEX_REQUIRED_TEXT_FIELDS = {
    "contact_name_role",
    "ai_visibility_usage",
    "operational_bottleneck",
    "biggest_operational_challenge",
}

INDEX_REQUIRED_ENUM_FIELDS = {
    "operating_years": {"0_2_years", "3_5_years", "6_10_years", "10_plus_years"},
    "funding_pathway": {"bootstrapped", "angel_seed", "vc_series_a_plus", "traditional_debt", "private_equity"},
    "team_size": {"1_5", "6_15", "16_50", "51_150", "150_plus"},
    "annual_revenue_band": {"under_500k", "500k_1m", "1m_3m", "3m_5m", "5m_10m", "10m_plus", "prefer_not_to_say"},
    "backend_operations_state": {"manual_heavy", "siloed_tech", "automated_integrated", "ai_native"},
    "ai_budget_allocation": {"none", "testing", "active", "significant", "ai_first"},
    "decision_process": {"gut_instinct", "old_reports", "real_time_dashboards", "predictive_analytics"},
    "profitability_report_time": {"minutes", "hours", "days", "cannot_track"},
    "metrics_tracking": {"manual_spreadsheets", "automated_rarely_used", "daily_dashboard", "predictive_alerts", "not_systematic"},
    "first_scale_investment": {"hiring", "marketing", "operational_architecture", "product_development"},
    "margin_trend": {"margins_shrank", "margins_flat", "margins_expanded", "revenue_not_grown"},
    "manual_effort_area": {
        "lead_gen_sales",
        "client_onboarding_project_management",
        "fulfillment_service_delivery",
        "back_office_admin_invoicing",
        "mostly_automated",
    },
    "founder_absence_resilience": {"halt", "run_but_growth_stops", "run_smoothly", "continue_growing"},
    "knowledge_systematization": {"in_heads", "scattered_docs", "documented_sops", "integrated_ai_workflows"},
    "valuation_awareness": {"formal_12_months", "formal_older", "rough_idea", "no_idea", "not_interested"},
    "strategic_goal": {"build_to_sell", "pass_down", "lifestyle_business", "public_vc_scale"},
    "podcast_interest": {"yes_guest", "maybe", "ask_again", "no_thanks"},
}

INDEX_REQUIRED_ARRAY_ENUM_FIELDS = {
    "ai_margin_uses": {
        "customer_acquisition",
        "sales_pipeline",
        "customer_onboarding",
        "service_delivery",
        "invoicing_payments",
        "customer_support",
        "reporting_data_analysis",
        "not_yet",
        "other",
    },
    "podcast_topics": {
        "ai_operations",
        "scaling_1m_5m",
        "founder_extraction",
        "valuation_systems",
        "bootstrapped_vs_vc",
        "other",
    },
    "report_opt_in": {"yes_send_report"},
}


def _is_non_empty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _validate_basic_email(value: str) -> bool:
    return "@" in value and "." in value.split("@")[-1]


def _validate_index_source_contract(
    source: str,
    contact_email: str,
    company_name: str,
    answers: Dict[str, Any],
) -> list[str]:
    """Validate strict field contract for first_city_foundry_index submissions."""
    if source != "first_city_foundry_index":
        return []

    errors: list[str] = []

    if not company_name:
        errors.append("company_name is required")
    if not contact_email:
        errors.append("contact_email is required")
    elif not _validate_basic_email(contact_email):
        errors.append("contact_email must be a valid email")

    for field in sorted(INDEX_REQUIRED_TEXT_FIELDS):
        value = answers.get(field)
        if not _is_non_empty_string(value):
            errors.append(f"{field} is required")

    for field, allowed in INDEX_REQUIRED_ENUM_FIELDS.items():
        value = answers.get(field)
        if not _is_non_empty_string(value):
            errors.append(f"{field} is required")
            continue
        if value not in allowed:
            errors.append(f"{field} must be one of: {', '.join(sorted(allowed))}")

    for field, allowed in INDEX_REQUIRED_ARRAY_ENUM_FIELDS.items():
        value = answers.get(field)
        if not isinstance(value, list) or len(value) == 0:
            errors.append(f"{field} must be a non-empty array")
            continue
        if len(value) > MAX_ARRAY_ITEMS:
            errors.append(f"{field} has too many items")
            continue
        for item in value:
            if item not in allowed:
                errors.append(f"{field} contains invalid value: {item}")

    ai_margin_uses = answers.get("ai_margin_uses") if isinstance(answers.get("ai_margin_uses"), list) else []
    podcast_topics = answers.get("podcast_topics") if isinstance(answers.get("podcast_topics"), list) else []

    if "other" in ai_margin_uses and not _is_non_empty_string(answers.get("ai_margin_uses_other")):
        errors.append("ai_margin_uses_other is required when ai_margin_uses includes 'other'")

    if "other" in podcast_topics and not _is_non_empty_string(answers.get("podcast_topics_other")):
        errors.append("podcast_topics_other is required when podcast_topics includes 'other'")

    return errors


def _score_index_submission(answers: Dict[str, Any]) -> Dict[str, Any]:
    """Generate deterministic scoring metadata for dashboard ranking."""
    score_maps = {
        "backend_operations_state": {
            "manual_heavy": 20,
            "siloed_tech": 45,
            "automated_integrated": 75,
            "ai_native": 95,
        },
        "ai_budget_allocation": {
            "none": 10,
            "testing": 35,
            "active": 60,
            "significant": 80,
            "ai_first": 95,
        },
        "decision_process": {
            "gut_instinct": 20,
            "old_reports": 40,
            "real_time_dashboards": 75,
            "predictive_analytics": 95,
        },
        "profitability_report_time": {
            "cannot_track": 10,
            "days": 30,
            "hours": 65,
            "minutes": 95,
        },
        "metrics_tracking": {
            "not_systematic": 15,
            "manual_spreadsheets": 25,
            "automated_rarely_used": 50,
            "daily_dashboard": 75,
            "predictive_alerts": 95,
        },
        "founder_absence_resilience": {
            "halt": 15,
            "run_but_growth_stops": 40,
            "run_smoothly": 75,
            "continue_growing": 95,
        },
        "knowledge_systematization": {
            "in_heads": 10,
            "scattered_docs": 35,
            "documented_sops": 70,
            "integrated_ai_workflows": 95,
        },
        "margin_trend": {
            "revenue_not_grown": 20,
            "margins_shrank": 30,
            "margins_flat": 55,
            "margins_expanded": 85,
        },
    }

    readiness_fields = [
        "backend_operations_state",
        "ai_budget_allocation",
        "decision_process",
        "profitability_report_time",
        "metrics_tracking",
        "founder_absence_resilience",
        "knowledge_systematization",
    ]
    margin_fields = ["margin_trend"]

    readiness_scores = [score_maps[field].get(answers.get(field), 0) for field in readiness_fields]
    margin_scores = [score_maps[field].get(answers.get(field), 0) for field in margin_fields]

    readiness = int(sum(readiness_scores) / len(readiness_scores)) if readiness_scores else 0
    margin = int(sum(margin_scores) / len(margin_scores)) if margin_scores else 0

    ai_uses = answers.get("ai_margin_uses") if isinstance(answers.get("ai_margin_uses"), list) else []
    breadth_bonus = min(len([v for v in ai_uses if v != "other"]) * 3, 15)

    total_score = min(100, int((readiness * 0.7) + (margin * 0.2) + breadth_bonus))

    tier = "explore"
    if total_score >= 80:
        tier = "high_priority"
    elif total_score >= 60:
        tier = "qualified"

    return {
        "version": "index-v1",
        "readiness": readiness,
        "margin": margin,
        "breadth_bonus": breadth_bonus,
        "total_score": total_score,
        "tier": tier,
    }


def _spool_submission(record: Dict[str, Any]) -> bool:
    """Best-effort disk spool used only when DB write fails."""
    try:
        _SPOOL_PATH.parent.mkdir(parents=True, exist_ok=True)
        with _SPOOL_PATH.open("a", encoding="utf-8") as fp:
            fp.write(json.dumps(record, ensure_ascii=True) + "\n")
        return True
    except Exception as exc:
        logger.error("the_index spool_failed error=%s", exc)
        return False


def _error(status: int, message: str, request_id: str):
    response = jsonify({"ok": False, "error": message, "request_id": request_id})
    return _apply_cors(make_response(response, status))


def _get_origin() -> str:
    return (request.headers.get("Origin") or "").strip()


def _apply_cors(response):
    origin = _get_origin()
    if origin in ALLOWED_CORS_ORIGINS:
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Vary"] = "Origin"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type, X-Request-ID"
        response.headers["Access-Control-Allow-Methods"] = "POST, GET, OPTIONS"
    return response


def _sanitize_string(value: Any) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        value = str(value)
    value = " ".join(value.replace("\x00", "").split())
    return value[:MAX_STRING_LENGTH]


def _sanitize_json(value: Any, depth: int = 0) -> Any:
    if depth > MAX_JSON_DEPTH:
        return _sanitize_string(value)

    if isinstance(value, dict):
        out = {}
        for idx, (k, v) in enumerate(value.items()):
            if idx >= MAX_ANSWER_KEYS:
                break
            clean_key = _sanitize_string(k)[:255]
            if not clean_key:
                continue
            out[clean_key] = _sanitize_json(v, depth + 1)
        return out

    if isinstance(value, list):
        return [_sanitize_json(v, depth + 1) for v in value[:MAX_ARRAY_ITEMS]]

    if isinstance(value, tuple):
        return [_sanitize_json(v, depth + 1) for v in list(value)[:MAX_ARRAY_ITEMS]]

    if isinstance(value, (str, int, float, bool)) or value is None:
        return _sanitize_string(value) if isinstance(value, str) else value

    return _sanitize_string(value)


def _extract_client_ip() -> str:
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",")[0].strip()[:128]
    return (request.remote_addr or "")[:128]


def _get_request_id() -> str:
    incoming = _sanitize_string(request.headers.get("X-Request-ID", ""))[:64]
    return incoming or uuid4().hex


def _parse_iso_date(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    raw = value.strip()
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    dt = datetime.fromisoformat(raw)
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def _allow_rate_limit(client_ip: str) -> bool:
    now = time.time()
    cutoff = now - 60
    key = client_ip or "unknown"

    with _rate_lock:
        window = _rate_windows.get(key)
        if window is None:
            window = deque()
            _rate_windows[key] = window

        while window and window[0] < cutoff:
            window.popleft()

        if len(window) >= POST_RATE_LIMIT_PER_MINUTE:
            return False

        window.append(now)
        return True


def _to_row_dict(row: IndexSurveySubmission) -> Dict[str, Any]:
    return {
        "id": row.id,
        "submitted_at": row.submitted_at.replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")
        if row.submitted_at
        else None,
        "source": row.source,
        "submitted_page": row.submitted_page,
        "contact_email": row.contact_email,
        "company_name": row.company_name,
        "answers": row.answers or {},
        "reporting": row.reporting or {},
        "request_meta": row.request_meta or {},
    }


def _is_authenticated_request() -> bool:
    try:
        from flask_login import current_user

        return bool(getattr(current_user, "is_authenticated", False))
    except Exception:
        return False


def _require_read_auth_guard():
    if request.method in {"POST", "OPTIONS"}:
        return None
    if _is_authenticated_request():
        return None

    request_id = getattr(request, "_index_request_id", None) or _get_request_id()
    request._index_request_id = request_id
    return _error(401, "Authentication required", request_id)


def _build_filtered_query(
    source: str,
    email: str,
    from_dt: Optional[datetime],
    to_dt: Optional[datetime],
):
    query = IndexSurveySubmission.query
    if source:
        query = query.filter(IndexSurveySubmission.source == source)
    if email:
        query = query.filter(IndexSurveySubmission.contact_email.ilike(f"%{email}%"))
    if from_dt:
        query = query.filter(IndexSurveySubmission.submitted_at >= from_dt)
    if to_dt:
        query = query.filter(IndexSurveySubmission.submitted_at <= to_dt)
    return query


def _parse_ids_arg() -> list[str]:
    values = request.args.getlist("ids")
    parsed: list[str] = []
    for raw in values:
        for part in (raw or "").split(","):
            cleaned = _sanitize_string(part).strip()
            if cleaned:
                parsed.append(cleaned)
    # Preserve order, dedupe.
    seen = set()
    unique = []
    for item in parsed:
        if item in seen:
            continue
        seen.add(item)
        unique.append(item)
    return unique


@index_submissions_bp.before_request
def _capture_start_time():
    request._index_started_at = time.perf_counter()


@index_submissions_bp.before_request
def _enforce_read_auth():
    return _require_read_auth_guard()


@index_submissions_bp.after_request
def _log_and_set_headers(response):
    latency_ms = int((time.perf_counter() - getattr(request, "_index_started_at", time.perf_counter())) * 1000)
    request_id = getattr(request, "_index_request_id", None) or _get_request_id()
    response.headers["X-Request-ID"] = request_id

    logger.info(
        "the_index request_id=%s method=%s path=%s status=%s latency_ms=%s",
        request_id,
        request.method,
        request.path,
        response.status_code,
        latency_ms,
    )
    return _apply_cors(response)


@index_submissions_bp.route("/index-submissions", methods=["OPTIONS"])
def options_index_submissions():
    return _apply_cors(make_response("", 204))


@index_submissions_bp.route("/index-submissions/summary", methods=["OPTIONS"])
def options_index_submissions_summary():
    return _apply_cors(make_response("", 204))


@index_submissions_bp.route("/index-submissions/export", methods=["OPTIONS"])
def options_index_submissions_export():
    return _apply_cors(make_response("", 204))


@index_submissions_bp.route("/index-submissions", methods=["POST"])
def create_index_submission():
    request_id = _get_request_id()
    request._index_request_id = request_id

    origin = _get_origin()
    if origin and origin not in ALLOWED_CORS_ORIGINS:
        return _error(403, "Origin not allowed", request_id)

    if request.content_length and request.content_length > MAX_POST_BYTES:
        return _error(413, "Payload too large", request_id)

    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return _error(400, "Payload must be a JSON object", request_id)

    client_ip = _extract_client_ip()
    if not _allow_rate_limit(client_ip):
        return _error(429, "Rate limit exceeded", request_id)

    source = _sanitize_string(payload.get("source") or "first_city_foundry_index")[:255]
    submitted_page = _sanitize_string(payload.get("submitted_page") or "")[:500]
    contact_email = _sanitize_string(payload.get("contact_email") or "")[:255]
    company_name = _sanitize_string(payload.get("company_name") or "")[:255]

    reporting_payload = payload.get("reporting") or {}
    reporting = _sanitize_json(reporting_payload if isinstance(reporting_payload, dict) else {})
    if not submitted_page and isinstance(reporting, dict):
        submitted_page = _sanitize_string(reporting.get("submitted_page") or "")[:500]

    answers = {}
    for key, value in payload.items():
        if key in RESERVED_PAYLOAD_KEYS:
            continue
        clean_key = _sanitize_string(key)[:255]
        if not clean_key:
            continue
        answers[clean_key] = _sanitize_json(value)
        if len(answers) >= MAX_ANSWER_KEYS:
            break

    validation_errors = _validate_index_source_contract(
        source=source,
        contact_email=contact_email,
        company_name=company_name,
        answers=answers,
    )
    if validation_errors and STRICT_INDEX_VALIDATION:
        response = jsonify(
            {
                "ok": False,
                "error": "Validation failed",
                "request_id": request_id,
                "validation_errors": validation_errors,
            }
        )
        return _apply_cors(make_response(response, 400))

    index_scoring = None
    scoring_error = None
    if source == "first_city_foundry_index":
        try:
            index_scoring = _score_index_submission(answers)
        except Exception as exc:
            scoring_error = str(exc)
            logger.warning("the_index scoring_failed request_id=%s error=%s", request_id, exc)

    submission_uuid = uuid4().hex
    now_utc = datetime.utcnow()

    request_meta = {
        "client_ip": client_ip,
        "request_id": request_id,
        "client_fingerprint": hashlib.sha256(f"{client_ip}:{contact_email}".encode("utf-8")).hexdigest()[:24],
        "index_scoring": index_scoring,
    }
    if validation_errors:
        request_meta["validation_warnings"] = validation_errors
    if scoring_error:
        request_meta["scoring_warning"] = "index scoring unavailable for this submission"

    row = IndexSurveySubmission(
        id=submission_uuid,
        submitted_at=now_utc,
        source=source,
        submitted_page=submitted_page,
        contact_email=contact_email,
        company_name=company_name,
        answers=answers,
        reporting=reporting,
        request_meta=request_meta,
    )

    try:
        db.session.add(row)
        db.session.commit()
        submitted_at_iso = now_utc.replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")
        payload_out: Dict[str, Any] = {"ok": True, "submission_id": submission_uuid, "submitted_at": submitted_at_iso}
        if validation_errors:
            payload_out["warnings"] = ["submission accepted with validation warnings"]
            payload_out["validation_warnings"] = validation_errors
        if scoring_error:
            payload_out["warnings"] = payload_out.get("warnings", []) + ["scoring unavailable"]
        return _apply_cors(make_response(jsonify(payload_out), 201))
    except Exception as exc:
        db.session.rollback()
        logger.error("the_index db_write_failed request_id=%s error=%s", request_id, exc)

        spooled = _spool_submission(
            {
                "id": submission_uuid,
                "submitted_at": now_utc.replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z"),
                "source": source,
                "submitted_page": submitted_page,
                "contact_email": contact_email,
                "company_name": company_name,
                "answers": answers,
                "reporting": reporting,
                "request_meta": request_meta,
            }
        )

        if spooled:
            response = jsonify(
                {
                    "ok": True,
                    "queued": True,
                    "submission_id": submission_uuid,
                    "submitted_at": now_utc.replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z"),
                    "warnings": ["database temporarily unavailable; submission queued"],
                }
            )
            return _apply_cors(make_response(response, 202))

        return _error(503, "Submission temporarily unavailable", request_id)


@index_submissions_bp.route("/index-submissions", methods=["GET"])
def list_index_submissions():
    request_id = _get_request_id()
    request._index_request_id = request_id

    try:
        limit = int(request.args.get("limit", 50))
    except Exception:
        limit = 50
    limit = max(1, min(limit, 500))

    source = _sanitize_string(request.args.get("source") or "")[:255]
    email = _sanitize_string(request.args.get("email") or "")[:255]
    from_raw = request.args.get("from")
    to_raw = request.args.get("to")

    try:
        from_dt = _parse_iso_date(from_raw)
        to_dt = _parse_iso_date(to_raw)
    except Exception:
        return _error(400, "Invalid from/to date format", request_id)

    query = _build_filtered_query(source, email, from_dt, to_dt)

    total = query.count()
    rows = query.order_by(IndexSurveySubmission.submitted_at.desc()).limit(limit).all()

    response = jsonify({"total": total, "submissions": [_to_row_dict(row) for row in rows]})
    return _apply_cors(make_response(response, 200))


@index_submissions_bp.route("/index-submissions/summary", methods=["GET"])
def summary_index_submissions():
    request_id = _get_request_id()
    request._index_request_id = request_id

    rows = IndexSurveySubmission.query.order_by(IndexSurveySubmission.submitted_at.desc()).all()

    today_date = date.today()
    total = len(rows)
    today = 0

    by_source: Dict[str, int] = defaultdict(int)
    utm_source: Dict[str, int] = defaultdict(int)
    utm_medium: Dict[str, int] = defaultdict(int)
    utm_campaign: Dict[str, int] = defaultdict(int)

    for row in rows:
        if row.submitted_at and row.submitted_at.date() == today_date:
            today += 1

        src = row.source or ""
        if src:
            by_source[src] += 1

        utm = ((row.reporting or {}).get("utm") or {}) if isinstance(row.reporting, dict) else {}
        us = _sanitize_string(utm.get("source") or "")[:255]
        um = _sanitize_string(utm.get("medium") or "")[:255]
        uc = _sanitize_string(utm.get("campaign") or "")[:255]
        if us:
            utm_source[us] += 1
        if um:
            utm_medium[um] += 1
        if uc:
            utm_campaign[uc] += 1

    recent = [_to_row_dict(row) for row in rows[:5]]

    response = jsonify(
        {
            "total": total,
            "today": today,
            "by_source": dict(by_source),
            "utm": {
                "source": dict(utm_source),
                "medium": dict(utm_medium),
                "campaign": dict(utm_campaign),
            },
            "recent": recent,
        }
    )
    return _apply_cors(make_response(response, 200))


@index_submissions_bp.route("/index-submissions/<submission_id>", methods=["GET"])
def get_index_submission(submission_id: str):
    request_id = _get_request_id()
    request._index_request_id = request_id

    row = IndexSurveySubmission.query.get(submission_id)
    if not row:
        return _error(404, "Submission not found", request_id)

    return _apply_cors(make_response(jsonify({"submission": _to_row_dict(row)}), 200))


@index_submissions_bp.route("/index-submissions/export", methods=["GET"])
def export_index_submissions():
    request_id = _get_request_id()
    request._index_request_id = request_id

    fmt = _sanitize_string(request.args.get("format") or "json").lower()
    if fmt not in {"json", "csv"}:
        return _error(400, "format must be json or csv", request_id)

    source = _sanitize_string(request.args.get("source") or "")[:255]
    email = _sanitize_string(request.args.get("email") or "")[:255]
    from_raw = request.args.get("from")
    to_raw = request.args.get("to")

    try:
        from_dt = _parse_iso_date(from_raw)
        to_dt = _parse_iso_date(to_raw)
    except Exception:
        return _error(400, "Invalid from/to date format", request_id)

    ids = _parse_ids_arg()
    max_rows = 10000

    if ids:
        rows = (
            IndexSurveySubmission.query.filter(IndexSurveySubmission.id.in_(ids))
            .order_by(IndexSurveySubmission.submitted_at.desc())
            .limit(max_rows)
            .all()
        )
    else:
        rows = (
            _build_filtered_query(source, email, from_dt, to_dt)
            .order_by(IndexSurveySubmission.submitted_at.desc())
            .limit(max_rows)
            .all()
        )

    payload = [_to_row_dict(row) for row in rows]
    stamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")

    if fmt == "json":
        body = json.dumps(payload, ensure_ascii=True)
        resp = Response(body, mimetype="application/json")
        resp.headers["Content-Disposition"] = f"attachment; filename=index-submissions-{stamp}.json"
        return _apply_cors(resp)

    output = io.StringIO()
    writer = csv.DictWriter(
        output,
        fieldnames=[
            "id",
            "submitted_at",
            "source",
            "submitted_page",
            "contact_email",
            "company_name",
            "answers_json",
            "reporting_json",
            "request_meta_json",
        ],
    )
    writer.writeheader()
    for row in payload:
        writer.writerow(
            {
                "id": row.get("id", ""),
                "submitted_at": row.get("submitted_at", ""),
                "source": row.get("source", ""),
                "submitted_page": row.get("submitted_page", ""),
                "contact_email": row.get("contact_email", ""),
                "company_name": row.get("company_name", ""),
                "answers_json": json.dumps(row.get("answers", {}), ensure_ascii=True),
                "reporting_json": json.dumps(row.get("reporting", {}), ensure_ascii=True),
                "request_meta_json": json.dumps(row.get("request_meta", {}), ensure_ascii=True),
            }
        )

    resp = Response(output.getvalue(), mimetype="text/csv")
    resp.headers["Content-Disposition"] = f"attachment; filename=index-submissions-{stamp}.csv"
    return _apply_cors(resp)


@index_submissions_bp.route("/the-index", methods=["GET"])
def the_index_dashboard_page():
    from flask import render_template

    return render_template("the_index_dashboard.html", title="The Index")

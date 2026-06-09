"""Public The Index submission endpoints for firstcityfoundry.com."""

from __future__ import annotations

from collections import defaultdict, deque
from datetime import date, datetime, timezone
import hashlib
import logging
import time
from threading import Lock
from typing import Any, Dict, Optional
from uuid import uuid4

from flask import Blueprint, jsonify, make_response, request

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

RESERVED_PAYLOAD_KEYS = {
    "source",
    "submitted_page",
    "turnstile_token",
    "contact_email",
    "company_name",
    "reporting",
}


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


@index_submissions_bp.before_request
def _capture_start_time():
    request._index_started_at = time.perf_counter()


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

    submission_uuid = uuid4().hex
    now_utc = datetime.utcnow()

    row = IndexSurveySubmission(
        id=submission_uuid,
        submitted_at=now_utc,
        source=source,
        submitted_page=submitted_page,
        contact_email=contact_email,
        company_name=company_name,
        answers=answers,
        reporting=reporting,
        request_meta={
            "client_ip": client_ip,
            "request_id": request_id,
            "client_fingerprint": hashlib.sha256(f"{client_ip}:{contact_email}".encode("utf-8")).hexdigest()[:24],
        },
    )

    db.session.add(row)
    db.session.commit()

    submitted_at_iso = now_utc.replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")
    response = jsonify({"ok": True, "submission_id": submission_uuid, "submitted_at": submitted_at_iso})
    return _apply_cors(make_response(response, 201))


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

    query = IndexSurveySubmission.query
    if source:
        query = query.filter(IndexSurveySubmission.source == source)
    if email:
        query = query.filter(IndexSurveySubmission.contact_email.ilike(f"%{email}%"))
    if from_dt:
        query = query.filter(IndexSurveySubmission.submitted_at >= from_dt)
    if to_dt:
        query = query.filter(IndexSurveySubmission.submitted_at <= to_dt)

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

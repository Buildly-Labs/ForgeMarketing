"""POST /api/matching-intakes (public) plus login-gated review endpoints.

Mounted behind the gateway at /marketing/api/matching-intakes. Separate from
the Index blueprint and schema on purpose.
"""

from __future__ import annotations

import hashlib
import logging
import os
import time
from collections import deque
from datetime import datetime
from threading import Lock
from typing import Any, Dict
from uuid import uuid4

from flask import Blueprint, jsonify, make_response, request

from custom_modules.quarterly_room import matching
from custom_modules.quarterly_room.models import MatchingIntake
from custom_modules.quarterly_room.validation import validate_intake, clean_text
from dashboard.models import db

logger = logging.getLogger(__name__)

quarterly_room_bp = Blueprint("quarterly_room", __name__, url_prefix="/api")

ALLOWED_CORS_ORIGINS = {
    "https://www.firstcityfoundry.com",
    "https://firstcityfoundry.com",
    "http://localhost:3000",
    "http://localhost:5173",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:5173",
}
MAX_POST_BYTES = 128 * 1024
POST_RATE_LIMIT_PER_MINUTE = int(os.getenv("QUARTERLY_ROOM_RATE_LIMIT_PER_MINUTE", "10"))
REVIEW_STATUSES = ("received", "reviewed", "selected_for_agenda", "declined", "archived")

_rate_lock = Lock()
_rate_windows: Dict[str, deque] = {}


# ── helpers ────────────────────────────────────────────────────────────────
def _origin() -> str:
    return (request.headers.get("Origin") or "").strip()


def _apply_cors(response):
    origin = _origin()
    if origin in ALLOWED_CORS_ORIGINS:
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Vary"] = "Origin"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type, X-Request-ID"
        response.headers["Access-Control-Allow-Methods"] = "POST, OPTIONS"
        response.headers["Access-Control-Max-Age"] = "600"
    return response


def _request_id() -> str:
    return clean_text(request.headers.get("X-Request-ID", ""), 64) or uuid4().hex


def _json(body: dict, status: int):
    return _apply_cors(make_response(jsonify(body), status))


def _error(status: int, message: str, request_id: str, **extra):
    return _json({"ok": False, "error": message, "request_id": request_id, **extra}, status)


def _client_ip() -> str:
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",")[0].strip()[:128]
    return (request.remote_addr or "")[:128]


def _allow(ip: str) -> bool:
    now = time.time()
    with _rate_lock:
        window = _rate_windows.setdefault(ip or "unknown", deque())
        while window and window[0] < now - 60:
            window.popleft()
        if len(window) >= POST_RATE_LIMIT_PER_MINUTE:
            return False
        window.append(now)
        if len(_rate_windows) > 5000:  # bound memory under a distributed flood
            for key in [k for k, w in _rate_windows.items() if not w or w[-1] < now - 60]:
                _rate_windows.pop(key, None)
        return True


def _is_staff() -> bool:
    try:
        from flask_login import current_user
        return bool(getattr(current_user, "is_authenticated", False))
    except Exception:
        return False


def _staff_only():
    if _is_staff():
        return None
    return _error(401, "Authentication required", _request_id())


def _staff_view(row: MatchingIntake, include_contact: bool = True) -> Dict[str, Any]:
    """Reviewer view. Contact details are withheld unless permission is 'yes'
    for matching/agenda lists; the full intake view is for reviewers only."""
    data = {
        "id": row.id,
        "received_at": row.received_at.isoformat() + "Z",
        "quarter": row.quarter_label,
        "seat": row.seat,
        "name": row.person_name,
        "city": row.person_city,
        "company": row.company,
        "role": row.role,
        "revenue_bands": row.revenue_bands,
        "people_bands": row.people_bands,
        "problem_category": row.problem_category,
        "problem_statement": row.problem_statement,  # verbatim
        "event_skew": row.event_skew,
        "problem_details": row.problem_details,
        "commitments": row.commitments,
        "contact_permission": row.contact_permission,
        "is_hold": row.is_hold,
        "review_status": row.review_status,
        "eligibility": matching.eligibility(row),
    }
    if include_contact and matching.may_contact(row):
        data["email"] = row.person_email
    return data


# ── public intake ──────────────────────────────────────────────────────────
@quarterly_room_bp.route("/matching-intakes", methods=["OPTIONS"])
def options_matching_intakes():
    return _apply_cors(make_response("", 204))


@quarterly_room_bp.route("/matching-intakes", methods=["POST"])
def create_matching_intake():
    request_id = _request_id()

    if _origin() and _origin() not in ALLOWED_CORS_ORIGINS:
        return _error(403, "Origin not allowed", request_id)
    if request.content_length and request.content_length > MAX_POST_BYTES:
        return _error(413, "Payload too large", request_id)

    ip = _client_ip()
    if not _allow(ip):
        return _error(429, "Rate limit exceeded", request_id)

    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return _error(400, "Payload must be a JSON object", request_id)

    clean, errors = validate_intake(payload)
    if errors:
        return _error(400, "Validation failed", request_id, validation_errors=errors)

    now = datetime.utcnow()
    person = clean["person"]
    row = MatchingIntake(
        id=uuid4().hex,
        received_at=now,
        quarter_label=matching.quarter_label(now),
        schema_version=clean["schema_version"],
        intake_type=clean["intake_type"],
        seat=clean["seat"],
        person_name=person["name"],
        person_email=person["email"],
        person_city=person["city"],
        company=person["company"],
        role=person["role"],
        company_url=person["company_url"],
        company_description=person["company_description"],
        revenue_bands=clean["revenue_bands"],
        people_bands=clean["people_bands"],
        problem_category=clean["problem_category"],
        problem_statement=clean["problem_statement"],
        event_skew=clean["event_skew"],
        problem_details=clean["problem_details"],
        commitments=clean["commitments"],
        no_pitch_acknowledged=True,
        contact_permission=clean["contact_permission"],
        is_hold=clean["is_hold"],
        source=clean["source"],
        submitted_page=clean["submitted_page"],
        reporting=clean["reporting"],
        raw_payload=_stored_payload(payload),
        # Hash only; never store the raw IP address.
        request_meta={"client_fingerprint": hashlib.sha256(f"{ip}:{person['email']}".encode()).hexdigest()[:24],
                      "request_id": request_id},
        review_status="received",
    )
    try:
        db.session.add(row)
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        logger.error("quarterly_room db_write_failed request_id=%s error=%s", request_id, type(exc).__name__)
        return _error(503, "Submission temporarily unavailable", request_id)

    logger.info("quarterly_room received id=%s seat=%s hold=%s", row.id, row.seat, row.is_hold)  # no PII in logs
    return _json({"ok": True, "id": row.id, "status": "received"}, 201)


def _stored_payload(payload: dict) -> dict:
    from custom_modules.quarterly_room.validation import clean_json
    return clean_json(payload)


# ── staff review (login required; nothing here contacts anyone) ────────────
@quarterly_room_bp.route("/matching-intakes", methods=["GET"])
def list_matching_intakes():
    denied = _staff_only()
    if denied:
        return denied
    query = MatchingIntake.query
    for arg, col in (("quarter", MatchingIntake.quarter_label), ("seat", MatchingIntake.seat),
                     ("review_status", MatchingIntake.review_status)):
        value = clean_text(request.args.get(arg), 40)
        if value:
            query = query.filter(col == value)
    if request.args.get("include_holds") != "true":
        query = query.filter(MatchingIntake.is_hold.is_(False))
    rows = query.order_by(MatchingIntake.received_at.desc()).limit(500).all()
    return jsonify({"ok": True, "items": [_staff_view(r) for r in rows]})


@quarterly_room_bp.route("/matching-intakes/<intake_id>", methods=["GET"])
def get_matching_intake(intake_id):
    denied = _staff_only()
    if denied:
        return denied
    row = db.session.get(MatchingIntake, intake_id)
    if not row:
        return _error(404, "Not found", _request_id())
    return jsonify({"ok": True, "item": _staff_view(row)})


@quarterly_room_bp.route("/matching-intakes/<intake_id>/review", methods=["PATCH"])
def review_matching_intake(intake_id):
    denied = _staff_only()
    if denied:
        return denied
    request_id = _request_id()
    row = db.session.get(MatchingIntake, intake_id)
    if not row:
        return _error(404, "Not found", request_id)
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return _error(400, "Payload must be a JSON object", request_id)
    status = body.get("review_status")
    if status is not None:
        if status not in REVIEW_STATUSES:
            return _error(400, "Validation failed", request_id, validation_errors=[
                {"field": "review_status", "code": "invalid_value", "message": f"must be one of: {', '.join(REVIEW_STATUSES)}"}])
        row.review_status = status
    if "reviewer_notes" in body:
        row.reviewer_notes = clean_text(body.get("reviewer_notes"))
    row.reviewed_at = datetime.utcnow()
    db.session.commit()
    return jsonify({"ok": True, "item": _staff_view(row)})


@quarterly_room_bp.route("/matching-intakes/agenda", methods=["GET"])
def agenda_view():
    """Candidate problem statements (verbatim) for the quarter, and - for up to
    three statements a human has chosen via ?statement_ids= - who fits each.

    Providers only appear for a statement they match on category, size band and
    proof; connectors only on category with prior-introduction evidence; room
    builders whose last room was mostly sellers are listed as design
    contributors. Emails appear only where contact_permission is 'yes'."""
    denied = _staff_only()
    if denied:
        return denied
    request_id = _request_id()
    quarter = clean_text(request.args.get("quarter"), 10) or matching.quarter_label(datetime.utcnow())
    pool = [r for r in MatchingIntake.query.filter_by(quarter_label=quarter).all()
            if matching.in_matching_pool(r, quarter)]

    owners = [r for r in pool if matching.owner_eligible(r)]
    chosen_ids = [clean_text(i, 64) for i in request.args.get("statement_ids", "").split(",") if i.strip()]
    if len(chosen_ids) > 3:
        return _error(400, "Choose at most three agenda statements", request_id)

    result: Dict[str, Any] = {
        "ok": True,
        "quarter": quarter,
        "candidate_statements": [
            {"id": o.id, "category": o.problem_category, "revenue_band": o.revenue_bands[0],
             "statement": o.problem_statement} for o in owners],
        "agenda": [],
        "room_design_contributors": [_staff_view(r) for r in pool if matching.room_builder_can_design(r)],
    }
    by_id = {o.id: o for o in owners}
    for sid in chosen_ids:
        owner = by_id.get(sid)
        if not owner:
            return _error(404, f"statement {sid} is not an eligible statement for {quarter}", request_id)
        result["agenda"].append({
            "id": owner.id,
            "statement": owner.problem_statement,  # verbatim, never rewritten
            "category": owner.problem_category,
            "solvers": [_staff_view(s) for s in matching.solvers_for(owner, pool)],
            "connectors": [_staff_view(c) for c in matching.connectors_for(owner, pool)],
        })
    return jsonify(result)

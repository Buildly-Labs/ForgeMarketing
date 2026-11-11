"""Server-side validation and normalisation for Quarterly Room intakes."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

SCHEMA_VERSION = 1
INTAKE_TYPE = "quarterly_problem_solution_matching"

SEATS = ("problem_owner", "problem_solver", "connector", "room_builder")
REVENUE_BANDS = ("under_1m", "1m_10m", "over_10m", "no_pl")
PEOPLE_BANDS = ("just_me", "2_10", "11_50", "51_plus")
PROBLEM_CATEGORIES = (
    "visibility", "thin_margins", "founder_dependency", "build_gap",
    "customer_fit", "team_capacity", "capital_transition", "people_connection",
)
# Only "yes" permits outreach. The others are accepted so the form can offer a
# softer choice, but all of them mean "do not contact about a match or room".
CONTACT_PERMISSIONS = ("yes", "no", "ask_first", "not_sure")
HOLD_TOKENS = {"not_this_quarter", "hold", "skip_this_quarter"}

# Field names inside problem.details. The frontend varies these by seat; the
# aliases keep us tolerant. Edit here if the form's field names change.
PROBLEM_STATEMENT_KEYS = ("problem_statement", "statement", "problem", "problem_wording", "wording")
OWNER_COST_KEYS = ("ninety_day_cost", "cost_90_day", "cost_90_days", "ninety_day_cost_estimate")
SOLVER_RESULT_KEYS = ("result_change", "concrete_result", "result", "change_delivered")
SOLVER_PROOF_KEYS = ("result_proof", "proof", "proof_of_result", "evidence")
CONNECTOR_EVIDENCE_KEYS = (
    "prior_introduction", "prior_introduction_evidence", "introduction_evidence", "intro_evidence",
)

MAX_TEXT = 4000
MAX_ITEMS = 100
MAX_DEPTH = 6
_EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[^@\s]+\.[^@\s]{2,}$")
_CTRL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def clean_text(value: Any, limit: int = MAX_TEXT) -> str:
    """Strip control characters and cap length. Does NOT collapse whitespace,
    so problem wording is preserved verbatim."""
    if value is None:
        return ""
    if not isinstance(value, str):
        value = str(value)
    return _CTRL_RE.sub("", value).strip()[:limit]


def clean_json(value: Any, depth: int = 0) -> Any:
    if depth > MAX_DEPTH:
        return clean_text(value)
    if isinstance(value, dict):
        return {clean_text(k, 255): clean_json(v, depth + 1) for k, v in list(value.items())[:MAX_ITEMS]}
    if isinstance(value, list):
        return [clean_json(v, depth + 1) for v in value[:MAX_ITEMS]]
    if isinstance(value, (bool, int, float)) or value is None:
        return value
    return clean_text(value)


def first_present(details: Dict[str, Any], keys: Tuple[str, ...]) -> Any:
    for key in keys:
        if has_content(details.get(key)):
            return details[key]
    return None


def has_content(value: Any) -> bool:
    if value is None or isinstance(value, bool):
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (int, float)):
        return True
    if isinstance(value, (list, dict)):
        return any(has_content(v) for v in (value.values() if isinstance(value, dict) else value))
    return False


def detect_hold(quarter: Dict[str, Any]) -> bool:
    commitments = quarter.get("commitments")
    if isinstance(commitments, list):
        for item in commitments:
            if isinstance(item, str) and item.strip().lower().replace(" ", "_").replace("-", "_") in HOLD_TOKENS:
                return True
    if quarter.get("hold") is True:
        return True
    participation = quarter.get("participation")
    return isinstance(participation, str) and participation.strip().lower().replace(" ", "_") in HOLD_TOKENS


def _bands(value: Any, allowed: Tuple[str, ...], field: str, errors: List[dict]) -> List[str]:
    if value is None or value == "":
        return []
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        errors.append(_err(field, "invalid_type", "must be a list of band values"))
        return []
    out: List[str] = []
    for item in value:
        if not isinstance(item, str) or item not in allowed:
            errors.append(_err(field, "invalid_value", f"{item!r} is not one of: {', '.join(allowed)}"))
            continue
        if item not in out:
            out.append(item)
    return out


def _err(field: str, code: str, message: str) -> dict:
    return {"field": field, "code": code, "message": message}


def validate_intake(payload: Any) -> Tuple[Optional[Dict[str, Any]], List[dict]]:
    """Return (normalised, errors). normalised is None when errors is non-empty."""
    errors: List[dict] = []
    if not isinstance(payload, dict):
        return None, [_err("", "invalid_type", "payload must be a JSON object")]

    if payload.get("schema_version") != SCHEMA_VERSION or isinstance(payload.get("schema_version"), bool):
        errors.append(_err("schema_version", "invalid_value", f"must be {SCHEMA_VERSION}"))
    if payload.get("intake_type") != INTAKE_TYPE:
        errors.append(_err("intake_type", "invalid_value", f"must be {INTAKE_TYPE!r}"))
    seat = payload.get("seat")
    if seat not in SEATS:
        errors.append(_err("seat", "invalid_value", f"must be one of: {', '.join(SEATS)}"))
        seat = None

    person_in = payload.get("person")
    person_in = person_in if isinstance(person_in, dict) else {}
    if not isinstance(payload.get("person"), dict):
        errors.append(_err("person", "required", "person object is required"))
    person = {k: clean_text(person_in.get(k), 255) for k in ("name", "email", "city", "company", "role", "company_url")}
    person["company_description"] = clean_text(person_in.get("company_description"))
    person["email"] = person["email"].lower()
    for req in ("name", "email", "city"):
        if not person[req]:
            errors.append(_err(f"person.{req}", "required", f"{req} is required"))
    if person["email"] and not _EMAIL_RE.match(person["email"]):
        errors.append(_err("person.email", "invalid_value", "must be a valid email address"))
    if person["company_url"]:
        parsed = urlparse(person["company_url"] if "://" in person["company_url"] else f"https://{person['company_url']}")
        if parsed.scheme not in ("http", "https") or not parsed.netloc or "." not in parsed.netloc:
            errors.append(_err("person.company_url", "invalid_value", "must be a valid http(s) URL"))

    quarter_in = payload.get("quarter")
    if not isinstance(quarter_in, dict):
        errors.append(_err("quarter", "required", "quarter object is required"))
        quarter_in = {}
    is_hold = detect_hold(quarter_in)

    if quarter_in.get("no_pitch_acknowledged") is not True:
        errors.append(_err("quarter.no_pitch_acknowledged", "required", "the no-pitch acknowledgment must be true"))

    permission = quarter_in.get("contact_permission")
    if isinstance(permission, bool):
        permission = "yes" if permission else "no"
    if not isinstance(permission, str) or permission not in CONTACT_PERMISSIONS:
        errors.append(_err("quarter.contact_permission", "required",
                           f"a contact-permission choice is required: {', '.join(CONTACT_PERMISSIONS)}"))
        permission = "no"

    commitments = quarter_in.get("commitments", [])
    if not isinstance(commitments, list):
        errors.append(_err("quarter.commitments", "invalid_type", "must be a list"))
        commitments = []

    size_in = person_in.get("company_size")
    size_in = size_in if isinstance(size_in, dict) else {}
    revenue = _bands(size_in.get("revenue_bands"), REVENUE_BANDS, "person.company_size.revenue_bands", errors)
    people = _bands(size_in.get("people_bands"), PEOPLE_BANDS, "person.company_size.people_bands", errors)

    problem_in = payload.get("problem")
    problem_in = problem_in if isinstance(problem_in, dict) else {}
    category = problem_in.get("category")
    details = problem_in.get("details")
    if details is None:
        details = {}
    if not isinstance(details, dict):
        errors.append(_err("problem.details", "invalid_type", "must be an object"))
        details = {}
    if category not in (None, "") and category not in PROBLEM_CATEGORIES:
        errors.append(_err("problem.category", "invalid_value", f"must be one of: {', '.join(PROBLEM_CATEGORIES)}"))
        category = None

    if not is_hold and seat:
        if seat == "problem_owner":
            if len(revenue) != 1:
                errors.append(_err("person.company_size.revenue_bands", "invalid_count",
                                   "problem owners must select exactly one revenue band"))
            if len(people) != 1:
                errors.append(_err("person.company_size.people_bands", "invalid_count",
                                   "problem owners must select exactly one people band"))
            if not has_content(first_present(details, PROBLEM_STATEMENT_KEYS)):
                errors.append(_err("problem.details.problem_statement", "required", "problem wording is required"))
        else:
            if not revenue:
                errors.append(_err("person.company_size.revenue_bands", "required",
                                   "select at least one revenue band you work with"))
            if not people:
                errors.append(_err("person.company_size.people_bands", "required",
                                   "select at least one people band you work with"))
        if seat != "room_builder" and not category:
            errors.append(_err("problem.category", "required", "problem category is required"))

    if errors:
        return None, errors

    statement = first_present(details, PROBLEM_STATEMENT_KEYS)
    reporting = payload.get("reporting")
    reporting = clean_json(reporting) if isinstance(reporting, dict) else {}
    submitted_page = clean_text(payload.get("submitted_page") or reporting.get("submitted_page"), 500)

    return {
        "schema_version": SCHEMA_VERSION,
        "intake_type": INTAKE_TYPE,
        "seat": seat,
        "person": person,
        "revenue_bands": revenue,
        "people_bands": people,
        "problem_category": category or "",
        "problem_statement": clean_text(statement),
        "event_skew": clean_json(problem_in.get("event_skew")),
        "problem_details": clean_json(details),
        "commitments": clean_json(commitments),
        "no_pitch_acknowledged": True,
        "contact_permission": permission,
        "is_hold": is_hold,
        "source": clean_text(payload.get("source") or "first_city_foundry_quarterly_room", 255),
        "submitted_page": submitted_page,
        "reporting": reporting,
    }, []

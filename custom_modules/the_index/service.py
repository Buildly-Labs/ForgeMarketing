"""Service logic for The Index custom module."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, List
import json
import os

import requests

from dashboard.models import db
from custom_modules.the_index.models import IndexReportSnapshot, IndexSubmission


def normalize_submission_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize arbitrary form JSON into a stable internal shape."""
    fields = {
        "external_id": payload.get("external_id") or payload.get("id") or "",
        "submission_type": payload.get("submission_type") or payload.get("type") or "general",
        "submitter_name": payload.get("submitter_name") or payload.get("name") or "",
        "submitter_email": payload.get("submitter_email") or payload.get("email") or "",
        "organization": payload.get("organization") or payload.get("company") or "",
        "title": payload.get("title") or payload.get("subject") or "",
        "summary": payload.get("summary") or payload.get("message") or payload.get("description") or "",
        "submitted_at": payload.get("submitted_at") or payload.get("timestamp") or datetime.utcnow().isoformat(),
        "tags": payload.get("tags") or [],
    }

    known_keys = {
        "external_id",
        "id",
        "submission_type",
        "type",
        "submitter_name",
        "name",
        "submitter_email",
        "email",
        "organization",
        "company",
        "title",
        "subject",
        "summary",
        "message",
        "description",
        "submitted_at",
        "timestamp",
        "tags",
    }

    fields["custom_fields"] = {k: v for k, v in payload.items() if k not in known_keys}
    return fields


def _heuristic_analysis(normalized: Dict[str, Any]) -> Dict[str, Any]:
    summary_text = str(normalized.get("summary") or "")
    tags = normalized.get("tags") or []

    completeness = 0
    for key in ["submitter_name", "submitter_email", "organization", "title", "summary"]:
        if normalized.get(key):
            completeness += 20

    urgency_keywords = ["urgent", "asap", "immediately", "deadline", "today"]
    opportunity_keywords = ["partnership", "sponsor", "pilot", "budget", "enterprise", "contract"]

    text_lower = summary_text.lower()
    urgency_hits = sum(1 for k in urgency_keywords if k in text_lower)
    opportunity_hits = sum(1 for k in opportunity_keywords if k in text_lower)

    urgency_score = min(100, 20 + urgency_hits * 15)
    opportunity_score = min(100, 20 + opportunity_hits * 15 + len(tags) * 2)

    overall = int((completeness * 0.35) + (urgency_score * 0.25) + (opportunity_score * 0.40))

    risk_flags: List[str] = []
    if not normalized.get("submitter_email"):
        risk_flags.append("missing_email")
    if completeness < 60:
        risk_flags.append("incomplete_submission")
    if not normalized.get("summary"):
        risk_flags.append("missing_summary")

    recommendation = "review"
    if overall >= 75 and "missing_email" not in risk_flags:
        recommendation = "prioritize"
    elif overall < 45:
        recommendation = "request_more_info"

    return {
        "scoring_version": "heuristic-v1",
        "scores": {
            "completeness": completeness,
            "urgency": urgency_score,
            "opportunity": opportunity_score,
            "overall": overall,
        },
        "risk_flags": risk_flags,
        "recommendation": recommendation,
    }


def _try_ollama_json_analysis(normalized: Dict[str, Any], heuristic: Dict[str, Any]) -> Dict[str, Any]:
    if os.getenv("THE_INDEX_USE_OLLAMA", "false").lower() not in {"1", "true", "yes"}:
        return {}

    ollama_host = os.getenv("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
    model = os.getenv("THE_INDEX_OLLAMA_MODEL", "llama3.2:1b")

    prompt = (
        "You are analyzing an inbound business submission for a marketing team. "
        "Return JSON only with keys: executive_summary (string), insights (array of strings), "
        "risks (array of strings), follow_up_questions (array of strings), confidence (0-100 integer).\n"
        f"Normalized submission: {json.dumps(normalized)}\n"
        f"Heuristic analysis: {json.dumps(heuristic)}"
    )

    try:
        response = requests.post(
            f"{ollama_host}/api/generate",
            json={"model": model, "prompt": prompt, "stream": False, "format": "json"},
            timeout=20,
        )
        response.raise_for_status()
        data = response.json()
        text = data.get("response") or "{}"
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


def analyze_submission(submission: IndexSubmission, force: bool = False) -> Dict[str, Any]:
    """Run analysis and persist results onto the submission record."""
    if submission.ai_analysis and not force:
        return submission.ai_analysis

    normalized = submission.normalized_payload or normalize_submission_payload(submission.raw_payload or {})
    heuristic = _heuristic_analysis(normalized)
    llm = _try_ollama_json_analysis(normalized, heuristic)

    analysis = {
        "heuristic": heuristic,
        "llm": llm,
        "generated_at": datetime.utcnow().isoformat(),
    }

    recommendation = heuristic.get("recommendation", "review")
    ai_summary = (
        llm.get("executive_summary")
        if isinstance(llm, dict) and llm.get("executive_summary")
        else f"Overall score {heuristic['scores']['overall']} with recommendation: {recommendation}."
    )

    flags = heuristic.get("risk_flags", [])

    submission.normalized_payload = normalized
    submission.ai_analysis = analysis
    submission.ai_summary = ai_summary
    submission.report_flags = flags
    submission.analyzed_at = datetime.utcnow()
    submission.status = "analyzed"

    db.session.add(submission)
    db.session.commit()

    return analysis


def create_submission(payload: Dict[str, Any], source: str = "json_api") -> IndexSubmission:
    normalized = normalize_submission_payload(payload)

    submission = IndexSubmission(
        external_id=str(normalized.get("external_id") or ""),
        source=source,
        submission_type=str(normalized.get("submission_type") or "general"),
        submitter_name=str(normalized.get("submitter_name") or ""),
        submitter_email=str(normalized.get("submitter_email") or ""),
        organization=str(normalized.get("organization") or ""),
        title=str(normalized.get("title") or ""),
        raw_payload=payload,
        normalized_payload=normalized,
    )

    db.session.add(submission)
    db.session.commit()
    return submission


def build_overview_report(days: int = 30) -> Dict[str, Any]:
    cutoff = datetime.utcnow() - timedelta(days=days)
    rows = IndexSubmission.query.filter(IndexSubmission.received_at >= cutoff).all()

    by_status: Dict[str, int] = {}
    by_source: Dict[str, int] = {}
    by_type: Dict[str, int] = {}
    score_values: List[int] = []

    for row in rows:
        by_status[row.status] = by_status.get(row.status, 0) + 1
        by_source[row.source] = by_source.get(row.source, 0) + 1
        by_type[row.submission_type] = by_type.get(row.submission_type, 0) + 1

        overall = (((row.ai_analysis or {}).get("heuristic") or {}).get("scores") or {}).get("overall")
        if isinstance(overall, int):
            score_values.append(overall)

    average_score = round(sum(score_values) / len(score_values), 2) if score_values else None

    return {
        "window_days": days,
        "generated_at": datetime.utcnow().isoformat(),
        "submission_count": len(rows),
        "status_breakdown": by_status,
        "source_breakdown": by_source,
        "type_breakdown": by_type,
        "average_overall_score": average_score,
    }


def build_daily_volume_report(days: int = 14) -> Dict[str, Any]:
    cutoff = datetime.utcnow() - timedelta(days=days)
    rows = IndexSubmission.query.filter(IndexSubmission.received_at >= cutoff).all()

    counts: Dict[str, int] = {}
    for row in rows:
        key = row.received_at.date().isoformat()
        counts[key] = counts.get(key, 0) + 1

    series = [{"date": d, "count": counts[d]} for d in sorted(counts.keys())]
    return {
        "window_days": days,
        "generated_at": datetime.utcnow().isoformat(),
        "series": series,
    }


def create_report_snapshot(report_type: str, report_data: Dict[str, Any], generated_by: str = "system") -> IndexReportSnapshot:
    snapshot = IndexReportSnapshot(
        report_type=report_type,
        report_data=report_data,
        generated_by=generated_by,
    )
    db.session.add(snapshot)
    db.session.commit()
    return snapshot

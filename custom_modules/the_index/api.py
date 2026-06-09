"""Flask API blueprint for The Index custom module."""

from typing import Any, Dict

from flask import Blueprint, jsonify, request

from custom_modules.the_index.models import IndexReportSnapshot, IndexSubmission
from custom_modules.the_index.service import (
    analyze_submission,
    build_daily_volume_report,
    build_overview_report,
    create_report_snapshot,
    create_submission,
)


the_index_bp = Blueprint("the_index", __name__, url_prefix="/api/the-index")


def _submission_to_dict(row: IndexSubmission) -> Dict[str, Any]:
    return {
        "id": row.id,
        "external_id": row.external_id,
        "source": row.source,
        "submission_type": row.submission_type,
        "submitter_name": row.submitter_name,
        "submitter_email": row.submitter_email,
        "organization": row.organization,
        "title": row.title,
        "status": row.status,
        "priority": row.priority,
        "normalized_payload": row.normalized_payload or {},
        "ai_analysis": row.ai_analysis or {},
        "ai_summary": row.ai_summary,
        "report_flags": row.report_flags or [],
        "received_at": row.received_at.isoformat() if row.received_at else None,
        "analyzed_at": row.analyzed_at.isoformat() if row.analyzed_at else None,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def _snapshot_to_dict(row: IndexReportSnapshot) -> Dict[str, Any]:
    return {
        "id": row.id,
        "report_type": row.report_type,
        "window_start": row.window_start.isoformat() if row.window_start else None,
        "window_end": row.window_end.isoformat() if row.window_end else None,
        "report_data": row.report_data or {},
        "generated_by": row.generated_by,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


@the_index_bp.route("/health", methods=["GET"])
def health_check():
    return jsonify({"success": True, "module": "the-index", "status": "ok"}), 200


@the_index_bp.route("/submissions", methods=["POST"])
def create_submission_endpoint():
    payload = request.get_json(silent=True) or {}
    if not isinstance(payload, dict) or not payload:
        return jsonify({"success": False, "error": "Expected non-empty JSON object"}), 400

    source = request.args.get("source", "json_api")
    analyze_now = str(request.args.get("analyze", "true")).lower() in {"1", "true", "yes"}

    row = create_submission(payload, source=source)
    if analyze_now:
        analyze_submission(row)

    return jsonify({"success": True, "submission": _submission_to_dict(row)}), 201


@the_index_bp.route("/submissions/bulk", methods=["POST"])
def create_submission_bulk_endpoint():
    payload = request.get_json(silent=True) or {}
    items = payload.get("items") if isinstance(payload, dict) else None
    if not isinstance(items, list) or not items:
        return jsonify({"success": False, "error": "Expected payload.items as non-empty list"}), 400

    created = []
    for item in items:
        if not isinstance(item, dict):
            continue
        row = create_submission(item, source="json_api_bulk")
        analyze_submission(row)
        created.append(_submission_to_dict(row))

    return jsonify({"success": True, "count": len(created), "submissions": created}), 201


@the_index_bp.route("/submissions", methods=["GET"])
def list_submissions_endpoint():
    status = request.args.get("status")
    source = request.args.get("source")
    limit = max(1, min(int(request.args.get("limit", 50)), 250))
    offset = max(0, int(request.args.get("offset", 0)))

    query = IndexSubmission.query
    if status:
        query = query.filter(IndexSubmission.status == status)
    if source:
        query = query.filter(IndexSubmission.source == source)

    total = query.count()
    rows = query.order_by(IndexSubmission.created_at.desc()).offset(offset).limit(limit).all()

    return jsonify(
        {
            "success": True,
            "total": total,
            "limit": limit,
            "offset": offset,
            "submissions": [_submission_to_dict(row) for row in rows],
        }
    ), 200


@the_index_bp.route("/submissions/<int:submission_id>", methods=["GET"])
def get_submission_endpoint(submission_id: int):
    row = IndexSubmission.query.get(submission_id)
    if not row:
        return jsonify({"success": False, "error": "Submission not found"}), 404
    return jsonify({"success": True, "submission": _submission_to_dict(row)}), 200


@the_index_bp.route("/submissions/<int:submission_id>/analyze", methods=["POST"])
def analyze_submission_endpoint(submission_id: int):
    row = IndexSubmission.query.get(submission_id)
    if not row:
        return jsonify({"success": False, "error": "Submission not found"}), 404

    force = bool((request.get_json(silent=True) or {}).get("force"))
    analysis = analyze_submission(row, force=force)

    return jsonify(
        {
            "success": True,
            "submission": _submission_to_dict(row),
            "analysis": analysis,
        }
    ), 200


@the_index_bp.route("/submissions/<int:submission_id>/status", methods=["POST"])
def update_submission_status_endpoint(submission_id: int):
    row = IndexSubmission.query.get(submission_id)
    if not row:
        return jsonify({"success": False, "error": "Submission not found"}), 404

    payload = request.get_json(silent=True) or {}
    new_status = (payload.get("status") or "").strip()
    if not new_status:
        return jsonify({"success": False, "error": "status is required"}), 400

    row.status = new_status
    if payload.get("priority"):
        row.priority = str(payload.get("priority"))

    from dashboard.models import db

    db.session.add(row)
    db.session.commit()

    return jsonify({"success": True, "submission": _submission_to_dict(row)}), 200


@the_index_bp.route("/reports/overview", methods=["GET"])
def report_overview_endpoint():
    days = max(1, min(int(request.args.get("days", 30)), 365))
    report = build_overview_report(days=days)
    return jsonify({"success": True, "report": report}), 200


@the_index_bp.route("/reports/daily-volume", methods=["GET"])
def report_daily_volume_endpoint():
    days = max(1, min(int(request.args.get("days", 14)), 365))
    report = build_daily_volume_report(days=days)
    return jsonify({"success": True, "report": report}), 200


@the_index_bp.route("/reports/snapshots", methods=["POST"])
def create_snapshot_endpoint():
    payload = request.get_json(silent=True) or {}
    report_type = str(payload.get("report_type") or "overview")

    if report_type == "daily-volume":
        report = build_daily_volume_report(days=int(payload.get("days", 14)))
    else:
        report = build_overview_report(days=int(payload.get("days", 30)))

    snapshot = create_report_snapshot(
        report_type=report_type,
        report_data=report,
        generated_by=str(payload.get("generated_by") or "system"),
    )

    return jsonify({"success": True, "snapshot": _snapshot_to_dict(snapshot)}), 201


@the_index_bp.route("/reports/snapshots", methods=["GET"])
def list_snapshots_endpoint():
    limit = max(1, min(int(request.args.get("limit", 25)), 100))
    rows = (
        IndexReportSnapshot.query.order_by(IndexReportSnapshot.created_at.desc())
        .limit(limit)
        .all()
    )
    return jsonify(
        {
            "success": True,
            "count": len(rows),
            "snapshots": [_snapshot_to_dict(row) for row in rows],
        }
    ), 200

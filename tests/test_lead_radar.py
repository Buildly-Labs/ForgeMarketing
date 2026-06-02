#!/usr/bin/env python3
"""Lead Radar smoke + CRUD tests."""

import io
import os
import sys
import time
from pathlib import Path

# Ensure project root on path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
os.chdir(PROJECT_ROOT)

from dashboard.app import app, db  # noqa: E402
from dashboard.models import Brand  # noqa: E402
from dashboard.database import DatabaseManager  # noqa: E402
from dashboard.lead_radar_models import RegionProfile, Lead, LeadSource, LeadCandidate, ScoringRule  # noqa: E402


def _ensure_brand(brand_name: str):
    brand = Brand.query.filter_by(name=brand_name).first()
    if brand:
        return brand
    brand = Brand(
        name=brand_name,
        display_name="Lead Radar Test Brand",
        description="Test brand for Lead Radar",
        is_active=True,
    )
    db.session.add(brand)
    db.session.commit()
    return brand


def _create_region(client, brand_name: str):
    payload = {
        "brand_name": brand_name,
        "name": "Test Region",
        "slug": f"test-region-{int(time.time())}",
        "owner": "tester",
        "countries": ["Testland"],
        "primary_offer": "Starter",
        "entry_price_min": 1000,
        "entry_price_max": 2000,
        "currency": "USD",
    }
    r = client.post("/api/leads/regions", json=payload)
    assert r.status_code in (200, 201), r.get_data(as_text=True)
    return r.get_json()["data"]


def test_lead_radar_end_to_end():
    brand_name = f"lrtest-{int(time.time())}"

    with app.app_context():
        db.create_all()
        DatabaseManager(app).init_db()
        _ensure_brand(brand_name)

    with app.test_client() as client:
        # 1) Create region
        region = _create_region(client, brand_name)
        assert region["brand_name"] == brand_name

        # 2) Create lead source
        source_payload = {
            "brand_name": brand_name,
            "region_id": region["id"],
            "name": "Manual LinkedIn Capture",
            "source_type": "linkedin_manual",
            "owner": "tester",
            "query_keywords": ["looking for CTO", "technical debt"],
        }
        r = client.post("/api/lead-radar/sources", json=source_payload)
        assert r.status_code == 201, r.get_data(as_text=True)
        source = r.get_json()["data"]

        # 3) Run manual research job
        r = client.post(
            "/api/lead-radar/research-jobs/run",
            json={
                "lead_source_id": source["id"],
                "manual_items": [
                    {
                        "name": "Jane Founder",
                        "company": "SignalCo",
                        "title": "Founder",
                        "url": "https://example.com/post/1",
                        "text": "Founder looking for CTO support and technical debt reduction after launch",
                        "detected_segment": "startup",
                        "detected_region": "Test Region",
                    }
                ],
            },
        )
        assert r.status_code == 200, r.get_data(as_text=True)
        job_data = r.get_json()["data"]
        assert job_data["candidates_created"] >= 1

        # 4) Verify candidate exists
        r = client.get(f"/api/lead-radar/candidates?brand_name={brand_name}")
        assert r.status_code == 200
        candidates = r.get_json()["data"]
        assert len(candidates) >= 1
        candidate_id = candidates[0]["id"]

        # 5) Create scoring rule and score lead
        rule_payload = {
            "brand_name": brand_name,
            "name": "CTO keyword boost",
            "rule_type": "positive_keyword",
            "match_value": "cto",
            "score_delta": 12,
        }
        r = client.post("/api/lead-radar/rules", json=rule_payload)
        assert r.status_code == 201

        # 6) Approve candidate review and convert to lead
        r = client.post(
            f"/api/lead-radar/candidates/{candidate_id}/review",
            json={"action": "approve", "reviewer": "qa"},
        )
        assert r.status_code == 200
        assert r.get_json()["data"]["status"] == "approved"

        r = client.post(
            f"/api/lead-radar/candidates/{candidate_id}/convert",
            json={"owner": "qa", "create_tasks": True},
        )
        assert r.status_code == 200, r.get_data(as_text=True)
        lead = r.get_json()["data"]
        lead_id = lead["id"]

        # 7) Score lead endpoint
        r = client.post(f"/api/leads/{lead_id}/score", json={})
        assert r.status_code == 200
        scored = r.get_json()["data"]
        assert scored["fit_score"] >= 0
        assert scored["priority"] in {"low", "medium", "high", "hot"}

        # 8) Create lead activity
        r = client.post(
            f"/api/leads/{lead_id}/activities",
            json={
                "activity_type": "follow_up",
                "channel": "email",
                "subject": "Follow-up note",
                "body": "Manual follow-up planned",
            },
        )
        assert r.status_code == 201

        # 9) Generate draft activity (allowed)
        r = client.post(f"/api/leads/{lead_id}/generate-draft", json={"channel": "email"})
        assert r.status_code == 200, r.get_data(as_text=True)
        draft = r.get_json()["data"]
        assert "warning" in draft

        # 10) Feedback capture
        r = client.post(
            "/api/lead-radar/feedback",
            json={
                "user": "qa",
                "lead_id": lead_id,
                "lead_candidate_id": candidate_id,
                "feedback_type": "good_fit",
                "feedback_notes": "Looks aligned",
            },
        )
        assert r.status_code == 201

        # 11) do_not_contact enforcement
        r = client.put(f"/api/leads/{lead_id}", json={"status": "do_not_contact", "is_do_not_contact": True})
        assert r.status_code == 200

        r = client.post(f"/api/leads/{lead_id}/generate-draft", json={"channel": "email"})
        assert r.status_code in (400, 403)

        # 12) CSV import
        csv_text = """first_name,last_name,title,company_name,company_url,linkedin_url,email,country,city,company_stage,segment,source,pain_signals,region,owner,notes
Alex,Ops,COO,ImportCo,https://importco.test,https://linkedin.com/in/alex,alex@importco.test,Testland,City,seed,startup,csv_import,technical debt,Test Region,qa,imported from csv
"""
        data = {
            "brand_name": brand_name,
            "file": (io.BytesIO(csv_text.encode("utf-8")), "leads.csv"),
        }
        r = client.post("/api/leads/import-csv", data=data, content_type="multipart/form-data")
        assert r.status_code == 200, r.get_data(as_text=True)
        import_result = r.get_json()["data"]
        assert import_result["created"] >= 1

        # 13) Summary endpoint
        r = client.get(f"/api/leads/dashboard-summary?brand_name={brand_name}")
        assert r.status_code == 200
        summary = r.get_json()["data"]
        assert "counts_by_region" in summary
        assert "next_actions_due_this_week" in summary

        # 14) ensure source list works
        r = client.get(f"/api/lead-radar/sources?brand_name={brand_name}")
        assert r.status_code == 200
        assert len(r.get_json()["data"]) >= 1


if __name__ == "__main__":
    # simple direct run
    test_lead_radar_end_to_end()
    print("Lead Radar tests passed")

from pathlib import Path

import dashboard.app as dashboard_app
import automation.contacts_manager as cm


def _seed_brand(client):
    payload = {
        "provider": "do_agent",
        "url": "https://upssgpoiscmhlp3uuvm65hyn.agents.do-ai.run",
        "model": "gpt-4o-mini",
        "token": "",
    }
    client.post("/api/onboarding/save-ai", json=payload)


def test_ai_test_endpoint_handles_do_agent_shape(monkeypatch):
    app = dashboard_app.app
    client = app.test_client()

    class FakeResp:
        status_code = 200
        text = "ok"

        def json(self):
            return {"response": "ok"}

    monkeypatch.setattr(dashboard_app.requests, "post", lambda *a, **k: FakeResp())

    res = client.post(
        "/api/onboarding/test-ai",
        json={
            "provider": "do_agent",
            "url": "https://example-agent",
            "model": "gpt-4o-mini",
            "token": "",
        },
    )
    assert res.status_code == 200
    data = res.get_json()
    assert data["success"] is True


def test_contacts_import_csv_endpoint_roundtrip(monkeypatch, tmp_path):
    monkeypatch.setattr(cm, "project_root", Path(tmp_path))
    app = dashboard_app.app
    client = app.test_client()

    csv_text = "First Name,Last Name,Email,Region\nJamie,Lee,jamie.lee.integration@example.com,SE Asia\n"

    dry = client.post(
        "/api/contacts/import-csv",
        json={
            "csv_text": csv_text,
            "brand": "buildly",
            "dry_run": True,
        },
    )
    assert dry.status_code == 200
    dry_data = dry.get_json()
    assert dry_data["success"] is True

    imp = client.post(
        "/api/contacts/import-csv",
        json={
            "csv_text": csv_text,
            "brand": "buildly",
            "mapping": dry_data["auto_mapping"],
            "source_label": "integration_test",
            "contact_type": "lead",
            "dry_run": False,
        },
    )
    assert imp.status_code == 200
    imp_data = imp.get_json()
    assert imp_data["success"] is True
    assert imp_data["imported"] == 1


def test_influencer_discovery_endpoint_reports_empty_with_error(monkeypatch):
    app = dashboard_app.app
    client = app.test_client()

    # Ensure discovery path is available and deterministic for test
    monkeypatch.setattr(dashboard_app, "INFLUENCER_SYSTEM_AVAILABLE", True)
    monkeypatch.setattr(dashboard_app, "ensure_brand_strategy", lambda brand: {"name": brand})

    class FakeDiscovery:
        async def discover_brand_influencers(self, brand, max_per_platform):
            return {"bluesky": [], "youtube": []}

    monkeypatch.setattr(dashboard_app, "BrandInfluencerDiscovery", lambda: FakeDiscovery())

    res = client.post("/api/influencers/discover/buildly", json={"max_per_platform": 3})
    assert res.status_code == 424
    data = res.get_json()
    assert data["success"] is False
    assert "zero influencer candidates" in data["error"].lower()


def test_api_status_contains_readiness_block(monkeypatch):
    app = dashboard_app.app
    client = app.test_client()

    # Keep runtime check deterministic and lightweight
    monkeypatch.setattr(dashboard_app.dashboard, "test_ai_connection", lambda: True)
    monkeypatch.setattr(dashboard_app, "CONTACTS_SYSTEM_AVAILABLE", True)
    monkeypatch.setattr(dashboard_app, "INFLUENCER_SYSTEM_AVAILABLE", True)

    class FakeContactsManager:
        def get_contacts(self, limit=100):
            return [{"id": 1}]

    class FakeDiscovery:
        def get_brand_influencers(self):
            return [{"id": 1}]

    monkeypatch.setattr(dashboard_app, "BrandInfluencerDiscovery", lambda: FakeDiscovery())
    import automation.contacts_manager as contacts_mod
    monkeypatch.setattr(contacts_mod, "UnifiedContactsManager", FakeContactsManager)

    res = client.get("/api/status")
    assert res.status_code == 200
    data = res.get_json()
    assert "core_dependencies" in data
    assert "system_ready" in data

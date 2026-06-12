from pathlib import Path

import automation.contacts_manager as cm


def _new_manager(monkeypatch, tmp_path):
    monkeypatch.setattr(cm, "project_root", Path(tmp_path))
    manager = cm.UnifiedContactsManager()
    return manager


def test_import_csv_derives_name_from_first_last(monkeypatch, tmp_path):
    manager = _new_manager(monkeypatch, tmp_path)

    rows = [
        {
            "First Name": "Jamie",
            "Last Name": "Lee",
            "Email": "jamie.lee@example.com",
            "Region": "SE Asia",
        }
    ]
    mapping = {
        "First Name": "first_name",
        "Last Name": "last_name",
        "Email": "email",
        "Region": "region",
    }

    result = manager.import_from_csv(
        rows=rows,
        mapping=mapping,
        source_label="test_csv",
        contact_type="lead",
        brand="buildly",
    )

    assert result["imported"] == 1
    assert result["skipped"] == 0

    saved = manager.get_contacts(brand="buildly", limit=10)
    assert len(saved) == 1
    assert saved[0]["name"] == "Jamie Lee"
    assert saved[0]["first_name"] == "Jamie"
    assert saved[0]["last_name"] == "Lee"
    assert saved[0]["region"] == "SE Asia"


def test_create_and_update_extended_contact_fields(monkeypatch, tmp_path):
    manager = _new_manager(monkeypatch, tmp_path)

    contact_id = manager.create_contact(
        {
            "brand": "buildly",
            "first_name": "Ava",
            "last_name": "Nguyen",
            "contact_title": "Dr",
            "email": "ava.nguyen@example.com",
            "city": "Singapore",
            "state": "Central",
            "country": "Singapore",
            "region": "SE Asia",
            "contact_type": "lead",
            "source": "manual",
        }
    )

    created = manager.get_contact(contact_id)
    assert created["name"] == "Ava Nguyen"
    assert created["contact_title"] == "Dr"
    assert created["city"] == "Singapore"
    assert created["region"] == "SE Asia"

    ok = manager.update_contact(
        contact_id,
        {
            "first_name": "Avery",
            "last_name": "Ng",
            "city": "Bangkok",
            "region": "SEA",
        },
    )
    assert ok is True

    updated = manager.get_contact(contact_id)
    assert updated["name"] == "Avery Ng"
    assert updated["first_name"] == "Avery"
    assert updated["last_name"] == "Ng"
    assert updated["city"] == "Bangkok"
    assert updated["region"] == "SEA"

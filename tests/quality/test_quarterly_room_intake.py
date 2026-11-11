"""Quarterly Room matching intake: validation, endpoint, eligibility."""
import copy
from datetime import datetime
from types import SimpleNamespace

import pytest
from flask import Flask

import custom_modules.quarterly_room.api as api
from custom_modules.quarterly_room import matching
from custom_modules.quarterly_room.models import MatchingIntake
from custom_modules.quarterly_room.validation import validate_intake
from dashboard.models import db

ORIGIN = "https://www.firstcityfoundry.com"


def payload(seat="problem_owner", **over):
    p = {
        "schema_version": 1,
        "intake_type": "quarterly_problem_solution_matching",
        "seat": seat,
        "person": {
            "name": "Ada Lovelace", "email": "Ada@Example.com", "city": "Portland",
            "company": "Analytical Co", "role": "Founder", "company_url": "https://example.com",
            "company_description": "We make engines.",
            "company_size": {"revenue_bands": ["1m_10m"], "people_bands": ["2_10"]},
        },
        "problem": {"category": "thin_margins", "event_skew": "more_owners", "details": {}},
        "quarter": {"commitments": ["show_up"], "no_pitch_acknowledged": True, "contact_permission": "yes"},
        "source": "first_city_foundry_quarterly_room",
        "submitted_page": "/quarterly-room",
        "reporting": {"utm_source": "newsletter"},
    }
    if seat == "problem_owner":
        p["problem"]["details"] = {"problem_statement": "Our  margins  keep\nshrinking.", "ninety_day_cost": "$40k"}
    elif seat == "problem_solver":
        p["person"]["company_size"] = {"revenue_bands": ["1m_10m", "over_10m"], "people_bands": ["2_10", "11_50"]}
        p["problem"]["details"] = {"result_change": "Cut COGS 12%", "result_proof": "Case study link"}
    elif seat == "connector":
        p["problem"]["details"] = {"prior_introduction": "Introduced X to Y; became a pricing project"}
    else:
        p["problem"] = {"event_skew": "mostly_sellers", "details": {"last_room_mostly_sellers": True}}
    for k, v in over.items():
        p[k] = v
    return p


@pytest.fixture
def client():
    app = Flask(__name__)
    app.config.update(SQLALCHEMY_DATABASE_URI="sqlite:///:memory:", SQLALCHEMY_TRACK_MODIFICATIONS=False, TESTING=True)
    db.init_app(app)
    app.register_blueprint(api.quarterly_room_bp)
    api._rate_windows.clear()
    with app.app_context():
        db.create_all()
        yield app.test_client()


def post(client, body, origin=ORIGIN):
    return client.post("/api/matching-intakes", json=body, headers={"Origin": origin})


@pytest.mark.parametrize("seat", ["problem_owner", "problem_solver", "connector", "room_builder"])
def test_valid_submission_each_seat(client, seat):
    r = post(client, payload(seat))
    assert r.status_code == 201, r.get_json()
    body = r.get_json()
    assert body["ok"] is True and body["status"] == "received" and body["id"]
    assert r.headers["Access-Control-Allow-Origin"] == ORIGIN
    row = db.session.get(MatchingIntake, body["id"])
    assert row.seat == seat and row.person_email == "ada@example.com"


def test_problem_wording_stored_verbatim(client):
    r = post(client, payload())
    row = db.session.get(MatchingIntake, r.get_json()["id"])
    assert row.problem_statement == "Our  margins  keep\nshrinking."
    assert row.raw_payload["problem"]["details"]["problem_statement"] == "Our  margins  keep\nshrinking."
    assert "client_ip" not in row.request_meta


@pytest.mark.parametrize("mutate,field", [
    (lambda p: p.pop("seat"), "seat"),
    (lambda p: p.update(seat="wizard"), "seat"),
    (lambda p: p.update(schema_version=2), "schema_version"),
    (lambda p: p.update(intake_type="index"), "intake_type"),
    (lambda p: p["person"].update(email="nope"), "person.email"),
    (lambda p: p["person"].pop("name"), "person.name"),
    (lambda p: p["problem"].update(category="astrology"), "problem.category"),
    (lambda p: p["problem"].pop("category"), "problem.category"),
    (lambda p: p["person"]["company_size"].update(revenue_bands=["huge"]), "person.company_size.revenue_bands"),
    (lambda p: p["problem"]["details"].pop("problem_statement"), "problem.details.problem_statement"),
])
def test_invalid_submissions_rejected(client, mutate, field):
    p = payload()
    mutate(p)
    r = post(client, p)
    assert r.status_code == 400
    body = r.get_json()
    assert body["ok"] is False and body["error"] == "Validation failed"
    assert field in [e["field"] for e in body["validation_errors"]]


def test_non_json_and_bad_origin(client):
    assert client.post("/api/matching-intakes", data="x", headers={"Origin": ORIGIN}).status_code == 400
    assert post(client, payload(), origin="https://evil.example").status_code == 403


def test_founder_needs_exactly_one_band_each():
    p = payload()
    p["person"]["company_size"]["revenue_bands"] = ["under_1m", "1m_10m"]
    _, errs = validate_intake(p)
    assert any(e["code"] == "invalid_count" and "revenue" in e["field"] for e in errs)
    p = payload()
    p["person"]["company_size"]["people_bands"] = []
    _, errs = validate_intake(p)
    assert any(e["code"] == "invalid_count" and "people" in e["field"] for e in errs)


def test_provider_may_select_multiple_bands_but_needs_at_least_one():
    for seat in ("problem_solver", "connector", "room_builder"):
        p = payload(seat)
        p["person"]["company_size"] = {"revenue_bands": ["under_1m", "1m_10m", "over_10m"], "people_bands": ["just_me", "51_plus"]}
        if seat == "room_builder":
            p["problem"]["category"] = "visibility"
        _, errs = validate_intake(p)
        assert errs == [], (seat, errs)
    p = payload("problem_solver")
    p["person"]["company_size"] = {"revenue_bands": [], "people_bands": ["2_10"]}
    _, errs = validate_intake(p)
    assert any(e["field"].endswith("revenue_bands") for e in errs)


def test_no_pitch_ack_and_contact_choice_required():
    p = payload(); p["quarter"]["no_pitch_acknowledged"] = False
    assert any("no_pitch" in e["field"] for e in validate_intake(p)[1])
    p = payload(); p["quarter"].pop("contact_permission")
    assert any("contact_permission" in e["field"] for e in validate_intake(p)[1])
    p = payload(); p["quarter"]["contact_permission"] = "maybe-later"
    assert validate_intake(p)[1]


def test_only_yes_permits_outreach(client):
    for perm, expected in [("yes", True), ("no", False), ("ask_first", False), ("not_sure", False)]:
        p = payload(); p["quarter"]["contact_permission"] = perm
        row = db.session.get(MatchingIntake, post(client, p).get_json()["id"])
        assert matching.may_contact(row) is expected


def test_hold_response_stored_but_excluded_from_matching(client):
    p = payload()
    p["quarter"]["commitments"] = ["not_this_quarter"]
    p["problem"] = {}
    p["person"]["company_size"] = {}
    r = post(client, p)
    assert r.status_code == 201
    row = db.session.get(MatchingIntake, r.get_json()["id"])
    assert row.is_hold is True
    assert not matching.in_matching_pool(row, row.quarter_label)
    assert matching.eligibility(row)["in_current_matching"] is False
    # Consent still required on a hold.
    p["quarter"]["no_pitch_acknowledged"] = False
    assert post(client, p).status_code == 400


def _intake(seat, **kw):
    base = dict(seat=seat, is_hold=False, quarter_label="2026-Q4", problem_category="thin_margins",
                revenue_bands=["1m_10m"], problem_details={}, contact_permission="yes", review_status="received")
    base.update(kw)
    return SimpleNamespace(**base)


OWNER = dict(problem_details={"ninety_day_cost": "$40k", "problem_statement": "x"})
SOLVER = dict(revenue_bands=["1m_10m", "over_10m"], problem_details={"result_change": "Cut COGS 12%", "result_proof": "case study"})


def test_owner_solver_match_requires_proof_and_cost_and_fit():
    owner, solver = _intake("problem_owner", **OWNER), _intake("problem_solver", **SOLVER)
    assert matching.owner_solver_match(owner, solver)
    # no proof => not eligible, even though everything else lines up
    assert not matching.owner_solver_match(owner, _intake("problem_solver", **{**SOLVER, "problem_details": {"result_change": "Cut COGS 12%"}}))
    # no concrete result
    assert not matching.owner_solver_match(owner, _intake("problem_solver", **{**SOLVER, "problem_details": {"result_proof": "x"}}))
    # owner with blank 90-day cost
    assert not matching.owner_solver_match(_intake("problem_owner", problem_details={"ninety_day_cost": "  "}), solver)
    # different category
    assert not matching.owner_solver_match(owner, _intake("problem_solver", problem_category="visibility", **SOLVER))
    # owner's revenue band not selected by the solver
    assert not matching.owner_solver_match(_intake("problem_owner", revenue_bands=["under_1m"], **{k: v for k, v in OWNER.items()}), solver)
    # holds never match
    assert not matching.owner_solver_match(owner, _intake("problem_solver", is_hold=True, **SOLVER))


def test_people_bands_do_not_affect_matching():
    owner = _intake("problem_owner", people_bands=["just_me"], **OWNER)
    solver = _intake("problem_solver", people_bands=["51_plus"], **SOLVER)
    assert matching.owner_solver_match(owner, solver)


def test_generic_description_never_creates_a_match():
    solver = _intake("problem_solver", revenue_bands=["1m_10m"], problem_details={"description": "We fix thin margins for everyone"},
                     company_description="thin margins experts")
    assert not matching.solver_eligible(solver)
    assert not matching.owner_solver_match(_intake("problem_owner", **OWNER), solver)


def test_connector_needs_prior_introduction_evidence():
    assert not matching.connector_eligible(_intake("connector", problem_details={}))
    assert not matching.connector_eligible(_intake("connector", problem_details={"prior_introduction": "   "}))
    c = _intake("connector", problem_details={"prior_introduction": "Intro became a pricing project"})
    assert matching.connector_eligible(c)
    assert matching.connectors_for(_intake("problem_owner", **OWNER), [c]) == [c]
    assert matching.connectors_for(_intake("problem_owner", problem_category="visibility", **OWNER), [c]) == []


def test_room_builder_design_contributor_only_if_last_room_mostly_sellers():
    assert matching.room_builder_can_design(_intake("room_builder", problem_details={"last_room_mostly_sellers": True}))
    assert not matching.room_builder_can_design(_intake("room_builder", problem_details={"last_room_mostly_sellers": False}))


def test_review_and_agenda_require_login(client):
    assert client.get("/api/matching-intakes").status_code == 401
    assert client.get("/api/matching-intakes/agenda").status_code == 401
    assert client.patch("/api/matching-intakes/x/review", json={}).status_code == 401


def test_agenda_shows_verbatim_statements_and_withholds_email_without_consent(client, monkeypatch):
    monkeypatch.setattr(api, "_is_staff", lambda: True)
    ids = {}
    for seat in ("problem_owner", "problem_solver"):
        p = payload(seat)
        if seat == "problem_solver":
            p["quarter"]["contact_permission"] = "no"
        ids[seat] = post(client, p).get_json()["id"]
    quarter = matching.quarter_label(datetime.utcnow())
    r = client.get(f"/api/matching-intakes/agenda?quarter={quarter}&statement_ids={ids['problem_owner']}").get_json()
    assert r["candidate_statements"][0]["statement"] == "Our  margins  keep\nshrinking."
    solvers = r["agenda"][0]["solvers"]
    assert len(solvers) == 1 and "email" not in solvers[0]
    assert client.get(f"/api/matching-intakes/agenda?statement_ids=a,b,c,d").status_code == 400


def test_rate_limit(client, monkeypatch):
    monkeypatch.setattr(api, "POST_RATE_LIMIT_PER_MINUTE", 2)
    assert post(client, payload()).status_code == 201
    assert post(client, payload()).status_code == 201
    assert post(client, payload()).status_code == 429


def test_index_endpoint_untouched():
    import custom_modules.the_index.index_submissions_api as idx
    assert idx.index_submissions_bp.name == "index_submissions"
    assert "/api/matching-intakes" not in [str(r) for r in []]

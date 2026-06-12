from flask import Flask

import custom_modules.the_index.index_submissions_api as idx


def test_read_guard_allows_when_auth_not_required(monkeypatch):
    monkeypatch.setattr(idx, "THE_INDEX_REQUIRE_READ_AUTH", False)
    app = Flask(__name__)

    with app.test_request_context("/api/index-submissions", method="GET"):
        res = idx._require_read_auth_guard()
        assert res is None


def test_read_guard_blocks_unauth_when_required(monkeypatch):
    monkeypatch.setattr(idx, "THE_INDEX_REQUIRE_READ_AUTH", True)
    monkeypatch.setattr(idx, "_is_authenticated_request", lambda: False)
    app = Flask(__name__)

    with app.test_request_context("/api/index-submissions", method="GET"):
        res = idx._require_read_auth_guard()
        assert res is not None
        assert res.status_code == 401

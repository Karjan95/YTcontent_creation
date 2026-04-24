"""Phase E tests: /api/usage/* routes.

Reuses the existing conftest.py Firestore + auth mocks. We override the
mocked Firestore chain to return seeded rollup docs, then hit the routes
via the Flask test client.
"""

from datetime import datetime, timedelta
from unittest.mock import MagicMock
import pytest


def _fake_snap(day, total_usd=1.0, by_tool=None, by_project=None):
    """Build a MagicMock snapshot that mimics firestore.DocumentSnapshot."""
    snap = MagicMock()
    snap.id = day
    snap.to_dict.return_value = {
        "day": day,
        "total_usd": total_usd,
        "by_tool": by_tool or {
            "text": {"calls": 10, "cost_usd": 0.5, "in_tokens": 1000,
                     "out_tokens": 500, "cached_tokens": 100},
            "image": {"calls": 2, "cost_usd": 0.5, "images": 2},
        },
        "by_project": by_project or {
            "p1": {"calls": 8, "cost_usd": 0.7},
            "p2": {"calls": 4, "cost_usd": 0.3},
            "_account": {"calls": 0, "cost_usd": 0.0},
        },
        "by_model": {
            "gemini-3-flash-preview": {"calls": 10, "cost_usd": 0.5},
        },
    }
    return snap


def _install_rollup_stream(mock_firestore_client, snaps):
    """Wire mock_firestore_client so cost_rollups.where(...).stream() returns snaps.

    Keeps the existing user-doc get() stub intact for the auth decorator.
    """
    mock_db = mock_firestore_client.return_value

    # Default auth-doc mock (user's gemini_api_key) must still work.
    auth_doc = MagicMock()
    auth_doc.exists = True
    auth_doc.to_dict.return_value = {"gemini_api_key": "k"}

    # Chain: db.collection("users").document(uid).collection("cost_rollups").where(...).where(...).stream()
    def collection_side(name):
        coll = MagicMock()
        if name == "users":
            def doc_side(_uid):
                user_doc = MagicMock()
                user_doc.get.return_value = auth_doc

                def sub_side(subname):
                    sub = MagicMock()
                    if subname == "cost_rollups":
                        # .where().where().stream() chain
                        q1 = MagicMock()
                        q2 = MagicMock()
                        q1.where.return_value = q2
                        q2.stream.return_value = iter(snaps)
                        sub.where.return_value = q1
                    elif subname == "cost_events":
                        q1 = MagicMock()
                        q2 = MagicMock()
                        q3 = MagicMock()
                        q1.where.return_value = q2
                        q2.where.return_value = q3
                        q3.limit.return_value.stream.return_value = iter([])
                        sub.where.return_value = q1
                    return sub

                user_doc.collection.side_effect = sub_side
                return user_doc

            coll.document.side_effect = doc_side
        return coll

    mock_db.collection.side_effect = collection_side


def _auth_headers():
    return {"Authorization": "Bearer test-token"}


def test_account_sums_rollups(client, mock_firebase_and_auth):
    today = datetime.now().strftime("%Y-%m-%d")
    d2 = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    _install_rollup_stream(mock_firebase_and_auth, [
        _fake_snap(d2, total_usd=2.50),
        _fake_snap(today, total_usd=1.25),
    ])

    resp = client.get("/api/usage/account", headers=_auth_headers())
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["days"] == 2
    assert body["total_usd"] == pytest.approx(3.75)
    assert "text" in body["by_tool"]
    assert body["by_tool"]["text"]["calls"] == 20
    assert "p1" in body["by_project"]


def test_trend_fills_zero_days(client, mock_firebase_and_auth):
    # Only 2 days of data, but ?days=5 should return 5 entries in order.
    today = datetime.now()
    d1 = (today - timedelta(days=4)).strftime("%Y-%m-%d")
    d2 = (today - timedelta(days=2)).strftime("%Y-%m-%d")
    _install_rollup_stream(mock_firebase_and_auth, [
        _fake_snap(d1, total_usd=1.00),
        _fake_snap(d2, total_usd=2.00),
    ])

    resp = client.get("/api/usage/trend?days=5", headers=_auth_headers())
    assert resp.status_code == 200
    body = resp.get_json()
    assert len(body["series"]) == 5

    # Days are ascending
    days = [e["day"] for e in body["series"]]
    assert days == sorted(days)

    # The two seeded days have totals; others are zero.
    totals_by_day = {e["day"]: e["total_usd"] for e in body["series"]}
    assert totals_by_day[d1] == pytest.approx(1.00)
    assert totals_by_day[d2] == pytest.approx(2.00)
    zero_days = [v for k, v in totals_by_day.items() if k not in (d1, d2)]
    assert all(v == 0 for v in zero_days)


def test_account_rejects_invalid_date(client, mock_firebase_and_auth):
    _install_rollup_stream(mock_firebase_and_auth, [])
    resp = client.get("/api/usage/account?start=not-a-date",
                      headers=_auth_headers())
    assert resp.status_code == 400
    assert "YYYY-MM-DD" in resp.get_json().get("error", "")


def test_account_rejects_reversed_range(client, mock_firebase_and_auth):
    _install_rollup_stream(mock_firebase_and_auth, [])
    resp = client.get("/api/usage/account?start=2026-04-30&end=2026-04-01",
                      headers=_auth_headers())
    assert resp.status_code == 400


def test_admin_pricing_requires_admin_uid(client, mock_firebase_and_auth, monkeypatch):
    # Default test user is 'test-user-id' — not in ADMIN_UIDS
    import server
    monkeypatch.setattr(server, "_ADMIN_UIDS", set())

    resp = client.get("/api/admin/pricing", headers=_auth_headers())
    assert resp.status_code == 403


def test_admin_pricing_allowed_for_admin(client, mock_firebase_and_auth, monkeypatch):
    import server
    import pricing
    pricing.reset_cache_for_tests()
    monkeypatch.setattr(pricing, "_fetch_from_firestore",
                        lambda: {"version": "v-admin", "text_models": {}})
    monkeypatch.setattr(server, "_ADMIN_UIDS", {"test-user-id"})

    resp = client.get("/api/admin/pricing", headers=_auth_headers())
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["pricing"]["version"] == "v-admin"

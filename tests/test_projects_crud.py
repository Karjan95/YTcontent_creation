"""Project CRUD lifecycle + per-project usage route.

Fills a gap: existing tests cover POST/GET in test_api_workflows.py only via
the broader script workflow; PUT (auto-save), DELETE, and the per-project
usage breakdown were untested. Commit 47b7f92 specifically patched a JSON
serialization bug in create_project — the SERVER_TIMESTAMP-leak guard below
is the regression test for that fix.
"""

import json
from datetime import datetime
from unittest.mock import MagicMock

import pytest


def _auth_headers():
    return {"Authorization": "Bearer test-token", "Content-Type": "application/json"}


def _install_projects_chain(
    mock_firestore_client,
    project_doc=None,
    list_docs=None,
    usage_rollups=None,
    usage_events=None,
):
    """Wire mock_firestore_client for project + per-project usage routes.

    project_doc:   dict returned by .get().to_dict() on a single project (None → 404)
    list_docs:     list of dicts for GET /api/projects (each may include __id__)
    usage_rollups: list of rollup-doc dicts for /api/usage/project/<pid>
    usage_events:  list of event-doc dicts for /api/usage/project/<pid>

    Returns a spy with:
      spy.set_calls    — list of (data, merge_kwarg) tuples from project_ref.set()
      spy.delete_calls — int
    """
    spy = MagicMock()
    spy.set_calls = []
    spy.delete_calls = 0

    auth_doc = MagicMock()
    auth_doc.exists = True
    auth_doc.to_dict.return_value = {"gemini_api_key": "k"}

    def make_project_ref(pid):
        ref = MagicMock()
        ref.id = pid or "auto-id-1"

        def set_side(data, merge=False):
            spy.set_calls.append((data, merge))
        ref.set.side_effect = set_side

        def delete_side(*a, **kw):
            spy.delete_calls += 1
        ref.delete.side_effect = delete_side

        proj_get = MagicMock()
        if project_doc is None:
            proj_get.exists = False
        else:
            proj_get.exists = True
            proj_get.to_dict.return_value = dict(project_doc)
            proj_get.id = pid or "p1"
        ref.get.return_value = proj_get
        return ref

    def make_projects_collection():
        coll = MagicMock()
        coll.document.side_effect = lambda *a: make_project_ref(a[0] if a else None)

        order_q = MagicMock()
        snaps = []
        for d in (list_docs or []):
            d = dict(d)
            sid = d.pop("__id__", "p?")
            snap = MagicMock()
            snap.id = sid
            snap.to_dict.return_value = d
            snaps.append(snap)
        order_q.stream.return_value = iter(snaps)
        coll.order_by.return_value = order_q
        return coll

    def make_rollups_collection():
        sub = MagicMock()
        snaps = []
        for d in (usage_rollups or []):
            s = MagicMock()
            s.id = d.get("day", "x")
            s.to_dict.return_value = dict(d)
            snaps.append(s)
        q1 = MagicMock(); q2 = MagicMock()
        q1.where.return_value = q2
        q2.stream.return_value = iter(snaps)
        sub.where.return_value = q1
        return sub

    def make_events_collection():
        sub = MagicMock()
        snaps = []
        for d in (usage_events or []):
            s = MagicMock()
            s.to_dict.return_value = dict(d)
            snaps.append(s)
        q1 = MagicMock(); q2 = MagicMock(); q3 = MagicMock()
        q1.where.return_value = q2
        q2.where.return_value = q3
        q3.limit.return_value.stream.return_value = iter(snaps)
        sub.where.return_value = q1
        return sub

    def make_user_doc():
        user_doc = MagicMock()
        user_doc.get.return_value = auth_doc

        def sub_side(name):
            if name == "projects":
                return make_projects_collection()
            if name == "cost_rollups":
                return make_rollups_collection()
            if name == "cost_events":
                return make_events_collection()
            return MagicMock()
        user_doc.collection.side_effect = sub_side
        return user_doc

    def collection_side(name):
        coll = MagicMock()
        if name == "users":
            coll.document.side_effect = lambda _uid: make_user_doc()
        return coll

    mock_firestore_client.return_value.collection.side_effect = collection_side
    return spy


# ── POST /api/projects ────────────────────────────────────────────────────────

def test_create_project_returns_id_and_iso_timestamps(client, mock_firebase_and_auth):
    """Regression for 47b7f92: SERVER_TIMESTAMP must not leak into JSON."""
    spy = _install_projects_chain(mock_firebase_and_auth)
    resp = client.post(
        "/api/projects",
        headers=_auth_headers(),
        data=json.dumps({"title": "My Topic", "topic": "AI"}),
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["success"] is True
    assert body["project_id"]
    proj = body["project"]
    assert isinstance(proj["created_at"], str)
    assert isinstance(proj["last_updated_at"], str)
    assert spy.set_calls, "project_ref.set() was not called"
    persisted = spy.set_calls[0][0]
    assert persisted["title"] == "My Topic"
    assert persisted["topic"] == "AI"
    assert "created_at" in persisted
    assert "last_updated_at" in persisted


def test_create_project_defaults_title_when_missing(client, mock_firebase_and_auth):
    spy = _install_projects_chain(mock_firebase_and_auth)
    resp = client.post(
        "/api/projects",
        headers=_auth_headers(),
        data=json.dumps({}),
    )
    assert resp.status_code == 200
    persisted = spy.set_calls[0][0]
    assert persisted["title"] == "Untitled Project"


def test_create_project_rejects_oversize_title(client, mock_firebase_and_auth):
    _install_projects_chain(mock_firebase_and_auth)
    resp = client.post(
        "/api/projects",
        headers=_auth_headers(),
        data=json.dumps({"title": "x" * 201}),
    )
    assert resp.status_code == 400


# ── GET /api/projects ────────────────────────────────────────────────────────

def test_list_projects_returns_metadata(client, mock_firebase_and_auth):
    ts = datetime(2026, 4, 24, 10, 0, 0)
    _install_projects_chain(mock_firebase_and_auth, list_docs=[
        {"__id__": "p1", "title": "First",  "topic": "AI", "last_updated_at": ts},
        {"__id__": "p2", "title": "Second", "topic": "ML", "last_updated_at": ts},
    ])
    resp = client.get("/api/projects", headers=_auth_headers())
    assert resp.status_code == 200
    body = resp.get_json()
    assert len(body["projects"]) == 2
    ids = [p["id"] for p in body["projects"]]
    assert ids == ["p1", "p2"]
    # Timestamp serialized as ISO string
    assert "T" in body["projects"][0]["last_updated_at"]


# ── GET /api/projects/<id> ───────────────────────────────────────────────────

def test_get_project_returns_404_when_missing(client, mock_firebase_and_auth):
    _install_projects_chain(mock_firebase_and_auth, project_doc=None)
    resp = client.get("/api/projects/p999", headers=_auth_headers())
    assert resp.status_code == 404


def test_get_project_serializes_timestamps(client, mock_firebase_and_auth):
    ts = datetime(2026, 4, 1, 9, 30, 0)
    _install_projects_chain(mock_firebase_and_auth, project_doc={
        "title": "Saved",
        "topic": "X",
        "created_at": ts,
        "last_updated_at": ts,
    })
    resp = client.get("/api/projects/p1", headers=_auth_headers())
    assert resp.status_code == 200
    proj = resp.get_json()["project"]
    assert proj["created_at"].startswith("2026-04-01T")
    assert proj["last_updated_at"].startswith("2026-04-01T")


# ── PUT /api/projects/<id> ───────────────────────────────────────────────────

def test_update_project_rejects_empty_body(client, mock_firebase_and_auth):
    _install_projects_chain(mock_firebase_and_auth)
    resp = client.put(
        "/api/projects/p1",
        headers=_auth_headers(),
        data=json.dumps({}),
    )
    assert resp.status_code == 400


def test_update_project_strips_client_timestamps(client, mock_firebase_and_auth):
    spy = _install_projects_chain(mock_firebase_and_auth)
    resp = client.put(
        "/api/projects/p1",
        headers=_auth_headers(),
        data=json.dumps({
            "title": "Renamed",
            "created_at": "client-bogus",
            "last_updated_at": "client-bogus",
        }),
    )
    assert resp.status_code == 200
    assert spy.set_calls, "project_ref.set() was not called"
    persisted, merge = spy.set_calls[0]
    assert persisted["title"] == "Renamed"
    # Server must overwrite client-supplied timestamps with SERVER_TIMESTAMP sentinel
    assert persisted.get("created_at") != "client-bogus"
    assert persisted.get("last_updated_at") != "client-bogus"
    assert merge is True


# ── DELETE /api/projects/<id> ────────────────────────────────────────────────

def test_delete_project_invokes_firestore_delete(client, mock_firebase_and_auth, monkeypatch):
    spy = _install_projects_chain(mock_firebase_and_auth)
    import server
    monkeypatch.setattr(server, "bucket", None)

    resp = client.delete("/api/projects/p1", headers=_auth_headers())
    assert resp.status_code == 200
    assert spy.delete_calls == 1


def test_delete_project_swallows_storage_errors(client, mock_firebase_and_auth, monkeypatch):
    spy = _install_projects_chain(mock_firebase_and_auth)
    fake_bucket = MagicMock()
    fake_bucket.list_blobs.side_effect = RuntimeError("storage offline")
    import server
    monkeypatch.setattr(server, "bucket", fake_bucket)

    resp = client.delete("/api/projects/p1", headers=_auth_headers())
    # Storage cleanup failure must not fail the user-facing delete
    assert resp.status_code == 200
    assert spy.delete_calls == 1


# ── GET /api/usage/project/<id> ──────────────────────────────────────────────

def test_usage_project_aggregates_per_project_costs(client, mock_firebase_and_auth):
    today = datetime.now().strftime("%Y-%m-%d")
    _install_projects_chain(
        mock_firebase_and_auth,
        usage_rollups=[
            {"day": today, "by_project": {"p1": {"cost_usd": 1.50}}},
            {"day": today, "by_project": {"p1": {"cost_usd": 0.25}}},
        ],
        usage_events=[
            {"day": today, "project_id": "p1", "tool": "image", "cost_usd": 1.50},
            {"day": today, "project_id": "p1", "tool": "image", "cost_usd": 0.25},
            {"day": today, "project_id": "p1", "tool": "text",  "cost_usd": 0.05},
        ],
    )
    resp = client.get("/api/usage/project/p1", headers=_auth_headers())
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["project_id"] == "p1"
    assert body["total_usd"] == pytest.approx(1.75)
    assert body["by_tool"]["image"]["calls"] == 2
    assert body["by_tool"]["image"]["cost_usd"] == pytest.approx(1.75)
    assert body["by_tool"]["text"]["calls"] == 1
    assert body["event_count"] == 3

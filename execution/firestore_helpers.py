"""Firestore subcollection helpers for per-project shots, visuals, and pipeline
checkpoints — the storage layer that lets production tables scale past
Firestore's 1MB per-document limit.

Background: production tables and visuals_scenes used to live as fields on the
project doc (users/{uid}/projects/{pid}). Once a project crossed ~400 shots,
that doc would exceed 1,048,576 bytes and Firestore rejected every autosave.
Here we split those fields into proper subcollections:

  users/{uid}/projects/{pid}/shots/{shot_id}              — one doc per shot
  users/{uid}/projects/{pid}/visuals/{visual_id}          — one doc per visual scene
  users/{uid}/projects/{pid}/pipeline_checkpoints/{name}  — resumable pipeline state

`migrate_project()` reads the legacy embedded fields on first project load and
moves them into the new subcollections, then clears the fields. Idempotent.

See plan: docs/plan_production_table_unlimited_scale_2026_05_24.md
"""

from firebase_admin import firestore
# SERVER_TIMESTAMP / DELETE_FIELD are re-exported by firebase_admin.firestore
# at runtime but missing from its type stubs, so static analyzers flag them.
# Pull them from the canonical google.cloud.firestore module to keep both
# the IDE and the runtime happy. firebase_admin depends on this package
# transitively, so no requirements change is needed.
from google.cloud.firestore import SERVER_TIMESTAMP, DELETE_FIELD

# Firestore caps batched writes at 500 ops. We chunk at 400 to leave headroom
# for the trailing field-deletion update in migrate_project().
_BATCH_CHUNK = 400


def _db():
    # Lazy so import order doesn't matter — by the time any helper runs,
    # server.py has called firebase_admin.initialize_app().
    return firestore.client()


def _project_ref(uid, pid):
    return _db().collection('users').document(uid).collection('projects').document(pid)


def _shot_id(order_idx):
    # Zero-padded so Firestore's lex sort matches numeric order without needing
    # an order_by('order') roundtrip when we know the index.
    return f"shot_{order_idx:05d}"


def _visual_id(order_idx):
    return f"visual_{order_idx:05d}"


# ─────────────────────────────────────────────────────────────────────────────
# Shots
# ─────────────────────────────────────────────────────────────────────────────

def read_shots(uid, pid):
    """Return all shots for a project, ordered by their `order` field."""
    docs = _project_ref(uid, pid).collection('shots') \
        .order_by('order').stream()
    out = []
    for d in docs:
        item = d.to_dict() or {}
        item.setdefault('_id', d.id)
        out.append(item)
    return out


def shots_count(uid, pid):
    """Count shots without reading their bodies. Used by resume logic."""
    try:
        agg = _project_ref(uid, pid).collection('shots').count().get()
        # Firestore returns [[AggregationResult]]; pull the int out.
        return int(agg[0][0].value)
    except Exception:
        # Fallback for environments where the aggregation API isn't enabled.
        return sum(1 for _ in _project_ref(uid, pid).collection('shots').stream())


def write_shots(uid, pid, shots, start_order=0):
    """Bulk-write a list of shots into the `shots/` subcollection.

    `start_order` is the order index assigned to shots[0]; subsequent shots
    get incrementing indexes. Use this when streaming completed batches into
    the subcollection — pass the running total as start_order.

    Idempotent for a given (uid, pid, start_order, shots) tuple since the
    doc IDs are derived deterministically from `order`.
    """
    if not shots:
        return 0
    db = _db()
    shots_ref = _project_ref(uid, pid).collection('shots')
    written = 0
    for i in range(0, len(shots), _BATCH_CHUNK):
        batch = db.batch()
        chunk = shots[i:i + _BATCH_CHUNK]
        for j, shot in enumerate(chunk):
            order_idx = start_order + i + j
            payload = dict(shot) if isinstance(shot, dict) else {'data': shot}
            payload['order'] = order_idx
            batch.set(shots_ref.document(_shot_id(order_idx)), payload)
        batch.commit()
        written += len(chunk)
    return written


def write_shot(uid, pid, shot_id, data):
    """Upsert a single shot doc. Used by inline-edit autosave."""
    payload = dict(data) if isinstance(data, dict) else {'data': data}
    _project_ref(uid, pid).collection('shots').document(shot_id) \
        .set(payload, merge=True)


def delete_shot(uid, pid, shot_id):
    """Delete a single shot. Caller is responsible for renumbering siblings
    if global `order` continuity matters."""
    _project_ref(uid, pid).collection('shots').document(shot_id).delete()


def clear_shots(uid, pid):
    """Wipe the `shots/` subcollection. Used by Discard / pipeline reset."""
    db = _db()
    docs = list(_project_ref(uid, pid).collection('shots').stream())
    for i in range(0, len(docs), _BATCH_CHUNK):
        batch = db.batch()
        for d in docs[i:i + _BATCH_CHUNK]:
            batch.delete(d.reference)
        batch.commit()
    return len(docs)


# ─────────────────────────────────────────────────────────────────────────────
# Visuals
# ─────────────────────────────────────────────────────────────────────────────

def read_visuals(uid, pid):
    """Return all visual scenes ordered by their `order` field."""
    docs = _project_ref(uid, pid).collection('visuals') \
        .order_by('order').stream()
    out = []
    for d in docs:
        item = d.to_dict() or {}
        item.setdefault('_id', d.id)
        out.append(item)
    return out


def write_visuals(uid, pid, visuals, start_order=0):
    """Bulk-write visual scenes. Same shape as write_shots()."""
    if not visuals:
        return 0
    db = _db()
    visuals_ref = _project_ref(uid, pid).collection('visuals')
    written = 0
    for i in range(0, len(visuals), _BATCH_CHUNK):
        batch = db.batch()
        chunk = visuals[i:i + _BATCH_CHUNK]
        for j, v in enumerate(chunk):
            order_idx = start_order + i + j
            payload = dict(v) if isinstance(v, dict) else {'data': v}
            payload['order'] = order_idx
            batch.set(visuals_ref.document(_visual_id(order_idx)), payload)
        batch.commit()
        written += len(chunk)
    return written


def write_visual(uid, pid, visual_id, data):
    payload = dict(data) if isinstance(data, dict) else {'data': data}
    _project_ref(uid, pid).collection('visuals').document(visual_id) \
        .set(payload, merge=True)


def delete_visual(uid, pid, visual_id):
    _project_ref(uid, pid).collection('visuals').document(visual_id).delete()


def clear_visuals(uid, pid):
    db = _db()
    docs = list(_project_ref(uid, pid).collection('visuals').stream())
    for i in range(0, len(docs), _BATCH_CHUNK):
        batch = db.batch()
        for d in docs[i:i + _BATCH_CHUNK]:
            batch.delete(d.reference)
        batch.commit()
    return len(docs)


# ─────────────────────────────────────────────────────────────────────────────
# Pipeline checkpoints
# ─────────────────────────────────────────────────────────────────────────────

def read_checkpoints(uid, pid):
    """Return all pipeline_checkpoints docs as a dict keyed by doc ID."""
    out = {}
    for d in _project_ref(uid, pid).collection('pipeline_checkpoints').stream():
        out[d.id] = d.to_dict() or {}
    return out


def write_checkpoint(uid, pid, name, payload):
    """Upsert a single checkpoint doc.

    `name` is typically 'phase0_script_doctor' or 'task_state'.
    """
    data = dict(payload) if isinstance(payload, dict) else {'data': payload}
    data['updated_at'] = SERVER_TIMESTAMP
    _project_ref(uid, pid).collection('pipeline_checkpoints').document(name) \
        .set(data, merge=True)


def read_checkpoint(uid, pid, name):
    doc = _project_ref(uid, pid).collection('pipeline_checkpoints').document(name).get()
    return doc.to_dict() if doc.exists else None


def clear_checkpoints(uid, pid):
    """Wipe all checkpoints. Used by the Discard button on the Resume banner."""
    db = _db()
    docs = list(_project_ref(uid, pid).collection('pipeline_checkpoints').stream())
    for i in range(0, len(docs), _BATCH_CHUNK):
        batch = db.batch()
        for d in docs[i:i + _BATCH_CHUNK]:
            batch.delete(d.reference)
        batch.commit()
    return len(docs)


def append_error(uid, pid, error_record, max_keep=50):
    """Append a single error record to `task_state.errors[]`.

    The UI's inline error log (ui/index.html:renderProductionErrorLog) reads
    these via /api/projects/<id>/resumable so users can see every phase/batch
    failure that's happened without trawling Cloud Run logs.

    `error_record` should be a dict with at least {phase, error}. Common extras:
    batch, task_id, response_length, response_head, response_tail. `ts` is
    auto-added if missing (server-side wall clock for ordering — Firestore
    SERVER_TIMESTAMP can't be inserted INTO an array element so we use a
    Python timestamp here).

    `max_keep` bounds the array so a runaway failure loop can't blow the
    1MB doc-size cap. Older records are dropped first.
    """
    if not isinstance(error_record, dict):
        return
    record = dict(error_record)
    if 'ts' not in record:
        # Use ISO UTC string — JSON-serializable, sortable, and easy to format
        # client-side. (SERVER_TIMESTAMP sentinels aren't allowed inside arrays.)
        from datetime import datetime, timezone
        record['ts'] = datetime.now(timezone.utc).isoformat()
    ref = _project_ref(uid, pid).collection('pipeline_checkpoints').document('task_state')
    # Read-modify-write — Firestore doesn't have ArrayAppendWithCap. The
    # contention window is tiny (write-only on phase failure) so a transaction
    # would be overkill.
    snap = ref.get()
    existing = (snap.to_dict() or {}) if snap.exists else {}
    errs = list(existing.get('errors') or [])
    errs.append(record)
    if max_keep and len(errs) > max_keep:
        errs = errs[-max_keep:]
    ref.set({'errors': errs, 'updated_at': SERVER_TIMESTAMP}, merge=True)


# ─────────────────────────────────────────────────────────────────────────────
# Migration: legacy embedded fields → subcollections
# ─────────────────────────────────────────────────────────────────────────────

def extract_legacy_shots(legacy_pd):
    """Pull the shots list out of the legacy `production_data` field, which
    has been saved in two shapes over time:

        {"production_table": {"shots": [...], ...}, ...}   (newer)
        {"shots": [...], ...}                              (older)

    Returns [] if neither shape applies.
    """
    if not isinstance(legacy_pd, dict):
        return []
    if isinstance(legacy_pd.get('production_table'), dict):
        return legacy_pd['production_table'].get('shots') or []
    return legacy_pd.get('shots') or []


def _subcoll_is_empty(coll_ref):
    # `limit(1).stream()` is cheap — one doc fetched at most.
    for _ in coll_ref.limit(1).stream():
        return False
    return True


def migrate_project(uid, pid, legacy_doc):
    """If the project doc still has embedded `production_data` or
    `visuals_scenes` fields and the corresponding subcollections are empty,
    split them out. Returns True if anything was migrated.

    Safe to call on every project load — the subcollection-emptiness check
    makes it idempotent.
    """
    if not isinstance(legacy_doc, dict):
        return False

    project_ref = _project_ref(uid, pid)
    migrated = False
    fields_to_clear = {}

    # production_data → shots/
    legacy_pd = legacy_doc.get('production_data')
    if legacy_pd:
        shots = extract_legacy_shots(legacy_pd)
        if shots and _subcoll_is_empty(project_ref.collection('shots')):
            write_shots(uid, pid, shots, start_order=0)
            migrated = True
        # Clear the field regardless (it's served by subcollection now).
        fields_to_clear['production_data'] = DELETE_FIELD

    # visuals_scenes → visuals/
    legacy_vs = legacy_doc.get('visuals_scenes')
    if isinstance(legacy_vs, list) and legacy_vs:
        if _subcoll_is_empty(project_ref.collection('visuals')):
            write_visuals(uid, pid, legacy_vs, start_order=0)
            migrated = True
        fields_to_clear['visuals_scenes'] = DELETE_FIELD

    if fields_to_clear:
        fields_to_clear['migrated_at'] = SERVER_TIMESTAMP
        project_ref.update(fields_to_clear)

    return migrated


# ─────────────────────────────────────────────────────────────────────────────
# Agentic 5-stage pipeline: production_stages/ subcollection
# ─────────────────────────────────────────────────────────────────────────────
#
# Each project that runs the new 5-stage pipeline has up to 5 stage docs:
#   users/{uid}/projects/{pid}/production_stages/stage_1 … stage_5
# Doc IDs are deterministic so writes are idempotent / upsertable.
# See docs/agentic_5stage_pipeline_2026_05_25/plan.md.

def _stage_id(n):
    return f"stage_{int(n)}"


def read_production_stages(uid, pid):
    """Return all production_stages docs as a list ordered by stage_number.

    Missing stages are not synthesized — caller can detect a fresh project
    by an empty return.
    """
    docs = _project_ref(uid, pid).collection('production_stages').stream()
    out = []
    for d in docs:
        item = d.to_dict() or {}
        item.setdefault('_id', d.id)
        out.append(item)
    out.sort(key=lambda s: s.get('stage_number', 99))
    return out


def read_production_stage(uid, pid, stage_number):
    """Return a single stage doc or None."""
    doc = _project_ref(uid, pid).collection('production_stages') \
        .document(_stage_id(stage_number)).get()
    return doc.to_dict() if doc.exists else None


def write_production_stage(uid, pid, stage_number, payload):
    """Upsert one stage doc. `payload` is merged into existing doc."""
    data = dict(payload) if isinstance(payload, dict) else {'data': payload}
    data['updated_at'] = SERVER_TIMESTAMP
    data.setdefault('stage_number', int(stage_number))
    _project_ref(uid, pid).collection('production_stages') \
        .document(_stage_id(stage_number)).set(data, merge=True)


def clear_production_stages(uid, pid):
    """Wipe production_stages/. Used by Cancel and by full reset before
    a fresh pipeline run."""
    db = _db()
    docs = list(_project_ref(uid, pid).collection('production_stages').stream())
    for i in range(0, len(docs), _BATCH_CHUNK):
        batch = db.batch()
        for d in docs[i:i + _BATCH_CHUNK]:
            batch.delete(d.reference)
        batch.commit()
    return len(docs)


def mark_stages_stale(uid, pid, from_stage):
    """Mark stages [from_stage..5] as 'stale'. Called when an earlier stage
    is regenerated or user-edited so downstream stages know they're invalid."""
    db = _db()
    coll = _project_ref(uid, pid).collection('production_stages')
    batch = db.batch()
    touched = 0
    for n in range(int(from_stage), 6):
        ref = coll.document(_stage_id(n))
        snap = ref.get()
        if not snap.exists:
            continue
        existing = snap.to_dict() or {}
        if existing.get('status') in ('pending',):
            continue  # nothing to invalidate
        batch.set(ref, {'status': 'stale', 'updated_at': SERVER_TIMESTAMP}, merge=True)
        touched += 1
    if touched:
        batch.commit()
    return touched


def cascade_delete_project_subcollections(uid, pid):
    """Called from delete_project to wipe shots/, visuals/,
    pipeline_checkpoints/, and production_stages/ before the project doc
    itself is deleted.
    """
    deleted = 0
    deleted += clear_shots(uid, pid)
    deleted += clear_visuals(uid, pid)
    deleted += clear_checkpoints(uid, pid)
    deleted += clear_production_stages(uid, pid)
    return deleted

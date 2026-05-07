"""Firestore storage for Seedance sequences.

Sequences live in a subcollection under the project doc:
    users/{uid}/projects/{project_id}/seedance_sequences/{seq_id}

This sidesteps the 1MB-per-doc Firestore limit — each sequence is its own
doc, so a bloated project doc (full of Veo data) can't block writes.

We intentionally do NOT write a `seedance_production_data` field on the
project doc itself, because that doc is often already near the 1MB limit
in real projects.
"""

from firebase_admin import firestore

from .schemas import SCHEMA_VERSION, now_iso

_db = None


def _get_db():
    global _db
    if _db is None:
        _db = firestore.client()
    return _db


def _project_ref(uid, project_id):
    return _get_db().collection("users").document(uid).collection("projects").document(project_id)


def _sequences_ref(uid, project_id):
    return _project_ref(uid, project_id).collection("seedance_sequences")


def get_seedance_data(uid, project_id):
    """Return synthesized seedance data: {version, sequences: [...]}.

    Reads sequences from the subcollection, ordered by created_at.
    """
    seqs = []
    for snap in _sequences_ref(uid, project_id).order_by("created_at").stream():
        d = snap.to_dict() or {}
        d.setdefault("id", snap.id)
        seqs.append(d)
    return {
        "version": SCHEMA_VERSION,
        "sequences": seqs,
        "updated_at": now_iso(),
    }


def append_sequence(uid, project_id, sequence):
    """Write a new sequence as its own doc in the subcollection."""
    seq_id = sequence["id"]
    _sequences_ref(uid, project_id).document(seq_id).set(sequence)
    return sequence


def get_sequence(uid, project_id, seq_id):
    snap = _sequences_ref(uid, project_id).document(seq_id).get()
    if not snap.exists:
        return None
    d = snap.to_dict() or {}
    d.setdefault("id", snap.id)
    return d


def update_sequence(uid, project_id, seq_id, patch):
    """Merge `patch` into the sequence doc and persist."""
    ref = _sequences_ref(uid, project_id).document(seq_id)
    snap = ref.get()
    if not snap.exists:
        return None
    cur = snap.to_dict() or {}
    merged = {**cur, **patch}
    ref.set(merged)
    merged.setdefault("id", seq_id)
    return merged

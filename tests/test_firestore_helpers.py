"""Unit tests for execution/firestore_helpers.py.

These cover the pure (non-Firestore) logic — legacy field extraction and
doc-id formatting. Real subcollection I/O is exercised in integration tests
where a Firestore emulator is available.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'execution'))

import firestore_helpers as fh


def test_extract_legacy_shots_new_shape():
    """The newer legacy shape: production_data wraps a production_table."""
    legacy = {
        'production_table': {
            'shots': [{'shot_number': '1'}, {'shot_number': '2'}],
            'total_shots': 2,
        },
        'title': 'foo',
    }
    out = fh.extract_legacy_shots(legacy)
    assert isinstance(out, list)
    assert len(out) == 2
    assert out[0]['shot_number'] == '1'


def test_extract_legacy_shots_old_shape():
    """The older legacy shape: production_data is the table itself."""
    legacy = {
        'shots': [{'shot_number': '1'}, {'shot_number': '2'}, {'shot_number': '3'}],
        'total_shots': 3,
    }
    out = fh.extract_legacy_shots(legacy)
    assert len(out) == 3


def test_extract_legacy_shots_empty_and_none():
    """Tolerate missing / non-dict inputs without raising."""
    assert fh.extract_legacy_shots(None) == []
    assert fh.extract_legacy_shots({}) == []
    assert fh.extract_legacy_shots({'production_table': {}}) == []
    assert fh.extract_legacy_shots("not a dict") == []


def test_shot_id_zero_padded():
    """Doc IDs must zero-pad so Firestore's lex sort matches numeric order."""
    assert fh._shot_id(0) == 'shot_00000'
    assert fh._shot_id(42) == 'shot_00042'
    assert fh._shot_id(99999) == 'shot_99999'


def test_visual_id_zero_padded():
    assert fh._visual_id(0) == 'visual_00000'
    assert fh._visual_id(1234) == 'visual_01234'


def test_batch_chunk_size_under_firestore_limit():
    """We chunk at 400 ops to leave headroom under Firestore's 500-op batch cap."""
    assert fh._BATCH_CHUNK <= 500
    # Need headroom because migrate_project() bundles a trailing field-delete
    # update onto the same batch sequence.
    assert fh._BATCH_CHUNK <= 450

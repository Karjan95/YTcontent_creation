"""Phase D tests: uid + project_id must flow through the scriptwriter pipeline
into every generate_content() call so cost events are attributable.

We monkeypatch research_scriptwriter.generate_content with a spy that records
every kwargs invocation. No Gemini calls happen.
"""

import json
from unittest.mock import MagicMock
import pytest


@pytest.fixture
def scriptwriter_with_spy(monkeypatch):
    import research_scriptwriter as rsw

    captured = []

    def spy_generate_content(prompt, model_name="gemini-3-flash-preview",
                             use_search=False, temperature=None,
                             api_key=None, max_output_tokens=None,
                             return_response=False, uid=None, project_id=None,
                             description=None):
        captured.append({
            "model": model_name,
            "uid": uid,
            "project_id": project_id,
            "description": description,
        })
        # Return a minimal JSON payload the parser will accept for narration
        if "narration" in (description or "") or "narration" in (prompt[:200] if prompt else ""):
            return json.dumps({"title": "T", "narration": [{"act": "ACT 1", "beat": "B1", "text": "hi"}]})
        if "director" in (description or ""):
            return json.dumps({"shots": [{"shot_number": "1"}]})
        if "storyboard" in (description or ""):
            return json.dumps({"shots": [{"shot_number": "1"}]})
        if "cinematographer" in (description or ""):
            return json.dumps({"shots": [{"shot_number": "1"}]})
        if "continuity" in (description or ""):
            return json.dumps({"shots": [{"shot_number": "1"}], "review_summary": {"shots_modified": 0}})
        if "dp" in (description or ""):
            return json.dumps({"shots": [{"shot_number": "1", "first_frame_prompt": "x"}]})
        if "script_doctor" in (description or ""):
            return json.dumps({"visual_brief": []})
        return json.dumps({"suggested_tone": "Neutral"})

    monkeypatch.setattr(rsw, "generate_content", spy_generate_content)
    return rsw, captured


def test_generate_narration_forwards_uid(scriptwriter_with_spy):
    rsw, captured = scriptwriter_with_spy

    rsw.generate_narration(
        topic="Topic", template_id="explainer", research_dossier="x",
        api_key="k", uid="u1", project_id="p1",
    )

    assert len(captured) == 1
    assert captured[0]["uid"] == "u1"
    assert captured[0]["project_id"] == "p1"
    assert captured[0]["description"] == "narration"


def test_auto_suggest_tone_forwards_uid(scriptwriter_with_spy):
    rsw, captured = scriptwriter_with_spy

    rsw.auto_suggest_tone(
        template_id="explainer", selected_title="T",
        audience="General", api_key="k",
        uid="u2", project_id="p2",
    )

    assert captured[-1]["uid"] == "u2"
    assert captured[-1]["project_id"] == "p2"


def test_production_pipeline_6phase_tags_stages(scriptwriter_with_spy):
    """Running 6-phase on a small narration should emit the expected stage tags."""
    rsw, captured = scriptwriter_with_spy

    narration = {
        "title": "T",
        "narration": [
            {"act": "ACT 1", "beat": "B1", "text": "alpha beta gamma."},
            {"act": "ACT 1", "beat": "B2", "text": "delta epsilon zeta."},
        ],
    }

    rsw.generate_production_table(
        narration_json=narration, duration_minutes=1,
        api_key="k", uid="u1", project_id="p1",
    )

    descriptions = [c["description"] for c in captured]
    # Phase 0 + all 5 6-phase stages should be present.
    assert "script_doctor" in descriptions
    assert "director_6phase" in descriptions
    assert "cinematographer_6phase" in descriptions
    assert "storyboard_6phase" in descriptions
    assert "continuity_6phase" in descriptions
    assert "dp_6phase" in descriptions

    # Every call must carry the same uid/project_id.
    for c in captured:
        assert c["uid"] == "u1"
        assert c["project_id"] == "p1"


def test_regenerate_beats_forwards_uid(scriptwriter_with_spy, monkeypatch):
    rsw, captured = scriptwriter_with_spy

    # regenerate_beats calls build_beat_regeneration_prompt — stub to bypass.
    monkeypatch.setattr(rsw, "build_beat_regeneration_prompt",
                        lambda **kwargs: "prompt")

    rsw.regenerate_beats(
        topic="T", template_id="explainer", research_dossier="d",
        full_narration={"narration": []}, target_beat_indices=[0],
        api_key="k", uid="u9", project_id="p9",
    )

    assert captured[-1]["uid"] == "u9"
    assert captured[-1]["project_id"] == "p9"
    assert captured[-1]["description"] == "regenerate_beats"

"""Unit tests for the agentic 5-stage production pipeline.

Covers:
  - Pydantic schemas round-trip valid example payloads.
  - JSON schemas emitted are Gemini-safe (no additionalProperties, no anyOf).
  - _compose_bible concatenates sections in order, skips pending/error.
  - Stage 5 server-side merge correctly carries Stage 4 fields forward.
  - _apply_user_edits handles dotted paths and array indices.
"""

import json
import pytest


# ──────────────────────────────────────────────────────────────────────
# Pydantic schemas
# ──────────────────────────────────────────────────────────────────────

class TestSchemas:
    def test_stage1_roundtrip(self):
        from agentic_schemas import Stage1Treatment
        sample = {
            "logline": "A wasp terrorizes a man.",
            "theme": "Power and fear.",
            "emotional_arc": [
                {"act": "1", "beat_ref": "Beat 1", "emotional_state": "calm",
                 "transition_note": "shift to dread"},
            ],
            "scene_treatments": [
                {"scene_id": "S1", "beat_refs": ["Beat 1"],
                 "treatment": "Suburban morning. The wasp arrives.",
                 "performance_note": "Restrained."},
            ],
            "performance_notes": "Hold tension.",
            "tonal_references": ["Errol Morris", "Werner Herzog"],
        }
        parsed = Stage1Treatment.model_validate(sample)
        assert parsed.logline == "A wasp terrorizes a man."
        assert len(parsed.emotional_arc) == 1

    def test_stage6_roundtrip(self):
        from agentic_schemas import Stage6Final
        sample = {
            "continuity_review": {
                "variety_check": "good", "consistency_notes": "ok",
                "pacing_notes": "tight", "revisions_made": ["S3 lens fix"],
            },
            "shot_deltas": [
                {"shot_number": "1",
                 "shot_size": "Medium",
                 "subject_pose": "A man at a desk, reading intently",
                 "environment": "Cozy home office, soft afternoon light",
                 "lighting": "Warm window key from camera-left, soft fill",
                 "lens_dof": "50mm at f/2.8, shallow with bokeh background",
                 "color_palette": "Warm ambers and sage greens, medium contrast",
                 "output_aesthetic": "Hand-drawn ink with watercolor wash",
                 "veo_prompt": "veo prompt",
                 "revised_blueprint_fields": [
                     {"field_name": "lens", "new_value": "wide",
                      "reason": "isolation"},
                 ]},
            ],
        }
        parsed = Stage6Final.model_validate(sample)
        assert parsed.shot_deltas[0].subject_pose.startswith("A man at a desk")
        assert parsed.shot_deltas[0].output_aesthetic == "Hand-drawn ink with watercolor wash"
        assert parsed.shot_deltas[0].revised_blueprint_fields[0].field_name == "lens"

    def test_stage5_continuity_brief_roundtrip(self):
        from agentic_schemas import Stage5ContinuityBrief
        sample = {
            "character_locks": [
                {"character_name": "Resident",
                 "locked_descriptor": "tall, mustard-yellow knit sweater, soft eyes"},
            ],
            "vocabulary_locks": [
                {"concept": "amber light", "canonical_phrase": "warm amber glow",
                 "rationale": "appears in 12+ shots"},
            ],
            "callback_map": [
                {"shot_number": "47", "callback_to_shot": "12",
                 "note": "same low-angle hex-tunnel framing"},
            ],
            "act_atmospheres": [
                {"act": "Act 1", "keywords": ["warm", "observational", "low-stakes"]},
            ],
            "consistency_concerns": "",
        }
        parsed = Stage5ContinuityBrief.model_validate(sample)
        assert parsed.character_locks[0].character_name == "Resident"
        assert parsed.vocabulary_locks[0].canonical_phrase == "warm amber glow"
        assert parsed.callback_map[0].callback_to_shot == "12"

    def test_all_schemas_gemini_safe(self):
        """No `additionalProperties` or `anyOf` (Optional) which Gemini's
        structured output API rejects."""
        from agentic_schemas import STAGE_SCHEMAS
        # All six stages must be Gemini-safe (1..6 after Continuity Brief).
        assert set(STAGE_SCHEMAS.keys()) == {1, 2, 3, 4, 5, 6}
        for n, M in STAGE_SCHEMAS.items():
            js = json.dumps(M.model_json_schema())
            assert "additionalProperties" not in js, \
                f"Stage {n} has additionalProperties (Gemini will reject)"
            assert "anyOf" not in js, \
                f"Stage {n} has anyOf (would mean Optional fields)"


# ──────────────────────────────────────────────────────────────────────
# Bible composer
# ──────────────────────────────────────────────────────────────────────

class TestBibleComposer:
    def test_compose_skips_pending_and_error(self):
        from agentic_prompts import _compose_bible
        stages = [
            {"stage_number": 1, "status": "complete",
             "bible_section": "## Stage 1 — Story\n\nLogline goes here."},
            {"stage_number": 2, "status": "pending",
             "bible_section": "## Stage 2 — World\n\nShouldn't appear."},
            {"stage_number": 3, "status": "error",
             "bible_section": "## Stage 3 — Cam\n\nShouldn't appear."},
            {"stage_number": 4, "status": "approved",
             "bible_section": "## Stage 4 — Shots\n\nApproved section."},
        ]
        bible = _compose_bible(stages, "Test")
        assert "Logline goes here." in bible
        assert "Approved section." in bible
        assert "Shouldn't appear." not in bible

    def test_compose_orders_by_stage_number(self):
        from agentic_prompts import _compose_bible
        stages = [
            {"stage_number": 3, "status": "complete", "bible_section": "## Three"},
            {"stage_number": 1, "status": "complete", "bible_section": "## One"},
            {"stage_number": 2, "status": "complete", "bible_section": "## Two"},
        ]
        bible = _compose_bible(stages, "T")
        i1 = bible.find("## One")
        i2 = bible.find("## Two")
        i3 = bible.find("## Three")
        assert 0 < i1 < i2 < i3

    def test_compose_includes_title(self):
        from agentic_prompts import _compose_bible
        bible = _compose_bible([], "The Wasp")
        assert "The Wasp" in bible


# ──────────────────────────────────────────────────────────────────────
# Stage 6 merge (renamed from _merge_stage5_with_blueprints)
# ──────────────────────────────────────────────────────────────────────

def _seven_fields_delta(shot_number, **overrides):
    """Helper: build a delta with all seven structured prompt fields filled."""
    base = {
        "shot_number": shot_number,
        "shot_size": "Medium",
        "subject_pose": "A subject doing a thing",
        "environment": "A place with depth",
        "lighting": "Soft side key",
        "lens_dof": "50mm f/2.8",
        "color_palette": "Warm ambers",
        "output_aesthetic": "Hand-drawn ink",
        "veo_prompt": "veo",
        "revised_blueprint_fields": [],
    }
    base.update(overrides)
    return base


class TestStage6Merge:
    def test_carries_forward_blueprint_fields(self):
        from agentic_pipeline import _merge_stage6_with_blueprints
        blueprints = [
            {"shot_number": "1", "timestamp": "00:00", "duration": "4",
             "act": "ACT 1", "beat": "Opening",
             "script_beat": "You think the walls are a barrier.",
             "cutting_rationale": "Set the premise.",
             "emotion": "secure",
             "character_expression": "soft eyes", "character_outfit": "yellow sweater",
             "directors_intent": "Establish", "lens": "wide"},
        ]
        deltas = [_seven_fields_delta("1")]
        merged, unmatched = _merge_stage6_with_blueprints(
            blueprints, deltas, rendering_anchor="Hand-drawn ink")
        assert len(merged) == 1
        assert unmatched == []
        s = merged[0]
        # Narrative anchors carried forward
        assert s["act"] == "ACT 1"
        assert s["script_beat"] == "You think the walls are a barrier."
        assert s["cutting_rationale"] == "Set the premise."
        assert s["emotion"] == "secure"
        # Character renames carried forward
        assert s["character_expression"] == "soft eyes"
        assert s["character_outfit"] == "yellow sweater"
        # Cinematography carried forward
        assert s["lens"] == "wide"
        # Seven structured prompt fields from Stage 6
        for f in ("shot_size", "subject_pose", "environment", "lighting",
                  "lens_dof", "color_palette", "output_aesthetic", "veo_prompt"):
            assert f in s and s[f]
        # Assembled first_frame_prompt with labels
        assert s["first_frame_prompt"].startswith("SHOT SIZE:")
        assert "SUBJECT:" in s["first_frame_prompt"]
        assert "OUTPUT AESTHETIC:" in s["first_frame_prompt"]
        assert "ASPECT RATIO:" in s["first_frame_prompt"]

    def test_style_lock_inject_on_drift(self):
        from agentic_pipeline import _merge_stage6_with_blueprints
        blueprints = [{"shot_number": "1"}]
        # Model drifted: output_aesthetic does not contain the anchor keywords.
        deltas = [_seven_fields_delta("1",
            output_aesthetic="photorealistic cinematic shot")]
        merged, _ = _merge_stage6_with_blueprints(
            blueprints, deltas,
            rendering_anchor="Hand-drawn ink linework with watercolor wash")
        # Merger should have hard-overridden output_aesthetic.
        assert merged[0]["output_aesthetic"] == \
               "Hand-drawn ink linework with watercolor wash"

    def test_style_lock_no_inject_when_intact(self):
        from agentic_pipeline import _merge_stage6_with_blueprints
        blueprints = [{"shot_number": "1"}]
        # Model echoed the anchor faithfully.
        deltas = [_seven_fields_delta("1",
            output_aesthetic="Hand-drawn ink linework with watercolor wash")]
        merged, _ = _merge_stage6_with_blueprints(
            blueprints, deltas,
            rendering_anchor="Hand-drawn ink linework with watercolor wash")
        assert merged[0]["output_aesthetic"] == \
               "Hand-drawn ink linework with watercolor wash"

    def test_applies_revised_fields(self):
        from agentic_pipeline import _merge_stage6_with_blueprints
        blueprints = [{"shot_number": "1", "lens": "wide", "angle": "low"}]
        deltas = [_seven_fields_delta("1", revised_blueprint_fields=[
            {"field_name": "lens", "new_value": "telephoto", "reason": "isolate"},
        ])]
        merged, _ = _merge_stage6_with_blueprints(blueprints, deltas)
        assert merged[0]["lens"] == "telephoto"  # revised wins
        assert merged[0]["angle"] == "low"        # carried forward unchanged

    def test_unmatched_delta_does_not_crash(self):
        from agentic_pipeline import _merge_stage6_with_blueprints
        blueprints = [{"shot_number": "1"}]
        deltas = [_seven_fields_delta("1"), _seven_fields_delta("99")]
        merged, unmatched = _merge_stage6_with_blueprints(blueprints, deltas)
        assert len(merged) == 1
        assert "99" in unmatched

    def test_preserves_blueprint_order_by_number(self):
        from agentic_pipeline import _merge_stage6_with_blueprints
        blueprints = [
            {"shot_number": "3"}, {"shot_number": "1"}, {"shot_number": "2"},
        ]
        deltas = [_seven_fields_delta("1"),
                  _seven_fields_delta("2"),
                  _seven_fields_delta("3")]
        merged, _ = _merge_stage6_with_blueprints(blueprints, deltas)
        assert [s["shot_number"] for s in merged] == ["1", "2", "3"]


# ──────────────────────────────────────────────────────────────────────
# Pacing math handles legacy narration shapes
# ──────────────────────────────────────────────────────────────────────

class TestPacingMath:
    def test_handles_narration_key(self):
        from agentic_pipeline import _compute_target_shot_count
        n = {"narration": [{"voiceover": "word " * 90}]}  # 90 words
        target, tier, words = _compute_target_shot_count(n, "standard")
        assert words == 90
        assert tier == "Standard"
        assert target == 10  # 90 / 9 ≈ 10

    def test_handles_legacy_acts_beats_nesting(self):
        from agentic_pipeline import _compute_target_shot_count
        # The bug that produced 20 shots from 1700 words: nested shape.
        n = {"acts": [{"beats": [{"voiceover": "word " * 1700}]}]}
        target, tier, words = _compute_target_shot_count(n, "standard")
        assert words == 1700
        assert target == round(1700 / 9)  # ~189

    def test_handles_script_beat_field(self):
        from agentic_pipeline import _compute_target_shot_count
        n = {"narration": [{"script_beat": "word " * 50}]}
        _, _, words = _compute_target_shot_count(n, "standard")
        assert words == 50

    def test_empty_narration_returns_zero(self):
        from agentic_pipeline import _compute_target_shot_count
        target, _, words = _compute_target_shot_count({}, "standard")
        assert target == 0 and words == 0


# ──────────────────────────────────────────────────────────────────────
# Stage 6 first_frame_prompt assembly + style lock check
# ──────────────────────────────────────────────────────────────────────

class TestStage6Assembly:
    def test_assemble_produces_eight_labels(self):
        from agentic_pipeline import _assemble_first_frame_prompt
        ff = _assemble_first_frame_prompt({
            "shot_size": "Medium",
            "subject_pose": "Subject",
            "environment": "Env",
            "lighting": "Light",
            "lens_dof": "Lens",
            "color_palette": "Pal",
            "output_aesthetic": "Aesthetic",
        }, aspect_ratio="9:16")
        assert "SHOT SIZE: Medium" in ff
        assert "SUBJECT: Subject" in ff
        assert "ENVIRONMENT: Env" in ff
        assert "LIGHTING: Light" in ff
        assert "LENS/DOF: Lens" in ff
        assert "COLOR PALETTE: Pal" in ff
        assert "OUTPUT AESTHETIC: Aesthetic" in ff
        assert "ASPECT RATIO: 9:16" in ff

    def test_style_lock_check(self):
        from agentic_pipeline import _style_lock_check
        anchor = "Hand-drawn graphic-novel ink linework with watercolor wash"
        assert _style_lock_check(
            "Hand-drawn graphic-novel ink linework", anchor) is True
        assert _style_lock_check("photorealistic shot", anchor) is False
        assert _style_lock_check("", anchor) is False
        assert _style_lock_check("anything", "") is True  # no anchor = passes


# ──────────────────────────────────────────────────────────────────────
# Duration normalization — the deterministic post-Stage 4 pass that
# replaces the model's fabricated durations with word_count/TARGET_WPS so
# the film runtime matches what the VO can physically read.
# ──────────────────────────────────────────────────────────────────────

class TestDurationNormalization:
    def test_long_script_beat_gets_long_duration(self):
        from agentic_pipeline import _normalize_shot_durations, TARGET_WPS
        # 66 words — the same shot 145 case the user reported.
        sentence = " ".join(["word"] * 66)
        shots = [{"shot_number": "1", "script_beat": sentence,
                  "duration": "3.2", "timestamp": "00:03"}]
        _normalize_shot_durations(shots)
        # 66 / 2.7 ≈ 24.4 seconds — far from the 3.2 the model wrote.
        assert float(shots[0]["duration"]) >= 20.0
        assert float(shots[0]["duration"]) <= 30.0

    def test_short_script_beat_gets_minimum(self):
        from agentic_pipeline import _normalize_shot_durations, MIN_SHOT_DURATION
        shots = [{"shot_number": "1", "script_beat": "Hi.",
                  "duration": "5"}]
        _normalize_shot_durations(shots)
        # 1 word / 2.7 = 0.37s, floored at MIN_SHOT_DURATION (1.5).
        assert float(shots[0]["duration"]) == MIN_SHOT_DURATION

    def test_empty_script_beat_keeps_existing_duration(self):
        from agentic_pipeline import _normalize_shot_durations
        shots = [{"shot_number": "1", "script_beat": "", "duration": "4.0"}]
        _normalize_shot_durations(shots)
        # No script_beat → no word-derived target; keep whatever was set
        # (clamped to minimum).
        assert float(shots[0]["duration"]) >= 1.5

    def test_timestamps_are_cumulative(self):
        from agentic_pipeline import _normalize_shot_durations
        shots = [
            {"shot_number": "1", "script_beat": " ".join(["w"] * 8)},   # ~3.0s
            {"shot_number": "2", "script_beat": " ".join(["w"] * 16)},  # ~5.9s
            {"shot_number": "3", "script_beat": " ".join(["w"] * 8)},   # ~3.0s
        ]
        _normalize_shot_durations(shots)
        # Timestamp 1 = 00:00, timestamp 2 ≈ 00:03, timestamp 3 ≈ 00:08 or 00:09.
        assert shots[0]["timestamp"] == "00:00"
        # Just check monotonic increase to avoid brittle exact-second asserts.
        ts_secs = [int(s["timestamp"].split(":")[1]) for s in shots]
        assert ts_secs[0] < ts_secs[1] < ts_secs[2]

    def test_no_physically_impossible_speech_rates(self):
        """No shot should end up with >4 wps after normalization. This is the
        regression guard for the 2026-05-27 issue (87/159 shots at >4 wps)."""
        from agentic_pipeline import _normalize_shot_durations
        shots = [
            {"shot_number": str(i),
             "script_beat": " ".join(["w"] * wc),
             "duration": "1.0"}
            for i, wc in enumerate([5, 12, 25, 50, 66, 80], start=1)
        ]
        _normalize_shot_durations(shots)
        for s in shots:
            wc = len(s["script_beat"].split())
            d = float(s["duration"])
            wps = wc / d if d > 0 else 0
            assert wps <= 3.0, (
                f"shot {s['shot_number']} has {wps:.2f} wps — "
                f"normalization should keep it below TARGET_WPS")

    def test_cap_enforced_when_max_duration_given(self):
        """Even without splitting, a shot's duration must never exceed
        max_shot_duration when the cap is passed in."""
        from agentic_pipeline import _normalize_shot_durations
        shots = [{"shot_number": "1",
                  "script_beat": " ".join(["w"] * 60)}]  # ~22s at 2.7 wps
        _normalize_shot_durations(shots, max_shot_duration=6.0)
        assert float(shots[0]["duration"]) <= 6.0


# ──────────────────────────────────────────────────────────────────────
# Dedupe + split pass — the safety net that handles model failure modes
# the Stage 4 prompt instructions don't always catch.
# ──────────────────────────────────────────────────────────────────────

class TestDedupeAndSplit:
    def test_adjacent_duplicate_script_beats_get_split_into_clauses(self):
        """The 2026-05-27 'shots 99 & 100 same line' bug. Two adjacent shots
        with identical script_beat must each end up with a DIFFERENT clause
        of that text."""
        from agentic_pipeline import _dedupe_and_split_shots
        line = ("When a wasp returns to the nest agitated, wings raised, "
                "posture rigid, the colony responds.")
        shots = [
            {"shot_number": "1", "script_beat": line, "camera_move": "wide",
             "lens": "35mm"},
            {"shot_number": "2", "script_beat": line, "camera_move": "close",
             "lens": "85mm"},
        ]
        result = _dedupe_and_split_shots(shots, max_shot_duration=6.0)
        assert len(result) == 2
        assert result[0]["script_beat"] != result[1]["script_beat"]
        # Both clauses must be substrings of the original (verbatim slicing).
        for s in result:
            assert s["script_beat"] in line or all(
                w in line for w in s["script_beat"].split())

    def test_oversize_shot_gets_split_into_multiple_children(self):
        from agentic_pipeline import _dedupe_and_split_shots
        # 60 words ≈ 22s at 2.7 wps — needs at least 4 children at 6s cap.
        long_text = ("She is just sitting in the entrance of a small paper "
                     "structure built by her mother, in a corner of a garden "
                     "you think of as yours, doing the job her colony built her "
                     "to do, which is to know every shape that moves through "
                     "the air around the nest.")
        shots = [{"shot_number": "1", "script_beat": long_text,
                  "camera_move": "locked", "lens": "50mm",
                  "directors_intent": "Quiet observation."}]
        result = _dedupe_and_split_shots(shots, max_shot_duration=6.0)
        assert len(result) >= 3
        # Each child must fit under the cap (≤16 words at 6s × 2.7 wps).
        for s in result:
            wc = len(s["script_beat"].split())
            assert wc <= 17

    def test_split_children_get_distinct_visual_variation(self):
        from agentic_pipeline import _dedupe_and_split_shots
        long_text = ("First clause that is fairly long; "
                     "second clause that is also long, and continues; "
                     "third clause, which still keeps going; "
                     "fourth and final clause to wrap up the sentence.")
        shots = [{"shot_number": "1", "script_beat": long_text,
                  "camera_move": "locked", "lens": "50mm",
                  "shot_size": "Medium"}]
        result = _dedupe_and_split_shots(shots, max_shot_duration=4.0)
        # Multiple children produced.
        assert len(result) >= 2
        # Camera moves cycle (not all identical).
        moves = {s.get("camera_move") for s in result}
        assert len(moves) >= 2

    def test_shot_numbers_renumber_sequentially_after_split(self):
        from agentic_pipeline import _dedupe_and_split_shots
        shots = [
            {"shot_number": "1", "script_beat": "Short."},
            {"shot_number": "2",
             "script_beat": " ".join(["w"] * 40)},  # will split
            {"shot_number": "3", "script_beat": "Also short."},
        ]
        result = _dedupe_and_split_shots(shots, max_shot_duration=6.0)
        nums = [int(s["shot_number"]) for s in result]
        assert nums == list(range(1, len(result) + 1))

    def test_short_shots_pass_through_unchanged(self):
        from agentic_pipeline import _dedupe_and_split_shots
        shots = [
            {"shot_number": "1", "script_beat": "Five words here total folks."},
            {"shot_number": "2", "script_beat": "Different short clause works fine."},
        ]
        result = _dedupe_and_split_shots(shots, max_shot_duration=6.0)
        assert len(result) == 2
        assert result[0]["script_beat"] == "Five words here total folks."
        assert result[1]["script_beat"] == "Different short clause works fine."

    def test_stage4_prompt_includes_max_shot_duration_instructions(self):
        from agentic_prompts import build_stage4_shot_list_prompt
        prompt, _ = build_stage4_shot_list_prompt(
            bible_so_far="# Bible", cast=None,
            narration={"narration": [{"voiceover": "Test text."}]},
            format_preset="standard", max_shot_duration=6.0,
        )
        assert "Max shot duration: 6.0s" in prompt
        assert "No two shots may share the same script_beat" in prompt
        assert "Creative-split cookbook" in prompt


# ──────────────────────────────────────────────────────────────────────
# Stage 4 batching helpers
# ──────────────────────────────────────────────────────────────────────

class TestStage4Batching:
    def test_split_narration_into_batches(self):
        from agentic_pipeline import _split_narration_into_batches
        narration = {
            "narration": [
                {"act": "1", "beat": str(i), "voiceover": f"text {i}"}
                for i in range(1, 26)  # 25 beats
            ]
        }
        # Default beats_per_batch = 10 → 3 batches (10, 10, 5)
        batches = _split_narration_into_batches(narration)
        assert len(batches) == 3
        assert len(batches[0]["narration"]) == 10
        assert len(batches[1]["narration"]) == 10
        assert len(batches[2]["narration"]) == 5
        # First beat of batch 2 is beat 11
        assert batches[1]["narration"][0]["beat"] == "11"

    def test_split_narration_small_input(self):
        from agentic_pipeline import _split_narration_into_batches
        # Fewer beats than batch size → single batch
        narration = {"narration": [{"voiceover": "one"}, {"voiceover": "two"}]}
        batches = _split_narration_into_batches(narration)
        assert len(batches) == 1

    def test_batch_word_count(self):
        from agentic_pipeline import _batch_word_count
        batch = {"narration": [
            {"voiceover": "one two three"},
            {"voiceover": "four five"},
        ]}
        assert _batch_word_count(batch) == 5


# ──────────────────────────────────────────────────────────────────────
# User edits application
# ──────────────────────────────────────────────────────────────────────

class TestUserEdits:
    def test_simple_top_level_edit(self):
        from agentic_pipeline import _apply_user_edits
        output = {"logline": "old", "theme": "ok"}
        result = _apply_user_edits(output, {"logline": "new"})
        assert result["logline"] == "new"
        assert result["theme"] == "ok"

    def test_array_index_edit(self):
        from agentic_pipeline import _apply_user_edits
        output = {"shots": [
            {"shot_number": "1", "directors_intent": "old"},
            {"shot_number": "2", "directors_intent": "ok"},
        ]}
        result = _apply_user_edits(output, {
            "shots.0.directors_intent": "revised",
        })
        assert result["shots"][0]["directors_intent"] == "revised"
        assert result["shots"][1]["directors_intent"] == "ok"

    def test_no_mutation_of_input(self):
        from agentic_pipeline import _apply_user_edits
        output = {"logline": "original"}
        _ = _apply_user_edits(output, {"logline": "changed"})
        assert output["logline"] == "original"

    def test_empty_edits_is_passthrough(self):
        from agentic_pipeline import _apply_user_edits
        output = {"a": 1}
        assert _apply_user_edits(output, None) is output
        assert _apply_user_edits(output, {}) == output


# ──────────────────────────────────────────────────────────────────────
# Prompt builders — basic shape checks
# ──────────────────────────────────────────────────────────────────────

class TestPromptBuilders:
    def test_stage1_includes_narration_and_brief(self):
        from agentic_prompts import build_stage1_treatment_prompt
        prompt, schema = build_stage1_treatment_prompt(
            narration={"title": "X", "narration": [
                {"act": "1", "beat": "1", "text": "Hello world."},
            ]},
            research_dossier="Research notes here.",
            audience="general", tone="conversational", format_preset="standard",
        )
        assert "Story Treatment" in prompt
        assert "Director" in prompt
        assert "Hello world" in prompt
        assert "Research notes" in prompt
        assert schema.__name__ == "Stage1Treatment"

    def test_stage6_includes_blueprints(self):
        from agentic_prompts import build_stage6_final_prompts_prompt
        prompt, schema = build_stage6_final_prompts_prompt(
            bible_so_far="# Test bible",
            shot_blueprints=[
                {"shot_number": "1", "timestamp": "00:00", "duration": "4",
                 "directors_intent": "Establish",
                 "character_expression": "Soft eyes",
                 "character_outfit": "Yellow sweater",
                 "lens": "wide"},
            ],
            rendering_style="hand-drawn graphic novel: ink linework",
        )
        assert "Final Prompts" in prompt
        assert "Stage6Final" == schema.__name__
        assert "shot_number" in prompt  # blueprints serialized in
        # Seven structured prompt fields named in the prompt
        for field in ("shot_size", "subject_pose", "environment", "lighting",
                      "lens_dof", "color_palette", "output_aesthetic"):
            assert f"`{field}`" in prompt
        # Rendering style anchored verbatim
        assert "hand-drawn graphic novel: ink linework" in prompt

    def test_stage5_continuity_brief_sees_full_shot_list(self):
        from agentic_prompts import build_stage5_continuity_brief_prompt
        blueprints = [
            {"shot_number": str(i), "beat": f"Beat {i // 5}",
             "character_expression": "circling",
             "character_outfit": "paper pulp",
             "script_beat": "buzz"}
            for i in range(1, 51)
        ]
        prompt, schema = build_stage5_continuity_brief_prompt(
            bible_so_far="# Bible",
            shot_blueprints=blueprints,
        )
        assert "Stage5ContinuityBrief" == schema.__name__
        assert "50 shots" in prompt
        # Pipe-delimited compact form: "{shot_number}|{beat}|..."
        for n in (1, 25, 50):
            assert f"{n}|Beat" in prompt

    def test_stage6_uses_continuity_brief(self):
        from agentic_prompts import build_stage6_final_prompts_prompt
        brief = {
            "character_locks": [{"character_name": "Resident", "locked_descriptor": "tall, knit sweater"}],
            "vocabulary_locks": [{"concept": "amber light", "canonical_phrase": "warm amber glow", "rationale": ""}],
            "callback_map": [{"shot_number": "47", "callback_to_shot": "12", "note": "same low angle"}],
            "act_atmospheres": [{"act": "Act 1", "keywords": ["warm", "observational"]}],
            "consistency_concerns": "",
        }
        prompt, _ = build_stage6_final_prompts_prompt(
            bible_so_far="# Bible",
            shot_blueprints=[{"shot_number": "47",
                              "character_expression": "X",
                              "character_outfit": "Y"}],
            continuity_brief=brief,
        )
        assert "warm amber glow" in prompt  # vocab lock surfaced
        assert "tall, knit sweater" in prompt  # character lock surfaced
        assert "echoes shot 12" in prompt  # callback surfaced for batch-resident shot 47

    def test_feedback_appears_when_given(self):
        from agentic_prompts import build_stage2_world_design_prompt
        prompt, _ = build_stage2_world_design_prompt(
            bible_so_far="# bible", style_analysis=None, cast=None,
            feedback="Use a colder palette.",
        )
        assert "colder palette" in prompt
        assert "User feedback" in prompt

    def test_stage2_pins_user_style_summary_verbatim(self):
        """When the user has approved a style_summary, Stage 2's prompt must
        instruct the LLM to set rendering_style to that exact text — not
        rephrase it. The 2026-05-27 regression came from Stage 2 inventing
        'Photoreal cinematic macro-cinematography' for a project whose user
        had approved 'polished graphic-novel illustration'."""
        from agentic_prompts import build_stage2_world_design_prompt
        approved = ("A polished graphic-novel illustration style defined by "
                    "confident black ink linework, soft painterly digital "
                    "colors, and warm cinematic lighting.")
        prompt, _ = build_stage2_world_design_prompt(
            bible_so_far="# bible",
            style_analysis={"style_summary": approved},
            cast=None,
        )
        assert "VERBATIM" in prompt
        assert approved in prompt

    def test_stage2_falls_back_to_creative_examples_without_user_style(self):
        from agentic_prompts import build_stage2_world_design_prompt
        prompt, _ = build_stage2_world_design_prompt(
            bible_so_far="# bible",
            style_analysis=None,
            cast=None,
        )
        # Without an approved style, the prompt should give the LLM creative
        # latitude (examples list).
        assert "Polished hand-drawn graphic-novel" in prompt


# ──────────────────────────────────────────────────────────────────────
# Stage 4 word-budget batching (output-cap truncation prevention)
# ──────────────────────────────────────────────────────────────────────

def _beats(*specs):
    """Build a narration dict from (beat_name, word_count) specs."""
    return {
        "title": "T",
        "narration": [
            {"act": "ACT 1", "beat": name, "text": " ".join(["word"] * n)}
            for name, n in specs
        ],
    }


class TestStage4WordBudgetBatching:
    def test_closes_batch_on_word_budget_before_beat_count(self):
        """The 2026-05-29 incident: a 10-beat, 831-word batch overflowed the
        output cap and dropped its last beat. With a word budget far below 10
        beats' worth of words, the batch must split BEFORE hitting 10 beats."""
        from agentic_pipeline import (_split_narration_into_batches,
                                       _batch_word_count)
        # 10 beats * 200 words = 2000 words; budget 500 → must be >1 batch.
        narration = _beats(*[(f"B{i}", 200) for i in range(10)])
        batches = _split_narration_into_batches(
            narration, beats_per_batch=10, max_batch_words=500)
        assert len(batches) > 1
        for b in batches:
            # No batch exceeds the word budget unless it's a single beat.
            n_beats = len(b["narration"])
            if n_beats > 1:
                assert _batch_word_count(b) <= 500

    def test_no_beat_is_dropped_across_batches(self):
        from agentic_pipeline import _split_narration_into_batches
        narration = _beats(*[(f"B{i}", 120) for i in range(7)])
        batches = _split_narration_into_batches(
            narration, beats_per_batch=10, max_batch_words=500)
        flat = [bt["beat"] for b in batches for bt in b["narration"]]
        assert flat == [f"B{i}" for i in range(7)]

    def test_lone_oversize_beat_becomes_its_own_batch(self):
        """A single beat larger than the budget is never split across batches;
        it goes in alone rather than being dropped or merged."""
        from agentic_pipeline import _split_narration_into_batches
        narration = _beats(("Small1", 50), ("Huge", 900), ("Small2", 50))
        batches = _split_narration_into_batches(
            narration, beats_per_batch=10, max_batch_words=500)
        huge = [b for b in batches
                if any(bt["beat"] == "Huge" for bt in b["narration"])]
        assert len(huge) == 1
        assert len(huge[0]["narration"]) == 1  # Huge is alone

    def test_beat_count_still_caps_when_words_are_light(self):
        from agentic_pipeline import _split_narration_into_batches
        # 12 tiny beats, generous word budget → split by beat count (10).
        narration = _beats(*[(f"B{i}", 3) for i in range(12)])
        batches = _split_narration_into_batches(
            narration, beats_per_batch=10, max_batch_words=5000)
        assert len(batches) == 2
        assert len(batches[0]["narration"]) == 10
        assert len(batches[1]["narration"]) == 2

    def test_short_script_stays_single_batch(self):
        """Regression guard: the common case (one light batch) must not gain
        extra batches/API calls."""
        from agentic_pipeline import _split_narration_into_batches
        narration = _beats(("A", 40), ("B", 40), ("C", 40))
        batches = _split_narration_into_batches(
            narration, beats_per_batch=10, max_batch_words=500)
        assert len(batches) == 1


# ──────────────────────────────────────────────────────────────────────
# Beat coverage net (reused from research_scriptwriter)
# ──────────────────────────────────────────────────────────────────────

class TestBeatCoverageNet:
    def test_detects_dropped_beat(self):
        """_check_beat_coverage must report a beat whose text appears in NO
        shot's script_beat — the exact 'The Reveal' failure mode."""
        from agentic_pipeline import _check_beat_coverage
        beats = [
            {"act": "ACT 1", "beat": "Hook",
             "text": "A teacher made a simple bet with himself."},
            {"act": "ACT 3", "beat": "The Reveal",
             "text": "He turned on a television set in the center of the stage."},
        ]
        shots = [
            {"script_beat": "A teacher made a simple bet with himself"},
            # Note: nothing covers "The Reveal".
        ]
        uncovered = _check_beat_coverage(beats, shots)
        assert len(uncovered) == 1
        assert uncovered[0]["beat"] == "The Reveal"

    def test_passes_when_all_beats_covered(self):
        from agentic_pipeline import _check_beat_coverage
        beats = [
            {"act": "ACT 1", "beat": "Hook",
             "text": "A teacher made a simple bet with himself."},
        ]
        shots = [
            {"script_beat": "A teacher made a simple bet with himself, alone."},
        ]
        assert _check_beat_coverage(beats, shots) == []


# ──────────────────────────────────────────────────────────────────────
# Stage 4 parallel execution (quality-equivalent to sequential)
# ──────────────────────────────────────────────────────────────────────

class TestStage4ParallelAssembly:
    def _run(self, monkeypatch, n_batches, complete_order=None, max_workers=3):
        """Drive _run_stage4_batched with the Gemini boundary stubbed.

        Each batch i has one beat whose text leads with a unique marker
        ("markI ...") and the stub returns a single shot whose script_beat
        echoes that marker — so the coverage net passes (no recovery noise)
        and we can assert assembly order by marker.

        complete_order: optional list of batch_idx to simulate out-of-order
                        completion (a sleep is injected per batch).
        """
        import time as _time
        import agentic_pipeline as ap

        # Distinct leading marker per beat so fingerprints differ + coverage
        # can be satisfied per batch.
        narration = {
            "title": "T",
            "narration": [
                {"act": "ACT 1", "beat": f"B{i}",
                 "text": f"mark{i} " + " ".join(["word"] * 30)}
                for i in range(n_batches)
            ],
        }
        # Force exactly n_batches (one beat each). Patch the splitter directly
        # rather than the constants — the constants are bound as default args
        # at definition time, so monkeypatching them wouldn't change splitting.
        def _split_one_per_beat(narr, *a, **k):
            title = narr.get("title", "")
            return [{"title": title, "narration": [b]}
                    for b in narr.get("narration", [])]
        monkeypatch.setattr(ap, "_split_narration_into_batches",
                            _split_one_per_beat)
        monkeypatch.setattr(ap, "STAGE4_PARALLEL_WORKERS", max_workers)
        monkeypatch.setattr(ap, "_check_cancelled", lambda *a, **k: None)
        monkeypatch.setattr(ap, "_compose_bible", lambda *a, **k: "# bible")
        # Identity post-passes so we assert raw assembly.
        monkeypatch.setattr(ap, "_dedupe_and_split_shots",
                            lambda shots, mx: shots)
        monkeypatch.setattr(ap, "_normalize_shot_durations",
                            lambda shots, **k: None)
        monkeypatch.setattr(ap, "build_stage4_shot_list_prompt",
                            lambda **k: ("prompt", object()),
                            raising=False)

        delay = {bi: 0.0 for bi in range(n_batches)}
        if complete_order:
            # Later in complete_order = finishes later (bigger sleep).
            for rank, bi in enumerate(complete_order):
                delay[bi] = 0.01 * (rank + 1)

        def fake_call(*, uid, pid, api_key, prompt, schema, model_kwargs,
                      batch_idx, batches_total):
            if delay.get(batch_idx):
                _time.sleep(delay[batch_idx])
            # script_beat echoes the beat's text so _check_beat_coverage passes.
            text = f"mark{batch_idx} " + " ".join(["word"] * 30)
            return [{"script_beat": text}]

        monkeypatch.setattr(ap, "_call_stage4_batch", fake_call)

        context = {
            "narration": narration,
            "target_shot_count": 0,  # no pacing target → no pacing retry
            "total_words": ap._count_narration_words(narration),
            "pacing_tier": "Standard",
            "format_preset": "standard",
            "style_analysis": None,
            "cast": None,
            "max_shot_duration": 6.0,
            "project_title": "T",
        }
        return ap._run_stage4_batched(
            "u", "p", context, stages_so_far=[], feedback=None, api_key="k")

    def test_assembles_in_batch_order_despite_out_of_order_completion(
            self, monkeypatch):
        # 3 batches; batch 2 finishes first, then 0, then 1.
        result = self._run(monkeypatch, 3, complete_order=[2, 0, 1])
        markers = [s["script_beat"].split()[0] for s in result["shots"]]
        # Must be in batch-index order, NOT completion order.
        assert markers == ["mark0", "mark1", "mark2"]
        # Shot numbers reassigned globally + sequentially.
        assert [s["shot_number"] for s in result["shots"]] == ["1", "2", "3"]
        # No coverage gap → no missing_beats flag.
        assert "missing_beats" not in result

    def test_no_shot_lost_across_parallel_batches(self, monkeypatch):
        result = self._run(monkeypatch, 5, complete_order=[4, 3, 2, 1, 0])
        assert len(result["shots"]) == 5
        markers = {s["script_beat"].split()[0] for s in result["shots"]}
        assert markers == {f"mark{i}" for i in range(5)}

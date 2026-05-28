"""
Agentic 5-stage production pipeline — orchestrator and auto-flow worker.

Replaces the parallel-batching 6-phase pipeline in research_scriptwriter.py
with five sequential, role-played stages that share a growing markdown
Production Bible as context. See docs/agentic_5stage_pipeline_2026_05_25/plan.md.

Public API:
    run_stage(uid, pid, stage_number, *, feedback=None, api_key=None,
              progress_callback=None) -> dict
    run_pipeline_worker(uid, pid, task_id, api_key, start_at=1) -> None
    GenerationCancelled  — sentinel exception (re-exported from server.py)

The worker is launched as a daemon thread by server.py. It reads
pipeline_checkpoints/agentic_flow on each iteration so the UI can pause,
resume, or cancel cleanly.
"""

from __future__ import annotations

import concurrent.futures
import json
import threading
import time
import traceback
from datetime import datetime, timezone
from typing import Any, Callable

import firestore_helpers as fh
from agentic_prompts import (
    BIBLE_RENDERERS, STAGE_PROMPT_BUILDERS, _compose_bible,
)
from agentic_schemas import STAGE_LABELS, STAGE_NAMES, STAGE_SCHEMAS

# Reuse the existing parser ladder — no need to duplicate it.
from research_scriptwriter import _parse_json_response

# Gemini wrapper.
from gemini_client import generate_content


# ──────────────────────────────────────────────────────────────────────
# Pacing tier → target shot count (ported from research_scriptwriter.py)
# ──────────────────────────────────────────────────────────────────────

# beats_per_batch is unused in the agentic pipeline (no parallel batches);
# words_per_shot is the only knob that matters for shot-count targeting.
PACE_TIERS = {
    "Meditative":  {"words_per_shot": 15},
    "Relaxed":     {"words_per_shot": 11},
    "Standard":    {"words_per_shot": 9},
    "High Energy": {"words_per_shot": 5},
    "Frenetic":    {"words_per_shot": 3},
}


def _resolve_pacing_tier(format_preset: str | None) -> str:
    if not format_preset:
        return "Standard"
    try:
        from research_templates import FORMAT_PRESETS
        preset = FORMAT_PRESETS.get(format_preset) or {}
        return preset.get("auto_pacing_tier") or "Standard"
    except Exception:
        return "Standard"


def _count_narration_words(narration: dict | None) -> int:
    if not narration:
        return 0
    # Accept several shapes: {narration: [...]}, {beats: [...]}, or
    # nested {acts: [{beats: [...]}]} (legacy format).
    beats = narration.get("narration") or narration.get("beats") or []
    if not beats and isinstance(narration.get("acts"), list):
        beats = []
        for act in narration["acts"]:
            if isinstance(act, dict):
                beats.extend(act.get("beats") or [])
    if not isinstance(beats, list):
        return 0
    total = 0
    for b in beats:
        if not isinstance(b, dict):
            continue
        text = (b.get("voiceover") or b.get("text")
                or b.get("narration") or b.get("script_beat") or "")
        if isinstance(text, str):
            total += len(text.split())
    return total


def _compute_target_shot_count(narration: dict | None,
                               format_preset: str | None) -> tuple[int, str, int]:
    """Returns (target_shots, pacing_tier, total_words). Floors at 1."""
    tier = _resolve_pacing_tier(format_preset)
    words_per_shot = PACE_TIERS.get(tier, PACE_TIERS["Standard"])["words_per_shot"]
    total_words = _count_narration_words(narration)
    target = max(1, int(round(total_words / words_per_shot))) if total_words else 0
    # Diagnostic: surface narration shape so we can see why count is off.
    if narration:
        shape_keys = sorted(list(narration.keys()))[:8]
        beats_field = ('narration' if narration.get('narration')
                       else 'beats' if narration.get('beats')
                       else 'acts' if narration.get('acts')
                       else 'NONE')
        beats_count = (len(narration.get('narration') or [])
                       or len(narration.get('beats') or [])
                       or sum(len(a.get('beats') or [])
                              for a in (narration.get('acts') or [])
                              if isinstance(a, dict)))
        print(f"[Stage4 pacing] preset={format_preset!r} tier={tier} "
              f"words_per_shot={words_per_shot} total_words={total_words} "
              f"target={target} narration_shape={shape_keys} "
              f"beats_field={beats_field} beats_count={beats_count}")
    else:
        print(f"[Stage4 pacing] no narration provided — target=0")
    return target, tier, total_words


# Stage-level model settings. Stages emit different shapes / sizes:
#   - Stage 1 produces a treatment (~3-10KB)
#   - Stage 4 produces the full shot list (large for 400+ shot projects)
#   - Stage 5 produces 2 prompts per shot (the largest output)
# Default to gemini-3.5-flash with high token budget. Per-stage overrides
# below let us crank Stage 4/5 to the model ceiling.
_STAGE_MODELS: dict[int, dict] = {
    1: {"model_name": "gemini-3.5-flash", "max_output_tokens": 16384,
        "thinking_level": "low", "timeout_s": 180},
    2: {"model_name": "gemini-3.5-flash", "max_output_tokens": 16384,
        "thinking_level": "low", "timeout_s": 180},
    3: {"model_name": "gemini-3.5-flash", "max_output_tokens": 16384,
        "thinking_level": "low", "timeout_s": 180},
    4: {"model_name": "gemini-3.5-flash", "max_output_tokens": 65536,
        "thinking_level": "low", "timeout_s": 300},
    5: {"model_name": "gemini-3.5-flash", "max_output_tokens": 16384,
        "thinking_level": "low", "timeout_s": 300},
    6: {"model_name": "gemini-3.5-flash", "max_output_tokens": 65536,
        "thinking_level": "low", "timeout_s": 600},
}

# Batch sizes for the two stages that batch.
STAGE4_BEATS_PER_BATCH = 10   # ~50 shots/batch at Standard tier
STAGE6_BATCH_SIZE = 25
STAGE6_PARALLEL_WORKERS = 3   # Stage 6 batches run concurrently
STAGE5_TWO_PHASE_THRESHOLD = 800  # above this many shots, split Stage 5 across two calls


class GenerationCancelled(Exception):
    """Raised cooperatively when the worker detects the run was cancelled.

    The worker catches this and exits without writing terminal state, so
    the wipe performed by the Cancel endpoint isn't undone by a late
    write from this thread.
    """


# ──────────────────────────────────────────────────────────────────────
# Project context loader
# ──────────────────────────────────────────────────────────────────────

def _load_project_context(uid: str, pid: str) -> dict:
    """Read the project doc + dossier and return what every stage may need.

    We deliberately fetch this once per run_stage() call — Firestore reads
    are cheap and this keeps the orchestrator a pure function of project
    state.
    """
    from firebase_admin import firestore
    db = firestore.client()
    project_ref = db.collection('users').document(uid) \
        .collection('projects').document(pid)
    snap = project_ref.get()
    if not snap.exists:
        raise ValueError(f"Project {pid} not found for user {uid}")
    project = snap.to_dict() or {}

    # Dossier lives in a separate collection
    dossier = None
    try:
        dsnap = project_ref.collection('dossiers').document('latest').get()
        if dsnap.exists:
            dossier = (dsnap.to_dict() or {}).get('content')
    except Exception:
        pass

    narration = project.get('narration_data') or {}
    format_preset = project.get('format_preset') or 'standard'
    target_shots, pacing_tier, total_words = _compute_target_shot_count(
        narration, format_preset)

    # Max shot duration — user-configurable per project (default 6s to match
    # the current Veo/Kie 6-second generation window the user is working in).
    try:
        max_shot_duration = float(project.get('max_shot_duration') or 6.0)
    except (TypeError, ValueError):
        max_shot_duration = 6.0
    max_shot_duration = max(2.0, min(15.0, max_shot_duration))

    return {
        'project_title': project.get('title') or project.get('topic') or '',
        'narration': narration,
        'research_dossier': dossier or project.get('research_dossier') or '',
        'cast': project.get('cast_data') or {},
        # The UI persists the user-approved style under `approved_style` (see
        # ui/index.html ~11730). The legacy single-shot endpoint used the key
        # `style_analysis` instead. Prefer the user-approved dict so Stage 2's
        # verbatim-paste branch fires and Stage 6's style-lock anchors to the
        # user's choice rather than an LLM-invented fallback.
        'style_analysis': project.get('approved_style')
                          or project.get('style_analysis')
                          or project.get('visual_style_analysis') or {},
        'audience': project.get('audience') or 'general',
        'tone': project.get('tone') or 'conversational',
        'format_preset': format_preset,
        'viewer_outcome': project.get('viewer_outcome'),
        'aspect_ratio': project.get('aspect_ratio') or '16:9',
        'pacing_tier': pacing_tier,
        'target_shot_count': target_shots,
        'total_words': total_words,
        'max_shot_duration': max_shot_duration,
    }


# ──────────────────────────────────────────────────────────────────────
# Cancel / pause cooperative checks
# ──────────────────────────────────────────────────────────────────────

def _read_flow(uid: str, pid: str) -> dict:
    doc = fh.read_checkpoint(uid, pid, 'agentic_flow')
    return doc or {}


def _write_flow(uid: str, pid: str, patch: dict) -> None:
    fh.write_checkpoint(uid, pid, 'agentic_flow', patch)


def _check_cancelled(uid: str, pid: str) -> None:
    flow = _read_flow(uid, pid)
    if (flow.get('status') == 'cancelled') or flow.get('cancelled'):
        raise GenerationCancelled()


def _check_paused(uid: str, pid: str) -> bool:
    flow = _read_flow(uid, pid)
    return bool(flow.get('paused'))


# ──────────────────────────────────────────────────────────────────────
# Stage 6 server-side merge — combine Stage 4 blueprints + Stage 6 deltas
# ──────────────────────────────────────────────────────────────────────

# Seven structured prompt fields the model returns per shot. The merger
# concatenates these into a labeled `first_frame_prompt` server-side so
# the shape is guaranteed regardless of model behavior.
_STAGE6_PROMPT_FIELDS = (
    'shot_size', 'subject_pose', 'environment', 'lighting',
    'lens_dof', 'color_palette', 'output_aesthetic',
)


def _assemble_first_frame_prompt(parts: dict, aspect_ratio: str = '16:9') -> str:
    """Build the labeled `first_frame_prompt` string from the seven structured
    fields. Mirrors the old 12-section template's structure at ~1/3 the tokens.
    """
    def _line(label, value):
        v = str(value or '').strip()
        return f"{label}: {v}" if v else f"{label}:"
    return "\n".join([
        _line("SHOT SIZE", parts.get('shot_size')),
        _line("SUBJECT", parts.get('subject_pose')),
        _line("ENVIRONMENT", parts.get('environment')),
        _line("LIGHTING", parts.get('lighting')),
        _line("LENS/DOF", parts.get('lens_dof')),
        _line("COLOR PALETTE", parts.get('color_palette')),
        _line("OUTPUT AESTHETIC", parts.get('output_aesthetic')),
        f"ASPECT RATIO: {aspect_ratio}",
    ])


def _style_lock_check(output_aesthetic: str, rendering_anchor: str) -> bool:
    """Returns True if output_aesthetic clearly carries the rendering_style.

    We don't require character-for-character equality (the model may add
    a clarifying tail). We require the anchor's distinctive keywords to
    appear in the field — same heuristic the old pipeline used implicitly
    via verbatim paste.
    """
    if not rendering_anchor:
        return True
    out = (output_aesthetic or "").lower()
    if not out:
        return False
    # Pull keywords > 4 chars from the anchor. If half or more of them
    # land in output_aesthetic, the style propagated.
    import re
    words = [w for w in re.findall(r"[a-zA-Z][a-zA-Z\-]{3,}", rendering_anchor.lower())
             if w not in {"with", "that", "this", "from", "into", "have",
                          "your", "their", "they", "more", "most", "very"}]
    if not words:
        return True
    hits = sum(1 for w in set(words) if w in out)
    # Require >= 50% of unique style keywords present.
    return hits / max(1, len(set(words))) >= 0.5


def _merge_stage6_with_blueprints(
    blueprints: list[dict], deltas: list[dict],
    rendering_anchor: str = "",
    aspect_ratio: str = "16:9",
) -> tuple[list[dict], list[str]]:
    """Combine Stage 4 shot blueprints with Stage 6 deltas by shot_number.

    Stage 6 contributes the seven structured prompt fields plus veo_prompt
    and any explicit revisions. This merger:
      1. Copies blueprint fields forward.
      2. Drops Stage 6's seven prompt-fields + veo_prompt onto each shot.
      3. Style-lock injection: if output_aesthetic drifts from the
         rendering_anchor, hard-overwrites it with the anchor verbatim
         (mirrors research_templates.py:2528 from the old pipeline).
      4. Assembles the labeled first_frame_prompt server-side.
      5. Applies any revised_blueprint_fields.

    Returns (merged_shots, unmatched_deltas).
    """
    by_num: dict[str, dict] = {}
    for bp in blueprints:
        sn = str(bp.get('shot_number') or '').strip()
        if sn:
            by_num[sn] = dict(bp)

    unmatched: list[str] = []
    style_drift_count = 0
    for delta in deltas:
        sn = str(delta.get('shot_number') or '').strip()
        if not sn or sn not in by_num:
            unmatched.append(sn or '<missing>')
            continue
        merged = by_num[sn]

        # 1. Copy the seven structured prompt fields onto the shot.
        for f in _STAGE6_PROMPT_FIELDS:
            merged[f] = delta.get(f, '') or ''

        # 2. Veo prompt.
        merged['veo_prompt'] = delta.get('veo_prompt', '') or ''

        # 3. Style-lock inject — hard override if the model drifted from
        #    the canonical rendering style.
        if rendering_anchor and not _style_lock_check(
                merged.get('output_aesthetic'), rendering_anchor):
            merged['output_aesthetic'] = rendering_anchor
            style_drift_count += 1

        # 4. Assemble the labeled first_frame_prompt server-side.
        merged['first_frame_prompt'] = _assemble_first_frame_prompt(
            merged, aspect_ratio=aspect_ratio)

        # 5. Apply explicit revisions last so they can touch blueprint
        #    fields (act/beat/script_beat etc.) without being trampled.
        for rev in (delta.get('revised_blueprint_fields') or []):
            field_name = rev.get('field_name')
            new_value = rev.get('new_value')
            if field_name:
                merged[field_name] = new_value

    if style_drift_count:
        print(f"[Stage6 merge] style-lock injected on {style_drift_count} shot(s) "
              f"that drifted from rendering_anchor")

    merged_shots = [by_num[sn] for sn in by_num.keys()]
    # Preserve blueprint order via shot_number numeric sort.
    def _key(s):
        try:
            return int(str(s.get('shot_number') or '0').lstrip('0') or '0')
        except ValueError:
            return 0
    merged_shots.sort(key=_key)
    return merged_shots, unmatched


# ──────────────────────────────────────────────────────────────────────
# Stage 4 batched executor
# ──────────────────────────────────────────────────────────────────────
#
# Stage 4 produces blueprints for the entire film. At 500+ shots the
# Gemini output cap (65536 tokens) truncates the response. We batch by
# groups of beats, allocating per-batch shot-count targets proportional
# to the beats' word counts, and assign sequential shot_numbers
# server-side so batches don't have to coordinate.

def _split_narration_into_batches(narration: dict,
                                  beats_per_batch: int = STAGE4_BEATS_PER_BATCH
                                  ) -> list[dict]:
    """Return a list of narration-shaped dicts, each holding a slice of beats."""
    beats = (narration or {}).get("narration") or (narration or {}).get("beats") or []
    if not isinstance(beats, list):
        return [narration]
    if not beats:
        return [narration]
    batches = []
    title = (narration or {}).get("title") or (narration or {}).get("topic") or ""
    for i in range(0, len(beats), beats_per_batch):
        batches.append({
            "title": title,
            "narration": beats[i:i + beats_per_batch],
        })
    return batches


def _batch_word_count(batch: dict) -> int:
    total = 0
    for b in (batch.get("narration") or batch.get("beats") or []):
        if not isinstance(b, dict):
            continue
        text = b.get("voiceover") or b.get("text") or b.get("narration") or ""
        if isinstance(text, str):
            total += len(text.split())
    return total


PACING_TOLERANCE = 0.15  # ±15% — beyond this, retry the batch once

# Target speech rate (words per second) for narration. Typical conversational
# documentary VO is 2.5-2.8 wps; we use 2.7 wps as the planning constant.
# After Stage 4 returns we recompute each shot's `duration` from its
# script_beat word count at this rate so durations reflect physical reading
# time instead of whatever the model decided to write.
TARGET_WPS = 2.7
MIN_SHOT_DURATION = 1.5  # seconds — visual shots get this minimum even with little/no text


def _normalize_shot_durations(shots: list[dict],
                              max_shot_duration: float | None = None) -> None:
    """Mutates each shot in place: recomputes `duration` from script_beat word
    count and rebuilds `timestamp` as cumulative MM:SS. Without this, the
    model invents durations that don't match what the VO can actually say
    (87/159 shots in the 2026-05-27 run were >4 wps — physically impossible).

    If `max_shot_duration` is given, each shot's duration is capped at that
    value. (The deterministic split pass — `_split_oversize_shots` — should
    have run first to add new shots for any overflow; this cap is a safety
    net for any oversized shot that survives.)
    """
    cursor = 0.0
    for s in shots:
        wc = len((s.get('script_beat') or '').split())
        if wc > 0:
            dur = max(MIN_SHOT_DURATION, round(wc / TARGET_WPS, 1))
        else:
            try:
                existing = float(str(s.get('duration') or '').strip().rstrip('s') or 2.0)
            except (TypeError, ValueError):
                existing = 2.0
            dur = max(MIN_SHOT_DURATION, existing)
        if max_shot_duration is not None:
            dur = min(dur, float(max_shot_duration))
        s['duration'] = f"{dur:.1f}"
        mins, secs = divmod(int(cursor), 60)
        s['timestamp'] = f"{mins:02d}:{secs:02d}"
        cursor += dur


# Cycling vocabulary used when auto-splitting one long shot into multiple
# children. Picked so consecutive children get visually distinct framing
# even if the model didn't bother to vary them itself.
_SPLIT_CAMERA_MOVES = ("locked off", "slow push-in", "tilt down",
                       "lateral drift", "handheld drift", "rack focus")
_SPLIT_LENSES = ("35mm", "50mm", "85mm", "24mm wide", "100mm macro", "70mm")
_SPLIT_SHOT_SIZES = ("Wide", "Medium", "Close-up", "Medium Close-up",
                     "Extreme Close-up", "Medium Wide")


def _split_text_into_clauses(text: str, n_parts: int) -> list[str]:
    """Split `text` into approximately `n_parts` substrings on natural breath
    boundaries (em-dash, semicolon, comma, conjunction). Falls back to even
    word-count splits if no punctuation is found. Used by the dedupe + split
    pass so child shots get distinct narration slices instead of repeating
    the parent's line.
    """
    text = (text or "").strip()
    if not text or n_parts <= 1:
        return [text] if text else []

    # Preferred split markers, most-distinctive first.
    import re
    pieces: list[str] = []
    remaining = text
    splitters = [r"\s+—\s+", r";\s+", r",\s+(?:and|but|or|while|which|that|when|because)\s+",
                 r",\s+", r"\s+(?:and|but|or)\s+"]
    for pat in splitters:
        if len(pieces) >= n_parts:
            break
        parts = re.split(pat, remaining, maxsplit=n_parts - len(pieces) - 1)
        if len(parts) > 1:
            pieces.extend(p.strip() for p in parts[:-1] if p.strip())
            remaining = parts[-1].strip()
    if remaining:
        pieces.append(remaining)

    # If natural splits didn't produce enough pieces, fall back to even
    # word-count chunks for the leftovers.
    if len(pieces) < n_parts:
        words = text.split()
        chunk = max(1, len(words) // n_parts)
        pieces = [
            " ".join(words[i:i + chunk])
            for i in range(0, len(words), chunk)
        ]
        # Merge any final fragment into the prior chunk to avoid a tiny tail.
        if len(pieces) > n_parts:
            pieces[-2] = (pieces[-2] + " " + pieces[-1]).strip()
            pieces = pieces[:-1]
    return [p for p in pieces if p]


def _clone_shot_with_variation(base: dict, idx: int) -> dict:
    """Return a copy of `base` with cycling camera/lens/size vocabulary
    indexed by `idx`. Used when splitting one parent shot into multiple
    children — each child gets a distinct visual feel."""
    child = dict(base)
    child['camera_move'] = _SPLIT_CAMERA_MOVES[idx % len(_SPLIT_CAMERA_MOVES)]
    child['lens'] = _SPLIT_LENSES[idx % len(_SPLIT_LENSES)]
    # Only override shot_size if the original is a "default" generic value;
    # otherwise we'd erase a deliberate choice from the model.
    base_size = (base.get('shot_size') or base.get('angle') or '').lower()
    if not base_size or base_size in {'medium', 'wide', 'close-up', 'cu', 'mcu'}:
        child['shot_size'] = _SPLIT_SHOT_SIZES[idx % len(_SPLIT_SHOT_SIZES)]
    return child


def _dedupe_and_split_shots(shots: list[dict],
                            max_shot_duration: float) -> list[dict]:
    """Two-part post-pass on Stage 4 output:

    1. **Dedupe**: if N adjacent shots share the same `script_beat`, that's a
       model bug (padding the count instead of splitting the text). Slice
       the shared script_beat into N clauses on natural boundaries and assign
       one clause per shot. Visual fields (composition, lens, camera) stay
       per-shot — only the text changes.

    2. **Split oversize**: any single shot whose script_beat would require
       longer than `max_shot_duration` to read gets replaced by K child
       shots, each with a clause of the text and cycling camera/lens/size
       vocab so the children feel like a real sequence, not duplicates.

    Returns a new list with sequential shot_numbers. Original is not mutated.
    """
    max_words = max(4, int(max_shot_duration * TARGET_WPS))

    # Step 1: dedupe adjacent identical script_beats by clause-slicing.
    deduped: list[dict] = []
    i = 0
    while i < len(shots):
        j = i + 1
        sb = (shots[i].get('script_beat') or '').strip()
        while (j < len(shots)
               and (shots[j].get('script_beat') or '').strip() == sb
               and sb):
            j += 1
        run = shots[i:j]
        if len(run) > 1 and sb:
            slices = _split_text_into_clauses(sb, len(run))
            # If we got fewer slices than shots (very short text), the
            # remaining duplicates collapse — drop them.
            for k, shot in enumerate(run[:len(slices)]):
                clone = dict(shot)
                clone['script_beat'] = slices[k]
                deduped.append(clone)
        else:
            deduped.extend(dict(s) for s in run)
        i = j

    # Step 2: split oversize shots.
    final: list[dict] = []
    for shot in deduped:
        wc = len((shot.get('script_beat') or '').split())
        if wc <= max_words or wc == 0:
            final.append(shot)
            continue
        # Need ceil(wc / max_words) children to fit under the cap.
        import math
        n_children = max(2, math.ceil(wc / max_words))
        slices = _split_text_into_clauses(shot.get('script_beat') or '', n_children)
        if not slices:
            final.append(shot)
            continue
        for k, piece in enumerate(slices):
            child = _clone_shot_with_variation(shot, k)
            child['script_beat'] = piece
            # First child keeps the parent's directors_intent; subsequent
            # children inherit but tag the position so downstream review
            # sees what happened.
            if k > 0:
                child['directors_intent'] = (
                    (shot.get('directors_intent') or '') +
                    f" (split {k + 1}/{len(slices)})"
                ).strip()
            final.append(child)

    # Renumber sequentially.
    for n, shot in enumerate(final, start=1):
        shot['shot_number'] = str(n)
    return final

def _call_stage4_batch(
    *, uid, pid, api_key, prompt, schema, model_kwargs, batch_idx, batches_total,
):
    """Single Gemini call for Stage 4 with one wrapper-retry on parse/empty.

    gemini_client already retries 503/429/quota internally. This wrapper
    handles a different class of error: model returned bytes but JSON
    parsing failed, or the response was empty after retries. ONE retry
    here, then bubble up.
    """
    last_exc = None
    for attempt in range(2):
        try:
            raw = generate_content(
                prompt, api_key=api_key,
                response_mime_type="application/json",
                response_schema=schema,
                uid=uid, project_id=pid,
                description=f"agentic_stage_4_batch_{batch_idx + 1}"
                            + ("_retry" if attempt else ""),
                **model_kwargs,
            )
            if not raw or not str(raw).strip():
                raise ValueError(
                    f"Empty response from Gemini for Stage 4 batch "
                    f"{batch_idx + 1}/{batches_total}")
            parsed_batch = _parse_json_response(raw)
            return parsed_batch.get('shots') or []
        except (ValueError, Exception) as e:
            last_exc = e
            if attempt == 0:
                print(f"[Stage4 batch {batch_idx + 1}] parse/empty failure: "
                      f"{type(e).__name__}: {e!s} — retrying once")
            else:
                raise
    if last_exc:
        raise last_exc
    return []


def _run_stage4_batched(
    uid: str, pid: str, context: dict, stages_so_far: list[dict],
    feedback: str | None, api_key: str | None,
    progress_callback: Callable[[dict], None] | None = None,
) -> dict:
    """Run Stage 4 in sequential batches of ~10 beats each.

    Per-batch target = round(total_target * batch_words / total_words),
    so the sum across batches matches the global pacing target. Batches
    are numbered continuously. If a batch undershoots its target by more
    than PACING_TOLERANCE (15%), retry that batch once with a stricter
    prompt that quotes the actual count and required range.
    """
    from agentic_prompts import build_stage4_shot_list_prompt

    narration = context.get('narration') or {}
    batches = _split_narration_into_batches(narration)
    total_target = int(context.get('target_shot_count') or 0)
    total_words = max(1, int(context.get('total_words') or 0))
    pacing_tier = context.get('pacing_tier') or 'Standard'
    format_preset = context.get('format_preset') or 'standard'
    style_analysis = context.get('style_analysis')
    cast = context.get('cast')
    max_shot_duration = float(context.get('max_shot_duration') or 6.0)
    model_kwargs = dict(_STAGE_MODELS[4])
    bible = _compose_bible(stages_so_far, context.get('project_title', ''))

    print(f"[Stage4 batched] {len(batches)} batches | target={total_target} "
          f"shots from {total_words} words | tier={pacing_tier} "
          f"format_preset={format_preset!r}")

    all_shots: list[dict] = []
    starting_shot_number = 1

    for batch_idx, batch_narration in enumerate(batches):
        _check_cancelled(uid, pid)
        batch_words = _batch_word_count(batch_narration)
        if total_target > 0 and total_words > 0:
            batch_target = max(1, round(total_target * batch_words / total_words))
        else:
            batch_target = 0
        label = f"(batch {batch_idx + 1}/{len(batches)})"
        print(f"[Stage4 batch {batch_idx + 1}/{len(batches)}] "
              f"words={batch_words} target={batch_target} "
              f"starting_shot_number={starting_shot_number}")

        if progress_callback:
            progress_callback({
                'event': 'stage4_batch_started',
                'batch_idx': batch_idx + 1,
                'total_batches': len(batches),
                'batch_target': batch_target,
            })

        def _build(extra_feedback=None):
            return build_stage4_shot_list_prompt(
                bible_so_far=bible,
                cast=cast,
                narration=batch_narration,
                format_preset=format_preset,
                style_analysis=style_analysis,
                target_shot_count=batch_target,
                pacing_tier=pacing_tier,
                total_words=batch_words,
                batch_info=label,
                starting_shot_number=starting_shot_number,
                max_shot_duration=max_shot_duration,
                target_wps=TARGET_WPS,
                feedback=(extra_feedback or
                          (feedback if batch_idx == 0 else None)),
            )

        prompt, schema = _build()
        batch_shots = _call_stage4_batch(
            uid=uid, pid=pid, api_key=api_key, prompt=prompt, schema=schema,
            model_kwargs=model_kwargs, batch_idx=batch_idx,
            batches_total=len(batches),
        )

        # Pacing retry: if we undershoot the tolerance band, ask once more
        # with a stricter prompt that quotes the actual count.
        if batch_target > 0:
            low = max(1, int(batch_target * (1 - PACING_TOLERANCE)))
            high = int(batch_target * (1 + PACING_TOLERANCE))
            if len(batch_shots) < low:
                print(f"[Stage4 batch {batch_idx + 1}] returned "
                      f"{len(batch_shots)} shots, below tolerance "
                      f"{low}–{high}. Retrying with stricter prompt.")
                retry_note = (
                    f"PACING RETRY: your previous attempt returned only "
                    f"{len(batch_shots)} shots for this batch. The acceptable "
                    f"range is {low}–{high} shots; the target is {batch_target}. "
                    f"You collapsed too many beats into too few shots. Treat "
                    f"the pacing target as non-negotiable. If a beat has 40+ "
                    f"words, give it 4-8 shots. Emit the full shot list now."
                )
                prompt2, schema2 = _build(extra_feedback=retry_note)
                batch_shots = _call_stage4_batch(
                    uid=uid, pid=pid, api_key=api_key, prompt=prompt2,
                    schema=schema2, model_kwargs=model_kwargs,
                    batch_idx=batch_idx, batches_total=len(batches),
                )

        # Renumber to be globally sequential. The prompt asks the model to
        # start at starting_shot_number but it isn't always reliable — we
        # enforce it deterministically here.
        for i, shot in enumerate(batch_shots):
            shot['shot_number'] = str(starting_shot_number + i)
        starting_shot_number += len(batch_shots)
        all_shots.extend(batch_shots)
        delta = len(batch_shots) - batch_target if batch_target else 0
        print(f"[Stage4 batch {batch_idx + 1}/{len(batches)}] returned "
              f"{len(batch_shots)} shots (target {batch_target}, delta {delta:+d})")

    total_returned = len(all_shots)
    if total_target > 0:
        ratio = total_returned / total_target
        print(f"[Stage4 done] total_returned={total_returned} "
              f"total_target={total_target} ratio={ratio:.2f}")
    else:
        print(f"[Stage4 done] total_returned={total_returned} "
              f"total_target=0 (no pacing target was set)")

    # Dedupe adjacent shots that share a script_beat, then split any shot
    # whose script_beat would exceed max_shot_duration into multiple shots
    # with cycling visual variation. Both fixes are deterministic safety
    # nets for model behavior the prompt instructions don't always catch.
    pre_split = len(all_shots)
    all_shots = _dedupe_and_split_shots(all_shots, max_shot_duration)
    if len(all_shots) != pre_split:
        print(f"[Stage4 dedupe+split] {pre_split} → {len(all_shots)} shots "
              f"(cap={max_shot_duration}s)")

    # Deterministic duration + timestamp normalization. Replaces whatever the
    # model wrote with word_count(script_beat)/TARGET_WPS so the film's runtime
    # actually matches the narration. Capped at max_shot_duration as a final
    # safety net; the split pass above should have already ensured no shot
    # exceeds the cap.
    _normalize_shot_durations(all_shots, max_shot_duration=max_shot_duration)
    if all_shots:
        total_runtime = sum(float(s.get('duration') or 0) for s in all_shots)
        narration_runtime = total_words / TARGET_WPS if total_words else 0
        print(f"[Stage4 normalize] runtime={total_runtime:.1f}s "
              f"narration_implied={narration_runtime:.1f}s "
              f"shots={len(all_shots)} target_wps={TARGET_WPS} "
              f"max_shot={max_shot_duration}s")
    return {'shots': all_shots}


# ──────────────────────────────────────────────────────────────────────
# Stage 6 batched executor (with per-batch checkpointing)
# ──────────────────────────────────────────────────────────────────────


def _run_stage5_two_phase(
    uid: str, pid: str, context: dict, stages_so_far: list[dict],
    feedback: str | None, api_key: str | None,
    progress_callback: Callable[[dict], None] | None = None,
) -> dict:
    """Stage 5 above STAGE5_TWO_PHASE_THRESHOLD: split into two sequential
    calls. Both see the full shot list (no continuity drift). Phase A
    emits character_locks; Phase B emits everything else, reading Phase
    A's locks as context. Returns a merged Stage5ContinuityBrief dict.
    """
    from agentic_prompts import (
        build_stage5_phase_a_prompt, build_stage5_phase_b_prompt,
    )

    stage4 = next((s for s in stages_so_far if s.get('stage_number') == 4), None)
    if not stage4:
        raise ValueError("Stage 5 cannot run before Stage 4.")
    blueprints = (_apply_user_edits(stage4.get('output') or {},
                                    stage4.get('user_edits'))
                  .get('shots') or [])
    style_analysis = context.get('style_analysis')
    cast = context.get('cast')
    bible = _compose_bible(stages_so_far, context.get('project_title', ''))
    model_kwargs = dict(_STAGE_MODELS[5])

    print(f"[Stage5 two-phase] {len(blueprints)} shots — splitting into "
          f"Phase A (character_locks) + Phase B (vocab/callbacks/atmospheres).")

    # Phase A
    _check_cancelled(uid, pid)
    if progress_callback:
        progress_callback({'event': 'stage5_phase_a_started'})
    prompt_a, schema_a = build_stage5_phase_a_prompt(
        bible_so_far=bible, shot_blueprints=blueprints,
        style_analysis=style_analysis, cast=cast, feedback=feedback,
    )
    raw_a = generate_content(
        prompt_a, api_key=api_key,
        response_mime_type="application/json",
        response_schema=schema_a,
        uid=uid, project_id=pid,
        description="agentic_stage_5_phase_a",
        **model_kwargs,
    )
    if not raw_a or not str(raw_a).strip():
        raise ValueError("Empty response from Gemini for Stage 5 Phase A")
    parsed_a = _parse_json_response(raw_a)
    character_locks = parsed_a.get('character_locks') or []
    print(f"[Stage5 phase A] returned {len(character_locks)} character locks")

    # Phase B
    _check_cancelled(uid, pid)
    if progress_callback:
        progress_callback({'event': 'stage5_phase_b_started'})
    prompt_b, schema_b = build_stage5_phase_b_prompt(
        bible_so_far=bible, shot_blueprints=blueprints,
        character_locks=character_locks,
        style_analysis=style_analysis, cast=cast,
        feedback=None,  # feedback already consumed by Phase A
    )
    raw_b = generate_content(
        prompt_b, api_key=api_key,
        response_mime_type="application/json",
        response_schema=schema_b,
        uid=uid, project_id=pid,
        description="agentic_stage_5_phase_b",
        **model_kwargs,
    )
    if not raw_b or not str(raw_b).strip():
        raise ValueError("Empty response from Gemini for Stage 5 Phase B")
    parsed_b = _parse_json_response(raw_b)

    merged = {
        'character_locks': character_locks,
        'vocabulary_locks': parsed_b.get('vocabulary_locks') or [],
        'callback_map': parsed_b.get('callback_map') or [],
        'act_atmospheres': parsed_b.get('act_atmospheres') or [],
        'consistency_concerns': parsed_b.get('consistency_concerns') or '',
    }
    print(f"[Stage5 phase B] returned {len(merged['vocabulary_locks'])} vocab locks, "
          f"{len(merged['callback_map'])} callbacks, "
          f"{len(merged['act_atmospheres'])} act atmospheres")
    return merged


def _run_stage6_batched(
    uid: str, pid: str, context: dict, stages_so_far: list[dict],
    feedback: str | None, api_key: str | None,
    progress_callback: Callable[[dict], None] | None = None,
) -> tuple[dict, list[dict]]:
    """Run Stage 6 (Final Prompts) in sequential batches of STAGE6_BATCH_SIZE.

    Resumability: each batch's deltas are persisted to the Stage 6 doc as
    soon as the batch completes. If the worker is killed (Cloud Run
    timeout), the next run reads the existing deltas and skips completed
    batches. The merge runs once all batches have written.

    Returns (aggregated_parsed_for_bible, merged_shots).
    """
    from agentic_prompts import build_stage6_final_prompts_prompt

    stage4 = next((s for s in stages_so_far if s.get('stage_number') == 4), None)
    if not stage4:
        raise ValueError("Stage 6 cannot run before Stage 4 — no shot blueprints.")
    stage4_output = _apply_user_edits(stage4.get('output') or {},
                                      stage4.get('user_edits'))
    blueprints = stage4_output.get('shots') or []
    if not blueprints:
        raise ValueError("Stage 4 produced no shots — cannot run Stage 6.")
    # Re-run dedupe + split + normalize against the (possibly user-edited)
    # blueprints so the Visuals tab sees corrected timings and unique
    # script_beats even after manual edits.
    max_shot_duration = float(context.get('max_shot_duration') or 6.0)
    blueprints = _dedupe_and_split_shots(blueprints, max_shot_duration)
    _normalize_shot_durations(blueprints, max_shot_duration=max_shot_duration)

    # Continuity Brief from Stage 5 (post-user-edits if any).
    stage5 = next((s for s in stages_so_far if s.get('stage_number') == 5), None)
    continuity_brief = {}
    if stage5:
        continuity_brief = _apply_user_edits(stage5.get('output') or {},
                                             stage5.get('user_edits'))

    bible = _compose_bible(stages_so_far, context.get('project_title', ''))

    # Resolve canonical style anchor. The user-approved style_summary
    # (from style analysis / cast tab — the text shown in the UI) is the
    # source of truth. Stage 2's rendering_style is a fallback because the
    # Stage 2 LLM has been observed to invent a generic photoreal sentence
    # instead of echoing the user's style — which then gets force-injected
    # into every shot by the style-lock and overwrites the user's choice.
    style_analysis = context.get('style_analysis') or {}
    user_style = (style_analysis.get('style_summary') or '').strip()
    stage2 = next((s for s in stages_so_far if s.get('stage_number') == 2), None)
    s2_rendering_style = ''
    if stage2:
        s2_output = _apply_user_edits(stage2.get('output') or {},
                                      stage2.get('user_edits'))
        s2_rendering_style = (s2_output.get('rendering_style') or '').strip()
    rendering_style = user_style or s2_rendering_style
    anchor_source = (
        'user_style_summary' if user_style and rendering_style == user_style
        else ('stage2_rendering_style' if rendering_style else 'none')
    )
    print(f"[Stage6 anchor] source={anchor_source} text={rendering_style[:140]!r}")

    aspect_ratio = context.get('aspect_ratio', '16:9')

    total = len(blueprints)
    total_batches = (total + STAGE6_BATCH_SIZE - 1) // STAGE6_BATCH_SIZE
    model_kwargs = dict(_STAGE_MODELS[6])

    # Read checkpoint: which batches have already completed?
    existing = fh.read_production_stage(uid, pid, 6) or {}
    completed_batches = set(existing.get('completed_batches') or [])
    persisted_deltas = list(existing.get('output', {}).get('shot_deltas') or [])
    persisted_reviews = list(existing.get('output', {}).get('all_reviews') or [])

    if completed_batches:
        print(f"[agentic_pipeline] Stage 6 resume: {len(completed_batches)} of "
              f"{total_batches} batches already complete; skipping those")

    # Build list of batches we still need to run (resume-aware).
    batches_to_run: list[tuple[int, int]] = [
        (batch_idx, start)
        for batch_idx, start in enumerate(range(0, total, STAGE6_BATCH_SIZE))
        if batch_idx not in completed_batches
    ]
    if not batches_to_run:
        print(f"[Stage6 parallel] all {total_batches} batches already complete; "
              f"skipping to merge")
    else:
        print(f"[Stage6 parallel] running {len(batches_to_run)} batches with "
              f"{STAGE6_PARALLEL_WORKERS} workers (of {total_batches} total)")

    checkpoint_lock = threading.Lock()
    failed_batches: list[tuple[int, BaseException]] = []
    failures_lock = threading.Lock()

    def _run_one_batch(args: tuple[int, int]) -> tuple[int, int]:
        batch_idx, start = args
        # Cancel check happens INSIDE the future — otherwise a cancel issued
        # after submit but before this batch picks up the work would be
        # ignored until merge.
        try:
            _check_cancelled(uid, pid)
        except GenerationCancelled:
            raise

        chunk = blueprints[start:start + STAGE6_BATCH_SIZE]
        label = (f"(batch {batch_idx + 1}/{total_batches} · "
                 f"shots {start + 1}-{start + len(chunk)} of {total})")

        if progress_callback:
            progress_callback({
                'event': 'stage6_batch_started',
                'batch_idx': batch_idx + 1,
                'total_batches': total_batches,
                'shots_in_batch': len(chunk),
            })

        prompt, schema = build_stage6_final_prompts_prompt(
            bible_so_far=bible,
            shot_blueprints=chunk,
            continuity_brief=continuity_brief,
            style_analysis=style_analysis,
            rendering_style=rendering_style,
            aspect_ratio=aspect_ratio,
            batch_info=label,
            feedback=feedback if batch_idx == 0 else None,
        )

        # Wrapper retry on parse/empty failures (gemini_client already
        # retries 503/429/quota internally).
        parsed_batch = None
        last_exc: BaseException | None = None
        for attempt in range(2):
            try:
                raw = generate_content(
                    prompt, api_key=api_key,
                    response_mime_type="application/json",
                    response_schema=schema,
                    uid=uid, project_id=pid,
                    description=f"agentic_stage_6_batch_{batch_idx + 1}"
                                + ("_retry" if attempt else ""),
                    **model_kwargs,
                )
                if not raw or not str(raw).strip():
                    raise ValueError(
                        f"Empty response from Gemini for Stage 6 batch "
                        f"{batch_idx + 1}/{total_batches}")
                parsed_batch = _parse_json_response(raw)
                break
            except Exception as e:
                last_exc = e
                if attempt == 0:
                    print(f"[Stage6 batch {batch_idx + 1}] parse/empty failure: "
                          f"{type(e).__name__}: {e!s} — retrying once")
                else:
                    raise
        if parsed_batch is None:
            raise last_exc or RuntimeError(
                f"Stage 6 batch {batch_idx + 1} failed without exception")

        batch_deltas = parsed_batch.get('shot_deltas') or []
        batch_review = parsed_batch.get('continuity_review') or {}

        # Serialize the shared-state update + checkpoint write. Brief lock
        # — just appending lists and one Firestore write. Doesn't bottleneck
        # parallel Gemini calls.
        with checkpoint_lock:
            persisted_deltas.extend(batch_deltas)
            persisted_reviews.append(batch_review)
            completed_batches.add(batch_idx)
            fh.write_production_stage(uid, pid, 6, {
                'stage_number': 6,
                'stage_name': STAGE_NAMES[6],
                'status': 'running',
                'output': {
                    'shot_deltas': persisted_deltas,
                    'all_reviews': persisted_reviews,
                },
                'completed_batches': sorted(completed_batches),
                'total_batches': total_batches,
            })
        print(f"[Stage6 batch {batch_idx + 1}/{total_batches}] "
              f"completed with {len(batch_deltas)} deltas (persisted)")
        return batch_idx, len(batch_deltas)

    if batches_to_run:
        with concurrent.futures.ThreadPoolExecutor(
                max_workers=STAGE6_PARALLEL_WORKERS,
                thread_name_prefix='stage6_batch') as executor:
            futures = {executor.submit(_run_one_batch, b): b
                       for b in batches_to_run}
            for fut in concurrent.futures.as_completed(futures):
                batch_idx, _start = futures[fut]
                try:
                    fut.result()
                except GenerationCancelled:
                    # Cancellation: drop the rest of the work and bubble up
                    # so the worker exits cleanly.
                    for other in futures:
                        other.cancel()
                    raise
                except Exception as exc:
                    # Other failures: record and keep waiting on in-flight
                    # batches so they can checkpoint their progress.
                    with failures_lock:
                        failed_batches.append((batch_idx, exc))
                    print(f"[Stage6 batch {batch_idx + 1}] FAILED: "
                          f"{type(exc).__name__}: {exc!s}")

        if failed_batches:
            failed_batches.sort(key=lambda x: x[0])
            first_idx, first_exc = failed_batches[0]
            failed_summary = ", ".join(
                f"batch {bi + 1}: {type(e).__name__}: {e!s}"
                for bi, e in failed_batches[:3]
            )
            raise RuntimeError(
                f"Stage 6: {len(failed_batches)}/{len(batches_to_run)} "
                f"batches failed. First failure: {failed_summary}. "
                f"Resume to retry only the failed batches."
            ) from first_exc

    # All batches complete — aggregate continuity reviews and merge.
    def _join(field: str) -> str:
        parts = [r.get(field, '') for r in persisted_reviews if r.get(field)]
        return ' | '.join(parts)

    aggregated_review = {
        'variety_check': _join('variety_check'),
        'consistency_notes': _join('consistency_notes'),
        'pacing_notes': _join('pacing_notes'),
        'revisions_made': [r2 for r in persisted_reviews
                           for r2 in (r.get('revisions_made') or [])],
    }
    aggregated_parsed = {
        'continuity_review': aggregated_review,
        'shot_deltas': persisted_deltas,
    }

    merged_shots, unmatched = _merge_stage6_with_blueprints(
        blueprints, persisted_deltas,
        rendering_anchor=rendering_style,
        aspect_ratio=context.get('aspect_ratio', '16:9'),
    )
    if unmatched:
        print(f"[agentic_pipeline] Stage 6: {len(unmatched)} unmatched "
              f"shot_deltas (shot_numbers={unmatched[:10]}...)")
    return aggregated_parsed, merged_shots


# ──────────────────────────────────────────────────────────────────────
# Stage-level executor
# ──────────────────────────────────────────────────────────────────────

def _build_prompt(stage_number: int, context: dict, stages_so_far: list[dict],
                  feedback: str | None) -> tuple[str, type]:
    bible = _compose_bible(stages_so_far, context.get('project_title', ''))
    builder = STAGE_PROMPT_BUILDERS[stage_number]
    if stage_number == 1:
        return builder(
            narration=context['narration'],
            research_dossier=context.get('research_dossier'),
            audience=context.get('audience') or 'general',
            tone=context.get('tone') or 'conversational',
            format_preset=context.get('format_preset') or 'standard',
            viewer_outcome=context.get('viewer_outcome'),
            feedback=feedback,
        )
    if stage_number == 2:
        return builder(
            bible_so_far=bible,
            style_analysis=context.get('style_analysis'),
            cast=context.get('cast'),
            feedback=feedback,
        )
    if stage_number == 3:
        return builder(
            bible_so_far=bible,
            style_analysis=context.get('style_analysis'),
            feedback=feedback,
        )
    if stage_number == 4:
        # Stage 4 is batched — _run_stage4_batched builds per-batch prompts.
        # This branch is a safe fallback if a caller bypasses the batched
        # executor; produces a single-call prompt with the full narration.
        return builder(
            bible_so_far=bible,
            cast=context.get('cast'),
            narration=context['narration'],
            format_preset=context.get('format_preset'),
            style_analysis=context.get('style_analysis'),
            target_shot_count=int(context.get('target_shot_count') or 0),
            pacing_tier=context.get('pacing_tier') or 'Standard',
            total_words=int(context.get('total_words') or 0),
            feedback=feedback,
        )
    if stage_number == 5:
        # Stage 5 Continuity Brief: sees the full Stage 4 shot list.
        stage4 = next((s for s in stages_so_far if s.get('stage_number') == 4), None)
        blueprints = []
        if stage4:
            s4_out = _apply_user_edits(stage4.get('output') or {},
                                       stage4.get('user_edits'))
            blueprints = s4_out.get('shots') or []
        return builder(
            bible_so_far=bible,
            shot_blueprints=blueprints,
            style_analysis=context.get('style_analysis'),
            cast=context.get('cast'),
            feedback=feedback,
        )
    if stage_number == 6:
        # Stage 6 is batched — _run_stage6_batched builds prompts per chunk.
        # Fallback only.
        stage4 = next((s for s in stages_so_far if s.get('stage_number') == 4), None)
        blueprints = []
        if stage4:
            s4 = _apply_user_edits(stage4.get('output') or {}, stage4.get('user_edits'))
            blueprints = s4.get('shots') or []
        stage5 = next((s for s in stages_so_far if s.get('stage_number') == 5), None)
        continuity_brief = {}
        if stage5:
            continuity_brief = _apply_user_edits(stage5.get('output') or {},
                                                 stage5.get('user_edits'))
        # Prefer user-approved style_summary; fall back to Stage 2.
        style_analysis = context.get('style_analysis') or {}
        user_style = (style_analysis.get('style_summary') or '').strip()
        stage2 = next((s for s in stages_so_far if s.get('stage_number') == 2), None)
        s2_rendering_style = ''
        if stage2:
            s2_out = _apply_user_edits(stage2.get('output') or {}, stage2.get('user_edits'))
            s2_rendering_style = (s2_out.get('rendering_style') or '').strip()
        rendering_style = user_style or s2_rendering_style
        return builder(
            bible_so_far=bible,
            shot_blueprints=blueprints,
            continuity_brief=continuity_brief,
            style_analysis=style_analysis,
            rendering_style=rendering_style,
            aspect_ratio=context.get('aspect_ratio', '16:9'),
            feedback=feedback,
        )
    raise ValueError(f"Unknown stage_number {stage_number}")


def _apply_user_edits(output: dict, user_edits: dict | None) -> dict:
    """Apply user_edits dict on top of stage output. Supports dotted paths.

    Edits are stored as {"path.to.field": value} so the UI can patch
    nested fields. For Stage 4 shot list, we expect edits like
    {"shots.5.directors_intent": "tighter, more urgent"} — the index 5
    targets the 6th shot.
    """
    if not user_edits or not isinstance(output, dict):
        return output
    patched = json.loads(json.dumps(output))  # deep copy
    for path, value in user_edits.items():
        parts = path.split('.')
        target = patched
        for i, p in enumerate(parts[:-1]):
            if p.isdigit():
                idx = int(p)
                if not isinstance(target, list) or idx >= len(target):
                    target = None
                    break
                target = target[idx]
            else:
                if not isinstance(target, dict) or p not in target:
                    target = None
                    break
                target = target[p]
        if target is None:
            continue
        last = parts[-1]
        if last.isdigit() and isinstance(target, list):
            idx = int(last)
            if idx < len(target):
                target[idx] = value
        elif isinstance(target, dict):
            target[last] = value
    return patched


def run_stage(
    uid: str, pid: str, stage_number: int, *,
    feedback: str | None = None,
    api_key: str | None = None,
    progress_callback: Callable[[dict], None] | None = None,
) -> dict:
    """Run a single stage of the agentic pipeline.

    Steps:
      1. Load project context + all existing stage docs.
      2. Compose Production Bible from completed prior stages.
      3. Build stage prompt (persona + brief + principles + bible + feedback).
      4. Call Gemini with the stage's Pydantic response_schema.
      5. Parse the response (parser ladder).
      6. For Stage 5: merge shot_deltas with Stage 4 blueprints by shot_number.
      7. Render bible_section markdown.
      8. Write stage doc to production_stages/<id>.
      9. If Stage 5: also write merged shots to shots/ subcollection.
     10. Mark downstream stages 'stale' if user_edits or feedback caused a
         non-final stage to rerun.

    Returns the final stage doc payload. Raises GenerationCancelled if the
    run was cancelled mid-flight.
    """
    if stage_number not in (1, 2, 3, 4, 5, 6):
        raise ValueError(f"stage_number must be 1..6, got {stage_number}")

    _check_cancelled(uid, pid)
    if progress_callback:
        progress_callback({
            'event': 'stage_started',
            'stage_number': stage_number,
            'stage_label': STAGE_LABELS[stage_number],
        })

    # Mark this stage running.
    fh.write_production_stage(uid, pid, stage_number, {
        'stage_number': stage_number,
        'stage_name': STAGE_NAMES[stage_number],
        'status': 'running',
        'error': None,
    })

    try:
        context = _load_project_context(uid, pid)
        stages_so_far = fh.read_production_stages(uid, pid)
        # Filter out the stage we're currently running (it's marked 'running').
        stages_so_far = [s for s in stages_so_far
                         if s.get('stage_number') != stage_number]

        # Apply user_edits when composing bible so Stage N sees the user's
        # corrections to earlier stages, not just the raw LLM output.
        for s in stages_so_far:
            if s.get('user_edits'):
                edited = _apply_user_edits(s.get('output') or {}, s['user_edits'])
                # Re-render the bible_section from edited output.
                renderer = BIBLE_RENDERERS.get(s.get('stage_number'))
                if renderer:
                    s['bible_section'] = renderer(edited)
                s['output'] = edited

        merged_shots: list[dict] | None = None

        if stage_number == 4:
            # Batched executor handles narration splitting + sequential numbering.
            parsed = _run_stage4_batched(
                uid, pid, context, stages_so_far, feedback, api_key,
                progress_callback=progress_callback,
            )
        elif stage_number == 5:
            # Above the threshold, split into two phases so output-token
            # ceiling doesn't bite. Below, fall through to the standard
            # single-call path.
            stage4_for_count = next(
                (s for s in stages_so_far if s.get('stage_number') == 4), None)
            blueprint_count = 0
            if stage4_for_count:
                blueprint_count = len(
                    (stage4_for_count.get('output') or {}).get('shots') or [])
            if blueprint_count > STAGE5_TWO_PHASE_THRESHOLD:
                parsed = _run_stage5_two_phase(
                    uid, pid, context, stages_so_far, feedback, api_key,
                    progress_callback=progress_callback,
                )
            else:
                # Standard single-call dispatch below.
                prompt, schema = _build_prompt(
                    stage_number, context, stages_so_far, feedback)
                model_kwargs = dict(_STAGE_MODELS[stage_number])
                _check_cancelled(uid, pid)
                raw_response = generate_content(
                    prompt, api_key=api_key,
                    response_mime_type="application/json",
                    response_schema=schema,
                    uid=uid, project_id=pid,
                    description=f"agentic_stage_{stage_number}",
                    **model_kwargs,
                )
                if not raw_response or not str(raw_response).strip():
                    raise ValueError(
                        f"Empty response from Gemini for Stage {stage_number}")
                _check_cancelled(uid, pid)
                parsed = _parse_json_response(raw_response)
        elif stage_number == 6:
            # Batched + checkpointed executor handles Stage 6's full work.
            parsed, merged_shots = _run_stage6_batched(
                uid, pid, context, stages_so_far, feedback, api_key,
                progress_callback=progress_callback,
            )
        else:
            prompt, schema = _build_prompt(
                stage_number, context, stages_so_far, feedback)
            model_kwargs = dict(_STAGE_MODELS[stage_number])

            _check_cancelled(uid, pid)

            # Call Gemini with structured-output constraint.
            raw_response = generate_content(
                prompt,
                api_key=api_key,
                response_mime_type="application/json",
                response_schema=schema,
                uid=uid,
                project_id=pid,
                description=f"agentic_stage_{stage_number}",
                **model_kwargs,
            )

            if not raw_response or not str(raw_response).strip():
                raise ValueError(
                    f"Empty response from Gemini for Stage {stage_number}")

            _check_cancelled(uid, pid)

            # Parse via the existing ladder.
            parsed = _parse_json_response(raw_response)

        # Render the bible_section markdown for this stage.
        renderer = BIBLE_RENDERERS[stage_number]
        bible_section = renderer(parsed)

        # Persist the stage.
        payload = {
            'stage_number': stage_number,
            'stage_name': STAGE_NAMES[stage_number],
            'status': 'complete',
            'output': parsed,
            'bible_section': bible_section,
            'error': None,
            'last_run_at': datetime.now(timezone.utc).isoformat(),
        }
        if feedback:
            # Append to feedback history (keep last 10).
            existing = fh.read_production_stage(uid, pid, stage_number) or {}
            hist = list((existing.get('feedback_history') or []))[-9:]
            hist.append({
                'ts': datetime.now(timezone.utc).isoformat(),
                'note': feedback,
            })
            payload['feedback_history'] = hist
        fh.write_production_stage(uid, pid, stage_number, payload)

        # Stage 6: write merged shots to the shots/ subcollection and a
        # production_data summary (without the shots array) onto the
        # project doc. We deliberately do NOT write the full `shots` array
        # onto the project doc — at >400 shots that exceeds Firestore's
        # 1 MB doc limit and the Visuals tab reads from the shots/
        # subcollection anyway.
        if stage_number == 6 and merged_shots is not None:
            fh.clear_shots(uid, pid)  # idempotent overwrite
            fh.write_shots(uid, pid, merged_shots, start_order=0)

            # Gather metadata for the top-level production_table:
            #   - style_summary — user-approved text (source of truth);
            #     fall back to Stage 2 only if the user didn't provide one
            #   - continuity_notes from Stage 5's callback_map
            #   - production_notes from Stage 5's consistency_concerns
            style_analysis = context.get('style_analysis') or {}
            style_summary = (style_analysis.get('style_summary') or '').strip()
            if not style_summary:
                stage2 = next((s for s in stages_so_far
                               if s.get('stage_number') == 2), None)
                if stage2:
                    s2_out = _apply_user_edits(stage2.get('output') or {},
                                                stage2.get('user_edits'))
                    style_summary = (s2_out.get('rendering_style') or '').strip()

            stage5 = next((s for s in stages_so_far
                           if s.get('stage_number') == 5), None)
            continuity_notes: list[str] = []
            challenging_shots = ''
            if stage5:
                s5_out = _apply_user_edits(stage5.get('output') or {},
                                            stage5.get('user_edits'))
                for cb in (s5_out.get('callback_map') or []):
                    sn = cb.get('shot_number', '?')
                    to = cb.get('callback_to_shot', '?')
                    nt = cb.get('note', '')
                    continuity_notes.append(
                        f"Shot {sn} echoes shot {to}: {nt}".strip())
                challenging_shots = (
                    s5_out.get('consistency_concerns') or '').strip()

            production_notes = {
                'challenging_shots': challenging_shots,
                'post_production': '',
                'recommended_workflow': (
                    'Generate first frames in batches. Use Veo for shots '
                    'with significant motion; static shots can use the '
                    'image-only path. Review continuity_notes when '
                    'sequencing the edit.'
                ),
            }

            from firebase_admin import firestore
            db = firestore.client()
            project_ref = db.collection('users').document(uid) \
                .collection('projects').document(pid)
            project_ref.set({
                'production_data': {
                    'success': True,
                    'production_table': {
                        'title': context.get('project_title', ''),
                        'aspect_ratio': context.get('aspect_ratio', '16:9'),
                        'style_summary': style_summary,
                        'continuity_notes': continuity_notes,
                        'production_notes': production_notes,
                        'total_shots': len(merged_shots),
                        'continuity_review':
                            parsed.get('continuity_review') or {},
                        # shots intentionally omitted — read from shots/
                        # subcollection (Firestore 1MB doc limit)
                    },
                },
            }, merge=True)

        if progress_callback:
            progress_callback({
                'event': 'stage_complete',
                'stage_number': stage_number,
                'stage_label': STAGE_LABELS[stage_number],
                'output_keys': list((parsed or {}).keys()),
            })

        return payload

    except GenerationCancelled:
        raise
    except Exception as e:
        err_msg = f"{type(e).__name__}: {e}"
        tb = traceback.format_exc(limit=4)
        print(f"[agentic_pipeline] Stage {stage_number} failed: {err_msg}\n{tb}")
        # Persist the error onto the stage doc + append to error log.
        fh.write_production_stage(uid, pid, stage_number, {
            'status': 'error',
            'error': err_msg,
            'last_error_at': datetime.now(timezone.utc).isoformat(),
        })
        fh.append_error(uid, pid, {
            'phase': f"Stage {stage_number} ({STAGE_LABELS[stage_number]})",
            'stage_number': stage_number,
            'error': err_msg,
            'traceback': tb,
        })
        if progress_callback:
            progress_callback({
                'event': 'stage_failed',
                'stage_number': stage_number,
                'stage_label': STAGE_LABELS[stage_number],
                'error': err_msg,
            })
        raise


# ──────────────────────────────────────────────────────────────────────
# Single-stage worker (gated pipeline)
# ──────────────────────────────────────────────────────────────────────
#
# The pipeline does NOT auto-flow. The worker runs exactly one stage and
# exits. The user advances by clicking Approve on the completed stage —
# the /approve endpoint spawns a fresh worker for the next pending or
# stale stage. This guarantees every stage gets explicit human review
# before downstream work runs against it.

def run_pipeline_worker(
    uid: str, pid: str, task_id: str, api_key: str | None,
    start_at: int = 1,
    feedback: str | None = None,
) -> None:
    """Execute exactly one stage (`start_at`) and exit.

    `start_at` is the stage to run. `feedback` is forwarded to run_stage
    when the caller is a Regenerate-with-feedback flow.

    Errors leave flow_state.status = 'error' so the UI surfaces the
    failure. Cancel wipes state from the endpoint side; we just bail.
    """
    n = int(start_at)
    print(f"[agentic_pipeline] worker started uid={uid} pid={pid} "
          f"task_id={task_id} stage={n}")
    _write_flow(uid, pid, {
        'status': 'running',
        'task_id': task_id,
        'current_stage': n,
        'cancelled': False,
        'started_at': datetime.now(timezone.utc).isoformat(),
        'last_event_at': datetime.now(timezone.utc).isoformat(),
    })

    try:
        _check_cancelled(uid, pid)
        run_stage(uid, pid, n, api_key=api_key, feedback=feedback)

        # Stage completed — leave pipeline awaiting user approval.
        new_status = 'complete' if n == 6 else 'awaiting_approval'
        _write_flow(uid, pid, {
            'status': new_status,
            'current_stage': n,
            'last_completed_stage': n,
            'last_event_at': datetime.now(timezone.utc).isoformat(),
            **({'completed_at': datetime.now(timezone.utc).isoformat()}
               if n == 6 else {}),
        })
        print(f"[agentic_pipeline] worker finished stage {n} "
              f"(status={new_status})")

    except GenerationCancelled:
        print(f"[agentic_pipeline] worker cancelled uid={uid} pid={pid}")
        return
    except Exception as e:
        print(f"[agentic_pipeline] worker failed at stage {n}: "
              f"{type(e).__name__}: {e}")
        _write_flow(uid, pid, {
            'status': 'error',
            'error': f"{type(e).__name__}: {e}",
            'current_stage': n,
            'last_event_at': datetime.now(timezone.utc).isoformat(),
        })


def find_next_runnable_stage(uid: str, pid: str) -> int | None:
    """Return the lowest stage number with status pending/stale/error, or
    None if every stage is complete. Used by the /approve endpoint to
    decide which stage to spawn next.
    """
    stages = fh.read_production_stages(uid, pid)
    by_num = {int(s.get('stage_number') or 0): s for s in stages}
    for n in range(1, 7):
        s = by_num.get(n) or {}
        status = s.get('status', 'pending')
        if status in ('pending', 'stale', 'error'):
            return n
    return None


def get_pipeline_state(uid: str, pid: str) -> dict:
    """Return everything the UI needs to render the 5-panel layout."""
    stages_raw = fh.read_production_stages(uid, pid)
    flow = _read_flow(uid, pid)

    # Compose bible from completed stages (with user edits applied).
    composed_stages = []
    for s in stages_raw:
        if s.get('user_edits'):
            edited = _apply_user_edits(s.get('output') or {}, s['user_edits'])
            renderer = BIBLE_RENDERERS.get(s.get('stage_number'))
            if renderer:
                s = {**s, 'bible_section': renderer(edited), 'output': edited}
        composed_stages.append(s)

    project_context = {}
    try:
        project_context = _load_project_context(uid, pid)
    except Exception:
        pass

    bible_markdown = _compose_bible(composed_stages,
                                    project_context.get('project_title', ''))

    # Normalize: ensure every stage 1..6 has an entry the UI can render.
    by_num = {s.get('stage_number'): s for s in composed_stages}
    stages_view = []
    for n in range(1, 7):
        s = by_num.get(n) or {
            'stage_number': n,
            'stage_name': STAGE_NAMES[n],
            'status': 'pending',
        }
        # Strip Firestore internals.
        view = {
            'stage_number': s.get('stage_number', n),
            'stage_name': s.get('stage_name', STAGE_NAMES[n]),
            'stage_label': STAGE_LABELS[n],
            'status': s.get('status', 'pending'),
            'output': s.get('output'),
            'user_edits': s.get('user_edits') or {},
            'bible_section': s.get('bible_section') or '',
            'error': s.get('error'),
            'last_run_at': s.get('last_run_at'),
            'feedback_history': s.get('feedback_history') or [],
            # Stage 6 checkpoint fields — UI Resume button reads these.
            'completed_batches': s.get('completed_batches') or [],
            'total_batches': s.get('total_batches') or 0,
        }
        stages_view.append(view)

    return {
        'stages': stages_view,
        'flow_state': flow,
        'bible_markdown': bible_markdown,
        'task_id': flow.get('task_id'),
    }

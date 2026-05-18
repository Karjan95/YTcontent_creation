"""
Research & Script Writer
========================
Orchestrates the script pipeline:
  Narration: Gemini writes a flowing narration (organized by acts/beats)
  Production: Gemini splits narration into timed shots and generates prompts

This module provides helper functions that server.py calls.
"""

import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, os.path.dirname(__file__))
from research_templates import (
    get_template,
    get_all_templates_metadata,
    build_research_queries,
    build_script_prompt,
    build_production_prompt,
    build_title_suggestions_prompt,
    build_tone_suggestion_prompt,
    build_beat_regeneration_prompt,
    build_script_doctor_prompt,
    build_director_prompt,
    build_cinematographer_prompt,
    build_storyboard_prompt,
    build_continuity_supervisor_prompt,
    build_boundary_stitcher_prompt,
    build_dp_prompt,
    build_spine_extraction_prompt,
    build_spine_rerank_prompt,
    build_spine_suggest_edits_prompt,
)
from gemini_client import generate_content


def build_research_dossier(topic: str, template_id: str,
                           notebook_query_results: list) -> str:
    """
    Take raw NotebookLM query results and format them into a structured
    research dossier string for the script prompt.

    Args:
        topic: The research topic
        template_id: Which template was used
        notebook_query_results: List of dicts with {question, answer} pairs
    Returns:
        Formatted research dossier string
    """
    template = get_template(template_id)
    if not template:
        return f"Topic: {topic}\nNo structured research available."

    dossier_parts = [
        f"# Research Dossier: {topic}",
        f"## Template: {template['metadata']['name']}",
        f"## Research Mode: {template['research_config']['mode']}",
        "",
    ]

    for i, result in enumerate(notebook_query_results):
        question = result.get("question", f"Analysis #{i+1}")
        answer = result.get("answer", "No data found.")
        dossier_parts.append(f"### {question}")
        dossier_parts.append(answer)
        dossier_parts.append("")

    return "\n".join(dossier_parts)


def _validate_spine(spine: dict) -> dict:
    """Validate and clean a parsed spine object.

    Drops dangling source ids, drops flow ids that don't exist in key_claims,
    and rebuilds source_map keys from the union of source_ids actually used.
    Returns the cleaned spine. Raises ValueError on structural failures
    (missing key_claims, wrong types) so the caller can fall back to legacy.
    """
    if not isinstance(spine, dict):
        raise ValueError("spine is not a dict")
    claims = spine.get("key_claims")
    if not isinstance(claims, list) or not claims:
        raise ValueError("spine has no key_claims")

    valid_importance = {"primary", "supporting", "color"}
    source_map = spine.get("source_map") or {}
    if not isinstance(source_map, dict):
        source_map = {}

    cleaned_claims = []
    seen_ids = set()
    for c in claims:
        if not isinstance(c, dict):
            continue
        kid = c.get("id")
        text = (c.get("text") or "").strip()
        if not kid or not text or kid in seen_ids:
            continue
        seen_ids.add(kid)
        importance = c.get("importance") if c.get("importance") in valid_importance else "supporting"
        src_ids = [s for s in (c.get("source_ids") or []) if s in source_map]
        cleaned = {
            "id": kid,
            "text": text,
            "importance": importance,
            "source_ids": src_ids,
        }
        if c.get("act_hint"):
            cleaned["act_hint"] = c["act_hint"]
        cleaned_claims.append(cleaned)

    if not cleaned_claims:
        raise ValueError("no valid key_claims after cleaning")

    flow = spine.get("logical_flow") or []
    cleaned_flow = [k for k in flow if k in seen_ids]
    # Append any claims missing from flow at the end
    for kid in seen_ids:
        if kid not in cleaned_flow:
            cleaned_flow.append(kid)

    used_source_ids = {s for c in cleaned_claims for s in c["source_ids"]}
    cleaned_source_map = {sid: source_map[sid] for sid in used_source_ids if sid in source_map}

    return {
        "version": spine.get("version", 1),
        "topic": spine.get("topic", ""),
        "key_claims": cleaned_claims,
        "logical_flow": cleaned_flow,
        "source_map": cleaned_source_map,
        "extracted_at": spine.get("extracted_at"),
        "edited_by_user": bool(spine.get("edited_by_user", False)),
    }


def extract_narrative_spine(topic: str, research_dossier: str,
                             structured: dict = None,
                             api_key: str = None,
                             uid: str = None,
                             project_id: str = None) -> dict:
    """Extract a Narrative Spine (ranked claims + logical flow + source map) from a dossier.

    Returns:
        On success: {"success": True, "spine": {...validated spine...}}
        On failure: {"error": "...", "spine": None} — caller should fall back to legacy path.
    """
    if not research_dossier or not research_dossier.strip():
        return {"error": "Empty research dossier", "spine": None}

    prompt = build_spine_extraction_prompt(
        topic=topic,
        research_dossier=research_dossier,
        structured=structured,
    )

    raw_response = generate_content(
        prompt, model_name="gemini-2.5-flash",
        temperature=0.2, api_key=api_key,
        uid=uid, project_id=project_id, description="extract_narrative_spine",
    )

    if not raw_response or raw_response.startswith("Error:"):
        return {"error": raw_response or "Empty response from Gemini", "spine": None}

    try:
        parsed = _parse_json_response(raw_response)
    except (json.JSONDecodeError, ValueError) as e:
        return {"error": f"Could not parse spine JSON: {e}", "spine": None}

    # Bootstrap source_map from structured research when the model didn't repopulate it
    if structured and isinstance(structured, dict):
        existing = parsed.get("source_map") or {}
        for s in (structured.get("sources") or []):
            sid = s.get("id")
            if sid and sid not in existing:
                existing[sid] = {
                    "url": s.get("url", ""),
                    "title": s.get("title", ""),
                    "publisher": s.get("publisher", ""),
                    "quote": s.get("quote", ""),
                }
        parsed["source_map"] = existing

    parsed["topic"] = topic
    parsed["extracted_at"] = parsed.get("extracted_at") or _now_iso()

    try:
        cleaned = _validate_spine(parsed)
    except ValueError as e:
        return {"error": f"Spine validation failed: {e}", "spine": None}

    return {"success": True, "spine": cleaned}


def _now_iso() -> str:
    """ISO 8601 UTC timestamp helper."""
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


def rerank_narrative_spine(spine: dict, title: str = "", audience: str = "",
                            tone: str = "", format_preset: str = "",
                            api_key: str = None,
                            uid: str = None, project_id: str = None) -> dict:
    """Re-rank an existing spine for a chosen title / audience / tone.

    Preserves every claim's id and text. Only `importance` and `logical_flow`
    change. On any failure, returns the original spine unchanged so the caller
    can keep going with what they had.

    Returns:
        {"success": True, "spine": {...}}  on success
        {"error": "...", "spine": <original>} on failure (caller can fall back)
    """
    if not spine or not isinstance(spine, dict):
        return {"error": "No spine provided", "spine": spine}
    claims = spine.get("key_claims") or []
    if not claims:
        return {"error": "Spine has no claims", "spine": spine}

    prompt = build_spine_rerank_prompt(
        spine=spine, title=title, audience=audience,
        tone=tone, format_preset=format_preset,
    )
    raw = generate_content(
        prompt, model_name="gemini-2.5-flash",
        temperature=0.2, api_key=api_key,
        uid=uid, project_id=project_id, description="rerank_narrative_spine",
    )
    if not raw or raw.startswith("Error:"):
        return {"error": raw or "Empty response from Gemini", "spine": spine}

    try:
        parsed = _parse_json_response(raw)
    except (json.JSONDecodeError, ValueError) as e:
        return {"error": f"Could not parse rerank JSON: {e}", "spine": spine}

    valid_ids = {c.get("id") for c in claims if c.get("id")}
    valid_importance = {"primary", "supporting", "color"}

    new_importance = {}
    for entry in (parsed.get("key_claims") or []):
        if not isinstance(entry, dict):
            continue
        kid = entry.get("id")
        imp = entry.get("importance")
        if kid in valid_ids and imp in valid_importance:
            new_importance[kid] = imp

    new_flow_raw = parsed.get("logical_flow") or []
    new_flow = [k for k in new_flow_raw if k in valid_ids]
    # Append any claims missing from the returned flow at the end (defensive)
    for kid in valid_ids:
        if kid not in new_flow:
            new_flow.append(kid)

    if not new_importance:
        return {"error": "Rerank returned no usable importance updates", "spine": spine}

    # Build the new spine: same claim text + sources, updated importance + flow
    updated_claims = []
    for c in claims:
        kid = c.get("id")
        cleaned = dict(c)
        if kid in new_importance:
            cleaned["importance"] = new_importance[kid]
        updated_claims.append(cleaned)

    return {
        "success": True,
        "spine": {
            **spine,
            "key_claims": updated_claims,
            "logical_flow": new_flow,
            "edited_by_user": False,
            "reranked_for": {
                "title": title or None,
                "audience": audience or None,
                "tone": tone or None,
                "format_preset": format_preset or None,
            },
        },
    }


def suggest_spine_edits(spine: dict, title: str = "", audience: str = "",
                         api_key: str = None,
                         uid: str = None, project_id: str = None) -> dict:
    """Ask the AI to propose 0-5 targeted improvements to a spine.

    Each suggestion has a kind (reorder | importance | edit_text), the affected
    claim id, the proposed change, and a one-sentence rationale. The caller's
    UI lets the user apply or reject each suggestion individually.

    Returns:
        {"success": True, "suggestions": [...], "overall_note": "..."}
        {"error": "..."} on failure
    """
    if not spine or not isinstance(spine, dict):
        return {"error": "No spine provided"}
    claims = spine.get("key_claims") or []
    if not claims:
        return {"error": "Spine has no claims"}

    prompt = build_spine_suggest_edits_prompt(
        spine=spine, title=title, audience=audience,
    )
    raw = generate_content(
        prompt, model_name="gemini-2.5-flash",
        temperature=0.4, api_key=api_key,
        uid=uid, project_id=project_id, description="suggest_spine_edits",
    )
    if not raw or raw.startswith("Error:"):
        return {"error": raw or "Empty response from Gemini"}

    try:
        parsed = _parse_json_response(raw)
    except (json.JSONDecodeError, ValueError) as e:
        return {"error": f"Could not parse suggestions JSON: {e}"}

    valid_ids = {c.get("id") for c in claims if c.get("id")}
    valid_kinds = {"reorder", "importance", "edit_text"}
    valid_importance = {"primary", "supporting", "color"}

    cleaned = []
    for s in (parsed.get("suggestions") or [])[:5]:
        if not isinstance(s, dict):
            continue
        kind = s.get("kind")
        kid = s.get("claim_id")
        rationale = (s.get("rationale") or "").strip()
        if kind not in valid_kinds or kid not in valid_ids or not rationale:
            continue
        if kind == "reorder":
            try:
                pos = int(s.get("new_position"))
            except (TypeError, ValueError):
                continue
            if pos < 0 or pos >= len(valid_ids):
                continue
            cleaned.append({"kind": "reorder", "claim_id": kid, "new_position": pos, "rationale": rationale})
        elif kind == "importance":
            new_imp = s.get("new_importance")
            if new_imp not in valid_importance:
                continue
            cleaned.append({"kind": "importance", "claim_id": kid, "new_importance": new_imp, "rationale": rationale})
        elif kind == "edit_text":
            new_text = (s.get("new_text") or "").strip()
            if not new_text:
                continue
            cleaned.append({"kind": "edit_text", "claim_id": kid, "new_text": new_text, "rationale": rationale})

    return {
        "success": True,
        "suggestions": cleaned,
        "overall_note": (parsed.get("overall_note") or "").strip(),
    }


def _salvage_truncated_shots(text: str):
    """Recover the valid prefix of a truncated `{"shots": [...]}` payload.

    Gemini occasionally hits its output token cap mid-object on huge phases
    (we observed 70-120 KB JSON outputs from Phase 3/5). The standard parser
    then loses ALL shots. This walks the shots array, tracks brace depth +
    string state, and returns whatever objects completed before the truncation.
    Returns a dict like `{"shots": [...N complete shots...]}` or None.
    """
    import re as _re
    m = _re.search(r'"shots"\s*:\s*\[', text)
    if not m:
        return None
    array_start = m.end()  # first char inside the array

    depth = 0           # nesting depth INSIDE the array
    in_string = False
    escape = False
    last_good_end = -1  # text index immediately after a complete top-level obj

    i = array_start
    n = len(text)
    while i < n:
        c = text[i]
        if escape:
            escape = False
        elif c == '\\' and in_string:
            escape = True
        elif in_string:
            if c == '"':
                in_string = False
        elif c == '"':
            in_string = True
        elif c == '{':
            depth += 1
        elif c == '}':
            depth -= 1
            if depth == 0:
                last_good_end = i + 1
        elif c == ']' and depth == 0:
            # Array closed cleanly — direct parse should have worked, bail.
            return None
        i += 1

    if last_good_end < 0:
        return None

    salvaged = text[:array_start] + text[array_start:last_good_end] + "]}"
    try:
        return json.loads(salvaged)
    except json.JSONDecodeError:
        return None


def _parse_json_response(raw_response: str) -> dict:
    """Parse JSON from a Gemini response, handling markdown code fences and
    salvaging truncated `{"shots": [...]}` payloads (huge phase outputs that
    hit the model's output token cap mid-object)."""
    if not raw_response:
        raise ValueError("Empty response from Gemini")
    text = raw_response.strip()

    # Strip markdown code fences (```json ... ``` or ``` ... ```)
    if text.startswith("```"):
        lines = text.split("\n")
        # Remove the opening ``` line
        lines = lines[1:]
        # Remove the closing ``` line (handle trailing whitespace/empty lines)
        while lines and lines[-1].strip() in ("```", ""):
            if lines[-1].strip() == "```":
                lines.pop()
                break
            lines.pop()
        text = "\n".join(lines).strip()

    # Try direct parse first
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Fallback: find the outermost { ... } in the text
    first_brace = text.find("{")
    last_brace = text.rfind("}")
    if first_brace != -1 and last_brace > first_brace:
        candidate = text[first_brace:last_brace + 1]
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass

    # Last resort: salvage as many complete shot objects as possible from a
    # truncated array. Better N-1 valid shots than zero — the coverage check
    # downstream will detect any missing beats and trigger a targeted retry.
    salvaged = _salvage_truncated_shots(text)
    if salvaged is not None:
        print(f"[parse] Salvaged truncated JSON: recovered {len(salvaged.get('shots') or [])} shots")
        return salvaged

    raise json.JSONDecodeError("No JSON object found", text, 0)


def generate_narration(topic: str, template_id: str, research_dossier: str,
                       duration_minutes: int = 10, audience: str = "general",
                       tone: str = "", focus: str = "", style_guide: str = None,
                       selected_title: str = None, format_preset: str = "",
                       viewer_outcome: str = "", style_blend_mode: str = "clone",
                       custom_audience: str = "", custom_tone: str = "",
                       api_key: str = None, structured: dict = None,
                       spine: dict = None,
                       uid: str = None, project_id: str = None) -> dict:
    """
    PHASE 1: Generate a flowing narration script using Gemini.

    Returns the narration organized by acts/beats — no timestamps or scene table.
    This output feeds into production (generate_production_table).

    Returns:
        Dict with 'success' and 'narration' (the parsed JSON), or 'error'
    """
    prompt = build_script_prompt(
        template_id=template_id,
        topic=topic,
        research_dossier=research_dossier,
        duration_minutes=duration_minutes,
        audience=audience,
        tone=tone,
        focus=focus,
        style_guide=style_guide,
        selected_title=selected_title,
        format_preset=format_preset,
        viewer_outcome=viewer_outcome,
        style_blend_mode=style_blend_mode,
        custom_audience=custom_audience,
        custom_tone=custom_tone,
        structured=structured,
        spine=spine,
    )

    raw_response = generate_content(
        prompt, model_name="gemini-3-flash-preview", api_key=api_key,
        uid=uid, project_id=project_id, description="narration",
    )

    if not raw_response or raw_response.startswith("Error:"):
        return {"error": raw_response or "Gemini returned an empty response for narration."}

    try:
        narration_data = _parse_json_response(raw_response)
        if spine:
            _sanitize_narration_claim_ids(narration_data, spine)
        return {"success": True, "narration": narration_data}
    except json.JSONDecodeError:
        return {
            "success": True,
            "narration": {
                "title": topic,
                "raw_text": raw_response,
                "parse_error": "Could not parse Phase 1 narration as JSON."
            }
        }


def _sanitize_narration_claim_ids(narration_data: dict, spine: dict) -> None:
    """Drop beat claim_ids that don't exist in the spine; recompute claim_ids_used.

    Mutates `narration_data` in place. Beats with zero remaining claim_ids
    are kept (rendered as `unsourced` in the UI) so the user can target a regen.
    """
    if not isinstance(narration_data, dict) or not isinstance(spine, dict):
        return
    valid_ids = {c.get("id") for c in (spine.get("key_claims") or []) if c.get("id")}
    if not valid_ids:
        return
    used = set()
    unsourced = 0
    for beat in narration_data.get("narration") or []:
        if not isinstance(beat, dict):
            continue
        raw_ids = beat.get("claim_ids") or []
        cleaned = [k for k in raw_ids if isinstance(k, str) and k in valid_ids]
        beat["claim_ids"] = cleaned
        used.update(cleaned)
        if not cleaned:
            unsourced += 1
    narration_data["claim_ids_used"] = sorted(used)
    if unsourced:
        print(f"[Narration] {unsourced} beat(s) returned with no valid claim_ids — rendered as unsourced")


def auto_suggest_tone(template_id: str, selected_title: str,
                      audience: str = "General", api_key: str = None,
                      uid: str = None, project_id: str = None) -> dict:
    """Auto-suggest the best tone for a title + audience combination."""
    prompt = build_tone_suggestion_prompt(
        template_id=template_id,
        selected_title=selected_title,
        audience=audience,
    )
    raw_response = generate_content(
        prompt, model_name="gemini-3-flash-preview", api_key=api_key,
        uid=uid, project_id=project_id, description="auto_suggest_tone",
    )
    if not raw_response or raw_response.startswith("Error:"):
        return {"suggested_tone": "Conversational", "reasoning": "Default (auto-suggest unavailable)"}
    try:
        return _parse_json_response(raw_response)
    except json.JSONDecodeError:
        return {"suggested_tone": "Conversational", "reasoning": "Default (parse error)"}


def regenerate_beats(topic: str, template_id: str, research_dossier: str,
                     full_narration: dict, target_act: str = None,
                     target_beat_indices: list = None, mode: str = "restyle",
                     audience: str = "General", tone: str = "",
                     duration_minutes: int = 10, api_key: str = None,
                     structured: dict = None,
                     spine: dict = None,
                     uid: str = None, project_id: str = None) -> dict:
    """
    Regenerate specific beats or an entire act within a narration.

    Args:
        topic: Video topic
        template_id: Template being used
        research_dossier: Full research dossier text (ignored when spine is supplied)
        full_narration: Complete narration JSON {title, narration: [...]}
        target_act: If set, regenerate all beats in this act
        target_beat_indices: List of 0-based beat indices to regenerate
        mode: 'restyle' or 'reimagine'
        audience, tone, duration_minutes: Context for the prompt
        api_key: Gemini API key
        spine: Optional Narrative Spine — when present, regenerated beats are
            anchored to the originals' claim_ids (restyle) or to spine claims
            of equal/higher importance (reimagine).

    Returns:
        Dict with 'success' and 'beats' (list of regenerated beats), or 'error'
    """
    # Resolve target indices for claim-id anchoring
    beats_all = full_narration.get("narration", []) if isinstance(full_narration, dict) else []
    if target_act and not target_beat_indices:
        target_beat_indices = [i for i, b in enumerate(beats_all) if b.get("act") == target_act]
    target_beat_indices = target_beat_indices or []

    original_claim_ids_per_idx = {}
    if spine:
        for i in target_beat_indices:
            if 0 <= i < len(beats_all):
                original_claim_ids_per_idx[i] = list(beats_all[i].get("claim_ids") or [])

    def _build_prompt(extra_system=""):
        p = build_beat_regeneration_prompt(
            template_id=template_id,
            topic=topic,
            research_dossier=research_dossier,
            full_narration=full_narration,
            target_beat_indices=target_beat_indices,
            target_act=target_act,
            mode=mode,
            audience=audience,
            tone=tone,
            duration_minutes=duration_minutes,
            structured=structured,
            spine=spine,
        )
        if extra_system and not p.startswith("Error:"):
            p = extra_system + "\n\n" + p
        return p

    prompt = _build_prompt()
    if prompt.startswith("Error:"):
        return {"error": prompt}

    def _call(p):
        return generate_content(
            p, model_name="gemini-3-flash-preview", api_key=api_key,
            uid=uid, project_id=project_id, description="regenerate_beats",
        )

    raw_response = _call(prompt)
    if not raw_response or raw_response.startswith("Error:"):
        return {"error": raw_response or "Gemini returned an empty response for beat regeneration."}

    try:
        regenerated = _parse_json_response(raw_response)
        if isinstance(regenerated, dict):
            regenerated = regenerated.get("beats", [regenerated])
        if not isinstance(regenerated, list):
            regenerated = [regenerated]
    except json.JSONDecodeError:
        return {"error": f"Could not parse regenerated beats as JSON: {raw_response[:200]}"}

    # Spine-aware claim-id verification (restyle mode requires set-equality)
    if spine and mode == "restyle" and original_claim_ids_per_idx:
        if not _claim_ids_match(regenerated, original_claim_ids_per_idx, target_beat_indices):
            print("[Regen] claim_ids drifted on restyle — retrying with tighter prompt")
            tighter = (
                "STRICT: This is a CLAIM-ANCHORED RESTYLE. Each regenerated beat MUST "
                "return the EXACT claim_ids of its original (same set, same elements, "
                "no additions, no removals). If you cannot satisfy this, return an "
                "error string instead of JSON."
            )
            raw_retry = _call(_build_prompt(extra_system=tighter))
            if raw_retry and not raw_retry.startswith("Error:"):
                try:
                    retry_parsed = _parse_json_response(raw_retry)
                    if isinstance(retry_parsed, dict):
                        retry_parsed = retry_parsed.get("beats", [retry_parsed])
                    if isinstance(retry_parsed, list) and _claim_ids_match(
                        retry_parsed, original_claim_ids_per_idx, target_beat_indices
                    ):
                        regenerated = retry_parsed
                    else:
                        print("[Regen] retry still drifted — accepting with warning")
                except json.JSONDecodeError:
                    print("[Regen] retry parse failed — accepting first response with warning")

    # Always sanitize: drop any claim_ids not in spine
    if spine:
        valid_ids = {c.get("id") for c in (spine.get("key_claims") or []) if c.get("id")}
        for b in regenerated:
            if isinstance(b, dict):
                b["claim_ids"] = [k for k in (b.get("claim_ids") or []) if k in valid_ids]

    return {"success": True, "beats": regenerated}


def _claim_ids_match(regenerated_beats, original_claim_ids_per_idx, target_beat_indices) -> bool:
    """Return True iff every regenerated beat's claim_ids set equals the original's at the same position."""
    if len(regenerated_beats) != len(target_beat_indices):
        return False
    for new_beat, orig_idx in zip(regenerated_beats, target_beat_indices):
        if not isinstance(new_beat, dict):
            return False
        new_set = set(new_beat.get("claim_ids") or [])
        orig_set = set(original_claim_ids_per_idx.get(orig_idx) or [])
        if new_set != orig_set:
            return False
    return True


def split_script_into_chunks(raw_text: str, max_words_per_chunk: int = 45) -> list:
    """Deterministically split a pasted script into chunks.

    Paragraph-first (blank-line split). Falls back to single-newline then
    sentence-split. Long chunks are greedy-packed by sentence so no chunk
    exceeds max_words_per_chunk. Markdown headers become their own chunk.
    The verbatim text inside chunks is preserved (whitespace only normalized
    for NBSP / zero-width characters before splitting).
    """
    import re

    if not raw_text:
        return []

    # Normalize exotic whitespace before splitting.
    text = raw_text.replace(" ", " ")  # NBSP → space
    text = re.sub(r"[​-‍﻿]", "", text)  # zero-width chars
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    # Lift Markdown headers onto their own paragraph so they split cleanly.
    text = re.sub(r"(?m)^(#{1,6})\s+(.*)$", r"\n\n\2\n\n", text)

    # Primary split on blank-line paragraphs.
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]

    # Fallback ladder: single-newline split, then sentence split.
    if len(paragraphs) <= 1:
        paragraphs = [p.strip() for p in text.split("\n") if p.strip()]
    if len(paragraphs) <= 1 and paragraphs:
        sentences = re.split(r"(?<=[.!?]) +", paragraphs[0])
        paragraphs = [s.strip() for s in sentences if s.strip()]

    chunks = []
    for para in paragraphs:
        if len(para.split()) <= max_words_per_chunk:
            chunks.append(para)
            continue
        # Greedy-pack sentences into chunks up to max_words_per_chunk.
        sentences = re.split(r"(?<=[.!?]) +", para)
        current = ""
        for sentence in sentences:
            proposed = len(current.split()) + len(sentence.split())
            if proposed > max_words_per_chunk and current:
                chunks.append(current.strip())
                current = sentence
            else:
                current = (current + " " + sentence).strip()
        if current:
            chunks.append(current.strip())

    return chunks


def _beat_fingerprint(text: str, n_words: int = 8) -> str:
    """First N normalized words of a beat — used to detect coverage in shots.
    Lowercased, punctuation stripped, single-spaced."""
    import re as _re
    cleaned = _re.sub(r'[^a-z0-9 ]+', ' ', (text or '').lower())
    cleaned = _re.sub(r'\s+', ' ', cleaned).strip()
    words = cleaned.split()
    return ' '.join(words[:n_words])


def _check_beat_coverage(input_beats: list, final_shots: list) -> list:
    """Return list of input beats not represented in final_shots.
    A beat is 'covered' if any shot's script_beat contains its fingerprint."""
    import re as _re
    if not input_beats:
        return []

    shot_corpus = ' '.join(
        _re.sub(r'\s+', ' ',
                _re.sub(r'[^a-z0-9 ]+', ' ', (s.get('script_beat') or '').lower())).strip()
        for s in (final_shots or [])
    )

    uncovered = []
    for idx, beat in enumerate(input_beats):
        text = beat.get('text', beat.get('narration', ''))
        fp = _beat_fingerprint(text)
        if not fp:
            continue
        if fp in shot_corpus:
            continue
        # Also try a shorter fingerprint as a fallback (Gemini may paraphrase)
        short_fp = _beat_fingerprint(text, n_words=4)
        if short_fp and short_fp in shot_corpus:
            continue
        uncovered.append({
            'index': idx,
            'act': beat.get('act', 'ACT 1'),
            'beat': beat.get('beat', f'Beat {idx + 1}'),
            'text': text,
        })
    return uncovered


_PATCHABLE_FIELDS = {
    "camera_movement", "camera_angle", "lighting_mood", "visual", "first_frame_prompt"
}


def _stitch_act_boundaries(final_shots: list, visual_brief: dict = None,
                           api_key: str = None,
                           uid: str = None, project_id: str = None) -> int:
    """Patch shot fields at act boundaries to improve cross-act continuity.

    Detects boundaries by finding consecutive shots whose 'act' differs.
    For each boundary, sends the joint pair to Gemini and applies returned
    deltas in place. Returns number of patches applied.

    Never modifies: script_beat, narration, shot_number, act, beat, veo_prompt, duration.
    """
    if not final_shots or len(final_shots) < 2:
        return 0

    # Detect boundaries by act transition in sequential shots.
    boundary_pairs = []
    for i in range(1, len(final_shots)):
        prev = final_shots[i - 1]
        nxt = final_shots[i]
        prev_act = (prev.get('act') or '').strip()
        next_act = (nxt.get('act') or '').strip()
        if prev_act and next_act and prev_act != next_act:
            boundary_pairs.append({
                'prev': prev, 'next': nxt,
                'prev_act': prev_act, 'next_act': next_act,
            })

    if not boundary_pairs:
        return 0

    print(f"[Production] Boundary stitcher: {len(boundary_pairs)} act joint(s) found")

    try:
        prompt = build_boundary_stitcher_prompt(boundary_pairs, visual_brief)
        raw = generate_content(
            prompt, model_name="gemini-2.5-flash",
            temperature=0.1, api_key=api_key,
            uid=uid, project_id=project_id, description="boundary_stitcher",
        )
        if not raw or raw.startswith("Error:"):
            print(f"[Production] Boundary stitcher skipped: {raw or 'empty response'}")
            return 0
        try:
            data = _parse_json_response(raw)
        except json.JSONDecodeError as e:
            print(f"[Production] Boundary stitcher JSON parse failed: {e}")
            return 0

        patches = data.get('patches', []) or []
        if not patches:
            print(f"[Production] Boundary stitcher: no patches needed")
            return 0

        # Index shots by shot_number for O(1) lookup.
        by_num = {str(s.get('shot_number', '')): s for s in final_shots}
        applied = 0
        for p in patches:
            if not isinstance(p, dict):
                continue
            num = str(p.get('shot_number', ''))
            field = p.get('field', '')
            new_value = p.get('new_value', '')
            if field not in _PATCHABLE_FIELDS:
                continue
            target = by_num.get(num)
            if not target or not isinstance(new_value, str) or not new_value.strip():
                continue
            target[field] = new_value
            applied += 1

        print(f"[Production] Boundary stitcher: {applied} patch(es) applied across "
              f"{len(boundary_pairs)} joint(s)")
        return applied
    except Exception as e:
        print(f"[Production] Boundary stitcher error: {e}")
        return 0


def generate_production_table(narration_json: dict, duration_minutes: int = 10,
                              style_analysis: dict = None,
                              aspect_ratio: str = "16:9",
                              api_key: str = None,
                              pacing_tier: str = "Standard",
                              quality_mode: str = "fast",
                              creative_direction: dict = None,
                              cast: dict = None,
                              format_preset: str = "",
                              spine: dict = None,
                              uid: str = None, project_id: str = None,
                              progress_callback=None) -> dict:
    """
    Generate production-ready prompts from narration beats using the 6-phase pipeline.

    Pipeline: Script Doctor → Director → Cinematographer → Storyboard → Continuity → DP

    The Script Doctor runs ONCE on the full narration before batching.
    All subsequent phases run per-batch with the shared Visual Brief.

    Args:
        narration_json: Narration object {title, narration: [{act, beat, text}, ...]}
        duration_minutes: Target video length
        style_analysis: Structured style dict {style_summary, style_intent, prompt_schema}
        aspect_ratio: Video aspect ratio
        api_key: Gemini API key
        pacing_tier: Pacing speed (Meditative, Relaxed, Standard, High Energy, Frenetic)
        quality_mode: Deprecated — always uses 6-phase pipeline (kept for backward compat)
    """
    beats = narration_json.get("narration", [])

    if not beats:
        return {"error": "No narration beats found. Generate narration first."}

    title = narration_json.get("title", "Untitled")

    # Normalize script: Split massive beats to avoid token limits.
    # Essential for manual pasted JSON or overly verbose generation.
    import re
    MAX_WORDS_PER_BEAT = 45
    normalized_beats = []
    for beat in beats:
        act = beat.get("act", "ACT 1")
        beat_name = beat.get("beat", "Beat")
        text = beat.get("text", beat.get("narration", "")).strip()
        
        if len(text.split()) > MAX_WORDS_PER_BEAT:
            sentences = re.split(r'(?<=[.!?]) +', text)
            current_chunk = ""
            for sentence in sentences:
                proposed_length = len(current_chunk.split()) + len(sentence.split())
                if proposed_length > MAX_WORDS_PER_BEAT and current_chunk:
                    normalized_beats.append({"act": act, "beat": beat_name, "text": current_chunk.strip()})
                    current_chunk = sentence
                else:
                    current_chunk = (current_chunk + " " + sentence).strip()
            if current_chunk:
                normalized_beats.append({"act": act, "beat": beat_name, "text": current_chunk.strip()})
        else:
            normalized_beats.append({"act": act, "beat": beat_name, "text": text})
            
    beats = normalized_beats
    narration_json["narration"] = beats # Update original object so _generate_single_batch uses correct chunks

    # Auto-map pacing tier from format preset if user hasn't explicitly changed it
    if format_preset:
        from research_templates import FORMAT_PRESETS
        preset_data = FORMAT_PRESETS.get(format_preset, {})
        auto_tier = preset_data.get("auto_pacing_tier")
        if auto_tier and pacing_tier == "Standard":  # only override default
            pacing_tier = auto_tier
            print(f"[Production] Auto-selected pacing tier '{pacing_tier}' from preset '{format_preset}'")

    # Define pacing parameters
    PACE_TIERS = {
        "Meditative": {"beats_per_batch": 12, "words_per_shot": 15},
        "Relaxed": {"beats_per_batch": 10, "words_per_shot": 11},
        "Standard": {"beats_per_batch": 8, "words_per_shot": 9},
        "High Energy": {"beats_per_batch": 5, "words_per_shot": 5},
        "Frenetic": {"beats_per_batch": 3, "words_per_shot": 3}
    }
    
    tier_config = PACE_TIERS.get(pacing_tier, PACE_TIERS["Standard"])
    BEATS_PER_BATCH = tier_config["beats_per_batch"]
    WORDS_PER_SHOT_TARGET = tier_config["words_per_shot"]

    # ── Phase 0: Script Doctor (runs ONCE before batching) ──
    print(f"[Production] Phase 0: Script Doctor analyzing full narration...")
    try:
        script_doctor_prompt = build_script_doctor_prompt(narration_json, style_analysis, creative_direction)
        raw_brief = generate_content(
            script_doctor_prompt, model_name="gemini-2.5-flash",
            temperature=0.3, api_key=api_key,
            uid=uid, project_id=project_id, description="script_doctor",
        )
        if raw_brief and not raw_brief.startswith("Error:"):
            visual_brief = _parse_json_response(raw_brief)
            brief_count = len(visual_brief.get("visual_brief", []))
            print(f"[Production] Script Doctor complete: {brief_count} beat briefs generated")
        else:
            print(f"[Production] Script Doctor failed: {(raw_brief or 'empty')[:100]}. Continuing without brief.")
            visual_brief = None
    except Exception as e:
        print(f"[Production] Script Doctor error: {e}. Continuing without brief.")
        visual_brief = None

    # Always use 6-phase pipeline. quality_mode controls whether Phase 4
    # (Continuity Supervisor) runs — it's the slowest non-critical phase,
    # so 'fast' (default) skips it and 'max' includes it.
    batch_fn = _generate_single_batch_6phase
    skip_continuity = (quality_mode or "fast").lower() != "max"
    mode_label = "6-Phase (max quality)" if not skip_continuity else "6-Phase (fast, no Phase 4)"

    # Small narrations: single call
    if len(beats) <= BEATS_PER_BATCH + 2:
        print(f"[Production] Mode: {mode_label}")
        single_result = batch_fn(narration_json, duration_minutes,
                        style_analysis=style_analysis,
                        aspect_ratio=aspect_ratio,
                        api_key=api_key,
                        pacing_tier=pacing_tier,
                        creative_direction=creative_direction,
                        cast=cast,
                        format_preset=format_preset,
                        visual_brief=visual_brief,
                        spine=spine,
                        skip_continuity=skip_continuity,
                        uid=uid, project_id=project_id)
        # Emit a single-batch progress event so streaming UI works uniformly.
        if progress_callback and "error" not in single_result:
            try:
                single_shots = single_result.get("production_table", {}).get("shots", [])
                progress_callback({"type": "batch", "batch_idx": 1, "total_batches": 1, "shots": single_shots})
            except Exception as cb_err:
                print(f"[Production] progress_callback error (ignored): {cb_err}")
        return single_result

    # Large narrations: batch by act
    MAX_CONCURRENT_BATCHES = 6  # bumped from 3 (2026-05-18): halves wall-clock on 6+ batch runs
    print(f"[Production] Large narration ({len(beats)} beats). Mode: {mode_label}. Batching by act...")

    # Group beats by act
    acts = {}
    for beat in beats:
        act_name = beat.get("act", "Unknown")
        if act_name not in acts:
            acts[act_name] = []
        acts[act_name].append(beat)

    # Build batches from acts (split large acts into sub-batches)
    batches = []
    for act_name, act_beats in acts.items():
        if len(act_beats) > BEATS_PER_BATCH:
            for i in range(0, len(act_beats), BEATS_PER_BATCH):
                batches.append(act_beats[i:i + BEATS_PER_BATCH])
        else:
            batches.append(act_beats)

    all_shots = []
    all_continuity = []
    all_challenging = []
    style_summary = ""

    # Calculate total words for proportional duration splitting
    total_words = sum(len(b.get("text", b.get("narration", "")).split()) for b in beats)
    estimated_total_shots = max(1, int(total_words / WORDS_PER_SHOT_TARGET))

    MAX_RETRIES = 2

    def process_batch(batch_idx, batch_beats):
        # Calculate offset based on previous words
        previous_beats = []
        for b in batches[:batch_idx - 1]:
            previous_beats.extend(b)

        previous_words = sum(len(b.get("text", b.get("narration", "")).split()) for b in previous_beats)
        batch_words = sum(len(b.get("text", b.get("narration", "")).split()) for b in batch_beats)

        # Proportional duration and shot offset
        batch_duration = max(1, round(duration_minutes * batch_words / total_words)) if total_words > 0 else duration_minutes
        shot_offset = max(1, round(estimated_total_shots * previous_words / total_words)) + 1 if total_words > 0 else 1

        batch_narration = {
            "title": title,
            "hook_type": narration_json.get("hook_type", ""),
            "narration": batch_beats,
        }

        print(f"[Production] Batch {batch_idx}/{len(batches)}: "
              f"{len(batch_beats)} beats, ~{batch_words} words, ~{batch_duration}min (Start shot: {shot_offset}) - STARTED")

        last_error = None
        for attempt in range(1, MAX_RETRIES + 2):  # attempts 1, 2, 3
            result = batch_fn(batch_narration, batch_duration,
                              style_analysis=style_analysis,
                              aspect_ratio=aspect_ratio,
                              api_key=api_key,
                              shot_start_number=shot_offset,
                              batch_label=f"batch {batch_idx}/{len(batches)}",
                              pacing_tier=pacing_tier,
                              creative_direction=creative_direction,
                              cast=cast,
                              format_preset=format_preset,
                              visual_brief=visual_brief,
                              spine=spine,
                              skip_continuity=skip_continuity,
                              uid=uid, project_id=project_id)

            if "error" not in result:
                break  # success

            last_error = result["error"]
            if attempt <= MAX_RETRIES:
                wait_sec = attempt * 3  # 3s, 6s backoff
                print(f"[Production] Batch {batch_idx} attempt {attempt} failed: {last_error}. "
                      f"Retrying in {wait_sec}s... ({MAX_RETRIES - attempt + 1} retries left)")
                time.sleep(wait_sec)
            else:
                print(f"[Production] Batch {batch_idx} FAILED after {MAX_RETRIES + 1} attempts: {last_error}")
                return {"batch_idx": batch_idx, "error": last_error}

        pt = result.get("production_table", {})
        batch_shots = pt.get("shots", [])
        print(f"[Production] Batch {batch_idx} COMPLETE: {len(batch_shots)} shots")

        return {
            "batch_idx": batch_idx,
            "shots": batch_shots,
            "continuity_notes": pt.get("continuity_notes", []),
            "challenging_shots": pt.get("production_notes", {}).get("challenging_shots", []),
            "style_summary": pt.get("style_summary", ""),
        }

    # Process batches in parallel, streaming results in batch-index order.
    # When a batch finishes out-of-order, hold it until the contiguous prefix
    # (1..K) is complete — then renumber + flush + emit progress events for that
    # prefix. This keeps shot_number assignment deterministic while still letting
    # the UI receive Act 1 the moment its batches finish.
    batch_results = {}
    streamed_up_to = 0
    final_shots = []
    final_continuity = []
    final_challenging = []
    failed_batches = []
    current_shot_num = 1

    if progress_callback:
        try:
            progress_callback({"type": "stage", "label": f"Producing {len(batches)} acts in parallel", "total_batches": len(batches)})
        except Exception as cb_err:
            print(f"[Production] progress_callback error (ignored): {cb_err}")

    def _drain_ready():
        """Flush every contiguous batch starting from streamed_up_to + 1.
        Renumbers in place, appends to final_shots/continuity, emits a progress event."""
        nonlocal streamed_up_to, current_shot_num, style_summary
        while (streamed_up_to + 1) in batch_results:
            next_idx = streamed_up_to + 1
            r = batch_results[next_idx]

            if "error" in r:
                failed_batches.append({
                    "batch": next_idx,
                    "total_batches": len(batches),
                    "error": r["error"],
                })
                print(f"[Production] WARNING: Batch {next_idx}/{len(batches)} failed permanently — "
                      f"these scenes will be missing. Error: {r['error']}")
                if progress_callback:
                    try:
                        progress_callback({"type": "batch_failed", "batch_idx": next_idx,
                                           "total_batches": len(batches), "error": r["error"]})
                    except Exception as cb_err:
                        print(f"[Production] progress_callback error (ignored): {cb_err}")
                streamed_up_to = next_idx
                continue

            batch_shots = r.get("shots", [])
            batch_continuity = r.get("continuity_notes", [])
            shot_map = {}
            renumbered = []
            for shot in batch_shots:
                old_num = str(shot.get("shot_number", ""))
                new_num = str(current_shot_num)
                shot_map[old_num] = new_num
                shot["shot_number"] = new_num
                final_shots.append(shot)
                renumbered.append(shot)
                current_shot_num += 1

            for note in batch_continuity:
                from_old = str(note.get("from_shot", ""))
                to_old = str(note.get("to_shot", ""))
                if from_old in shot_map:
                    note["from_shot"] = shot_map[from_old]
                if to_old in shot_map:
                    note["to_shot"] = shot_map[to_old]
                final_continuity.append(note)

            final_challenging.extend(r.get("challenging_shots", []))
            if next_idx == 1:
                style_summary = r.get("style_summary", "") or style_summary

            if progress_callback:
                try:
                    progress_callback({
                        "type": "batch",
                        "batch_idx": next_idx,
                        "total_batches": len(batches),
                        "shots": renumbered,
                    })
                except Exception as cb_err:
                    print(f"[Production] progress_callback error (ignored): {cb_err}")

            streamed_up_to = next_idx

    with ThreadPoolExecutor(max_workers=MAX_CONCURRENT_BATCHES) as executor:
        future_to_batch = {
            executor.submit(process_batch, idx + 1, batch_beats): idx + 1
            for idx, batch_beats in enumerate(batches)
        }
        for future in as_completed(future_to_batch):
            batch_idx = future_to_batch[future]
            try:
                result = future.result()
                batch_results[result["batch_idx"]] = result
            except Exception as e:
                import traceback
                traceback.print_exc()
                print(f"[Production] Batch {batch_idx} exception: {e}")
                batch_results[batch_idx] = {"batch_idx": batch_idx, "error": str(e)}
            _drain_ready()

    if not final_shots:
        return {"error": "All batches failed to produce shots.", "missing_beats": [
            {'index': i, 'act': b.get('act', 'ACT 1'),
             'beat': b.get('beat', f'Beat {i + 1}'),
             'text': b.get('text', b.get('narration', ''))}
            for i, b in enumerate(beats)
        ]}

    # ── Beat coverage check: did every input beat make it into the table? ──
    uncovered = _check_beat_coverage(beats, final_shots)
    if uncovered:
        print(f"[Production] Coverage gap: {len(uncovered)}/{len(beats)} beats missing. Retrying as targeted batch...")
        retry_narration = {
            "title": title,
            "hook_type": narration_json.get("hook_type", ""),
            "narration": [{"act": u['act'], "beat": u['beat'], "text": u['text']} for u in uncovered],
        }
        retry_result = _generate_single_batch_6phase(
            retry_narration, duration_minutes,
            style_analysis=style_analysis,
            aspect_ratio=aspect_ratio,
            api_key=api_key,
            shot_start_number=current_shot_num,
            batch_label="coverage retry",
            pacing_tier=pacing_tier,
            creative_direction=creative_direction,
            cast=cast,
            format_preset=format_preset,
            visual_brief=visual_brief,
            spine=spine,
            uid=uid, project_id=project_id,
        )
        if "error" not in retry_result:
            retry_shots = retry_result.get("production_table", {}).get("shots", [])
            for shot in retry_shots:
                shot["shot_number"] = str(current_shot_num)
                final_shots.append(shot)
                current_shot_num += 1
            print(f"[Production] Coverage retry recovered {len(retry_shots)} shots")
        else:
            print(f"[Production] Coverage retry failed: {retry_result['error']}")

        # Re-check after retry
        uncovered = _check_beat_coverage(beats, final_shots)
        if uncovered:
            print(f"[Production] Still uncovered after retry: {len(uncovered)} beats")
            return {
                "error": "coverage_failure",
                "missing_beats": uncovered,
                "production_table": {
                    "title": title,
                    "aspect_ratio": aspect_ratio,
                    "style_summary": style_summary,
                    "total_shots": len(final_shots),
                    "shots": final_shots,
                    "continuity_notes": final_continuity,
                },
            }

    # ── Boundary Stitcher: patch cross-act transitions (only when multi-batch) ──
    if len(batches) > 1:
        _stitch_act_boundaries(
            final_shots, visual_brief=visual_brief,
            api_key=api_key, uid=uid, project_id=project_id,
        )

    # Build warning message for partial failures
    batch_warning = None
    if failed_batches:
        failed_labels = [f"batch {fb['batch']}/{fb['total_batches']}" for fb in failed_batches]
        batch_warning = (
            f"Warning: {len(failed_batches)} of {len(batches)} section(s) failed after retries "
            f"({', '.join(failed_labels)}). The production table has {len(final_shots)} shots "
            f"but some scenes from the middle of your script may be missing. "
            f"You can regenerate to try again."
        )
        print(f"[Production] {batch_warning}")

    merged = {
        "title": title,
        "aspect_ratio": aspect_ratio,
        "style_summary": style_summary,
        "total_shots": len(final_shots),
        "shots": final_shots,
        "continuity_notes": final_continuity,
        "production_notes": {
            "challenging_shots": final_challenging,
            "recommended_workflow": "Generate in batch order for visual continuity",
            "post_production": "Review cross-batch transitions for consistency",
        },
    }

    if batch_warning:
        merged["batch_warning"] = batch_warning
        merged["failed_batches"] = failed_batches

    print(f"[Production] Complete: {len(final_shots)} total shots (normalized 1-{len(final_shots)}) from {len(batches)} batches")
    return {"success": True, "production_table": merged}


def _generate_single_batch(narration_json: dict, duration_minutes: int = 10,
                           style_analysis: dict = None,
                           aspect_ratio: str = "16:9",
                           api_key: str = None,
                           shot_start_number: int = 1,
                           batch_label: str = "",
                           pacing_tier: str = "Standard",
                           creative_direction: dict = None,
                           cast: dict = None,
                           format_preset: str = "",
                           uid: str = None, project_id: str = None) -> dict:
    """Generate production table for a single batch of narration beats."""
    prompt = build_production_prompt(
        narration_json=narration_json,
        duration_minutes=duration_minutes,
        style_analysis=style_analysis,
        aspect_ratio=aspect_ratio,
        shot_start_number=shot_start_number,
        pacing_tier=pacing_tier,
        creative_direction=creative_direction,
        format_preset=format_preset
    )

    label = f" ({batch_label})" if batch_label else ""
    print(f"[Production] Generating production table{label}...")
    raw_response = generate_content(
        prompt, model_name="gemini-3.1-pro-preview", temperature=0.1, api_key=api_key,
        uid=uid, project_id=project_id, description="production_single",
    )

    if not raw_response or raw_response.startswith("Error:"):
        return {"error": raw_response or "Gemini returned an empty response for production table."}

    try:
        production_data = _parse_json_response(raw_response)
        shot_count = len(production_data.get("shots", []))
        print(f"[Production] Got {shot_count} shots{label}")
        return {"success": True, "production_table": production_data}
    except json.JSONDecodeError:
        return {
            "success": True,
            "production_table": {
                "title": narration_json.get("title", "Untitled"),
                "raw_text": raw_response,
                "parse_error": f"Could not parse production JSON{label}."
            }
        }


def _generate_single_batch_3phase(narration_json: dict, duration_minutes: int = 10,
                                   style_analysis: dict = None,
                                   aspect_ratio: str = "16:9",
                                   api_key: str = None,
                                   shot_start_number: int = 1,
                                   batch_label: str = "",
                                   pacing_tier: str = "Standard",
                                   creative_direction: dict = None,
                                   cast: dict = None,
                                   format_preset: str = "",
                                   visual_brief: dict = None,
                                   spine: dict = None,
                                   uid: str = None, project_id: str = None) -> dict:
    """
    Generate production table using the 3-phase pipeline (Max Quality mode).

    Phase 1: Director — editorial cuts (where to split, duration, emotion)
    Phase 2: Storyboard Artist — visual composition (what each shot shows)
    Phase 3: DP — final prompts (first_frame, last_frame, veo)

    Same signature as _generate_single_batch() for drop-in compatibility.
    """
    label = f" ({batch_label})" if batch_label else ""

    # ── Phase 1: Director ──
    print(f"[Production 3-Phase] Phase 1: Director{label}...")
    director_prompt = build_director_prompt(
        narration_json=narration_json,
        duration_minutes=duration_minutes,
        shot_start_number=shot_start_number,
        pacing_tier=pacing_tier,
        creative_direction=creative_direction,
        format_preset=format_preset,
        spine=spine,
    )
    raw_director = generate_content(
        director_prompt, model_name="gemini-3.1-pro-preview",
        temperature=0.1, api_key=api_key,
        uid=uid, project_id=project_id, description="director_3phase",
    )
    if not raw_director or raw_director.startswith("Error:"):
        return {"error": f"Phase 1 (Director) failed{label}: {raw_director or 'empty response'}"}

    try:
        director_data = _parse_json_response(raw_director)
        director_shots = director_data.get("shots", [])
    except json.JSONDecodeError as e:
        return {"error": f"Phase 1 (Director) JSON parse failed{label}: {e}"}

    print(f"[Production 3-Phase] Phase 1 complete: {len(director_shots)} shots{label}")

    # ── Phase 2: Storyboard Artist ──
    print(f"[Production 3-Phase] Phase 2: Storyboard Artist{label}...")
    style_intent = style_analysis.get("style_intent", {}) if style_analysis else {}
    storyboard_prompt = build_storyboard_prompt(
        director_shots=director_shots,
        narration_json=narration_json,
        style_intent=style_intent,
        creative_direction=creative_direction,
        cast=cast,
    )
    raw_storyboard = generate_content(
        storyboard_prompt, model_name="gemini-3.1-pro-preview",
        temperature=0.1, api_key=api_key,
        uid=uid, project_id=project_id, description="storyboard_3phase",
    )
    if not raw_storyboard or raw_storyboard.startswith("Error:"):
        return {"error": f"Phase 2 (Storyboard) failed{label}: {raw_storyboard or 'empty response'}"}

    try:
        storyboard_data = _parse_json_response(raw_storyboard)
        storyboard_shots = storyboard_data.get("shots", [])
    except json.JSONDecodeError as e:
        return {"error": f"Phase 2 (Storyboard) JSON parse failed{label}: {e}"}

    print(f"[Production 3-Phase] Phase 2 complete: {len(storyboard_shots)} shots{label}")

    # ── Phase 3: Director of Photography ──
    print(f"[Production 3-Phase] Phase 3: Director of Photography{label}...")
    title = narration_json.get("title", "Untitled")
    dp_prompt = build_dp_prompt(
        storyboard_shots=storyboard_shots,
        style_analysis=style_analysis,
        aspect_ratio=aspect_ratio,
        cast=cast,
        title=title,
        creative_direction=creative_direction,
    )
    raw_dp = generate_content(
        dp_prompt, model_name="gemini-3.1-pro-preview",
        temperature=0.1, api_key=api_key,
        uid=uid, project_id=project_id, description="dp_3phase",
    )
    if not raw_dp or raw_dp.startswith("Error:"):
        return {"error": f"Phase 3 (DP) failed{label}: {raw_dp or 'empty response'}"}

    try:
        production_data = _parse_json_response(raw_dp)
        shot_count = len(production_data.get("shots", []))
        print(f"[Production 3-Phase] Phase 3 complete: {shot_count} shots{label}")
        return {"success": True, "production_table": production_data}
    except json.JSONDecodeError:
        return {
            "success": True,
            "production_table": {
                "title": title,
                "raw_text": raw_dp,
                "parse_error": f"Could not parse Phase 3 (DP) JSON{label}."
            }
        }


def _generate_single_batch_6phase(narration_json: dict, duration_minutes: int = 10,
                                   style_analysis: dict = None,
                                   aspect_ratio: str = "16:9",
                                   api_key: str = None,
                                   shot_start_number: int = 1,
                                   batch_label: str = "",
                                   pacing_tier: str = "Standard",
                                   creative_direction: dict = None,
                                   cast: dict = None,
                                   format_preset: str = "",
                                   visual_brief: dict = None,
                                   spine: dict = None,
                                   skip_continuity: bool = False,
                                   uid: str = None, project_id: str = None) -> dict:
    """
    Generate production table using the 6-phase pipeline.

    Phase 0: Script Doctor (pre-computed, passed via visual_brief)
    Phase 1: Director — editorial cuts + camera intent + emotional arc
    Phase 2: Cinematographer — camera technique from 62-technique library
    Phase 3: Storyboard Artist — layered visual compositions
    Phase 4: Continuity Supervisor — review + auto-fix
    Phase 5: DP — final prompts with lighting vocabulary
    """
    label = f" ({batch_label})" if batch_label else ""
    title = narration_json.get("title", "Untitled")
    style_intent = style_analysis.get("style_intent", {}) if style_analysis else {}

    def _call_phase(phase_name: str, prompt: str, temperature: float,
                    description: str, prev_count: int = 0) -> tuple:
        """Run a phase, parse shots, retry once if shot count drops >10% vs prev_count.
        Returns (shots_list, error_str or None)."""
        raw = generate_content(
            prompt, model_name="gemini-2.5-flash",
            temperature=temperature, api_key=api_key,
            uid=uid, project_id=project_id, description=description,
        )
        if not raw or raw.startswith("Error:"):
            return None, f"{phase_name} failed{label}: {raw or 'empty response'}"
        try:
            data = _parse_json_response(raw)
            shots = data.get("shots", [])
        except json.JSONDecodeError as e:
            return None, f"{phase_name} JSON parse failed{label}: {e}"

        if prev_count > 0 and len(shots) < prev_count * 0.9:
            print(f"[Production 6-Phase] {phase_name} dropped shots "
                  f"({len(shots)}/{prev_count}). Retrying once...")
            raw_retry = generate_content(
                prompt, model_name="gemini-2.5-flash",
                temperature=temperature, api_key=api_key,
                uid=uid, project_id=project_id, description=f"{description}_retry",
            )
            if raw_retry and not raw_retry.startswith("Error:"):
                try:
                    retry_data = _parse_json_response(raw_retry)
                    retry_shots = retry_data.get("shots", [])
                    if len(retry_shots) > len(shots):
                        shots = retry_shots
                        data = retry_data
                except json.JSONDecodeError:
                    pass
        return (shots, data), None

    # ── Phase 1: Director ──
    print(f"[Production 6-Phase] Phase 1: Director{label}...")
    director_prompt = build_director_prompt(
        narration_json=narration_json,
        duration_minutes=duration_minutes,
        shot_start_number=shot_start_number,
        pacing_tier=pacing_tier,
        creative_direction=creative_direction,
        format_preset=format_preset,
        visual_brief=visual_brief,
        spine=spine,
    )
    phase1, err = _call_phase("Phase 1 (Director)", director_prompt, 0.1, "director_6phase")
    if err:
        return {"error": err}
    director_shots, _ = phase1
    print(f"[Production 6-Phase] Phase 1 complete: {len(director_shots)} shots{label}")

    # ── Phase 2: Cinematographer ──
    print(f"[Production 6-Phase] Phase 2: Cinematographer{label}...")
    cinematographer_prompt = build_cinematographer_prompt(
        director_shots=director_shots,
        visual_brief=visual_brief,
    )
    phase2, err = _call_phase("Phase 2 (Cinematographer)", cinematographer_prompt,
                              0.2, "cinematographer_6phase",
                              prev_count=len(director_shots))
    if err:
        return {"error": err}
    cinematographer_shots, _ = phase2
    print(f"[Production 6-Phase] Phase 2 complete: {len(cinematographer_shots)} shots{label}")

    # ── Phase 3: Storyboard Artist ──
    print(f"[Production 6-Phase] Phase 3: Storyboard Artist{label}...")
    storyboard_prompt = build_storyboard_prompt(
        director_shots=cinematographer_shots,
        narration_json=narration_json,
        style_intent=style_intent,
        creative_direction=creative_direction,
        cast=cast,
        visual_brief=visual_brief,
    )
    phase3, err = _call_phase("Phase 3 (Storyboard)", storyboard_prompt,
                              0.1, "storyboard_6phase",
                              prev_count=len(cinematographer_shots))
    if err:
        return {"error": err}
    storyboard_shots, _ = phase3
    print(f"[Production 6-Phase] Phase 3 complete: {len(storyboard_shots)} shots{label}")

    # ── Phase 4: Continuity Supervisor ──
    # Phase 4 is a quality-of-life pass (variety/flow review) that takes
    # ~90-120s per batch. It's non-critical — failures fall through. When
    # skip_continuity is set we omit it entirely; the user opts in via the
    # "Max Quality" toggle. Removes the largest single contributor to the
    # 40-50 min wall-clock for large scripts.
    if skip_continuity:
        print(f"[Production 6-Phase] Phase 4 skipped{label} (fast mode)")
        corrected_shots = storyboard_shots
    else:
        print(f"[Production 6-Phase] Phase 4: Continuity Supervisor{label}...")
        continuity_prompt = build_continuity_supervisor_prompt(
            storyboard_shots=storyboard_shots,
            visual_brief=visual_brief,
        )
        raw_continuity = generate_content(
            continuity_prompt, model_name="gemini-2.5-flash",
            temperature=0.05, api_key=api_key,
            uid=uid, project_id=project_id, description="continuity_6phase",
        )
        if not raw_continuity or raw_continuity.startswith("Error:"):
            # Continuity is non-critical — fall through with uncorrected shots
            print(f"[Production 6-Phase] Phase 4 failed{label} — continuing with uncorrected shots")
            corrected_shots = storyboard_shots
        else:
            try:
                continuity_data = _parse_json_response(raw_continuity)
                corrected_shots = continuity_data.get("shots", storyboard_shots)
                # Guard: if Phase 4 truncated, fall back to uncorrected (never lose shots here)
                if len(corrected_shots) < len(storyboard_shots) * 0.9:
                    print(f"[Production 6-Phase] Phase 4 dropped shots "
                          f"({len(corrected_shots)}/{len(storyboard_shots)}){label} — using uncorrected")
                    corrected_shots = storyboard_shots
                else:
                    modified = continuity_data.get("review_summary", {}).get("shots_modified", 0)
                    print(f"[Production 6-Phase] Phase 4 complete: {modified} shots modified{label}")
            except json.JSONDecodeError:
                print(f"[Production 6-Phase] Phase 4 parse failed{label} — using uncorrected shots")
                corrected_shots = storyboard_shots

    # ── Phase 5: DP ──
    print(f"[Production 6-Phase] Phase 5: DP{label}...")
    dp_prompt = build_dp_prompt(
        storyboard_shots=corrected_shots,
        style_analysis=style_analysis,
        aspect_ratio=aspect_ratio,
        title=title,
        creative_direction=creative_direction,
        cast=cast,
        visual_brief=visual_brief,
    )
    phase5, err = _call_phase("Phase 5 (DP)", dp_prompt, 0.1, "dp_6phase",
                              prev_count=len(corrected_shots))
    if err:
        return {"error": err}
    dp_shots, production_data = phase5
    print(f"[Production 6-Phase] Phase 5 complete: {len(dp_shots)} shots with prompts{label}")
    return {"success": True, "production_table": production_data}


def start_deep_research(topic: str, template_id: str, api_key: str = None) -> dict:
    """
    Start an async deep research session using the Deep Research Agent.

    Uses the Interactions API with background=True. Returns immediately
    with an interaction_id that can be polled for results.

    Returns:
        Dict with 'interaction_id' and 'status', or 'error'
    """
    from google import genai

    template = get_template(template_id)
    template_name = template['metadata']['name'] if template else template_id
    analysis_questions = template['research_config']['analysis_questions'] if template else [
        f"Provide a comprehensive analysis of {topic}"
    ]

    questions_text = "\n".join(f"- {q}" for q in analysis_questions)

    research_input = f"""Conduct deep, comprehensive research on the following topic.

TOPIC: {topic}
RESEARCH TEMPLATE: {template_name}

Answer each of these analysis questions with specific facts, names, numbers, and dates:
{questions_text}

Provide a thorough research report with:
- Detailed answers to each question above
- Specific facts, statistics, and data points
- Named sources for key claims
- A summary of all findings"""

    try:
        if not api_key:
            raise ValueError("No API key provided. Please save your Gemini API key in Settings.")
        client = genai.Client(api_key=api_key)

        interaction = client.interactions.create(
            input=research_input,
            agent='deep-research-pro-preview-12-2025',
            background=True
        )

        print(f"[Deep Research] Started interaction: {interaction.id}")
        return {
            "interaction_id": interaction.id,
            "status": "in_progress",
        }

    except Exception as e:
        print(f"[Deep Research] Failed to start: {e}")
        return {"error": f"Deep Research failed to start: {str(e)}"}


def poll_deep_research(interaction_id: str, api_key: str = None) -> dict:
    """
    Poll a running deep research interaction for results.

    Returns:
        Dict with 'status' ('in_progress', 'completed', 'failed')
        and 'result' (the research text) when completed.
    """
    from google import genai

    try:
        if not api_key:
            raise ValueError("No API key provided. Please save your Gemini API key in Settings.")
        client = genai.Client(api_key=api_key)

        interaction = client.interactions.get(interaction_id)

        if interaction.status == "completed":
            result_text = interaction.outputs[-1].text if interaction.outputs else ""
            print(f"[Deep Research] Completed: {len(result_text)} chars")
            return {
                "status": "completed",
                "result": result_text,
            }
        elif interaction.status == "failed":
            error_msg = str(getattr(interaction, 'error', 'Unknown error'))
            print(f"[Deep Research] Failed: {error_msg}")
            return {
                "status": "failed",
                "error": error_msg,
            }
        else:
            print(f"[Deep Research] Status: {interaction.status}")
            return {
                "status": "in_progress",
            }

    except Exception as e:
        print(f"[Deep Research] Poll error: {e}")
        return {"status": "failed", "error": str(e)}


# ═══════════════════════════════════════════════════════════════════
#  STRUCTURED RESEARCH PIPELINE
#  (Planner → parallel Pro+Search sub-researchers → merger with stable ids)
# ═══════════════════════════════════════════════════════════════════

import re as _re
from datetime import datetime as _datetime


def _extract_grounding_sources(response) -> list:
    """Pull {url, title, snippet} entries from Gemini's grounding_metadata.

    The google-genai SDK exposes grounding data under candidates[0].grounding_metadata,
    but field names drift across versions (grounding_chunks vs grounding_supports).
    We try multiple shapes; on failure, return [] so the caller can fall back to
    regex-scraping URLs from response.text.
    """
    sources = []
    try:
        candidates = getattr(response, 'candidates', None) or []
        if not candidates:
            return []
        gm = getattr(candidates[0], 'grounding_metadata', None)
        if not gm:
            return []

        # Primary SDK shape: grounding_chunks[].web.{uri,title}
        chunks = getattr(gm, 'grounding_chunks', None) or []
        for chunk in chunks:
            web = getattr(chunk, 'web', None)
            if not web:
                continue
            url = getattr(web, 'uri', None) or getattr(web, 'url', None)
            title = getattr(web, 'title', None) or ''
            if url:
                sources.append({'url': url, 'title': title, 'snippet': ''})

        # Enrich with grounding_supports if available (maps chunks → text segments).
        if sources:
            supports = getattr(gm, 'grounding_supports', None) or []
            for s in supports:
                seg = getattr(s, 'segment', None)
                indices = getattr(s, 'grounding_chunk_indices', None) or []
                seg_text = getattr(seg, 'text', '') if seg else ''
                for idx in indices:
                    if 0 <= idx < len(sources) and seg_text and not sources[idx].get('snippet'):
                        sources[idx]['snippet'] = seg_text[:400]
    except Exception as e:
        print(f"[Research-Structured] Grounding extract failed: {e}")

    # De-dupe by URL
    seen = set()
    unique = []
    for s in sources:
        key = s.get('url')
        if key and key not in seen:
            seen.add(key)
            unique.append(s)
    return unique


def _scrape_urls_from_text(text: str) -> list:
    """Last-resort fallback: regex-extract URLs from text."""
    if not text:
        return []
    urls = _re.findall(r'https?://[^\s\)\]\}<>"\']+', text)
    seen = set()
    out = []
    for u in urls:
        u = u.rstrip('.,;:')
        if u and u not in seen:
            seen.add(u)
            out.append({'url': u, 'title': '', 'snippet': ''})
    return out


def _empty_structured(topic: str, template_id: str, mode: str, model: str) -> dict:
    """Return the canonical empty schema."""
    return {
        'meta': {
            'topic': topic,
            'template_id': template_id,
            'mode': mode,
            'model': model,
            'generated_at': _datetime.utcnow().isoformat() + 'Z',
        },
        'sections': [],
        'claims': [],
        'sources': [],
    }


def _markdown_from_structured(structured: dict) -> str:
    """Render the structured schema back into the legacy dossier markdown shape.

    Mirrors build_research_dossier()'s `# Research Dossier / ## Template / ### heading`
    layout so the UI renders unchanged.
    """
    if not structured or not isinstance(structured, dict):
        return ""

    meta = structured.get('meta', {}) or {}
    topic = meta.get('topic', '')
    template_id = meta.get('template_id', '')
    mode = meta.get('mode', '')

    template = get_template(template_id)
    template_name = template['metadata']['name'] if template else (template_id or 'General')

    parts = [
        f"# Research Dossier: {topic}",
        f"## Template: {template_name}",
        f"## Research Mode: {mode}",
        "",
    ]

    claims_by_id = {c.get('id'): c for c in structured.get('claims', []) if c.get('id')}
    sources_by_id = {s.get('id'): s for s in structured.get('sources', []) if s.get('id')}

    for section in structured.get('sections', []) or []:
        title = section.get('title', 'Section')
        summary = section.get('summary', '')
        claim_ids = section.get('claim_ids', []) or []

        parts.append(f"### {title}")
        if summary:
            parts.append(summary)
            parts.append("")

        for cid in claim_ids:
            claim = claims_by_id.get(cid)
            if not claim:
                continue
            text = claim.get('text', '')
            src_ids = claim.get('source_ids', []) or []
            cites = " ".join(f"[{sid}]" for sid in src_ids if sid in sources_by_id)
            line = f"- {text}"
            if cites:
                line += f" {cites}"
            parts.append(line)

        parts.append("")

    if structured.get('sources'):
        parts.append("### Sources")
        for s in structured['sources']:
            sid = s.get('id', '')
            url = s.get('url', '')
            title = s.get('title') or url or '(untitled)'
            publisher = s.get('publisher', '')
            line = f"- [{sid}] {title}"
            if publisher:
                line += f" — {publisher}"
            if url:
                line += f" ({url})"
            parts.append(line)

    return "\n".join(parts)


_STRUCTURED_CLAIM_SCHEMA_PROMPT = """Respond ONLY with a valid JSON object (no markdown fences) matching this shape:
{
  "section": { "title": "<section heading>", "summary": "<1-3 sentence section summary>" },
  "claims": [
    { "text": "<a single factual claim>", "confidence": "high|med|low", "source_urls": ["<url1>", "<url2>"] }
  ]
}
Rules:
- Emit 8-20 distinct claims per sub-query.
- Every claim MUST cite at least one source_url drawn from the web search results. Never fabricate URLs.
- Use "high" confidence only for facts stated by official/primary sources; "med" for analysis/news; "low" for opinion."""


def _planner_expand_subqueries(topic: str, template_id: str, api_key: str,
                                uid: str = None, project_id: str = None) -> list:
    """Use Flash (no search) to expand template search_layers into concrete sub-queries."""
    template = get_template(template_id)
    if not template:
        return [{"name": "General", "query": f"Comprehensive research on {topic}"}]

    layers = template["research_config"].get("search_layers", [])
    analysis_qs = template["research_config"].get("analysis_questions", [])

    layer_text = "\n".join(
        f"- {l.get('name','?')}: {l.get('query_template','{topic}').format(topic=topic)}"
        for l in layers
    )
    qs_text = "\n".join(f"- {q}" for q in analysis_qs[:6])

    planner_prompt = f"""You are planning a research project. Expand the research layers below into
3-6 SPECIFIC, CONCRETE sub-queries. Each sub-query will be run against Google Search independently.

TOPIC: {topic}

RESEARCH LAYERS:
{layer_text}

ANALYSIS QUESTIONS WE NEED TO ANSWER:
{qs_text}

Return ONLY JSON:
{{
  "sub_queries": [
    {{"name": "<short section name>", "query": "<concrete Google search query>"}}
  ]
}}"""

    raw = generate_content(
        planner_prompt,
        model_name="gemini-3-flash-preview",
        temperature=0.3,
        api_key=api_key,
        max_output_tokens=4096,
        uid=uid, project_id=project_id, description="research_planner",
    )
    fallback = [
        {"name": l.get("name", f"Layer {i+1}"),
         "query": l.get("query_template", "{topic}").format(topic=topic)}
        for i, l in enumerate(layers[:5])
    ]
    if not raw or raw.startswith("Error:"):
        return fallback
    try:
        data = _parse_json_response(raw)
        subs = data.get("sub_queries", [])
        if isinstance(subs, list) and subs:
            # Keep only entries with both name + query
            cleaned = [s for s in subs if isinstance(s, dict) and s.get("query")]
            return cleaned or fallback
        return fallback
    except (json.JSONDecodeError, ValueError):
        return fallback


def _run_sub_researcher(sub_query: dict, topic: str, api_key: str, mode: str,
                         uid: str = None, project_id: str = None) -> dict:
    """Run one Pro+Search call for a sub-query. Returns {section, claims[], sources[]}."""
    name = sub_query.get("name", "Section")
    query = sub_query.get("query", topic)
    model_name = "gemini-3.1-pro-preview" if mode == "deep" else "gemini-3-flash-preview"

    prompt = f"""You are a research analyst. Use Google Search to answer the question below.
Return only factual claims with the source URLs that support them.

SECTION: {name}
QUESTION: {query}
TOPIC CONTEXT: {topic}

{_STRUCTURED_CLAIM_SCHEMA_PROMPT}

Return ONLY the JSON object."""

    try:
        response = generate_content(
            prompt,
            model_name=model_name,
            use_search=True,
            temperature=0.1,
            api_key=api_key,
            max_output_tokens=32768,
            return_response=True,
            uid=uid, project_id=project_id,
            description=f"sub_researcher({name})",
        )
    except Exception as e:
        print(f"[Research-Structured] Sub-researcher '{name}' failed: {e}")
        return {"section": {"title": name, "summary": ""}, "claims": [], "sources": []}

    text = getattr(response, 'text', None) or ""
    grounding_sources = _extract_grounding_sources(response)
    if not grounding_sources:
        grounding_sources = _scrape_urls_from_text(text)

    # Map URLs → provisional source dicts
    url_to_src = {}
    for gs in grounding_sources:
        url = gs.get("url")
        if not url:
            continue
        url_to_src[url] = {
            "url": url,
            "title": gs.get("title", ""),
            "publisher": "",
            "quote": gs.get("snippet", ""),
        }

    try:
        data = _parse_json_response(text)
    except (json.JSONDecodeError, ValueError):
        print(f"[Research-Structured] Sub-researcher '{name}' JSON parse failed")
        return {
            "section": {"title": name, "summary": (text[:400] if text else "")},
            "claims": [],
            "sources": list(url_to_src.values()),
        }

    section_obj = data.get("section") or {"title": name, "summary": ""}
    raw_claims = data.get("claims") if isinstance(data.get("claims"), list) else []

    # Merge any URLs the model cited that weren't in grounding metadata
    for claim in raw_claims:
        for url in (claim.get("source_urls") or []):
            if url and url not in url_to_src:
                url_to_src[url] = {"url": url, "title": "", "publisher": "", "quote": ""}

    return {
        "section": section_obj,
        "claims": raw_claims,
        "sources": list(url_to_src.values()),
    }


def _merge_subresearcher_outputs(topic: str, template_id: str, mode: str,
                                   model: str, sub_outputs: list) -> dict:
    """Merge parallel sub-researcher outputs into the canonical schema.

    Dedupes sources by URL, assigns stable c1..cN / s1..sN ids,
    and maps claim.source_urls → claim.source_ids.
    """
    url_to_sid = {}
    sources = []
    for sub in sub_outputs:
        for src in sub.get("sources", []) or []:
            url = src.get("url") or ""
            if not url or url in url_to_sid:
                continue
            sid = f"s{len(sources) + 1}"
            url_to_sid[url] = sid
            sources.append({
                "id": sid,
                "url": url,
                "title": src.get("title", ""),
                "publisher": src.get("publisher", ""),
                "quote": src.get("quote", ""),
                "accessed_at": _datetime.utcnow().isoformat() + "Z",
            })

    claims = []
    sections = []
    for idx, sub in enumerate(sub_outputs):
        section_obj = sub.get("section") or {}
        section_id = f"sec{idx + 1}"
        section_claim_ids = []

        for claim in sub.get("claims", []) or []:
            cid = f"c{len(claims) + 1}"
            urls = claim.get("source_urls") or []
            source_ids = [url_to_sid[u] for u in urls if u in url_to_sid]
            claims.append({
                "id": cid,
                "text": claim.get("text", ""),
                "confidence": claim.get("confidence", "med"),
                "source_ids": source_ids,
            })
            section_claim_ids.append(cid)

        sections.append({
            "id": section_id,
            "title": section_obj.get("title", f"Section {idx+1}"),
            "summary": section_obj.get("summary", ""),
            "claim_ids": section_claim_ids,
        })

    return {
        "meta": {
            "topic": topic,
            "template_id": template_id,
            "mode": mode,
            "model": model,
            "generated_at": _datetime.utcnow().isoformat() + "Z",
        },
        "sections": sections,
        "claims": claims,
        "sources": sources,
    }


def run_structured_research(topic: str, template_id: str,
                             api_key: str, mode: str = "deep",
                             uid: str = None, project_id: str = None) -> dict:
    """Orchestrate the 3-step structured research pipeline.

    1. Planner (Flash): expand template layers → 3-6 concrete sub-queries
    2. Sub-researchers (parallel Pro+Search calls with grounding metadata)
    3. Merger: dedupe sources, assign stable c1..cN / s1..sN ids

    Returns the canonical structured schema {meta, sections, claims, sources}.
    On any failure, returns an empty-but-valid schema so callers can always persist it.
    """
    try:
        print(f"[Research-Structured] Planning sub-queries for '{topic}'...")
        sub_queries = _planner_expand_subqueries(topic, template_id, api_key,
                                                  uid=uid, project_id=project_id)
        print(f"[Research-Structured] Planner produced {len(sub_queries)} sub-queries")

        sub_outputs = []
        if sub_queries:
            worker_count = min(4, len(sub_queries))
            with ThreadPoolExecutor(max_workers=worker_count) as executor:
                futures = {
                    executor.submit(_run_sub_researcher, sq, topic, api_key, mode,
                                    uid, project_id): sq
                    for sq in sub_queries
                }
                for fut in as_completed(futures):
                    try:
                        result = fut.result()
                        sub_outputs.append(result)
                        sec_name = result.get("section", {}).get("title", "?")
                        print(f"[Research-Structured] Sub-query '{sec_name}' → "
                              f"{len(result.get('claims', []))} claims, "
                              f"{len(result.get('sources', []))} sources")
                    except Exception as e:
                        sq = futures[fut]
                        print(f"[Research-Structured] Sub-query '{sq.get('name')}' failed: {e}")

        model_label = "gemini-3.1-pro-preview" if mode == "deep" else "gemini-3-flash-preview"
        structured = _merge_subresearcher_outputs(topic, template_id, mode, model_label, sub_outputs)
        print(f"[Research-Structured] Merged: {len(structured['sections'])} sections, "
              f"{len(structured['claims'])} claims, {len(structured['sources'])} sources")
        return structured
    except Exception as e:
        print(f"[Research-Structured] Pipeline failed: {e}")
        return _empty_structured(topic, template_id, mode,
                                  "gemini-3.1-pro-preview" if mode == "deep" else "gemini-3-flash-preview")


def structure_from_blob(text: str, topic: str, template_id: str,
                         mode: str, model: str, api_key: str,
                         uid: str = None, project_id: str = None) -> dict:
    """Best-effort: convert an unstructured research text blob into the canonical schema.

    Used for the deep_research_agent path where we receive a single text output and
    cannot access grounding metadata. Asks Flash to extract claims/sources from the text.
    Returns _empty_structured on any failure so the field is always present.
    """
    if not text or not text.strip():
        return _empty_structured(topic, template_id, mode, model)

    text_excerpt = text[:60000]
    extractor_prompt = f"""You are extracting claims and sources from a research report.

REPORT:
\"\"\"
{text_excerpt}
\"\"\"

TOPIC: {topic}

Break the report into 3-6 thematic sections. For each section, extract:
- 5-15 factual claims (short sentences)
- The source URLs that support each claim — copy any http/https URLs that appear in the report.
  If the report mentions a publication by name without a URL, include that in source_titles instead.

Return ONLY JSON:
{{
  "sections": [
    {{
      "title": "<section heading>",
      "summary": "<1-2 sentence section summary>",
      "claims": [
        {{
          "text": "<factual claim>",
          "confidence": "high|med|low",
          "source_urls": ["<url>", "..."],
          "source_titles": ["<publication/title for URL-less sources>"]
        }}
      ]
    }}
  ]
}}"""

    raw = generate_content(
        extractor_prompt,
        model_name="gemini-3-flash-preview",
        temperature=0.1,
        api_key=api_key,
        max_output_tokens=16384,
        uid=uid, project_id=project_id, description="structure_from_blob",
    )
    if not raw or raw.startswith("Error:"):
        return _empty_structured(topic, template_id, mode, model)

    try:
        parsed = _parse_json_response(raw)
    except (json.JSONDecodeError, ValueError):
        return _empty_structured(topic, template_id, mode, model)

    sub_outputs = []
    for sec in parsed.get("sections", []) or []:
        claims_out = []
        sources_out = []
        seen_keys = set()
        for c in sec.get("claims", []) or []:
            urls = c.get("source_urls") or []
            titles = c.get("source_titles") or []
            for u in urls:
                if u and u not in seen_keys:
                    seen_keys.add(u)
                    sources_out.append({"url": u, "title": "", "publisher": "", "quote": ""})
            for t in titles:
                key = f"title:{t}"
                if t and key not in seen_keys:
                    seen_keys.add(key)
                    sources_out.append({"url": "", "title": t, "publisher": "", "quote": ""})
            claims_out.append({
                "text": c.get("text", ""),
                "confidence": c.get("confidence", "med"),
                "source_urls": urls,
            })
        sub_outputs.append({
            "section": {"title": sec.get("title", "Section"), "summary": sec.get("summary", "")},
            "claims": claims_out,
            "sources": sources_out,
        })

    return _merge_subresearcher_outputs(topic, template_id, mode, model, sub_outputs)


if __name__ == "__main__":
    # Quick test: list templates
    templates = get_all_templates_metadata()
    for t in templates:
        print(f"  {t['icon']} {t['name']} — {t['description'][:60]}...")


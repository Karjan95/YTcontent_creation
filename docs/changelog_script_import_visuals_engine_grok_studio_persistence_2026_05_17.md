# Changelog — Script Import, Visuals Engine, Grok I2V, Studio Persistence

**Date:** 2026-05-17
**Branch:** main
**Staging revision:** `content-creation-app-staging-00160-76w`
**Service URL:** https://content-creation-app-staging-qj4rflrraa-uc.a.run.app

## Why

Five user-reported bugs/asks bundled into one pass:

1. **Pasted scripts silently lost content.** A 17-paragraph fly-biology script came back as a production table starting at paragraph 5 ("Stay until the end…") because the structuring LLM dropped the entire 4-paragraph opening.
2. **JSON-format UX clutter.** Phase 2's "Paste Your Own Script" hinted at JSON, and Phase 3 still had a manual "Paste Your Own Narration JSON" path — users should never have to think about JSON.
3. **Visuals tab was locked to Google models** even though Studio supports ~100 Kie models. Users wanted per-scene model choice.
4. **Grok Imagine I2V wasn't taking the scene image as input** — schema bugs plus a frontend payload omission.
5. **Studio gallery items disappeared after ~24h.** Kie generations were storing ephemeral `tempfile.redpandaai.co/*` URLs that 404 the next day, instead of the persistent Firebase Storage URLs the server was already rehosting to.

## Changes

### 1. Loss-proof script import (Phase 2)

**Core shift:** the LLM no longer re-emits the user's text. Backend deterministically splits the paste; LLM only returns short act/beat labels keyed by chunk index; backend zips labels ↔ verbatim chunks back together; an equality assertion guarantees zero content loss.

- `execution/research_scriptwriter.py` — new `split_script_into_chunks(raw_text, max_words_per_chunk=45)` helper. Paragraph-first split (`\n\s*\n`), single-newline fallback, sentence regex fallback; greedy-packs sentences up to the word cap; strips ` ` (NBSP) and zero-width characters; promotes Markdown headers to their own chunk.
- `execution/research_templates.py` — `build_script_structuring_prompt(chunks, duration_minutes)` rewritten as labeler-only. Renders chunks as `[i] <first ~200 chars>…`; output schema is `{title, labels:[{index, act, beat}]}`; no `text` field anywhere.
- `execution/server.py` — `structure_script_route` rewritten. Calls `split_script_into_chunks`, asks `gemini-3.1-flash-lite` (temp 0.2) for labels, **reconstructs** narration from the chunk list (text never comes from the LLM), merges consecutive same-`(act, beat)` entries with `\n\n`, runs an equality assertion (`re.sub(r'\s+', ' ', s).strip()` normalize, case-sensitive, punctuation preserved). On any failure (LLM error / malformed JSON / equality mismatch) → deterministic fallback labels (`ACT 1 / Beat {i+1}`), `structuring_mode: "fallback"`. On partial failure, fills only missing indices with defaults, mode stays `"llm"`.

**Model change:** `gemini-3-flash-preview` → `gemini-3.1-flash-lite` at the script-structuring call site only. `gemini-3-pro-preview` was deprecated 2026-03-09; flash-lite is the right tier for short-snippet labeling.

### 2. JSON-free UX

- **Phase 2** (`ui/index.html:1234–1247`) — removed "Or paste structured JSON…" hint. Placeholder shortened to "Paste your narration here…". One-line caption explains the auto-structuring.
- **Phase 2** (`ui/index.html` `importScript`) — deleted both JSON-detection branches; always POSTs raw text. If response includes `structuring_mode: "fallback"`, shows a non-blocking toast: "Imported with auto-labels — feel free to rename acts and beats."
- **Phase 3** — removed the "Paste Your Own Narration JSON" toggle button, its panel, and `importSceneBreakdown()` entirely. Phase 3 reads from Phase 2's `currentNarration` only.

### 3. Visuals → Studio engine bridge

Users can now pick any Studio-registered Kie/Google model as the **Visuals engine** for image or video generation, either globally (panel above scene grid) or per-scene (override row on each scene card).

- `ui/index.html` — added Visuals Engine panel below Characters section.
- `visualsEngine` state holds `{image:{modelId, inputs, params, refs}, video:{...}}` and is saved/restored under the project's `visuals_engine` field.
- `visualsConfigureEngine(kind, sceneIdx)` opens the Studio model picker with `studioState._pickerForVisuals = true`.
- `visualsSaveCurrentStudioAsEngine()` snapshots the composer.
- `_visualsBuildStudioPayload(idx, kind)` merges engine snapshot with scene-specific prompt and image:
  - For **image** kind, scene's character/style refs are appended to the engine's `reference_images`.
  - For **video** kind, scene's existing image is plumbed to the engine's `first_frame` slot (scalar) or unshifted to the front of an `image_urls` list slot (Grok I2V style) with cap-trimming.
  - Safety scrub drops any `data:` URI inputs with a console warning (Kie's upload endpoint rejects base64).
- `generateSceneViaStudio(idx, kind)` POSTs to `/api/studio/generate` and routes the response through `_visualsPollStudioKie` or the appropriate path.
- `generateSceneImage` and `animateScene` now delegate to the studio path when an override or global engine is set.
- Studio's model picker filters out exotic-input models in Visuals context via `VISUALS_ENGINE_EXCLUDE = new Set(['sora-2-pro-storyboard', 'elevenlabs/text-to-dialogue-v3'])` — those need multi-shot JSON inputs that don't fit a single scene.

### 4. Grok Imagine I2V

Two bugs, both fixed.

- `execution/model_schemas.py:2088` — corrected against docs.kie.ai:
  - `image_urls` was `max_n=7`; docs say exactly one image → `max_n=1`.
  - `duration` was a string-enum `["6","10","15","20","30"]`; docs say number range 6–30 → `_int("duration", 6, 30, default=6)`.
  - Defaults aligned: `aspect_ratio="2:3"`, `resolution="480p"`, `nsfw_checker=True`. Help text on `mode` calls out the "Spicy forced to Normal with external image_urls" caveat.
- `ui/index.html` `_visualsBuildStudioPayload` — for `kind === 'video'`, only handled scalar image slots (`first_frame` / `image`). Grok I2V uses an `image_urls` **list** slot, so the scene image was silently dropped. Added a list-slot fallback that unshifts the scene image to position 0 (so the prompt's `@image1` reference resolves correctly) and trims to the schema cap.

> ⚠️ **Re-save the Grok engine in Studio** if you saved it before this deploy — old snapshots have `duration: "6"` (string) and the new schema expects an int.

### 5. Studio gallery persistence (the "lost after a few days" bug)

**Root cause:** Studio's Kie pollers stored `data.result_urls[]` — those are Kie's `tempfile.redpandaai.co/*` CDN URLs that 404 after ~24h. The server's `/api/kie/poll` already downloads each result and re-uploads to Firebase Storage, returning the persistent URLs in `data.firebase_urls`, but the frontend was ignoring that field. The Visuals tab's regular Kie path (lines 10844, 11214) correctly does `data.firebase_urls || data.result_urls` — Studio just hadn't been updated.

- `ui/index.html` `studioPollKieTask` — now prefers `data.firebase_urls`, falls back to `result_urls` only when rehost failed.
- `ui/index.html` `_visualsPollStudioKie` — same fix for the Visuals-via-Studio bridge poller.

Combined with the existing 7-day signed-URL auto-refresh in `_serialize_asset` (server.py:2465–2497), Studio gallery items now survive:
- page refresh
- project switch and re-load
- arbitrary aging (asset listing re-signs expired URLs in place and updates the Firestore doc)

**Won't self-heal retroactively:** Kie generations done before this deploy hold dead `tempfile.redpandaai.co` URLs in their Firestore asset docs. They'll show as broken tiles until deleted/regenerated.

## Files Changed

| File | Why |
|------|-----|
| `execution/research_scriptwriter.py` | New `split_script_into_chunks` helper |
| `execution/research_templates.py` | Labeler-only `build_script_structuring_prompt` |
| `execution/server.py` | `structure_script_route` rewrite, `gemini-3.1-flash-lite` |
| `execution/model_schemas.py` | Grok Imagine I2V schema corrected against docs |
| `ui/index.html` | Phase 2/3 UX cleanup, Visuals engine bridge, Grok payload list-slot fallback, Studio poller `firebase_urls` preference |

## Verification

**Script import:**
1. Phase 2 → Paste Your Own Script → paste the 17-paragraph fly script.
2. Click Import & Breakdown Script. Expect `Imported (N acts, M beats)` where M ≥ 17, response `structuring_mode: "llm"`.
3. Beat 1's text MUST begin with "You've seen flies your entire life…" (not "Stay until the end,").
4. Devtools console:
   ```js
   const joined = currentNarration.narration.map(b => b.text).join(' ').replace(/\s+/g,' ').trim();
   const paste = document.getElementById('scriptPasteArea').value.replace(/\s+/g,' ').trim();
   console.log('match:', joined === paste);  // → true
   ```
5. Phase 3 has no "Paste Your Own Narration JSON" button in the DOM.

**Visuals engine:**
1. Open Studio → pick any Kie image model → Save as Visuals Engine.
2. Generate a production table on any project. On a scene card, hit Generate Image — it should route through `/api/studio/generate` (check Network tab) instead of the legacy Google image path.
3. Override one scene to a different model via the per-scene override row.

**Grok I2V:**
1. Studio → Grok Imagine I2V → verify image slot accepts only 1 image, duration is a number input 6–30, defaults `2:3` / `480p`.
2. Save as Visuals Engine, then on a scene with an image click Animate. Check `/api/studio/generate` request body: `inputs.image_urls = [<Firebase URL>]`, `params.duration = 6` (integer, not "6").

**Studio persistence:**
1. Generate a Kie image in Studio. After it lands in the gallery, right-click → Copy image address. URL must be `firebasestorage.googleapis.com/...`, not `tempfile.redpandaai.co/...`.
2. Refresh — gallery re-populates from Firestore with the same URLs.
3. Switch project away and back — same URLs.

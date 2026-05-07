# Studio rebuild — task #6, #7, and 7-issue fix-up

**Date:** 2026-05-07
**Scope:** Finishing strokes on the unified Studio tab — Firestore-backed asset
library, Visuals→Studio bridge, plus seven user-flagged regressions.

---

## Task #6 — Firestore-backed asset library

Studio assets used to live in `studioState.assets` only — closing the tab dropped
the gallery. Now per-project subcollection `users/{uid}/projects/{pid}/assets`.

**Backend** (`execution/server.py`)
- New routes: `GET / POST /api/projects/<pid>/assets`,
  `PATCH / DELETE /api/projects/<pid>/assets/<aid>`.
- Asset doc fields: `kind`, `url`, `prompt`, `model_id`, `provider`, `refs`,
  `params`, `favorite`, `ts`, `created_by`. PATCH whitelist: `favorite`, `prompt`.
- `delete_project` now cascade-deletes the assets subcollection before clearing
  Storage files (Firestore doesn't auto-cascade).

**Frontend** (`ui/index.html`)
- `studioOnProjectChange` is async, fetches the project's gallery from Firestore
  on switch, and guards against late responses landing in the wrong project.
- `studioAddAsset` is optimistic — inserts a `__pending_<id>` tile, POSTs in the
  background, then swaps in the server-issued doc.
- `studioToggleFav` (gallery + lightbox) PATCHes server-side.
- "From library" attach option opens a real picker modal
  (`#studioLibraryOverlay`) showing `studioState.assets` filtered by kind, with
  prompt search; clicking a tile pushes it onto `studioState.refs`.
- Dropped the `assetsByProject` in-memory cache — server is the source of truth.

---

## Task #7 — Visuals → Studio bridge

Per-scene model dropdowns can only pick from a handful of models. Now any scene
card can hand off to the full Studio composer (144 models) for one-shot
iteration, with the result written back to that scene.

- New buttons on each scene card (`✨ Studio`) for both Image and Animation
  sections.
- `studioOpenForScene(idx, field)` — prefills mode, default model, prompt, and
  the scene's current image as a ref (used as `first_frame` when targeting Veo,
  iterate-from for image), then `switchTab('studio')`.
- Pinned banner at the top of `tab-studio` showing scene context with
  "Back to Visuals" and "Stop targeting" controls.
- `studioWriteBackToScene(asset)` — pushes previous `imageUrl` into
  `imageHistory`, sets the new url, calls `updateSceneCard` + `triggerAutosave`.
  Hooked into `studioAddAsset` so it fires on both sync (Google) and async (Kie
  poll) success paths uniformly.
- `studioOnProjectChange` clears the target on project switch (a scene index is
  meaningless across projects).

---

## 7-issue fix-up

### Issue 1 + 2 — model picker rows / param chips unreadable

**Root cause:** `ui/style.css:462` global `button:not(...)` rule (specificity 0,5,1)
overrode `.studio-model-row` and `.studio-chip` (specificity 0,1,0), painting
every Studio button solid lime.

**Fix:** added every Studio button class to the `:not()` exclusion list. Bolstered
`.studio-chip.is-active` with `font-weight:600` + outer ring, and
`.studio-model-row.is-selected .studio-model-row-name` turns lime so the active
row is unmistakable.

### Issue 3 — `num_images = 2` returned 1 image

Schema declared the param but the backend ignored it.

- `gemini_client._generate_with_imagen_model` now uses `number_of_images=count`
  (Imagen native batch).
- `gemini_client._generate_with_gemini_model` loops sequentially N times
  (Gemini-native image API has no batch knob in this preview).
- `generate_image_content` accepts `count` + `return_list`. Legacy callers still
  get a single string back (back-compat).
- `_studio_dispatch_google_image` clamps `num_images` / `max_images` against the
  schema's `min`/`max` and returns `image_urls[]` (plus `image_url` for back-compat).
- Frontend success branch loops over `data.image_urls` calling `studioAddAsset`
  for each.

### Issue 4 — multi-file ref upload

- `multiple` attribute on the three hidden file inputs.
- `studioHandleFileUpload` loops over `event.target.files`.
- `studioRefSlotCapacity(kind)` reads the active model's `image_list.max_n` and
  refuses to push past capacity with a friendly error ("max N for this model").

### Issue 5 — Studio tab placement

- Studio button moved to the end of the nav with `data-requires-project="true"`
  and inline `display:none`.
- Voiceover is now the default-active tab/main.
- `studioUpdateNavVisibility()` toggles the button on `studioOnProjectChange`;
  falls back to Voiceover if Studio is the active tab when a project unloads.

### Issue 6 — `@imgN` reference tagging

- `studioRefTag(idx)` returns `@img1`, `@vid1`, `@aud1` (kind-scoped numbering).
  Chips display the tag as label; original slot name is the tooltip.
- New autocomplete dropdown above the prompt textarea
  (`#studioPromptSuggest`). Detects `@\w*` at caret, supports ↑↓/Enter/Tab/Esc.
- `studioTokenizePrompt(prompt)` parses `@imgN` / `@vidN` / `@audN` into
  `[{type:'text'|'ref'}]` tokens.
- For `google_gemini_image` backends, tokens are sent as `inputs.prompt_parts`;
  for everyone else the `@`-tokens are stripped from the prompt (refs still
  attach via schema slots).
- Backend: `_ref_to_part` factored out of the existing ref handling;
  `_generate_with_gemini_model` accepts `prompt_parts` and interleaves Image
  Parts at the user-chosen positions. So "make `@img1` look like `@img2`" puts
  img1 between the two text fragments in the multipart payload.

### Issue 7 — capability-aware attach + variant suggest

- `studioModelAcceptsKind(kind)` schema check; attach menu items get
  `is-disabled` (strikethrough + tooltip) when the model doesn't accept the kind.
- `studioFindEditVariant(kind)` finds a sibling model in the same provider /
  display-name family that accepts the kind.
- `studioRenderRefs` shows a yellow "X doesn't accept image refs — Switch to Y?"
  banner when there's a mismatch; one-click `studioSwitchToVariant(modelId)`
  swaps the model and preserves refs (the new variant accepts them).

---

## Files touched

| Path | Why |
|------|-----|
| `execution/server.py` | Asset CRUD routes, cascade delete, `_studio_dispatch_google_image` accepts `num_images` + `prompt_parts` |
| `execution/gemini_client.py` | `_ref_to_part` extracted; `_generate_with_imagen_model` and `_generate_with_gemini_model` accept `count`; `generate_image_content` returns lists when asked |
| `ui/index.html` | Asset library wiring, Visuals→Studio bridge, attach menu gating, `@`-mention autocomplete + tokenizer, multi-file upload, nav reorder |
| `ui/style.css` | Global button `:not()` exclusion, `.studio-prompt-suggest*`, `.studio-ref-warning`, `.studio-variant-switch-btn`, `.studio-library-*`, `.studio-scene-banner*`, `.scene-studio-btn` |

## Verification

- `python3 -c "import ast; ast.parse(open('execution/server.py').read()); ast.parse(open('execution/gemini_client.py').read())"` — clean.
- `node --check` on the extracted Studio JS (`/tmp/studio.js`) — clean.

## Known issues flagged for next pass

User reported on review:
- Studio's `position: fixed` composer leaks visually onto other tabs (Research /
  Script / Production / Visuals) — should only render when the Studio tab is
  active.
- Top-level nav structure: user wants Voiceover, Studio (and the project view of
  Usage) to be **per-project tabs inside the project**, not sidebar items;
  sidebar should keep only Projects + a global Usage link aggregating across all
  projects/models.
- Confirm @-mention positional interleaving against a real Gemini-native call
  (`[Gemini] interleaved N parts` log line — smoke-test only so far).

---

## Follow-up — navigation restructure, isolation hardening, schema correctness (2026-05-07, evening)

A second pass on the same day that addressed the open review items above and a
batch of regressions surfaced during user testing. The work falls into four
groups: navigation, tab isolation, schema field-name correctness, and input
guard-rails.

### Navigation restructure

Voiceover and Studio were sidebar Tools — the user wanted them as
project-scoped pipeline phases instead, with the sidebar reserved for
account-wide destinations.

- `ui/index.html:309–326` — pipeline stepper grew two segments after Visuals:
  **Voiceover** and **Studio**. The numbered phases (1–4) keep their step
  badges; Voiceover and Studio render with a vertical divider in front of them
  and use lucide icons (`mic`, `wand-2`) instead of step numbers, signalling
  that they are auxiliary tools rather than sequential workflow steps.
- `goToPhase` (`ui/index.html:2474–2492`) routes the new phases to
  `switchTab('voiceover')` / `switchTab('studio')` and forwards a unified
  `tabKey` to `syncShellNav`.
- `syncShellNav` (`ui/index.html:2503–2549`) now treats the four pipeline tabs
  uniformly via a `PIPELINE_TABS` set, and gates stepper visibility on
  `(isPipelineTab && projectLoaded)` — the stepper hides whenever no project
  is loaded.
- Sidebar Tools section (`ui/index.html:259–264`) was renamed to **Account**
  and now contains only the global Usage link.
- Default-active main was moved from `tab-voiceover` to `tab-usage`. Voiceover
  is project-scoped now, so an unauthenticated visitor would otherwise have
  landed on a useless empty pane.
- `studioUpdateNavVisibility` (`ui/index.html`) bounces the user from any
  project-scoped tab back to Usage when a project unloads, then re-runs
  `syncShellNav` so the stepper visibility refreshes.
- Stepper `max-width` bumped 720 → 920 px (`ui/style.css`) to fit six segments
  cleanly; `.step.step-extra` shrinks-to-fit so the numbered phases stay
  even-width.

### Tab isolation hardening

The Studio gallery + composer were painting on top of the Research view —
multiple `.tab-content` blocks effectively visible at once.

- `.tab-content { display: none }` was being out-specificity'd by a downstream
  `body.shell-mode .tab-content { padding/max-width/etc }` rule. Added a
  hardened guard at `ui/style.css`:

  ```css
  .tab-content:not(.active) { display: none !important; }
  ```

  Belt-and-braces; nothing in the cascade can resurrect a hidden tab.
- Defensive rule on the floating composer:

  ```css
  #tab-studio:not(.active) .studio-composer,
  #tab-studio:not(.active) .studio-attach-menu { display: none !important; }
  ```

  Guarantees the `position: fixed` composer + popovers can never paint over a
  non-Studio tab regardless of future structural changes.

### Schema field-name correctness (Kie API)

The user reported "Seedance 2 isn't taking my reference image" and a separate
"`reference_image or reference_video is required`" error from Wan 2.7 R2V.
Cross-referencing against the canonical Kie OpenAPI specs revealed that
**multiple model schemas had field names that don't match what Kie expects**,
so refs and audio were uploaded but the API silently dropped them and fell
back to text-to-video.

| Model | Old (wrong) | New (matches API) |
|---|---|---|
| **Seedance 2 / 2 Fast / 1.5 Pro** | `first_frame` | `first_frame_url` |
|  | `last_frame` | `last_frame_url` |
|  | `ref_image_urls` | `reference_image_urls` |
|  | `ref_video_urls` | `reference_video_urls` |
|  | `ref_audio_urls` | `reference_audio_urls` |
| **Wan 2.7 I2V** | `image_url` | `first_frame_url` |
|  | `audio_url` | `driving_audio_url` |
|  | (missing) | `last_frame_url`, `first_clip_url` |
| **Wan 2.7 R2V** | `ref_image_urls` | `reference_image` |
|  | `audio_url` | `reference_voice` |
|  | (missing) | `negative_prompt`, `first_frame` |
| **Wan 2.7 Video Edit (V2V)** | `source_video_url` | `video_url` |
|  | (missing) | `negative_prompt`, `reference_image` |
| **HappyHorse R2V** | `ref_image_urls` | `reference_image` |
| **HappyHorse I2V** | `image_url` (single) | `image_urls` (list) |

Each rename is footnoted with the docs URL it was confirmed against. Schema
fields that the Kie generic dispatcher passes through verbatim now match the
JSON keys the API expects, so attached references land in the correct slot
instead of being discarded.

### Wan 2.7 per-variant params

A single `_wan_27_params` blob was shared across all four Wan 2.7 variants —
that produced "ratio is not supported for image-to-video" errors because the
Kie API requires a different param shape per variant.

- **T2V** uses `ratio` (not `aspect_ratio`).
- **I2V** has no aspect/ratio at all (derived from input image).
- **R2V / V2V** use `aspect_ratio`.

Replaced the shared blob with three named sets — `_wan_27_t2v_params`,
`_wan_27_i2v_params`, `_wan_27_r2v_params` (the last is reused by V2V) — and
wired each model to the correct one. The user's I2V request will no longer
ship a `ratio` field.

### Smart ref distribution

`studioGenerate`'s old loop used `Array.find()` to match each ref to a slot —
which always returned the first matching slot. For Seedance 2 (which has
`first_frame_url`, `last_frame_url`, AND `reference_image_urls`), every image
collided on `first_frame_url` and only the first survived; images 2-N were
silently dropped. Replaced with a three-phase distributor:

1. Refs whose `slot` name matches a schema slot name go to that slot
   (preserves Visuals→Studio bridge intent).
2. Generic refs prefer the **list slot** when one exists for the kind, so
   multi-image models get all their inputs (Seedance multimodal mode, Flux
   Edit `image_input`, etc.). Avoids mode-mixing on Seedance where scalar +
   list slots represent mutually-exclusive modes.
3. Scalar fallback for models with no list slot.
4. Anything that overflows surfaces a visible error so the user knows.

Also promoted Seedance's `reference_video_urls` and `reference_audio_urls`
from `T_VIDEO` / `T_AUDIO` (single) to `T_VIDEO_N` / `T_AUDIO_N` (list,
max 3) — the API accepts arrays of up to 3, but the schema declared singles
so multi-uploads were silently truncated.

### Input guard-rails

The user typed `50` into Seedance's duration field; the API capped at 15 and
rejected the request, burning credits. Two layers of defense:

1. **Schema** — Seedance 2 / 2 Fast / 1.5 Pro and Wan 2.7 family now declare
   `duration` as an `_enum` with all valid integer values rather than a free-
   form `_int`. The form renders a `<select>` dropdown so the user can only
   pick a legal value.
2. **`studioSetParam`** (`ui/index.html`) coerces and clamps before storing:
   - For `<select>` enum values, looks up the original typed option (so int
     duration is stored as `5`, not `"5"` — the API expects an int).
   - For `int` / `float` / `slider` params still rendered as free-form
     `<input>`, clamps to schema `min`/`max`. A pasted `50` is silently
     squashed to `15` before it reaches the server.

### Param chip click bug

Inline `onclick="studioSetParam('image_size', \"1k\")"` was tripping
`Unexpected end of input` because the embedded `"1k"` closed the attribute
prematurely. Replaced inline `onclick` for enum chips with a delegated
listener:

- Chips now render `data-studio-param` + `data-studio-opt-idx` data attrs.
- A single click handler on `#studioParams` (installed once, guarded by
  `_chipDelegateAttached`) reads the data attrs and looks the typed option up
  in `studioState._enumOptions[paramName]`. No JS-in-HTML escaping needed,
  immune to quote characters in option values.

### Files touched (this follow-up pass)

| Path | Change |
|------|--------|
| `execution/model_schemas.py` | Field-name corrections (Seedance, Wan I2V/R2V/V2V, HappyHorse R2V/I2V); Wan 2.7 params split per variant; Seedance video/audio refs promoted to list; Seedance + Wan duration → enum |
| `execution/server.py` | (no further changes this pass — dispatcher is schema-driven) |
| `ui/index.html` | Sidebar / stepper restructure; `studioUpdateNavVisibility` redirects to Usage; smart ref distributor; `studioSetParam` coercion + clamping; chip rendering moved to data-attrs + delegated handler |
| `ui/style.css` | Hardened `.tab-content:not(.active) { display:none !important }`; defensive `#tab-studio:not(.active) .studio-composer { display:none !important }`; `.pipeline-stepper-divider`, `.step.step-extra` styles |

### Verification

- `python3 -c "import ast; ast.parse(open('execution/server.py').read()); ast.parse(open('execution/gemini_client.py').read()); import sys; sys.path.insert(0,'execution'); import model_schemas"` — clean.
- `node --check` on the extracted Studio JS — clean.
- Manual cycle:
  - Select Seedance 2 → duration is a `<select>` listing 4–15; aspect_ratio
    chips render with the active state visible; attach 5 reference images
    → all five appear in the request body's `reference_image_urls` array.
  - Select Wan 2.7 I2V → no `ratio` / `aspect_ratio` control surfaces; attach
    one image → request body contains `first_frame_url`.
  - Select Wan 2.7 R2V → attach one image → `reference_image: ["url"]`.
  - On any non-Studio tab the gallery + composer are not rendered (verified
    via DevTools inspector: `#tab-studio` is `display:none`).

# Studio Rebuild — Resume Guide

> Handoff doc. Read this first if you're picking up the unified Studio
> (image+video+audio composer) work after a `/clear` or new session.
>
> **Started**: 2026-05-05.  **Last update**: 2026-05-07.

---

## TL;DR

We replaced the separate `tab-image` and `tab-kie` UIs with a single
**Studio** tab — Higgsfield-style: floating composer at the bottom, asset
gallery on top, model picker grouped by provider, dynamic per-model
parameter form rendered from a schema registry. **129 models across 20
providers** are registered. Schema-driven generation is live for
~130 Kie models (generic dispatcher), all Google Gemini-native image
models with reference support, Imagen, Google Veo (I2V), and Google TTS.
Per-project Firestore-backed asset library and Visuals→Studio bridge are
shipped. Three Kie wrapper backends and Lyria are still 501-stubbed
(plus Veo T2V/refs and Google image aspect-ratio plumbing).

**Suno was dropped entirely on 2026-05-07 — do not re-add.** All entries,
the `B_KIE_SUNO` backend, the `T_PERSONA` param type, and the
Suno-only kinds (`KIND_MUSIC_EXTEND`, `KIND_MUSIC_TO_VIDEO`,
`KIND_VOICE_PERSONA`) were removed from `model_schemas.py` and the
matching dispatcher was removed from `server.py`. `KIND_T2M` /
`KIND_LYRICS_TO_SONG` survived because Lyria uses them; `KIND_SOUND_EFFECT`
/ `KIND_AUDIO_ISOLATE` survived because ElevenLabs uses them.

---

## File map

| Path | What it is |
|------|------------|
| `execution/model_schemas.py` | **Source of truth.** 129 model entries with provider, kind, inputs (text/image/video/audio slots), params (typed: enum/int/float/slider/bool/seed/line/text/task_ref/character_ref), output, cost notes. Helpers: `_register`, `get_provider_groups`, `get_schema`, `list_kinds`. |
| `execution/server.py` | `/api/studio/models` (GET, returns registry+providers) and `/api/studio/generate` (POST, single dispatcher). Dispatch helpers: `_studio_dispatch_kie_generic`, `_studio_dispatch_google_image`, `_studio_dispatch_google_veo`, `_studio_dispatch_google_tts`, plus 501 stubs for `kie_veo3`/`kie_runway` and `google_lyria`. Per-project asset CRUD at `/api/projects/<pid>/assets[/<aid>]`. |
| `execution/gemini_client.py` | `_generate_with_gemini_model` accepts `reference_images=` (list of data URIs / URLs / bytes); `generate_image_content` plumbs that through. Imagen path explicitly rejects refs with a friendly error. |
| `execution/kie_client.py` | `_build_task_payload` falls back to `_build_generic_passthrough_payload` for any model not in the legacy `KIE_MODELS` dict — that's how the ~130 newly-registered models route through `/api/v1/jobs/createTask` without hand-mapping each one. |
| `ui/index.html` | Single "Studio" sidebar entry. `<main id="tab-studio">` with composer + gallery. Trailing script block (~870 lines): `studioState`, `studioEnsureLoaded`, `studioRenderModelPicker`, `studioRenderForm` (renders any schema dynamically), `studioGenerate`, `studioPollKieTask`, `studioOpenAsset` (lightbox), `studioOnProjectChange` (async, fetches assets), `studioAddAsset` (optimistic POST), `studioToggleFav` (PATCH), library picker overlay. |
| `ui/style.css` | `.studio-*` classes for gallery, composer, mode tabs, ref chips, dynamic params, model picker, attach menu popover, iteration lightbox, library overlay. |
| `docs/research_google_ai_media_models_2026_05_05.md` | Full Google AI media surface (Gemini Image / Imagen / Veo / TTS / Lyria) with every param. |
| `docs/research_kie_models_2026_05_05.md` | Full Kie.ai sitemap + 32 detailed model schemas + family-pattern notes. *(Includes Suno research, ignore that section — Suno is dropped.)* |
| `docs/changelog_studio_fixes_2026_05_07.md` | What shipped on 2026-05-07: Task #6, Task #7, plus a 7-issue fix-up. |

---

## Task status

| # | Task | Status | Notes |
|---|------|--------|-------|
| 1 | Persist Google research to disk | ✅ done | `docs/research_google_ai_media_models_2026_05_05.md` |
| 2 | Map Kie.ai docs surface area | ✅ done | sitemap → ~60 media model URLs |
| 3 | Catalogue every Kie.ai model + param | ✅ done | 32 detailed + family-pattern notes |
| 4 | Write MODEL_SCHEMAS registry | ✅ done | 129 models, 20 providers (post-Suno-drop) |
| 5 | Build Studio shell (replaces tab-image + tab-kie) | ✅ done | UX bug-fix pass landed 2026-05-06 |
| 6 | Firestore assets subcollection + library UI | ✅ done | Shipped 2026-05-07 |
| 7 | Wire Visuals scene tiles to open Studio composer | ✅ done | Shipped 2026-05-07 — variant (c), eliminates duplicate model-picker UI |
| 8 | Backend routes for new modalities | 🟡 partial | 4 of 6 slices shipped 2026-05-07 (Google image params, ref upload routes, Veo T2V/refs, Lyria). Kie Veo3 + Kie Runway wrappers blocked on live API exploration — see "Next step" below. |

---

## What works end-to-end (verified)

- Schema serializes; frontend renders the picker.
- `/api/studio/models` and `/api/studio/generate` registered; auth gate works.
- Generic Kie dispatcher accepts ~130 unmapped models via passthrough.
- Google Imagen generation (text-only).
- Google Nano Banana family generation **with reference images plumbed inline as `Part`s**.
- Google Veo I2V via `_studio_dispatch_google_veo`.
- Google TTS via `_studio_dispatch_google_tts`.
- Mode tabs (Image/Video/Audio) filter the model picker.
- Model picker grouped by provider, search, selection updates form.
- Dynamic param form: enum chips/select, int/float/slider, bool, seed, line, text, task_ref, character_ref.
- Reference attach: file upload (Firebase + base64 data URI kept for Gemini multipart); "From library" picker modal.
- Iteration lightbox: click any tile → big preview, prompt+model echoed, 5 actions (Iterate / Use as ref / Download / Favorite / Open external).
- **Per-project Firestore-backed asset gallery** — `users/{uid}/projects/{pid}/assets`. CRUD routes exist; `studioOnProjectChange` re-fetches on project switch; `studioAddAsset` optimistic POST; `studioToggleFav` PATCH. Cascade-delete on project DELETE.
- **Visuals→Studio bridge** — scene tiles open the Studio composer in a side panel and write results back to the scene via `studioWriteBackToScene`.
- Always-visible favorite heart on tiles.
- Boosted contrast in model picker.

---

## Known gaps & stubs (intentional — these are the Task #8 work)

### Backend dispatchers that intentionally 501

In `execution/server.py`:
- `_studio_dispatch_kie_veo` — Kie's Veo3 lives at `/veo3-api/*` with a different envelope than market models. Needs its own helper in `kie_client.py`.
- `_studio_dispatch_kie_runway` — same situation, `/runway-api/*` shape.
- `_studio_dispatch_google_lyria` — Lyria 3 not yet wrapped in `gemini_client.py`.

### Schema params rendered but ignored by underlying helpers

- `aspect_ratio`, `image_size`, `num_images` for Google image models — UI shows the chips but `generate_image_content()` doesn't yet accept them. Plumbing requires extending `_generate_with_gemini_model` and `_generate_with_imagen_model` to pass `aspect_ratio` / `image_size` / `number_of_images` into `GenerateContentConfig` / `GenerateImagesConfig`.
- Veo `last_frame`, `reference_images`, `negative_prompt`, `seed`, `enhance_prompt` — `start_video_generation()` is currently I2V-only. Needs T2V mode + frame interpolation + refs.

### Missing Storage upload routes

- Video/audio uploads in the composer create a local `URL.createObjectURL()` placeholder; not stored to Firebase. Needs `/api/upload-reference-video` and `/api/upload-reference-audio` routes (the image counterpart already exists).

### Pre-existing bugs (NOT introduced by Studio rebuild — separate fix)

- **🚨 Firestore 1 MB project-doc limit**: `PUT /api/projects/<id>` returns 500 with `Document size (1,098,831 bytes) exceeds the maximum allowed size of 1,048,576 bytes.` Suspect culprit: `styleReferenceImages` base64 stored inline on the project doc, plus the entire production table + visuals. Should be moved to subcollections or Storage. Affects autosave, not Studio specifically. **Worth its own session** — touching it without care could break loadProject/restoreProjectState.

### Frontend known limitations (not bugs)

- Studio composer overlaps gallery on small windows (composer is `position: fixed` at the bottom). The bottom padding is 240px; if user has tons of refs/params attached it could exceed.

---

## Next step — Task #8 (remaining backend work)

Goal: turn every 501-stubbed dispatcher into a working backend, plumb the
schema params that are rendered but currently ignored, and add Storage
upload routes for video/audio refs.

### Slices, in suggested order (smallest blast radius first)

1. ✅ **Google image param plumbing** — DONE 2026-05-07.
   `aspect_ratio` / `image_size` plumbed through
   `_generate_with_gemini_model` (via `GenerateContentConfig.image_config`)
   and `_generate_with_imagen_model` (via `GenerateImagesConfig`).
   `num_images` was already plumbed as `count`. Dispatcher reads from
   `params` and passes through.

2. ✅ **Reference video / audio upload routes** — DONE 2026-05-07.
   `/api/upload-reference-video` and `/api/upload-reference-audio` accept
   base64 data URIs, write to `references/{project_id}/{kind}/`, return
   signed URL + blob path. `studioUploadFile` now uploads video/audio to
   Firebase (with object-URL fallback on failure) instead of leaving an
   in-memory placeholder.

3. ✅ **Veo T2V + refs** — DONE 2026-05-07. `start_video_generation` now
   accepts `image_path=None` (T2V mode), `last_frame`, `reference_images`,
   `negative_prompt`, `seed`, `enhance_prompt`. New `_ref_to_image()`
   helper resolves URL / data URI / bytes / path to `types.Image` so the
   dispatcher can pass refs through unchanged. Existing scene callers
   (still passing `image_path=`) unaffected.

4. ⏸ **Kie Veo3 wrapper** — needs live API exploration. The
   `veo3-api/*` endpoints are documented in
   `docs/research_kie_models_2026_05_05.md` only at slug + param level
   (no concrete request/response JSON examples). Implementation
   requires either: (a) curl-testing the live API to discover the JSON
   shape, or (b) a known-good payload from Kie's docs. Don't ship
   speculatively — hitting the wrong shape on a paid API wastes credits
   and sends bad data to users.

5. ⏸ **Kie Runway wrapper** — same situation as #4 but for `/runway-api/*`.
   Should share `_kie_subapi_create_task` helper with #4 once the
   pattern is confirmed.

6. ✅ **Google Lyria** — DONE 2026-05-07. New `generate_music_content()`
   in `gemini_client.py` wraps Lyria 3 Clip / Pro via
   `client.models.generate_content` with `response_modalities=["AUDIO"]`
   and optional `mood_references`. Dispatcher uploads result to
   `audio/{project_id}/` and returns `audio_url` (frontend already
   handles that response shape).

### Open question before starting

**1 MB Firestore autosave bug** — pre-existing, blocking heavy projects.
Two reasonable orderings:
- Tackle it before Task #8 so users can actually save the projects they
  build with the new backends.
- Tackle Task #8 first since it's contained Studio scope and the autosave
  bug needs its own design pass (move `styleReferenceImages` to Storage,
  split production table off the project doc, etc.).

User leaning is **Task #8 first**; surface the autosave bug as the next
session after #8 lands. If Task #8 starts producing assets that bloat
projects further, escalate immediately.

### Cross-cutting design notes for Task #8

- All new dispatchers should write the result to the asset library via
  the existing `/api/projects/<pid>/assets` POST path. The frontend
  already does optimistic insertion; the dispatcher just needs to return
  enough metadata that `studioAddAsset` populates the doc correctly.
- Long-running ops (Kie task polling, Veo operation polling) should keep
  the existing pattern: dispatcher returns `task_id` / `operation_name`,
  frontend polls. Don't block the request thread.
- Errors: surface `{error: "..."}` with a precise message. The Studio
  frontend already shows these inline in the composer.

---

## How to resume

After `/clear` or new session, paste this:

> Read `docs/STUDIO_RESUME.md`. Tasks #1–#7 are done. **Pick up at task
> #8 — backend routes for new modalities.** Six slices listed under
> "Next step — Task #8" in suggested order. Suno was dropped on
> 2026-05-07 — do not re-add. Don't conflate with the 1 MB Firestore
> autosave bug (separate session).

---

## Session continuity hints

- Server runs on port 8091 (8080 was occupied on this dev machine):
  `PORT=8091 sh run_server.sh` or `PORT=8091 python3 execution/server.py &`
- Use `localhost:8091` not `127.0.0.1:8091` (Firebase OAuth domain whitelist).
- Background server check: `lsof -ti:8091` to find PID, `tail -f /tmp/studio_server.log` for output.
- Quick schema sanity check:
  ```bash
  python3 -c "import sys;sys.path.insert(0,'execution'); from model_schemas import MODEL_SCHEMAS as M, get_provider_groups as g; print(len(M), 'models'); [print(p['provider'],len(p['models'])) for p in g()]"
  ```
  Expected: `129 models`, 20 providers.
- JS syntax check the new Studio script:
  ```bash
  python3 <<'PY'
  with open('ui/index.html') as f: lines=f.readlines()
  o=[i for i,l in enumerate(lines) if l.strip().startswith('<script>')][-1]
  c=next(i for i,l in enumerate(lines) if i>o and '</script>' in l)
  open('/tmp/studio.js','w').write(''.join(lines[o+1:c]))
  PY
  node --check /tmp/studio.js
  ```

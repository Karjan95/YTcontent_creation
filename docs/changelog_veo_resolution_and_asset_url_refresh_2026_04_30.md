# Veo Resolution-Aware Billing & Project Asset URL Refresh

**Date:** 2026-04-30
**Type:** Feature + Bug fixes
**Commits:** `09fd443`, `cb9b2c0`, `5ddad0b`, `d09d8f4`

---

## Summary

Three related streams of work landed in this session:

1. **Veo billing now respects resolution.** A user picking 1080p or 4K is no longer billed at the 720p rate.
2. **Cast portraits collapsed to a single reference sheet** driven by the approved style.
3. **Every persisted asset URL is re-signed on project load**, so a project opened weeks later still renders fully — no broken images, no missing portraits.

---

## 1. Veo Resolution-Aware Billing — `09fd443`

### Problem

`pricing.py` treated every Veo model as a single `per_second` rate. UI did not let the user pick a video resolution — generation always defaulted to 720p, and billing always used the 720p price even when Google's actual rates differ by resolution (4K is +50% on Veo Quality, +200% on Veo Fast).

### Solution

Per-resolution rates plus an end-to-end resolution parameter through the Veo path.

**Backend**
- `pricing.py` — each Veo model gets a `by_resolution` map alongside the legacy `per_second` baseline:
  ```python
  "veo-3.1-generate-preview": {
      "per_second": 0.40,
      "by_resolution": {"720p": 0.40, "1080p": 0.40, "4k": 0.60},
  },
  "veo-3.1-fast-generate-preview": {
      "per_second": 0.10,
      "by_resolution": {"720p": 0.10, "1080p": 0.12, "4k": 0.30},
  },
  "veo-3.1-lite-generate-preview": {
      "per_second": 0.05,
      "by_resolution": {"720p": 0.05, "1080p": 0.08},  # no 4K
  },
  ```
- `cost_tracker.py` — `get_cost("veo", ...)` reads `usage["resolution"]`, lower-cases it, looks up `by_resolution`, and falls back to `per_second` if the resolution is unknown or the model doesn't support it.
- `cost_tracker.py` — `track_veo` and `track_veo_refund` accept and persist `resolution`. Refunds use the same resolution-aware math so a failed 4K Veo run refunds the 4K cost, not 720p.
- `gemini_client.py` — `start_video_generation(..., resolution="720p", ...)` stores resolution in the in-memory `_video_operations` entry; `poll_video_generation` retrieves it on failure to refund correctly.
- `server.py` — both `/api/visuals/start-animation` (single) and `/api/visuals/start-batch-animation` (batch) read `resolution` from the request and thread it into `start_video_generation`.

**Frontend (`ui/index.html`)**
- New "Video Resolution" dropdown (`#visVideoResolution`) with `720p` / `1080p` / `4k` (lowercase values to match backend keys; display labels capitalized).
- Per-scene resolution override on the scene card (falls back to global config).
- Veo model labels now show resolution-aware $/clip (e.g. "Veo 3.1 ~$3.60/6s @ 4k").
- 4K is automatically disabled when Veo 3.1 Lite is selected (Google doesn't support 4K on Lite). If the user had 4K selected and switches to Lite, the resolution falls back to 1080p.
- The selected resolution is sent in every single + batch start-animation request and is persisted on `visualsConfig.videoResolution`.

### Tests

- `tests/test_cost_tracker.py::test_get_cost_veo_resolution_aware` — covers 4K pricing, case-insensitivity, Lite 1080p uplift, unknown-resolution fallback, Lite + 4K graceful fallback.
- `tests/test_cost_tracker.py::test_veo_refund_resolution_aware` — verifies a 4K refund posts `-$3.60` for 6s and preserves `resolution` on the refund event.
- 14/14 ad-hoc smoke cases pass; full suite stays green at 99/99.

---

## 2. Cast Portraits → Single Reference Sheet — `cb9b2c0`

### Problem

The cast UI generated **two** images per character (`face_closeup` + `full_body`). Users had to wait for two API calls, manage two sets of prompts, and the two renders often disagreed on what the same character looked like. The approved style from Style Review didn't influence cast portrait prompts at all, so portraits frequently clashed with the project's chosen visual style.

### Solution

One image per character — a 7-panel reference sheet — with the approved style baked into the prompt.

**`research_templates.py`**
- `build_cast_suggestion_prompt(...)` accepts `style_summary`. When present, it is injected at the start of every reference-sheet prompt so the AI matches the approved visual style.
- `portrait_prompts` now has a single `reference_sheet` key (was `face_closeup` + `full_body`). The prompt template describes a 7-panel layout: 4 full-body views (front / left profile / right profile / back) on the top row, 3 close-up portraits on the bottom row, A-pose, plain background, consistent lighting.

**`server.py`**
- `/api/suggest-cast` reads `style_analysis` from the request and forwards `style_summary` into the casting prompt.
- `/api/generate-cast-portrait` and the batch variant accept `portrait_type='reference_sheet'` (16:9 aspect, replacing the old 1:1 face-closeup and 9:16 full-body).
- Both routes pass `style_summary` as `additional_context` so the image model holds the style reference at generation time.

**`ui/index.html`**
- One **Generate Reference Sheet** button per cast card, replacing the dual face/body buttons.
- A "No style set — character may not match your visuals" warning chip appears on cast cards when `approvedStyle` is empty.
- The dual API calls collapsed into a single request to `/api/generate-cast-portrait` with `portrait_type: 'reference_sheet'`.
- Legacy `face_closeup` / `full_body` fields are kept as **read fallbacks** (see §3) — old projects don't lose their saved portraits, but new generation only writes `reference_sheet`.

**`ui/style.css`**
- New `.cast-portrait-wide` (16:9 inline image) and `.cast-style-warning` styles.

### Migration

No data migration. Existing characters with old portraits show "Regenerate Sheet"; clicking it produces a fresh `reference_sheet`. Until they regenerate, the legacy image renders in the same single-image slot via the fallback in §3.

---

## 3. Project Asset URL Refresh on Load — `5ddad0b`, `d09d8f4`

### Problem

Two distinct symptoms with the same root cause: signed Firebase Storage URLs expire after 4 hours, but the UI's auto-sync only fired when a URL field was completely missing. After expiry the URL string still sat in Firestore, and the UI rendered broken `<img>` tags even though the asset was perfectly intact in Firebase Storage.

In addition, the cast card render in `cb9b2c0` only displayed `portraits.reference_sheet.url`, so any character generated before the refactor (data still keyed under `face_closeup` or `full_body`) showed nothing — the `hasPortraits` check correctly recognized the legacy data, but the actual `<img>` tag ignored it.

### Solution

A new server endpoint that re-signs every persisted asset URL in one round-trip, called automatically on every project load — plus a legacy fallback in the cast UI.

**`server.py` — new endpoint `/api/refresh-project-urls`**

```
POST /api/refresh-project-urls
Body:    { project_id, blob_paths: [str], scene_ids: [str] }
Returns: { blobs:  { blob_path: fresh_url, ... },   # direct re-sign
           scenes: { scene_id:  fresh_url, ... },   # prefix-scan images/{pid}/
           videos: { scene_id:  fresh_url, ... } }  # prefix-scan videos/{pid}/
```

Direct `blob_path` re-sign is used for assets where we persist the path (cast portraits, style references, character images). Scene images and videos are matched by scanning `images/{project_id}/scene_*` and `videos/{project_id}/scene_*` and matching by `scene_id` — same approach as the existing `/api/visuals/sync-storage-images`, since scenes don't persist a `blob_path`.

`blob_paths` are validated against the prefixes `references/`, `images/`, `videos/` only — a user can't ask the server to sign arbitrary blobs.

**`ui/index.html` — `refreshAllProjectUrls()`**

Called from `loadProject` on every project switch. In one round-trip it re-signs:

| Asset | How |
|---|---|
| `visualsScenes[*].imageUrl` | prefix scan by `scene_id` |
| `visualsScenes[*].videoUrl` | prefix scan by `scene_id` |
| `visualsScenes[*].lastFrameUrl` | path extracted from URL → blob re-sign |
| `visualsScenes[*].refImages[*]` | path extracted from URL → blob re-sign |
| `visualsScenes[*].imageHistory[*]` | already re-signed by existing `fetchImageHistory()` |
| `currentCast.cast[*].portraits.{reference_sheet,face_closeup,full_body}` | persisted `blob_path` → re-sign |
| `visualsConfig.styleImages[*]` | persisted `path` → re-sign |
| `styleReferenceImages[*]` (Style Review panel) | persisted `path` → re-sign |
| `visualsCharacters[*].images[*]` | persisted `path` → re-sign |

A small helper, `pathFromFirebaseUrl(url)`, extracts the bucket-relative path from any signed URL pointing into `references/`, `images/`, `videos/`, or `audio/` — used as a fallback whenever an asset is missing its persisted `blob_path` (e.g. older `lastFrameUrl` values).

After the round-trip, the function rewrites URLs in memory and re-renders cast / scenes / characters / style previews, then triggers an autosave so Firestore picks up the fresh URLs.

**`ui/index.html` — cast portrait legacy fallback**

The cast card render now resolves the displayed URL as:

```js
const url = char.portraits?.reference_sheet?.url
         || char.portraits?.face_closeup?.url
         || char.portraits?.full_body?.url;
```

Old projects render their existing image in the single Reference Sheet slot. New work only writes `reference_sheet`.

### What is **not** refreshed (intentional)

- `kie_generations[*].url` — these are KIE.ai CDN URLs, not Firebase signed URLs, so they don't expire.
- TTS / voiceover audio — not persisted on the project document.

---

## Files Changed

| File | Stream | Notes |
|---|---|---|
| `execution/pricing.py` | Veo | per-Veo `by_resolution` rate map |
| `execution/cost_tracker.py` | Veo | `track_veo` + `track_veo_refund` accept `resolution` |
| `execution/gemini_client.py` | Veo | thread `resolution` through `start_video_generation` / `poll_video_generation` |
| `execution/research_templates.py` | Cast | `style_summary` parameter, single `reference_sheet` prompt template |
| `execution/server.py` | Cast + URL refresh | cast routes accept `style_summary`; new `/api/refresh-project-urls` |
| `ui/index.html` | All three | resolution dropdown + per-scene override, single reference-sheet UI, legacy portrait fallback, `refreshAllProjectUrls()` |
| `ui/style.css` | Cast | `.cast-portrait-wide`, `.cast-style-warning` |
| `tests/test_cost_tracker.py` | Veo | resolution-aware get_cost + refund tests |

## Tests

99/99 pytest cases pass on a clean checkout. Two new resolution-aware test cases added.

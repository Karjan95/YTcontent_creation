# Kie Studio model registry — full doc-driven audit

**Date:** 2026-05-17
**Scope:** Verified 83 of 86 Kie-backed Studio models against `docs.kie.ai`,
patched every mismatch in `execution/model_schemas.py`, and taught the
`/api/studio/generate` dispatcher about the new field names + JSON-array
inputs surfaced by the sweep.

---

## Why

User report: "most of my models in the Studio tab are missing either some
parameter, or have some issues." The registry had drifted from the live Kie
docs for almost every provider. Many entries shipped wrong `model` IDs (so the
API returned "unknown model" on every call), wrong field names (so the API
silently dropped reference images / source videos and fell back to text-only
generation), or wrong enum values (so the user's selection was rejected).

The audit fetched every model's docs page on `docs.kie.ai/market/*` and diffed
each entry — `model` field, every required + optional input, every enum, every
default — against our schema. Bugs were grouped into BROKEN (call fails or
behaves wrong) and DEGRADED (works but param is rejected/ignored).

---

## Models with wrong `model` IDs (catastrophic — every call failed)

Schema id was being used as the value of the `model` field in the createTask
body. These no longer matched the strings the API actually accepts:

| Old schema id (rejected by API) | Corrected id |
|---|---|
| `kling/text-to-video` | `kling-2.6/text-to-video` |
| `kling/image-to-video` | `kling-2.6/image-to-video` |
| `kling/motion-control` | `kling-2.6/motion-control` |
| `kling/motion-control-v3` | `kling-3.0/motion-control` |
| `bytedance/seedance-1-5-pro` | `bytedance/seedance-1.5-pro` |
| `bytedance/seedream-4-5-text-to-image` | `seedream/4.5-text-to-image` |
| `bytedance/seedream-4-5-edit` | `seedream/4.5-edit` |
| `bytedance/seedream-5-lite-text-to-image` | `seedream/5-lite-text-to-image` |
| `bytedance/seedream-5-lite-image-to-image` | `seedream/5-lite-image-to-image` |
| `gpt-image/1-5-text-to-image` | `gpt-image/1.5-text-to-image` |
| `gpt-image/1-5-image-to-image` | `gpt-image/1.5-image-to-image` |
| `z-image/z-image` | `z-image` |

For each, the schema was also rewritten to reflect the correct param shape
documented on the model's page (some, like Seedream 4.5 and 5 Lite, use a
totally different `aspect_ratio + quality` shape than the V4 it had been
copying).

---

## Wrong field names (request body shipped but API ignored / rejected)

The single most common bug. The dispatcher only normalised `image_input` /
`image_urls` as the primary image input; every other field went through as-is.
When the schema declared the wrong name, the API silently dropped it.

- **Sora 2 (T2V + Pro T2V + I2V + Pro I2V)** — `image_url` (singular) → `image_urls` (array, max 1); `character_ids` → `character_id_list`; added required `upload_method` enum to ALL four variants; `size` enum is Pro-only.
- **Sora 2 Pro Storyboard** — `storyboard_json` (text blob) → `shots` (array of `{Scene, duration}` objects); added `upload_method`, `n_frames` enum (incl. `'25'`), optional `image_urls`; dropped `size`.
- **Sora Watermark Remover** — `origin_task_id` (task picker) → `video_url` (URL string) with required `upload_method`.
- **Wan 2.6 V2V / Flash V2V** — `source_video_url` (singular) → `video_urls` (array, max 3).
- **Wan 2.2 Animate Move / Replace** — `source_video` + `motion_video` / `character_image` → `video_url` + `image_url`. (Note: in Animate Move the "character" is an IMAGE, the "motion" is a VIDEO — the field types had been swapped.)
- **Wan 2.6 / 2.6 Flash I2V** — `image_url` (singular) → `image_urls` (array, max 1).
- **Seedance v1 (Pro, Pro Fast, Lite × T2V/I2V)** — I2V `first_frame` → `image_url` (singular); Lite I2V added `end_image_url`.
- **HappyHorse Video Edit** — `source_video_url` → `video_url`; added `reference_image` (array max 5) and `audio_setting` enum.
- **Kling 2.5 Turbo Pro I2V / Kling 2.1 Master I2V / Kling 2.1 Pro / 2.1 Standard** — dropped `aspect_ratio` (not accepted by I2V endpoints); Kling 2.1 Pro added optional `tail_image_url`.
- **Kling Motion Control (2.6 + 3.0)** — `image_url` + `motion_video_url` → `input_urls` + `video_urls` (both arrays); added `mode`, `character_orientation`; 3.0 additionally added `background_source`.
- **Flux 2 Pro I2I / Flex I2I** — `image_input` (max 4) → `input_urls` (max 8); I2I aspect_ratio includes `auto`.
- **Google nano-banana-edit** — `image_input` (max 3) → `image_urls` (max 10).
- **Seedream V4 Edit** — `image_input` (max 6) → `image_urls` (max 10).
- **GPT Image 2 I2I / 1.5 I2I** — `image_input` (max 4) → `input_urls` (max 16).
- **Qwen Image I2I / Image Edit / Qwen2 Image Edit** — `image_input` array → `image_url` singular.
- **Qwen2 T2I / Image Edit** — split out of the v1 loop, params replaced with v2 shape (aspect-ratio strings, no `guidance_scale` / `num_inference_steps`).
- **Ideogram V3 Edit** — schema rebuilt: required `image_url` + `mask_url` (both singular strings); dropped per-variant params that don't belong.
- **Ideogram V3 Remix** — `image_input` array → `image_url` singular; added `strength` slider.
- **Ideogram Character** — `character_reference_image` (max 4) → `reference_image_urls` (max 1); style enum corrected to `[AUTO, REALISTIC, FICTION]`.
- **Ideogram Character Edit** — added required `image_url` + `mask_url`; same enum/field fixes.
- **Ideogram Character Remix** — added required `image_url` + `reference_image_urls` (max 1).
- **Grok Imagine I2I** — `image_input` (max 1) → `image_urls` (array up to 5; only 1 active).
- **Grok Imagine Extend / Upscale** — `origin_task_id` → `task_id`. Extend additionally: `duration` enum → `extend_times` enum `['6','10']`; added optional `extend_at`.

---

## Wrong enums / defaults / missing params

- **Seedance 2 Fast** — resolution enum dropped `1080p` (Fast doesn't support it).
- **Seedance 1.5 Pro** — completely separate shape from Seedance 2: `input_urls` (0-2), `aspect_ratio` (required), `duration` enum `['4','8','12']` (required), `fixed_lens` bool, `generate_audio` default `false`.
- **Seedance v1 family** — `duration` int range → string enum `['5','10']`; aspect_ratio dropped on I2V; Pro Fast resolution `[720p, 1080p]` only; added `camera_fixed`, `seed`, `enable_safety_checker`, `nsfw_checker`.
- **Wan 2.6 T2V/V2V/Flash V2V** — dropped `ratio` (doesn't exist); duration int → string enum; resolution dropped `480p`; default `'1080p'`.
- **Wan 2.5 T2V** — `ratio` → `aspect_ratio`; added `enable_prompt_expansion`.
- **Wan 2.5 I2V** — `image_url` correctly kept singular (differs from Wan 2.6); duration enum; resolution `[720p, 1080p]`.
- **Wan 2.7 R2V** — `reference_image` + `reference_video` combined cap of 5 (was 9 + 3); duration max 10 (was 15).
- **Wan 2.7 Video Edit** — added `audio_setting` enum (`auto` / `origin`).
- **Wan 2.2 Turbo T2V/I2V** — dropped non-existent `duration`; resolution `[480p, 720p]` (no `580p`); T2V aspect_ratio `[16:9, 9:16]` (no `1:1`); I2V dropped aspect_ratio; added `acceleration` enum, `enable_prompt_expansion`, `nsfw_checker`.
- **Hailuo 02 Pro (T2V + I2V)** — dropped non-existent `duration`/`resolution`; added `prompt_optimizer`, `end_image_url`.
- **Hailuo 02 Standard T2V** — kept `duration` enum; dropped non-existent `resolution`; added `prompt_optimizer`.
- **Hailuo 02 Standard I2V** — added `end_image_url`, `prompt_optimizer`; resolution corrected to `[512P, 768P]` (was `[768P, 1080P]`); default duration `'10'`.
- **Kling 3.0** — `mode` enum gained `"4K"` option.
- **Grok Imagine T2I** — aspect_ratio enum `[2:3, 3:2, 1:1, 16:9, 9:16]` (was `[1:1, 16:9, 9:16, 4:3, 3:4]`); added `enable_pro`, `nsfw_checker`.
- **Grok Imagine T2V** — aspect_ratio enum corrected (default `2:3`); duration `['6','10','15','20','30']` (was `['5','10']`); added `resolution`, `mode`, `nsfw_checker`.
- **Grok Imagine I2V** — duration enum corrected to `['6','10','15','20','30']`; added `resolution`, `mode`, `nsfw_checker`.
- **Imagen 4 (Kie)** — dropped `num_images` from base + Ultra (only Fast accepts it, as string enum); Fast default aspect_ratio `16:9`.
- **InfiniTalk** — `prompt` now required.
- **ElevenLabs Multilingual v2 + Turbo 2.5** — `voice` now required with default `EkK5I93UQWFDigLMpZcX` (James). Was optional with no default; API rejected blank.
- **ElevenLabs Dialogue v3** — field renamed `dialogue_json` → `dialogue` (dispatcher JSON-parses the textarea content before sending); `stability` is a number enum `[0, 0.5, 1]`, not strings.
- **Z-Image** — `model` is `z-image` not `z-image/z-image`; added `nsfw_checker`.
- **Wan 2.7 Image / Image Pro** — added `input_urls` (max 9), full aspect_ratio enum (`21:9`, `8:1`, `1:8`), `resolution` enum (default `2K`), `watermark`, `nsfw_checker`.

---

## Dispatcher changes (`execution/server.py`)

`_studio_dispatch_kie_generic` got two extensions:

1. **JSON-array fields parsed before send.** Two models accept a structured
   array in a field the UI can only ship as a JSON text blob:
   - `elevenlabs/text-to-dialogue-v3` → `dialogue` (array of `{text, voice}`)
   - `sora-2-pro-storyboard` → `shots` (array of `{Scene, duration}`)
   The dispatcher now `json.loads` these fields and returns a 400 with a clear
   parse error if invalid JSON arrives.

2. **URL re-hosting expanded.** The audit introduced several new field names
   that carry user-uploaded URLs (Firebase Storage URLs need to be re-hosted
   to Kie's CDN before generation). Added: `input_urls`, `video_urls`,
   `tail_image_url`, `end_image_url`, `mask_url`, `first_clip_url`.

---

## What's still NOT fixed

- **Veo via Kie** (`veo3-kie`, `veo3-kie-extend`) — still return HTTP 501.
  Needs a new dispatcher for the `/veo3-api/*` endpoint shape (different from
  generic `/jobs/createTask`).
- **Runway via Kie** (`runway-gen`, `runway-aleph`, `runway-extend`) — still
  HTTP 501. Same situation, different endpoint shape.
- **Three model pages 404'd** on docs.kie.ai and could not be verified, so
  left as-is: `ideogram/v3-reframe`, `elevenlabs/sound-effect-v2`,
  `elevenlabs/speech-to-text`.
- **`KIE_MODELS` legacy dict** in `execution/kie_client.py` still lives in
  parallel with `MODEL_SCHEMAS`. Where both register the same model id
  (handful of cases — Kling 3.0, Nano Banana family), the legacy hand-tuned
  builder still runs. Not breaking, but worth unifying eventually.

---

## Files

| File | Δ |
|---|---|
| `execution/model_schemas.py` | +1293 / -382 lines (the bulk of the audit) |
| `execution/server.py` | +30 lines in `_studio_dispatch_kie_generic` |
| `docs/changelog_kie_models_audit_2026_05_17.md` | new |

Verified by `import model_schemas` (129 entries register clean) and spot-check
of every catastrophic-id fix. No live API calls were run as part of this
change — user will smoke-test on staging.

---

## Follow-up: passthrough payload field default (commit 798542a)

First smoke test on staging caught a regression: Seedream 5 Lite I2I returned
HTTP 500 after the audit. Root cause was in `kie_client._build_generic_passthrough_payload`,
not the schema audit itself — the passthrough builder defaulted the image-array
field to `image_input` when the schema declared `image_urls`. Because the
`/api/studio/generate` dispatcher extracts the image URLs out of inputs and
hands them to `kie_create_task` as a positional `image_urls` arg, the
passthrough never sees them in its `params` dict and always falls back to
the default — so it shipped the wrong field name and Kie silently dropped
the image, then errored.

Fix: changed the passthrough default from `image_input` to `image_urls`
(the field name verified-correct for every modern Kie market model). The
two nano-banana variants that genuinely use `image_input` route through the
hand-tuned `_build_task_payload` legacy path, not the passthrough, so they
aren't affected.

Models unblocked by this one-line change:
`seedream/v4-edit`, `seedream/4.5-edit`, `seedream/5-lite-image-to-image`,
`google/nano-banana-edit`, `sora-2-image-to-video`, `sora-2-pro-image-to-video`,
`kling-2.6/image-to-video`, `happyhorse/image-to-video`,
`grok-imagine/image-to-image`, `grok-imagine/image-to-video`,
`wan/2-6-image-to-video`, `wan/2-6-flash-image-to-video`.

Models that send `input_urls` (Flux 2 I2I, GPT Image I2I, Seedance 1.5 Pro,
Wan 2.7 Image, Kling motion-control) were already correct — the dispatcher
doesn't extract `input_urls`, so it stays in `extras` and reaches the
passthrough via `params`, where it's preserved as-is.

# Research — Google AI Media Generation Surface (2026-05-05)

> Source-of-truth dump for the Studio UI rebuild. Cross-checked against
> `google-genai==1.63.0` SDK introspection and the official `ai.google.dev`
> docs. "unknown" = could not confirm; do NOT guess.

Existing integration in `execution/gemini_client.py` already calls a subset
(Gemini 2.5/3 image, Imagen 4 family, Veo 3.1 family, gemini-2.5-flash-preview-tts).

---

## 1. IMAGES — `client.models.generate_content` (Gemini-native, "Nano Banana" family)

Conversational, multimodal image models — invoked through `generate_content`
with `response_modalities=["TEXT","IMAGE"]` (or `["IMAGE"]`). Support
**reference images, editing, and grounding**.

### 1.1 `gemini-3-pro-image-preview` — Nano Banana Pro
- **Display name**: Nano Banana Pro (Gemini 3 Pro Image)
- **Modality**: `text_to_image`, `image_edit`, `image_compose`
- **Inputs**: text + up to **6 object refs** OR **5 character refs**; supports Google Search grounding
- **Params** (`ImageConfig` + `GenerateContentConfig`):
  - `response_modalities`: `["TEXT","IMAGE"]` (default) | `["IMAGE"]`
  - `aspect_ratio`: `1:1`, `2:3`, `3:2`, `3:4`, `4:3`, `4:5`, `5:4`, `9:16`, `16:9`, `21:9`
  - `image_size`: `1K` (default), `2K`, `4K`
  - `tools`: optional `googleSearch`
  - Standard: `temperature`, `top_p`, `top_k`, `max_output_tokens`, `system_instruction`, `safety_settings`, `seed`
- **Output**: PNG bytes in `response.candidates[].content.parts[].inline_data` + SynthID
- **Pricing**: $0.134/img @ 1K-2K · **$0.24/img @ 4K** (standard). Batch & Flex 50%.
- **Quirks**: "Thinking" model — may return interim images; supports text rendering.

### 1.2 `gemini-3.1-flash-image-preview` — Nano Banana 2
- **Display**: Nano Banana 2 (Gemini 3.1 Flash Image)
- **Modality**: `text_to_image`, `image_edit`, `image_compose`
- **Inputs**: text + up to **10 object refs** OR **4 character refs**; Google Search grounding
- **Params**:
  - `response_modalities`: as above
  - `aspect_ratio`: `1:1`, `1:4`, `1:8`, `2:3`, `3:2`, `3:4`, `4:1`, `4:3`, `4:5`, `5:4`, `8:1`, `9:16`, `16:9`, `21:9` (widest of any)
  - `image_size`: `512`, `1K` (default), `2K`, `4K`
  - `thinking_level`: `minimal` (default) | `high`
  - `include_thoughts` (bool)
  - `tools`: `googleSearch`
- **Output**: PNG + SynthID
- **Pricing**: $0.045 (0.5K), **$0.067 (1K)**, $0.101 (2K), $0.151 (4K). Batch ~50%.
- **Quirks**: Up to 2 interim "thinking" images may stream.

### 1.3 `gemini-2.5-flash-image` — Nano Banana (STABLE, currently used)
- **Display**: Nano Banana (Gemini 2.5 Flash Image)
- **Modality**: `text_to_image`, `image_edit`
- **Inputs**: text + up to **3 reference images** (optimal)
- **Params**:
  - `response_modalities`: as above
  - `aspect_ratio`: `1:1`, `2:3`, `3:2`, `3:4`, `4:3`, `4:5`, `5:4`, `9:16`, `16:9`, `21:9`
  - **No `image_size`** — fixed 1024px base (e.g., 1:1=1024x1024, 16:9=1344x768)
- **Output**: PNG + SynthID
- **Pricing**: $0.039/img std ($0.0195 batch/flex, $0.0702 priority)
- **Quirks**: Only stable Nano Banana variant.

---

## 2. IMAGES — `client.models.generate_images` (Imagen 4 family)

Text-only, no reference image support. Returns 1–4 images per call.

**Shared `GenerateImagesConfig`** (full SDK):
| Field | Type | Default | Notes |
|---|---|---|---|
| `number_of_images` | int | 4 | 1-4 |
| `aspect_ratio` | str | `"1:1"` | `1:1`, `3:4`, `4:3`, `9:16`, `16:9` |
| `image_size` | str | `"1K"` | `1K`, `2K` |
| `person_generation` | enum | `ALLOW_ADULT` | `DONT_ALLOW`, `ALLOW_ADULT`, `ALLOW_ALL` |
| `safety_filter_level` | enum | unknown | `BLOCK_LOW_AND_ABOVE`, `BLOCK_MEDIUM_AND_ABOVE`, `BLOCK_ONLY_HIGH`, `BLOCK_NONE` |
| `negative_prompt` | str | None | SDK exposes; **may be ignored** on Imagen 4 per public docs |
| `seed` | int | None | Ignored when `add_watermark=True` |
| `guidance_scale` | float | None | SDK-exposed |
| `language` | enum | `auto` | `auto`, `en`, `ja`, `ko`, `hi`, `zh`, `pt`, `es` |
| `output_mime_type` | str | `image/png` | png \| jpeg |
| `output_compression_quality` | int | None | JPEG 0-100 |
| `add_watermark` | bool | True | SynthID |
| `enhance_prompt` | bool | None | LLM rewrite |
| `include_safety_attributes` | bool | None | |
| `include_rai_reason` | bool | None | |
| `output_gcs_uri` | str | None | Vertex/GCS sink |
| `labels` | dict | None | Billing |
| `http_options` | HttpOptions | None | |

Input prompt limit: **480 tokens**.

| Model | Pricing | Notes |
|---|---|---|
| `imagen-4.0-generate-001` | **$0.04/img** | Standard |
| `imagen-4.0-fast-generate-001` | **$0.02/img** | Fast |
| `imagen-4.0-ultra-generate-001` | **$0.06/img** | `number_of_images=1` only |

(Imagen 3 has been **shut down**.)

---

## 3. IMAGES — Edit / Recontext / Upscale / Segment (Imagen-class)

Available via SDK `client.models.edit_image`, `recontext_image`,
`upscale_image`, `segment_image`. **Public Gemini API availability is
partial — Vertex-first**; verify per model before exposing.

### 3.1 `edit_image` — `EditImageConfig`
All fields from `GenerateImagesConfig` plus:
- `edit_mode`: `EDIT_MODE_DEFAULT`, `INPAINT_REMOVAL`, `INPAINT_INSERTION`, `OUTPAINT`, `CONTROLLED_EDITING`, `STYLE`, `BGSWAP`, `PRODUCT_IMAGE`
- `base_steps`: int (denoising)
- Reference image types (any combo):
  - `RawReferenceImage` (source)
  - `MaskReferenceImage` + `MaskReferenceConfig{mask_mode: USER_PROVIDED|BACKGROUND|FOREGROUND|SEMANTIC, segmentation_classes: list[int], mask_dilation: float}`
  - `ControlReferenceImage` + `ControlReferenceConfig{control_type: DEFAULT|CANNY|SCRIBBLE|FACE_MESH, enable_control_image_computation: bool}`
  - `StyleReferenceImage` + `StyleReferenceConfig{style_description: str}`
  - `SubjectReferenceImage` + `SubjectReferenceConfig{subject_type: DEFAULT|PERSON|ANIMAL|PRODUCT, subject_description: str}`

### 3.2 `upscale_image` — `UpscaleImageConfig`
- `enhance_input_image` (bool)
- `image_preservation_factor` (float 0-1)
- `output_mime_type`, `output_compression_quality`
- `safety_filter_level`, `person_generation`, `include_rai_reason`
- `output_gcs_uri`, `labels`, `http_options`
- Models: `imagen-...-upscale` (Vertex). **Public API: unknown**.

### 3.3 `recontext_image` — `RecontextImageConfig`
- `number_of_images`, `base_steps`, `seed`, `enhance_prompt`, `add_watermark`
- `safety_filter_level`, `person_generation`
- output config + `output_gcs_uri`, `labels`
- Use: re-stage subject in new scene (`imagen-product-recontext-preview-...`). **Availability: unknown**.

### 3.4 `segment_image` — `SegmentImageConfig`
- `mode`: `FOREGROUND`, `BACKGROUND`, `PROMPT`, `SEMANTIC`, `INTERACTIVE`
- `max_predictions` (int)
- `confidence_threshold` (float)
- `mask_dilation` (float)
- `binary_color_threshold` (float)
- Produces mask for `MaskReferenceImage`. **Availability: unknown**.

---

## 4. VIDEO — `client.models.generate_videos` (Veo)

All Veo calls return long-running `Operation` — **must poll** `client.operations.get(op)` until `op.done=True` (10s typical interval; 11s min latency, ~6 min max). Already wired in our `start_video_generation`.

**Shared `GenerateVideosConfig`** (full SDK):
| Field | Type | Default | Notes |
|---|---|---|---|
| `number_of_videos` | int | 1 | All preview = 1; Veo 2 = 1 or 2 |
| `aspect_ratio` | str | `"16:9"` | `16:9`, `9:16` |
| `resolution` | str | `"720p"` | `720p`, `1080p`, `4k` (per-model) |
| `duration_seconds` | int | 8 | Veo 3/3.1: 4, 6, 8; Veo 2: 5, 6, 8. **1080p/4k require 8** |
| `fps` | int | 24 | All Veo = 24fps |
| `person_generation` | str | `allow_adult` | T2V allows `allow_all`; I2V allows `allow_adult`; Veo 2 supports `dont_allow` |
| `generate_audio` | bool | True (Veo 3+) | Veo 2 = silent only |
| `negative_prompt` | str | None | |
| `seed` | int | None | |
| `enhance_prompt` | bool | None | |
| `last_frame` | Image | None | Final-frame for interpolation |
| `reference_images` | list[VideoGenerationReferenceImage] | None | Up to **3 refs** (Veo 3.1 family) |
| `mask` | VideoGenerationMask | None | Masked region |
| `compression_quality` | enum | `OPTIMIZED` | `OPTIMIZED` \| `LOSSLESS` |
| `output_gcs_uri` | str | None | |
| `pubsub_topic` | str | None | Async notif |

Inputs by mode:
- T2V: text only
- I2V: text + first-frame image
- Frames: text + first-frame + `last_frame`
- Reference-guided: text + `reference_images`
- Extension: existing video (Veo 3.1 / 3.1 Fast only, **720p only**)

| Model | Modes | Resolution | Audio | Pricing |
|---|---|---|---|---|
| `veo-3.1-generate-preview` | T2V, I2V, frames, refs(3), extend | 720p, 1080p, 4k(8s) | yes | $0.40/s @ 720p/1080p · **$0.60/s @ 4K** |
| `veo-3.1-fast-generate-preview` | same | same | yes | $0.10/s @ 720p · $0.12/s @ 1080p · $0.30/s @ 4K |
| `veo-3.1-lite-generate-preview` | T2V, I2V, frames, refs | 720p, 1080p (no 4K) | yes | $0.05/s @ 720p · $0.08/s @ 1080p |
| `veo-3.0-generate-001` | T2V, I2V, frames | 720p, 1080p(8s) | yes | $0.40/s std |
| `veo-3.0-fast-generate-001` | same | 720p, 1080p, 4k | yes | $0.10/s @ 720p · $0.12/s @ 1080p · $0.30/s @ 4K |
| `veo-2.0-generate-001` | T2V, I2V | (no resolution knob) | **silent** | $0.35/s |

---

## 5. SPEECH (TTS) — `client.models.generate_content` + `SpeechConfig`

Text in, 24 kHz mono PCM out (wrap as WAV). No streaming. 32k input ctx. SynthID.

**`SpeechConfig` fields:**
- `voice_config` (`VoiceConfig`): single-speaker
  - `prebuilt_voice_config.voice_name`: one of 30 names below
  - `replicated_voice_config`: custom cloning (gated)
- `multi_speaker_voice_config` (`MultiSpeakerVoiceConfig`):
  - `speaker_voice_configs`: list of `{speaker: str, voice_config: ...}` — **max 2 speakers**
- `language_code`: BCP-47 (auto-detected from text if omitted)

**Voice expression** also driven by **inline natural-language stage directions** (e.g. `"Say cheerfully: ..."`). Already used via `generate_tts(style_instructions=...)`.

### 5.1 The 30 prebuilt voices (case-sensitive, capitalized)
Zephyr (Bright), Puck (Upbeat), Charon (Informative), Kore (Firm), Fenrir (Excitable), Leda (Youthful), Orus (Firm), Aoede (Breezy), Callirrhoe (Easy-going), Autonoe (Bright), Enceladus (Breathy), Iapetus (Clear), Umbriel (Easy-going), Despina (Smooth), Erinome (Clear), Algieba (Gravelly), Rasalgethi (Informative), Laomedeia (Upbeat), Achernar (Soft), Alnilam (Firm), Schedar (Even), Gacrux (Mature), Pulcherrima (Forward), Achird (Friendly), Zubenelgenubi (Casual), Vindemiatrix (Gentle), Sadachbia (Lively), Sadaltager (Knowledgeable), Sulafat (Warm), Algenib (Gravelly).

Our existing code uses lowercase `"kore"` — **verify or normalize to `"Kore"`**.

### 5.2 Languages
24+ supported; auto-detected. EN (US/UK/AU/IN), ES (US/ES), FR, DE, IT, PT (BR/PT), ZH, JA, KO, HI, AR (multiple), RU, NL, PL, TR, VI, TH, ID, BN, TA, TE, MR, UK.

### 5.3 No exposed pitch/rate/volume knobs
All tone/pacing/emotion via inline prompt instructions.

### 5.4 Models
| Model | Status | Pricing (per 1M tok) |
|---|---|---|
| `gemini-2.5-flash-preview-tts` (current) | Preview | $0.50 in / **$10.00 out** (batch: $0.25/$5.00) |
| `gemini-2.5-pro-preview-tts` | Preview | $1.00 in / $20.00 out |
| `gemini-3.1-flash-tts-preview` | Preview | $1.00 in / $20.00 out |

All 3 support both single- and multi-speaker. Output: 24kHz mono 16-bit PCM.

---

## 6. MUSIC — Lyria

### 6.1 `lyria-3-clip-preview` — Lyria 3 Clip
- **Modality**: `text_to_music` (+ up to **10 image inputs** for mood)
- **Output**: **MP3 only**, 44.1 kHz stereo, fixed **30s** clip; SynthID
- **Params**: text prompt (lyrics, structure tags `[Verse]/[Chorus]/[Bridge]`, timestamps `[M:SS – M:SS]`); language follows prompt
- **Pricing**: **$0.04/song**

### 6.2 `lyria-3-pro-preview` — Lyria 3 Pro
- Same as Clip plus **WAV output** and **up to ~3 min** duration via prompt control
- **Pricing**: **$0.08/song**
- Response is multipart — text part + `inline_data` audio. Don't assume ordering.

### 6.3 `models/lyria-realtime-exp` — Lyria RealTime (streaming, experimental)
- Real-time text→music via WebSocket (`client.aio.live.music.connect`)
- **Output**: 48 kHz / 16-bit / stereo PCM
- Weighted prompts: `[{text: str, weight: float}]`
- **`LiveMusicGenerationConfig`**:
  - `bpm` (int, **60-200**)
  - `density` (float, 0-1)
  - `brightness` (float, 0-1)
  - `scale` (Scale enum, 12 values + UNSPECIFIED) — `C_MAJOR_A_MINOR`, `D_FLAT_MAJOR_B_FLAT_MINOR`, `D_MAJOR_B_MINOR`, `E_FLAT_MAJOR_C_MINOR`, `E_MAJOR_D_FLAT_MINOR`, `F_MAJOR_D_MINOR`, `G_FLAT_MAJOR_E_FLAT_MINOR`, `G_MAJOR_E_MINOR`, `A_FLAT_MAJOR_F_MINOR`, `A_MAJOR_G_FLAT_MINOR`, `B_FLAT_MAJOR_G_MINOR`, `B_MAJOR_A_FLAT_MINOR`
  - `guidance` (float, **0-6**, default 4)
  - `temperature` (float, **0-3**, default 1.1)
  - `top_k` (int, **1-1000**, default 40)
  - `seed` (int, 0 to 2,147,483,647)
  - `mute_bass` (bool)
  - `mute_drums` (bool)
  - `only_bass_and_drums` (bool)
  - `music_generation_mode`: `QUALITY` (default) | `DIVERSITY` | `VOCALIZATION`
- **Pricing**: **unknown**
- Continuous bidirectional stream; gradual prompt steering recommended.

---

## 7. Cross-Cutting

- **SynthID** on all image/video/audio outputs.
- Setting `add_watermark=False` on Imagen disables `seed`.
- All generation models share `safety_filter_level` + `person_generation`.
- **Polling**: only Veo (long-running operations).
- **`MediaResolution`** enum (`LOW/MEDIUM/HIGH`) controls **input** image tokens (for understanding refs, not generation).
- No free tier on any media generation model.

---

## 8. Alignment with current code (`execution/gemini_client.py`)

**Already wired:**
- `gemini-3-pro-image-preview`, `gemini-2.5-flash-image`
- `imagen-4.0-generate-001/-fast/-ultra`
- `veo-3.1-generate-preview/-fast/-lite` (with Lite→1080p cap)
- `gemini-2.5-flash-preview-tts` (lowercase voice names — **double-check capitalization**)

**Not yet wired but worth surfacing:**
- `gemini-3.1-flash-image-preview` (Nano Banana 2 — widest aspect ratios, `thinking_level`, `image_size` to 4K)
- `veo-3.0-generate-001`, `veo-3.0-fast-generate-001`, `veo-2.0-generate-001`
- `gemini-2.5-pro-preview-tts`, `gemini-3.1-flash-tts-preview`
- Multi-speaker TTS
- `lyria-3-clip-preview`, `lyria-3-pro-preview`, `lyria-realtime-exp`
- Imagen edit/recontext/upscale/segment (verify Vertex-only first)

---

## 9. Known unknowns

- Per-model RPM/TPM rate limits on public Gemini API.
- Whether Imagen 4 actually honors `negative_prompt`/`seed`/`guidance_scale`.
- Public Gemini API availability of `edit_image`/`upscale_image`/`recontext_image`/`segment_image`.
- Lyria RealTime pricing.
- TTS voice-name case sensitivity (current code is lowercase).
- Whether `gemini-3-pro-image-preview` accepts `image_size: "512"`.

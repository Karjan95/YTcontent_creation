# Research — Kie.ai Model Catalog (2026-05-05)

> Source-of-truth dump for the Studio UI rebuild. Every media model on
> docs.kie.ai (chat-only LLM models excluded — Studio is for media).
> Filled in batches as WebFetch results come back.

Existing wired-up subset is in `execution/kie_client.py:KIE_MODELS`
(~16 models). This file expands to the full ~60+ media surface.

---

## Inventory checklist (from sitemap)

### IMAGE — text-to-image / image-to-image / edit

- [ ] **Seedream** — `market/seedream/seedream-v4-text-to-image`
- [ ] **Seedream v4 Edit** — `market/seedream/seedream-v4-edit`
- [ ] **Seedream 4.5 T2I** — `market/seedream/4-5-text-to-image`
- [ ] **Seedream 4.5 Edit** — `market/seedream/4-5-edit`
- [ ] **Seedream 5 Lite T2I** — `market/seedream/5-lite-text-to-image`
- [ ] **Seedream 5 Lite I2I** — `market/seedream-5-lite-image-to-image`
- [ ] **Z-Image** — `market/z-image/z-image`
- [ ] **Nano Banana** — `market/google/nano-banana`
- [ ] **Nano Banana Edit** — `market/google/nano-banana-edit`
- [ ] **Nano Banana 2** — `market/google/nanobanana2`
- [ ] **Nano Banana Pro I2I** — `market/google/pro-image-to-image`
- [ ] **Imagen 4** — `market/google/imagen4`
- [ ] **Imagen 4 Fast** — `market/google/imagen4-fast`
- [ ] **Imagen 4 Ultra** — `market/google/imagen4-ultra`
- [ ] **Flux 2 Pro T2I** — `market/flux2/pro-text-to-image`
- [ ] **Flux 2 Pro I2I** — `market/flux2/pro-image-to-image`
- [ ] **Flux 2 Flex T2I** — `market/flux2/flex-text-to-image`
- [ ] **Flux 2 Flex I2I** — `market/flux2/flex-image-to-image`
- [ ] **Grok Imagine T2I** — `market/grok-imagine/text-to-image`
- [ ] **Grok Imagine I2I** — `market/grok-imagine/image-to-image`
- [ ] **GPT Image 1.5 T2I** — `market/gpt-image/1-5-text-to-image`
- [ ] **GPT Image 1.5 I2I** — `market/gpt-image/1-5-image-to-image`
- [ ] **GPT Image 2 T2I** — `market/gpt/gpt-image-2-text-to-image`
- [ ] **GPT Image 2 I2I** — `market/gpt/gpt-image-2-image-to-image`
- [ ] **Ideogram v3 T2I** — `market/ideogram/v3-text-to-image`
- [ ] **Ideogram v3 Edit** — `market/ideogram/v3-edit`
- [ ] **Ideogram v3 Remix** — `market/ideogram/v3-remix`
- [ ] **Ideogram v3 Reframe** — `market/ideogram/v3-reframe`
- [ ] **Ideogram Character** — `market/ideogram/character`
- [ ] **Ideogram Character Edit** — `market/ideogram/character-edit`
- [ ] **Ideogram Character Remix** — `market/ideogram/character-remix`
- [ ] **Qwen T2I** — `market/qwen/text-to-image`
- [ ] **Qwen I2I** — `market/qwen/image-to-image`
- [ ] **Qwen Image Edit** — `market/qwen/image-edit`
- [ ] **Qwen 2 T2I** — `market/qwen2/text-to-image`
- [ ] **Qwen 2 Image Edit** — `market/qwen2/image-edit`
- [ ] **Wan 2.7 Image** — `market/wan/2-7-image`
- [ ] **Wan 2.7 Image Pro** — `market/wan/2-7-image-pro`
- [ ] **GPT-4o Image API** — `4o-image-api/generate-4-o-image` (legacy)
- [ ] **Flux Kontext API** — `flux-kontext-api/generate-or-edit-image` (legacy)

### IMAGE — utility (upscale / bgremove)

- [ ] **Topaz Image Upscale** — `market/topaz/image-upscale`
- [ ] **Recraft Crisp Upscale** — `market/recraft/crisp-upscale`
- [ ] **Recraft Remove Background** — `market/recraft/remove-background`

### VIDEO — text-to-video / image-to-video

- [ ] **Kling T2V** — `market/kling/text-to-video`
- [ ] **Kling I2V** — `market/kling/image-to-video`
- [ ] **Kling 2.5 Turbo Pro T2V** — `market/kling/v25-turbo-text-to-video-pro`
- [ ] **Kling 2.5 Turbo Pro I2V** — `market/kling/v25-turbo-image-to-video-pro`
- [ ] **Kling 2.1 Master I2V** — `market/kling/v2-1-master-image-to-video`
- [ ] **Kling 2.1 Master T2V** — `market/kling/v2-1-master-text-to-video`
- [ ] **Kling 2.1 Pro** — `market/kling/v2-1-pro`
- [ ] **Kling 2.1 Standard** — `market/kling/v2-1-standard`
- [ ] **Kling 3.0** — `market/kling/kling-3-0`
- [ ] **Seedance 2** — `market/bytedance/seedance-2`
- [ ] **Seedance 2 Fast** — `market/bytedance/seedance-2-fast`
- [ ] **Seedance 1.5 Pro** — `market/bytedance/seedance-1-5-pro`
- [ ] **Seedance v1 Pro Fast I2V** — `market/bytedance/v1-pro-fast-image-to-video`
- [ ] **Seedance v1 Pro I2V** — `market/bytedance/v1-pro-image-to-video`
- [ ] **Seedance v1 Pro T2V** — `market/bytedance/v1-pro-text-to-video`
- [ ] **Seedance v1 Lite I2V** — `market/bytedance/v1-lite-image-to-video`
- [ ] **Seedance v1 Lite T2V** — `market/bytedance/v1-lite-text-to-video`
- [ ] **Hailuo 2.3 I2V Pro** — `market/hailuo/2-3-image-to-video-pro`
- [ ] **Hailuo 2.3 I2V Standard** — `market/hailuo/2-3-image-to-video-standard`
- [ ] **Hailuo 02 T2V Pro** — `market/hailuo/02-text-to-video-pro`
- [ ] **Hailuo 02 I2V Pro** — `market/hailuo/02-image-to-video-pro`
- [ ] **Hailuo 02 T2V Standard** — `market/hailuo/02-text-to-video-standard`
- [ ] **Hailuo 02 I2V Standard** — `market/hailuo/02-image-to-video-standard`
- [ ] **Sora 2 T2V** — `market/sora2/sora-2-text-to-video`
- [ ] **Sora 2 I2V** — `market/sora2/sora-2-image-to-video`
- [ ] **Sora 2 Pro T2V** — `market/sora2/sora-2-pro-text-to-video`
- [ ] **Sora 2 Pro I2V** — `market/sora2/sora-2-pro-image-to-video`
- [ ] **Sora 2 Pro Storyboard** — `market/sora-2-pro-storyboard`
- [ ] **Sora 2 Characters** — `market/sora2/sora-2-characters`
- [ ] **Sora 2 Characters Pro** — `market/sora2/sora-2-characters-pro`
- [ ] **Wan 2.2 A14B I2V Turbo** — `market/wan/2-2-a14b-image-to-video-turbo`
- [ ] **Wan 2.2 A14B T2V Turbo** — `market/wan/2-2-a14b-text-to-video-turbo`
- [ ] **Wan 2.6 I2V** — `market/wan/2-6-image-to-video`
- [ ] **Wan 2.6 T2V** — `market/wan/2-6-text-to-video`
- [ ] **Wan 2.6 V2V** — `market/wan/2-6-video-to-video`
- [ ] **Wan 2.6 Flash I2V** — `market/wan/2-6-flash-image-to-video`
- [ ] **Wan 2.6 Flash V2V** — `market/wan/2-6-flash-video-to-video`
- [ ] **Wan 2.5 I2V** — `market/wan/2-5-image-to-video`
- [ ] **Wan 2.5 T2V** — `market/wan/2-5-text-to-video`
- [ ] **Wan 2.7 T2V** — `market/wan/2-7-text-to-video`
- [ ] **Wan 2.7 I2V** — `market/wan/2-7-image-to-video`
- [ ] **Wan 2.7 Video Edit** — `market/wan/2-7-videoedit`
- [ ] **Wan 2.7 R2V** — `market/wan/2-7-r2v` (reference-to-video)
- [ ] **Happyhorse T2V** — `market/happyhorse/text-to-video`
- [ ] **Happyhorse I2V** — `market/happyhorse/image-to-video`
- [ ] **Happyhorse R2V** — `market/happyhorse/reference-to-video`
- [ ] **Happyhorse Video Edit** — `market/happyhorse/video-edit`
- [ ] **Grok Imagine T2V** — `market/grok-imagine/text-to-video`
- [ ] **Grok Imagine I2V** — `market/grok-imagine/image-to-video`
- [ ] **Grok Imagine Upscale** — `market/grok-imagine/upscale`
- [ ] **Grok Imagine Extend** — `market/grok-imagine/extend`
- [ ] **Veo 3** — `veo3-api/generate-veo-3-video`
- [ ] **Veo 3 1080p** — `veo3-api/get-veo-3-1080-p-video`
- [ ] **Veo 3 4K** — `veo3-api/get-veo-3-4k-video`
- [ ] **Veo 3 Extend** — `veo3-api/extend-video`
- [ ] **Runway Gen** — `runway-api/generate-ai-video`
- [ ] **Runway Aleph** — `runway-api/generate-aleph-video`
- [ ] **Runway Extend** — `runway-api/extend-ai-video`

### VIDEO — utility / animate / lipsync

- [ ] **Topaz Video Upscale** — `market/topaz/video-upscale`
- [ ] **Sora Watermark Remover** — `market/sora2/sora-watermark-remover`
- [ ] **Wan 2.2 Animate Move** — `market/wan/2-2-animate-move`
- [ ] **Wan 2.2 Animate Replace** — `market/wan/2-2-animate-replace`
- [ ] **Wan 2.2 A14B Speech-to-Video Turbo** — `market/wan/2-2-a14b-speech-to-video-turbo`
- [ ] **Kling Motion Control** — `market/kling/motion-control`
- [ ] **Kling Motion Control v3** — `market/kling/motion-control-v3`
- [ ] **Kling AI Avatar Standard (lipsync)** — `market/kling/ai-avatar-standard`
- [ ] **Kling AI Avatar Pro (lipsync)** — `market/kling/ai-avatar-pro`
- [ ] **InfiniTalk from Audio (lipsync)** — `market/infinitalk/from-audio`

### MUSIC — Suno

- [ ] **Suno Generate Music** — `suno-api/generate-music`
- [ ] **Suno Extend Music** — `suno-api/extend-music`
- [ ] **Suno Cover** — `suno-api/cover-suno`
- [ ] **Suno Replace Section** — `suno-api/replace-section`
- [ ] **Suno Generate Persona** — `suno-api/generate-persona`
- [ ] **Suno Generate Mashup** — `suno-api/generate-mashup`
- [ ] **Suno Add Instrumental** — `suno-api/add-instrumental`
- [ ] **Suno Add Vocals** — `suno-api/add-vocals`
- [ ] **Suno Generate Lyrics** — `suno-api/generate-lyrics`
- [ ] **Suno Boost Style** — `suno-api/boost-music-style`
- [ ] **Suno Convert to WAV** — `suno-api/convert-to-wav`
- [ ] **Suno Separate Vocals** — `suno-api/separate-vocals`
- [ ] **Suno Generate MIDI** — `suno-api/generate-midi`
- [ ] **Suno Create Music Video** — `suno-api/create-music-video`
- [ ] **Suno Generate Sounds** — `suno-api/generate-sounds`
- [ ] **Suno Upload & Cover** — `suno-api/upload-and-cover-audio`
- [ ] **Suno Upload & Extend** — `suno-api/upload-and-extend-audio`
- [ ] **Suno Get Timestamped Lyrics** — `suno-api/get-timestamped-lyrics`

### SPEECH / AUDIO — ElevenLabs

- [ ] **ElevenLabs TTS Multilingual v2** — `market/elevenlabs/text-to-speech-multilingual-v2`
- [ ] **ElevenLabs TTS Turbo 2.5** — `market/elevenlabs/text-to-speech-turbo-2-5`
- [ ] **ElevenLabs Text-to-Dialogue v3** — `market/elevenlabs/text-to-dialogue-v3`
- [ ] **ElevenLabs Speech-to-Text** — `market/elevenlabs/speech-to-text`
- [ ] **ElevenLabs Sound Effect v2** — `market/elevenlabs/sound-effect-v2`
- [ ] **ElevenLabs Audio Isolation** — `market/elevenlabs/audio-isolation`

### LLM CHAT (excluded from Studio — listed for completeness)

- chat/gpt-5-{2,4,5}, claude/{haiku-4-5, opus-4-5, opus-4-6, sonnet-4-5, sonnet-4-6}, codex/gpt-codex, gemini/{2-5-pro, 3-pro, 3-1-pro, 2-5-flash, 3-flash, 3-flash-v1beta}

---

## Per-model details

> Schema target per model: **id, display_name, provider, modality, inputs, params (typed), output, pricing/credits, quirks**.

Common across nearly every Kie model:
- All are **async** — `POST /api/v1/jobs/createTask` returns `taskId`; poll `Get Task Details` or use `callBackUrl` webhook.
- Bearer auth: `Authorization: Bearer <KIE_API_KEY>`.
- Image refs must be **URLs** (uploaded via `/file-upload-api/*`), not raw bytes.
- Common error codes: 200, 401, 402 (no credits), 404, 408, 422, 429, 433 (sub-key), 455 (maintenance), 500, 501 (gen failed), 505 (feature off).
- Almost all support optional `callBackUrl` (URI) for completion webhook — implied for all entries below.
- Pricing rarely shown in docs — must be confirmed from the in-app credits page.

---

### IMAGE — text-to-image / edit

#### Seedream V4 — `bytedance/seedream-v4-text-to-image`
- modality: text_to_image
- inputs: `prompt` str req max 5000
- params:
  - `image_size` enum [square, square_hd, portrait_4_3, portrait_3_2, portrait_16_9, landscape_4_3, landscape_3_2, landscape_16_9, landscape_21_9] = square_hd
  - `image_resolution` enum [1K, 2K, 4K] = 1K
  - `max_images` int 1–6 = 1 *(also state count in prompt)*
  - `seed` int (opt)
  - `nsfw_checker` bool = false (false = filtering OFF)
- output: 1–6 images, URLs
- quirks: combine `image_size` (aspect) + `image_resolution` (pixels)

#### Nano Banana — `google/nano-banana`
- modality: text_to_image
- inputs: `prompt` str req max 5000
- params:
  - `output_format` enum [png, jpeg] = png
  - `image_size` enum [1:1, 9:16, 16:9, 3:4, 4:3, 3:2, 2:3, 5:4, 4:5, 21:9, auto] = 1:1
- output: 1 image

#### Nano Banana 2 — `nano-banana-2`
- modality: text_to_image + ref-conditioned (image_compose)
- inputs: `prompt` str max 20000; up to **14** ref images (jpg/png/webp, ≤30 MB each)
- params:
  - `aspect_ratio` enum [1:1, 1:4, 1:8, 2:3, 3:2, 3:4, 4:1, 4:3, 4:5, 5:4, 8:1, 9:16, 16:9, 21:9, auto] = auto
  - `resolution` enum [1K, 2K, 4K] = 1K
  - `output_format` enum [png, jpg] = jpg

#### Nano Banana Pro (I2I) — `nano-banana-pro`
- modality: text_to_image, image_edit, image_compose
- inputs: `prompt` str max 10000; up to **8** ref images (jpg/png/webp, ≤30 MB)
- params:
  - `aspect_ratio` enum [1:1, 2:3, 3:2, 3:4, 4:3, 4:5, 5:4, 9:16, 16:9, 21:9, auto] = 1:1
  - `resolution` enum [1K, 2K, 4K] = 1K
  - `output_format` enum [png, jpg] = png

#### Flux 2 Pro T2I — `flux-2/pro-text-to-image`
- modality: text_to_image
- inputs: `prompt` str 3–5000
- params:
  - `aspect_ratio` enum [1:1, 4:3, 3:4, 16:9, 9:16, 3:2, 2:3] = 1:1
  - `resolution` enum [1K, 2K] = 1K
  - `nsfw_checker` bool = false

#### Ideogram V3 T2I — `ideogram/v3-text-to-image`
- modality: text_to_image
- inputs: `prompt` str req max 5000
- params:
  - `rendering_speed` enum [TURBO, BALANCED, QUALITY] = BALANCED
  - `style` enum [AUTO, GENERAL, REALISTIC, DESIGN] = AUTO
  - `expand_prompt` bool = false (Ideogram MagicPrompt rewriter)
  - `image_size` enum [square, square_hd, portrait_4_3, portrait_16_9, landscape_4_3, landscape_16_9] = square_hd
  - `seed` int (opt)
  - `negative_prompt` str max 5000
- quirks: cannot combine `style` with `style_codes`

#### Qwen T2I — `qwen/text-to-image`
- modality: text_to_image
- inputs: `prompt` str req max 5000
- params:
  - `image_size` enum [square, square_hd, portrait_4_3, portrait_16_9, landscape_4_3, landscape_16_9] = square_hd
  - `num_inference_steps` int 2–250 = 30
  - `guidance_scale` float 0–20 = 2.5
  - `seed` int (opt)
  - `negative_prompt` str max 500
  - `enable_safety_checker` bool = true
  - `output_format` enum [png, jpeg] = png
  - `acceleration` enum [none, regular, high] = none
  - `nsfw_checker` bool = false

#### GPT Image 2 T2I — `gpt-image-2-text-to-image`
- modality: text_to_image
- inputs: `prompt` str req max 20000
- params:
  - `aspect_ratio` enum [auto, 1:1, 9:16, 16:9, 4:3, 3:4] = auto
  - `resolution` enum [1K, 2K, 4K] (no default)
- quirks: 1:1 cannot go to 4K; `auto` aspect → 1K only

---

### VIDEO — text-to-video / image-to-video

#### Kling 2.5 Turbo Pro T2V — `kling/v2-5-turbo-text-to-video-pro`
- modality: text_to_video
- inputs: `prompt` str max 2500; `negative_prompt` str max 2500
- params:
  - `duration` enum ['5','10'] = '5' (seconds)
  - `aspect_ratio` enum [16:9, 9:16, 1:1] = 16:9
  - `cfg_scale` float 0–1 step 0.1 = 0.5

#### Seedance 2.0 — `bytedance/seedance-2`
- modality: text_to_video, image_to_video, frames_to_video, image_compose_to_video, multimodal_ref_to_video
- inputs:
  - `prompt` str 3–20000 req
  - `first_frame` URL or `asset://<id>` (opt)
  - `last_frame` URL or `asset://<id>` (opt)
  - up to **9 ref images** (jpg/png/webp/bmp/tiff/gif, AR 0.4–2.5, 300–6000 px, ≤30 MB)
  - up to **3 ref videos** (mp4/mov, 480–720p, 2–15 s each, 15 s total, 24–60 fps, ≤50 MB)
  - up to **3 ref audio** (wav/mp3, 2–15 s each, 15 s total, ≤15 MB)
- params:
  - `resolution` enum [480p, 720p, 1080p] = 720p
  - `aspect_ratio` enum [1:1, 4:3, 3:4, 16:9, 9:16, 21:9, adaptive] = 16:9
  - `duration` int 4–15 = 5
  - `generate_audio` bool = true (extra cost)
  - `web_search` bool
  - `nsfw_checker` bool = false
- quirks: I2V (first), Frames (first+last), Multimodal-R2V are **mutually exclusive**

#### Hailuo 2.3 Pro I2V — `hailuo/2-3-image-to-video-pro`
- modality: image_to_video
- inputs: `prompt` str max 5000 req; `image_url` req (jpg/png/webp ≤10 MB)
- params:
  - `duration` enum ['6','10'] = '6' (10s unavailable at 1080P)
  - `resolution` enum [768P, 1080P] = 768P
  - `nsfw_checker` bool = false

#### Sora 2 Pro T2V — `sora-2-pro-text-to-video`
- modality: text_to_video
- inputs: `prompt` str max 10000 req; up to **5 character ids** (opt)
- params:
  - `aspect_ratio` enum [portrait, landscape] = landscape
  - `n_frames` enum ['10','15'] = '10'
  - `size` enum [standard, high] = high
  - `remove_watermark` bool = false
  - `upload_method` enum [s3, oss] = s3

#### Wan 2.7 T2V — `wan/2-7-text-to-video`
- modality: text_to_video
- inputs: `prompt` str 1–5000 req; `negative_prompt` str ≤500; `audio_url` URI (opt — custom audio track)
- params:
  - `resolution` enum [720p, 1080p] = 1080p
  - `ratio` enum [16:9, 9:16, 1:1, 4:3, 3:4] = 16:9
  - `duration` int 2–15 sec = 5
  - `prompt_extend` bool = true (intelligent prompt rewrite)
  - `watermark` bool = false
  - `seed` int 0–2147483647
  - `nsfw_checker` bool = false

#### Veo 3.x family (Kie wrapper) — `veo3` / `veo3_fast` / `veo3_lite`
- modality: text_to_video, image_to_video, frames_to_video, ref_to_video
- inputs: `prompt` str req; 1–3 image URLs (single ref / first+last frames / material ref)
- params:
  - `model` enum [veo3, veo3_fast, veo3_lite] = veo3_fast
  - `generationType` enum [TEXT_2_VIDEO, FIRST_AND_LAST_FRAMES_2_VIDEO, REFERENCE_2_VIDEO] (auto-detected)
  - `aspect_ratio` enum [16:9, 9:16, Auto] = 16:9
  - `resolution` enum [720p, 1080p, 4k] = 720p (4K ~2× credits)
  - `watermark` str (opt — text overlay)
  - `enableTranslation` bool = true
- quirks: `REFERENCE_2_VIDEO` requires `veo3_fast`; pricing ~25% of Google official

#### Kling AI Avatar Pro — `kling/ai-avatar-pro`
- modality: lipsync (talking-avatar from image+audio)
- inputs:
  - `image_url` req (jpg/png/webp ≤10 MB)
  - `audio_url` req (mp3/wav/aac/mp4/ogg ≤10 MB)
  - `prompt` str ≤5000 (instruction)

#### Runway Aleph — `runway-aleph`
- modality: video_to_video (transformation with text guidance)
- inputs: `prompt` str ≤2048 req; `videoUrl` req; `referenceImage` URI (opt — style/content); `waterMark` str (opt)
- params:
  - `aspectRatio` enum [16:9, 9:16, 4:3, 3:4, 1:1, 21:9]
  - `seed` int
  - `uploadCn` bool = false (R2 vs OSS upload destination)
- output: video_url + cover image_url; URLs **valid 14 days**

---

### IMAGE — utilities

#### Topaz Image Upscale — `topaz/image-upscale`
- modality: image_upscale
- inputs: `image_url` req (jpg/png/webp ≤10 MB)
- params: `upscale_factor` enum ['1','2','4','8'] = '2'

#### Recraft Remove Background — `recraft/remove-background`
- modality: background_remove
- inputs: `image` req (png/jpg/webp ≤5 MB, ≤16 MP, dim 256–4096 px)
- params: (no extras beyond model + callback)

#### Recraft Crisp Upscale — `recraft/crisp-upscale`
- modality: image_upscale
- inputs: `image` req (jpg/png/webp ≤10 MB)
- params: (no extras)

---

### VIDEO — animate / lipsync / talking-head / character

#### Wan 2.2 Animate Replace — `wan/2-2-animate-replace`
- modality: video_animate (character swap on source video)
- inputs: source video (mp4/mov/mkv ≤10 MB) + character image (jpg/png/webp ≤10 MB)
- params:
  - `resolution` enum [480p, 580p, 720p] = 480p
  - `nsfw_checker` bool = false
- quirks: input image resized + center-cropped if AR mismatch

#### Wan 2.2 A14B Speech-to-Video Turbo — `wan/2-2-a14b-speech-to-video-turbo`
- modality: speech_to_video (talking-portrait from image + audio)
- inputs: `prompt` ≤5000; image (jpg/png/webp ≤10 MB); audio (mp3/wav/ogg/m4a/flac/aac ≤10 MB)
- params:
  - `num_frames` int 40–120 step 4 = 80
  - `frames_per_second` int 4–60 = 16
  - `resolution` enum [480p, 580p, 720p] = 480p
  - `negative_prompt` str ≤500
  - `seed` int
  - `num_inference_steps` int 2–40 = 27
  - `guidance_scale` float 1–10 = 3.5
  - `shift` float 1–10 = 5
  - `nsfw_checker` bool = false

#### InfiniTalk from Audio — `infinitalk/from-audio`
- modality: lipsync (image + audio → talking head)
- inputs: image (jpg/png/webp ≤10 MB); audio (mp3/wav/aac/mp4/ogg ≤10 MB); `prompt` ≤5000
- params:
  - `resolution` enum [480p, 720p] = 480p
  - `seed` int 10000–1000000

#### HappyHorse Reference-to-Video — `happyhorse/reference-to-video`
- modality: reference_to_video (multi-character)
- inputs: `prompt` ≤5000 EN/2500 ZH; **1–9 ref images** (jpg/png/webp, ≥400 px shortest side, ≤10 MB each)
- params:
  - `resolution` enum [720p, 1080p] = 1080p
  - `aspect_ratio` enum [16:9, 9:16, 1:1, 4:3, 3:4] = 16:9
  - `duration` int 3–15 sec = 5
  - `seed` int 0–2147483647
- quirks: image **order = character1, character2…** in prompt

#### Sora 2 Characters Pro — `sora-2-characters-pro`
- modality: character_extract_to_video (creates a reusable character_id from a slice of an existing Sora video)
- inputs:
  - `origin_task_id` req (must reference completed Sora 2 video task)
  - `timestamps` str req — `"x,y"` format, **1–4 sec window** within original video
  - `character_prompt` req
  - `character_user_name` opt (≤40 chars)
  - `safety_instruction` opt
- output: `character_id` (use as ref in subsequent Sora 2 calls)

---

### MUSIC — Suno

#### Suno Generate Music — `POST /api/v1/generate`
- modality: text_to_music + lyrics_to_song
- inputs:
  - `prompt` str req
  - `style` str (conditional on customMode)
  - `title` str (conditional)
- params:
  - `model` enum [V4, V4_5, V4_5PLUS, V4_5ALL, V5, V5_5]
  - `customMode` bool — if true, must supply lyrics+style+title
  - `instrumental` bool — true = no vocals
  - `vocalGender` enum [m, f] — probabilistic, not guaranteed
  - `styleWeight` float 0–1 step 0.01
  - `weirdnessConstraint` float 0–1 step 0.01
  - `audioWeight` float 0–1 step 0.01
  - `negativeTags` str (free text, exclude)
  - `personaId` str (link to a generated persona)
  - `callBackUrl` URI **REQUIRED**
- char limits per model:
  - V4: prompt 3000, style 200, title 80
  - V4_5+: prompt 5000, style 1000, title 80
  - non-customMode: prompt 500 max
- output: multiple audio variations; **retained 14 days**
- quirks: callback fires staged: `text` → `first` → `complete`

#### Suno Generate Persona — `POST /api/v1/persona/generate`
- modality: voice_persona (creates reusable vocal persona from a generated track)
- inputs:
  - `taskId` req (from prior Suno gen)
  - `audioId` req
  - `name` req
  - `description` req
- params:
  - `vocalStart` float (sec, default 0)
  - `vocalEnd` float (sec, default 30) — window must be **10–30 s**
  - `style` str (opt — supplemental style tag)
- output: `personaId` (use in subsequent generate / extend / cover calls)
- quirks: requires v3.5+ source track; **each audioId can generate one persona only**

#### Suno Cover (Music Cover Image) — `POST /api/v1/suno/cover/generate`
- modality: cover_art_for_music_track
- inputs: `taskId` req; `callBackUrl` req
- output: 2 cover image URLs (typically 2 styles), 14-day retention
- quirks: 1 cover per task; duplicate request returns existing taskId

#### Suno Create Music Video — `POST /api/v1/mp4/generate`
- modality: music_to_video (audio visualization)
- inputs: `taskId` req; `audioId` req; `callBackUrl` req
- params:
  - `author` str ≤50 (attribution)
  - `domainName` str ≤50 (watermark)
- output: `video_url` (mp4), 14-day retention

---

### SPEECH / AUDIO — ElevenLabs

#### TTS Multilingual v2 — `elevenlabs/text-to-speech-multilingual-v2`
- modality: text_to_speech
- inputs: `text` req max 5000
- params:
  - `voice` str (80+ preset names or custom voice_ids), default Rachel
  - `stability` float 0–1 = 0.5
  - `similarity_boost` float 0–1 = 0.75
  - `style` float 0–1 = 0
  - `speed` float 0.7–1.2 = 1.0
  - `timestamps` bool = false
  - `previous_text` str ≤5000 (continuity context)
  - `next_text` str ≤5000
  - `language_code` ISO 639-1 (opt)

#### Text-to-Dialogue v3 — `elevenlabs/text-to-dialogue-v3`
- modality: multi_speaker_tts (dialogue)
- inputs: `dialogue[]` array of `{text, voice}` turns; **combined ≤5000 chars total**
- voice library: 60+ presets + custom voice_ids
- params:
  - `stability` enum [0.0, 0.5, 1.0] = 0.5
  - `language_code` opt (60+ languages)

#### Sound Effect v2 — `elevenlabs/sound-effect-v2`
- modality: text_to_sfx
- inputs: `text` ≤5000 (description)
- params:
  - `duration_seconds` float 0.5–22 step 0.1 (None = auto from prompt)
  - `prompt_influence` float 0–1 step 0.01 = 0.3
  - `loop` bool — smooth looping
  - `output_format` enum [mp3_44100_128 (default), various PCM/ulaw/alaw/Opus]

#### Speech-to-Text — `elevenlabs/speech-to-text`
- modality: transcription
- inputs: audio URL (mp3/wav/aac/ogg ≤200 MB)
- params:
  - `language_code` str ≤500
  - `tag_audio_events` bool (laugh/applause tags)
  - `diarize` bool (speaker annotation)

---

### Variants (inferred from family patterns — confirm individually before launch)

Within each family, sibling models share the same param shape with these documented deltas:

**Image — Seedream**: `seedream-v4-edit` adds `image_input` (1+ refs); `4-5-text-to-image` and `4-5-edit` likely same shape; `5-lite-text-to-image`/`5-lite-image-to-image` lower-tier variants of same shape.

**Image — Google**: `nano-banana-edit` = nano-banana + `image_input` (refs); `imagen4`/`imagen4-fast`/`imagen4-ultra` = thin Kie wrappers around Google Imagen 4 family (params per Google research doc § 2; ultra forces n=1).

**Image — Flux 2**: `pro-image-to-image` = pro-text-to-image + `image_input`; `flex-text-to-image`/`flex-image-to-image` = cheaper Flex tier with same shape.

**Image — Ideogram**: `v3-edit` = v3-t2i + image+mask; `v3-remix` = v3-t2i + ref image (style transfer); `v3-reframe` = aspect change of existing image; `character`/`character-edit`/`character-remix` add character reference image(s) via `character_reference_image`.

**Image — Qwen**: `image-to-image`/`image-edit` = t2i + `image_input`; Qwen 2 variants likely same shape with new model id.

**Image — GPT**: `gpt-image-2-image-to-image` = t2i + `image_input` (1+); `gpt-image/1-5-text-to-image`/`1-5-image-to-image` are legacy with same shape.

**Image — Grok Imagine**: `text-to-image` and `image-to-image` likely match Flux pattern; xAI-branded.

**Image — Wan**: `2-7-image` and `2-7-image-pro` are image generation variants of the Wan 2.7 family.

**Video — Kling**: `text-to-video`/`image-to-video` are routing aliases; specific versioned endpoints follow `cfg_scale`+`duration`+`aspect_ratio` shape with version-specific quality. `motion-control`/`motion-control-v3` add a motion-reference video input. `ai-avatar-standard` = lower-tier of `ai-avatar-pro`.

**Video — Seedance**: `seedance-2-fast`/`seedance-1-5-pro`/`v1-pro-*`/`v1-lite-*` are tiered variants of seedance-2 with same param family.

**Video — Hailuo**: `02-*` and `2-3-image-to-video-standard` are quality tiers of `2-3-image-to-video-pro`.

**Video — Sora 2**: `sora-2-text-to-video`/`sora-2-image-to-video` are non-pro tiers; `sora-2-pro-image-to-video` = pro+i2v; `sora-watermark-remover` removes watermark from a Sora task; `sora-2-pro-storyboard` accepts a multi-shot storyboard structure; `sora-2-characters` = non-pro of `characters-pro`.

**Video — Wan**: `2-2-a14b-text-to-video-turbo`/`-image-to-video-turbo` mirror the `speech-to-video-turbo` shape minus the audio input. `2-2-animate-move` = motion transfer (uses motion video instead of character image). `2-5-*`/`2-6-*`/`2-7-*` are version progressions; `2-6-flash-*` are speed variants; `2-7-r2v` = reference-to-video; `2-7-videoedit` = video-to-video edit.

**Video — Happyhorse**: `text-to-video`/`image-to-video`/`video-edit` mirror the R2V shape minus reference inputs.

**Video — Runway**: `generate-ai-video` = Gen-3/Gen-4 family (`prompt`, image input, duration, aspectRatio). `extend-ai-video` extends an existing Runway task by N seconds.

**Video — Veo 3**: `extend-video` extends a prior Veo task; 1080p/4k retrieval endpoints fetch upscaled variants of completed tasks.

**Video utility — Topaz Video Upscale, Sora Watermark Remover**: same input pattern as image utilities + `target_resolution`.

**Music — Suno extras**: `extend-music`, `replace-section`, `add-instrumental`, `add-vocals`, `boost-music-style`, `cover-suno`, `generate-mashup`, `convert-to-wav`, `separate-vocals`, `generate-midi`, `generate-lyrics`, `generate-sounds`, `upload-and-cover-audio`, `upload-and-extend-audio` — each takes a prior `taskId` + operation-specific params (see suno-api index for individual schemas).

**Speech — ElevenLabs extras**: `text-to-speech-turbo-2-5` = lower-latency TTS sibling of multilingual-v2 (same param shape, model_id differs). `audio-isolation` = noise/music removal from input audio (input: audio URL).






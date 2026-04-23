# Changelog: Kie Studio Integration + Higgsfield Theme

**Date:** 2026-03-09
**Scope:** Full-stack integration of Kie.ai multi-model API + app-wide visual redesign

---

## Summary

Added a new **"Kie Studio" tab** that provides access to 14 AI models (6 video, 8 image) through the Kie.ai unified API. The entire app also received a Higgsfield.ai-inspired visual overhaul with glassmorphism and neon accents. All existing Gemini functionality remains completely untouched.

---

## New Files

### `execution/kie_client.py` (~350 lines)

Complete Kie.ai API client module, fully separate from `gemini_client.py`.

- **`KIE_MODELS` registry** — 14 models with metadata: model IDs, types (image/video), supported modes (T2I/I2I/T2V/I2V), available parameters (durations, resolutions, aspect ratios, audio), pricing per configuration, and per-model parameter quirks.
- **`_build_task_payload()`** — Normalizes per-model API quirks:
  - Hailuo: `image_url` (singular string, not array)
  - Flux I2I: `input_urls` instead of `image_urls`
  - Nano Banana: `image_input` instead of `image_urls`
  - Sora 2: converts duration to `n_frames` (duration × 24fps)
  - Seedream: `quality` (basic/high) instead of `resolution`
  - Hailuo constraint: raises ValueError for 10s @ 1080P (unsupported)
- **Core functions:** `_kie_request()`, `check_credits()`, `upload_image_url()`, `create_task()`, `poll_task()`, `get_models_info()`, `download_result()`
- Uses only Python stdlib (`urllib.request`, `json`, `time`, `os`, `tempfile`) — no new pip dependencies.

---

## Modified Files

### `execution/server.py`

**Import:** Added Kie client functions (aliased to avoid naming collisions with existing Gemini functions).

**`require_auth` update:** Now also extracts `kie_api_key` from the same Firestore user document read:
```python
stored_kie_key = user_data.get('kie_api_key')
g.kie_api_key = decrypt_api_key(stored_kie_key) if stored_kie_key else None
```

**7 new routes** under `# KIE.AI INTEGRATION`:

| Route | Method | Rate Limit | Purpose |
|-------|--------|------------|---------|
| `/api/kie/save-api-key` | POST | 200/hr | Save Kie key (Fernet encrypted → Firestore) |
| `/api/kie/check-api-key` | GET | 200/hr | Check if Kie key exists |
| `/api/kie/check-credits` | GET | 60/hr | Get remaining credits balance |
| `/api/kie/models` | GET | 200/hr | Return model registry with pricing |
| `/api/kie/upload-image` | POST | 120/hr | Upload image URL to Kie.ai for I2V/I2I |
| `/api/kie/generate` | POST | 120/hr | Create generation task |
| `/api/kie/poll/<task_id>` | GET | 600/hr | Poll task; on success downloads result → uploads to Firebase Storage |

**Download-and-persist pattern:** Kie.ai result URLs expire in 24 hours. The poll endpoint downloads completed results immediately and re-uploads to Firebase Storage (`kie_images/` or `kie_videos/`) for permanent access. Reuses existing `upload_to_storage()` function.

**Security:** SSRF validation on image upload endpoint (only allows Firebase Storage and data URIs).

---

### `ui/style.css`

**CSS Variables updated** — Higgsfield-inspired dark glassmorphic palette:
- `--bg-color: #08080a`, `--card-bg: rgba(22, 22, 30, 0.75)`
- New accent colors: `--accent-cyan: #00e5ff`, `--accent-neon-green: #b8ff57`
- New utilities: `--glass-blur: 16px`, `--border-hover: rgba(255,255,255,0.15)`

**App-wide glassmorphism** applied to:
- `body` → gradient background
- `.sidebar` → backdrop-filter blur + semi-transparent bg
- `.tab-bar` → glass effect
- `.input-group` → glass effect
- `.project-item` borders → CSS variable instead of hardcoded `#333`

**New component styles (~400 lines):**
- `.glass-panel` utility class
- `.api-key-tabs` / `.api-key-tab` — dual settings tabs
- `.btn-generate-neon` — neon green gradient button with glow and 3D press effect
- `.kie-sub-tabs` — glassmorphic sub-navigation with cyan active state
- `.kie-model-grid` / `.kie-model-card` — responsive grid, hover lift, cyan selection border
- `.kie-cap-badge` / `.kie-price-badge` — capability and pricing badges
- `.kie-params-panel` — dynamic parameter controls
- `.kie-prompt-area` / `.kie-upload-zone` — prompt input and file upload
- `.kie-visuals-picker` — scrollable thumbnail grid for picking from Visuals tab
- `.kie-gallery` / `.kie-gallery-item` — results gallery with hover overlay
- `.kie-progress-bar` — cyan-to-green gradient progress fill
- `@keyframes pulseGlow` — oscillating glow animation for generating state
- Responsive breakpoints for all Kie components

---

### `ui/index.html`

**Settings Modal — Dual API Key Tabs:**
- Replaced single Gemini key input with tabbed interface
- Tab 1: "Gemini API Key" (existing flow, unchanged)
- Tab 2: "Kie.ai API Key" — password input, save to `/api/kie/save-api-key`, credits display
- New JS: `switchApiKeyTab()`, `saveKieApiKey()`, `checkKieCredits()`

**Tab Bar:**
- Added 5th tab: "Kie Studio" with stacked-layers SVG icon

**Kie Studio Tab HTML:**
```
Kie Studio Tab
├── Sub-tabs bar: [Images] [Videos] + Credits badge
├── No API key message (shown when key not configured)
├── IMAGE Sub-tab
│   ├── Model Selection Grid (cards with provider, pricing, capability tags)
│   ├── Dynamic Parameters Panel (resolution/quality/aspect ratio — per model)
│   ├── Prompt Input Area
│   │   ├── Textarea
│   │   ├── Image Input (for I2I models)
│   │   │   ├── Source toggle: [Upload New] [Pick from Visuals]
│   │   │   ├── File upload zone / Visuals thumbnail picker
│   │   │   └── Selected image preview
│   │   ├── Cost badge (auto-calculated)
│   │   └── Generate button (neon green)
│   └── Results Gallery
├── VIDEO Sub-tab (same structure + progress bar)
└── Error display
```

**Kie Studio JavaScript (~400 lines):**

| Function | Purpose |
|----------|---------|
| `initKieStudio()` | Fetch models, render cards, check credits |
| `switchKieSubTab()` | Toggle Images/Videos |
| `renderKieModelCards()` | Build model card grid with pricing and capabilities |
| `selectKieModel()` | Highlight card, show params, show/hide image input |
| `renderKieParamControls()` | Dynamic controls per model (duration, resolution, quality, audio, aspect ratio) |
| `updateKieCostBadge()` | Calculate estimated cost from model + params |
| `populateKieVisualsPicker()` | Read existing `visualsScenes` global, show thumbnails |
| `kieGenerate()` | Validate, upload image if needed, POST generate, start polling |
| `kieStartPolling()` | Poll every 3s, update progress, add to gallery on complete |
| `addToKieGallery()` | Create gallery items (img/video) with Open/Download actions |
| `restoreKieGallery()` | Restore gallery from saved project state |
| `clearKieGalleries()` | Reset galleries for new project |

**Auth flow:** Non-blocking Kie key check on login (alongside existing Gemini key check).

**Persistence:** `gatherProjectState()` now includes `kie_generations` array; `restoreProjectState()` restores gallery from saved URLs. `clearAppForNewProject()` clears Kie state.

---

## Models Supported

### Video Models (6)

| Model | Modes | Duration | Resolution | Audio | Price Range |
|-------|-------|----------|------------|-------|-------------|
| Kling 3.0 | T2V, I2V | 3-15s | 720p, 1080p | Yes | $0.30–$3.00 |
| Kling 2.6 | I2V | 5s, 10s | 720p | Yes | $0.28–$1.10 |
| Sora 2 | I2V | 10s, 15s | 1080p | No | $0.15–$0.175 |
| Grok Imagine | I2V | 6s, 10s, 15s | 480p, 720p | No | $0.05–$0.20 |
| Wan 2.6 | I2V | 5s, 10s, 15s | 720p, 1080p | No | $0.35–$1.58 |
| Hailuo 2.3 Pro | I2V | 6s, 10s | 768P, 1080P | No | $0.22–$0.45 |

### Image Models (8)

| Model | Modes | Resolution/Quality | Price Range |
|-------|-------|--------------------|-------------|
| Nano Banana 2 | T2I (+refs) | 1K, 2K, 4K | $0.04–$0.09 |
| Nano Banana Pro | T2I, I2I | 1K-2K, 4K | $0.09–$0.12 |
| Seedream 5.0 Lite T2I | T2I | basic, high | $0.028 |
| Seedream 5.0 Lite I2I | I2I | basic, high | $0.028 |
| Flux 2 Pro T2I | T2I | 1K, 2K | $0.025–$0.035 |
| Flux 2 Pro I2I | I2I | 1K, 2K | $0.025–$0.035 |
| Grok Imagine T2I | T2I | — | $0.02 |
| Grok Imagine I2I | I2I | — | $0.02 |

---

## Architecture Decisions

1. **Separate module** — `kie_client.py` is completely independent from `gemini_client.py`. Zero risk of breaking existing Gemini functionality.
2. **Same encryption** — Reuses existing Fernet instance. Kie key stored as `kie_api_key` field on the same Firestore user doc.
3. **Download-and-persist** — Kie URLs expire in 24h. Poll endpoint downloads → uploads to Firebase Storage (permanent). Same pattern as existing Veo video handling.
4. **Shared Visuals** — Kie Studio reads the existing `visualsScenes` global array to let users pick previously generated images as input for I2V/I2I.
5. **CSS variable compatibility** — New colors added as new variables. Existing `--accent-color` stays purple. All existing components keep working.
6. **No new dependencies** — `kie_client.py` uses only Python stdlib.

---

## Testing

- **Python syntax:** Both `kie_client.py` and `server.py` pass AST parse
- **Module import:** All 14 models registered, all API functions importable
- **Test suite:** 7/7 existing tests pass (1 pre-existing Playwright fixture error, unrelated)
- **JS functions:** All 12 Kie JS functions confirmed present in HTML

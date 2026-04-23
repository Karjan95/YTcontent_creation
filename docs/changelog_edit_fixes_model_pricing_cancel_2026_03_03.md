# Changelog: Edit Fixes, Nano Banana 2, Dynamic Pricing, Smart Batch Generation — 2026-03-03

## Summary

Four changes in this session:
1. **Fixed image editing bugs** — two bugs that caused 500 errors when using the lightbox image editor on Cloud Run
2. **Added Gemini 3.1 Flash (Nano Banana 2) model** — new fast/cheap image model added to all selectors
3. **Resolution-aware dynamic pricing** — cost badges now update based on selected resolution
4. **Smart batch generation + cancel** — "Generate All" skips scenes that already have images, and a cancel button stops in-flight batches

---

## 1. Image Editing Bug Fixes

### Problem 1: `_get_client` not defined
The `edit_scene_image()` function in `gemini_client.py` called `_get_client(api_key)` but the actual function name is `get_client(api_key)` (no underscore prefix). This caused a 500 error on every edit attempt.

### Fix
**File:** `execution/gemini_client.py` (line ~1085)
- Changed `_get_client(api_key)` → `get_client(api_key)`

### Problem 2: `No such file or directory: generated_images/`
On Cloud Run, the filesystem starts empty. `edit_scene_image()` tried to save the edited image to `generated_images/` without creating the directory first. `generate_scene_image()` had `os.makedirs()` but `edit_scene_image()` was missing it.

### Fix
**File:** `execution/gemini_client.py` (line ~1086)
- Added `os.makedirs(os.path.join(os.path.dirname(__file__), '..', 'generated_images'), exist_ok=True)` at the start of the function, matching the pattern in `generate_scene_image()`.

---

## 2. Gemini 3.1 Flash Image Model (Nano Banana 2)

### Feature
Added `gemini-3.1-flash-image-preview` (Nano Banana 2) — Google's high-efficiency image model optimized for speed and cost. Supports both text-to-image generation and image-to-image editing.

### Pricing comparison
| Model | 1K | 2K | 4K |
|-------|-----|-----|-----|
| Gemini 3 Pro | $0.13 | $0.13 | $0.24 |
| **Gemini 3.1 Flash (new)** | **$0.07** | **$0.10** | **$0.15** |
| Gemini 2.5 Flash | $0.04 | $0.04 | $0.04 |

### Files changed

**`ui/index.html`** — Added to all 5 model selectors:
1. **Lightbox editor** model dropdown (~line 88) — also removed Imagen options from editor since Imagen doesn't support image-to-image editing
2. **Simple image generator** dropdown (~line 181)
3. **Visuals tab global model** selector (~line 349) with pricing label
4. **PRICING object** (~line 1685) for cost calculations
5. **Per-scene model override** dropdown (~line 4353)

### No backend changes needed
The model ID starts with `gemini-` so it automatically routes through the existing Gemini generation path in `gemini_client.py` (line ~171: `if model_name.startswith("imagen-")` handles the routing).

---

## 3. Resolution-Aware Dynamic Pricing

### Problem
All cost badges and dropdown labels showed a single flat price per model, regardless of the selected resolution. In reality, some models (especially Gemini 3 Pro and 3.1 Flash) charge significantly more for higher resolutions (e.g. 4K costs ~2x more than 1K for Gemini 3 Pro).

### Fix

**`ui/index.html`** — Restructured pricing and added dynamic updates:

1. **PRICING object restructured** from flat `{ cost, label }` to resolution-keyed:
   ```javascript
   // Before
   'gemini-3-pro-image-preview': { cost: 0.134, label: '~$0.13 / image' }
   // After
   'gemini-3-pro-image-preview': { '1K': 0.134, '2K': 0.134, '4K': 0.24 }
   ```

2. **Video pricing also resolution-aware**:
   ```javascript
   'veo-3.1-generate-preview': { '720p': 0.40, '1080p': 0.40, '4K': 0.60 }
   ```

3. **New helper functions**:
   - `getImageCost(model, resolution)` — looks up per-image cost
   - `getVideoCostPerSec(model, resolution)` — looks up per-second video cost
   - `updateModelPriceLabels()` — dynamically rewrites the visuals model dropdown option labels with correct prices for the current resolution

4. **Dynamic update chain**: When user changes the resolution dropdown:
   `visResolution onchange` → `updateVisualsConfig()` → `updateModelPriceLabels()` + `updateBatchCostBadges()`

5. **Called on project restore**: `updateModelPriceLabels()` and `updateBatchCostBadges()` are now called when a project is loaded from Firestore (in the config restore block ~line 6360) and when visuals are initialized from a production table.

### Full pricing table

**Image models:**
| Model | 1K | 2K | 4K |
|-------|-----|-----|-----|
| Gemini 3 Pro | $0.134 | $0.134 | $0.240 |
| Gemini 3.1 Flash | $0.067 | $0.101 | $0.151 |
| Gemini 2.5 Flash | $0.039 | $0.039 | $0.039 |
| Imagen 4 Standard | $0.04 | $0.04 | $0.04 |
| Imagen 4 Fast | $0.02 | $0.02 | $0.02 |
| Imagen 4 Ultra | $0.06 | $0.06 | $0.06 |

**Video models:**
| Model | 720p/1080p | 4K |
|-------|------------|-----|
| Veo 3.1 | $0.40/s | $0.60/s |
| Veo 3.1 Fast | $0.15/s | $0.35/s |

---

## 4. Smart Batch Generation + Cancel

### Problem 1: "Generate All" regenerates everything
When a user comes back to a project with 5/20 images already done and clicks "Generate All Images", it would start from Scene 1 again — wasting time and money regenerating images that already exist.

### Problem 2: No way to cancel
Once "Generate All Images" is clicked, there's no way to stop it. If a user accidentally starts batch generation or wants to change settings mid-batch, they're stuck waiting for all scenes to finish.

### Fix

**`ui/index.html`** — Smart skip + cancel button:

1. **New `updateGenerateAllBtnText()` function**: Updates the button text and `visualsGenerationPhase` based on current scene state:
   - 0 images done → "Generate All Images" (phase: `idle`)
   - Some done → "Generate Remaining N Images" (phase: `preview`)
   - All done → "All Images Generated" (phase: `batch`)

2. **Called on project load**: `updateGenerateAllBtnText()` runs when visuals are initialized from a production table, so the button immediately shows the correct remaining count.

3. **Called after individual scene generation**: When a user manually generates or regenerates a single scene, the button text updates to reflect the new remaining count.

4. **Phase 1 (preview) now skips completed scenes**: Instead of always generating Scene 1, it finds the first scene without an image and generates that one for review.

5. **Cancel button**: During batch generation (Phase 2), the "Generate All" button transforms:
   - **Appearance**: Turns red (`btn-cancel` CSS class) with gradient `#dc2626 → #ef4444`
   - **Text**: Shows live progress: "Cancel Generation (3/15)"
   - **Click behavior**: Sets `_batchCancelled = true`, which causes workers to stop pulling from the queue
   - **After cancel**: Completed images are kept. Button reverts to purple "Generate Remaining X Images"

6. **Helper functions**:
   - `_setBtnGenerating(btn, text)` — switches button to cancel mode (red, onclick → `cancelBatchGeneration`)
   - `_setBtnNormal(btn, text)` — restores button to normal mode (purple, onclick → `generateAllImages`)
   - `cancelBatchGeneration()` — sets the cancel flag and shows "Cancelling..."

**`ui/style.css`** — New cancel button styles:
```css
.btn-cancel { background: linear-gradient(135deg, #dc2626, #ef4444); }
.btn-cancel:hover { background: linear-gradient(135deg, #b91c1c, #dc2626); }
```

### User flow examples

**Returning to a project with 5/20 images:**
1. Project loads → button shows "Generate Remaining 15 Images"
2. User clicks → Phase 1 generates first incomplete scene for review
3. User clicks again → Phase 2 starts batch for remaining 14 scenes
4. Button turns red: "Cancel Generation (0/14)"
5. After 8 finish, user clicks cancel → "Cancelling..." → "Generate Remaining 6 Images"
6. User makes changes, clicks again → generates final 6

**Accidental click:**
1. User clicks "Generate All" by mistake
2. Button immediately shows "Cancel Generation (0/15)"
3. User clicks cancel before any complete → "Generate Remaining 15 Images"
4. No images were changed

---

## File Change Summary

| File | Changes |
|------|---------|
| `execution/gemini_client.py` | Fixed `_get_client` → `get_client`, added `os.makedirs` for `generated_images/` |
| `ui/index.html` | Added Gemini 3.1 Flash to all 5 model selectors, restructured PRICING to resolution-keyed, added `getImageCost()`/`getVideoCostPerSec()`/`updateModelPriceLabels()`, smart batch skip + cancel button with `updateGenerateAllBtnText()`/`cancelBatchGeneration()`, removed Imagen from lightbox editor |
| `ui/style.css` | Added `.btn-cancel` and `.btn-cancel:hover` styles |

# Changelog: Character Assignment, Download, Pricing, Storage Cleanup & Character Enforcement

**Date:** 2026-03-17

---

## Fix: Character-to-Shot Assignment Accuracy

**Problem:** Characters were sometimes incorrectly assigned to shots. The old logic mapped characters using beat **names** (e.g., "Hook", "Rising Action"), but these names can repeat across acts — causing characters from unrelated beats to be assigned to the wrong shots.

**Fix:** Replaced beat-name mapping with direct analysis of the production table's `character_outfit` field:
- If `character_outfit` is "N/A — no characters in shot" → no characters assigned
- Matches cast member **names** against `character_outfit` text and `first_frame_prompt`
- Falls back to matching `visual_identity` keywords if name matching fails
- Much more reliable since the Storyboard Artist (Phase 2) explicitly decides who appears in each shot

**File:** `ui/index.html` — `initVisualsFromProductionTable()`

---

## Fix: Download Now Uses Single Zip File

**Problem:** Downloading 200+ images triggered 200+ individual browser downloads via `a.click()`. Browsers throttle this, causing failures after ~200 files.

**Fix:** Download now uses the server-side zip endpoint:
- Single zip file downloaded to browser (one click)
- Zip is named after the project title (e.g., `My Video Project.zip`)
- Contains organized folders: `images/`, `videos/`, `audio/`
- Supports "Active Images Only" or "All Generated Images" mode
- Uses `ZIP_STORED` instead of `ZIP_DEFLATED` (images are already compressed — faster build)

**Files:** `ui/index.html` — `downloadAllAssets()`, `execution/server.py` — `/api/visuals/download-all`

---

## Fix: Cloud Run Memory Increased to 2GB

**Problem:** Default Cloud Run memory is 512MB. Building a zip of 260+ images (500MB–1.3GB) caused out-of-memory crashes.

**Fix:** Added `--memory 2Gi` to both deploy scripts.

**Files:** `deploy.sh`, `deploy_staging.sh`

---

## Fix: Project Delete Now Cleans Firebase Storage

**Problem:** Deleting a project only removed the Firestore document. All images, videos, audio, and reference files remained orphaned in Firebase Storage, consuming space indefinitely.

**Fix:** Project deletion now deletes all associated Storage files:
- `images/{project_id}/`
- `videos/{project_id}/`
- `audio/{project_id}/`
- `references/{project_id}/`

**Note:** Firebase Storage free tier (Spark plan) is 5 GB total. At ~1-2MB per image, that's roughly 2,500-5,000 images. Deleting projects now actually frees this space.

**File:** `execution/server.py` — `delete_project()`

---

## Improvement: Dynamic Pricing with Input Token Costs

**Problem:** Batch cost badges only showed output image cost. For Gemini models with character/style reference images, input token costs add significantly ($0.02–0.08 per image depending on model and number of references).

**Fix:** Cost estimation now includes input token costs:
- Estimates ~700 tokens per reference image
- Adds per-model input cost: Gemini 3 Pro ($2/1M tokens), Flash 3.1 ($0.50/1M), Flash 2.5 ($0.30/1M)
- Imagen models unaffected (flat pricing, no input token cost)
- Batch cost badge shows more accurate total

**Pricing reference:**

| Model | 1K | 2K | 4K | Input/1M tokens |
|-------|-----|-----|-----|-----------------|
| Gemini 3 Pro Image | $0.134 | $0.134 | $0.24 | $2.00 |
| Gemini 3.1 Flash Image | $0.067 | $0.101 | $0.151 | $0.50 |
| Gemini 2.5 Flash Image | $0.039 | $0.039 | $0.039 | $0.30 |
| Imagen 4 Standard | $0.04 | $0.04 | $0.04 | N/A (flat) |
| Imagen 4 Fast | $0.02 | $0.02 | $0.02 | N/A (flat) |
| Imagen 4 Ultra | $0.06 | $0.06 | $0.06 | N/A (flat) |

**File:** `ui/index.html` — `estimateInputCostPerImage()`, `updateBatchCostBadges()`

---

## Improvement: Character Reference Enforcement in Image Generation

**Problem:** Character references were inconsistently applied. Long scene prompts (10+ fields — environment, lighting, lens FX, aperture, DOF, texture, color palette) consumed Gemini's attention, causing it to sometimes ignore reference images.

**Root causes identified:**
1. Character enforcement was a generic "REMINDER" mixed into the scene prompt block
2. `additional_context` was labeled "ADDITIONAL STYLE NOTES" — character instructions there were deprioritized as style hints
3. The scene prompt was the last thing Gemini saw, but character enforcement was buried inside it

**Fix — 3 changes to prompt structure:**

1. **Character enforcement is now a separate final Part** — the very last thing Gemini processes (maximum recency bias). Lists each character by name and enumerates what must match (face, hair, body, skin tone, age).

2. **Enforcement is forceful** — labeled `⚠️ FINAL MANDATORY CHECK`, states "this is the HIGHEST PRIORITY instruction — it overrides all style and composition choices."

3. **`additional_context` renamed** from "ADDITIONAL STYLE NOTES" to "ADDITIONAL INSTRUCTIONS" — so user-typed instructions aren't misclassified as style suggestions.

**Prompt structure before:**
```
1. System instruction
2. Character refs + images
3. Character binding
4. Style refs + images
5. Scene prompt + "ADDITIONAL STYLE NOTES" + generic REMINDER  ← all one block
```

**Prompt structure after:**
```
1. System instruction
2. Character refs + images
3. Character binding
4. Style refs + images
5. Scene prompt + "ADDITIONAL INSTRUCTIONS"                     ← scene block
6. ⚠️ FINAL MANDATORY CHECK (character enforcement per name)   ← separate, VERY LAST
```

**File:** `execution/gemini_client.py` — `generate_scene_image()`

---

## Files Changed Summary

| File | Changes |
|------|---------|
| `execution/gemini_client.py` | Character enforcement as final prompt part, renamed additional_context label |
| `execution/server.py` | Storage cleanup on project delete, improved download-all zip endpoint |
| `ui/index.html` | Character-to-shot assignment via character_outfit, zip download, input cost estimation |
| `deploy.sh` | Added `--memory 2Gi` |
| `deploy_staging.sh` | Added `--memory 2Gi` |

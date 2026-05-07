# Changelog — Full UI/UX Redesign (2026-05-05)

A complete visual + structural redesign of the Gemini Studio frontend.
Backend logic and Firestore contracts are untouched. Every change lives in
`ui/index.html`, `ui/style.css`, and one config-only line in
`execution/server.py` (port env-var).

Direction locked with the user before implementation:

- **Theme:** dark only.
- **Palette:** monochrome with a single electric-lime accent (`#B8FF57`).
  All purple was purged in three sweeps.
- **Navigation:** left rail (Projects + Tools) + sticky topbar with a
  4-segment pipeline stepper. Pipeline is the hero; standalone tools are
  demoted.
- **Visuals/media:** cinema-tile grid for scenes (16:9 enforced via
  `aspect-ratio`).
- **Buttons:** flat solid pills, subtle hover lift (1px), no glow.
- **Icons:** Lucide SVG, single 1.5px stroke. Emojis purged from controls.

---

## Pass 1 — Foundation

### Tokens (`ui/style.css` `:root`)
Replaced legacy variables with a full design-system token set. Old variable
names kept as **aliases** of the new tokens so existing CSS keeps working
without a sweep.

| Group | New tokens |
|------|------------|
| Canvas/surfaces | `--bg`, `--bg-elev-1/2/3`, `--bg-hover`, `--bg-press` |
| Text | `--fg`, `--fg-muted`, `--fg-dim`, `--fg-inverse` |
| Borders | `--border`, `--border-strong` |
| Accent | `--accent` (#B8FF57), `--accent-hover`, `--accent-press`, `--accent-soft` |
| Semantic | `--success`, `--warning`, `--danger`, `--info` |
| Radii | `--r-xs/sm/md/lg/pill` |
| Spacing | `--s-1…--s-12` (4-pt scale) |
| Type | `--font-display` (Space Grotesk), `--font-ui` (Inter), `--font-mono` (JetBrains Mono) |
| Type scale | `--t-xs…--t-4xl` |
| Motion | `--ease-out`, `--ease-spring`, `--d-fast/base/slow` |
| Elevation | `--shadow-1`, `--shadow-2`, `--shadow-modal` |
| Z-scale | `--z-base`, `--z-sticky`, `--z-toast`, `--z-modal`, `--z-tooltip` |
| Icon sizes | `--ic-sm/md/lg/xl` |

Body became flat (gradient stripped), `prefers-reduced-motion` respected
globally, font-smoothing enabled.

### Purple purge
Hardcoded purple values found and rewritten to lime/neutral via four
mechanical sweeps:

- `#9d4edd` / `#7b2cbf` / `#7c3aed` → `#B8FF57` / `#A4E84A`
- `rgba(157, 78, 221, …)` / `(123, 44, 191, …)` / `(124, 58, 237, …)` /
  `(139, 92, 246, …)` → `rgba(184, 255, 87, …)` (preserves alpha)
- Light purple variants `#c084fc`, `#b388ff` → `#B8FF57`
- Two purple linear-gradients flattened to solid lime (one button, one
  notification banner).

Final sweep returns zero hits.

### Fonts + Lucide (`ui/index.html` `<head>`)
- Added Inter + Space Grotesk + JetBrains Mono in one preconnected
  Google Fonts call.
- Added Lucide UMD CDN and a `window.renderIcons()` helper that runs on
  `DOMContentLoaded` and after each dynamic markup injection.

### Component primitives
Rewrote, all using new tokens:

- `button:not(.tab):not(.template-card):not(.title-card):not(.mode-btn):not(.dossier-card)`
  → flat lime pill, `translateY(-1px)` hover, `translateY(0)` active,
  proper disabled styling.
- `.btn-secondary` → transparent + 1px border, hover fills with bg-hover.
- `.btn-cancel` → transparent + danger border (was a red gradient).
- `textarea` / `.style-input` / `input[type=text|email|password|number|search]`
  → unified flat surface with lime focus ring (`box-shadow: 0 0 0 3px var(--accent-soft)`).
- `select` → matching style + new SVG caret in `--fg-muted` color.
- `.cost-badge` → mono lime on accent-soft pill.
- `.modal-overlay` → 60% black + 8px backdrop blur (the **only** sanctioned
  blur), fade-in 120ms.
- `.modal-card` → flat surface, 14px radius, scale-in 220ms with `ease-out`.

### Inline `<style>` block in index.html
Refreshed all hardcoded blues/grays/yellows in the spine editor, claim
chips, AI suggestions panel, and toast notifications to use design tokens.
Toasts now have a colored 3px left bar (lime/amber/red) instead of muddy
backgrounds.

### New utility layer (appended at end of `style.css`)
Additive — every existing class continues to work.

| Utility | Purpose |
|---------|---------|
| `.ic`, `[data-lucide]` | Lucide icon sizing & display |
| `.field`, `.field-label`, `.field-help`, `.field-error`, `.is-error` | Form-field primitives |
| `.status-pip` (`.is-pending/running/done/error`) | 8px status dots, with pulse on running |
| `.badge` (`.is-accent/success/warning/danger/info`) | Pill badges |
| `.progress-bar` + `.progress-fill`, `.is-indeterminate` | Lime-fill progress |
| `.skeleton`, `.skeleton-text/line/tile/pill` | Shimmer skeletons |
| `.segmented` | Pill-segmented toggle (used everywhere) |
| `.empty-state` | Icon + title + desc + CTA empty state |
| `.card`, `.card-header/title/body/footer` | Flat card primitive |
| `.btn-sm/lg/icon/ghost/danger` | Button size + variant utilities |
| `[data-tooltip]` | CSS-only tooltip with 200ms delay |
| `*:focus-visible` | Lime ring + 4px halo, never removed |
| Custom scrollbars | Polished thumb in `--border-strong` |
| `[data-lucide="loader-2"]` | Auto-spin animation |

---

## Pass 2 — Shell

### Markup (`ui/index.html`)
Restructured the app shell. The legacy `<header>` with brand + user pills
and the `<nav class="tab-bar">` are kept in DOM (so `switchTab`'s
`querySelector('[data-tab="…"]')` still finds them) but **hidden** in
`shell-mode`.

- New **left rail** (`.sidebar`, 240px, sticky full-height):
  - `.sidebar-brand` — STUDIO wordmark + lime square dot.
  - `.sidebar-section` "Projects" with `+ New project` and the existing
    project list rerendered with new flat row look.
  - `.sidebar-section` "Tools" — Image / Voiceover / Kie Studio / Usage
    rows with Lucide icons. Click → `goToTool(name)` → `switchTab(name)`.
  - `.sidebar-footer` — avatar + Settings + Sign out icon buttons.
  - Collapses to 64px icon-only at `<1024px`.

- New **sticky topbar** (`.topbar`, 56px, `--bg-elev-1`):
  - Left: project title + autosave pip (`#topbarAutosave`).
  - Center: 4-segment **pipeline stepper** (`#pipelineStepper` — Research ·
    Script · Production · Visuals).
  - Right: Export icon button (`#topbarExportBtn`) wired to existing
    `downloadAllAssets()`, disabled until any scene has media.
  - Stepper labels collapse at `<768px`.

### JS helpers (`ui/index.html`)
All additive. **No existing handler signatures changed.**

| Function | Role |
|----------|------|
| `showPhaseCard(id)` | Toggles `display` on `#phase1Card / #phase2Card / #phase3Card` so only one is visible. ~10 lines. |
| `goToPhase(phase)` | Stepper segment routing: research/script/production → `switchTab('research')` + `showPhaseCard(...)`; visuals → `switchTab('visuals')`. |
| `goToTool(name)` | Sidebar Tools click → `switchTab(name)`. |
| `syncShellNav(tabName, phase?)` | Reflects current tab/phase into sidebar active state + stepper segment + visibility. |
| `refreshExportButton()` | Enables/disables Export based on `visualsScenes` having media. |
| `refreshStepperDoneState()` | Lights up done-state per segment from `currentDossier`, `currentNarration`, `currentProductionData`, `visualsScenes`. |
| `updateTopbarProjectTitle(title)` | Updates the topbar's project title. |
| `setAutosaveState('saving' \| 'saved' \| 'error' \| '')` | Drives the autosave pip; auto-fades after 4s. |

### Hooks into existing flows
- `showApp()` adds `body.shell-mode` and runs initial sync.
- `switchTab()` extended only at the bottom to call `syncShellNav` (and
  also lazy-load Usage when the tab opens).
- `loadProject()` calls `updateTopbarProjectTitle`, `refreshExportButton`,
  `refreshStepperDoneState`, `showPhaseCard('phase1Card')`, and
  `syncShellNav('research', 'research')`.
- `confirmNewProject()` mirrors the same.
- `doSaveProject()` and `triggerAutosave()` call `setAutosaveState`
  on enter/success/failure. The 'saved' branch also refreshes the export
  button + stepper done state.

---

## Pass 3 — Per-surface redesigns

### Image tab (the biggest functional add)
Markup completely rewritten into the new card system. New capability:

- **Mode toggle** (segmented): `Text → image` / `Image → image`.
- **Reference image attach** — drag-drop or click; preview with × to
  clear; max 8 MB; PNG/JPG/WebP. Backend stays untouched: i2i mode reuses
  `/api/visuals/edit-image` with a synthetic `scene_id` of
  `manual-${Date.now()}`.
- **Aspect ratio** segmented: 1:1 / 16:9 / 9:16 / 4:3.
- **Result actions**: Download · Use as reference (one-click recycle into
  i2i mode).
- **Recent generations** strip — 24 most recent, persisted in
  `localStorage` under `imageStudioHistory`. Click a tile → restore.
- Better loading state: "Generating…" empty-state title, descriptive
  desc per mode.

### Voiceover tab
Card layout, surface header, Lucide mic icon, voice select preserved (30+
voices), audio player gets `.audio-stage` wrapper with download as
secondary button. Empty state with `audio-lines` icon.

### Kie Studio
- Surface header with title + Credits chip in lime mono.
- Sub-tabs (Images / Videos / Midjourney) converted to segmented control;
  `switchKieSubTab` updated to set both `.active` (legacy) and
  `.is-active` (new).
- CSS overrides flatten `.glass-panel` to clean cards, restyle
  `.btn-generate-neon` to lime pill, restyle `.kie-cost-badge`,
  `.kie-upload-zone`, `.kie-progress-bar` (lime fill), Midjourney
  `.mj-mode-bar` (segmented), `.mj-slider` (lime accent).

### Usage dashboard
Restructured into proper KPI cards (`.usage-kpi-row`), 7d/30d/90d
preset segmented control, date-range card, daily-spend chart card,
side-by-side By tool / By project (`.usage-grid`), proper styled
`.usage-table` with hover, monospace numerics, semantic header.

### Phase 1 Research
- `book-open` Lucide title icon.
- Template grid → 220px+ flat cards with lime border on selected.
- Selected-template badge → lime pill.
- Buttons: `arrow-left` Back, `search` Start Research, `file-text`
  Dossier section header, `chevron-down` collapse, `git-branch` for
  Narrative Spine, `sparkles` for "Ask AI", `save` Save Spine.

### Phase 2 Script
- `pen-line` Lucide title icon.
- Mode toggle (Use Research / Paste your own) → `link` + `clipboard`
  icons.
- Title cards reformatted with display-font title + muted desc.
- Generate Narration button → primary lime with `pen-line` icon.
- Lock & continue → `lock` icon.
- Script table restyled (mono headers in muted, lime hover row).
- `.style-toggle` radio cards become pill chips with checked-state lime
  fill.

### Phase 3 Production
- `clapperboard` Lucide title icon.
- Mode toggle icons (Use Script / Paste JSON).

### Phase 4 Visuals
- Surface header.
- Section blocks (`.visuals-data-section`, `.visuals-config-section`,
  `.visuals-characters-section`) flat-carded in `--bg-elev-2`.
- Mode toggle icons (Auto-detect / Paste).
- **Cinema grid** for scenes — `.visuals-scene-list` becomes responsive
  `auto-fill, minmax(320–360px, 1fr)` grid; every scene image and video
  enforced to `aspect-ratio: 16/9` with `object-fit: cover`.
- Scene cards split into header / narration / body / footer with proper
  borders.
- **Sticky bottom action bar** — `.visuals-action-bar` becomes
  sticky with shadow; primary actions (Generate all / Animate all
  marked) become lime primaries; secondary actions get Lucide icons
  (`refresh-cw`, `download`).

### Phase cards (shared shell)
- `.phase-header` → flat 32px lime numbered disc + display title + muted
  subtitle + status pill.
- `.phase-status` variants (`running`, `complete`, `success`, `error`)
  rendered in semantic colors.
- `.btn-tiny` restyled to flat sm-button look.

---

## Backend (config only)

`execution/server.py` — one line:

```py
# was: app.run(..., port=8080)
app.run(..., port=int(os.environ.get('PORT', 8080)))
```

Lets local dev pick a port via env when 8080 is occupied (e.g., another
local app). Mirrors how Cloud Run already injects `$PORT`. **No business
logic changed.**

---

## Files touched

| File | Change |
|------|--------|
| `ui/style.css` | Tokens rewrite + 4 purple sweeps + design-system utility layer + per-surface override layers (Image/Voice/Kie/Usage/Phase 1–4). 4574 → 6499 lines. CSS braces 905/905. |
| `ui/index.html` | Inline `<style>` token refresh; new shell (sidebar + topbar + stepper); new shell-helper JS functions; Image tab functional rewrite (mode/ref/aspect/history); Voice/Usage/Kie/Phase 1–4 markup updates. 10929 → 11529 lines. |
| `execution/server.py` | One line: `port=int(os.environ.get('PORT', 8080))`. |
| `docs/changelog_ui_redesign_2026_05_05.md` | This file. |

---

## Verification

- Sanity: CSS braces balance (905/905), HTML lines ~11.5k.
- Purple sweep: zero hits across hex, rgb-triplet, and named-color
  patterns in both files.
- All preserved JS hooks present: `switchTab`, `currentProjectId`,
  `loadProject`, `triggerAutosave`, `authFetch`, `visualsScenes`,
  `backgroundOps`, `kieModelsLoaded`, `initKieStudio`, plus
  `#phase1Card / #phase2Card / #phase3Card` ids.
- Local server runs on port 8090 (8080 was occupied by another local
  Node app on the dev machine) via `PORT=8090 sh run_server.sh` or
  equivalent.

## Deferred (intentionally — separate pass)

- **Lightbox absorbing per-scene editing UI.** Currently the scene cards
  still own their inline prompt / model / edit / animate inputs. The
  spec calls for these to move into a 4-tab side panel inside a
  full-screen lightbox (Versions · Prompt · Edit · Animate). Function
  names (`regenerateSceneImage`, `openImageEditor`) and API paths stay
  the same when this lands — only DOM-id targets shift.
- **Filmstrip timeline** at the bottom of the Visuals workspace.
- **Command palette (`⌘K`)** stub.
- **Skeletons applied to in-flight scene tiles** during batch
  generation.

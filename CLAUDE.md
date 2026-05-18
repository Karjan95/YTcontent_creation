# Gemini Studio — AI Content Creation Platform

## Project Overview

Full-stack AI-powered video production app: research → scriptwriting → visual production.
Users authenticate via Firebase, provide their own Gemini API key (encrypted at rest), and create projects that auto-save to Firestore.

## References

See @README.md for project intro and local setup instructions.
See @AGENTS.md for the 3-layer architecture (directive → orchestration → execution) and operating principles.
See @requirements.txt for Python dependencies.
See @Dockerfile for container build.
See @deploy.sh and @deploy_staging.sh for Cloud Run deployment.

### Directives (SOPs)
- @directives/research_and_scriptwriting.md — Research & script pipeline
- @directives/gemini_interaction.md — Gemini API usage patterns
- @directives/fix_parallel_projects.md — Parallel project handling

### Changelogs & Docs
- @docs/ — All changelogs and session summaries (35 files; see `docs/changelog_6phase_pipeline_2026_03_22.md` for the current production pipeline)
- @QA_Test_Plan.md — QA test plan

## Tech Stack

- **Backend:** Flask 3.1.2 + Gunicorn (Python 3.10)
- **AI Engine:** Google Gemini API (`google-genai`) — text, image (Imagen 4 / Gemini Pro Image), video (Veo 3.1), TTS (30+ voices)
- **Database:** Firestore (projects, dossiers, settings) + Firebase Storage (media)
- **Auth:** Firebase Authentication (Google OAuth)
- **Security:** Fernet encryption for API keys, Flask-Limiter for rate limiting
- **Frontend:** Single-page vanilla HTML/CSS/JS (no framework), Firebase client SDK
- **Deployment:** Docker → Google Cloud Run (`us-central1`)

## Full Project Tree

```
.
├── CLAUDE.md                 # ← You are here
├── AGENTS.md                 # 3-layer architecture instructions (mirrored to GEMINI.md)
├── GEMINI.md                 # Same as AGENTS.md (for Gemini/other AI environments)
├── README.md                 # Project intro and local setup
├── QA_Test_Plan.md           # QA testing plan
├── SKILL_SkillCreator.md     # Skill creation template
│
├── execution/                # ── Backend Python modules ──
│   ├── server.py             # Flask app — @require_auth middleware, all API routes (4,356 lines)
│   ├── gemini_client.py      # Gemini API wrapper — text/image/TTS/video, retry+backoff (1,708 lines)
│   ├── research_scriptwriter.py  # Research + script + 6-phase production pipeline (1,907 lines)
│   ├── research_templates.py # All prompts, templates, audience/tone definitions (4,617 lines)
│   ├── model_schemas.py      # Structured-output JSON schemas for Gemini (1,660 lines)
│   ├── kie_client.py         # KIE.AI integration (Midjourney, Kling, etc.) (1,025 lines)
│   ├── cost_tracker.py       # Per-call cost tracking → Firestore (343 lines)
│   ├── pricing.py            # Gemini/Imagen/Veo rate sheet (209 lines)
│   ├── seedance_studio/      # Seedance video generation routes + storage
│   │   ├── routes.py
│   │   ├── schemas.py
│   │   └── storage.py
│   ├── youtube_utils.py      # YouTube transcript analysis
│   ├── debug_items.py        # Debug utilities
│   ├── debug_youtube.py      # YouTube debug scripts
│   ├── debug_youtube_v2.py
│   ├── test_genai_simple.py  # Quick genai sanity check
│   └── test_server_logic.py  # Server logic unit tests
│
├── ui/                       # ── Frontend ──
│   ├── index.html            # Entire SPA — all tabs, modals, JS logic (~13,023 lines)
│   └── style.css             # CSS variables, animations, Space Grotesk font (~7,437 lines)
│
├── tests/                    # ── Test suite (pytest) ──
│   ├── conftest.py           # Shared fixtures (mock Firebase, Firestore, Gemini)
│   ├── pytest.ini            # Pytest config
│   ├── test_api_workflows.py # API integration tests
│   ├── test_ui_workflows.py  # Frontend workflow tests
│   ├── test_production_batching.py  # Batch processing tests
│   ├── test_research.py      # Research pipeline tests
│   ├── test_deep_research.py # Deep research tests
│   ├── test_all_templates.py # Template validation
│   ├── test_gemini_call.py   # Gemini API call tests
│   └── test_list*.py         # Model listing tests
│
├── directives/               # ── SOPs (3-layer architecture) ──
│   ├── research_and_scriptwriting.md  # Research + script pipeline directive
│   ├── gemini_interaction.md          # Gemini API interaction directive
│   └── fix_parallel_projects.md       # Parallel project handling
│
├── docs/                     # ── Changelogs & session summaries ──
│   ├── changelog_3phase_style.md
│   ├── changelog_creative_direction.md
│   ├── changelog_dynamic_wardrobe_expressions_2026_03_04.md
│   ├── changelog_edit_fixes_model_pricing_cancel_2026_03_03.md
│   ├── changelog_history_and_download_fixes.md
│   ├── changelog_image_history_and_downloads.md
│   ├── changelog_image_history_edit_ratelimits_2026_03_02.md
│   ├── changelog_reference_image_persistence.md
│   ├── changelog_script_ui_and_prompts.md
│   ├── changelog_vibe_architecture.md
│   ├── changelog_visual_style_overhaul.md
│   ├── bugfix_image_history_and_downloads_2026_03_02.md
│   ├── fix_visuals_persistence_on_refresh_2026_03_02.md
│   ├── manual_import_fix_summary.md
│   ├── session_summary_character_intelligence_2026_03_04.md
│   └── dual_layer_style_guide.md
│
├── tools/                    # ── Utility scripts ──
│   ├── create_notebook.py
│   ├── inspect_genai*.py     # GenAI introspection utilities
│   ├── verify_notebooklm.py
│   └── n8n-mcp-server/      # N8N MCP integration (TypeScript)
│       ├── index.ts
│       ├── package.json
│       └── tsconfig.json
│
├── .agent/skills/            # ── Agent skill definitions ──
│   ├── chief-of-staff/
│   ├── code-reviewer/
│   ├── critical-thinker/
│   ├── environment-setup-guide/
│   ├── math-stats-expert/
│   ├── mcp-builder/
│   ├── project-manager/
│   ├── qa-engineer/
│   └── ui-ux-pro-max/
│
├── generated_images/         # Local image cache (gitignored)
├── generated_audio/          # Local audio cache (gitignored)
├── .tmp/                     # Temp processing files (gitignored)
│
├── Dockerfile                # python:3.10-slim, gunicorn, Cloud Run compatible
├── deploy.sh                 # Production deployment → Cloud Run
├── deploy_staging.sh         # Staging deployment → Cloud Run
├── run_server.sh             # Local server launcher
├── requirements.txt          # Python dependencies
├── firebase-service-account.json  # Firebase credentials (gitignored in deploy)
├── .env                      # Environment variables (never commit)
├── .dockerignore
├── .gcloudignore
└── .gitignore
```

## Key Architecture

**Auth flow:** Firebase ID token → `@require_auth` decorator → decrypt user API key from Firestore → Gemini calls

**6-Phase Production Pipeline** (always-on; the old "Fast"/"Max Quality" modes are deprecated — `quality_mode` is ignored). Implemented in `execution/research_scriptwriter.py:638` (`generate_production_table`) → `:1128` (`_generate_single_batch_6phase`):

0. **Script Doctor** — runs **once** on the full narration before batching; produces a shared Visual Brief (gemini-2.5-flash, `research_scriptwriter.py:724`)
1. **Director** — editorial cuts, camera intent, emotional arc
2. **Cinematographer** — camera technique from the 62-technique library
3. **Storyboard Artist** — layered visual compositions
4. **Continuity Supervisor** — review + auto-fix (non-critical; falls through on failure)
5. **Director of Photography** — final image/video prompts with lighting vocabulary

Phases 1–5 run **sequentially per batch**, all on `gemini-2.5-flash`. Batching is per act with `BEATS_PER_BATCH` driven by pacing tier (Standard=8, Frenetic=3, …, `research_scriptwriter.py:711-717`). Batches run in parallel up to `MAX_CONCURRENT_BATCHES = 3` (`:763`).

**Retries on the production table are stacked**: every Gemini call retries 3× with exponential backoff on 503/429 (`gemini_client.py:36-58`), and the *whole 5-phase batch* retries up to 3× on top of that (`research_scriptwriter.py:817-840`). One stuck phase can compound into many minutes of wall time.

**Production table is a synchronous endpoint.** `POST /api/generate-production-table` (`server.py:3109`) runs the entire pipeline inline and only writes `production_data` to Firestore after the whole job finishes — there is no per-batch save, no `/poll` endpoint, and no job queue. The UI calls it with a single `fetch` (`ui/index.html:4795`) with no client-side timeout, and shows hardcoded status messages that stop updating after 110s (`ui/index.html:4748-4754`). This is the leading cause of "looks frozen" / "only Act 1 visible" reports — any Act 1 the user sees during a long generation is leftover data from a *previous* save.

**State:** Auto-save with 2s debounce to Firestore. Projects include all tabs, settings, and media references.

## Build & Run

```bash
# Install dependencies
pip install -r requirements.txt

# Run locally
python execution/server.py
# OR with gunicorn
gunicorn --bind :8080 --workers 1 --threads 8 execution.server:app

# Run tests
pytest tests/

# Deploy
./deploy.sh            # Production (content-creation-app)
./deploy_staging.sh    # Staging (content-creation-app-staging)
```

## Environment Variables

```
GEMINI_API_KEY=         # Fallback server key
ENCRYPTION_KEY=         # Fernet key for API key encryption
GOOGLE_CLOUD_PROJECT=   # GCP project ID (gen-lang-client-0854991687)
ENVIRONMENT=            # staging | production
```

Never commit `.env`, service account JSON, or plaintext secrets.

## Coding Conventions

- **Python:** snake_case, module-level constants for pacing/costs/templates
- **JavaScript:** camelCase
- **Error handling:** Retry with exponential backoff for 503/429 (max 3 attempts), safe error responses (no sensitive data)
- **Routes:** All in `server.py`, business logic separated into other modules
- **Prompts:** All prompt templates live in `research_templates.py`
- **Rate limits:** Per-user (not IP): research 30/hr, images 600/hr, TTS 60/hr, video 60/hr

## Important Patterns

- User API keys are Fernet-encrypted in Firestore, decrypted per-request
- Firebase Storage uses signed URLs with 4-hour expiration
- Image generation supports 6 models with different cost/quality tradeoffs
- Production table generation uses the 6-phase pipeline (Script Doctor + 5 per-batch phases on `gemini-2.5-flash`); see the "Key Architecture" section
- Character Intelligence System manages cast identity, wardrobe (locked vs story-driven), and expressions (dynamic vs neutral)
- Visual Style system uses 1-4 reference images with style lock modes (full, art_only, loose)
- Narrative Spine: per-project list of factual claims (`claim_id`s) that flow through script → beat regen → production prompts (see `docs/changelog_narrative_spine_2026_04_26.md`)
- Cost tracking: every Gemini/Imagen/Veo call is logged via `cost_tracker.py` for the per-project cost dashboard

## Cloud Run Deployment

- **Project:** `gen-lang-client-0854991687`
- **Region:** `us-central1`
- **Timeout:** 3600s (long-running generation ops)
- **Auth:** Unauthenticated ingress (Firebase handles auth)
- Docker: `python:3.10-slim`, Gunicorn, port via `$PORT`

## Testing

- Framework: pytest + pytest-mock + pytest-flask
- Tests mock Firebase auth, Firestore, and Gemini API calls
- Key test files: `test_api_workflows.py`, `test_research.py`, `test_production_batching.py`, `test_all_templates.py`

## Content Pipeline (User Journey)

1. **Research** — Select template (10+ types) → enter topic → AI does deep web research → structured dossier
2. **Script** — AI suggests titles → select audience (12 profiles) & tone (15+ tones) → generate narration (acts/beats) → edit/regenerate
3. **Production** — Define visual style → configure cast → generate production table (6-phase: Script Doctor + Director + Cinematographer + Storyboard + Continuity + DP) → shot-by-shot prompts
4. **Visuals** — Generate images (batch/individual) → edit with prompts → animate with Veo → download all as zip

## Key API Route Groups

| Group | Prefix | Examples |
|-------|--------|---------|
| Auth/Config | `/api/` | `save-api-key`, `check-api-key` |
| Research | `/api/research` | `research`, `research/poll`, `templates` |
| Scripting | `/api/` | `generate-script`, `regenerate-beat`, `suggest-titles` |
| Style | `/api/` | `analyze-style-images`, `suggest-cast`, `expand-creative-direction` |
| Visuals | `/api/visuals/` | `generate-image`, `edit-image`, `start-animation`, `download-all` |
| Production | `/api/` | `generate-production-table` (synchronous; see Key Architecture for caveats) |
| KIE / Seedance | `/api/kie/`, `/api/seedance/` | Third-party generation integrations |
| Cost | `/api/cost/` | Per-project + workspace cost dashboard |
| Projects | `/api/projects` | CRUD + `dossiers` |

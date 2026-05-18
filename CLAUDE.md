# Gemini Studio — AI Content Creation Platform

## Project Overview

Full-stack AI-powered video production app: research → scriptwriting → visual production → Studio composer.
Users authenticate via Firebase, provide their own Gemini and Kie API keys (encrypted at rest), and create projects that auto-save to Firestore. A remote MCP server exposes Studio capabilities to Claude.ai connectors.

## References

- @README.md — project intro and local setup
- @AGENTS.md — 3-layer architecture (directive → orchestration → execution) and operating principles
- @requirements.txt — Python dependencies
- @Dockerfile — container build
- @deploy.sh / @deploy_staging.sh — Cloud Run deployment
- @QA_Test_Plan.md — QA test plan

### Directives (SOPs)
- @directives/research_and_scriptwriting.md
- @directives/gemini_interaction.md
- @directives/fix_parallel_projects.md

### Docs / Changelogs
`docs/` holds dated session changelogs (`changelog_*_YYYY_MM_DD.md`) — the most recent ones are the source of truth for current behavior. Notable handoff docs:
- `docs/STUDIO_RESUME.md` — resume guide for the unified Studio rebuild
- `docs/dual_layer_style_guide.md` — visual style architecture

## Tech Stack

- **Backend:** Flask 3.1.2 + Gunicorn (Python 3.10)
- **AI engines:**
  - Google Gemini (`google-genai`) — text, image (Imagen 4 / Gemini Pro Image), video (Veo 3.1), TTS (30+ voices)
  - Kie (`execution/kie_client.py`) — ~83 image/video models including Midjourney, Seedance, Topaz upscaling
  - Seedance sequences (`execution/seedance_studio/`) — parallel video pipeline
- **Database:** Firestore (projects, dossiers, settings, assets) + Firebase Storage (media)
- **Auth:** Firebase Authentication (Google OAuth) for web; OAuth 2.1 + PKCE + DCR for MCP
- **Security:** Fernet encryption for API keys, Flask-Limiter for rate limiting
- **Frontend:** Single-page vanilla HTML/CSS/JS (no framework), Firebase client SDK
- **Deployment:** Docker → Google Cloud Run (`us-central1`)

## Repo Layout

```
execution/         Backend Python — see "Key modules" below
ui/                Single-page app (index.html + style.css)
tests/             pytest suite
directives/        SOPs (3-layer architecture)
docs/              Dated changelogs + handoff guides
tools/             Local utility scripts (not deployed)
.tmp/              Per-project temp files (gitignored)
generated_*/       Local media cache (gitignored)
```

### Key modules in `execution/`

| Module | Purpose |
|--------|---------|
| `server.py` | Flask app, all HTTP routes, `@require_auth` middleware |
| `gemini_client.py` | Gemini API wrapper (text/image/TTS/video) |
| `kie_client.py` | Kie.ai API wrapper (Midjourney, Seedance, Topaz, etc.) |
| `research_scriptwriter.py` | Research + script generation pipeline |
| `research_templates.py` | All prompts, templates, audience/tone definitions, 6-phase pipeline |
| `model_schemas.py` | Per-model parameter schemas (Kie + native) |
| `pricing.py` + `cost_tracker.py` | Cost estimation and per-user usage tracking |
| `mcp_studio/` | Remote MCP server (OAuth + tool surface) — see "MCP Server" below |
| `seedance_studio/` | Seedance sequence pipeline blueprint |
| `youtube_utils.py` | YouTube transcript analysis |

## Key Architecture

**Auth flow:** Firebase ID token → `@require_auth` decorator → decrypt user API key from Firestore → Gemini/Kie call.

**6-Phase Production Pipeline** (replaced the older 3-phase / Fast mode on 2026-03-22 — see `docs/changelog_6phase_pipeline_2026_03_22.md`):

| Phase | Agent | Output |
|-------|-------|--------|
| 0 | Script Doctor | Per-beat Visual Brief (metaphors, mood, palette, symbols) |
| 1 | Director | Scene cuts, emotional arc, camera intent |
| 2 | Cinematographer | Camera technique from 62-technique library |
| 3 | Storyboard Artist | Layered compositions informed by camera decisions |
| 4 | Continuity Supervisor | Auto-fix variety / flow / consistency |
| 5 | DP | Final prompts with lighting vocabulary |

The Visual Brief from Phase 0 is shared context to every downstream phase.

**State:** Auto-save with 2s debounce to Firestore. Project doc holds all phase outputs (research dossier, narration, production table, visuals scenes, Studio asset refs) so refresh / project switch fully restores state — see `directives/fix_parallel_projects.md` for the rationale.

## Build & Run

```bash
# Install dependencies
pip install -r requirements.txt

# Run locally (either form works)
sh run_server.sh
# or:
PYTHONPATH=$PYTHONPATH:$(pwd)/execution python3 execution/server.py
# or with gunicorn:
gunicorn --bind :8080 --workers 1 --threads 8 execution.server:app

# Run tests
pytest tests/

# Deploy
./deploy.sh            # Production (content-creation-app)
./deploy_staging.sh    # Staging (content-creation-app-staging)
```

## Environment Variables

```
# Required
ENCRYPTION_KEY          # Fernet key for API key encryption (also seeds MCP JWT secret via HKDF)
GOOGLE_CLOUD_PROJECT    # GCP project ID (gen-lang-client-0854991687)

# Optional / situational
GEMINI_API_KEY          # Fallback server-side Gemini key
ENVIRONMENT             # staging | production
MCP_ISSUER_URL          # Canonical public URL for the MCP OAuth issuer. Required in prod — JWT iss/aud pinned to this. deploy.sh auto-sets it from the Cloud Run URL.
MCP_DISABLED            # "1" to skip MCP route registration entirely

# Feature flags (off by default during rollout)
NARRATIVE_SPINE         # "1" enables the intermediate ranking layer between research and script — see changelog_narrative_spine_2026_04_26.md
RESEARCH_STRUCTURED     # "1" enables the planner → parallel sub-researcher → merger research pipeline — see changelog_structured_research_pipeline_2026_04_23.md
```

Never commit `.env`, `firebase-service-account.json`, or plaintext secrets. Both are in `.gitignore`.

## MCP Server (Studio tab)

Cloud Run hosts a remote MCP server at `/mcp` that exposes Studio capabilities (image / video / audio generation, asset library, Seedance sequences) to Claude.ai custom connectors. Auth is OAuth 2.1 + PKCE + Dynamic Client Registration, backed by Firebase Auth — every MCP user maps to the same `users/{uid}` Firestore doc as the web UI, so per-user Gemini/Kie keys and asset libraries are unified.

- Discovery: `/.well-known/oauth-protected-resource`, `/.well-known/oauth-authorization-server`
- DCR: `POST /oauth/register`. Authorize/consent/token/revoke under `/oauth/*`
- Implementation: `execution/mcp_studio/` (mirrors the `seedance_studio/` blueprint pattern)
- Long-running ops (Veo, Kie, Seedance) return a `task_id` that Claude polls via `studio_get_generation_status` — `/mcp` never blocks

## Coding Conventions

- **Python:** snake_case, module-level constants for pacing/costs/templates
- **JavaScript:** camelCase
- **Routes:** All in `server.py`; business logic in sibling modules
- **Prompts:** All prompt templates live in `research_templates.py` — don't inline prompts in `server.py`
- **Error handling:** Exponential backoff for 503/429 (max 3 attempts); safe error responses (never leak sensitive data)
- **Rate limits:** Per-user (not IP): research 30/hr, images 600/hr, TTS 60/hr, video 60/hr — set with Flask-Limiter

## Important Patterns

- User API keys (Gemini, Kie) are Fernet-encrypted in Firestore, decrypted per-request
- Firebase Storage uses signed URLs; project assets are re-signed on every project load (URLs expire)
- Kie task results are re-hosted to Firebase Storage so the app owns the asset (Kie URLs are short-lived)
- Long-running generation (Veo, Kie, Seedance) is task-based: kick off → return `task_id` → poll
- Character Intelligence System: cast identity, wardrobe (locked vs story-driven), expressions (dynamic vs neutral)
- Visual Style system: 1–4 reference images with style lock modes (full, art_only, loose)

## Cloud Run Deployment

- **Project:** `gen-lang-client-0854991687`
- **Region:** `us-central1`
- **Services:** `content-creation-app` (prod), `content-creation-app-staging` (staging)
- **Timeout:** 3600s (long-running generation ops)
- **Auth:** Unauthenticated ingress (Firebase / MCP OAuth handle auth)
- **Image:** `python:3.10-slim` + Gunicorn, port via `$PORT`
- Service account needs `roles/iam.serviceAccountTokenCreator` for signed URL generation — see comment in `deploy.sh` for the one-time grant.

## Testing

- Framework: pytest + pytest-mock + pytest-flask
- Tests mock Firebase auth, Firestore, and AI API calls
- Notable suites: `test_api_workflows.py`, `test_research.py`, `test_production_batching.py`, `test_structured_research.py`, `test_narrative_spine.py`, `test_cost_tracker.py`, `test_pricing.py`, `test_usage_routes.py`

## Content Pipeline (User Journey)

1. **Research** — pick template → enter topic → AI does deep web research → structured dossier
2. **Script** — AI suggests titles → select audience & tone → generate narration (acts/beats) → edit/regenerate
3. **Production** — define visual style → configure cast → run 6-phase pipeline → shot-by-shot prompts
4. **Visuals** — generate images (batch / individual) → edit with prompts → animate with Veo or Seedance → download all as zip
5. **Studio** — unified composer for image/video/audio across all engines (Gemini, Kie, Seedance), with persistent asset library

## Key API Route Groups

| Group | Prefix | Examples |
|-------|--------|----------|
| Auth / Config | `/api/` | `save-api-key`, `check-api-key`, `kie/save-api-key`, `kie/check-credits` |
| Research | `/api/research` | `research`, `research/poll`, `templates` |
| Scripting | `/api/` | `generate-script`, `regenerate-beat`, `suggest-titles` |
| Style | `/api/` | `analyze-style-images`, `suggest-cast`, `expand-creative-direction` |
| Visuals | `/api/visuals/` | `generate-image`, `edit-image`, `start-animation`, `download-all` |
| Kie | `/api/kie/` | `models`, `generate`, `poll/<task_id>`, `mj/poll/<task_id>`, `upload-image` |
| Projects | `/api/projects` | CRUD + `dossiers` |
| Studio (MCP) | `/mcp`, `/oauth/*`, `/.well-known/*` | Remote MCP server for Claude connectors |

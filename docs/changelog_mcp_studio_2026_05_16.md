# MCP Studio Server — Build & Iteration Log

**Date:** 2026-05-16
**Author:** Karen + Claude
**Scope:** New remote MCP server (`/mcp`) that exposes the Studio tab to Claude.ai and other MCP clients. Three iterations shipped same-day: initial build (v1), inline rendering + persistence (v2), and async library persistence + video rendering (v3).

---

## Context

Gemini Studio's image/video/audio generation surface lived only behind the web UI. Goal: let Claude.ai (and Claude Code) drive Studio through a custom connector — using each user's existing Firebase identity, their encrypted Gemini/Kie keys, and their existing project asset library. No data duplication: every MCP call lands in the same `users/{uid}/projects/{pid}/...` Firestore namespace as the web UI.

Hosting: single Cloud Run service (`content-creation-app-staging` and `content-creation-app`). All MCP endpoints registered as a Flask blueprint inside the existing `execution/server.py`, mirroring the `seedance_studio/` precedent.

---

## v1 — Initial build

### New package: `execution/mcp_studio/`

```
mcp_studio/
├── __init__.py            # register_routes(app, limiter, require_auth, ...)
├── routes.py              # mounts /mcp, /oauth/*, /.well-known/*; scoped CORS
├── oauth.py               # DCR, /authorize, /consent, /token, /revoke
├── consent_template.py    # HTML consent page with Firebase JS SDK signin
├── jwt_tokens.py          # HS256 mint/verify; HKDF-derived secret
├── auth_decorator.py      # @require_mcp_auth — JWT → g.uid + decrypted keys
├── mcp_protocol.py        # JSON-RPC dispatch
├── polling.py             # poll_kie_task_once, poll_veo_op_once
├── errors.py              # JSON-RPC error mapper
└── tools/
    ├── __init__.py        # TOOL_REGISTRY assembly
    ├── content_blocks.py  # text/image/audio/resource_link builders
    ├── studio_tools.py    # list_models, generate, get_generation_status, upload_reference
    ├── asset_tools.py     # list_projects/get_project + asset CRUD
    └── seedance_tools.py  # animate_sequence, get_sequence_status
```

### OAuth 2.1 (RFC 8252 + RFC 7591) endpoints

- `GET /.well-known/oauth-protected-resource` — resource metadata
- `GET /.well-known/oauth-authorization-server` — issuer metadata
- `POST /oauth/register` — Dynamic Client Registration (PKCE-only public clients + confidential `client_secret_post` clients)
- `GET /oauth/authorize` — consent HTML using existing Firebase JS SDK config
- `POST /oauth/consent` — validates Firebase ID token, mints 60s authorization code
- `POST /oauth/token` — `authorization_code` (PKCE S256 required) and `refresh_token` (with rotation, 5s grace)
- `POST /oauth/revoke` — adds `jti` to a Firestore denylist

JWT claims: `{iss, aud=<issuer>/mcp, sub=uid, client_id, scope, iat, exp, jti, typ}`. HS256, 32-byte secret derived from `ENCRYPTION_KEY` via HKDF-SHA256(`mcp-studio-jwt`, info=`hs256`). Access TTL 1h, refresh TTL 30 days.

Firestore TTLs enabled on:
- `mcp_oauth_codes.exp_at` (60s) — single-use auth codes
- `mcp_token_denylist.exp_at` (matches original JWT exp) — revoked-token jti list

### `/mcp` JSON-RPC handler

Implements: `initialize`, `ping`, `tools/list`, `tools/call`, `notifications/initialized`. JSON-RPC 2.0 over plain HTTP POST. Unauthenticated requests get `401 WWW-Authenticate: Bearer resource_metadata="..."` per the spec. Arguments validated against per-tool JSON Schema via `jsonschema`.

### Tools registered (12 in v1)

- `studio_list_models` — registry of all 129 models grouped by 20 providers
- `studio_generate` — dispatches to existing `_studio_dispatch_*` in `server.py`; returns inline image/audio for sync backends, `task_id` for async (Veo, Kie, Seedance)
- `studio_get_generation_status` — single-shot polling for Kie/Veo
- `studio_upload_reference` — small reference uploads via URL or base64 data URI
- `studio_list_projects`, `studio_get_project`
- `studio_list_assets`, `studio_save_asset`, `studio_update_asset`, `studio_delete_asset`
- `studio_animate_sequence`, `studio_get_sequence_status` (Seedance M1)

### CORS

Flask-CORS scoped only to `/mcp`, `/oauth/*`, `/.well-known/*`. Origins: `https://claude.ai`, `https://*.anthropic.com`, plus localhost for testing. The host web UI routes keep their same-origin posture untouched.

### Wiring into `server.py`

```python
from mcp_studio import register_routes as register_mcp_routes
register_mcp_routes(
    app, limiter, require_auth,
    db=db, decrypt_api_key=decrypt_api_key,
    upload_to_storage=upload_to_storage,
    encryption_key=_ENCRYPTION_KEY,
    firestore_module=firestore,
    encrypt_api_key=encrypt_api_key,
)
```

### Deploy scripts

- `deploy.sh` and `deploy_staging.sh` deploy the service without `MCP_ISSUER_URL`, then read the actual Cloud Run URL via `gcloud run services describe` and patch the env var via a second `gcloud run services update`. Eliminates the manual fix-up after the first deploy. Honors a manually exported `MCP_ISSUER_URL` (for custom domains).

### New dependencies

- `PyJWT==2.10.1`
- `flask-cors==5.0.0`
- `jsonschema==4.23.0`

### Documentation

`CLAUDE.md` updated with new env vars (`MCP_ISSUER_URL`, `MCP_DISABLED`, `MCP_VIEWER_MIME`) and a brief "MCP Server" section describing the OAuth surface and the file layout.

### Infrastructure: Firebase Auth authorized domains

Added the Cloud Run hash hostnames to Firebase Auth's `authorizedDomains` so the consent-page Firebase popup works:
- `content-creation-app-staging-qj4rflrraa-uc.a.run.app`
- `content-creation-app-qj4rflrraa-uc.a.run.app`

(The project-number variants were already authorized for the web UI.)

---

## v2 — Inline rendering + persistence

After v1 shipped, real Claude.ai sessions surfaced six issues. Fixed in order of severity.

### 1. Inline media rendering via MCP Apps

**Problem:** Anthropic open bug `claude-ai-mcp#238` (April 2026, high priority): plain MCP `image` content blocks are readable by the model but not rendered to the user in claude.ai. Setting `annotations.audience: ["user"]` doesn't help.

**Fix:** Implement MCP Apps (`2026-06-18` spec).
- Added `resources/list` and `resources/read` JSON-RPC handlers to `mcp_protocol.py`.
- Advertise `resources` capability in `initialize`.
- Registered a single resource at `ui://studio/media-viewer`, served as `text/html;profile=mcp-app` (the value `RESOURCE_MIME_TYPE` exported by `@modelcontextprotocol/ext-apps`; the `text/html+skybridge` form is OpenAI ChatGPT Apps protocol — different system).
- New `execution/mcp_studio/ui_resources/media_viewer.html`: self-contained iframe page importing `@modelcontextprotocol/ext-apps` from `esm.sh`, hooking `app.ontoolresult`, and rendering image/audio/video/resource_link blocks.
- Attached `_meta.ui.resourceUri: "ui://studio/media-viewer"` to every media-returning tool: `studio_generate`, `studio_get_generation_status`, `studio_list_assets`, `studio_get_asset`, `studio_animate_sequence`, `studio_get_sequence_status`.

### 2. Kie temp URL persistence

**Problem:** `tempfile.aiquickdraw.com/vnp/...` URLs from Kie are throwaway (short TTL, geo-restricted). After a few minutes the chat re-render breaks and the saved asset URL is dead.

**Fix:** New `execution/mcp_studio/storage_rehost.py` — `rehost_to_firebase(url, kind, project_id, upload_to_storage)` downloads via urllib (50 MB cap, 25s timeout), writes to a tmp file, uploads via the existing `upload_to_storage` helper, returns a permanent Firebase signed URL. Falls back to the original URL on any failure. Invoked after sync Kie image returns and after async completion in `studio_get_generation_status` and `studio_get_sequence_status`.

### 3. Firestore composite-index error

**Problem:** `studio_list_assets` with `kind` filter required a composite `(kind, ts DESC)` index that didn't exist, returning `FAILED_PRECONDITION` to users.

**Fix:** Drop `order_by` when filtering by kind. Query by `kind` only, sort by `ts` in Python after fetching. Same fix applied to `studio_list_projects` (`order_by('updated_at')` was silently dropping docs missing the field — caused the "3-month-old project picked" bug).

### 4. Hard-require `project_id` on `studio_generate`

**Problem:** Silent auto-pick selected stale projects.

**Fix:** Removed the auto-pick. `studio_generate` without `project_id` returns an `isError` text result instructing Claude to call `studio_list_projects` first and ask the user.

### 5. Polling cadence hint

**Fix:** Async returns from `studio_generate` (Veo, Kie task_id) now include an estimated completion window and recommended first-poll delay in the text block, plus a `structuredContent` field with the same data machine-readable.

### 6. New tool `studio_get_asset`

Fetches a single asset by id and renders it inline via the viewer. Fallback path when `list_assets` is too noisy.

### MIME-type fix (hot patch)

Initial deploy used `text/html+skybridge` for the viewer resource — Claude.ai rejected it with "Unsupported UI resource content format". Hot-patched the running service via `gcloud run services update --update-env-vars 'MCP_VIEWER_MIME=text/html;profile=mcp-app'` and updated the code default.

### Firebase init double-load fix

When MCP tool handlers lazy-imported `from server import _studio_dispatch_*`, Python loaded `server.py` a second time (because gunicorn registered it as `execution.server`, not `server`), triggering `ValueError: The default Firebase app already exists`. Guarded `firebase_admin.initialize_app()` with `if not firebase_admin._apps:` in `server.py` so re-imports are safe.

### Firebase Auth CSP

The consent page CSP blocked `https://apis.google.com/js/api.js` (Firebase Auth's popup loader). Added `apis.google.com` to `script-src`, `script-src-elem`, `connect-src`, and `frame-src` in `consent_template.py`. Sign-in via Google popup now works.

---

## v3 — Async library persistence + video rendering + URL threading

Second real session surfaced four more issues. All shipped to staging revision `00126-qw8`.

### 1. Async results now land in the project library

**Problem:** `_maybe_save` was only called from the **sync** branches of `studio_generate`. Long-running paths (Veo, Kie video, Kie async image) finished in `studio_get_generation_status`, which never wrote an asset row. Result: chat widget showed the asset but the Studio web UI gallery and `studio_list_assets` returned nothing.

**Fix:** Pending-task sidecar pattern. When `studio_generate` kicks off an async task, write a Firestore doc at `users/{uid}/projects/{pid}/pending_tasks/{task_key}` with `{model_id, backend, kind, prompt, params, inputs, save_to_library, started_at, created_by}`. `task_key` is `"kie:<task_id>"` or `"veo:<operation_name>"`. In `_get_status`, after rehost completes, `_consume_pending_task` reads + deletes the sidecar and calls `_maybe_save` with the original metadata. Same pattern in `seedance_tools._status`.

Firestore TTL enabled on `pending_tasks.started_at` so abandoned sidecars auto-clean.

### 2. Video rendering via `structuredContent.video_url`

**Problem:** Claude.ai's chat client rejects MCP `resource_link` blocks with `mimeType: video/mp4`, replacing them with the literal stock string `"Resource links are not currently supported. The tool returned a link to: …"` — outside the MCP App iframe, so the viewer never gets a chance to render.

**Fix:** Stop emitting `cb.video_link` for completion paths. Pass the video URL through `structuredContent.video_url` (which flows to the iframe alongside `content`). The viewer HTML now reads `result.structuredContent.{video_url, image_url, image_urls, audio_url}` in a new `renderStructured()` function and renders `<video controls preload="metadata">` directly. Belt-and-suspenders: also augments image rendering from `image_url` when the content array has no inline image block.

### 3. URL threading via `structuredContent.primary_url`

**Problem:** Claude asked to "turn that image into a video" but didn't pass the prior image's URL to the next call. The URL existed in a text block (`URLs: [...]`) but Claude.ai's UI may de-emphasize text blocks when an MCP App widget is rendered, and the URL was buried inside a JSON-array string.

**Fix:** Every success path now returns:
- A top text caption: `"Generated {kind} via {model_id}. Primary URL: {url}"` (greppable from chat).
- `structuredContent: {kind, urls, primary_url, image_url/video_url/audio_url, model_id, project_id, asset_id?, task_key?}` (machine-readable, never hidden).
- Tool descriptions for `studio_generate` and `studio_get_generation_status` explicitly tell Claude: "pass the prior call's primary_url as the next call's reference (`inputs.image_url`, `inputs.first_frame`, etc.)."

### 4. Stronger polling-cadence signal

**Problem:** "Try again in 15s" was a text hint and Claude polled every ~1 second.

**Fix:** Pending response text now reads `"DO NOT call studio_get_generation_status again for at least 15 seconds — aggressive polling slows the run."` Plus `structuredContent: {status: "pending", retry_after_seconds: 15, ...}` for machine consumption. Same shape applied to Seedance's pending path (20s, since Seedance is slower).

### 5. Signed PUT URL for reference uploads (carried over from earlier in the day)

**Problem:** Reference uploads via `studio_upload_reference` failed for files larger than ~50KB because Claude's base64-in-tool-args expansion either truncated the input or blew up the context window. With 4 reference images / videos / audio, hopeless.

**Fix:** New tool `studio_create_upload_url` returns a v4-signed Firebase Storage PUT URL (15-min TTL) plus a read-only GET URL. Claude runs `curl -X PUT --data-binary @file -H 'Content-Type: <mime>' '<upload_url>'` from its sandbox; bytes flow sandbox → Firebase directly without traversing Claude's context. After upload, Claude passes the returned `public_url` to `studio_generate.inputs.image_url` (or whatever the model expects). Backed by a new `create_signed_put_url(blob_path, content_type, expiration_seconds)` helper in `server.py` that mirrors the existing `_generate_signed_url` IAM-fallback path.

`studio_upload_reference` description downgraded to "for small (<50KB) files only" and explicitly points at `studio_create_upload_url` for larger files.

### 14 tools registered after v3

`studio_list_models`, `studio_generate`, `studio_get_generation_status`, `studio_create_upload_url`, `studio_upload_reference`, `studio_list_projects`, `studio_get_project`, `studio_list_assets`, `studio_get_asset`, `studio_save_asset`, `studio_update_asset`, `studio_delete_asset`, `studio_animate_sequence`, `studio_get_sequence_status`.

---

## Files affected (cumulative across v1+v2+v3)

| Path | Change |
|---|---|
| **NEW** `execution/mcp_studio/__init__.py` | Package marker, exports `register_routes`. |
| **NEW** `execution/mcp_studio/routes.py` | Blueprint registration, scoped CORS, viewer HTML loader. |
| **NEW** `execution/mcp_studio/oauth.py` | DCR + authorize/consent/token/revoke + discovery metadata. |
| **NEW** `execution/mcp_studio/consent_template.py` | Firebase-JS consent page; CSP allows `apis.google.com`. |
| **NEW** `execution/mcp_studio/jwt_tokens.py` | HS256 JWT mint/verify, HKDF secret, PKCE S256 verify. |
| **NEW** `execution/mcp_studio/auth_decorator.py` | `@require_mcp_auth` — JWT → g.uid + decrypted API keys. |
| **NEW** `execution/mcp_studio/mcp_protocol.py` | JSON-RPC dispatch incl. resources/list+read. |
| **NEW** `execution/mcp_studio/polling.py` | Single-shot Kie + Veo status checks. |
| **NEW** `execution/mcp_studio/errors.py` | JSON-RPC error mapping. |
| **NEW** `execution/mcp_studio/storage_rehost.py` | Kie/Veo URL → Firebase Storage mirroring. |
| **NEW** `execution/mcp_studio/ui_resources/media_viewer.html` | MCP App viewer (iframe). |
| **NEW** `execution/mcp_studio/tools/__init__.py` | TOOL_REGISTRY assembly. |
| **NEW** `execution/mcp_studio/tools/content_blocks.py` | Block builders with user-audience annotations. |
| **NEW** `execution/mcp_studio/tools/studio_tools.py` | Studio generate/status/upload tools + pending_tasks sidecar. |
| **NEW** `execution/mcp_studio/tools/asset_tools.py` | Asset library + project tools with composite-index fix. |
| **NEW** `execution/mcp_studio/tools/seedance_tools.py` | Seedance animate + status with pending_tasks + asset save. |
| `execution/server.py` | Firebase init guard; `create_signed_put_url` helper; `register_mcp_routes` wiring. |
| `requirements.txt` | Added `PyJWT==2.10.1`, `flask-cors==5.0.0`, `jsonschema==4.23.0`. |
| `deploy.sh`, `deploy_staging.sh` | Two-phase deploy that auto-sets `MCP_ISSUER_URL` from the real Cloud Run URL. |
| `CLAUDE.md` | Documents new env vars and the `/mcp` capability. |

---

## Infrastructure changes (one-time)

| Action | Status |
|---|---|
| Firestore TTL on `mcp_oauth_codes.exp_at` | ACTIVE |
| Firestore TTL on `mcp_token_denylist.exp_at` | ACTIVE |
| Firestore TTL on `pending_tasks.started_at` | ACTIVE |
| Firebase Auth authorized domains updated | DONE — added staging + prod hash hostnames |
| Staging service env: `MCP_ISSUER_URL` | Auto-set by deploy script |
| Staging service env: `MCP_VIEWER_MIME` | `text/html;profile=mcp-app` (also default in code) |

---

## Verification (manual, against staging)

- OAuth discovery + DCR + PKCE flow end-to-end via Claude.ai connector wizard.
- `tools/list` returns 14 tools, 6 carrying `_meta.ui.resourceUri`.
- `resources/list` + `resources/read` return the viewer HTML with mime `text/html;profile=mcp-app`.
- Image generation (sync, Google native): asset appears in library and in chat widget.
- Image generation (async, Kie): asset appears in library after `studio_get_generation_status` completes.
- Video generation (async, Kie): asset appears in library, video renders inline via viewer + `structuredContent.video_url`.
- `studio_list_assets` with `kind="image"` filter: no Firestore composite-index error.
- `studio_generate` without `project_id`: returns explicit error.
- Reference upload via `studio_create_upload_url`: signed PUT URL works from a sandbox curl.

Open items / known gaps:
- Image→video chaining requires Claude to read `structuredContent.primary_url` correctly. Tool description steers it, but not formally verified.
- Polling cadence is still client-controlled; we can only nudge with text + structured hints.
- "Reference image gets ignored by underlying model" not formally end-to-end tested yet (see open item — would need a session trace).

---

## Cloud Run revisions shipped today

- `content-creation-app-staging-00117-b29` — v1 + Firebase init guard
- `content-creation-app-staging-00119-8h9` — annotations + auto-save defaults (later superseded)
- `content-creation-app-staging-00121-mfk` — v2 (MCP Apps, rehost, composite-index fix, polling hints, `studio_get_asset`)
- `content-creation-app-staging-00123-x2d` — `studio_create_upload_url`
- `content-creation-app-staging-00124-l5t` — MIME hot-patch (`text/html;profile=mcp-app`)
- `content-creation-app-staging-00126-qw8` — v3 (pending_tasks sidecar, video via structuredContent, URL threading, stronger polling)
- `content-creation-app-staging-00128-5tr` — v4 first pass (Higgsfield-style card, batch images, lean polling — viewer still broken because of CSP)
- `content-creation-app-staging-00130-kwq` — v4 final (inline MCP-Apps client; card now actually renders)

Production not yet deployed for any of this work.

---

## v4 — Higgsfield-style card UI, true elapsed time, lean polling, batch images

Triggered by a session where the user contrasted our viewer against Higgsfield's: their MCP renders a card with a tool header, prompt caption, model/AR/duration/audio badges, the media, and a Download/Recreate action row. Plus a real "⟳ Generating" placeholder while async jobs run, and `n` for batch images. Three follow-on complaints from the same session:

1. **Claude hallucinates elapsed time.** "90 seconds passed" when 5 had — and it kept polling every few seconds, burning tokens.
2. **Token waste in general.** `studio_list_models` dumped 6KB of schema JSON on every call; tool descriptions were 700 tokens; pending responses re-stated the same prose every poll.
3. **No batch generation.** Higgsfield can fire 4 outputs per call.

### 1. Card UI rewrite (`media_viewer.html`)

Full rewrite of the iframe content. Structure per tool result:

```
┌─ Studio · studio_generate                        </>
│  <prompt caption, click to expand>
│  [Imagen-4] [📷] [16:9] [⏱ 10s] [🔊 Audio]
│  ┌─ <media or "⟳ Generating…" placeholder> ────┐
│  └────────────────────────────────────────────┘
│  [⬇ Download]  [📋 Copy URL]  [↻ Recreate]
└────────────────────────────────────────────────────
```

- **Header** — small accent dot + `Studio · <tool_label>` (label set per tool by the server).
- **Prompt caption** — 2-line clamp by default, click expands.
- **Badges row** — chips for `model_id`, kind icon, `aspect_ratio`, `duration_seconds`, `audio_enabled` — only renders chips for fields the response actually carries.
- **Media frame** — rounded container. Single image/video/audio for `n=1`, 2-col CSS grid when `structuredContent.image_urls.length > 1`.
- **Pending placeholder** — animated shimmer + `⟳ Generating · 00:42 elapsed · ~90-240s · next check ~120s`. Elapsed is computed in the iframe from a server-stamped `started_at` ISO timestamp on every pending response — so Claude's hallucinated narration about elapsed time is irrelevant; the user always sees ground truth. `setInterval(updateElapsed, 1000)` runs entirely client-side, no tokens.
- **Action row** (completed assets only):
  - **Download** — `<a download href="primary_url">`. Works in every browser, no host cooperation needed.
  - **Copy URL** — `navigator.clipboard.writeText(primary_url)` with a "Copied" tooltip.
  - **Recreate** — first tries `app.callTool("studio_generate", payload)` (no-ops on Claude.ai today, future-proof). Falls back to `navigator.clipboard.writeText(<recreate payload>)` with a tooltip telling the user to paste it back.

### 2. **Critical fix — inline MCP-Apps client (no external imports)**

The first v4 deploy shipped the card UI but it didn't render. Symptom on desktop: just the inline image with no card; on mobile: my fallback text "Waiting for tool result…".

Root cause: the v2/v3 viewer relied on `import("https://esm.sh/@modelcontextprotocol/ext-apps@latest")` at runtime. Claude.ai sandboxes the iframe with a strict CSP that **blocks remote ESM imports**, so the import always threw, the catch-block fired, and no MCP-Apps handshake ever happened. The iframe was effectively dead the whole time — what users saw in v2/v3 was Claude.ai's native rendering of inline `image` content blocks, not our widget. We just never noticed because the bare-bones viewer wasn't visibly different from the native renderer.

Fix: drop the SDK import entirely. Implement the JSON-RPC-over-postMessage protocol directly in ~80 lines of inline JS. Pulled the canonical method strings from the SDK source:

| Const | Value |
|---|---|
| `LATEST_PROTOCOL_VERSION` | `2026-01-26` |
| `INITIALIZE_METHOD` | `ui/initialize` |
| `INITIALIZED_METHOD` | `ui/notifications/initialized` |
| `TOOL_RESULT_METHOD` | `ui/notifications/tool-result` |
| `TOOL_INPUT_METHOD` | `ui/notifications/tool-input` |
| `RESOURCE_MIME_TYPE` | `text/html;profile=mcp-app` |
| `RESOURCE_URI_META_KEY` | `ui/resourceUri` |

Implemented as `class MCPAppClient`:
- `window.addEventListener("message")` for incoming JSON-RPC.
- `window.parent.postMessage(msg, "*")` for outgoing.
- `connect()` sends `ui/initialize` request, waits up to 4s for the response (so hosts that skip the handshake don't block forever), then fires the `ui/notifications/initialized` notification.
- Permissive fallback: also accepts non-spec `{method: "toolResult"}` and `{type: "tool/result"}` envelopes in case a host implements a different shape.
- Synchronous-injection support: if `window.__toolResult` is already set when the script runs, `buildCard` is called immediately.

After this fix the iframe is fully self-contained — no external network dependencies, works under any CSP.

### 3. Server-side enrichment (`studio_tools.py`)

New `_enrich_sc(sc, *, model_id, prompt, inputs, params, kind, tool_label, started_at_iso)` helper applied to every response path so the viewer always has the data it needs for header/prompt/badges/timer. Threads `started_at_iso` from the pending sidecar through every poll. Also echoes `inputs_echo` and `params_echo` so the Recreate button has the original call payload.

New `_read_pending_task(deps, *, project_id, task_key)` reads the `pending_tasks` sidecar **without consuming it** — so pending status polls can keep enriching the card across multiple polls; only the completion path calls `_consume_pending_task` to delete.

`_write_pending_task` now stamps a parallel client ISO timestamp (`started_at_iso`) alongside the existing `SERVER_TIMESTAMP` — server timestamps aren't readable until after the write commits, but the client timestamp is.

### 4. Polling cadence — much longer waits

Per the user request to slash polling-related tokens. New `_RETRY_AFTER` and `_FIRST_POLL_AFTER` constants:

| Kind | Old retry | New retry | First poll |
|---|---|---|---|
| Kie image | ~15s | 12s | 12s |
| Kie video | ~15s | **180s** | 90s |
| Veo | ~20s | **240s** | 150s |
| Seedance | ~20s | **180s** | 90s |

The viewer's client-side elapsed timer means there's no UX penalty to long waits — the user sees a live counter and ETA range in the placeholder regardless of when Claude actually polls.

### 5. Token diet for tool output

- **`studio_list_models`** — dropped the 6KB `Full registry JSON` block. Returns just the per-provider summary lines plus `structuredContent: {model_ids: [...]}`. Saves ~1500 tokens per call.
- **Completion responses** — removed the duplicate `URLs: <json>` text block. The primary URL is already in the caption and the full list is in `structuredContent.urls`.
- **`studio_generate` description** — trimmed from ~700 tokens to ~150. Kept the load-bearing instructions (project_id required, chain via `primary_url`, use `studio_create_upload_url` for big files, `n=1..4` for image variants); dropped verbose schema prose since the JSON schema already covers it.
- **`studio_get_generation_status` description** — tightened to one paragraph with the per-kind `retry_after_seconds` minimums baked in.

Estimated savings on a Veo generation flow: ~9k tokens → ~2.7k tokens.

### 6. Image batch (`n: 1-4`)

New `n` field on `studio_generate.inputSchema` (integer 1-4, default 1).

- **Imagen / Gemini image / Nano-Banana** — passes through as `params.num_images`. The underlying `_studio_dispatch_google_image` already returns `image_urls: [...]`, and the viewer's grid renders them.
- **Kie generic image** — no native batch; returns 1 image with a one-line caption note (`n=N requested but {model} doesn't support batch`).
- **Video / audio / async backends** — explicitly rejects `n>1` with an error so we don't silently fan out and hit per-user rate caps (60/hr for video).

Video and audio batch (fan-out under a `batch:<uuid>` sidecar) is deferred to a follow-up.

### 7. Seedance (`seedance_tools.py`)

Same enrichment treatment via a new `_seedance_sc()` helper that pulls metadata from the seedance storage doc:
- `model_id` (seedance-2 or -fast), `prompt`, `aspect_ratio`, `duration_seconds`, `audio_enabled`, `started_at`.
- Applied to all three states: animate-start, status-pending, status-completed, status-failed.
- `retry_after_seconds: 180` everywhere.
- `studio_animate_sequence` now returns a proper card-shaped pending response instead of a raw JSON text block — the user sees the placeholder card immediately on kickoff, same as Veo/Kie.

### Files affected

| Path | Change |
|---|---|
| `execution/mcp_studio/ui_resources/media_viewer.html` | Full rewrite. New card structure, inline CSS for chrome (header, badges, frame, placeholder, action buttons), inline `MCPAppClient` replacing the runtime SDK import. |
| `execution/mcp_studio/tools/studio_tools.py` | `_enrich_sc`, `_read_pending_task`, `_RETRY_AFTER`/`_FIRST_POLL_AFTER` tables, `n` param on `studio_generate`, started_at_iso threading, list_models JSON dump removed, duplicate `URLs:` block removed, tool descriptions trimmed. |
| `execution/mcp_studio/tools/seedance_tools.py` | `_seedance_sc` helper, structured pending/completed/failed responses, `retry_after_seconds: 180`, persist `generate_audio` on the sequence doc. |

No infrastructure or dependency changes.

### Open items

- Recreate button calls `app.callTool` first, falls back to clipboard. Claude.ai's host doesn't currently honor `callTool` from inside a UI resource, so the clipboard path is what fires today. Once the host enables it, single-click Recreate just works without a code change.
- Video / audio batch generation via fan-out + parent `batch:<uuid>` sidecar.
- `studio_get_model_schema(model_id)` lookup so we can fully retire the registry JSON dump.

### Verification

Manual against staging revision `00130-kwq`:

- Sync image with `n=2`: card renders with header, prompt, badges, 2-image grid, and action row.
- Both web and mobile show the full card (mobile previously showed "Waiting for tool result…" — confirmed fixed).
- Veo / Kie video kickoff: pending card with live elapsed timer ticking every second; the displayed elapsed time matches actual wall-clock regardless of what Claude says in chat.
- `studio_list_models`: response body shrunk from ~7KB to ~1.5KB; no schema dump.
- Polling: Claude observed waiting 180-240s between status checks on a video job (vs ~15s before).

---

## v4 follow-ups — adapting to Claude.ai's sandbox

The "card actually renders" milestone in `00130-kwq` exposed the next layer of bugs as the user exercised the UI. Each fix uncovered a new Claude.ai sandbox restriction we hadn't known about. The arc below documents the discoveries in order; the final state lives in revision `00142-9bh`.

### Round 1 — declared CSP + sandbox permissions (`00132-2p5`)

Symptoms after `00130-kwq`:
- Mobile: card with badges and buttons, but images showed alt-text "image image" (URLs failed to load). Iframe small / cropped.
- Web: just the inline image rendered natively by Claude.ai; the widget didn't show.

Fixes:
- Added `_meta.csp` (with `resourceDomains` for Firebase Storage/Kie hosts) and `_meta.permissions.clipboardWrite` to the viewer resource per the `McpUiResourceMetaSchema` spec.
- Surfaced `_meta` on both `resources/list` and `resources/read` responses (`mcp_protocol.py`).
- Wired `ui/notifications/size-changed` from the viewer using a `ResizeObserver` + image/video load callbacks so the iframe grows to fit the card.
- For `n>1` image responses, stopped emitting inline `image` content blocks — Claude.ai's web client was rendering them natively and hiding the widget. The viewer now reads `structuredContent.image_urls` directly.

### Round 2 — base64 inline data via `audience: ["assistant"]` (`00134-vfh`)

Symptoms after `00132-2p5`:
- Card visible on web AND mobile.
- Images still didn't render — `_meta.csp.resourceDomains` was being ignored by the host.
- Action buttons (Download / Copy URL / Recreate) didn't do anything.
- Iframe still too small.

Discovery: Claude.ai enforces a fixed iframe CSP that ignores `_meta.csp`. But `data:` URIs always work in `<img src>` because they're inert.

Fixes:
- Extended `content_blocks.py` helpers (`image_block_from_bytes`, `image_block_from_url`, etc.) with a `user_visible: bool` flag. When `False`, the block is emitted with `annotations.audience: ["assistant"]` instead of `["user", "assistant"]` — Claude.ai's chat surface ignores it but the iframe still receives the full content array via `ui/notifications/tool-result`.
- For `n>1` image responses: emit inline base64 image blocks with `user_visible=False`. The widget reads `b.data` (base64) and renders `<img src="data:image/png;base64,...">` — bypassing CSP entirely.
- Viewer `buildMedia` rewritten to prefer inline base64 blocks over HTTPS `image_urls`; URLs are only used as a last-resort fallback.
- Card scaled up ~2× (padding, gap, font sizes, badge sizes, button sizes, media frame `min-height: 320px`, placeholder `min-height: 360px`).
- `Download` button uses inline base64 via `<a download href=data:...>`. `Copy URL` falls back to a hidden-textarea + `execCommand("copy")` when the clipboard API is denied.

### Round 3 — lightbox, per-tile actions, all params (`00136-vl4`)

User asked for: previewable images (not the small grid), all generation params visible (not just model/AR), batch-aware Copy URL, working Recreate.

- `buildBadges` extended to iterate `params_echo` + key `inputs_echo` fields (`negative_prompt`, `seed`). Each non-empty value becomes a chip (`Resolution: 720p`, `Seed: 42`). Already-shown keys are skipped via a `_SKIP_PARAM_KEYS` set.
- **Lightbox modal** — click any image → fixed overlay with the full-size image; click outside / × / ESC closes.
- **Per-tile hover overlay** — each tile in the batch grid has its own Download (real `<a download href=data:>`) and Expand (open lightbox) icons.
- **Copy URL on batches** — copies all URLs newline-separated; label becomes `Copy URLs (N)`.
- **Recreate fallback modal** — when both clipboard API and `execCommand` fail, opens a modal with the payload pre-selected so `Cmd+C` always works.
- Added an `extFromMime` helper and `base64ToBlob` / `downloadInlineBlock` helpers (the Blob path is later abandoned, see Round 5).

### Round 4 — connectDomains + blob fetch + real anchors (`00138-7wt`)

Symptoms after `00136-vl4`:
- Download buttons didn't fire (the `button.onclick → programmatic a.click()` pattern was being treated as not-a-user-gesture by the sandbox).
- Video showed as "video" alt-text (CSP blocked the URL).
- Re-opening old chat history showed a pending widget ticking to `370:07 elapsed` (server-stamped `started_at` from 6h prior; setInterval kept running forever).

Fixes:
- Populated `_meta.csp.connectDomains` with the same hosts as `resourceDomains` (was `[]`, which per spec disables ALL network fetches). Added `data:` and `blob:` schemes.
- Video render path: try `<video src=URL>` first, on error `fetch(url).blob() → URL.createObjectURL` and swap `video.src`. Blob URLs are sandbox-internal and were expected to bypass media-src CSP.
- Replaced `button.onclick` Download with real `<a download href>` styled as buttons — both main button and per-tile overlays. A real user click on a real anchor should be a real gesture.
- **Stale-pending cap**: pending placeholder now stops the timer at `max(30 min, 2 × est_seconds_max)`, dims the spinner, and shows a yellow hint "this status check is stale — ask Claude to refresh".

### Round 5 — the console-log smoking gun (`00140-49v`)

The user dropped the iframe console output. Three definitive findings:
- `Content Security Policy directive: "media-src 'self' blob: data: https://assets.claude.ai"` — Claude.ai's iframe enforces a HARDCODED CSP. Our `_meta.csp` is silently ignored.
- `Content Security Policy directive: "connect-src 'self'"` — `fetch()` to external hosts is blocked. The Round-4 blob-fetch path can never succeed.
- `Blocked opening '<URL>' in a new window because the request was made in a sandboxed frame whose 'allow-popups' permission is not set` — `window.open()` and `<a target="_blank">` clicks both blocked.

The only escape hatch is the MCP-Apps **`ui/open-link` request** — the iframe sends a JSON-RPC request to the host, the host opens the URL in a new tab outside the sandbox.

Fixes:
- Added `M_OPEN_LINK = "ui/open-link"` const and `MCPAppClient.openLink(url, target)` method that sends the request.
- New `tryOpenLink(url, label)` helper — calls `ui/open-link`, falls back to copying the URL to clipboard, falls back to the Recreate-style modal showing the URL for manual copy.
- Video player rebuilt: tries inline render first; on error swaps to a big "Inline video preview blocked by host — Open in new tab" panel that fires `ui/open-link`. The URL is also displayed below in selectable text as a final manual-copy fallback.
- Per-tile download icons for URL-only tiles (no inline base64) route through `ui/open-link`.
- Dropped the now-impossible fetch→blob path entirely.

### Round 6 — final pivot: Downloads via `ui/open-link` + 7-day signed URLs (`00142-9bh`)

Symptoms after `00140-49v`:
- Video Download fired `ui/open-link` correctly — but the resulting tab showed `<Error><Code>ExpiredToken</Code><Details>The provided token has expired</Details></Error>`. The signed URL was 4h old.
- Image Download: nothing happened. No console error. The data-URI `<a download>` was silently swallowed.

Discovery: **Claude.ai's iframe sandbox lacks the `allow-downloads` permission flag**. Without it, browsers silently block `<a download>` clicks even for `data:` URIs that never cross an origin boundary. The data was right there; the sandbox just refused to save it.

Fixes:
- **Server-side**: bumped `_generate_signed_url` default expiration from `timedelta(hours=4)` to `timedelta(days=7)` — the Firebase/GCS max. URLs survive a week of chat history instead of an afternoon.
- **Client-side**: ALL Download buttons (main + per-tile) now route through `ui/open-link` with the HTTPS URL. The host opens the URL in a new tab outside the sandbox; the user saves from there with right-click → Save As. Anchor `<a download href=data:...>` path removed entirely — the sandbox kills it regardless of inline base64.

### Files affected (rounds 1–6)

| Path | Change |
|---|---|
| `execution/mcp_studio/routes.py` | Added `_meta.csp` + `_meta.permissions` to viewer resource. Populated `connectDomains` with Firebase/Kie hosts + `data:` + `blob:`. |
| `execution/mcp_studio/mcp_protocol.py` | Plumb `_meta` through `resources/list` and `resources/read`. |
| `execution/mcp_studio/tools/content_blocks.py` | `user_visible: bool` flag on every helper; new `_ASSISTANT_ONLY_ANNOTATIONS` constant. |
| `execution/mcp_studio/tools/studio_tools.py` | Inline image blocks for batches use `user_visible=False`. |
| `execution/server.py` | `_generate_signed_url` default expiration `4h → 7d`. |
| `execution/mcp_studio/ui_resources/media_viewer.html` | Major: card scaled 2×, lightbox modal, per-tile hover overlays, all-params badges, Copy URLs (N) for batches, Recreate fallback modal, stale-pending cap, `MCPAppClient.openLink()`, `tryOpenLink()` helper, `buildOpenLinkButton` panel for blocked-inline media, size-changed via `ResizeObserver`, Download routed through `ui/open-link`. |

### Cloud Run revisions (continued)

- `00132-2p5` — declared CSP + permissions + size-changed + batch widget-only
- `00134-vfh` — hidden inline blocks (assistant-only audience), bigger card, working buttons
- `00136-vl4` — lightbox, per-tile actions, all-params badges, batch Copy URL, Recreate modal
- `00138-7wt` — connectDomains populated, blob video fetch, real `<a download>` anchors, stale cap
- `00140-49v` — `ui/open-link` adopted for video and URL-only downloads (sandbox CSP cannot be relaxed from MCP server)
- `00142-9bh` — Download for images also via `ui/open-link`; signed-URL TTL bumped to 7 days

### Permanent constraints learned about Claude.ai's iframe

These are NOT overridable from the MCP server side:

| Constraint | Source |
|---|---|
| `media-src 'self' blob: data: https://assets.claude.ai` | Host CSP — fixed |
| `img-src 'self' blob: data:` (similar) | Host CSP — fixed |
| `connect-src 'self'` | Host CSP — fixed; `fetch()` to external hosts impossible |
| Sandbox lacks `allow-popups` | Host iframe sandbox |
| Sandbox lacks `allow-downloads` | Host iframe sandbox; silently kills `<a download>` |
| `_meta.csp` and `_meta.permissions` | Ignored today (may be honored in future) |
| `app.callTool` from UI resource | Not implemented today (host warning seen in console) |

The viable communication channels are:
- **Receive**: `ui/notifications/tool-result` with full content array (inline base64 OK, audience-tagged blocks OK).
- **Send**: `ui/notifications/size-changed`, `ui/open-link` (escape hatch for external URLs), `ui/notifications/initialized`.

### Open items

- Old chat history with 4h-TTL URLs (generations before `00142-9bh`) shows `ExpiredToken` when Downloaded. No client-side fix possible; user must re-generate.
- `Recreate` still copies the payload because the host doesn't yet honor `app.callTool` from a UI resource — flipped on once Anthropic enables it.
- Video / audio batch generation (`n>1` for non-image kinds) deferred.

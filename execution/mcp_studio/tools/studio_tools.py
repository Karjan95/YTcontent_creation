"""Studio-tab MCP tools: list models, generate, upload reference, poll status."""

import base64
import json
import os
import tempfile
import time

from flask import g

from datetime import datetime, timedelta

from . import content_blocks as cb
from .. import polling
from ..storage_rehost import rehost_many, rehost_to_firebase


def _pending_tasks_coll(deps, project_id):
    """users/{uid}/projects/{pid}/pending_tasks — sidecar to bridge async
    studio_generate calls (which start the task) to studio_get_generation_status
    (which sees the result and must save it to the library)."""
    return (deps["db"].collection("users").document(g.uid)
              .collection("projects").document(project_id)
              .collection("pending_tasks"))


def _write_pending_task(deps, *, project_id, task_key, model_id, backend, kind,
                        prompt, params, inputs, save_to_library, started_at_iso=None):
    firestore = deps["firestore"]
    doc = {
        "task_key": task_key,
        "model_id": model_id,
        "backend": backend,
        "kind": kind,
        "prompt": prompt or "",
        "params": params or {},
        "inputs": inputs or {},
        "save_to_library": bool(save_to_library),
        "started_at": firestore.SERVER_TIMESTAMP,
        "started_at_iso": started_at_iso or (datetime.utcnow().isoformat() + "Z"),
        "created_by": g.uid,
    }
    try:
        _pending_tasks_coll(deps, project_id).document(_safe_key(task_key)).set(doc)
    except Exception as e:
        print(f"[MCP] _write_pending_task failed for {task_key}: {e}")


def _read_pending_task(deps, *, project_id, task_key):
    """Read the pending_tasks doc WITHOUT deleting it. For pending-status polls."""
    if not project_id or not task_key:
        return None
    try:
        ref = _pending_tasks_coll(deps, project_id).document(_safe_key(task_key))
        snap = ref.get()
        if not snap.exists:
            return None
        return snap.to_dict() or {}
    except Exception as e:
        print(f"[MCP] _read_pending_task failed for {task_key}: {e}")
        return None


def _enrich_sc(sc, *, model_id=None, prompt=None, inputs=None, params=None,
               kind=None, tool_label="studio_generate", started_at_iso=None):
    """Add Higgsfield-style metadata to structuredContent so the viewer can
    render header/prompt/badges. Mutates and returns sc."""
    if sc is None:
        sc = {}
    if tool_label is not None:
        sc.setdefault("tool_label", tool_label)
    if model_id:
        sc.setdefault("model_id", model_id)
    if kind:
        sc.setdefault("kind", kind)
    p = prompt
    if p is None and inputs is not None:
        p = (inputs or {}).get("prompt") or (inputs or {}).get("text") or ""
    if p:
        sc.setdefault("prompt", p)
    pr = params or {}
    if pr.get("aspect_ratio"):
        sc.setdefault("aspect_ratio", pr["aspect_ratio"])
    if kind == "video" and pr.get("duration_seconds"):
        sc.setdefault("duration_seconds", pr["duration_seconds"])
    if kind == "video" and pr.get("duration"):
        sc.setdefault("duration_seconds", pr["duration"])
    if kind == "video":
        sc.setdefault("audio_enabled", bool(pr.get("generate_audio", True)))
    if started_at_iso:
        sc.setdefault("started_at", started_at_iso)
    # Echo inputs/params so the viewer's Recreate button can rebuild the call.
    if inputs is not None:
        sc.setdefault("inputs_echo", inputs)
    if params is not None:
        sc.setdefault("params_echo", params)
    return sc


def _consume_pending_task(deps, *, project_id, task_key):
    """Read the pending_tasks doc and delete it. Returns the doc dict or None."""
    if not project_id or not task_key:
        return None
    try:
        ref = _pending_tasks_coll(deps, project_id).document(_safe_key(task_key))
        snap = ref.get()
        if not snap.exists:
            return None
        data = snap.to_dict() or {}
        try:
            ref.delete()
        except Exception:
            pass
        return data
    except Exception as e:
        print(f"[MCP] _consume_pending_task failed for {task_key}: {e}")
        return None


def _safe_key(task_key: str) -> str:
    """Firestore document IDs can't contain '/'. Replace with '__'."""
    return (task_key or "").replace("/", "__")


_BACKEND_KINDS = {
    "kie_generic": "kie",
    "kie_veo3": "kie",
    "kie_runway": "kie",
    "google_gemini_image": "sync",
    "google_imagen": "sync",
    "google_veo": "veo",
    "google_tts": "sync",
    "google_lyria": "sync",
}

# Estimated completion windows for the polling hint in async responses.
_EST_SECONDS = {
    "kie_image": (15, 45),
    "kie_video": (60, 180),
    "veo": (90, 240),
    "seedance": (60, 180),
}

# Per-kind polling cadence — long waits to slash token waste on status polls.
# Claude treats these as a floor; the viewer renders its own client-side timer.
_RETRY_AFTER = {
    "kie_image": 12,
    "kie_video": 180,
    "veo": 240,
    "seedance": 180,
}
_FIRST_POLL_AFTER = {
    "kie_image": 12,
    "kie_video": 90,
    "veo": 150,
    "seedance": 90,
}

# Shared MCP App resource URI — tools that return media point at this so the
# host renders the result inline.
_VIEWER_META = {"ui": {"resourceUri": "ui://studio/media-viewer"}}


_KIND_FOLDER = {"image": "image", "video": "video", "audio": "audio"}
_KIND_DEFAULT_MIME = {
    "image": "image/png", "video": "video/mp4", "audio": "audio/mpeg",
}
_KIND_DEFAULT_EXT = {"image": "png", "video": "mp4", "audio": "mp3"}


def build_handlers(deps: dict) -> dict:
    upload_to_storage = deps["upload_to_storage"]
    create_signed_put_url = deps.get("create_signed_put_url")

    # ──────────────── studio_list_models ────────────────

    def _list_models(args):
        from model_schemas import get_provider_groups
        providers = get_provider_groups()
        # Compact summary only — full schema dump removed to save tokens.
        # If a caller needs a specific model's schema, look it up on demand.
        lines = []
        ids = []
        for prov in providers:
            for m in prov.get("models", []):
                ids.append(m["id"])
            names = ", ".join(m["id"] for m in prov.get("models", [])[:6])
            count = len(prov.get("models", []))
            more = f" (+{count - 6} more)" if count > 6 else ""
            prov_name = prov.get("provider") or prov.get("name") or "Provider"
            lines.append(f"• {prov_name} ({count}): {names}{more}")
        summary = "Studio models available:\n" + "\n".join(lines)
        return {
            "content": [cb.text_block(summary)],
            "structuredContent": {"model_ids": ids},
            "isError": False,
        }

    # ──────────────── studio_generate ────────────────

    def _generate(args):
        # Lazy import the live dispatchers from server.py. They read from g.uid
        # / g.api_key / g.kie_api_key — already populated by require_mcp_auth.
        from server import (
            _studio_dispatch_kie_generic,
            _studio_dispatch_kie_veo,
            _studio_dispatch_kie_runway,
            _studio_dispatch_google_image,
            _studio_dispatch_google_veo,
            _studio_dispatch_google_tts,
            _studio_dispatch_google_lyria,
        )
        from model_schemas import get_schema

        model_id = args.get("model_id", "").strip()
        inputs = args.get("inputs") or {}
        params = args.get("params") or {}
        project_id = args.get("project_id")
        save_to_library = bool(args.get("save_to_library", True))
        n = args.get("n")
        try:
            n = int(n) if n is not None else 1
        except (TypeError, ValueError):
            n = 1
        n = max(1, min(4, n))

        schema = get_schema(model_id)
        if not schema:
            return _err(f"Unknown model: {model_id}")
        backend = schema["backend"]

        # project_id is required — silent auto-pick produced wrong-project
        # surprises in real sessions, so we now force Claude to ask.
        if not project_id:
            return _err(
                "project_id is required. Call studio_list_projects to see the "
                "user's projects, ask which one to target, then re-call "
                "studio_generate with project_id set.")

        # Image batch: only Imagen/Gemini image backends support num_images.
        # For other backends, reject n>1 explicitly instead of silently no-opping.
        if n > 1:
            if backend in ("google_gemini_image", "google_imagen"):
                params = {**params, "num_images": n}
            elif backend == "kie_generic" and (schema.get("kind") or "").startswith("image"):
                # Kie image: no native batch; we'll return 1 and note it in the caption.
                pass
            else:
                return _err(
                    f"n={n} requested but batch generation (n>1) is only "
                    f"supported for image backends in this version. Pass n=1 "
                    f"or omit n.")

        dispatchers = {
            "kie_generic": lambda: _studio_dispatch_kie_generic(schema, inputs, params, project_id),
            "kie_veo3": lambda: _studio_dispatch_kie_veo(schema, inputs, params, project_id),
            "kie_runway": lambda: _studio_dispatch_kie_runway(schema, inputs, params, project_id),
            "google_gemini_image": lambda: _studio_dispatch_google_image(
                schema, inputs, params, project_id, native=True),
            "google_imagen": lambda: _studio_dispatch_google_image(
                schema, inputs, params, project_id, native=False),
            "google_veo": lambda: _studio_dispatch_google_veo(schema, inputs, params, project_id),
            "google_tts": lambda: _studio_dispatch_google_tts(schema, inputs, params, project_id),
            "google_lyria": lambda: _studio_dispatch_google_lyria(schema, inputs, params, project_id),
        }
        if backend not in dispatchers:
            return _err(f"Backend not yet implemented: {backend}")

        response = dispatchers[backend]()
        payload, status = _unwrap(response)
        if status >= 400 or payload.get("error"):
            return _err(payload.get("error") or f"Generation failed (HTTP {status})")

        blocks = []
        structured = None
        if backend in ("google_gemini_image", "google_imagen"):
            urls = payload.get("image_urls") or ([payload["image_url"]] if payload.get("image_url") else [])
            primary = urls[0] if urls else None
            blocks.append(cb.text_block(
                f"Generated {len(urls)} image(s) via {model_id}. "
                f"Primary URL: {primary or '(none)'}"))
            # Inline image content blocks. For n=1 keep them user-visible (the
            # chat renders the inline image native, widget overlays). For n>1
            # mark them assistant-only so Claude.ai's chat surface won't render
            # them — the widget still receives the full content array and reads
            # the base64 data directly, sidestepping iframe-CSP blocks on the
            # HTTPS Firebase URLs.
            for u in urls[:4]:
                if u:
                    blocks.append(cb.image_block_from_url(
                        u, fallback_name="generated.png",
                        user_visible=(len(urls) == 1)))
            _maybe_save(args, payload, project_id, save_to_library, kind="image",
                        urls=urls, model_id=model_id, deps=deps)
            structured = _enrich_sc(
                {"kind": "image", "urls": urls, "primary_url": primary,
                 "image_url": primary, "image_urls": urls,
                 "project_id": project_id},
                model_id=model_id, inputs=inputs, params=params, kind="image")
        elif backend == "google_tts":
            url = payload.get("audio_url")
            blocks.append(cb.text_block(
                f"Generated TTS audio via {model_id}. URL: {url}"))
            blocks.append(cb.audio_block_from_url(url, fallback_name="tts.mp3"))
            _maybe_save(args, payload, project_id, save_to_library, kind="audio",
                        urls=[url], model_id=model_id, deps=deps)
            structured = _enrich_sc(
                {"kind": "audio", "audio_url": url, "primary_url": url,
                 "urls": [url], "project_id": project_id},
                model_id=model_id, inputs=inputs, params=params, kind="audio")
        elif backend == "google_lyria":
            url = payload.get("audio_url")
            blocks.append(cb.text_block(
                f"Generated music via {model_id}. URL: {url}"))
            blocks.append(cb.audio_block_from_url(url, fallback_name="lyria.mp3"))
            _maybe_save(args, payload, project_id, save_to_library, kind="audio",
                        urls=[url], model_id=model_id, deps=deps)
            structured = _enrich_sc(
                {"kind": "audio", "audio_url": url, "primary_url": url,
                 "urls": [url], "project_id": project_id},
                model_id=model_id, inputs=inputs, params=params, kind="audio")
        elif backend == "google_veo":
            op = payload.get("operation")
            op_name = op.get("name") if isinstance(op, dict) else str(op)
            lo, hi = _EST_SECONDS["veo"]
            task_key = f"veo:{op_name}"
            started_iso = datetime.utcnow().isoformat() + "Z"
            _write_pending_task(
                deps, project_id=project_id, task_key=task_key,
                model_id=model_id, backend="veo", kind="video",
                prompt=(inputs.get("prompt") or "").strip(),
                params=params, inputs=inputs, save_to_library=save_to_library,
                started_at_iso=started_iso)
            blocks.append(cb.text_block(
                f"Started Veo job. Typical completion: {lo}-{hi}s. "
                f"First check in ~{_FIRST_POLL_AFTER['veo']}s; then wait "
                f"{_RETRY_AFTER['veo']}s between checks. Use backend='veo' "
                f"task_id={json.dumps(op_name)} "
                f"project_id={json.dumps(project_id)}."))
            structured = _enrich_sc(
                {"status": "pending", "task_id": op_name, "task_key": task_key,
                 "backend": "veo", "operation": op,
                 "est_seconds_min": lo, "est_seconds_max": hi,
                 "first_poll_after_sec": _FIRST_POLL_AFTER["veo"],
                 "retry_after_seconds": _RETRY_AFTER["veo"],
                 "project_id": project_id},
                model_id=model_id, inputs=inputs, params=params, kind="video",
                started_at_iso=started_iso)
        elif backend in ("kie_generic", "kie_veo3", "kie_runway"):
            task_id = payload.get("task_id") or payload.get("taskId")
            if backend == "kie_generic" and payload.get("image_urls"):
                # Synchronous Kie image return — re-host and persist now.
                raw_urls = payload["image_urls"]
                urls = rehost_many(raw_urls, kind="image", project_id=project_id,
                                   upload_to_storage=upload_to_storage)
                primary = urls[0] if urls else None
                note = ""
                if n > 1 and len(urls) == 1:
                    note = (f" (n={n} requested but this Kie model returned 1 "
                            f"image; native batch unsupported)")
                blocks.append(cb.text_block(
                    f"Kie returned {len(urls)} image(s) via {model_id} "
                    f"(mirrored to Firebase). Primary URL: {primary or '(none)'}"
                    f"{note}"))
                # Inline image blocks — assistant-only for batches so the widget
                # can read the base64 but Claude.ai chat doesn't double-render.
                for u in urls[:4]:
                    if u:
                        blocks.append(cb.image_block_from_url(
                            u, fallback_name="kie.png",
                            user_visible=(len(urls) == 1)))
                payload["image_urls"] = urls
                _maybe_save(args, payload, project_id, save_to_library, kind="image",
                            urls=urls, model_id=model_id, deps=deps)
                structured = _enrich_sc(
                    {"kind": "image", "urls": urls,
                     "primary_url": primary, "image_url": primary,
                     "image_urls": urls, "project_id": project_id},
                    model_id=model_id, inputs=inputs, params=params, kind="image")
            elif task_id:
                kind_hint = "kie_video" if "video" in (schema.get("kind") or "") else "kie_image"
                lo, hi = _EST_SECONDS[kind_hint]
                guess_kind = "video" if kind_hint == "kie_video" else "image"
                task_key = f"kie:{task_id}"
                retry = _RETRY_AFTER[kind_hint]
                first = _FIRST_POLL_AFTER[kind_hint]
                started_iso = datetime.utcnow().isoformat() + "Z"
                _write_pending_task(
                    deps, project_id=project_id, task_key=task_key,
                    model_id=model_id, backend="kie", kind=guess_kind,
                    prompt=(inputs.get("prompt") or inputs.get("text") or "").strip(),
                    params=params, inputs=inputs,
                    save_to_library=save_to_library,
                    started_at_iso=started_iso)
                blocks.append(cb.text_block(
                    f"Started Kie task {task_id} via {model_id}. Typical "
                    f"completion: {lo}-{hi}s. First check in ~{first}s; then "
                    f"wait {retry}s between checks. Use backend='kie' "
                    f"task_id={json.dumps(task_id)} "
                    f"project_id={json.dumps(project_id)}."))
                structured = _enrich_sc(
                    {"status": "pending", "task_id": task_id, "task_key": task_key,
                     "backend": "kie",
                     "est_seconds_min": lo, "est_seconds_max": hi,
                     "first_poll_after_sec": first,
                     "retry_after_seconds": retry,
                     "project_id": project_id},
                    model_id=model_id, inputs=inputs, params=params,
                    kind=guess_kind, started_at_iso=started_iso)
            else:
                blocks.append(cb.text_block(f"Kie response: {json.dumps(payload)[:1500]}"))
        else:
            blocks.append(cb.text_block(f"Response: {json.dumps(payload)[:2000]}"))

        result = {"content": blocks, "isError": False}
        if structured is not None:
            result["structuredContent"] = structured
        return result

    # ──────────────── studio_get_generation_status ────────────────

    def _get_status(args):
        backend = (args.get("backend") or "").strip().lower()
        task_id = args.get("task_id")
        project_id = args.get("project_id")
        if backend == "kie":
            if not getattr(g, "kie_api_key", None):
                return _err("No Kie API key configured for this user.")
            if not task_id:
                return _err("task_id required for backend='kie'")
            poll_result = polling.poll_kie_task_once(task_id, g.kie_api_key)
            task_key = f"kie:{task_id}"
        elif backend == "veo":
            if not getattr(g, "api_key", None):
                return _err("No Gemini API key configured for this user.")
            op = task_id if isinstance(task_id, dict) else {"name": task_id}
            poll_result = polling.poll_veo_op_once(op, g.api_key)
            op_name = op.get("name") if isinstance(op, dict) else str(task_id)
            task_key = f"veo:{op_name}"
        elif backend == "seedance":
            return _err("Use studio_get_sequence_status for Seedance sequences.")
        else:
            return _err("backend must be 'kie' or 'veo'")

        status = poll_result.get("status")
        if status == "pending":
            # Read (don't consume) the sidecar so the viewer can render the
            # full card (prompt/model/badges + live elapsed timer) on every
            # pending poll.
            pending = _read_pending_task(deps, project_id=project_id,
                                          task_key=task_key) or {}
            kind_hint = "kie_video" if (pending.get("kind") == "video" and backend == "kie") else (
                "kie_image" if backend == "kie" else "veo")
            retry = _RETRY_AFTER.get(kind_hint, 60)
            lo, hi = _EST_SECONDS.get(kind_hint, (60, 180))
            sc = _enrich_sc(
                {"status": "pending",
                 "retry_after_seconds": retry,
                 "est_seconds_min": lo, "est_seconds_max": hi,
                 "task_key": task_key,
                 "backend": backend,
                 "project_id": project_id},
                model_id=pending.get("model_id"),
                prompt=pending.get("prompt"),
                inputs=pending.get("inputs"),
                params=pending.get("params"),
                kind=pending.get("kind") or ("video" if backend == "veo" else None),
                tool_label="studio_get_generation_status",
                started_at_iso=pending.get("started_at_iso"))
            return {
                "content": [cb.text_block(
                    f"Status: pending. Wait at least {retry}s before the next "
                    f"studio_get_generation_status call. Aggressive polling "
                    f"wastes tokens and quota.")],
                "structuredContent": sc,
                "isError": False,
            }
        if status == "failed":
            pending = _read_pending_task(deps, project_id=project_id,
                                          task_key=task_key) or {}
            sc = _enrich_sc(
                {"status": "failed",
                 "error": poll_result.get("error"),
                 "task_key": task_key,
                 "project_id": project_id},
                model_id=pending.get("model_id"),
                prompt=pending.get("prompt"),
                inputs=pending.get("inputs"),
                params=pending.get("params"),
                kind=pending.get("kind"),
                tool_label="studio_get_generation_status")
            return {
                "content": [cb.text_block(
                    f"Status: failed. {poll_result.get('error') or ''}")],
                "structuredContent": sc,
                "isError": True,
            }

        # ──── Completed: rehost, save to library, build chat blocks ────
        raw_urls = poll_result.get("result_urls") or (
            [poll_result["video_url"]] if poll_result.get("video_url") else [])

        # Try to pull metadata from the pending_tasks sidecar so the saved
        # asset carries the original prompt/model_id, and so we know whether
        # the user opted out of save_to_library.
        pending = _consume_pending_task(deps, project_id=project_id,
                                         task_key=task_key) or {}
        recorded_kind = pending.get("kind")
        model_id = pending.get("model_id") or "(unknown)"
        prompt = pending.get("prompt") or ""
        params = pending.get("params") or {}
        inputs_origin = pending.get("inputs") or {}
        save_to_library = pending.get("save_to_library", True)

        urls = []
        kinds = []
        for u in raw_urls:
            lower = (u or "").lower().split("?")[0]
            if recorded_kind in ("image", "video", "audio"):
                kind = recorded_kind
            elif any(lower.endswith(ext) for ext in (".mp4", ".webm", ".mov")):
                kind = "video"
            elif any(lower.endswith(ext) for ext in (".mp3", ".wav", ".ogg", ".m4a")):
                kind = "audio"
            else:
                kind = "image"
            kinds.append(kind)
            urls.append(rehost_to_firebase(
                u, kind=kind, project_id=project_id,
                upload_to_storage=upload_to_storage))

        primary = urls[0] if urls else None
        primary_kind = kinds[0] if kinds else "image"

        # Save to library — by kind. Reuses _maybe_save's Firestore writer.
        if save_to_library and project_id and urls:
            save_payload = {"backend": backend}
            save_args = {"inputs": {"prompt": prompt}, "params": params}
            same_kind_urls = [u for k, u in zip(kinds, urls) if k == primary_kind]
            _maybe_save(save_args, save_payload, project_id, True,
                        kind=primary_kind, urls=same_kind_urls,
                        model_id=model_id, deps=deps)

        # Chat blocks — caption + URL up top so Claude can thread it; then
        # inline image/audio. Videos render via the MCP App viewer reading
        # structuredContent.video_url (the chat client rejects resource_link
        # for video).
        blocks = [cb.text_block(
            f"Status: completed. {primary_kind} via {model_id}. "
            f"Primary URL: {primary or '(none)'}")]
        for kind, u in zip(kinds, urls):
            base = os.path.basename((u or "").split("?")[0]) or kind
            if kind == "image":
                blocks.append(cb.image_block_from_url(u, fallback_name=base))
            elif kind == "audio":
                blocks.append(cb.audio_block_from_url(u, fallback_name=base))
            # video: intentionally NO content block — relies on viewer +
            # structuredContent.video_url. Claude.ai rejects resource_link
            # video with a stock "not supported" message.

        structured = {
            "status": "completed",
            "kind": primary_kind,
            "urls": urls,
            "primary_url": primary,
            "project_id": project_id,
            "task_key": task_key,
        }
        if primary_kind == "video":
            structured["video_url"] = primary
        elif primary_kind == "image":
            structured["image_url"] = primary
            structured["image_urls"] = [u for k, u in zip(kinds, urls) if k == "image"]
        elif primary_kind == "audio":
            structured["audio_url"] = primary
        structured = _enrich_sc(
            structured,
            model_id=model_id, prompt=prompt, inputs=inputs_origin,
            params=params, kind=primary_kind,
            tool_label="studio_get_generation_status")
        return {"content": blocks, "structuredContent": structured,
                "isError": False}

    # ──────────────── studio_create_upload_url ────────────────

    def _create_upload_url(args):
        if create_signed_put_url is None:
            return _err("Signed upload URLs are not configured on this server.")
        kind = (args.get("kind") or "").strip().lower()
        if kind not in ("image", "video", "audio"):
            return _err("kind must be image, video, or audio")
        project_id = args.get("project_id")
        if not project_id:
            return _err("project_id is required")
        subtype = (args.get("type") or kind).strip()
        filename = (args.get("filename") or "").strip() or f"upload.{_KIND_DEFAULT_EXT[kind]}"
        mime_type = (args.get("mime_type") or "").strip() or _KIND_DEFAULT_MIME[kind]

        # Same blob layout as studio_upload_reference / web UI reference uploads.
        safe_name = f"{subtype}_{int(time.time())}_{os.urandom(3).hex()}_{os.path.basename(filename)}"
        blob_path = f"references/{project_id}/{subtype}/{safe_name}"

        put_url, get_url = create_signed_put_url(blob_path, mime_type, 900)
        if not put_url or not get_url:
            return _err("Failed to generate signed upload URL")

        instructions = (
            f"Upload the file to the signed URL with HTTP PUT and a matching "
            f"Content-Type header, then pass `public_url` to studio_generate "
            f"as a reference. Example:\n"
            f"  curl -X PUT --data-binary @{filename} "
            f"-H 'Content-Type: {mime_type}' '<upload_url>'\n"
            f"After PUT returns 200, the file is accessible at public_url for ~4h."
        )
        payload = {
            "upload_url": put_url,
            "public_url": get_url,
            "blob_path": blob_path,
            "mime_type": mime_type,
            "expires_in_seconds": 900,
            "instructions": instructions,
        }
        return {
            "content": [cb.text_block(json.dumps(payload, indent=2))],
            "structuredContent": payload,
            "isError": False,
        }

    # ──────────────── studio_upload_reference ────────────────

    def _upload_reference(args):
        kind = (args.get("kind") or "").strip().lower()
        if kind not in ("image", "video", "audio"):
            return _err("kind must be image, video, or audio")
        source = (args.get("source") or "url").strip().lower()
        data_str = args.get("data") or ""
        project_id = args.get("project_id")
        filename = args.get("filename") or f"{kind}.bin"
        subtype = (args.get("type") or kind).strip()

        if not data_str:
            return _err("data is required")

        # Resolve to raw bytes
        if source == "url":
            raw, mime = cb.fetch_bytes(data_str, max_bytes=64 * 1024 * 1024)
            if raw is None:
                return _err("Could not fetch URL (size cap or fetch failed)")
        elif source == "base64":
            if data_str.startswith("data:"):
                header, b64 = data_str.split(",", 1)
                mime = header.split(":")[1].split(";")[0] if ":" in header else None
            else:
                b64 = data_str
                mime = None
            try:
                raw = base64.b64decode(b64)
            except Exception as e:
                return _err(f"Invalid base64: {e}")
        else:
            return _err("source must be 'url' or 'base64'")

        ext_default = {"image": "png", "video": "mp4", "audio": "mp3"}[kind]
        ext = filename.rsplit(".", 1)[-1] if "." in filename else ext_default
        safe_name = f"{subtype}_{int(time.time())}_{filename.rsplit('.', 1)[0]}.{ext}"
        tmp_dir = tempfile.mkdtemp()
        tmp_path = os.path.join(tmp_dir, safe_name)
        try:
            with open(tmp_path, "wb") as f:
                f.write(raw)
            remote_folder = (f"references/{project_id}/{subtype}"
                             if project_id else f"references/{subtype}")
            url, blob_path = upload_to_storage(tmp_path, remote_folder, return_path=True)
        finally:
            try:
                os.unlink(tmp_path)
                os.rmdir(tmp_dir)
            except Exception:
                pass
        if not url:
            return _err("Upload to Firebase Storage failed")
        return [cb.text_block(json.dumps({"url": url, "path": blob_path, "size_bytes": len(raw)}))]

    return {
        "studio_list_models": {
            "description": "List all Studio models with their providers and parameter schemas. "
                           "Use this to discover model_ids before calling studio_generate.",
            "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
            "handler": _list_models,
        },
        "studio_generate": {
            "description": "Generate image/video/audio with any Studio model. "
                           "project_id is required (call studio_list_projects first). "
                           "Sync backends return media inline; async backends (Veo, Kie video) "
                           "return a task_id — poll with studio_get_generation_status. "
                           "Chain calls: pass the prior result's structuredContent.primary_url "
                           "to the next call's inputs.image_url / inputs.first_frame. "
                           "For reference media >50KB: use studio_create_upload_url, "
                           "PUT via curl, then pass the public_url back. "
                           "Pass n=1..4 for image variants (Imagen/Gemini only).",
            "_meta": _VIEWER_META,
            "inputSchema": {
                "type": "object",
                "properties": {
                    "model_id": {"type": "string", "description": "Model id from studio_list_models"},
                    "inputs": {"type": "object", "additionalProperties": True,
                                "description": "Prompt + references per model schema"},
                    "params": {"type": "object", "additionalProperties": True,
                                "description": "aspect_ratio, duration_seconds, resolution, etc."},
                    "project_id": {"type": "string"},
                    "n": {"type": "integer", "minimum": 1, "maximum": 4, "default": 1,
                            "description": "Number of image variants (Imagen/Gemini only). Capped at 4."},
                    "save_to_library": {"type": "boolean", "default": True},
                },
                "required": ["model_id"],
                "additionalProperties": False,
            },
            "handler": _generate,
        },
        "studio_get_generation_status": {
            "description": "Check a long-running studio_generate task. Returns media inline "
                           "when complete, or status='pending'/'failed'. "
                           "Wait at least structuredContent.retry_after_seconds before polling "
                           "again (Kie image 12s, Kie video 180s, Veo 240s). Polling sooner "
                           "wastes tokens and quota — the viewer shows the user a live timer; "
                           "you don't need to check often. "
                           "On completion, pass structuredContent.primary_url to the next "
                           "studio_generate as a reference.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "backend": {"type": "string", "enum": ["kie", "veo"]},
                    "task_id": {
                        "description": "For backend=kie: the Kie task_id (string). For "
                                       "backend=veo: the operation name (string) OR the full "
                                       "operation object returned by studio_generate.",
                    },
                    "project_id": {"type": "string",
                                    "description": "Project to scope the re-hosted asset under."},
                },
                "required": ["backend", "task_id"],
                "additionalProperties": False,
            },
            "_meta": _VIEWER_META,
            "handler": _get_status,
        },
        "studio_create_upload_url": {
            "description": "Get a short-lived signed PUT URL to upload a reference file "
                           "directly to Firebase Storage. **This is the right path for any "
                           "file >50KB or any video/audio** — it avoids the base64-in-args "
                           "size limit that breaks studio_upload_reference for large files. "
                           "Workflow: call this tool → run `curl -X PUT --data-binary @<file> "
                           "-H 'Content-Type: <mime>' '<upload_url>'` from your sandbox → on "
                           "200 response, pass the returned `public_url` to studio_generate "
                           "as a reference (in inputs.image_url, inputs.image_urls, "
                           "inputs.reference_images, inputs.first_frame, etc., per the "
                           "model's schema).",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "kind": {"type": "string", "enum": ["image", "video", "audio"]},
                    "project_id": {"type": "string"},
                    "filename": {"type": "string",
                                  "description": "Original filename (used for blob naming)."},
                    "mime_type": {"type": "string",
                                   "description": "Exact MIME type the PUT will send "
                                                  "(e.g. image/jpeg, video/mp4). Must match "
                                                  "the Content-Type header on upload."},
                    "type": {"type": "string",
                              "description": "Subfolder/category (e.g. 'style', 'character'). "
                                             "Defaults to kind."},
                },
                "required": ["kind", "project_id"],
                "additionalProperties": False,
            },
            "handler": _create_upload_url,
        },
        "studio_upload_reference": {
            "description": "Upload a small (<50KB) reference image to Firebase Storage so it "
                           "can be used as a reference input in studio_generate calls. Source "
                           "can be a public URL or a base64 data string. **For larger files "
                           "or any video/audio, use studio_create_upload_url instead** — "
                           "base64 payloads larger than ~50KB blow up Claude's tool-call "
                           "context.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "kind": {"type": "string", "enum": ["image", "video", "audio"]},
                    "source": {"type": "string", "enum": ["url", "base64"], "default": "url"},
                    "data": {"type": "string", "description": "URL or base64 (data URI accepted)"},
                    "project_id": {"type": "string"},
                    "filename": {"type": "string"},
                    "type": {"type": "string",
                              "description": "Subfolder/category, e.g. 'style', 'character'. Defaults to kind."},
                },
                "required": ["kind", "data"],
                "additionalProperties": False,
            },
            "handler": _upload_reference,
        },
    }


def _err(msg: str) -> dict:
    return {"content": [cb.text_block(msg)], "isError": True}


def _unwrap(response):
    """Convert a Flask response (or (response, status) tuple) into (dict, status_code)."""
    if isinstance(response, tuple):
        resp, status = response[0], response[1]
    else:
        resp, status = response, 200
    try:
        payload = resp.get_json(silent=True) or {}
    except Exception:
        payload = {}
    if hasattr(resp, "status_code"):
        status = resp.status_code
    return payload, status


def _maybe_save(args, payload, project_id, save_to_library, *, kind, urls, model_id, deps):
    """Persist generated assets to the project asset library when requested."""
    if not save_to_library or not project_id or not urls:
        return
    db = deps["db"]
    firestore = deps["firestore"]
    from datetime import datetime as _dt
    for u in urls:
        doc = {
            "kind": kind,
            "url": u,
            "model_id": model_id,
            "provider": payload.get("backend") or "",
            "prompt": (args.get("inputs") or {}).get("prompt", ""),
            "params": args.get("params") or {},
            "favorite": False,
            "created_by": g.uid,
            "ts": firestore.SERVER_TIMESTAMP,
        }
        try:
            (db.collection("users").document(g.uid)
                .collection("projects").document(project_id)
                .collection("assets").document().set(doc))
        except Exception:
            pass

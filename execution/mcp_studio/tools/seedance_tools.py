"""Seedance MCP tools: kick off and check sequences.

Uses kie_client + seedance_studio.storage directly so we don't touch the
existing HTTP route handlers.
"""

import json
import os

from flask import g

from . import content_blocks as cb
from ..storage_rehost import rehost_to_firebase


_VIEWER_META = {"ui": {"resourceUri": "ui://studio/media-viewer"}}


def _seedance_sc(seq, *, status, tool_label, **extra):
    """Build a Higgsfield-card-style structuredContent for a Seedance sequence."""
    anim = (seq or {}).get("animation") or {}
    sc = {
        "tool_label": tool_label,
        "status": status,
        "kind": "video",
        "model_id": anim.get("model") or seq.get("model") or "seedance-2",
        "prompt": seq.get("prompt") or seq.get("seedance_prompt") or "",
        "aspect_ratio": seq.get("aspect_ratio"),
        "duration_seconds": seq.get("duration_sec"),
        "audio_enabled": bool(seq.get("generate_audio", True)),
        "sequence_id": seq.get("id"),
        "started_at": anim.get("started_at"),
    }
    sc.update({k: v for k, v in extra.items() if v is not None})
    return {k: v for k, v in sc.items() if v not in (None, "")}


def build_handlers(deps: dict) -> dict:
    upload_to_storage = deps["upload_to_storage"]

    def _animate(args):
        if not getattr(g, "kie_api_key", None):
            return _err("Kie.ai API key required. Add it in Studio Settings.")
        project_id = args.get("project_id")
        prompt = (args.get("prompt") or "").strip()
        grid_url = (args.get("grid_url") or "").strip()
        char_ref_urls = args.get("char_ref_urls") or []
        aspect_ratio = args.get("aspect_ratio", "16:9")
        duration = int(args.get("duration", 15))
        resolution = args.get("resolution", "720p")
        generate_audio = bool(args.get("generate_audio", True))
        title = args.get("title")
        model = args.get("model", "seedance-2")
        if not project_id or not prompt or not grid_url:
            return _err("project_id, prompt, and grid_url are required")
        if model not in ("seedance-2", "seedance-2-fast"):
            return _err("model must be seedance-2 or seedance-2-fast")

        from kie_client import (
            upload_image_url as kie_upload_image,
            create_task as kie_create_task,
        )
        from seedance_studio.schemas import (
            new_sequence, STATUS_ANIMATING, STATUS_FAILED, now_iso,
        )
        from seedance_studio import storage

        seq = new_sequence(
            prompt=prompt, grid_url=grid_url, char_ref_urls=char_ref_urls,
            aspect_ratio=aspect_ratio, duration_sec=duration, title=title,
        )
        storage.append_sequence(g.uid, project_id, seq)

        up = kie_upload_image(grid_url, g.kie_api_key)
        if not up.get("success"):
            storage.update_sequence(g.uid, project_id, seq["id"], {
                "status": STATUS_FAILED,
                "animation": {"status": "failed", "error": up.get("error"),
                              "started_at": now_iso()},
            })
            return _err(f"KIE grid upload failed: {up.get('error')}")
        cdn_grid = up["url"]

        cdn_refs = []
        for ref_url in (char_ref_urls or [])[:9]:
            r = kie_upload_image(ref_url, g.kie_api_key)
            cdn_refs.append(r["url"] if r.get("success") else ref_url)

        kie_inputs = {
            "image_urls": [cdn_grid] + cdn_refs,
            "prompt": prompt,
            "aspect_ratio": aspect_ratio,
            "duration": duration,
            "resolution": resolution,
            "generate_audio": generate_audio,
        }
        task = kie_create_task(model, prompt, g.kie_api_key,
                               image_urls=kie_inputs["image_urls"],
                               aspect_ratio=aspect_ratio,
                               duration=duration,
                               resolution=resolution,
                               generate_audio=generate_audio)
        if not task.get("success"):
            storage.update_sequence(g.uid, project_id, seq["id"], {
                "status": STATUS_FAILED,
                "animation": {"status": "failed", "error": task.get("error"),
                              "started_at": now_iso()},
            })
            return _err(f"KIE task creation failed: {task.get('error')}")

        task_id = task.get("task_id") or task.get("taskId")
        started_iso = now_iso()
        # Persist generate_audio so the status card can show the badge.
        seq["generate_audio"] = generate_audio
        seq["model"] = model
        storage.update_sequence(g.uid, project_id, seq["id"], {
            "status": STATUS_ANIMATING,
            "generate_audio": generate_audio,
            "model": model,
            "animation": {
                "task_id": task_id,
                "operation_name": f"kie:{task_id}",
                "status": "in_progress",
                "model": model,
                "started_at": started_iso,
            },
        })
        # Refresh seq snapshot with animation.started_at so the viewer can tick
        # elapsed time from the same anchor as later status polls.
        seq["animation"] = {
            "task_id": task_id, "operation_name": f"kie:{task_id}",
            "status": "in_progress", "model": model, "started_at": started_iso,
        }
        sc = _seedance_sc(
            seq, status="pending", tool_label="studio_animate_sequence",
            task_id=task_id, project_id=project_id,
            est_seconds_min=60, est_seconds_max=180,
            first_poll_after_sec=90, retry_after_seconds=180)
        return {
            "content": [cb.text_block(
                f"Started Seedance {model} sequence {seq['id']}. Typical "
                f"completion 60-180s. First check ~90s; then wait 180s between "
                f"checks.")],
            "structuredContent": sc,
            "isError": False,
        }

    def _status(args):
        project_id = args.get("project_id")
        sequence_id = args.get("sequence_id")
        if not project_id or not sequence_id:
            return _err("project_id and sequence_id are required")
        if not getattr(g, "kie_api_key", None):
            return _err("Kie.ai API key required.")

        from kie_client import poll_task as kie_poll_task, download_result as kie_download_result
        from seedance_studio import storage
        from seedance_studio.schemas import STATUS_SUCCEEDED, STATUS_FAILED, now_iso

        data = storage.get_seedance_data(g.uid, project_id) or {}
        sequences = data.get("sequences") or []
        seq = next((s for s in sequences if s.get("id") == sequence_id), None)
        if not seq:
            return _err(f"Sequence {sequence_id} not found")

        anim = seq.get("animation") or {}
        if anim.get("status") in ("completed", "succeeded") and anim.get("video_url"):
            url = anim["video_url"]
            return _completed_video(sequence_id, url, anim.get("model"),
                                     project_id, seq, deps, persist_asset=False)
        task_id = anim.get("task_id")
        if not task_id:
            return _err("Sequence has no task_id yet")

        poll = kie_poll_task(task_id, g.kie_api_key)
        raw_status = (poll.get("status") or "").lower()
        if raw_status in ("success", "succeeded", "completed", "done"):
            urls = poll.get("result_urls") or poll.get("resultUrls") or []
            raw_video_url = urls[0] if isinstance(urls, list) and urls else None
            video_url = rehost_to_firebase(
                raw_video_url, kind="video", project_id=project_id,
                upload_to_storage=upload_to_storage) if raw_video_url else None
            update = {
                "status": STATUS_SUCCEEDED,
                "animation": {**anim, "status": "completed",
                              "video_url": video_url, "completed_at": now_iso()},
            }
            if video_url:
                storage.update_sequence(g.uid, project_id, sequence_id, update)
                return _completed_video(sequence_id, video_url,
                                         anim.get("model"), project_id, seq,
                                         deps, persist_asset=True)
            return _err("Completed but no video_url returned by Kie")
        if raw_status in ("failed", "error"):
            err = poll.get("error") or "Kie reported failure"
            storage.update_sequence(g.uid, project_id, sequence_id, {
                "status": STATUS_FAILED,
                "animation": {**anim, "status": "failed", "error": err,
                              "completed_at": now_iso()},
            })
            sc = _seedance_sc(seq, status="failed",
                               tool_label="studio_get_sequence_status",
                               error=err, project_id=project_id)
            return {
                "content": [cb.text_block(f"Sequence {sequence_id}: failed. {err}")],
                "structuredContent": sc,
                "isError": True,
            }
        sc = _seedance_sc(
            seq, status="pending", tool_label="studio_get_sequence_status",
            project_id=project_id,
            est_seconds_min=60, est_seconds_max=180,
            retry_after_seconds=180)
        return {
            "content": [cb.text_block(
                f"Sequence {sequence_id}: pending. Wait at least 180s before "
                f"the next studio_get_sequence_status call — the viewer shows "
                f"the user a live timer; polling sooner wastes tokens.")],
            "structuredContent": sc,
            "isError": False,
        }

    def _completed_video(sequence_id, video_url, model, project_id, seq,
                         deps, persist_asset):
        """Build the completion response for a Seedance sequence.

        Returns content with caption + structuredContent.video_url so the
        MCP App viewer renders the <video>. Optionally writes an entry into
        the user's project asset library so it appears in the Studio web UI.
        """
        if persist_asset:
            try:
                firestore = deps["firestore"]
                db = deps["db"]
                doc = {
                    "kind": "video",
                    "url": video_url,
                    "model_id": model or "seedance-2",
                    "provider": "Seedance",
                    "prompt": seq.get("prompt") or seq.get("seedance_prompt") or "",
                    "params": {"aspect_ratio": seq.get("aspect_ratio"),
                                "duration": seq.get("duration_sec"),
                                "sequence_id": sequence_id},
                    "favorite": False,
                    "created_by": g.uid,
                    "ts": firestore.SERVER_TIMESTAMP,
                }
                (db.collection("users").document(g.uid)
                    .collection("projects").document(project_id)
                    .collection("assets").document().set(doc))
            except Exception as e:
                print(f"[MCP] seedance asset save failed for {sequence_id}: {e}")
        sc = _seedance_sc(
            seq, status="completed", tool_label="studio_get_sequence_status",
            video_url=video_url, primary_url=video_url,
            project_id=project_id, model_id=model or "seedance-2")
        return {
            "content": [cb.text_block(
                f"Sequence {sequence_id}: completed. Primary URL: {video_url}")],
            "structuredContent": sc,
            "isError": False,
        }

    return {
        "studio_animate_sequence": {
            "description": "Kick off a Seedance 2.0 animation (the multimodal grid + character "
                           "refs path used by the Seedance Studio M1 flow). Returns sequence_id "
                           "and task_id; poll with studio_get_sequence_status.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "project_id": {"type": "string"},
                    "prompt": {"type": "string"},
                    "grid_url": {"type": "string", "description": "URL of the grid/keyframe image"},
                    "char_ref_urls": {"type": "array", "items": {"type": "string"}},
                    "aspect_ratio": {"type": "string", "enum": ["16:9", "9:16", "1:1"], "default": "16:9"},
                    "duration": {"type": "integer", "default": 15},
                    "resolution": {"type": "string", "default": "720p"},
                    "generate_audio": {"type": "boolean", "default": True},
                    "title": {"type": "string"},
                    "model": {"type": "string", "enum": ["seedance-2", "seedance-2-fast"],
                              "default": "seedance-2"},
                },
                "required": ["project_id", "prompt", "grid_url"],
                "additionalProperties": False,
            },
            "_meta": _VIEWER_META,
            "handler": _animate,
        },
        "studio_get_sequence_status": {
            "description": "Check whether a Seedance sequence finished animating and return the "
                           "video URL if ready. The video is mirrored to Firebase Storage on "
                           "completion so the URL stays valid for later re-renders and the "
                           "asset library.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "project_id": {"type": "string"},
                    "sequence_id": {"type": "string"},
                },
                "required": ["project_id", "sequence_id"],
                "additionalProperties": False,
            },
            "_meta": _VIEWER_META,
            "handler": _status,
        },
    }


def _err(msg: str) -> dict:
    return {"content": [cb.text_block(msg)], "isError": True}

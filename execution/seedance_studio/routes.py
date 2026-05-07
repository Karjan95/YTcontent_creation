"""Flask routes for Seedance Studio (M1 — manual prompt path).

M1 scope: user provides hand-written Seedance prompt + grid image URL +
optional character ref URLs. Backend uploads refs to KIE, kicks off Seedance
2.0 multimodal task, persists task_id, polls for completion, stores video URL.

No agents yet. Wiring proof only. Agents land in M2/M3.
"""

import os

from flask import g, jsonify, request

from kie_client import (
    upload_image_url as kie_upload_image,
    create_task as kie_create_task,
    poll_task as kie_poll_task,
    download_result as kie_download_result,
)

from .schemas import (
    new_sequence,
    STATUS_ANIMATING,
    STATUS_SUCCEEDED,
    STATUS_FAILED,
    now_iso,
)
from . import storage


def register_routes(app, limiter, require_auth, upload_to_storage):
    """Register all /api/seedance/* routes on the given Flask app.

    Dependencies are passed in (rather than imported) because the existing
    server module owns the app, limiter, auth decorator, and storage helper.
    """

    @app.route("/api/seedance/project/<project_id>", methods=["GET"])
    @require_auth
    @limiter.limit("200/hour")
    def seedance_get_project(project_id):
        try:
            data = storage.get_seedance_data(g.uid, project_id)
            return jsonify({"seedance_production_data": data})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/seedance/sequences/animate", methods=["POST"])
    @require_auth
    @limiter.limit("60/hour")
    def seedance_animate():
        """M1 manual path: take prompt + grid + char refs, kick off KIE Seedance."""
        try:
            if not g.kie_api_key:
                return jsonify({"error": "Kie.ai API key required. Add it in Settings."}), 400

            data = request.json or {}
            project_id = data.get("project_id")
            prompt = (data.get("prompt") or "").strip()
            grid_url = (data.get("grid_url") or "").strip()
            char_ref_urls = data.get("char_ref_urls") or []
            aspect_ratio = data.get("aspect_ratio", "16:9")
            duration = int(data.get("duration", 15))
            resolution = data.get("resolution", "720p")
            generate_audio = bool(data.get("generate_audio", True))
            title = data.get("title")
            model = data.get("model", "seedance-2")

            if not project_id:
                return jsonify({"error": "project_id is required"}), 400
            if not prompt:
                return jsonify({"error": "prompt is required"}), 400
            if not grid_url:
                return jsonify({"error": "grid_url is required"}), 400
            if model not in ("seedance-2", "seedance-2-fast"):
                return jsonify({"error": "model must be seedance-2 or seedance-2-fast"}), 400

            # Build sequence record + persist before KIE call so we can attach task_id after
            seq = new_sequence(
                prompt=prompt,
                grid_url=grid_url,
                char_ref_urls=char_ref_urls,
                aspect_ratio=aspect_ratio,
                duration_sec=duration,
                title=title,
            )
            storage.append_sequence(g.uid, project_id, seq)

            # Upload grid image to KIE CDN
            up = kie_upload_image(grid_url, g.kie_api_key)
            if not up.get("success"):
                storage.update_sequence(g.uid, project_id, seq["id"], {
                    "status": STATUS_FAILED,
                    "error": f"Grid upload to KIE failed: {up.get('error', 'unknown')}",
                })
                return jsonify({"error": f"Grid upload failed: {up.get('error', 'unknown')}"}), 500
            kie_grid_url = up["url"]

            # Upload char refs (max 9 per Seedance spec; grid counts as primary so 8 left)
            uploaded_refs = []
            for ref_url in (char_ref_urls or [])[:8]:
                ref_up = kie_upload_image(ref_url, g.kie_api_key)
                if ref_up.get("success"):
                    uploaded_refs.append(ref_up["url"])

            task_params = {
                "aspect_ratio": aspect_ratio,
                "duration": duration,
                "resolution": resolution,
                "audio": generate_audio,
            }
            if uploaded_refs:
                # Multimodal mode passes refs alongside primary; mirrors server.py:3200-3208
                task_params["ref_image_urls"] = uploaded_refs

            gen_result = kie_create_task(
                model, prompt, g.kie_api_key,
                image_urls=[kie_grid_url], **task_params,
            )
            if not gen_result.get("success"):
                storage.update_sequence(g.uid, project_id, seq["id"], {
                    "status": STATUS_FAILED,
                    "error": f"KIE task creation failed: {gen_result.get('error', 'unknown')}",
                })
                return jsonify({"error": f"KIE task creation failed: {gen_result.get('error', 'unknown')}"}), 500

            task_id = gen_result.get("taskId")
            storage.update_sequence(g.uid, project_id, seq["id"], {
                "status": STATUS_ANIMATING,
                "animation": {
                    "task_id": task_id,
                    "operation_name": f"kie:{task_id}",
                    "status": "in_progress",
                    "started_at": now_iso(),
                    "model": model,
                },
            })

            return jsonify({
                "success": True,
                "sequence_id": seq["id"],
                "operation_name": f"kie:{task_id}",
                "status": "in_progress",
            })

        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/seedance/sequences/<seq_id>/status", methods=["GET"])
    @require_auth
    @limiter.limit("200/hour")
    def seedance_status(seq_id):
        """Poll KIE for sequence status. Persists video URL on completion."""
        try:
            project_id = request.args.get("project_id")
            if not project_id:
                return jsonify({"error": "project_id is required"}), 400

            seq = storage.get_sequence(g.uid, project_id, seq_id)
            if not seq:
                return jsonify({"error": "sequence not found"}), 404

            anim = seq.get("animation") or {}
            task_id = anim.get("task_id")
            if not task_id:
                return jsonify({"status": seq.get("status", "unknown"), "sequence": seq})

            # Already terminal? Don't re-poll.
            if anim.get("status") in ("completed", "failed"):
                return jsonify({"status": anim["status"], "sequence": seq})

            if not g.kie_api_key:
                return jsonify({"error": "Kie.ai API key not configured"}), 400

            poll_result = kie_poll_task(task_id, g.kie_api_key)
            kie_status = poll_result.get("status", "processing")

            if kie_status == "completed" and poll_result.get("result_urls"):
                video_url = None
                for kie_url in poll_result["result_urls"]:
                    local_path = kie_download_result(kie_url, task_id)
                    if not local_path:
                        continue
                    try:
                        firebase_url = upload_to_storage(local_path, "videos", project_id=project_id)
                        if firebase_url:
                            video_url = firebase_url
                    finally:
                        try:
                            os.unlink(local_path)
                            os.rmdir(os.path.dirname(local_path))
                        except OSError:
                            pass
                    if not video_url:
                        video_url = kie_url

                updated = storage.update_sequence(g.uid, project_id, seq_id, {
                    "status": STATUS_SUCCEEDED,
                    "animation": {
                        **anim,
                        "status": "completed",
                        "video_url": video_url,
                        "completed_at": now_iso(),
                    },
                })
                return jsonify({"status": "completed", "video_url": video_url, "sequence": updated})

            if kie_status == "failed":
                updated = storage.update_sequence(g.uid, project_id, seq_id, {
                    "status": STATUS_FAILED,
                    "animation": {
                        **anim,
                        "status": "failed",
                        "error": poll_result.get("error", "KIE task failed"),
                        "completed_at": now_iso(),
                    },
                })
                return jsonify({"status": "failed", "error": poll_result.get("error"), "sequence": updated}), 500

            return jsonify({
                "status": "processing",
                "progress": poll_result.get("progress"),
                "sequence": seq,
            })

        except Exception as e:
            return jsonify({"error": str(e)}), 500

import json
import os
import subprocess
import tempfile
from urllib.parse import urlparse

import requests
from flask import Blueprint, jsonify, request

creator_worker_bp = Blueprint("creator_worker", __name__)

ALLOWED_STORAGE_HOSTS = {
    "zlnhaqzawbzagraxhmlb.supabase.co",
    "zlnhaqzawbzagraxhmlb.storage.supabase.co",
}


def _valid_source_url(value):
    try:
        parsed = urlparse(str(value or ""))
        return (
            parsed.scheme == "https"
            and parsed.hostname in ALLOWED_STORAGE_HOSTS
            and "/storage/v1/object/sign/droxion-creator-sources/" in parsed.path
            and bool(parsed.query)
        )
    except Exception:
        return False


def _valid_output_url(value):
    try:
        parsed = urlparse(str(value or ""))
        return (
            parsed.scheme == "https"
            and parsed.hostname in ALLOWED_STORAGE_HOSTS
            and "/storage/v1/object/upload/sign/droxion-creator-clips/" in parsed.path
            and bool(parsed.query)
        )
    except Exception:
        return False


def _probe_duration(path):
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "json",
            path,
        ],
        capture_output=True,
        text=True,
        timeout=30,
        check=True,
    )
    payload = json.loads(result.stdout or "{}")
    return max(0.0, float(payload.get("format", {}).get("duration") or 0.0))


def _clip_plan(duration, max_count):
    if duration <= 0:
        return [(0.0, 15.0)]

    if duration <= 20:
        return [(0.0, max(1.0, min(duration, 20.0)))]

    clip_len = min(18.0, max(10.0, duration / 6.0))
    if max_count <= 1:
        starts = [max(0.0, min(duration - clip_len, duration * 0.35))]
    elif max_count == 2:
        starts = [duration * 0.15, duration * 0.60]
    else:
        starts = [duration * 0.10, duration * 0.42, duration * 0.74]

    plan = []
    for start in starts[:max_count]:
        safe_start = max(0.0, min(float(start), max(0.0, duration - clip_len)))
        safe_len = max(1.0, min(clip_len, duration - safe_start))
        plan.append((safe_start, safe_len))
    return plan


def _render_vertical(source_path, output_path, start, duration):
    video_filter = (
        "scale=720:1280:force_original_aspect_ratio=decrease,"
        "pad=720:1280:(ow-iw)/2:(oh-ih)/2:color=black"
    )
    command = [
        "ffmpeg",
        "-y",
        "-ss",
        f"{start:.3f}",
        "-i",
        source_path,
        "-t",
        f"{duration:.3f}",
        "-vf",
        video_filter,
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "23",
        "-c:a",
        "aac",
        "-b:a",
        "128k",
        "-movflags",
        "+faststart",
        output_path,
    ]
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=90,
    )
    if result.returncode != 0:
        raise RuntimeError((result.stderr or "FFmpeg processing failed.")[-2000:])


@creator_worker_bp.route("/creator/process", methods=["POST"])
def creator_process():
    body = request.get_json(silent=True) or {}
    source_url = body.get("source_url")
    outputs = body.get("outputs") or []

    if not _valid_source_url(source_url):
        return jsonify({"ok": False, "error": "Invalid creator source URL."}), 400

    clean_outputs = [
        item for item in outputs
        if isinstance(item, dict)
        and _valid_output_url(item.get("signed_url"))
        and item.get("path")
    ][:3]

    if not clean_outputs:
        return jsonify({"ok": False, "error": "No valid creator clip destinations."}), 400

    try:
        with tempfile.TemporaryDirectory(prefix="droxion-creator-") as workdir:
            source_path = os.path.join(workdir, "source.mp4")
            with requests.get(source_url, stream=True, timeout=(15, 120)) as response:
                response.raise_for_status()
                with open(source_path, "wb") as target:
                    for chunk in response.iter_content(chunk_size=1024 * 1024):
                        if chunk:
                            target.write(chunk)

            duration = _probe_duration(source_path)
            plan = _clip_plan(duration, len(clean_outputs))
            clips = []

            for position, ((start, clip_duration), destination) in enumerate(zip(plan, clean_outputs), start=1):
                output_path = os.path.join(workdir, f"clip-{position}.mp4")
                _render_vertical(source_path, output_path, start, clip_duration)

                with open(output_path, "rb") as clip_file:
                    upload = requests.put(
                        destination["signed_url"],
                        data=clip_file,
                        headers={
                            "Content-Type": "video/mp4",
                            "cache-control": "max-age=3600",
                        },
                        timeout=(15, 120),
                    )
                if upload.status_code >= 300:
                    raise RuntimeError(
                        f"Clip upload failed ({upload.status_code}): {upload.text[:500]}"
                    )

                clips.append(
                    {
                        "index": position,
                        "path": destination["path"],
                        "start_seconds": round(start, 3),
                        "duration_seconds": round(clip_duration, 3),
                    }
                )

            return jsonify(
                {
                    "ok": True,
                    "source_duration_seconds": round(duration, 3),
                    "clips": clips,
                    "processor": "ffmpeg-v1",
                }
            )
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500

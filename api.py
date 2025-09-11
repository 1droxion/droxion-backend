# api.py
import os, json, base64, uuid, traceback
from datetime import datetime
from typing import Optional
from urllib.parse import quote

from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import requests

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY", "")
REPLICATE_API_TOKEN = os.getenv("REPLICATE_API_TOKEN", "")  # <-- your Replit/Replicate key
OPENAI_CHAT_MODEL = os.getenv("OPENAI_CHAT_MODEL", "gpt-4o-mini")
OPENAI_IMAGE_MODEL = os.getenv("OPENAI_IMAGE_MODEL", "gpt-image-1")
LOG_FILE = os.getenv("LOG_FILE", "user_logs.jsonl")
STATIC_DIR = os.getenv("STATIC_DIR", "public")
os.makedirs(STATIC_DIR, exist_ok=True)

app = Flask(__name__, static_folder=STATIC_DIR, static_url_path="/static")
CORS(app, resources={r"/*": {"origins": "*"}}, supports_credentials=False)

def _json_error(msg: str, status: int = 400):
    return jsonify({"ok": False, "error": msg}), status

def _safe_str(x) -> str:
    try:
        return str(x)
    except Exception:
        return "<unprintable>"

def _log_line(payload: dict):
    payload = dict(payload or {})
    payload["ts"] = datetime.utcnow().isoformat()
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")
    except Exception:
        pass

def _openai_chat(prompt: str) -> str:
    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY not set")
    url = "https://api.openai.com/v1/chat/completions"
    headers = {"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"}
    data = {
        "model": OPENAI_CHAT_MODEL,
        "messages": [
            {"role": "system", "content": "You are Droxion's helpful assistant."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.7,
    }
    r = requests.post(url, headers=headers, json=data, timeout=60)
    r.raise_for_status()
    j = r.json()
    return j["choices"][0]["message"]["content"].strip()

def _replicate_image(prompt: str) -> Optional[str]:
    """Call Replicate API; returns /static/ URL or None."""
    if not REPLICATE_API_TOKEN:
        return None
    # Model examples: "black-forest-labs/FLUX.1-dev" or "stability-ai/sdxl"
    # FLUX 1 is popular and fast; adjust if you prefer a different model.
    data = {
        "version": "black-forest-labs/FLUX.1-dev",
        "input": {"prompt": prompt}
    }
    # Replicate HTTP API (predictions)
    r = requests.post(
        "https://api.replicate.com/v1/predictions",
        headers={
            "Authorization": f"Token {REPLICATE_API_TOKEN}",
            "Content-Type": "application/json"
        },
        json=data,
        timeout=120
    )
    if r.status_code >= 400:
        return None
    pred = r.json()
    # Poll until finished
    url = pred.get("urls", {}).get("get")
    if not url:
        return None
    for _ in range(50):
        pr = requests.get(url, headers={"Authorization": f"Token {REPLICATE_API_TOKEN}"}, timeout=120)
        pj = pr.json()
        status = pj.get("status")
        if status in ("succeeded", "failed", "canceled"):
            if status == "succeeded":
                out = pj.get("output")
                if isinstance(out, list) and out:
                    image_http = out[0]  # public HTTP URL
                    # Download, store to /static, and return local URL
                    img = requests.get(image_http, timeout=120)
                    if img.status_code < 400:
                        fname = f"{uuid.uuid4().hex}.png"
                        fpath = os.path.join(STATIC_DIR, fname)
                        with open(fpath, "wb") as f:
                            f.write(img.content)
                        return f"/static/{fname}"
            return None
    return None

def _openai_image(prompt: str) -> Optional[str]:
    if not OPENAI_API_KEY:
        return None
    url = "https://api.openai.com/v1/images/generations"
    headers = {"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"}
    data = {"model": OPENAI_IMAGE_MODEL, "prompt": prompt, "size": "1024x1024", "response_format": "b64_json"}
    r = requests.post(url, headers=headers, json=data, timeout=120)
    if r.status_code >= 400:
        return None
    j = r.json()
    b64 = j["data"][0]["b64_json"]
    fname = f"{uuid.uuid4().hex}.png"
    fpath = os.path.join(STATIC_DIR, fname)
    with open(fpath, "wb") as f:
        f.write(base64.b64decode(b64))
    return f"/static/{fname}"

@app.route("/", methods=["GET"])
def root():
    return jsonify({"ok": True, "service": "Droxion API", "time": datetime.utcnow().isoformat()})

@app.route("/chat", methods=["POST"])
def chat():
    try:
        data = request.get_json(force=True, silent=True) or {}
        prompt = (data.get("prompt") or "").strip()
        if not prompt:
            return _json_error("Missing 'prompt'")
        reply = _openai_chat(prompt)
        if "who" in prompt.lower() and any(k in prompt.lower() for k in ["made", "created", "built"]):
            reply = "I was created and managed by **Dhruv Patel**, powered by OpenAI."
        _log_line({"route": "/chat", "prompt": prompt, "reply_len": len(reply)})
        return jsonify({"ok": True, "reply": reply})
    except Exception as e:
        traceback.print_exc()
        return _json_error(f"chat failed: {_safe_str(e)}", 500)

@app.route("/generate-image", methods=["POST"])
def generate_image():
    try:
        data = request.get_json(force=True, silent=True) or {}
        prompt = (data.get("prompt") or "").trim() if hasattr(str, "trim") else (data.get("prompt") or "").strip()
        if not prompt:
            return _json_error("Missing 'prompt'")

        url = _replicate_image(prompt) or _openai_image(prompt)
        if not url:
            ph = f"https://dummyimage.com/1024x1024/111/fff.png&text={quote('Image unavailable')}"
            _log_line({"route": "/generate-image", "prompt": prompt, "image_url": ph, "provider": "placeholder"})
            return jsonify({"ok": True, "image_url": ph})

        _log_line({"route": "/generate-image", "prompt": prompt, "image_url": url, "provider": "replicate_or_openai"})
        return jsonify({"ok": True, "image_url": url})
    except Exception as e:
        traceback.print_exc()
        return _json_error(f"image generation failed: {_safe_str(e)}", 500)

@app.route("/search-youtube", methods=["POST"])
def search_youtube():
    try:
        data = request.get_json(force=True, silent=True) or {}
        q = (data.get("prompt") or "").strip()
        if not q:
            return _json_error("Missing 'prompt'")
        if not YOUTUBE_API_KEY:
            return _json_error("YOUTUBE_API_KEY not set on server", 500)
        params = {"key": YOUTUBE_API_KEY, "part": "snippet", "type": "video", "q": q, "maxResults": 1, "safeSearch": "none"}
        r = requests.get("https://www.googleapis.com/youtube/v3/search", params=params, timeout=30)
        if r.status_code >= 400:
            return _json_error(f"YouTube API error: {r.status_code} {r.text[:200]}", 500)
        j = r.json()
        items = j.get("items") or []
        if not items:
            return jsonify({"ok": True, "url": None})
        vid = items[0]["id"]["videoId"]
        url = f"https://www.youtube.com/watch?v={vid}"
        _log_line({"route": "/search-youtube", "q": q, "videoId": vid})
        return jsonify({"ok": True, "url": url})
    except Exception as e:
        traceback.print_exc()
        return _json_error(f"youtube search failed: {_safe_str(e)}", 500)

@app.route("/track", methods=["POST"])
def track():
    try:
        data = request.get_json(force=True, silent=True) or {}
        rec = {
            "user_id": data.get("user_id") or "unknown",
            "action": data.get("action") or "event",
            "input": data.get("input", ""),
            "timestamp": data.get("timestamp") or datetime.utcnow().isoformat(),
            "ip": request.headers.get("X-Forwarded-For", request.remote_addr),
            "ua": request.headers.get("User-Agent"),
        }
        _log_line({"route": "/track", **rec})
        return jsonify({"ok": True})
    except Exception as e:
        traceback.print_exc()
        return _json_error(f"track failed: {_safe_str(e)}", 500)

@app.route("/public/<path:filename>")
def public_files(filename):
    return send_from_directory(STATIC_DIR, filename)

if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    app.run(host="0.0.0.0", port=port, debug=False)
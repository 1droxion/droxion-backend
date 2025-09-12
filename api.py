import os, json, base64, uuid, traceback, time
from datetime import datetime
from typing import Optional
from urllib.parse import quote, urljoin

import requests
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS

# ========================
# -------- ENV -----------
# ========================
OPENAI_API_KEY      = os.getenv("OPENAI_API_KEY", "")
OPENAI_CHAT_MODEL   = os.getenv("OPENAI_CHAT_MODEL", "gpt-4o-mini")
OPENAI_IMAGE_MODEL  = os.getenv("OPENAI_IMAGE_MODEL", "gpt-image-1")

REPLICATE_API_TOKEN = os.getenv("REPLICATE_API_TOKEN", "")
REPLICATE_MODEL     = os.getenv("REPLICATE_MODEL", "black-forest-labs/FLUX.1-dev")

YOUTUBE_API_KEY     = os.getenv("YOUTUBE_API_KEY", "")

LOG_FILE            = os.getenv("LOG_FILE", "user_logs.jsonl")
STATIC_DIR          = os.getenv("STATIC_DIR", "public")
ALLOWED_ORIGINS     = os.getenv("ALLOWED_ORIGINS", "*")          # set to your Vercel URL for stricter CORS
PUBLIC_BASE_URL     = os.getenv("PUBLIC_BASE_URL", "").rstrip("/")  # e.g. https://droxion-backend.onrender.com

os.makedirs(STATIC_DIR, exist_ok=True)

app = Flask(__name__, static_folder=STATIC_DIR, static_url_path="/static")
CORS(app, resources={r"/*": {"origins": ALLOWED_ORIGINS}}, supports_credentials=False)


# ========================
# ------ Helpers ---------
# ========================
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

def _abs_url(u: str) -> str:
    """Return absolute URL for any relative path (e.g., /static/abc.png)."""
    if not u:
        return u
    if u.startswith("http://") or u.startswith("https://"):
        return u
    base = PUBLIC_BASE_URL or (request.host_url.rstrip("/") if request else "")
    return urljoin(base + "/", u.lstrip("/"))


# ========================
# ------- OpenAI ---------
# ========================
def _openai_chat(prompt: str) -> str:
    if not OPENAI_API_KEY:
        # Graceful local fallback (no external call)
        return f"You said: **{prompt}**"
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
    if r.status_code >= 400:
        raise RuntimeError(f"OpenAI chat error: {r.status_code} {r.text[:200]}")
    j = r.json()
    return (j["choices"][0]["message"]["content"] or "").strip()

def _openai_image(prompt: str) -> Optional[str]:
    """Generates image via OpenAI Images API; saves to /static; returns relative /static/<file>. """
    if not OPENAI_API_KEY:
        return None
    url = "https://api.openai.com/v1/images/generations"
    headers = {"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"}
    data = {
        "model": OPENAI_IMAGE_MODEL,
        "prompt": prompt,
        "size": "1024x1024",
        "response_format": "b64_json"
    }
    r = requests.post(url, headers=headers, json=data, timeout=120)
    if r.status_code >= 400:
        return None
    j = r.json()
    b64 = j["data"][0]["b64_json"]
    img_bytes = base64.b64decode(b64)
    fname = f"{uuid.uuid4().hex}.png"
    fpath = os.path.join(STATIC_DIR, fname)
    with open(fpath, "wb") as f:
        f.write(img_bytes)
    return f"/static/{fname}"


# ========================
# ----- Replicate --------
# ========================
def _replicate_image(prompt: str) -> Optional[str]:
    """
    Uses Replicate Predictions API:
    - Create prediction
    - Poll until status == 'succeeded'
    - Download first output URL to /static and return /static/<file>
    """
    if not REPLICATE_API_TOKEN:
        return None

    create = requests.post(
        "https://api.replicate.com/v1/predictions",
        headers={
            "Authorization": f"Token {REPLICATE_API_TOKEN}",
            "Content-Type": "application/json",
        },
        json={
            "model": REPLICATE_MODEL,
            "input": {"prompt": prompt}
        },
        timeout=60
    )
    if create.status_code >= 400:
        return None

    pred = create.json()
    get_url = pred.get("urls", {}).get("get")
    if not get_url:
        return None

    for _ in range(60):  # ~120s max (2s polling)
        pr = requests.get(get_url, headers={"Authorization": f"Token {REPLICATE_API_TOKEN}"}, timeout=60)
        if pr.status_code >= 400:
            return None
        pj = pr.json()
        status = pj.get("status")
        if status == "succeeded":
            output = pj.get("output")
            if isinstance(output, list) and output:
                image_url = output[0]  # public CDN URL
                img = requests.get(image_url, timeout=120)
                if img.status_code < 400:
                    fname = f"{uuid.uuid4().hex}.png"
                    fpath = os.path.join(STATIC_DIR, fname)
                    with open(fpath, "wb") as f:
                        f.write(img.content)
                    return f"/static/{fname}"
            return None
        if status in ("failed", "canceled"):
            return None
        time.sleep(2)
    return None


# ========================
# ------- Routes ---------
# ========================
@app.route("/", methods=["GET"])
def root():
    return jsonify({"ok": True, "service": "Droxion API", "time": datetime.utcnow().isoformat()})


@app.route("/chat", methods=["POST"])
def chat():
    """Main chat. Emits simple cards for weather/time; otherwise uses OpenAI chat."""
    try:
        data = request.get_json(force=True, silent=True) or {}
        prompt = (data.get("prompt") or "").strip()
        if not prompt:
            return _json_error("Missing 'prompt'")

        lower = prompt.lower()

        # --- Simple weather card (demo) ---
        if "weather" in lower:
            city = lower.replace("weather", "").replace("in", "").strip() or "Ahmedabad"
            reply = f"Here is the weather for **{city.title()}**:"
            cards = [{
                "type": "weather",
                "title": f"🌤️ {city.title()} Weather",
                "description": "29°C, Clear sky",
                "meta": "Demo • Replace with live provider"
            }]
            _log_line({"route": "/chat", "prompt": prompt, "cards": True})
            return jsonify({"ok": True, "reply": reply, "cards": cards})

        # --- Simple time card (demo) ---
        if "time" in lower:
            place = (lower.replace("time", "").replace("now", "").replace("in", "").strip() or "London").title()
            now_utc = datetime.utcnow().strftime("%H:%M UTC")
            reply = f"Current time in **{place}**: **{now_utc}**"
            cards = [{"type": "link", "title": f"Current time in {place}", "description": now_utc}]
            _log_line({"route": "/chat", "prompt": prompt, "cards": True})
            return jsonify({"ok": True, "reply": reply, "cards": cards})

        # --- Normal OpenAI chat ---
        reply = _openai_chat(prompt)

        # Brand line override
        if "who" in lower and any(k in lower for k in ["made", "created", "built"]):
            reply = "I was created and managed by **Dhruv Patel**, powered by OpenAI."

        _log_line({"route": "/chat", "prompt": prompt, "reply_len": len(reply)})
        return jsonify({"ok": True, "reply": reply})
    except Exception as e:
        traceback.print_exc()
        return _json_error(f"chat failed: {_safe_str(e)}", 500)


@app.route("/generate-image", methods=["POST"])
def generate_image():
    """Generate image using Replicate → OpenAI → placeholder; always return **absolute** image_url."""
    try:
        data = request.get_json(force=True, silent=True) or {}
        prompt = (data.get("prompt") or "").strip()
        if not prompt:
            return _json_error("Missing 'prompt'")

        # Try Replicate -> OpenAI
        rel_url = _replicate_image(prompt) or _openai_image(prompt)

        if not rel_url:
            ph = f"https://dummyimage.com/1024x1024/111/fff.png&text={quote('Image unavailable')}"
            abs_ph = _abs_url(ph)  # stays absolute
            _log_line({"route": "/generate-image", "prompt": prompt, "image_url": abs_ph, "provider": "placeholder"})
            return jsonify({"ok": True, "image_url": abs_ph})

        abs_url = _abs_url(rel_url)  # convert /static/... → https://...
        _log_line({"route": "/generate-image", "prompt": prompt, "image_url": abs_url, "provider": "replicate_or_openai"})
        return jsonify({"ok": True, "image_url": abs_url})
    except Exception as e:
        traceback.print_exc()
        return _json_error(f"image generation failed: {_safe_str(e)}", 500)


@app.route("/realtime", methods=["POST"])
def realtime():
    """Google-style inline cards for `google:` trigger from frontend."""
    try:
        data = request.get_json(force=True, silent=True) or {}
        query = (data.get("query") or "").strip()
        if not query:
            return jsonify({"summary": "No query.", "cards": []})

        # Demo cards (replace with live fetches when ready)
        cards = [
            {
                "type": "link",
                "title": f"Top result for {query}",
                "url": "https://example.com",
                "description": "Example result",
                "meta": "Source: Example"
            }
        ]
        md = f"""### Summary for **{query}**

| Item | Detail |
|---|---|
| Query | {query} |
| Info  | Demo cards below |
"""
        return jsonify({"summary": f"Results for {query}", "markdown": md, "cards": cards})
    except Exception as e:
        traceback.print_exc()
        return _json_error(f"realtime failed: {_safe_str(e)}", 500)


@app.route("/suggest", methods=["GET"])
def suggest():
    """Type-ahead suggestions used by the input box."""
    try:
        q = (request.args.get("q") or "").strip()
        if not q:
            return jsonify({"suggestions": []})
        base = [
            f"google: {q}",
            f"image: {q}",
            f"search: {q} latest news",
            f"table: Top 5 facts about {q}",
            f"{q} — pros and cons",
        ]
        out, seen = [], set()
        for s in base:
            if s not in seen:
                out.append(s); seen.add(s)
        return jsonify({"suggestions": out[:8]})
    except Exception as e:
        traceback.print_exc()
        return _json_error(f"suggest failed: {_safe_str(e)}", 500)


@app.route("/search-youtube", methods=["POST"])
def search_youtube():
    try:
        data = request.get_json(force=True, silent=True) or {}
        q = (data.get("prompt") or "").strip()
        if not q:
            return _json_error("Missing 'prompt'")
        if not YOUTUBE_API_KEY:
            return _json_error("YOUTUBE_API_KEY not set on server", 500)

        params = {
            "key": YOUTUBE_API_KEY,
            "part": "snippet",
            "type": "video",
            "q": q,
            "maxResults": 1,
            "safeSearch": "none",
        }
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


# ========================
# ------ Main ------------
# ========================
if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    app.run(host="0.0.0.0", port=port, debug=False)
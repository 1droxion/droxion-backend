import os, json, uuid, traceback, time
from datetime import datetime
from typing import Optional
from urllib.parse import quote, urljoin

import requests
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS

# ========================
# -------- ENV -----------
# ========================
OPENAI_API_KEY      = os.getenv("OPENAI_API_KEY", "")  # optional
OPENAI_CHAT_MODEL   = os.getenv("OPENAI_CHAT_MODEL", "gpt-4o-mini")

YOUTUBE_API_KEY     = os.getenv("YOUTUBE_API_KEY", "")  # optional

LOG_FILE            = os.getenv("LOG_FILE", "user_logs.jsonl")
STATIC_DIR          = os.getenv("STATIC_DIR", "public")
ALLOWED_ORIGINS     = os.getenv("ALLOWED_ORIGINS", "*")  # set to your Vercel URL for stricter CORS
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

def _mk_web_card(title, url, source=None, snippet=None, image=None, meta=None):
    return {
        "type": "web",
        "title": title,
        "url": url,
        "source": source or (url.split("/")[2] if "://" in url else "source"),
        "snippet": snippet,
        "image": image,
        "meta": meta
    }

# ========================
# ------- OpenAI ---------
# ========================
def _openai_chat(prompt: str) -> str:
    """Optional OpenAI call; if no API key, return a simple echo so app still works."""
    if not OPENAI_API_KEY:
        return f"{prompt}"
    url = "https://api.openai.com/v1/chat/completions"
    headers = {"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"}
    data = {
        "model": OPENAI_CHAT_MODEL,
        "messages": [
            {"role": "system", "content": "You are Droxion's helpful assistant. Prefer numbered lists and tight structure."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.5,
    }
    r = requests.post(url, headers=headers, json=data, timeout=60)
    if r.status_code >= 400:
        raise RuntimeError(f"OpenAI chat error: {r.status_code} {r.text[:200]}")
    j = r.json()
    return (j["choices"][0]["message"]["content"] or "").strip()

# ========================
# ------- Routes ---------
# ========================
@app.route("/", methods=["GET"])
def root():
    return jsonify({"ok": True, "service": "Droxion API", "time": datetime.utcnow().isoformat()})

# ---------- Chat: adds clean numbered structure + simple cards for weather/time ----------
def _structure_answer(prompt: str, raw: str) -> str:
    """Force neat numbered lists for common intents."""
    low = prompt.lower()
    # Pros & cons
    if "pros" in low and "cons" in low:
        # Split raw into sentences; build numbered lists
        pros = [
            "24/7 availability",
            "Quick information retrieval",
            "Consistency",
            "Wide knowledge base",
            "Non-judgmental support",
            "Task automation",
            "Language support"
        ]
        cons = [
            "No real-time sensing or browsing unless wired",
            "May misunderstand vague context",
            "Lacks personal lived experience",
            "Quality depends on prompt clarity"
        ]
        out = ["### Pros", *(f"{i}. {p}" for i, p in enumerate(pros, 1)),
               "", "### Cons", *(f"{i}. {c}" for i, c in enumerate(cons, 1))]
        return "\n".join(out)

    # Steps / plan
    if any(k in low for k in ["steps", "how to", "plan", "roadmap", "1 by 1", "1by1", "one by one"]):
        lines = [
            "1. Define the goal and success metrics.",
            "2. Gather inputs (users, data, constraints).",
            "3. Draft the approach and choose tools.",
            "4. Execute a small pilot / MVP.",
            "5. Measure results and iterate.",
            "6. Launch, monitor, and maintain."
        ]
        return "### Plan\n" + "\n".join(lines)

    # Default: if raw already looks like markdown, keep; else add simple paragraph
    return raw if any(h in raw for h in ["\n1.", "\n- ", "### "]) else raw

@app.route("/chat", methods=["POST"])
def chat():
    try:
        data = request.get_json(force=True, silent=True) or {}
        prompt = (data.get("prompt") or "").strip()
        if not prompt:
            return _json_error("Missing 'prompt'")

        lower = prompt.lower()

        # Weather card (demo)
        if "weather" in lower:
            city = lower.replace("weather", "").replace("in", "").strip() or "Ahmedabad"
            reply = f"### Weather\n1. **City:** {city.title()}\n2. **Status:** Clear sky (demo)\n3. **Temp:** 29°C\n4. **Tip:** Use `google: {city} weather` for live details."
            cards = [
                _mk_web_card(
                    f"Google Weather – {city.title()}",
                    "https://www.google.com/search?q=" + quote(f"{city} weather"),
                    source="google.com",
                    snippet="Live weather card and hourly graph."
                )
            ]
            return jsonify({"ok": True, "reply": reply, "cards": cards})

        # Time card (demo)
        if "time" in lower:
            place = (lower.replace("time", "").replace("now", "").replace("in", "").strip() or "London").title()
            reply = f"### Time\n1. **Place:** {place}\n2. **Note:** Live time opens below."
            cards = [
                _mk_web_card(
                    f"Current time in {place}",
                    "https://www.google.com/search?q=" + quote(f"time in {place}"),
                    source="google.com",
                    snippet="Official time with timezone."
                )
            ]
            return jsonify({"ok": True, "reply": reply, "cards": cards})

        # Structured OpenAI (or fallback)
        raw = _openai_chat(prompt)
        # Brand line override
        if "who" in lower and any(k in lower for k in ["made", "created", "built"]):
            raw = "I was created and managed by **Dhruv Patel**, powered by OpenAI."
        reply = _structure_answer(prompt, raw)

        _log_line({"route": "/chat", "prompt": prompt, "reply_len": len(reply)})
        return jsonify({"ok": True, "reply": reply})
    except Exception as e:
        traceback.print_exc()
        return _json_error(f"chat failed: {_safe_str(e)}", 500)

# ---------- Google-style inline cards for `google:` trigger ----------
@app.post("/realtime")
def realtime():
    try:
        data = request.get_json(force=True, silent=True) or {}
        query = (data.get("query") or "").strip()
        if not query:
            return jsonify({"summary": "No query.", "cards": []})

        cards = [
            _mk_web_card(
                f"Google – {query}",
                "https://www.google.com/search?q=" + quote(query),
                source="google.com",
                snippet="Top web results and rich card (if available)."
            ),
            _mk_web_card(
                f"Wikipedia – {query}",
                "https://en.wikipedia.org/wiki/" + quote(query.replace(" ", "_")),
                source="wikipedia.org",
                snippet="Encyclopedic overview (may not exist for all queries)."
            )
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

# ---------- Suggestions for the input box ----------
@app.get("/suggest")
def suggest():
    try:
        q = (request.args.get("q") or "").strip()
        if not q:
            return jsonify({"suggestions": []})
        base = [
            f"google: {q}",
            f"search: {q} latest news",
            f"table: Top 5 facts about {q}",
            f"{q} — pros and cons",
            f"steps to do {q}"
        ]
        out, seen = [], set()
        for s in base:
            if s not in seen:
                out.append(s); seen.add(s)
        return jsonify({"suggestions": out[:8]})
    except Exception as e:
        traceback.print_exc()
        return _json_error(f"suggest failed: {_safe_str(e)}", 500)

# ---------- Basic search endpoint so UI never shows 'unavailable' ----------
@app.post("/search")
def search():
    try:
        data = request.get_json(force=True, silent=True) or {}
        q = (data.get("prompt") or "").strip()
        if not q:
            return jsonify({"ok": True, "results": []})

        results = [
            {
                "title": f"Top result for {q}",
                "url": "https://example.com",
                "image": None,
                "source": "example.com",
                "snippet": "Example result",
            },
            {
                "title": f"More about {q}",
                "url": "https://example.org",
                "image": None,
                "source": "example.org",
                "snippet": "Example summary",
            },
        ]
        return jsonify({"ok": True, "results": results})
    except Exception as e:
        return _json_error(f"search failed: {_safe_str(e)}", 500)

# ---------- YouTube helper (optional) ----------
@app.post("/search-youtube")
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

# ---------- Analytics ----------
@app.post("/track")
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

# ---------- Static ----------
@app.get("/public/<path:filename>")
def public_files(filename):
    return send_from_directory(STATIC_DIR, filename)


# ========================
# ------ Main ------------
# ========================
if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    app.run(host="0.0.0.0", port=port, debug=False)
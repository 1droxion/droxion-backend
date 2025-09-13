# app.py  (Droxion backend – images fixed + simple weather card)
import os, json, uuid, traceback
from datetime import datetime
from urllib.parse import quote, urljoin, urlparse

import requests
from flask import Flask, request, jsonify, send_from_directory, Response
from flask_cors import CORS

# ========================
# -------- ENV -----------
# ========================
OPENAI_API_KEY      = os.getenv("OPENAI_API_KEY", "")
OPENAI_CHAT_MODEL   = os.getenv("OPENAI_CHAT_MODEL", "gpt-4o-mini")
YOUTUBE_API_KEY     = os.getenv("YOUTUBE_API_KEY", "")

LOG_FILE            = os.getenv("LOG_FILE", "user_logs.jsonl")
STATIC_DIR          = os.getenv("STATIC_DIR", "public")
ALLOWED_ORIGINS     = os.getenv("ALLOWED_ORIGINS", "*")
PUBLIC_BASE_URL     = os.getenv("PUBLIC_BASE_URL", "").rstrip("/")

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
    if not u:
        return u
    if u.startswith("http://") or u.startswith("https://"):
        return u
    base = PUBLIC_BASE_URL or (request.host_url.rstrip("/") if request else "")
    return urljoin(base + "/", u.lstrip("/"))

def _mk_web_card(title, url, source=None, snippet=None, image=None, meta=None, ctype="web"):
    return {
        "type": ctype,
        "title": title,
        "url": url,
        "source": source or (url.split("/")[2] if "://" in url else "source"),
        "snippet": snippet,
        "image": image,
        "meta": meta
    }

def _openai_chat(prompt: str) -> str:
    # Optional – if no key, just echo the prompt so app still works
    if not OPENAI_API_KEY:
        return prompt
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
    r.raise_for_status()
    j = r.json()
    return (j["choices"][0]["message"]["content"] or "").strip()

# ========================
# ---- Source builders ---
# ========================
def _hq_news_cards(q: str):
    e = quote(q)
    return [
        _mk_web_card(f"Forbes — {q}",               f"https://www.forbes.com/search/?q={e}",          "forbes.com",   ctype="news"),
        _mk_web_card(f"Bloomberg — {q}",            f"https://www.bloomberg.com/search?query={e}",    "bloomberg.com",ctype="news"),
        _mk_web_card(f"Reuters — {q}",              f"https://www.reuters.com/site-search/?query={e}","reuters.com",  ctype="news"),
        _mk_web_card(f"CNBC — {q}",                 f"https://www.cnbc.com/search/?query={e}",        "cnbc.com",     ctype="news"),
        _mk_web_card(f"Google News — {q}",          f"https://news.google.com/search?q={e}",          "news.google.com",ctype="news"),
        _mk_web_card(f"Wikipedia — {q}",            f"https://en.wikipedia.org/wiki/{quote(q.replace(' ','_'))}", "wikipedia.org", ctype="wiki"),
        _mk_web_card(f"Google — {q}",               f"https://www.google.com/search?q={e}",           "google.com"),
    ]

def _crypto_cards(q: str):
    e = q.lower()
    sym = "bitcoin" if ("bitcoin" in e or "btc" in e) else ("ethereum" if ("ethereum" in e or "eth" in e) else q)
    s = quote(sym)
    return [
        _mk_web_card(f"CoinMarketCap — {sym}", f"https://coinmarketcap.com/currencies/{s}/", "coinmarketcap.com", ctype="crypto"),
        _mk_web_card(f"CoinGecko — {sym}",     f"https://www.coingecko.com/en/coins/{s}",   "coingecko.com",     ctype="crypto"),
        _mk_web_card(f"CoinDesk — {q}",        f"https://www.coindesk.com/search/{quote(q)}","coindesk.com",     ctype="news"),
        _mk_web_card(f"Cointelegraph — {q}",   f"https://cointelegraph.com/search?query={quote(q)}","cointelegraph.com",ctype="news"),
    ]

def _weather_cards_links(city: str):
    e = quote(city)
    return [
        _mk_web_card(f"Google Weather — {city.title()}", f"https://www.google.com/search?q={e}+weather","google.com",ctype="weather"),
        _mk_web_card(f"Weather.com — {city.title()}",    f"https://weather.com/search/enhancedlocalsearch?where={e}","weather.com", ctype="weather"),
        _mk_web_card(f"AccuWeather — {city.title()}",    f"https://www.accuweather.com/en/search-locations?query={e}","accuweather.com",ctype="weather"),
    ]

def _time_cards(place: str):
    p = place.strip() or "London"
    e = quote(p)
    return [
        _mk_web_card(f"Current time in {p.title()}", f"https://www.google.com/search?q=time+in+{e}", "google.com", ctype="time"),
        _mk_web_card(f"Time.is — {p.title()}",       f"https://time.is/{e}",                        "time.is",    ctype="time"),
    ]

def _free_image_urls(q: str, n=12):
    """
    Return hot-linkable JPEGs from providers that allow direct embedding.
    We mix three sources and add a cache-buster query so Safari doesn’t reuse 302s.
    """
    qs   = quote(q)
    rnd  = uuid.uuid4().hex[:8]
    out  = []

    # 1) Picsum (royalty-free placeholder photos)
    for i in range(min(4, n)):
        out.append(f"https://picsum.photos/seed/{rnd}-{i}/900/600.jpg")

    # 2) LoremFlickr topic images
    for i in range(min(4, n - len(out))):
        out.append(f"https://loremflickr.com/900/600/{qs}?lock={i}")

    # 3) Unsplash *image CDN* via the “source.unsplash.com” redirect
    #    We keep it, but the frontend will load through /img proxy to avoid referrer issues.
    for i in range(min(6, n - len(out))):
        out.append(f"https://source.unsplash.com/900x600/?{qs}&sig={i}&_b={rnd}")

    return out[:n]

# ========================
# ------- Routes ---------
# ========================
@app.route("/", methods=["GET"])
def root():
    return jsonify({"ok": True, "service": "Droxion API", "time": datetime.utcnow().isoformat()})

# ---------- Chat ----------
@app.post("/chat")
def chat():
    try:
        data = request.get_json(force=True, silent=True) or {}
        prompt = (data.get("prompt") or "").strip()
        if not prompt:
            return _json_error("Missing 'prompt'")

        low = prompt.lower()
        if "weather" in low:
            city = low.replace("weather","").replace("in","").strip() or "Ahmedabad"
            reply = f"### Weather\n1. **City:** {city.title()}\n2. Open the live tracker below."
            return jsonify({"ok": True, "reply": reply, "cards": _weather_cards_links(city)})

        if "time" in low:
            place = low.replace("time","").replace("now","").replace("in","").strip() or "London"
            reply = f"### Time\n1. **Place:** {place.title()}\n2. Tap a source for live time."
            return jsonify({"ok": True, "reply": reply, "cards": _time_cards(place)})

        raw = _openai_chat(prompt)
        return jsonify({"ok": True, "reply": raw})
    except Exception as e:
        traceback.print_exc()
        return _json_error(f"chat failed: {_safe_str(e)}", 500)

# ---------- Realtime ----------
@app.post("/realtime")
def realtime():
    try:
        data = request.get_json(force=True, silent=True) or {}
        query  = (data.get("query")  or "").strip()
        intent = (data.get("intent") or "").strip().lower()
        if not query:
            return jsonify({"summary": "No query.", "cards": []})

        cards = []
        images = []
        md = f"### Results for **{query}**"

        if intent == "weather":
            # Minimal synthetic weather card so the UI renders the **WeatherCard** block.
            city = query.title()
            cards = [{
                "type": "weather",
                "title": f"Weather — {city}",
                "subtitle": "Tap sources for live details",
                "icon": "https://openweathermap.org/img/wn/01d.png",
                "temp_c": None,
                "temp_f": None,
                "feels_like_c": None,
                "feels_like_f": None,
                "humidity": None,
                "wind_kph": None,
                "wind_mph": None,
                "hourly": [],
                "daily": []
            }] + _weather_cards_links(query)

        elif intent == "time":
            cards = _time_cards(query)

        elif intent == "crypto":
            cards = _crypto_cards(query)

        elif intent == "images":
            # ✅ return actual image URLs (frontend will proxy them)
            images = _free_image_urls(query, n=12)
            cards = [
                _mk_web_card(f"Google Images — {query}", f"https://www.google.com/search?tbm=isch&q={quote(query)}", "google.com", ctype="images"),
                _mk_web_card(f"Bing Images — {query}",   f"https://www.bing.com/images/search?q={quote(query)}",     "bing.com",   ctype="images"),
                _mk_web_card("Unsplash",                  f"https://unsplash.com/s/photos/{quote(query)}",            "unsplash.com", ctype="images"),
                _mk_web_card("Lexica (AI images)",        f"https://lexica.art/?q={quote(query)}",                    "lexica.art", ctype="images"),
            ]

        else:
            cards = _hq_news_cards(query)

        return jsonify({
            "summary": f"Results for {query}",
            "markdown": md,
            "cards": cards,
            "images": images
        })
    except Exception as e:
        traceback.print_exc()
        return _json_error(f"realtime failed: {_safe_str(e)}", 500)

# ---------- Suggestions ----------
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
            f"steps to do {q}",
            f"youtube: {q}"
        ]
        out, seen = [], set()
        for s in base:
            if s not in seen:
                out.append(s); seen.add(s)
        return jsonify({"suggestions": out[:8]})
    except Exception as e:
        traceback.print_exc()
        return _json_error(f"suggest failed: {_safe_str(e)}", 500)

# ---------- Search ----------
@app.post("/search")
def search():
    try:
        data = request.get_json(force=True, silent=True) or {}
        q = (data.get("prompt") or "").strip()
        if not q:
            return jsonify({"ok": True, "results": []})
        results = _hq_news_cards(q)
        out = [{
            "title": r["title"],
            "url": r["url"],
            "image": r.get("image"),
            "source": r.get("source"),
            "snippet": r.get("snippet")
        } for r in results]
        return jsonify({"ok": True, "results": out})
    except Exception as e:
        return _json_error(f"search failed: {_safe_str(e)}", 500)

# ---------- YouTube ----------
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

# ---------- Image proxy ----------
@app.get("/img")
def img_proxy():
    u = request.args.get("url", "")
    p = urlparse(u)
    if p.scheme not in ("http", "https"):
        return Response(b"", status=400)
    try:
        r = requests.get(u, headers={"User-Agent": "Mozilla/5.0", "Referer": ""}, timeout=15)
        ct = r.headers.get("content-type", "image/jpeg")
        data = r.content[:5_000_000]
        resp = Response(data, content_type=ct)
        resp.headers["Cache-Control"] = "public, max-age=86400"
        resp.headers["Access-Control-Allow-Origin"] = "*"
        return resp
    except Exception:
        return Response(b"", status=502)

# ---------- Static ----------
@app.get("/public/<path:filename>")
def public_files(filename):
    return send_from_directory(STATIC_DIR, filename)

# ================
# ---- Main ------
# ================
if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    app.run(host="0.0.0.0", port=port, debug=False)
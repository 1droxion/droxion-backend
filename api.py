# app.py  (Droxion backend – enriched sources + /preview OG image)
import os, json, uuid, traceback, time, re
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
    try: return str(x)
    except Exception: return "<unprintable>"

def _log_line(payload: dict):
    payload = dict(payload or {}); payload["ts"] = datetime.utcnow().isoformat()
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")
    except Exception: pass

def _abs_url(u: str) -> str:
    if not u: return u
    if u.startswith("http://") or u.startswith("https://"): return u
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
    if not OPENAI_API_KEY: return f"{prompt}"
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
    if r.status_code >= 400: raise RuntimeError(f"OpenAI chat error: {r.status_code} {r.text[:200]}")
    j = r.json()
    return (j["choices"][0]["message"]["content"] or "").strip()

# ========================
# ---- Source builders ---
# ========================
def _hq_news_cards(q: str):
    e = quote(q)
    return [
        _mk_web_card(f"Forbes — {q}",               f"https://www.forbes.com/search/?q={e}",             "forbes.com",      "Forbes site results",            ctype="news"),
        _mk_web_card(f"Bloomberg — {q}",            f"https://www.bloomberg.com/search?query={e}",       "bloomberg.com",   "Bloomberg site results",         ctype="news"),
        _mk_web_card(f"Reuters — {q}",              f"https://www.reuters.com/site-search/?query={e}",   "reuters.com",     "Reuters site results",           ctype="news"),
        _mk_web_card(f"CNBC — {q}",                 f"https://www.cnbc.com/search/?query={e}",           "cnbc.com",        "CNBC site results",              ctype="news"),
        _mk_web_card(f"Google News — {q}",          f"https://news.google.com/search?q={e}",             "news.google.com", "Top coverage & local outlets",   ctype="news"),
        _mk_web_card(f"Wikipedia — {q}",            f"https://en.wikipedia.org/wiki/{quote(q.replace(' ','_'))}", "wikipedia.org","Background overview", ctype="wiki"),
    ]

def _crypto_cards(q: str):
    e = q.lower()
    sym = "bitcoin" if ("bitcoin" in e or "btc" in e) else ("ethereum" if ("ethereum" in e or "eth" in e) else q)
    s = quote(sym)
    return [
        _mk_web_card(f"CoinMarketCap — {sym}", f"https://coinmarketcap.com/currencies/{s}/", "coinmarketcap.com", "Price, market cap, chart", ctype="crypto"),
        _mk_web_card(f"CoinGecko — {sym}",     f"https://www.coingecko.com/en/coins/{s}",   "coingecko.com",     "Price, chart",             ctype="crypto"),
        _mk_web_card(f"CoinDesk — {q}",        f"https://www.coindesk.com/search/{quote(q)}","coindesk.com",     "Crypto news",              ctype="news"),
        _mk_web_card(f"Cointelegraph — {q}",   f"https://cointelegraph.com/search?query={quote(q)}","cointelegraph.com","Crypto news",       ctype="news"),
        _mk_web_card(f"Google — {q}",          f"https://www.google.com/search?q={quote(q)}","google.com",       "Top web results"),
    ]

def _weather_cards(q: str):
    city = q.strip() or "Ahmedabad"; e = quote(city)
    return [
        _mk_web_card(f"Google Weather — {city.title()}", f"https://www.google.com/search?q={e}+weather","google.com","Live card & hourly graph", ctype="weather"),
        _mk_web_card(f"Weather.com — {city.title()}",    f"https://weather.com/search/enhancedlocalsearch?where={e}","weather.com","Detailed forecast", ctype="weather"),
        _mk_web_card(f"AccuWeather — {city.title()}",    f"https://www.accuweather.com/en/search-locations?query={e}","accuweather.com","Extended forecast", ctype="weather"),
    ]

def _time_cards(place: str):
    p = place.strip() or "London"; e = quote(p)
    return [
        _mk_web_card(f"Current time in {p.title()}", f"https://www.google.com/search?q=time+in+{e}", "google.com", "Official time & timezone", ctype="time"),
        _mk_web_card(f"Time.is — {p.title()}",       f"https://time.is/{e}",                        "time.is",    "Atomic clock synced time", ctype="time"),
    ]

# ========================
# ------- Routes ---------
# ========================
@app.route("/", methods=["GET"])
def root():
    return jsonify({"ok": True, "service": "Droxion API", "time": datetime.utcnow().isoformat()})

# ---------- Chat ----------
def _structure_answer(prompt: str, raw: str) -> str:
    low = prompt.lower()
    if "pros" in low and "cons" in low:
        pros = ["24/7 availability","Quick information retrieval","Consistency","Wide knowledge base","Non-judgmental support","Task automation","Language support"]
        cons = ["No real-time browsing unless wired","May miss vague context","No personal lived experience","Quality depends on prompt clarity"]
        out = ["### Pros", *(f"{i}. {p}" for i,p in enumerate(pros,1)), "", "### Cons", *(f"{i}. {c}" for i,c in enumerate(cons,1))]
        return "\n".join(out)
    if any(k in low for k in ["steps","how to","plan","roadmap","1 by 1","1by1","one by one"]):
        lines = ["1. Define the goal and success metrics.","2. Gather inputs (users, data, constraints).","3. Draft the approach and choose tools.","4. Execute a small pilot / MVP.","5. Measure results and iterate.","6. Launch, monitor, and maintain."]
        return "### Plan\n" + "\n".join(lines)
    return raw if any(h in raw for h in ["\n1.", "\n- ", "### "]) else raw

@app.post("/chat")
def chat():
    try:
        data = request.get_json(force=True, silent=True) or {}
        prompt = (data.get("prompt") or "").strip()
        if not prompt: return _json_error("Missing 'prompt'")
        lower = prompt.lower()

        if "weather" in lower:
            city = lower.replace("weather","").replace("in","").strip() or "Ahmedabad"
            reply = f"### Weather\n1. **City:** {city.title()}\n2. **Tip:** Open the live tracker below."
            return jsonify({"ok": True, "reply": reply, "cards": _weather_cards(city)})

        if "time" in lower:
            place = lower.replace("time","").replace("now","").replace("in","").strip() or "London"
            reply = f"### Time\n1. **Place:** {place.title()}\n2. **Note:** Open for live time."
            return jsonify({"ok": True, "reply": reply, "cards": _time_cards(place)})

        raw = _openai_chat(prompt)
        if "who" in lower and any(k in lower for k in ["made","created","built"]):
            raw = "I was created and managed by **Dhruv Patel**, powered by OpenAI."
        reply = _structure_answer(prompt, raw)

        _log_line({"route": "/chat", "prompt": prompt, "reply_len": len(reply)})
        return jsonify({"ok": True, "reply": reply})
    except Exception as e:
        traceback.print_exc(); return _json_error(f"chat failed: {_safe_str(e)}", 500)

# ---------- Realtime ----------
@app.post("/realtime")
def realtime():
    try:
        data = request.get_json(force=True, silent=True) or {}
        query  = (data.get("query")  or "").strip()
        intent = (data.get("intent") or "").strip().lower()
        if not query: return jsonify({"summary": "No query.", "cards": []})

        if intent == "weather": cards = _weather_cards(query)
        elif intent == "time":  cards = _time_cards(query)
        elif intent == "crypto":cards = _crypto_cards(query)
        elif intent == "images":
            e = quote(query)
            cards = [
                _mk_web_card(f"Google Images — {query}", f"https://www.google.com/search?tbm=isch&q={e}", "google.com", "Image results"),
                _mk_web_card(f"Bing Images — {query}",   f"https://www.bing.com/images/search?q={e}",    "bing.com",   "Image results"),
            ]
        else:
            cards = _hq_news_cards(query)

        md = f"""### Summary for **{query}**

| Item | Detail |
|---|---|
| Query | {query} |
| Info  | Open the sources below |
"""
        return jsonify({"summary": f"Results for {query}", "markdown": md, "cards": cards})
    except Exception as e:
        traceback.print_exc(); return _json_error(f"realtime failed: {_safe_str(e)}", 500)

# ---------- Suggestions ----------
@app.get("/suggest")
def suggest():
    try:
        q = (request.args.get("q") or "").strip()
        if not q: return jsonify({"suggestions": []})
        base = [f"google: {q}", f"search: {q} latest news", f"table: Top 5 facts about {q}", f"{q} — pros and cons", f"steps to do {q}", f"youtube: {q}"]
        out, seen = [], set()
        for s in base:
            if s not in seen: out.append(s); seen.add(s)
        return jsonify({"suggestions": out[:8]})
    except Exception as e:
        traceback.print_exc(); return _json_error(f"suggest failed: {_safe_str(e)}", 500)

# ---------- Search ----------
@app.post("/search")
def search():
    try:
        data = request.get_json(force=True, silent=True) or {}
        q = (data.get("prompt") or "").strip()
        if not q: return jsonify({"ok": True, "results": []})

        results = []
        results.extend(_hq_news_cards(q))
        results.append(_mk_web_card(f"Google — {q}", "https://www.google.com/search?q=" + quote(q), "google.com", "Top web results"))
        out = [{"title": r["title"], "url": r["url"], "image": r.get("image"), "source": r.get("source"), "snippet": r.get("snippet")} for r in results]
        return jsonify({"ok": True, "results": out})
    except Exception as e:
        return _json_error(f"search failed: {_safe_str(e)}", 500)

# ---------- YouTube helper ----------
@app.post("/search-youtube")
def search_youtube():
    try:
        data = request.get_json(force=True, silent=True) or {}
        q = (data.get("prompt") or "").strip()
        if not q: return _json_error("Missing 'prompt'")
        if not YOUTUBE_API_KEY: return _json_error("YOUTUBE_API_KEY not set on server", 500)

        params = {"key": YOUTUBE_API_KEY, "part": "snippet", "type": "video", "q": q, "maxResults": 1, "safeSearch": "none"}
        r = requests.get("https://www.googleapis.com/youtube/v3/search", params=params, timeout=30)
        if r.status_code >= 400: return _json_error(f"YouTube API error: {r.status_code} {r.text[:200]}", 500)
        j = r.json(); items = j.get("items") or []
        if not items: return jsonify({"ok": True, "url": None})
        vid = items[0]["id"]["videoId"]; url = f"https://www.youtube.com/watch?v={vid}"
        _log_line({"route": "/search-youtube", "q": q, "videoId": vid})
        return jsonify({"ok": True, "url": url})
    except Exception as e:
        traceback.print_exc(); return _json_error(f"youtube search failed: {_safe_str(e)}", 500)

# ---------- Image proxy ----------
@app.get("/img")
def img_proxy():
    u = request.args.get("url", ""); p = urlparse(u)
    if p.scheme not in ("http", "https"): return Response(b"", status=400)
    try:
        r = requests.get(u, headers={"User-Agent": "Mozilla/5.0", "Referer": ""}, timeout=10)
        ct = r.headers.get("content-type", "image/jpeg"); data = r.content[:5_000_000]
        resp = Response(data, content_type=ct)
        resp.headers["Cache-Control"] = "public, max-age=86400"
        resp.headers["Access-Control-Allow-Origin"] = "*"
        return resp
    except Exception:
        return Response(b"", status=502)

# ---------- NEW: OG/Twitter image extractor with cache ----------
_og_cache = {}  # {url: {"img": "...", "ts": epoch}}
_OG_TTL = 60 * 60 * 24  # 24h

def _make_absolute(base_url: str, maybe_rel: str) -> str:
    try:
        if not maybe_rel: return ""
        if maybe_rel.startswith("http://") or maybe_rel.startswith("https://"): return maybe_rel
        return urljoin(base_url, maybe_rel)
    except Exception:
        return maybe_rel

@app.get("/preview")
def preview():
    url = request.args.get("url","").strip()
    if not url: return _json_error("Missing 'url'")
    now = time.time()
    try:
        # serve from cache
        ent = _og_cache.get(url)
        if ent and now - ent.get("ts",0) < _OG_TTL:
            return jsonify({"ok": True, "image_url": ent.get("img")})

        r = requests.get(url, headers={"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36"}, timeout=8)
        if r.status_code >= 400: return jsonify({"ok": False, "image_url": None})
        html = r.text or ""

        # find og:image / twitter:image (basic regex – fast, dependency-free)
        def _find(meta_name):
            pat = re.compile(rf'<meta[^>]+(?:property|name)\s*=\s*["\']{meta_name}["\'][^>]*?content\s*=\s*["\']([^"\']+)["\']', re.I)
            m = pat.search(html); return m.group(1) if m else None

        img = _find("og:image") or _find("twitter:image") or _find("og:image:secure_url")
        img = _make_absolute(url, img)

        # tiny validation (HEAD)
        if img:
            try:
                hr = requests.head(img, allow_redirects=True, timeout=5)
                if hr.status_code >= 400: img = None
            except Exception:
                pass

        _og_cache[url] = {"img": img, "ts": now}
        return jsonify({"ok": True, "image_url": img})
    except Exception:
        return jsonify({"ok": False, "image_url": None})

# ---------- Health ----------
@app.get("/_health/youtube")
def health_youtube():
    ok = bool(YOUTUBE_API_KEY); tail = (YOUTUBE_API_KEY or "")[-4:]
    return jsonify({"ok": ok, "present": ok, "tail": tail})

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
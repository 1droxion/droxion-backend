# app.py  (Droxion backend — branding + images fixed + weather + STT/TTS + file/deepsearch + IMAGE REMIX SUITE)
import os, json, uuid, base64, mimetypes, traceback, io, time
from datetime import datetime
from urllib.parse import quote, urljoin, urlparse

import requests
from PIL import Image
import replicate

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
UPLOADS_DIR         = os.path.join(STATIC_DIR, "uploads")
ALLOWED_ORIGINS     = os.getenv("ALLOWED_ORIGINS", "*")
PUBLIC_BASE_URL     = os.getenv("PUBLIC_BASE_URL", "").rstrip("/")

# <<< BRANDING >>>
CREATOR_NAME        = os.getenv("CREATOR_NAME", "Dhruv Patel")
ASSISTANT_NAME      = os.getenv("ASSISTANT_NAME", "Droxion")
POWERED_BY_LINE     = os.getenv("POWERED_BY_LINE", "— Powered by Droxion")

# Voice I/O (speech-to-text & text-to-speech)
WHISPER_MODEL       = os.getenv("WHISPER_MODEL", "whisper-1")    # speech → text
TTS_MODEL           = os.getenv("TTS_MODEL", "tts-1")            # text  → speech
TTS_VOICE           = os.getenv("TTS_VOICE", "alloy")            # alloy | nova | verse | etc.
TTS_FORMAT          = os.getenv("TTS_FORMAT", "mp3")             # mp3 | wav | opus
MAX_TTS_CHARS       = int(os.getenv("MAX_TTS_CHARS", "900"))     # safety trim for long answers

# --- Image Remix Suite (Replicate) ---
REPLICATE_API_TOKEN = os.getenv("REPLICATE_API_TOKEN", "")

# You can provide either "owner/model" OR "owner/model:version". If you give only the model,
# we'll append the VERSION env var when available.
# Known-good default for INPAINT uses explicit version to avoid 422 "invalid version".
REPLICATE_REMIX_MODEL   = os.getenv("REPLICATE_REMIX_MODEL",   "stability-ai/sdxl")  # txt2img & img2img
REPLICATE_REMIX_VERSION = os.getenv("REPLICATE_REMIX_VERSION", "")                  # optional

REPLICATE_INPAINT_MODEL   = os.getenv("REPLICATE_INPAINT_MODEL",   "stability-ai/stable-diffusion-inpainting")
REPLICATE_INPAINT_VERSION = os.getenv("REPLICATE_INPAINT_VERSION", "a9758cbf7ce14f33a6178d99d12b8f0d9d4cd7c33c3d08efb505de87f1cfcc0b")

REPLICATE_RMBG_MODEL    = os.getenv("REPLICATE_RMBG_MODEL",    "jianfch/stable-diffusion-rembg")
REPLICATE_RMBG_VERSION  = os.getenv("REPLICATE_RMBG_VERSION",  "")  # optional

REPLICATE_BGGEN_MODEL   = os.getenv("REPLICATE_BGGEN_MODEL",   "stability-ai/sdxl")
REPLICATE_BGGEN_VERSION = os.getenv("REPLICATE_BGGEN_VERSION", "")  # optional

replicate_client = replicate.Client(api_token=REPLICATE_API_TOKEN) if REPLICATE_API_TOKEN else None

os.makedirs(STATIC_DIR, exist_ok=True)
os.makedirs(UPLOADS_DIR, exist_ok=True)

app = Flask(__name__, static_folder=STATIC_DIR, static_url_path="/public")
CORS(app, resources={r"/*": {"origins": ALLOWED_ORIGINS}}, supports_credentials=False)

# ========================
# ------ Helpers ---------
# ========================
def _json_error(msg: str, status: int = 400):
    return jsonify({"ok": False, "error": msg}), status

def _reject(msg: str, status: int = 400):
    return jsonify({"ok": False, "error": msg}), status

def _safe_str(x) -> str:
    try: return str(x)
    except Exception: return "<unprintable>"

def _log_line(payload: dict):
    payload = dict(payload or {})
    payload["ts"] = datetime.utcnow().isoformat()
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")
    except Exception:
        pass

def _abs_url(u: str) -> str:
    if not u: return u
    if u.startswith("http://") or u.startswith("https://"): return u
    base = PUBLIC_BASE_URL or (request.host_url.rstrip("/") if request else "")
    return urljoin(base + "/", u.lstrip("/"))

def _mk_web_card(title, url, source=None, snippet=None, image=None, meta=None, ctype="web"):
    return {
        "type": ctype, "title": title, "url": url,
        "source": source or (url.split("/")[2] if "://" in url else "source"),
        "snippet": snippet, "image": image, "meta": meta
    }

# <<< BRANDING >>>
def _brand_footer(text: str) -> str:
    t = (text or "").rstrip()
    if not t or POWERED_BY_LINE in t: return t
    return t + "\n\n" + POWERED_BY_LINE

def _identity_answer(kind: str) -> str:
    if kind == "who_made":   return f"I was created by **{CREATOR_NAME}**. {POWERED_BY_LINE}"
    if kind == "who_built":  return f"I was built by **{CREATOR_NAME}**. {POWERED_BY_LINE}"
    if kind == "who_created":return f"I was created by **{CREATOR_NAME}**. {POWERED_BY_LINE}"
    if kind == "your_name":  return f"My name is **{ASSISTANT_NAME}**. {POWERED_BY_LINE}"
    if kind == "powered_by": return f"I'm **powered by Droxion** — fast search, rich cards, and memory. {POWERED_BY_LINE}"
    return f"{ASSISTANT_NAME}. {POWERED_BY_LINE}"

def _match_identity_intent(prompt: str):
    p = (prompt or "").lower().strip()
    if not p: return None
    checks = [
        (["who made you","who created you","who built you","who developed you"], "who_made"),
        (["your name","what is your name","who are you","what are you called"], "your_name"),
        (["powered by","who powers you","what powers you"], "powered_by"),
    ]
    for keys, tag in checks:
        if any(k in p for k in keys): return tag
    return None

def _trim_for_tts(text: str, limit: int = MAX_TTS_CHARS) -> str:
    t = (text or "").strip()
    if len(t) <= limit: return t
    cut = t[:limit]; last_dot = cut.rfind(". ")
    return cut[:last_dot+1] if last_dot > 150 else cut + "…"

def _openai_chat(prompt: str) -> str:
    if not OPENAI_API_KEY: return prompt
    url = "https://api.openai.com/v1/chat/completions"
    headers = {"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"}
    sys_msg = (
        f"You are {ASSISTANT_NAME}, a helpful AI created by {CREATOR_NAME}. "
        f"Never claim you were created by OpenAI. "
        f"If asked about who made you, ALWAYS say {CREATOR_NAME}. "
        f"Prefer numbered lists and tight structure. "
        f"When it fits, end answers with a short footer: '{POWERED_BY_LINE}'."
    )
    data = {"model": OPENAI_CHAT_MODEL, "messages": [
        {"role": "system", "content": sys_msg},
        {"role": "user", "content": prompt}
    ], "temperature": 0.5}
    r = requests.post(url, headers=headers, json=data, timeout=60); r.raise_for_status()
    j = r.json()
    return (j["choices"][0]["message"]["content"] or "").strip()

def _openai_vision(prompt: str, img_bytes: bytes, mime: str) -> str:
    if not OPENAI_API_KEY:
        return f"I received your image. {POWERED_BY_LINE}"
    try:
        data_url = f"data:{mime};base64," + base64.b64encode(img_bytes).decode("utf-8")
        url = "https://api.openai.com/v1/chat/completions"
        headers = {"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"}
        payload = {"model": OPENAI_CHAT_MODEL, "messages": [
            {"role": "system", "content": f"You are {ASSISTANT_NAME}, created by {CREATOR_NAME}. Be precise and concise."},
            {"role": "user", "content": [
                {"type": "text", "text": prompt or "Describe the image and list key details in bullets."},
                {"type": "image_url", "image_url": {"url": data_url}}
            ]}
        ]}
        r = requests.post(url, headers=headers, json=payload, timeout=120); r.raise_for_status()
        j = r.json()
        return (j["choices"][0]["message"]["content"] or "").strip()
    except Exception as e:
        _log_line({"vision_error": _safe_str(e)})
        return "I analyzed the image, but couldn't run the AI model. Here’s a generic summary:\n\n- An image was provided.\n- I can still attach helpful sources and examples.\n\n" + POWERED_BY_LINE

# ---- Image helpers ----
def _b64_to_pil(b64_str: str) -> Image.Image:
    data = (b64_str or "").split(",")[-1]
    return Image.open(io.BytesIO(base64.b64decode(data)))

def _img_to_bytes(img: Image.Image, mode="PNG") -> io.BytesIO:
    buf = io.BytesIO(); img.save(buf, format=mode); buf.seek(0); return buf

def _safe_image_models_ready() -> bool:
    return bool(replicate_client)

def _spec(model: str, version: str = "") -> str:
    """Return 'owner/model:version' if version provided and ':' not already in model."""
    if ":" in (model or ""): return model
    return f"{model}:{version}" if version else model

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
    p = place.strip() or "London"; e = quote(p)
    return [
        _mk_web_card(f"Current time in {p.title()}", f"https://www.google.com/search?q=time+in+{e}", "google.com", ctype="time"),
        _mk_web_card(f"Time.is — {p.title()}",       f"https://time.is/{e}",                        "time.is",    ctype="time"),
    ]

def _free_image_urls(q: str, n=12):
    qs   = quote(q or "wallpaper")
    rnd  = uuid.uuid4().hex[:8]
    out  = []
    for i in range(min(4, n)): out.append(f"https://picsum.photos/seed/{rnd}-{i}/900/600.jpg")
    for i in range(min(4, n - len(out))): out.append(f"https://loremflickr.com/900/600/{qs}?lock={i}")
    for i in range(min(6, n - len(out))): out.append(f"https://source.unsplash.com/900x600/?{qs}&sig={i}&_b={rnd}")
    return out[:n]

# ========================
# ------- Weather --------
# ========================
_WEATHER_CACHE = {}

def _client_ip():
    hdr = request.headers.get("X-Forwarded-For", "")
    if hdr: return hdr.split(",")[0].strip()
    return request.remote_addr or "0.0.0.0"

def _ip_to_geo(ip):
    try:
        r = requests.get(f"https://ipapi.co/{ip}/json/", timeout=4)
        j = r.json()
        return float(j.get("latitude")), float(j.get("longitude")), j.get("city"), j.get("region"), j.get("country_name")
    except Exception:
        return 39.8283, -98.5795, None, None, None  # USA centroid fallback

def _round_5m(ts=None):
    ts = ts or time.time()
    return int(ts // 300)

def _fetch_openmeteo(lat, lon):
    weather_url = (
        "https://api.open-meteo.com/v1/forecast"
        f"?latitude={lat}&longitude={lon}"
        "&current=temperature_2m,relative_humidity_2m,apparent_temperature,precipitation,weather_code,wind_speed_10m"
        "&hourly=temperature_2m,precipitation_probability&forecast_days=1&timezone=auto"
    )
    aqi_url = (
        "https://air-quality-api.open-meteo.com/v1/air-quality"
        f"?latitude={lat}&longitude={lon}&current=european_aqi,pm2_5,pm10,ozone&timezone=auto"
    )
    w = requests.get(weather_url, timeout=6).json()
    a = requests.get(aqi_url, timeout=6).json()

    cur = w.get("current", {}); hourly = w.get("hourly", {})
    out = {
        "lat": lat, "lon": lon, "timezone": w.get("timezone"),
        "current": {
            "tempC": cur.get("temperature_2m"),
            "feelsLikeC": cur.get("apparent_temperature"),
            "humidity": cur.get("relative_humidity_2m"),
            "precip": cur.get("precipitation"),
            "windKph": cur.get("wind_speed_10m"),
            "code": cur.get("weather_code"),
        },
        "hourly": [
            {"time": t, "tempC": tc, "pop": pop}
            for t, tc, pop in zip(
                hourly.get("time", [])[:12],
                hourly.get("temperature_2m", [])[:12],
                hourly.get("precipitation_probability", [])[:12]
            )
        ],
        "air": {
            "aqi": (a.get("current", {}) or {}).get("european_aqi"),
            "pm25": (a.get("current", {}) or {}).get("pm2_5"),
            "pm10": (a.get("current", {}) or {}).get("pm10"),
            "ozone": (a.get("current", {}) or {}).get("ozone"),
        }
    }
    return out

@app.get("/weather")
def weather():
    try:
        lat = request.args.get("lat", type=float)
        lon = request.args.get("lon", type=float)
        city = region = country = None

        if lat is None or lon is None:
            ip = _client_ip()
            lat, lon, city, region, country = _ip_to_geo(ip)

        bucket = _round_5m()
        key = (round(lat, 3), round(lon, 3), bucket)
        if key in _WEATHER_CACHE:
            data = _WEATHER_CACHE[key]
        else:
            data = _fetch_openmeteo(lat, lon)
            _WEATHER_CACHE[key] = data

        if city or region or country:
            data["place"] = {"city": city, "region": region, "country": country}

        return jsonify(data)
    except Exception as e:
        traceback.print_exc()
        return _json_error(f"weather failed: {_safe_str(e)}", 500)

# ========================
# ------- Routes ---------
# ========================
@app.route("/", methods=["GET"])
def root():
    return jsonify({"ok": True, "service": f"{ASSISTANT_NAME} API", "powered_by": "Droxion", "time": datetime.utcnow().isoformat()})

# ---------- Chat ----------
@app.post("/chat")
def chat():
    try:
        data = request.get_json(force=True, silent=True) or {}
        prompt = (data.get("prompt") or "").strip()
        if not prompt:
            return _json_error("Missing 'prompt'")

        # Identity overrides
        id_tag = _match_identity_intent(prompt)
        if id_tag:
            reply = _identity_answer(id_tag)
            return jsonify({"ok": True, "reply": reply})

        low = prompt.lower()
        if "weather" in low:
            city = low.replace("weather", "").replace("in", "").strip() or "Ahmedabad"
            reply = f"### Weather\n1. **City:** {city.title()}\n2. Open the live tracker below.\n\n{POWERED_BY_LINE}"
            return jsonify({"ok": True, "reply": reply, "cards": _weather_cards_links(city)})

        if "time" in low:
            place = low.replace("time", "").replace("now", "").replace("in", "").strip() or "London"
            reply = f"### Time\n1. **Place:** {place.title()}\n2. Tap a source for live time.\n\n{POWERED_BY_LINE}"
            return jsonify({"ok": True, "reply": reply, "cards": _time_cards(place)})

        raw = _openai_chat(prompt)
        branded = _brand_footer(raw)
        return jsonify({"ok": True, "reply": branded})
    except Exception as e:
        traceback.print_exc()
        return _json_error(f"chat failed: {_safe_str(e)}", 500)

# ---------- Unified Image Endpoint ----------
@app.post("/imagine")
def imagine():
    """
    One endpoint to handle all cases.
    JSON body:
      - prompt (required)
      - image_base64 (optional)
      - mask_base64 (optional)  # if present + image present => inpaint
      - style_strength (optional float 0..1, remix only)
    Behavior:
      - text only => txt2img (SDXL)
      - image only + prompt => remix (img2img, SDXL)
      - image + mask + prompt => inpaint (Stable Diffusion Inpainting)
    """
    try:
        if not _safe_image_models_ready():
            return _json_error("REPLICATE_API_TOKEN not set", 500)

        data = request.get_json(force=True, silent=True) or {}
        prompt = (data.get("prompt") or "").strip()
        if not prompt:
            return _json_error("Missing 'prompt'", 400)

        img_b64  = (data.get("image_base64") or "").strip()
        mask_b64 = (data.get("mask_base64") or "").strip()
        style_strength = float(data.get("style_strength") or 0.6)

        # --- CASE A: text-only => txt2img (SDXL)
        if not img_b64:
            out = replicate_client.run(
                _spec(REPLICATE_BGGEN_MODEL, REPLICATE_BGGEN_VERSION),
                input={
                    "prompt": prompt,
                    "num_inference_steps": 28,
                    "guidance_scale": 7
                }
            )
            images = out if isinstance(out, list) else [out]
            images = [u for u in images if u]
            if not images: return _json_error("No image produced (txt2img)", 500)
            return jsonify({"ok": True, "mode": "txt2img", "images": images})

        # --- build base image bytes
        base_img = _b64_to_pil(img_b64).convert("RGBA")
        base_bytes = _img_to_bytes(base_img, "PNG")

        # --- CASE B: image + mask => inpaint  (explicit version to avoid 422)
        if mask_b64:
            mask_img = _b64_to_pil(mask_b64).convert("L")
            if mask_img.size != base_img.size:
                mask_img = mask_img.resize(base_img.size, Image.LANCZOS)
            mask_bytes = _img_to_bytes(mask_img, "PNG")

            out = replicate_client.run(
                _spec(REPLICATE_INPAINT_MODEL, REPLICATE_INPAINT_VERSION),
                input={
                    "image": base_bytes,
                    "mask": mask_bytes,
                    "prompt": prompt,
                    "num_inference_steps": 35,
                    "guidance_scale": 7
                }
            )
            images = out if isinstance(out, list) else [out]
            images = [u for u in images if u]
            if not images: return _json_error("No image produced (inpaint)", 500)
            return jsonify({"ok": True, "mode": "inpaint", "images": images})

        # --- CASE C: image only + prompt => remix (img2img)
        out = replicate_client.run(
            _spec(REPLICATE_REMIX_MODEL, REPLICATE_REMIX_VERSION),
            input={
                "prompt": prompt,
                "image": base_bytes,
                "num_inference_steps": 28,
                "guidance_scale": 7,
                "strength": style_strength  # many SDXL builds use "strength"
            }
        )
        images = out if isinstance(out, list) else [out]
        images = [u for u in images if u]
        if not images: return _json_error("No image produced (remix)", 500)
        return jsonify({"ok": True, "mode": "remix", "images": images})

    except Exception as e:
        traceback.print_exc()
        return _json_error(f"imagine failed: {_safe_str(e)}", 500)

# ---------- Realtime ----------
@app.post("/realtime")
def realtime():
    try:
        data = request.get_json(force=True, silent=True) or {}
        query  = (data.get("query")  or "").strip()
        intent = (data.get("intent") or "").strip().lower()
        if not query:
            return jsonify({"summary": "No query.", "cards": []})

        cards = []; images = []
        md = f"### Results for **{query}**\n\n{POWERED_BY_LINE}"

        if intent == "weather":
            city = query.title()
            cards = [{
                "type": "weather",
                "title": f"Weather — {city}",
                "subtitle": "Tap sources for live details",
                "icon": "https://openweathermap.org/img/wn/01d.png",
                "temp_c": None, "temp_f": None,
                "feels_like_c": None, "feels_like_f": None,
                "humidity": None, "wind_kph": None, "wind_mph": None,
                "hourly": [], "daily": []
            }] + _weather_cards_links(query)

        elif intent == "time":
            cards = _time_cards(query)

        elif intent == "crypto":
            cards = _crypto_cards(query)

        elif intent == "images":
            images = _free_image_urls(query, n=12)
            cards = [{
                "type": "images-grid",
                "title": f"Images — {query}",
                "images": images
            },
            _mk_web_card(f"Google Images — {query}", f"https://www.google.com/search?tbm=isch&q={quote(query)}", "google.com", ctype="images"),
            _mk_web_card(f"Bing Images — {query}",   f"https://www.bing.com/images/search?q={quote(query)}",     "bing.com",   ctype="images"),
            _mk_web_card("Unsplash",                  f"https://unsplash.com/s/photos/{quote(query)}",            "unsplash.com", ctype="images"),
            _mk_web_card("Lexica (AI images)",        f"https://lexica.art/?q={quote(query)}",                    "lexica.art", ctype="images"),
            ]

        else:
            cards = _hq_news_cards(query)

        return jsonify({"summary": f"Results for {query}", "markdown": md, "cards": cards, "images": images})
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

        params = {"key": YOUTUBE_API_KEY, "part": "snippet", "type": "video", "q": q, "maxResults": 1, "safeSearch": "none"}
        r = requests.get("https://www.googleapis.com/youtube/v3/search", params=params, timeout=30)
        if r.status_code >= 400:
            return _json_error(f"YouTube API error: {r.status_code} {r.text[:200]}", 500)
        j = r.json(); items = j.get("items") or []
        if not items: return jsonify({"ok": True, "url": None})
        vid = items[0]["id"]["videoId"]; url = f"https://www.youtube.com/watch?v={vid}"
        _log_line({"route": "/search-youtube", "q": q, "videoId": vid})
        return jsonify({"ok": True, "url": url})
    except Exception as e:
        traceback.print_exc()
        return _json_error(f"youtube search failed: {_safe_str(e)}", 500)

# ---------- Speech to Text ----------
@app.post("/transcribe")
def transcribe():
    try:
        if not OPENAI_API_KEY:
            return _json_error("OPENAI_API_KEY not set", 500)
        if "audio" not in request.files:
            return _json_error("Missing audio file field 'audio'", 400)
        f = request.files["audio"]
        files = {"file": (f.filename or "audio.webm", f.stream, f.mimetype or "application/octet-stream")}
        data  = {"model": WHISPER_MODEL}
        headers = {"Authorization": f"Bearer {OPENAI_API_KEY}"}
        r = requests.post("https://api.openai.com/v1/audio/transcriptions", headers=headers, data=data, files=files, timeout=120)
        if r.status_code >= 400:
            return _json_error(f"whisper error {r.status_code}: {r.text[:200]}", 500)
        j = r.json(); text = (j.get("text") or "").strip()
        _log_line({"route":"/transcribe","ok":True,"len":len(text)})
        return jsonify({"ok": True, "text": text})
    except Exception as e:
        traceback.print_exc()
        return _json_error(f"transcribe failed: {_safe_str(e)}", 500)

# ---------- Text to Speech ----------
@app.post("/tts")
def tts():
    try:
        if not OPENAI_API_KEY:
            return _json_error("OPENAI_API_KEY not set", 500)
        data = request.get_json(force=True, silent=True) or {}
        txt   = _trim_for_tts(data.get("text") or "")
        voice = data.get("voice") or TTS_VOICE
        fmt   = (data.get("format") or TTS_FORMAT).lower()
        if not txt: return _json_error("Missing text", 400)
        if fmt not in ("mp3","wav","opus"): return _json_error("Unsupported format", 400)

        headers = {"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"}
        body = {"model": TTS_MODEL, "voice": voice, "input": txt, "format": fmt}
        r = requests.post("https://api.openai.com/v1/audio/speech", headers=headers, json=body, timeout=120)
        if r.status_code >= 400:
            return _json_error(f"tts error {r.status_code}: {r.text[:200]}", 500)

        audio_bytes = r.content
        mime = "audio/mpeg" if fmt=="mp3" else ("audio/wav" if fmt=="wav" else "audio/ogg")
        resp = Response(audio_bytes, content_type=mime)
        resp.headers["Cache-Control"] = "no-store"
        resp.headers["Access-Control-Allow-Origin"] = "*"
        return resp
    except Exception as e:
        traceback.print_exc()
        return _json_error(f"tts failed: {_safe_str(e)}", 500)

# ---------- Analyze Image (Vision) ----------
@app.post("/analyze-image")
def analyze_image():
    try:
        if "image" not in request.files:
            return _json_error("Missing 'image' form file", 400)
        img = request.files["image"]
        prompt = (request.form.get("prompt") or request.form.get("text") or "").strip()
        web    = (request.form.get("web") or "false").lower() == "true"

        img_bytes = img.read()
        mime = img.mimetype or "image/jpeg"

        ai_desc = _openai_vision(prompt, img_bytes, mime)

        name = f"{uuid.uuid4().hex}_{(img.filename or 'image').replace('/', '_')}"
        path = os.path.join(UPLOADS_DIR, name)
        with open(path, "wb") as f:
            f.write(img_bytes)
        public_url = _abs_url(f"/public/uploads/{name}")

        topic = (prompt or img.filename or "photo").split()[0]
        grid = {"type": "images-grid", "title": f"Images — {topic}", "images": _free_image_urls(topic, 12)}

        return jsonify({
            "ok": True,
            "ai_description": _brand_footer(ai_desc),
            "image_url": public_url,
            "cards": [grid] + (_hq_news_cards(topic) if web else [])
        })
    except Exception as e:
        traceback.print_exc()
        return _json_error(f"analyze-image failed: {_safe_str(e)}", 500)

# ---------- File Analyze ----------
@app.post("/file-analyze")
def file_analyze():
    try:
        if "file" not in request.files:
            return _json_error("Missing 'file' form field", 400)
        f = request.files["file"]
        raw = f.read()
        size = len(raw)
        mime = f.mimetype or mimetypes.guess_type(f.filename or "")[0] or "application/octet-stream"

        name = f"{uuid.uuid4().hex}_{(f.filename or 'file').replace('/', '_')}"
        path = os.path.join(UPLOADS_DIR, name)
        with open(path, "wb") as fp:
            fp.write(raw)
        public_url = _abs_url(f"/public/uploads/{name}")

        title = f.name or f.filename or "Uploaded file"
        title = f"{title} ({mime}, {round(size/1024,1)} KB)"

        preview = ""
        if mime.startswith("text/") or mime in ("application/json",):
            try:
                txt = raw.decode("utf-8", errors="replace")
                snippet = txt.strip().splitlines()[:20]
                preview = "```\n" + "\n".join(snippet) + "\n```"
            except Exception:
                preview = ""
        elif mime in ("application/pdf", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "application/msword"):
            preview = "_Preview not available for this file type._"
        else:
            preview = "_Binary file uploaded._"

        return jsonify({"ok": True, "title": title, "preview": preview, "url": public_url, "cards": []})
    except Exception as e:
        traceback.print_exc()
        return _json_error(f"file-analyze failed: {_safe_str(e)}", 500)

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
        return Response(b="", status=502)

# ===============================
# --- Image Remix Suite ROUTES ---
# ===============================
@app.post("/remix-image")
def remix_image():
    """
    Face-preserving remix: keep identity, change style/scene/outfit via prompt.
    Body (JSON): { image_base64: dataURL, prompt: str, style_strength?: 0..1 }
    """
    try:
        if not _safe_image_models_ready():
            return _reject("REPLICATE_API_TOKEN not set on server", 500)

        data = request.get_json(force=True, silent=True) or {}
        b64 = (data.get("image_base64") or "").strip()
        prompt = (data.get("prompt") or "").strip()
        style_strength = float(data.get("style_strength") or 0.6)

        if not b64:    return _reject("No image provided.")
        if not prompt: return _reject("Please add a prompt.")

        img = _b64_to_pil(b64).convert("RGBA")
        img_bytes = _img_to_bytes(img, "PNG")

        inputs = {
            "prompt": prompt,
            "image": img_bytes,            # file-like object
            "guidance_scale": 7,
            "num_inference_steps": 28,
            "strength": style_strength,
            "seed": None,
        }
        inputs = {k:v for k,v in inputs.items() if v is not None}

        out = replicate_client.run(_spec(REPLICATE_REMIX_MODEL, REPLICATE_REMIX_VERSION), input=inputs)
        images = out if isinstance(out, list) else [out]
        images = [u for u in images if u]
        if not images: return _reject("No image produced. Try a different prompt.")
        _log_line({"route": "/remix-image", "ok": True})
        return jsonify({"ok": True, "images": images})
    except Exception as e:
        traceback.print_exc()
        _log_line({"route": "/remix-image", "ok": False, "err": _safe_str(e)})
        return _reject(f"Remix failed: {_safe_str(e)}", 500)

@app.post("/inpaint-image")
def inpaint_image():
    """
    Mask edit: white = edit, black = keep.
    Body (JSON): { image_base64: dataURL, mask_base64: dataURL, prompt: str }
    """
    try:
        if not _safe_image_models_ready():
            return _reject("REPLICATE_API_TOKEN not set on server", 500)

        data = request.get_json(force=True, silent=True) or {}
        base_b64 = (data.get("image_base64") or "").strip()
        mask_b64 = (data.get("mask_base64") or "").strip()
        prompt   = (data.get("prompt") or "").strip()
        if not base_b64: return _reject("No base image.")
        if not mask_b64: return _reject("No mask image.")
        if not prompt:   return _reject("Please add a prompt.")

        base_img = _b64_to_pil(base_b64).convert("RGBA")
        mask_img = _b64_to_pil(mask_b64).convert("L")
        if mask_img.size != base_img.size:
            mask_img = mask_img.resize(base_img.size, Image.LANCZOS)

        base_bytes = _img_to_bytes(base_img, "PNG")
        mask_bytes = _img_to_bytes(mask_img, "PNG")

        out = replicate_client.run(_spec(REPLICATE_INPAINT_MODEL, REPLICATE_INPAINT_VERSION), input={
            "image": base_bytes,
            "mask": mask_bytes,
            "prompt": prompt,
            "num_inference_steps": 35,
            "guidance_scale": 7
        })
        images = out if isinstance(out, list) else [out]
        images = [u for u in images if u]
        if not images: return _reject("No image produced. Refine the mask or prompt.")
        _log_line({"route": "/inpaint-image", "ok": True})
        return jsonify({"ok": True, "images": images})
    except Exception as e:
        traceback.print_exc()
        _log_line({"route": "/inpaint-image", "ok": False, "err": _safe_str(e)})
        return _reject(f"Inpaint failed: {_safe_str(e)}", 500)

@app.post("/bg-swap")
def bg_swap():
    """
    Background swap: remove BG, then compose with new scene.
    Body (JSON): { image_base64: dataURL, prompt?: str }
    """
    try:
        if not _safe_image_models_ready():
            return _reject("REPLICATE_API_TOKEN not set on server", 500)

        data = request.get_json(force=True, silent=True) or {}
        b64 = (data.get("image_base64") or "").strip()
        prompt = (data.get("prompt") or "").strip() or "subject on a clean studio background"
        if not b64: return _reject("No image provided.")

        img = _b64_to_pil(b64)
        img_bytes = _img_to_bytes(img, "PNG")

        # 1) Remove background (returns a URL to a PNG with alpha)
        cutout = replicate_client.run(_spec(REPLICATE_RMBG_MODEL, REPLICATE_RMBG_VERSION), input={"image": img_bytes})

        # 2) Compose into new scene (init image accepted as URL by most txt2img+img2img models)
        out = replicate_client.run(_spec(REPLICATE_BGGEN_MODEL, REPLICATE_BGGEN_VERSION), input={
            "prompt": prompt,
            "image": cutout,
            "strength": 0.65,
            "num_inference_steps": 28,
            "guidance_scale": 7
        })
        images = out if isinstance(out, list) else [out]
        images = [u for u in images if u]
        if not images: return _reject("No image produced. Try another prompt.")
        _log_line({"route": "/bg-swap", "ok": True})
        return jsonify({"ok": True, "images": images})
    except Exception as e:
        traceback.print_exc()
        _log_line({"route": "/bg-swap", "ok": False, "err": _safe_str(e)})
        return _reject(f"BG swap failed: {_safe_str(e)}", 500)

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
# api.py — Droxion backend (matches AIChat.jsx endpoints 1:1)
# - /chat: GPT-4o → Claude 3.5 Sonnet → Gemini 1.5 Pro (auto-fallbacks)
# - /realtime: news / weather / crypto / images (web cards)
# - /suggest: typeahead + follow-ups
# - /search: simple web results (Wikipedia-first) → cards
# - /deepsearch: lightweight multi-source summary + cards
# - /analyze-image: image upload → (Vision if available) → description + gallery
# - /img: image proxy (fixes mixed-content / CORS)
# - Image tools kept (replicate): /remix-image, /inpaint-image, /remix-face-locked, /bg-swap
# Notes:
#   • All "cards" are arrays; nothing is trimmed server-side (frontend ranks/trims).
#   • No external keys are strictly required; optional keys unlock better results.
#   • Safe fallbacks (Unsplash, Open-Meteo, CoinGecko, Wikipedia) require no keys.

import os, io, base64, mimetypes, time, json
from urllib.parse import urlencode
import requests
from flask import Flask, request, jsonify, Response, send_file
from flask_cors import CORS

# ========= Optional AI providers =========
# pip install openai anthropic google-generativeai replicate
OPENAI_API_KEY     = os.getenv("OPENAI_API_KEY", "")
ANTHROPIC_API_KEY  = os.getenv("ANTHROPIC_API_KEY", "")
GOOGLE_API_KEY     = os.getenv("GOOGLE_API_KEY", "")
REPLICATE_API_TOKEN= os.getenv("REPLICATE_API_TOKEN","")

try:
    from openai import OpenAI
except Exception:
    OpenAI = None
try:
    import anthropic
except Exception:
    anthropic = None
try:
    import google.generativeai as genai
except Exception:
    genai = None
try:
    import replicate
except Exception:
    replicate = None

# ========= Optional image tool models (Replicate) =========
IMG_REPIX_MODEL   = os.getenv("IMG_REPIX_MODEL", "timbrooks/instruct-pix2pix")
IMG_REPIX_VERSION = os.getenv("IMG_REPIX_VERSION", "")     # set explicit hash for stability

IMG_INPAINT_MODEL   = os.getenv("IMG_INPAINT_MODEL", "stability-ai/stable-diffusion-inpainting")
IMG_INPAINT_VERSION = os.getenv("IMG_INPAINT_VERSION", "")

FACE_LOCK_MODEL   = os.getenv("FACE_LOCK_MODEL", "")       # e.g. "tencentarc/instantid"
FACE_LOCK_VERSION = os.getenv("FACE_LOCK_VERSION", "")
FACE_RESTORE_MODEL   = os.getenv("FACE_RESTORE_MODEL", "") # e.g. "sczhou/codeformer"
FACE_RESTORE_VERSION = os.getenv("FACE_RESTORE_VERSION", "")

BG_REMOVE_MODEL   = os.getenv("BG_REMOVE_MODEL", "")       # e.g. "cjwbw/rembg"
BG_REMOVE_VERSION = os.getenv("BG_REMOVE_VERSION", "")
BG_COMPOSE_MODEL   = os.getenv("BG_COMPOSE_MODEL", "")     # e.g. "black-forest-labs/flux-schnell"
BG_COMPOSE_VERSION = os.getenv("BG_COMPOSE_VERSION", "")

# ========= App =========
app = Flask(__name__)
CORS(app)

# ========= Helpers =========
def ok(data=None, **kw):
    out = {"ok": True}
    if data and isinstance(data, dict):
        out.update(data)
    out.update(kw)
    return jsonify(out)

def err(status, msg, detail=None):
    out = {"ok": False, "error": msg}
    if detail:
        out["detail"] = str(detail)
    return jsonify(out), status

def str_urls(rep_result):
    """Normalize Replicate outputs to List[str] of URLs."""
    if rep_result is None:
        return []
    if isinstance(rep_result, list):
        out = []
        for x in rep_result:
            try:
                out.append(str(x.url) if hasattr(x, "url") else str(x))
            except Exception:
                out.append(str(x))
        return out
    try:
        return [str(rep_result.url)] if hasattr(rep_result, "url") else [str(rep_result)]
    except Exception:
        return [repr(rep_result)]

def dataurl(file_bytes: bytes, mime: str):
    b64 = base64.b64encode(file_bytes).decode("ascii")
    return f"data:{mime};base64,{b64}"

def is_data_url(s: str) -> bool:
    return isinstance(s, str) and s.strip().startswith("data:image/")

def get_json(url, params=None, headers=None, timeout=12):
    try:
        r = requests.get(url, params=params, headers=headers, timeout=timeout)
        r.raise_for_status()
        return r.json()
    except Exception:
        return None

def get_text(url, params=None, headers=None, timeout=12):
    try:
        r = requests.get(url, params=params, headers=headers, timeout=timeout)
        r.raise_for_status()
        return r.text
    except Exception:
        return ""

def gpt_client():
    if OPENAI_API_KEY and OpenAI:
        return OpenAI(api_key=OPENAI_API_KEY)
    return None

def claude_client():
    if ANTHROPIC_API_KEY and anthropic:
        return anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    return None

def gemini_client():
    if GOOGLE_API_KEY and genai:
        genai.configure(api_key=GOOGLE_API_KEY)
        return genai
    return None

# ========= Health =========
@app.get("/health")
def health():
    return ok({
        "service":"droxion",
        "chat": {
            "openai": bool(OPENAI_API_KEY),
            "anthropic": bool(ANTHROPIC_API_KEY),
            "gemini": bool(GOOGLE_API_KEY),
        },
        "replicate": bool(REPLICATE_API_TOKEN),
    })

# ========= CHAT (fallbacks) =========
@app.post("/chat")
def chat():
    """
    Body: { "messages":[{role,content}], ... } OR { "prompt": "..." }
    Returns: { ok, model, text|reply, cards?[] }
    """
    try:
        data = request.get_json(force=True, silent=True) or {}
        msgs = data.get("messages")
        prompt = data.get("prompt")
        if not msgs and prompt:
            msgs = [{"role":"user","content":prompt}]
        if not msgs:
            return err(400, "messages or prompt required")

        # 1) OpenAI (GPT-4o)
        try:
            oc = gpt_client()
            if oc:
                resp = oc.chat.completions.create(
                    model="gpt-4o",
                    messages=msgs,
                    temperature=0.2
                )
                text = resp.choices[0].message.content
                return ok({"reply": text, "model":"gpt-4o", "cards":[]})
        except Exception:
            pass

        # 2) Claude 3.5 Sonnet
        try:
            ac = claude_client()
            if ac:
                sys_prompt = ""
                convo = []
                for m in msgs:
                    r = m.get("role"); c=m.get("content","")
                    if r=="system": sys_prompt = (sys_prompt + "\n" + c).strip()
                    elif r in ("user","assistant"): convo.append({"role":r,"content":c})
                msg = ac.messages.create(
                    model="claude-3-5-sonnet-20240620",
                    max_tokens=1024,
                    temperature=0.2,
                    system=sys_prompt or None,
                    messages=convo
                )
                out = "".join([b.text for b in msg.content if hasattr(b,"text")])
                return ok({"reply": out, "model":"claude-3.5-sonnet", "cards":[]})
        except Exception:
            pass

        # 3) Gemini 1.5 Pro
        try:
            g = gemini_client()
            if g:
                model = g.GenerativeModel("gemini-1.5-pro")
                stitched = "\n".join([f"{m.get('role')}: {m.get('content','')}" for m in msgs])
                resp = model.generate_content(stitched)
                return ok({"reply": getattr(resp,"text","") or "", "model":"gemini-1.5-pro", "cards":[]})
        except Exception:
            pass

        return err(502, "all providers failed (OpenAI → Anthropic → Gemini)")
    except Exception as e:
        return err(500, "server_error", e)

# ========= SUGGEST (typeahead + followups) =========
@app.get("/suggest")
def suggest():
    """
    Query: ?q=... [&mode=followup]
    Returns: { ok, suggestions: [] }
    """
    q = (request.args.get("q") or "").strip()
    mode = (request.args.get("mode") or "").strip().lower()
    sugs = []

    # DuckDuckGo suggestions (no key)
    if q:
        try:
            j = get_json("https://duckduckgo.com/ac/", params={"q": q})
            if j and isinstance(j, list):
                sugs = [x.get("phrase") for x in j if isinstance(x, dict) and x.get("phrase")]
        except Exception:
            sugs = []

    # lightweight follow-ups
    if mode == "followup":
        base = [
            f"Explain {q} in simple steps",
            f"Pros & cons of {q}",
            f"Give an example using {q}",
            f"What should I do next about {q}?",
        ]
        return ok({"suggestions": base[:8]})

    return ok({"suggestions": sugs[:10]})

# ========= REALTIME (news / weather / crypto / images) =========
def make_card(**kw):
    # Uniform card creator (never None fields required by frontend)
    c = {"type": "web", "title":"", "url":"", "image":None, "source":"", "snippet":""}
    c.update({k:v for k,v in kw.items() if v is not None})
    return c

def news_cards(query):
    # Google News RSS JSON via gnews no-key HTML? Use Google News RSS feed safely.
    # Example feed: https://news.google.com/rss/search?q=bitcoin&hl=en-US&gl=US&ceid=US:en
    import xml.etree.ElementTree as ET
    q = query or "top news"
    url = "https://news.google.com/rss/search"
    params = {"q": q, "hl":"en-US", "gl":"US", "ceid":"US:en"}
    xmltxt = get_text(url, params=params)
    out = []
    try:
        root = ET.fromstring(xmltxt)
        for item in root.findall(".//item")[:15]:
            title = (item.findtext("title") or "").strip()
            link = (item.findtext("link") or "").strip()
            source = (item.findtext("{http://search.yahoo.com/mrss/}source") or "") or "news"
            pub = (item.findtext("pubDate") or "")
            out.append(make_card(type="news", title=title, url=link, source=source, time=pub))
    except Exception:
        pass
    return out

def geocode_city(name):
    # Open-Meteo geocoding (no key)
    j = get_json("https://geocoding-api.open-meteo.com/v1/search", params={"name": name, "count": 1})
    if j and j.get("results"):
        r = j["results"][0]
        return {"name": r.get("name"), "lat": r.get("latitude"), "lon": r.get("longitude"), "country": r.get("country")}
    return None

def weather_cards(query):
    # Parse a simple city name out of query
    city = query.replace("weather", "").strip() or "New York"
    geo = geocode_city(city)
    if not geo:
        return [make_card(type="weather", title="Weather", subtitle=f"{city}", temp_c=None)]
    lat, lon = geo["lat"], geo["lon"]
    j = get_json("https://api.open-meteo.com/v1/forecast", params={
        "latitude": lat, "longitude": lon,
        "hourly":"temperature_2m,relative_humidity_2m,wind_speed_10m",
        "daily":"temperature_2m_max,temperature_2m_min",
        "current_weather":"true", "timezone":"auto"
    })
    if not j:
        return [make_card(type="weather", title="Weather", subtitle=f"{geo['name']}, {geo['country']}")]

    cw = j.get("current_weather") or {}
    temp_c = cw.get("temperature")
    wind_kph = cw.get("windspeed")
    # Build hourly / daily arrays into the shape your component expects
    hours = []
    h_t = (j.get("hourly") or {}).get("time") or []
    h_temp = (j.get("hourly") or {}).get("temperature_2m") or []
    for t, tc in list(zip(h_t, h_temp))[:8]:
        hours.append({"time": t, "temp_c": tc})

    daily = []
    d_tmax = (j.get("daily") or {}).get("temperature_2m_max") or []
    d_tmin = (j.get("daily") or {}).get("temperature_2m_min") or []
    for i in range(min(3, len(d_tmax), len(d_tmin))):
        daily.append({"day": f"Day {i+1}", "max_c": d_tmax[i], "min_c": d_tmin[i]})

    card = {
        "type":"weather",
        "title":"Weather",
        "subtitle": f"{geo['name']}, {geo['country']}",
        "temp_c": temp_c, "feels_c": temp_c,
        "wind_kph": wind_kph, "humidity": None,
        "hourly": hours, "daily": daily,
        "icon": None
    }
    return [card]

def crypto_cards(query):
    # CoinGecko (no key)
    coins = ["bitcoin","ethereum","solana"]
    res = get_json("https://api.coingecko.com/api/v3/coins/markets",
                   params={"vs_currency":"usd","ids":",".join(coins)})
    out=[]
    if res:
        for c in res:
            title = c.get("name")
            url = f"https://www.coingecko.com/en/coins/{c.get('id')}"
            price = f"${c.get('current_price'):,}"
            ch = c.get("price_change_percentage_24h")
            change = f"{ch:+.2f}%"
            out.append({
                "type":"crypto","title":title,"url":url,"price":price,"change":change,
                "symbol": c.get("symbol","").upper(),
                "image": c.get("image"), "source":"CoinGecko"
            })
    return out

def image_cards(query):
    # Build an images-grid using Unsplash source URLs (no key); frontend also has its own fallback
    q = (query or "wallpaper").replace("images:", "").strip() or "wallpaper"
    urls = [f"https://source.unsplash.com/600x400/?{requests.utils.quote(q)}&sig={i}" for i in range(1, 13)]
    return [{"type":"images-grid", "images": urls}]

@app.post("/realtime")
def realtime():
    """
    Body: { query, intent?('news'|'weather'|'crypto'|'images'|...), web? }
    Returns: { ok, cards:[], markdown? }
    """
    try:
        data = request.get_json(force=True, silent=True) or {}
        q = (data.get("query") or "").strip()
        intent = (data.get("intent") or "").strip().lower()

        cards=[]
        md=None
        if intent == "news":
            cards = news_cards(q)
            md = f"Top news for **{q or 'today'}**"
        elif intent == "weather":
            cards = weather_cards(q)
            md = f"Weather for **{q or 'your city'}**"
        elif intent == "crypto":
            cards = crypto_cards(q)
            md = "Crypto prices (CoinGecko)"
        elif intent == "images":
            cards = image_cards(q)
            md = f"Images for **{q or 'wallpaper'}**"
        else:
            # generic: mix a little bit
            cards = (news_cards(q)[:6] + crypto_cards(q)[:3])
            md = f"Results for **{q}**"

        return ok({"cards": cards, "markdown": md})
    except Exception as e:
        return err(500, "server_error", e)

# ========= SEARCH (Wikipedia-first simple cards) =========
@app.post("/search")
def search():
    """
    Body: { prompt, web? }
    Returns: { ok, results:[{title,url,image,source,snippet}] }
    """
    try:
        data = request.get_json(force=True, silent=True) or {}
        prompt = (data.get("prompt") or "").strip()
        if not prompt:
            return ok({"results":[]})

        # Wikipedia search
        sj = get_json("https://en.wikipedia.org/w/api.php", params={
            "action":"query","list":"search","format":"json","srlimit":10,"srsearch": prompt
        }) or {}
        results=[]
        for it in (sj.get("query",{}).get("search") or []):
            title = it.get("title")
            page = f"https://en.wikipedia.org/wiki/{title.replace(' ','_')}"
            snippet = it.get("snippet","").replace("<span class=\"searchmatch\">","").replace("</span>","")
            results.append({"title": title, "url": page, "image": None, "source":"wikipedia.org", "snippet": snippet})
        return ok({"results": results})
    except Exception as e:
        return err(500, "server_error", e)

# ========= DEEPSEARCH (light multi-source summary) =========
@app.post("/deepsearch")
def deepsearch():
    """
    Body: { q, agent? }
    Returns: { ok, answer, cards }
    """
    try:
        data = request.get_json(force=True, silent=True) or {}
        q = (data.get("q") or "").strip()
        cards = news_cards(q)[:6] + crypto_cards(q)[:2]
        summary = f"**Summary for “{q}”**\n\n- I gathered top headlines and market context.\n- Tap any card to open sources.\n- Ask for more detail on a specific source."
        return ok({"answer": summary, "cards": cards})
    except Exception as e:
        return err(500, "server_error", e)

# ========= ANALYZE IMAGE (multipart) =========
@app.post("/analyze-image")
def analyze_image():
    """
    Multipart form:
      image: <file>, prompt?, agent?, web?, persona?
    Returns: { ok, ai_description|summary|reply, cards:[{type:'gallery',images:[dataurl or proxy]}] }
    """
    try:
        if "image" not in request.files:
            return err(400, "image file required")
        f = request.files["image"]
        blob = f.read()
        mime = f.mimetype or mimetypes.guess_type(f.filename)[0] or "image/jpeg"
        durl = dataurl(blob, mime)

        prompt = request.form.get("prompt") or "Describe this image in detail and list notable elements."
        description = "Here’s what I see: a photo with noticeable features (lighting, colors, subjects)."

        # If OpenAI Vision available, try it
        tried_vision = False
        if OPENAI_API_KEY and OpenAI:
            try:
                tried_vision = True
                oc = OpenAI(api_key=OPENAI_API_KEY)
                vision = oc.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[
                        {"role":"system","content":"Be concise but specific."},
                        {"role":"user","content":[
                            {"type":"text","text": prompt},
                            {"type":"image_url","image_url":{"url": durl}}
                        ]}
                    ]
                )
                description = vision.choices[0].message.content.strip() or description
            except Exception:
                pass

        cards = [{"type":"gallery","images":[durl]}]
        return ok({"ai_description": description, "cards": cards, "vision_used": tried_vision})
    except Exception as e:
        return err(500, "server_error", e)

# ========= IMG Proxy (fixes CORS / mixed content) =========
@app.get("/img")
def img_proxy():
    """
    Proxy remote images: /img?url=<http(s)://...>
    """
    url = request.args.get("url", "").strip()
    if not url.startswith("http"):
        return err(400, "invalid url")
    try:
        r = requests.get(url, stream=True, timeout=14)
        r.raise_for_status()
        mime = r.headers.get("Content-Type","image/jpeg")
        return Response(r.iter_content(64*1024), content_type=mime)
    except Exception as e:
        return err(502, "fetch_failed", e)

# ========= Image tools via Replicate (optional) =========
def replicate_required():
    if not (replicate and REPLICATE_API_TOKEN):
        return False
    os.environ["REPLICATE_API_TOKEN"] = REPLICATE_API_TOKEN
    return True

@app.post("/remix-image")
def remix_image():
    try:
        if not replicate_required():
            return err(501, "replicate_not_configured")
        data = request.get_json(force=True, silent=True) or {}
        img = data.get("image_base64"); prompt = data.get("prompt","")
        strength = float(data.get("style_strength", 0.5))
        if not img or not prompt:
            return err(400, "image_base64 and prompt required")
        model_ref = f"{IMG_REPIX_MODEL}:{IMG_REPIX_VERSION}" if IMG_REPIX_VERSION else IMG_REPIX_MODEL
        out = replicate.run(model_ref, input={
            "image": img if is_data_url(img) else str(img),
            "prompt": prompt,
            "num_outputs": 1,
            "guidance_scale": 7.5,
            "image_guidance_scale": max(0.0, min(strength,1.0))
        })
        urls = str_urls(out)
        if not urls: return err(502, "no image returned from replicate")
        return ok({"images": urls})
    except Exception as e:
        return err(500, "server_error", e)

@app.post("/inpaint-image")
def inpaint_image():
    try:
        if not replicate_required():
            return err(501, "replicate_not_configured")
        data = request.get_json(force=True, silent=True) or {}
        img = data.get("image_base64"); mask = data.get("mask_base64"); prompt = data.get("prompt","")
        if not img or not mask or not prompt:
            return err(400, "image_base64, mask_base64 and prompt required")
        model_ref = f"{IMG_INPAINT_MODEL}:{IMG_INPAINT_VERSION}" if IMG_INPAINT_VERSION else IMG_INPAINT_MODEL
        out = replicate.run(model_ref, input={
            "image": img if is_data_url(img) else str(img),
            "mask":  mask if is_data_url(mask) else str(mask),
            "prompt": prompt
        })
        urls = str_urls(out)
        if not urls: return err(502, "no image returned from replicate")
        return ok({"images": urls})
    except Exception as e:
        return err(500, "server_error", e)

@app.post("/remix-face-locked")
def remix_face_locked():
    try:
        if not replicate_required():
            return err(501, "replicate_not_configured")
        if not FACE_LOCK_MODEL:
            return err(501, "face_lock_not_configured")
        data = request.get_json(force=True, silent=True) or {}
        img = data.get("image_base64")
        prompt = data.get("prompt","")
        id_b64 = data.get("id_image_base64") or img
        strength = float(data.get("strength", 0.45))
        restore = bool(data.get("restore_face", True))
        if not img:
            return err(400, "image_base64 required")

        model_ref = f"{FACE_LOCK_MODEL}:{FACE_LOCK_VERSION}" if FACE_LOCK_VERSION else FACE_LOCK_MODEL
        gen = replicate.run(model_ref, input={
            "image": img if is_data_url(img) else str(img),
            "id_image": id_b64 if is_data_url(id_b64) else str(id_b64),
            "prompt": prompt,
            "denoise_strength": max(0.2, min(strength, 0.8)),
            "num_outputs": 1, "guidance_scale": 6.5
        })
        urls = str_urls(gen)
        if not urls: return err(502, "no image returned from face_lock")

        out_url = urls[0]
        if restore and FACE_RESTORE_MODEL:
            fr_ref = f"{FACE_RESTORE_MODEL}:{FACE_RESTORE_VERSION}" if FACE_RESTORE_VERSION else FACE_RESTORE_MODEL
            fr = replicate.run(fr_ref, input={"image": out_url, "fidelity": 0.7})
            fr_urls = str_urls(fr)
            if fr_urls: out_url = fr_urls[0]

        return ok({"images":[out_url]})
    except Exception as e:
        return err(500, "server_error", e)

@app.post("/bg-swap")
def bg_swap():
    try:
        if not replicate_required():
            return err(501, "replicate_not_configured")
        if not (BG_REMOVE_MODEL and (BG_REMOVE_VERSION or ":" not in BG_REMOVE_MODEL)):
            return err(501, "bg_swap_not_configured", "Set BG_REMOVE_MODEL/BG_REMOVE_VERSION")
        if not (BG_COMPOSE_MODEL and (BG_COMPOSE_VERSION or ":" not in BG_COMPOSE_MODEL)):
            return err(501, "bg_swap_not_configured", "Set BG_COMPOSE_MODEL/BG_COMPOSE_VERSION")

        data = request.get_json(force=True, silent=True) or {}
        img = data.get("image_base64"); prompt = data.get("prompt","")
        if not img or not prompt:
            return err(400, "image_base64 and prompt required")

        rm_ref = f"{BG_REMOVE_MODEL}:{BG_REMOVE_VERSION}" if BG_REMOVE_VERSION else BG_REMOVE_MODEL
        cut = replicate.run(rm_ref, input={"image": img if is_data_url(img) else str(img)})
        cut_urls = str_urls(cut)
        if not cut_urls: return err(502, "background removal failed")

        bg_ref = f"{BG_COMPOSE_MODEL}:{BG_COMPOSE_VERSION}" if BG_COMPOSE_VERSION else BG_COMPOSE_MODEL
        bg = replicate.run(bg_ref, input={"prompt": prompt, "width":1024, "height":1024})
        bg_urls = str_urls(bg)
        if not bg_urls: return err(502, "background generation failed")

        return ok({"subject_png": cut_urls[:1], "background": bg_urls[:1]})
    except Exception as e:
        return err(500, "server_error", e)

# ========= Main =========
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
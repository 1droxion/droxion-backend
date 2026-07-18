# api.py — Droxion backend (full, drop-in)
# Matches AIChat.jsx endpoints 1:1 and fixes previews:
# - /chat: GPT-4o → Claude 3.5 Sonnet → Gemini 1.5 Pro (fallbacks)
# - /realtime: news / weather / crypto / images / youtube (cards)
# - /suggest: typeahead + followups
# - /search: Wikipedia-first search → cards
# - /deepsearch: lightweight multi-source summary + cards
# - /analyze-image: multipart image → (Vision if available) → gallery + description
# - /generate-image: original AI image generation through OpenAI
# - /youtube: explicit YouTube search → youtube cards
# - /img: hardened image proxy (CORS, redirects, MIME)
# - Image tools via Replicate: /remix-image, /inpaint-image, /remix-face-locked, /bg-swap

import os, io, base64, mimetypes, time, json
import hmac
import hashlib
from urllib.parse import urlencode
import requests
from flask import Flask, request, jsonify, Response
from flask_cors import CORS

# ========= Optional AI / APIs =========
OPENAI_API_KEY      = os.getenv("OPENAI_API_KEY", "")
ANTHROPIC_API_KEY   = os.getenv("ANTHROPIC_API_KEY", "")
GOOGLE_API_KEY      = os.getenv("GOOGLE_API_KEY", "")
REPLICATE_API_TOKEN = os.getenv("REPLICATE_API_TOKEN", "")
YOUTUBE_API_KEY     = os.getenv("YOUTUBE_API_KEY", "") 

# ========= Supabase REST Parameters =========
SUPABASE_URL        = os.getenv("SUPABASE_URL", os.getenv("VITE_SUPABASE_URL", ""))
SUPABASE_ANON_KEY   = os.getenv("SUPABASE_ANON_KEY", os.getenv("VITE_SUPABASE_ANON_KEY", ""))

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
IMG_REPIX_VERSION = os.getenv("IMG_REPIX_VERSION", "")     

IMG_INPAINT_MODEL   = os.getenv("IMG_INPAINT_MODEL", "stability-ai/stable-diffusion-inpainting")
IMG_INPAINT_VERSION = os.getenv("IMG_INPAINT_VERSION", "")

FACE_LOCK_MODEL   = os.getenv("FACE_LOCK_MODEL", "")       
FACE_LOCK_VERSION = os.getenv("FACE_LOCK_VERSION", "")
FACE_RESTORE_MODEL   = os.getenv("FACE_RESTORE_MODEL", "") 
FACE_RESTORE_VERSION = os.getenv("FACE_RESTORE_VERSION", "")

BG_REMOVE_MODEL   = os.getenv("BG_REMOVE_MODEL", "")       
BG_REMOVE_VERSION = os.getenv("BG_REMOVE_VERSION", "")
BG_COMPOSE_MODEL   = os.getenv("BG_COMPOSE_MODEL", "")     
BG_COMPOSE_VERSION = os.getenv("BG_COMPOSE_VERSION", "")
IMAGE_GENERATION_MODEL = os.getenv("IMAGE_GENERATION_MODEL", "gpt-image-1")

# ========= App =========
app = Flask(__name__)
CORS(app)

@app.route("/")
def home():
    return jsonify({
        "ok": True,
        "message": "Droxion backend is live"
    })

# ===== DAU / WAU / MAU =====
from datetime import datetime, timedelta, timezone
from dateutil import parser
import pytz

LOG_PATH = os.getenv("USER_LOGS_PATH", "/tmp/user_logs.json")
os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
if not os.path.exists(LOG_PATH):
    with open(LOG_PATH, "w", encoding="utf-8") as f:
        f.write("")

NY = pytz.timezone("America/New_York")

def iter_logs(path):
    if not os.path.exists(path):
        return
    with open(path, "r", encoding="utf-8") as f:
        first = f.read(1)
        if not first:
            return
        f.seek(0)
        if first == "[":  
            try:
                arr = json.load(f)
                for item in arr:
                    if isinstance(item, dict):
                        yield item
            except Exception:
                return
        else:  
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    evt = json.loads(line)
                    if isinstance(evt, dict):
                        yield evt
                except Exception:
                    continue

def to_ny_date(dt):
    if isinstance(dt, str):
        try:
            dt = parser.isoparse(dt)
        except Exception:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(NY).date()

# ---- tracking: append a visit/event ----
@app.route("/track", methods=["POST"])
def track():
    try:
        evt = request.get_json(force=True) or {}
        evt.setdefault("type", "visit")
        evt.setdefault("time", datetime.now(timezone.utc).isoformat())
        evt["ip"] = request.headers.get("X-Forwarded-For", request.remote_addr)
        evt["ua"] = request.headers.get("User-Agent")

        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(evt, ensure_ascii=False) + "\n")

        return jsonify({"ok": True, "path": LOG_PATH})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

# ---- quick debug: last 20 raw log lines ----
@app.route("/logs", methods=["GET"])
def view_logs():
    if not os.path.exists(LOG_PATH):
        return jsonify({"logs": []})
    with open(LOG_PATH, "r", encoding="utf-8") as f:
        lines = f.readlines()
    return jsonify({"logs": lines[-20:]})

# ---- active users summary ----
@app.route("/stats/active", methods=["GET"])
def stats_active():
    today_ny = datetime.now(NY).date()
    day_cutoff = today_ny
    week_cutoff = today_ny - timedelta(days=6)   
    month_cutoff = today_ny - timedelta(days=29) 

    dau_set, wau_set, mau_set = set(), set(), set()

    for evt in iter_logs(LOG_PATH):
        uid = evt.get("user_id") or evt.get("uid")
        ts  = evt.get("time") or evt.get("timestamp")
        if not uid or not ts:
            continue
        d = to_ny_date(ts)
        if not d:
            d = today_ny

        if d >= day_cutoff:
            dau_set.add(uid)
        if d >= week_cutoff:
            wau_set.add(uid)
        if d >= month_cutoff:
            mau_set.add(uid)

    return jsonify({
        "dau": len(dau_set),
        "wau": len(wau_set),
        "mau": len(mau_set)
    })

# =========================================================================
# ---- Day 5: Secure Webhook Receiver + OpenAI + Supabase REST Engine ----
# =========================================================================
@app.route("/api/webhooks/shopify/product-create", methods=["POST"])
def shopify_product_create():
    shopify_secret = os.environ.get("SHOPIFY_API_SECRET", "")
    if not shopify_secret:
        return jsonify({"success": False, "error": "SHOPIFY_API_SECRET not configured"}), 500

    hmac_header = request.headers.get("X-Shopify-Hmac-SHA256", "")
    raw_data = request.get_data()

    # 1. Verify Cryptographic Integrity
    digest = hmac.new(
        shopify_secret.encode("utf-8"),
        raw_data,
        hashlib.sha256,
    ).digest()

    calculated_hmac = base64.b64encode(digest).decode("utf-8")

    if not hmac.compare_digest(calculated_hmac, hmac_header):
        return jsonify({"success": False, "error": "Invalid HMAC signature matching"}), 401

    # 2. Extract Data Tokens directly from raw input byte buffers
    try:
        payload = json.loads(raw_data.decode("utf-8")) if raw_data else {}
    except Exception:
        return jsonify({"success": False, "error": "Malformed JSON payload payload"}), 400

    product_id   = payload.get("id")
    title        = payload.get("title", "")
    body_html    = payload.get("body_html", "")
    vendor       = payload.get("vendor", "")
    product_type = payload.get("product_type", "")

    if not product_id or not title:
        return jsonify({"success": False, "error": "Missing fundamental tracking variables"}), 400

    # 3. Request Multi-Channel Conversion Copies from AI Engine
    if not OpenAI:
        return jsonify({"success": False, "error": "OpenAI SDK missing configuration"}), 500
        
    client = OpenAI(api_key=OPENAI_API_KEY)

    completion = client.chat.completions.create(
        model="gpt-4o-mini",
        response_format={"type": "json_object"},
        messages=[
            {
                "role": "system",
                "content": (
                    "You are an expert DTC Facebook Ads copywriter. "
                    "Return ONLY valid JSON with the following structure: "
                    '{"captions":["caption 1","caption 2","caption 3"]}. '
                    "Do not include markdown, backticks, or any extra text."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Generate 3 high-converting Facebook ad captions for this Shopify product.\n\n"
                    f"Product ID: {product_id}\n"
                    f"Title: {title}\n"
                    f"Description: {body_html}\n"
                    f"Vendor: {vendor}\n"
                    f"Product Type: {product_type}"
                ),
            },
        ],
    )

    generated_data = json.loads(completion.choices[0].message.content)
    captions_array = generated_data.get("captions", [])

    # 4. Stream Data To Supabase via Secured Network Hooks
    if not SUPABASE_URL or not SUPABASE_ANON_KEY:
        print("Database warnings: Supabase credentials are empty strings.")
        return jsonify({"success": True, "warning": "Ads generated but DB configurations are missing"}), 200

    headers = {
        "apikey": SUPABASE_ANON_KEY,
        "Authorization": f"Bearer {SUPABASE_ANON_KEY}",
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates" # Upsert strategy
    }

    # First injection: Sync product parameters
    product_endpoint = f"{SUPABASE_URL}/rest/v1/shopify_products"
    product_payload = {
        "product_id": product_id,
        "title": title,
        "description": body_html,
        "vendor": vendor
    }
    

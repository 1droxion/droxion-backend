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
# pip install: openai anthropic google-generativeai replicate
OPENAI_API_KEY      = os.getenv("OPENAI_API_KEY", "")
ANTHROPIC_API_KEY   = os.getenv("ANTHROPIC_API_KEY", "")
GOOGLE_API_KEY      = os.getenv("GOOGLE_API_KEY", "")
REPLICATE_API_TOKEN = os.getenv("REPLICATE_API_TOKEN", "")
YOUTUBE_API_KEY     = os.getenv("YOUTUBE_API_KEY", "")  # <-- add this on Render

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
import json, os
from dateutil import parser
import pytz
from flask import request, jsonify

# Write & read the SAME file; /tmp is always writable on Render
LOG_PATH = os.getenv("USER_LOGS_PATH", "/tmp/user_logs.json")
os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
if not os.path.exists(LOG_PATH):
    with open(LOG_PATH, "w", encoding="utf-8") as f:
        f.write("")

NY = pytz.timezone("America/New_York")

def iter_logs(path):
    """Yield dict events from file that can be JSONL or a JSON array."""
    if not os.path.exists(path):
        return
    with open(path, "r", encoding="utf-8") as f:
        first = f.read(1)
        if not first:
            return
        f.seek(0)
        if first == "[":  # JSON array
            try:
                arr = json.load(f)
                for item in arr:
                    if isinstance(item, dict):
                        yield item
            except Exception:
                return
        else:  # JSONL
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
    """Return date in America/New_York from ISO string or datetime."""
    if isinstance(dt, str):
        try:
            dt = parser.isoparse(dt)
        except Exception:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(NY).date()

def iso_week_start(d):
    return d - timedelta(days=d.weekday())

def month_key(d):
    return f"{d.year:04d}-{d.month:02d}"

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

# ---- (optional) quick debug: last 20 raw log lines ----
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
    week_cutoff = today_ny - timedelta(days=6)   # last 7 days
    month_cutoff = today_ny - timedelta(days=29) # last 30 days

    dau_set, wau_set, mau_set = set(), set(), set()

    for evt in iter_logs(LOG_PATH):
        uid = evt.get("user_id") or evt.get("uid")
        ts  = evt.get("time") or evt.get("timestamp")
        if not uid or not ts:
            continue
        d = to_ny_date(ts)
        if not d:
            # fallback: count as today if parsing failed
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
        return None

# =========================================================================
# ---- Day 3: Secured Shopify Webhook Receiver Endpoint ----
# =========================================================================
@app.route("/api/webhooks/shopify/product-create", methods=["POST"])
def shopify_product_create_webhook():
    try:
        shopify_secret = os.getenv("SHOPIFY_API_SECRET", "")
        if not shopify_secret:
            return jsonify({"ok": False, "error": "Server configuration missing secret"}), 500

        # 1. Capture raw request payload for strict cryptographic signature matching
        raw_data = request.get_data()
        received_hmac = request.headers.get("X-Shopify-Hmac-SHA256", "")

        if not received_hmac:
            return jsonify({"ok": False, "error": "Missing signature verification token"}), 401

        # 2. Compute security hash
        computed_hmac = base64.b64encode(
            hmac.new(shopify_secret.encode("utf-8"), raw_data, hashlib.sha256).digest()
        ).decode("utf-8")

        # 3. Secure matching check to verify legitimacy
        if not hmac.compare_digest(computed_hmac, received_hmac):
            return jsonify({"ok": False, "error": "Invalid webhook cryptographic signature"}), 401

        # 4. Extract target data tokens
        payload = json.loads(raw_data.decode("utf-8"))
        product_info = {
            "id": payload.get("id"),
            "title": payload.get("title", ""),
            "body_html": payload.get("body_html", ""),
            "vendor": payload.get("vendor", ""),
            "product_type": payload.get("product_type", "")
        }

        # Temp log to terminal verification stream

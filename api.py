# api.py — Droxion backend (Chat + Image tools + Metrics/Logging)
# - /chat: GPT-4o → Claude 3.5 Sonnet → Gemini 1.5 Pro (auto-fallbacks)
# - /remix-image, /inpaint-image, /remix-face-locked, /bg-swap (Replicate)
# - NEW: /track-visit (beacon), /metrics (DAU/WAU/MAU, series), /logs (recent)
# - Logging: line-delimited JSON at USER_LOG_PATH (default user_logs.jsonl)

import os, json, uuid
from datetime import datetime, timedelta, timezone
from collections import defaultdict, Counter
from flask import Flask, request, jsonify
from flask_cors import CORS

# === Providers (install listed in requirements.txt) ===
# openai>=1.0.0 anthropic google-generativeai replicate
from openai import OpenAI
import anthropic
import google.generativeai as genai
import replicate

app = Flask(__name__)
CORS(app)

# ===== ENV =====
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "")
# REPLICATE_API_TOKEN must be set for the replicate SDK to work

# ---- Image model refs (override versions via env to avoid 422s) ----
IMG_REPIX_MODEL   = os.getenv("IMG_REPIX_MODEL", "timbrooks/instruct-pix2pix")
IMG_REPIX_VERSION = os.getenv("IMG_REPIX_VERSION", "")  # paste latest hash

IMG_INPAINT_MODEL   = os.getenv("IMG_INPAINT_MODEL", "stability-ai/stable-diffusion-inpainting")
IMG_INPAINT_VERSION = os.getenv("IMG_INPAINT_VERSION", "")

FACE_LOCK_MODEL   = os.getenv("FACE_LOCK_MODEL", "")        # e.g. "tencentarc/instantid"
FACE_LOCK_VERSION = os.getenv("FACE_LOCK_VERSION", "")
FACE_RESTORE_MODEL   = os.getenv("FACE_RESTORE_MODEL", "")  # e.g. "sczhou/codeformer"
FACE_RESTORE_VERSION = os.getenv("FACE_RESTORE_VERSION", "")

BG_REMOVE_MODEL   = os.getenv("BG_REMOVE_MODEL", "")        # e.g. "cjwbw/rembg"
BG_REMOVE_VERSION = os.getenv("BG_REMOVE_VERSION", "")
BG_COMPOSE_MODEL   = os.getenv("BG_COMPOSE_MODEL", "")      # e.g. "black-forest-labs/flux-schnell"
BG_COMPOSE_VERSION = os.getenv("BG_COMPOSE_VERSION", "")

# ====== Metrics / Logging setup ======
USER_LOG_PATH = os.getenv("USER_LOG_PATH", "user_logs.jsonl")  # line-delimited JSON

def utcnow():
    return datetime.now(timezone.utc)

def utc_iso(dt=None):
    return (dt or utcnow()).isoformat()

def _ensure_log_dir():
    d = os.path.dirname(USER_LOG_PATH)
    if d:
        os.makedirs(d, exist_ok=True)

def _append_log(obj: dict):
    _ensure_log_dir()
    with open(USER_LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")

def _iter_logs(since_days=365):
    """Yield parsed log lines (newest window only for speed)."""
    cutoff = utcnow() - timedelta(days=since_days)
    if not os.path.exists(USER_LOG_PATH):
        return
    with open(USER_LOG_PATH, "r", encoding="utf-8") as f:
        for line in f:
            try:
                rec = json.loads(line)
                ts = datetime.fromisoformat(rec.get("ts")).astimezone(timezone.utc)
                if ts >= cutoff:
                    rec["_dt"] = ts
                    yield rec
            except Exception:
                continue

def _client_ip():
    xff = request.headers.get("X-Forwarded-For", "")
    if xff:
        return xff.split(",")[0].strip()
    return request.remote_addr or "0.0.0.0"

def log_event(kind: str, details: dict | None = None):
    rec = {
        "id": str(uuid.uuid4()),
        "ts": utc_iso(),
        "type": kind,                 # 'visit' | 'chat' | 'image' | ...
        "ip": _client_ip(),
        "ua": request.headers.get("User-Agent", ""),
        "path": request.path,
        "details": details or {},
    }
    _append_log(rec)
    return rec

# ===== Clients (lazy) =====
def get_openai():
    return OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None

def get_anthropic():
    return anthropic.Anthropic(api_key=ANTHROPIC_API_KEY) if ANTHROPIC_API_KEY else None

def get_gemini():
    if not GOOGLE_API_KEY:
        return None
    genai.configure(api_key=GOOGLE_API_KEY)
    return genai

# ===== Helpers =====
def err(status, msg, detail=None):
    out = {"ok": False, "error": msg}
    if detail:
        out["detail"] = str(detail)
    return jsonify(out), status

def require(val, name):
    if not val:
        raise ValueError(f"{name} required")

def b64_is_data_url(s: str) -> bool:
    return isinstance(s, str) and s.strip().startswith("data:image/")

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

# ===== Routes =====
@app.get("/health")
def health():
    return jsonify({
        "ok": True,
        "service": "droxion",
        "chat": {
            "openai": bool(OPENAI_API_KEY),
            "anthropic": bool(ANTHROPIC_API_KEY),
            "gemini": bool(GOOGLE_API_KEY),
        }
    })

# ---- Metrics: visit beacon ----
@app.post("/track-visit")
def track_visit():
    payload = request.get_json(silent=True) or {}
    rec = log_event("visit", {
        "page": payload.get("page") or "unknown",
        "ref": payload.get("ref") or "",
        "session": payload.get("session") or "",
    })
    return jsonify({"ok": True, "id": rec["id"]})

# ---- Metrics: DAU/WAU/MAU + series ----
@app.get("/metrics")
def metrics():
    # Params: ?days=30 (default), ?tz_offset_minutes=-300 (America/Chicago ~ CST/CDT)
    days = max(1, int(request.args.get("days", 30)))
    tz_off = int(request.args.get("tz_offset_minutes", "0"))
    tz_delta = timedelta(minutes=tz_off)

    per_day_visits = Counter()         # counts repeated IPs
    per_day_chats  = Counter()
    per_day_ips    = defaultdict(set)  # unique IPs per day

    total_visits = 0
    unique_ips = set()
    now = utcnow()

    for rec in _iter_logs(since_days=max(days, 35)):
        ts_local = rec["_dt"] + tz_delta
        day_key = ts_local.date().isoformat()
        typ = rec.get("type")
        ip = rec.get("ip") or "0.0.0.0"

        if typ == "visit":
            per_day_visits[day_key] += 1
            total_visits += 1
        if typ == "chat":
            per_day_chats[day_key] += 1

        per_day_ips[day_key].add(ip)
        unique_ips.add(ip)

    # Build timeline (oldest -> newest)
    days_list = [(now + tz_delta - timedelta(days=i)).date() for i in range(days-1, -1, -1)]
    x = [d.isoformat() for d in days_list]
    visits = [int(per_day_visits[d]) for d in x]
    chats  = [int(per_day_chats[d])  for d in x]
    uniques = [int(len(per_day_ips[d])) for d in x]

    def uniq_in_window(window_days):
        # unique IPs over the last N days in the displayed window
        if not x:
            return 0
        start_idx = max(0, len(x) - window_days)
        ips = set()
        for d in x[start_idx:]:
            ips |= per_day_ips[d]
        return len(ips)

    dau = uniques[-1] if uniques else 0
    wau = uniq_in_window(min(7, len(x)))
    mau = uniq_in_window(min(30, len(x)))

    return jsonify({
        "ok": True,
        "range_days": days,
        "tz_offset_minutes": tz_off,
        "kpis": {
            "DAU": dau,
            "WAU": wau,
            "MAU": mau,
            "total_visits": int(total_visits),
            "total_unique_ips": int(len(unique_ips)),
        },
        "series": {
            "dates": x,
            "visits": visits,     # repeats included (as requested)
            "unique_ips": uniques,
            "chats": chats
        }
    })

# ---- Metrics: recent logs (raw table) ----
@app.get("/logs")
def logs():
    # ?limit=200 (default 100), newest first
    limit = min(1000, int(request.args.get("limit", 100)))
    rows = []
    for rec in _iter_logs(since_days=365):
        rows.append({
            "ts": rec.get("ts"),
            "type": rec.get("type"),
            "ip": rec.get("ip"),
            "ua": (rec.get("ua", "")[:160]),
            "path": rec.get("path"),
            "details": rec.get("details", {}),
        })
    rows.sort(key=lambda r: r["ts"] or "", reverse=True)
    return jsonify({"ok": True, "rows": rows[:limit]})

# ---- CHAT (GPT-4o → Claude 3.5 Sonnet → Gemini 1.5 Pro) ----
@app.post("/chat")
def chat():
    """
    Body:
      { "messages": [{role, content}, ...] } OR { "prompt": "..." }
    Returns:
      { ok, model, text }
    """
    try:
        data = request.get_json(force=True, silent=True) or {}
        messages_in = data.get("messages")
        prompt = data.get("prompt")

        # METRICS: log chat early (counts even if provider fails)
        try:
            msgs = messages_in or []
            ptxt = prompt or ""
            prompt_len = sum(len(m.get("content","")) for m in msgs) if msgs else len(ptxt)
            log_event("chat", {"prompt_len": int(prompt_len)})
        except Exception:
            pass

        if not messages_in and prompt:
            messages_in = [{"role": "user", "content": prompt}]
        if not messages_in:
            return err(400, "messages or prompt required")

        # 1) GPT-4o
        try:
            oc = get_openai()
            if oc:
                resp = oc.chat.completions.create(
                    model="gpt-4o",
                    messages=messages_in,
                    temperature=0.2
                )
                return jsonify({"ok": True, "model": "gpt-4o", "text": resp.choices[0].message.content})
        except Exception:
            pass

        # 2) Claude 3.5 Sonnet
        try:
            ac = get_anthropic()
            if ac:
                sys_prompt = ""
                convo = []
                for m in messages_in:
                    r, c = m.get("role"), m.get("content", "")
                    if r == "system":
                        sys_prompt = (sys_prompt + "\n" + c).strip()
                    elif r in ("user", "assistant"):
                        convo.append({"role": r, "content": c})
                msg = ac.messages.create(
                    model="claude-3-5-sonnet-20240620",
                    max_tokens=1024,
                    temperature=0.2,
                    system=sys_prompt or None,
                    messages=convo
                )
                out = "".join([b.text for b in msg.content if hasattr(b, "text")])
                return jsonify({"ok": True, "model": "claude-3.5-sonnet", "text": out})
        except Exception:
            pass

        # 3) Gemini 1.5 Pro
        try:
            g = get_gemini()
            if g:
                model = g.GenerativeModel("gemini-1.5-pro")
                stitched = "\n".join([f"{m.get('role','user')}: {m.get('content','')}" for m in messages_in])
                resp = model.generate_content(stitched)
                return jsonify({"ok": True, "model": "gemini-1.5-pro", "text": resp.text or ""})
        except Exception:
            pass

        return err(502, "all providers failed (OpenAI → Anthropic → Gemini)")
    except Exception as e:
        return err(500, "server_error", e)

# ---- IMAGE: REMIX (style remix, keeps structure) ----
@app.post("/remix-image")
def remix_image():
    try:
        data = request.get_json(force=True, silent=True) or {}
        img_b64 = data.get("image_base64")
        prompt = data.get("prompt", "")
        style_strength = float(data.get("style_strength", 0.5))  # 0..1

        require(img_b64, "image_base64")
        require(prompt, "prompt")

        model_ref = f"{IMG_REPIX_MODEL}:{IMG_REPIX_VERSION}" if IMG_REPIX_VERSION else IMG_REPIX_MODEL
        out = replicate.run(model_ref, input={
            "image": img_b64 if b64_is_data_url(img_b64) else str(img_b64),
            "prompt": prompt,
            "num_outputs": 1,
            "guidance_scale": 7.5,
            "image_guidance_scale": max(0.0, min(style_strength, 1.0))
        })
        urls = str_urls(out)
        if not urls:
            return err(502, "no image returned from replicate")
        # Metrics: log image gen
        log_event("image", {"kind": "remix", "count": len(urls)})
        return jsonify({"ok": True, "images": urls})
    except replicate.exceptions.ReplicateError as e:
        return err(422, "replicate_error", e)
    except Exception as e:
        return err(500, "server_error", e)

# ---- IMAGE: INPAINT (mask white=change, black=keep) ----
@app.post("/inpaint-image")
def inpaint_image():
    try:
        data = request.get_json(force=True, silent=True) or {}
        img_b64 = data.get("image_base64")
        mask_b64 = data.get("mask_base64")
        prompt = data.get("prompt", "")

        require(img_b64, "image_base64")
        require(mask_b64, "mask_base64")
        require(prompt, "prompt")

        model_ref = f"{IMG_INPAINT_MODEL}:{IMG_INPAINT_VERSION}" if IMG_INPAINT_VERSION else IMG_INPAINT_MODEL
        out = replicate.run(model_ref, input={
            "image": img_b64 if b64_is_data_url(img_b64) else str(img_b64),
            "mask": mask_b64 if b64_is_data_url(mask_b64) else str(mask_b64),
            "prompt": prompt
        })
        urls = str_urls(out)
        if not urls:
            return err(502, "no image returned from replicate")
        log_event("image", {"kind": "inpaint", "count": len(urls)})
        return jsonify({"ok": True, "images": urls})
    except replicate.exceptions.ReplicateError as e:
        return err(422, "replicate_error", e)
    except Exception as e:
        return err(500, "server_error", e)

# ---- IMAGE: FACE-LOCKED REMIX (same identity) ----
@app.post("/remix-face-locked")
def remix_face_locked():
    """
    JSON:
      image_base64: data:image/*;base64,...
      prompt: "pixar style portrait..." (light prompt recommended)
      id_image_base64?: optional reference; if missing, uses image_base64
      strength?: 0..1 (default 0.45) lower = stronger identity lock
      restore_face?: bool (default True)
    """
    try:
        data = request.get_json(force=True, silent=True) or {}
        img_b64 = data.get("image_base64")
        prompt = data.get("prompt", "")
        id_b64 = data.get("id_image_base64") or img_b64
        strength = float(data.get("strength", 0.45))
        restore_face = bool(data.get("restore_face", True))

        require(img_b64, "image_base64")

        if not FACE_LOCK_MODEL:
            return err(501, "face_lock_not_configured",
                       "Set FACE_LOCK_MODEL / FACE_LOCK_VERSION in env.")
        model_ref = f"{FACE_LOCK_MODEL}:{FACE_LOCK_VERSION}" if FACE_LOCK_VERSION else FACE_LOCK_MODEL

        gen = replicate.run(model_ref, input={
            "image": img_b64 if b64_is_data_url(img_b64) else str(img_b64),
            "id_image": id_b64 if b64_is_data_url(id_b64) else str(id_b64),
            "prompt": prompt,
            "denoise_strength": max(0.2, min(strength, 0.8)),
            "num_outputs": 1,
            "guidance_scale": 6.5
        })
        urls = str_urls(gen)
        if not urls:
            return err(502, "no image returned from face_lock model")
        out_url = urls[0]

        if restore_face and FACE_RESTORE_MODEL:
            fr_ref = f"{FACE_RESTORE_MODEL}:{FACE_RESTORE_VERSION}" if FACE_RESTORE_VERSION else FACE_RESTORE_MODEL
            fr = replicate.run(fr_ref, input={
                "image": out_url,
                "fidelity": 0.7
            })
            fr_urls = str_urls(fr)
            if fr_urls:
                out_url = fr_urls[0]

        log_event("image", {"kind": "face_locked", "count": 1})
        return jsonify({"ok": True, "images": [out_url]})
    except replicate.exceptions.ReplicateError as e:
        return err(422, "replicate_error", e)
    except Exception as e:
        return err(500, "server_error", e)

# ---- IMAGE: BACKGROUND SWAP (subject cutout + generated BG) ----
@app.post("/bg-swap")
def bg_swap():
    """
    JSON:
      image_base64: data:image/*;base64,...
      prompt: "new background description"
    Returns:
      { ok, subject_png: [url], background: [url] }
    Compose client-side by overlaying subject_png on background.
    """
    try:
        data = request.get_json(force=True, silent=True) or {}
        img_b64 = data.get("image_base64")
        prompt = data.get("prompt", "")

        require(img_b64, "image_base64")
        require(prompt, "prompt")

        if not (BG_REMOVE_MODEL and (BG_REMOVE_VERSION or ":" not in BG_REMOVE_MODEL)):
            return err(501, "bg_swap_not_configured",
                       "Set BG_REMOVE_MODEL/BG_REMOVE_VERSION & BG_COMPOSE_MODEL/BG_COMPOSE_VERSION.")
        if not (BG_COMPOSE_MODEL and (BG_COMPOSE_VERSION or ":" not in BG_COMPOSE_MODEL)):
            return err(501, "bg_swap_not_configured",
                       "Set BG_COMPOSE_MODEL/BG_COMPOSE_VERSION.")

        rm_ref = f"{BG_REMOVE_MODEL}:{BG_REMOVE_VERSION}" if BG_REMOVE_VERSION else BG_REMOVE_MODEL
        cut = replicate.run(rm_ref, input={"image": img_b64 if b64_is_data_url(img_b64) else str(img_b64)})
        cut_urls = str_urls(cut)
        require(cut_urls, "background removal output")

        bg_ref = f"{BG_COMPOSE_MODEL}:{BG_COMPOSE_VERSION}" if BG_COMPOSE_VERSION else BG_COMPOSE_MODEL
        bg = replicate.run(bg_ref, input={"prompt": prompt, "width": 1024, "height": 1024})
        bg_urls = str_urls(bg)
        require(bg_urls, "background compose output")

        log_event("image", {"kind": "bg_swap", "count": 1})
        return jsonify({"ok": True, "subject_png": cut_urls[:1], "background": bg_urls[:1]})
    except replicate.exceptions.ReplicateError as e:
        return err(422, "replicate_error", e)
    except Exception as e:
        return err(500, "server_error", e)

# ---- main ----
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
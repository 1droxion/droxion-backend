# api.py — Droxion backend (chat + image tools, prompt→image fixed)
# Changes:
# - ✅ /generate-image (text→image) using correct Replicate slug: black-forest-labs/flux-1-schnell
# - ✅ Extra logging for Replicate model+version and HTTP details
# - Keeps: /remix-image, /inpaint-image, /bg-swap, /chat, /health

import os, io, base64, json
from typing import List, Tuple
from flask import Flask, request, jsonify
from flask_cors import CORS

# Providers (optional)
from openai import OpenAI
import anthropic
import google.generativeai as genai
import replicate
import requests

from PIL import Image, ImageOps, ImageFilter

app = Flask(__name__)
CORS(app)

# ===== ENV =====
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "")
REPLICATE_API_TOKEN = os.getenv("REPLICATE_API_TOKEN", "")

# Modes & knobs
USE_LOCAL_CPU = os.getenv("LOCAL_CPU_IMG", "0") == "1"     # 1 → Diffusers CPU; 0 → Replicate
PRELOAD_CPU   = os.getenv("PRELOAD_CPU", "0") == "1"       # optional: preload CPU models
MAX_IMAGE_SIZE = int(os.getenv("MAX_IMAGE_SIZE", "768"))   # <— 768 is a safe clarity/speed balance
SAFE_STEPS     = int(os.getenv("LOCAL_STEPS", "20"))       # safe 16–24
TORCH_THREADS  = int(os.getenv("TORCH_NUM_THREADS", "4"))
FEATHER_RADIUS = int(os.getenv("FEATHER_RADIUS", "6"))     # bg-swap edge softening (px)
LOG_REPLICATE  = os.getenv("LOG_REPLICATE", "1") == "1"    # print model + payload keys

# Replicate models (edit/inpaint)
IMG_REPIX_MODEL     = os.getenv("IMG_REPIX_MODEL", "timbrooks/instruct-pix2pix")
IMG_REPIX_VERSION   = os.getenv("IMG_REPIX_VERSION", "")
IMG_INPAINT_MODEL   = os.getenv("IMG_INPAINT_MODEL", "stability-ai/stable-diffusion-inpainting")
IMG_INPAINT_VERSION = os.getenv("IMG_INPAINT_VERSION", "")

# ✅ Replicate text-to-image model (fixed slug, all lowercase with dashes)
# Fast:    black-forest-labs/flux-1-schnell
# Quality: black-forest-labs/flux-1-dev
TEXT2IMG_MODEL   = os.getenv("TEXT2IMG_MODEL", "black-forest-labs/flux-1-schnell")
TEXT2IMG_VERSION = os.getenv("TEXT2IMG_VERSION", "")  # optional pin

# Optional background pipeline (Replicate)
BG_REMOVE_MODEL   = os.getenv("BG_REMOVE_MODEL", "")
BG_REMOVE_VERSION = os.getenv("BG_REMOVE_VERSION", "")
BG_COMPOSE_MODEL  = os.getenv("BG_COMPOSE_MODEL", "")
BG_COMPOSE_VERSION= os.getenv("BG_COMPOSE_VERSION", "")

# ===== Clients =====
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

def clamp(v, lo, hi):
    try:
        v = float(v)
    except Exception:
        v = lo
    return max(lo, min(hi, v))

def b64_is_data_url(s: str) -> bool:
    return isinstance(s, str) and s.strip().startswith("data:image/")

def looks_like_url(s: str) -> bool:
    return isinstance(s, str) and s.lower().startswith(("http://", "https://"))

def pil_to_data_url(img: Image.Image, fmt="PNG") -> str:
    buf = io.BytesIO()
    img.save(buf, format=fmt)
    b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
    return f"data:image/{fmt.lower()};base64,{b64}"

def fetch_image_url(url: str) -> Image.Image:
    r = requests.get(url, timeout=20)
    r.raise_for_status()
    return Image.open(io.BytesIO(r.content)).convert("RGBA")

def decode_image_any(s: str) -> Image.Image:
    """Accepts data URL, raw base64, or HTTP/HTTPS URL. Returns RGB PIL.Image."""
    if b64_is_data_url(s):
        header, b64 = s.split(",", 1)
        raw = base64.b64decode(b64)
        return Image.open(io.BytesIO(raw)).convert("RGB")
    if looks_like_url(s):
        r = requests.get(s, timeout=20)
        r.raise_for_status()
        return Image.open(io.BytesIO(r.content)).convert("RGB")
    # raw base64
    try:
        raw = base64.b64decode(s, validate=True)
        return Image.open(io.BytesIO(raw)).convert("RGB")
    except Exception:
        raise ValueError("image_base64 must be a data URL, raw base64, or http(s) URL")

def decode_mask_any(s: str, size: Tuple[int,int]) -> Image.Image:
    m = decode_image_any(s)
    if m.mode != "L":
        m = ImageOps.grayscale(m)
    return m.resize(size, Image.NEAREST)

def str_urls(rep_result) -> List[str]:
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

def map_style_strength_to_img_guidance(style_strength_0_1: float) -> float:
    # UI 0..1 -> 1..6 (safe middle), clamp
    return clamp(1.0 + float(style_strength_0_1) * 5.0, 1.0, 10.0)

def feather_alpha(rgba: Image.Image, radius: int) -> Image.Image:
    """Feather the alpha of an RGBA image to soften edges for compositing."""
    if rgba.mode != "RGBA":
        rgba = rgba.convert("RGBA")
    r, g, b, a = rgba.split()
    a = a.filter(ImageFilter.GaussianBlur(radius=max(1, radius)))
    return Image.merge("RGBA", (r, g, b, a))

def log_replicate_call(model_ref: str, payload: dict):
    if not LOG_REPLICATE:
        return
    keys_only = {k: ("<...>" if isinstance(v, (bytes, bytearray, str)) and len(str(v)) > 120 else v)
                 for k, v in payload.items()}
    print(f"[replicate] model={model_ref} input_keys={list(payload.keys())}")
    print(f"[replicate] input_preview={json.dumps(keys_only)[:800]}")

# ===== Local CPU (Diffusers) optional =====
_cpu_ready = False
if USE_LOCAL_CPU:
    try:
        import torch
        from diffusers import (
            StableDiffusionInstructPix2PixPipeline,
            StableDiffusionInpaintPipeline,
        )
        torch.set_num_threads(TORCH_THREADS)
        P2P_ID = os.getenv("LOCAL_CPU_PIX2PIX_ID", "timbrooks/instruct-pix2pix").strip()
        INP_ID = os.getenv("LOCAL_CPU_INPAINT_ID", "runwayml/stable-diffusion-inpainting").strip()
        _cpu_pix2pix = None
        _cpu_inpaint = None

        def get_cpu_pix2pix():
            global _cpu_pix2pix
            if _cpu_pix2pix is None:
                pipe = StableDiffusionInstructPix2PixPipeline.from_pretrained(P2P_ID, safety_checker=None)
                pipe = pipe.to("cpu"); pipe.enable_attention_slicing()
                _cpu_pix2pix = pipe
            return _cpu_pix2pix

        def get_cpu_inpaint():
            global _cpu_inpaint
            if _cpu_inpaint is None:
                pipe = StableDiffusionInpaintPipeline.from_pretrained(INP_ID, safety_checker=None)
                pipe = pipe.to("cpu"); pipe.enable_attention_slicing()
                _cpu_inpaint = pipe
            return _cpu_inpaint

        if PRELOAD_CPU:
            print("🔄 Preloading CPU pipelines…")
            _ = get_cpu_pix2pix(); _ = get_cpu_inpaint()
            print("✅ CPU models ready.")
        _cpu_ready = True
    except Exception as e:
        print(f"⚠️ CPU init failed, falling back to Replicate if used: {e}")
        USE_LOCAL_CPU = False

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
        },
        "images": {
            "local_cpu": USE_LOCAL_CPU and _cpu_ready,
            "replicate": bool(REPLICATE_API_TOKEN),
            "max_image_size": MAX_IMAGE_SIZE,
            "safe_steps": SAFE_STEPS,
            "text2img_model": TEXT2IMG_MODEL,
            "text2img_version": TEXT2IMG_VERSION or "(latest)"
        }
    })

# ---- CHAT ----
@app.post("/chat")
def chat():
    try:
        data = request.get_json(force=True, silent=True) or {}
        messages_in = data.get("messages")
        prompt = data.get("prompt")
        if not messages_in and prompt:
            messages_in = [{"role": "user", "content": prompt}]
        if not messages_in:
            return err(400, "messages or prompt required")

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

        try:
            ac = get_anthropic()
            if ac:
                sys_prompt = ""
                convo = []
                for m in messages_in:
                    r, c = m.get("role"), m.get("content", "")
                    if r == "system": sys_prompt = (sys_prompt + "\n" + c).strip()
                    elif r in ("user", "assistant"): convo.append({"role": r, "content": c})
                msg = ac.messages.create(
                    model="claude-3-5-sonnet-20240620",
                    max_tokens=1024, temperature=0.2,
                    system=sys_prompt or None, messages=convo
                )
                out = "".join([b.text for b in msg.content if hasattr(b, "text")])
                return jsonify({"ok": True, "model": "claude-3.5-sonnet", "text": out})
        except Exception:
            pass

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

# ---- IMAGE: TEXT2IMG (Prompt → Image) ----
@app.post("/generate-image")
def generate_image():
    """
    JSON body:
      - prompt (str, required)
      - negative_prompt (str, optional)
      - width (int, default 1024)  - clamped 256..1536
      - height (int, default 1024) - clamped 256..1536
      - steps (int, default SAFE_STEPS) - clamped 8..40
      - guidance (float, default 4.0)   - clamped 1..12
      - num_outputs (int, default 1, max 4)
      - seed (int, optional)
    """
    try:
        if not REPLICATE_API_TOKEN:
            return err(500, "replicate_token_missing", "Set REPLICATE_API_TOKEN in environment")

        data = request.get_json(force=True, silent=True) or {}
        prompt = (data.get("prompt") or "").strip()
        require(prompt, "prompt")

        negative = (data.get("negative_prompt") or "").strip()
        width  = int(clamp(data.get("width",  1024), 256, 1536))
        height = int(clamp(data.get("height", 1024), 256, 1536))
        steps  = int(clamp(data.get("steps",  SAFE_STEPS), 8, 40))
        guidance = float(clamp(data.get("guidance", 4.0), 1.0, 12.0))
        num_outputs = int(clamp(data.get("num_outputs", 1), 1, 4))
        seed = data.get("seed", None)

        model_ref = f"{TEXT2IMG_MODEL}:{TEXT2IMG_VERSION}" if TEXT2IMG_VERSION else TEXT2IMG_MODEL

        input_payload = {
            "prompt": prompt,
            "negative_prompt": negative or None,
            "width": width,
            "height": height,
            "num_inference_steps": steps,
            "guidance": guidance,
            "num_outputs": num_outputs,
        }
        if seed is not None:
            input_payload["seed"] = int(seed)

        log_replicate_call(model_ref, input_payload)
        out = replicate.run(model_ref, input=input_payload)
        urls = str_urls(out)
        if not urls:
            return err(502, "no_image_returned", f"model={model_ref}")
        return jsonify({"ok": True, "mode": "text2img", "images": urls})
    except replicate.exceptions.ReplicateError as e:
        # Typical 404/401/422 info
        return err(422, "replicate_error", f"{e}")
    except Exception as e:
        return err(500, "server_error", e)

# ---- IMAGE: REMIX ----
@app.post("/remix-image")
def remix_image():
    try:
        data = request.get_json(force=True, silent=True) or {}
        img_b64 = data.get("image_base64")
        prompt = (data.get("prompt") or "").strip()
        ui_strength = clamp(data.get("style_strength", 0.6), 0.0, 1.0)

        require(img_b64, "image_base64")
        require(prompt, "prompt")

        # Resize to avoid OOM and improve clarity
        img = decode_image_any(img_b64)
        img = ImageOps.contain(img, (MAX_IMAGE_SIZE, MAX_IMAGE_SIZE))

        image_guidance_scale = map_style_strength_to_img_guidance(ui_strength)
        steps = int(clamp(SAFE_STEPS, 8, 28))
        txt_guidance = clamp(7.0, 3.0, 12.0)

        if USE_LOCAL_CPU and _cpu_ready:
            import torch
            pipe = get_cpu_pix2pix()
            with torch.inference_mode():
                out = pipe(
                    prompt=prompt,
                    image=img,
                    guidance_scale=float(txt_guidance),
                    image_guidance_scale=float(image_guidance_scale),
                    num_inference_steps=int(steps),
                ).images[0]
            return jsonify({"ok": True, "images": [pil_to_data_url(out)]})

        model_ref = f"{IMG_REPIX_MODEL}:{IMG_REPIX_VERSION}" if IMG_REPIX_VERSION else IMG_REPIX_MODEL
        input_payload = {
            "image": pil_to_data_url(img),
            "prompt": prompt,
            "num_outputs": 1,
            "guidance_scale": float(txt_guidance),
            "image_guidance_scale": float(image_guidance_scale),
            "num_inference_steps": int(steps)
        }
        log_replicate_call(model_ref, {"image": "<dataurl>", **{k:v for k,v in input_payload.items() if k!="image"}})
        out = replicate.run(model_ref, input=input_payload)
        urls = str_urls(out)
        if not urls:
            return err(502, "no image returned from replicate")
        return jsonify({"ok": True, "images": urls})
    except replicate.exceptions.ReplicateError as e:
        return err(422, "replicate_error", e)
    except Exception as e:
        return err(500, "server_error", e)

# ---- IMAGE: INPAINT ----
@app.post("/inpaint-image")
def inpaint_image():
    try:
        data = request.get_json(force=True, silent=True) or {}
        img_b64 = data.get("image_base64")
        mask_b64 = data.get("mask_base64")
        prompt = (data.get("prompt") or "").strip()

        require(img_b64, "image_base64")
        require(mask_b64, "mask_base64")
        require(prompt, "prompt")

        img = decode_image_any(img_b64)
        img = ImageOps.contain(img, (MAX_IMAGE_SIZE, MAX_IMAGE_SIZE))
        mask = decode_mask_any(mask_b64, img.size)

        steps = int(clamp(SAFE_STEPS, 8, 28))
        txt_guidance = clamp(7.0, 3.0, 12.0)

        if USE_LOCAL_CPU and _cpu_ready:
            import torch
            pipe = get_cpu_inpaint()
            with torch.inference_mode():
                out = pipe(
                    prompt=prompt,
                    image=img,
                    mask_image=mask,
                    guidance_scale=float(txt_guidance),
                    num_inference_steps=int(steps),
                ).images[0]
            return jsonify({"ok": True, "images": [pil_to_data_url(out)]})

        model_ref = f"{IMG_INPAINT_MODEL}:{IMG_INPAINT_VERSION}" if IMG_INPAINT_VERSION else IMG_INPAINT_MODEL
        input_payload = {
            "image": pil_to_data_url(img),
            "mask": pil_to_data_url(mask.convert("RGB")),
            "prompt": prompt
        }
        log_replicate_call(model_ref, {"image":"<dataurl>","mask":"<dataurl>","prompt":prompt})
        out = replicate.run(model_ref, input=input_payload)
        urls = str_urls(out)
        if not urls:
            return err(502, "no image returned from replicate")
        return jsonify({"ok": True, "images": urls})
    except replicate.exceptions.ReplicateError as e:
        return err(422, "replicate_error", e)
    except Exception as e:
        return err(500, "server_error", e)

# ---- IMAGE: BACKGROUND SWAP ----
@app.post("/bg-swap")
def bg_swap():
    try:
        data = request.get_json(force=True, silent=True) or {}
        img_b64 = data.get("image_base64")
        prompt = (data.get("prompt") or "").strip()
        require(img_b64, "image_base64")
        require(prompt, "prompt")

        if not (BG_REMOVE_MODEL and (BG_REMOVE_VERSION or ":" not in BG_REMOVE_MODEL)):
            return err(501, "bg_swap_not_configured",
                       "Set BG_REMOVE_MODEL/BG_REMOVE_VERSION & BG_COMPOSE_MODEL/BG_COMPOSE_VERSION.")
        if not (BG_COMPOSE_MODEL and (BG_COMPOSE_VERSION or ":" not in BG_COMPOSE_MODEL)):
            return err(501, "bg_swap_not_configured",
                       "Set BG_COMPOSE_MODEL/BG_COMPOSE_VERSION.")

        # Downsize for stable removal
        src = decode_image_any(img_b64)
        src = ImageOps.contain(src, (MAX_IMAGE_SIZE, MAX_IMAGE_SIZE))

        # 1) Subject cutout (PNG w/ alpha)
        rm_ref = f"{BG_REMOVE_MODEL}:{BG_REMOVE_VERSION}" if BG_REMOVE_VERSION else BG_REMOVE_MODEL
        log_replicate_call(rm_ref, {"image":"<dataurl>"})
        cut = replicate.run(rm_ref, input={"image": pil_to_data_url(src)})
        cut_urls = str_urls(cut)
        require(cut_urls, "background removal output")
        subject_rgba = fetch_image_url(cut_urls[0])
        subject_rgba = feather_alpha(subject_rgba, FEATHER_RADIUS)

        # 2) Generate background
        bg_ref = f"{BG_COMPOSE_MODEL}:{BG_COMPOSE_VERSION}" if BG_COMPOSE_VERSION else BG_COMPOSE_MODEL
        bg = replicate.run(bg_ref, input={"prompt": prompt, "width": 1024, "height": 1024})
        bg_urls = str_urls(bg)
        require(bg_urls, "background compose output")
        bg_img = fetch_image_url(bg_urls[0]).convert("RGBA")

        # 3) Composite (center)
        canvas = bg_img.copy()
        max_w = int(canvas.width * 0.85)
        max_h = int(canvas.height * 0.85)
        subject_scaled = ImageOps.contain(subject_rgba, (max_w, max_h))
        x = (canvas.width - subject_scaled.width) // 2
        y = (canvas.height - subject_scaled.height) // 2
        canvas.alpha_composite(subject_scaled, (x, y))

        return jsonify({
            "ok": True,
            "subject_png": cut_urls[:1],
            "background": bg_urls[:1],
            "composited": [pil_to_data_url(canvas)]
        })
    except replicate.exceptions.ReplicateError as e:
        return err(422, "replicate_error", e)
    except Exception as e:
        return err(500, "server_error", e)

# ---- main ----
if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    print(f"🚀 Droxion api up on :{port}")
    print(f"→ TEXT2IMG_MODEL={TEXT2IMG_MODEL}  TEXT2IMG_VERSION={TEXT2IMG_VERSION or '(latest)'}")
    app.run(host="0.0.0.0", port=port)
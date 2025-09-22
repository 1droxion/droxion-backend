# api.py — Droxion backend (chat + image tools; CPU-first image gen)
# New: LOCAL_CPU_IMG=1 will use Diffusers on CPU (fast + safe defaults).
# Fallback: if LOCAL_CPU_IMG!=1, we use Replicate exactly as before.

import os, io, base64
from typing import Tuple
from flask import Flask, request, jsonify
from flask_cors import CORS

# Providers (optional)
from openai import OpenAI
import anthropic
import google.generativeai as genai
import replicate

# ---------- Optional CPU pipelines ----------
USE_LOCAL_CPU = os.getenv("LOCAL_CPU_IMG", "0") == "1"
if USE_LOCAL_CPU:
    import torch
    from PIL import Image, ImageOps
    from diffusers import (
        StableDiffusionInstructPix2PixPipeline,
        StableDiffusionInpaintPipeline,
    )
    torch.set_num_threads(int(os.getenv("TORCH_NUM_THREADS", "8")))  # tune per instance

app = Flask(__name__)
CORS(app)

# ===== ENV =====
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "")

# Image models (names kept for Replicate path)
IMG_REPIX_MODEL   = os.getenv("IMG_REPIX_MODEL", "timbrooks/instruct-pix2pix")
IMG_REPIX_VERSION = os.getenv("IMG_REPIX_VERSION", "")
IMG_INPAINT_MODEL   = os.getenv("IMG_INPAINT_MODEL", "stability-ai/stable-diffusion-inpainting")
IMG_INPAINT_VERSION = os.getenv("IMG_INPAINT_VERSION", "")

BG_REMOVE_MODEL   = os.getenv("BG_REMOVE_MODEL", "")
BG_REMOVE_VERSION = os.getenv("BG_REMOVE_VERSION", "")
BG_COMPOSE_MODEL   = os.getenv("BG_COMPOSE_MODEL", "")
BG_COMPOSE_VERSION = os.getenv("BG_COMPOSE_VERSION", "")

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

def b64_is_data_url(s: str) -> bool:
    return isinstance(s, str) and s.strip().startswith("data:image/")

def decode_image_b64(s: str) -> Image.Image:
    """Accepts data URL or plain base64 or URL (which we just pass through to Replicate)."""
    if not b64_is_data_url(s):
        # plain base64?
        try:
            raw = base64.b64decode(s, validate=True)
            return Image.open(io.BytesIO(raw)).convert("RGB")
        except Exception:
            raise ValueError("image_base64 must be a data URL or raw base64 when using LOCAL_CPU_IMG=1")
    header, b64 = s.split(",", 1)
    raw = base64.b64decode(b64)
    return Image.open(io.BytesIO(raw)).convert("RGB")

def decode_mask_b64(s: str) -> Image.Image:
    m = decode_image_b64(s)
    # Expect white=edit, black=keep → convert to 1-channel mask as required by diffusers
    if m.mode != "L":
        m = ImageOps.grayscale(m)
    return m

def str_urls(rep_result):
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

def clamp(v, lo, hi):
    try: v = float(v)
    except Exception: v = lo
    return max(lo, min(hi, v))

def map_style_strength_to_img_guidance(style_strength_0_1: float) -> float:
    return clamp(1.0 + float(style_strength_0_1) * 5.0, 1.0, 20.0)

def pil_to_data_url(img: Image.Image, fmt="PNG") -> str:
    buf = io.BytesIO()
    img.save(buf, format=fmt)
    b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
    return f"data:image/{fmt.lower()};base64,{b64}"

# ===== Lazy-load CPU pipelines =====
_cpu_pix2pix = None
_cpu_inpaint = None

def get_cpu_pix2pix():
    global _cpu_pix2pix
    if _cpu_pix2pix is None:
        # light, CPU-friendly defaults
        model_id = os.getenv("LOCAL_CPU_PIX2PIX_ID", "timbrooks/instruct-pix2pix")
        _cpu_pix2pix = StableDiffusionInstructPix2PixPipeline.from_pretrained(
            model_id, safety_checker=None
        )
        _cpu_pix2pix = _cpu_pix2pix.to("cpu")
        _cpu_pix2pix.enable_attention_slicing()
    return _cpu_pix2pix

def get_cpu_inpaint():
    global _cpu_inpaint
    if _cpu_inpaint is None:
        model_id = os.getenv("LOCAL_CPU_INPAINT_ID", "runwayml/stable-diffusion-inpainting")
        _cpu_inpaint = StableDiffusionInpaintPipeline.from_pretrained(
            model_id, safety_checker=None
        )
        _cpu_inpaint = _cpu_inpaint.to("cpu")
        _cpu_inpaint.enable_attention_slicing()
    return _cpu_inpaint

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
            "local_cpu": USE_LOCAL_CPU,
            "replicate": True
        }
    })

# ---- CHAT (unchanged logic) ----
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

        # OpenAI
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

        # Anthropic
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

        # Gemini
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

# ---- IMAGE: REMIX (style remix, keep structure) ----
@app.post("/remix-image")
def remix_image():
    try:
        data = request.get_json(force=True, silent=True) or {}
        img_b64 = data.get("image_base64")
        prompt = (data.get("prompt") or "").strip()
        ui_strength = clamp(data.get("style_strength", 0.6), 0.0, 1.0)
        require(img_b64, "image_base64")
        require(prompt, "prompt")

        if USE_LOCAL_CPU:
            image = decode_image_b64(img_b64)
            # CPU-friendly: work at 512 and let frontend upscale if needed
            image = ImageOps.contain(image, (512, 512))
            image_guidance_scale = map_style_strength_to_img_guidance(ui_strength)

            pipe = get_cpu_pix2pix()
            with torch.inference_mode():
                out = pipe(
                    prompt=prompt,
                    image=image,
                    guidance_scale=7.5,
                    image_guidance_scale=float(image_guidance_scale),
                    num_inference_steps=int(os.getenv("LOCAL_STEPS", "20")),
                ).images[0]
            return jsonify({"ok": True, "images": [pil_to_data_url(out)]})

        # ---- Replicate fallback (unchanged) ----
        image_guidance_scale = map_style_strength_to_img_guidance(ui_strength)
        model_ref = f"{IMG_REPIX_MODEL}:{IMG_REPIX_VERSION}" if IMG_REPIX_VERSION else IMG_REPIX_MODEL
        input_payload = {
            "image": img_b64 if b64_is_data_url(img_b64) else str(img_b64),
            "prompt": prompt,
            "num_outputs": 1,
            "guidance_scale": 7.5,
            "image_guidance_scale": image_guidance_scale,
            "num_inference_steps": 28
        }
        out = replicate.run(model_ref, input=input_payload)
        urls = str_urls(out)
        if not urls:
            return err(502, "no image returned from replicate")
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
        prompt = (data.get("prompt") or "").strip()
        require(img_b64, "image_base64")
        require(mask_b64, "mask_base64")
        require(prompt, "prompt")

        if USE_LOCAL_CPU:
            image = decode_image_b64(img_b64)
            mask = decode_mask_b64(mask_b64)
            image = ImageOps.contain(image, (512, 512))
            mask = mask.resize(image.size, Image.NEAREST)

            pipe = get_cpu_inpaint()
            with torch.inference_mode():
                out = pipe(
                    prompt=prompt,
                    image=image,
                    mask_image=mask,
                    guidance_scale=7.5,
                    num_inference_steps=int(os.getenv("LOCAL_STEPS", "20")),
                ).images[0]
            return jsonify({"ok": True, "images": [pil_to_data_url(out)]})

        # ---- Replicate fallback (unchanged) ----
        model_ref = f"{IMG_INPAINT_MODEL}:{IMG_INPAINT_VERSION}" if IMG_INPAINT_VERSION else IMG_INPAINT_MODEL
        out = replicate.run(model_ref, input={
            "image": img_b64 if b64_is_data_url(img_b64) else str(img_b64),
            "mask": mask_b64 if b64_is_data_url(mask_b64) else str(mask_b64),
            "prompt": prompt
        })
        urls = str_urls(out)
        if not urls:
            return err(502, "no image returned from replicate")
        return jsonify({"ok": True, "images": urls})

    except replicate.exceptions.ReplicateError as e:
        return err(422, "replicate_error", e)
    except Exception as e:
        return err(500, "server_error", e)

# ---- IMAGE: BACKGROUND SWAP (still via Replicate unless you add a CPU cutout) ----
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

        rm_ref = f"{BG_REMOVE_MODEL}:{BG_REMOVE_VERSION}" if BG_REMOVE_VERSION else BG_REMOVE_MODEL
        cut = replicate.run(rm_ref, input={
            "image": img_b64 if b64_is_data_url(img_b64) else str(img_b64)
        })
        cut_urls = str_urls(cut)
        require(cut_urls, "background removal output")

        bg_ref = f"{BG_COMPOSE_MODEL}:{BG_COMPOSE_VERSION}" if BG_COMPOSE_VERSION else BG_COMPOSE_MODEL
        bg = replicate.run(bg_ref, input={
            "prompt": prompt, "width": 1024, "height": 1024
        })
        bg_urls = str_urls(bg)
        require(bg_urls, "background compose output")

        return jsonify({"ok": True, "subject_png": cut_urls[:1], "background": bg_urls[:1]})
    except replicate.exceptions.ReplicateError as e:
        return err(422, "replicate_error", e)
    except Exception as e:
        return err(500, "server_error", e)

# ---- main ----
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
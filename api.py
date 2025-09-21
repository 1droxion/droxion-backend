# api.py — Droxion backend (Auto mode + identity-safe image tools)
# Endpoints:
#   GET  /health
#   POST /chat
#   POST /image-auto         <-- NEW: picks best mode from your prompt
#   POST /remix-image
#   POST /inpaint-image
#   POST /bg-swap
#
# Notes:
# - Set REPLICATE_API_TOKEN in your environment.
# - OpenAI/Anthropic/Gemini keys are optional; /chat will fall back automatically.
# - All Replicate outputs are coerced to plain URL strings (JSON safe).

import os
import re
from flask import Flask, request, jsonify
from flask_cors import CORS

# Optional chat providers (install via requirements)
from openai import OpenAI
import anthropic
import google.generativeai as genai
import replicate

app = Flask(__name__)
CORS(app)

# ========= ENV =========
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "")

# Replicate models (allow overriding via Render env)
# InstructPix2Pix (style remix, keeps structure/identity fairly well)
IMG_REPIX_MODEL   = os.getenv("IMG_REPIX_MODEL", "timothybrooks/instruct-pix2pix")
IMG_REPIX_VERSION = os.getenv("IMG_REPIX_VERSION", "")  # paste a version hash to pin

# Stable Diffusion Inpainting (mask editing)
IMG_INPAINT_MODEL   = os.getenv("IMG_INPAINT_MODEL", "stability-ai/stable-diffusion-inpainting")
IMG_INPAINT_VERSION = os.getenv("IMG_INPAINT_VERSION", "")

# Background removal + background generator
BG_REMOVE_MODEL   = os.getenv("BG_REMOVE_MODEL", "cjwbw/rembg")
BG_REMOVE_VERSION = os.getenv("BG_REMOVE_VERSION", "")
BG_COMPOSE_MODEL   = os.getenv("BG_COMPOSE_MODEL", "black-forest-labs/flux-schnell")
BG_COMPOSE_VERSION = os.getenv("BG_COMPOSE_VERSION", "")

# ========= Clients =========
def get_openai():
    return OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None

def get_anthropic():
    return anthropic.Anthropic(api_key=ANTHROPIC_API_KEY) if ANTHROPIC_API_KEY else None

def get_gemini():
    if not GOOGLE_API_KEY:
        return None
    genai.configure(api_key=GOOGLE_API_KEY)
    return genai

# ========= Helpers =========
def jerr(status, msg, detail=None):
    out = {"ok": False, "error": msg}
    if detail:
        out["detail"] = str(detail)
    return jsonify(out), status

def require(val, name):
    if not val:
        raise ValueError(f"{name} required")

def is_data_url(s: str) -> bool:
    return isinstance(s, str) and s.strip().startswith("data:image/")

def str_urls(rep_result):
    """Coerce Replicate outputs (FileOutput, list, single) into list[str] URLs."""
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

def model_ref(name, version):
    return f"{name}:{version}" if version else name

# ========= Health =========
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

# ========= Chat (optional) =========
@app.post("/chat")
def chat():
    try:
        data = request.get_json(force=True, silent=True) or {}
        messages_in = data.get("messages")
        prompt = data.get("prompt")

        if not messages_in and prompt:
            messages_in = [{"role": "user", "content": prompt}]
        if not messages_in:
            return jerr(400, "messages or prompt required")

        # 1) OpenAI
        try:
            oc = get_openai()
            if oc:
                r = oc.chat.completions.create(
                    model="gpt-4o",
                    messages=messages_in,
                    temperature=0.2,
                )
                return jsonify({"ok": True, "model": "gpt-4o", "text": r.choices[0].message.content})
        except Exception:
            pass

        # 2) Anthropic
        try:
            ac = get_anthropic()
            if ac:
                sys_prompt, convo = "", []
                for m in messages_in:
                    role = m.get("role", "user")
                    content = m.get("content", "")
                    if role == "system":
                        sys_prompt = (sys_prompt + "\n" + content).strip()
                    elif role in ("user", "assistant"):
                        convo.append({"role": role, "content": content})
                r = ac.messages.create(
                    model="claude-3-5-sonnet-20240620",
                    system=sys_prompt or None,
                    temperature=0.2,
                    max_tokens=1024,
                    messages=convo
                )
                out = "".join([b.text for b in r.content if hasattr(b, "text")])
                return jsonify({"ok": True, "model": "claude-3.5-sonnet", "text": out})
        except Exception:
            pass

        # 3) Gemini
        try:
            g = get_gemini()
            if g:
                stitched = "\n".join([f"{m.get('role','user')}: {m.get('content','')}" for m in messages_in])
                r = g.GenerativeModel("gemini-1.5-pro").generate_content(stitched)
                return jsonify({"ok": True, "model": "gemini-1.5-pro", "text": r.text or ""})
        except Exception:
            pass

        return jerr(502, "all providers failed")
    except Exception as e:
        return jerr(500, "server_error", e)

# ========= Core Image Tools =========
@app.post("/remix-image")
def remix_image():
    """Style remix while preserving structure/identity."""
    try:
        d = request.get_json(force=True, silent=True) or {}
        img = d.get("image_base64")
        prompt = d.get("prompt", "")
        strength = float(d.get("style_strength", 0.5))  # 0..1

        require(img, "image_base64")
        require(prompt, "prompt")

        # Some instruct-pix2pix versions require image_guidance_scale >= 1
        image_guidance = max(1.0, min(7.0, 1.0 + strength * 3.0))  # 1.0..4.0
        guidance = 7.0  # text guidance

        out = replicate.run(
            model_ref(IMG_REPIX_MODEL, IMG_REPIX_VERSION),
            input={
                "image": img if is_data_url(img) else str(img),
                "prompt": prompt,
                "num_outputs": 1,
                "guidance_scale": guidance,
                "image_guidance_scale": image_guidance,
            },
        )
        urls = str_urls(out)
        if not urls:
            return jerr(502, "no image returned from replicate")
        return jsonify({"ok": True, "images": urls})
    except replicate.exceptions.ReplicateError as e:
        return jerr(422, "replicate_error", e)
    except Exception as e:
        return jerr(500, "server_error", e)

@app.post("/inpaint-image")
def inpaint_image():
    """Mask editing (white = change, black = keep)."""
    try:
        d = request.get_json(force=True, silent=True) or {}
        img = d.get("image_base64")
        mask = d.get("mask_base64")
        prompt = d.get("prompt", "")

        require(img, "image_base64")
        require(mask, "mask_base64")
        require(prompt, "prompt")

        out = replicate.run(
            model_ref(IMG_INPAINT_MODEL, IMG_INPAINT_VERSION),
            input={
                "image": img if is_data_url(img) else str(img),
                "mask": mask if is_data_url(mask) else str(mask),
                "prompt": prompt,
            },
        )
        urls = str_urls(out)
        if not urls:
            return jerr(502, "no image returned from replicate")
        return jsonify({"ok": True, "images": urls})
    except replicate.exceptions.ReplicateError as e:
        return jerr(422, "replicate_error", e)
    except Exception as e:
        return jerr(500, "server_error", e)

@app.post("/bg-swap")
def bg_swap():
    """
    Returns:
      { ok, subject_png: [url], background: [url] }
    Compose client-side by overlaying subject_png over background.
    """
    try:
        d = request.get_json(force=True, silent=True) or {}
        img = d.get("image_base64")
        prompt = d.get("prompt", "")

        require(img, "image_base64")
        require(prompt, "prompt")

        cut = replicate.run(
            model_ref(BG_REMOVE_MODEL, BG_REMOVE_VERSION),
            input={"image": img if is_data_url(img) else str(img)}
        )
        cut_urls = str_urls(cut)
        require(cut_urls, "background removal output")

        bg = replicate.run(
            model_ref(BG_COMPOSE_MODEL, BG_COMPOSE_VERSION),
            input={"prompt": prompt, "width": 1024, "height": 1024}
        )
        bg_urls = str_urls(bg)
        require(bg_urls, "background compose output")

        return jsonify({"ok": True, "subject_png": cut_urls[:1], "background": bg_urls[:1]})
    except replicate.exceptions.ReplicateError as e:
        return jerr(422, "replicate_error", e)
    except Exception as e:
        return jerr(500, "server_error", e)

# ========= Auto Mode =========
AUTO_BG_HINTS = re.compile(
    r"\b(bg|background|backdrop|behind|forest|beach|ocean|city|street|sky|mountain|desert|room|studio)\b",
    re.I,
)
AUTO_INPAINT_HINTS = re.compile(
    r"\b(remove|erase|replace|fix|clean|logo|pimple|acne|blemish|stain|text|object|jacket|shirt|change)\b",
    re.I,
)

def decide_mode(prompt: str):
    p = (prompt or "").strip()
    if AUTO_INPAINT_HINTS.search(p):
        return "inpaint"
    if AUTO_BG_HINTS.search(p):
        return "bg"
    return "remix"

@app.post("/image-auto")
def image_auto():
    """
    JSON:
      image_base64: data:image/...  (required)
      prompt: "what you want"       (required)
      mask_base64?: needed only if auto chooses inpaint
      style_strength?: 0..1 (optional; used by remix)
    """
    try:
        d = request.get_json(force=True, silent=True) or {}
        img = d.get("image_base64")
        prompt = d.get("prompt", "")
        mask = d.get("mask_base64")
        style_strength = float(d.get("style_strength", 0.6))

        require(img, "image_base64")
        require(prompt, "prompt")

        mode = decide_mode(prompt)

        if mode == "bg":
            # Reuse bg-swap
            rsp = bg_swap_inner(img, prompt)
            return jsonify({"ok": True, "mode": "bg", **rsp})

        if mode == "inpaint":
            if not mask:
                return jerr(400, "mask_base64 required for inpaint (white = change, black = keep)")
            urls = inpaint_inner(img, mask, prompt)
            return jsonify({"ok": True, "mode": "inpaint", "images": urls})

        # remix
        urls = remix_inner(img, prompt, style_strength)
        return jsonify({"ok": True, "mode": "remix", "images": urls})

    except replicate.exceptions.ReplicateError as e:
        return jerr(422, "replicate_error", e)
    except Exception as e:
        return jerr(500, "server_error", e)

# ====== Inner helpers used by /image-auto (to avoid double JSON plumbing)
def remix_inner(img, prompt, strength):
    image_guidance = max(1.0, min(7.0, 1.0 + strength * 3.0))
    out = replicate.run(
        model_ref(IMG_REPIX_MODEL, IMG_REPIX_VERSION),
        input={
            "image": img if is_data_url(img) else str(img),
            "prompt": prompt,
            "num_outputs": 1,
            "guidance_scale": 7.0,
            "image_guidance_scale": image_guidance,
        },
    )
    urls = str_urls(out)
    if not urls:
        raise ValueError("no image returned from replicate")
    return urls

def inpaint_inner(img, mask, prompt):
    out = replicate.run(
        model_ref(IMG_INPAINT_MODEL, IMG_INPAINT_VERSION),
        input={
            "image": img if is_data_url(img) else str(img),
            "mask": mask if is_data_url(mask) else str(mask),
            "prompt": prompt,
        },
    )
    urls = str_urls(out)
    if not urls:
        raise ValueError("no image returned from replicate (inpaint)")
    return urls

def bg_swap_inner(img, prompt):
    cut = replicate.run(
        model_ref(BG_REMOVE_MODEL, BG_REMOVE_VERSION),
        input={"image": img if is_data_url(img) else str(img)}
    )
    cut_urls = str_urls(cut)
    if not cut_urls:
        raise ValueError("background removal failed")

    bg = replicate.run(
        model_ref(BG_COMPOSE_MODEL, BG_COMPOSE_VERSION),
        input={"prompt": prompt, "width": 1024, "height": 1024}
    )
    bg_urls = str_urls(bg)
    if not bg_urls:
        raise ValueError("background generation failed")

    return {"subject_png": cut_urls[:1], "background": bg_urls[:1]}

# ========= main =========
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
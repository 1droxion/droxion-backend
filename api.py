# api.py — Droxion backend (ChatGPT-quality chat + image edit routes)
# - Chat: GPT-4o primary, Claude 3.5, then Gemini 1.5 fallback
# - Image: Remix / Inpaint via Replicate (serializes outputs to URLs)
# - BG Swap: optional (no 404; returns 501 unless configured)
# - CORS enabled, helpful JSON errors

import os
import base64
from flask import Flask, request, jsonify
from flask_cors import CORS

# ===== Optional SDKs (install if you want the fallbacks) =====
# requirements (add): openai>=1.0.0 anthropic google-generativeai replicate
from openai import OpenAI
import anthropic
import google.generativeai as genai
import replicate

# ---------- Flask ----------
app = Flask(__name__)
CORS(app)

# ---------- ENV ----------
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "")

# Replicate models (set latest hashes in env to avoid 422)
IMG_REPIX_MODEL   = os.getenv("IMG_REPIX_MODEL", "timbrooks/instruct-pix2pix")
IMG_REPIX_VERSION = os.getenv("IMG_REPIX_VERSION", "")  # paste a valid version hash

IMG_INPAINT_MODEL   = os.getenv("IMG_INPAINT_MODEL", "stability-ai/stable-diffusion-inpainting")
IMG_INPAINT_VERSION = os.getenv("IMG_INPAINT_VERSION", "")  # paste a valid version hash

# Optional (only if you want fully automatic BG swap)
BG_REMOVE_MODEL   = os.getenv("BG_REMOVE_MODEL", "")      # e.g. "cjwbw/rembg" (if available to your account)
BG_REMOVE_VERSION = os.getenv("BG_REMOVE_VERSION", "")    # version hash
BG_COMPOSE_MODEL   = os.getenv("BG_COMPOSE_MODEL", "")    # e.g. "black-forest-labs/flux-schnell"
BG_COMPOSE_VERSION = os.getenv("BG_COMPOSE_VERSION", "")  # version hash

# ---------- Clients (created lazily so missing keys don’t crash app) ----------
def get_openai():
    if not OPENAI_API_KEY:
        return None
    return OpenAI(api_key=OPENAI_API_KEY)

def get_anthropic():
    if not ANTHROPIC_API_KEY:
        return None
    return anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

def get_gemini():
    if not GOOGLE_API_KEY:
        return None
    genai.configure(api_key=GOOGLE_API_KEY)
    return genai

# ---------- Helpers ----------
def err(status, msg, detail=None):
    out = {"ok": False, "error": msg}
    if detail:
        out["detail"] = str(detail)
    return jsonify(out), status

def str_urls(rep_result):
    """
    Replicate may return:
      - list[str URLs]
      - list[FileOutput]
      - single URL / object
    Normalize to List[str].
    """
    if rep_result is None:
        return []
    if isinstance(rep_result, list):
        urls = []
        for x in rep_result:
            try:
                if hasattr(x, "url"):
                    urls.append(str(x.url))
                else:
                    urls.append(str(x))
            except Exception:
                urls.append(str(x))
        return urls
    # single object / URL
    try:
        if hasattr(rep_result, "url"):
            return [str(rep_result.url)]
        return [str(rep_result)]
    except Exception:
        return [repr(rep_result)]

def require(v, name):
    if not v:
        raise ValueError(f"{name} required")

def b64_is_data_url(s: str) -> bool:
    return isinstance(s, str) and s.strip().startswith("data:image/")

# ---------- Routes ----------
@app.get("/health")
def health():
    return jsonify({"ok": True, "service": "droxion", "chat": bool(OPENAI_API_KEY or ANTHROPIC_API_KEY or GOOGLE_API_KEY)})

# ---- CHAT (GPT-4o -> Claude 3.5 -> Gemini 1.5) ----
@app.post("/chat")
def chat():
    """
    Body:
      { "messages": [{role: "user"/"system"/"assistant", "content": "..."}] }
      or { "prompt": "..." } for simple use
    """
    try:
        data = request.get_json(force=True, silent=True) or {}
        messages_in = data.get("messages")
        prompt = data.get("prompt")

        if not messages_in and prompt:
            messages_in = [{"role": "user", "content": prompt}]
        if not messages_in:
            return err(400, "messages or prompt required")

        # 1) GPT-4o
        try:
            oc = get_openai()
            if oc:
                rsp = oc.chat.completions.create(
                    model="gpt-4o",
                    messages=messages_in,
                    temperature=0.2,
                )
                out = rsp.choices[0].message.content
                return jsonify({"ok": True, "model": "gpt-4o", "text": out})
        except Exception as e:
            # fall through to next
            pass

        # 2) Claude 3.5 Sonnet
        try:
            ac = get_anthropic()
            if ac:
                # Convert to Anthropic format
                sys_prompt = ""
                user_turns = []
                for m in messages_in:
                    r, c = m.get("role"), m.get("content", "")
                    if r == "system":
                        sys_prompt = f"{sys_prompt}\n{c}".strip()
                    elif r in ("user", "assistant"):
                        user_turns.append({"role": r, "content": c})

                msg = ac.messages.create(
                    model="claude-3-5-sonnet-20240620",
                    max_tokens=1024,
                    temperature=0.2,
                    system=sys_prompt or None,
                    messages=user_turns,
                )
                out = "".join([b.text for b in msg.content if hasattr(b, "text")])
                return jsonify({"ok": True, "model": "claude-3.5-sonnet", "text": out})
        except Exception as e:
            # fall through to next
            pass

        # 3) Gemini 1.5 Pro
        try:
            g = get_gemini()
            if g:
                model = g.GenerativeModel("gemini-1.5-pro")
                # Concatenate simple chat into one prompt (for MVP)
                stitched = []
                for m in messages_in:
                    stitched.append(f"{m.get('role','user')}: {m.get('content','')}")
                gem_prompt = "\n".join(stitched)
                resp = model.generate_content(gem_prompt)
                out = resp.text or ""
                return jsonify({"ok": True, "model": "gemini-1.5-pro", "text": out})
        except Exception as e:
            pass

        return err(502, "all providers failed (OpenAI → Anthropic → Gemini)")

    except Exception as e:
        return err(500, "server_error", e)

# ---- IMAGE: REMIX (Instruct-Pix2Pix) ----
@app.post("/remix-image")
def remix_image():
    try:
        data = request.get_json(force=True, silent=True) or {}
        img_b64 = data.get("image_base64")
        prompt = data.get("prompt", "")
        style_strength = float(data.get("style_strength", 0.6))

        require(img_b64, "image_base64")
        require(prompt, "prompt")

        model = f"{IMG_REPIX_MODEL}:{IMG_REPIX_VERSION}" if IMG_REPIX_VERSION else IMG_REPIX_MODEL

        out = replicate.run(
            model,
            input={
                "image": img_b64 if b64_is_data_url(img_b64) else str(img_b64),
                "prompt": prompt,
                "num_outputs": 1,
                "guidance_scale": 7.5,
                # 0..1 — higher = stronger style push
                "image_guidance_scale": max(0.0, min(style_strength, 1.0)),
            },
        )
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
        prompt = data.get("prompt", "")

        require(img_b64, "image_base64")
        require(mask_b64, "mask_base64")
        require(prompt, "prompt")

        model = f"{IMG_INPAINT_MODEL}:{IMG_INPAINT_VERSION}" if IMG_INPAINT_VERSION else IMG_INPAINT_MODEL

        out = replicate.run(
            model,
            input={
                "image": img_b64 if b64_is_data_url(img_b64) else str(img_b64),
                "mask": mask_b64 if b64_is_data_url(mask_b64) else str(mask_b64),
                "prompt": prompt,
            },
        )
        urls = str_urls(out)
        if not urls:
            return err(502, "no image returned from replicate")
        return jsonify({"ok": True, "images": urls})

    except replicate.exceptions.ReplicateError as e:
        return err(422, "replicate_error", e)
    except Exception as e:
        return err(500, "server_error", e)

# ---- IMAGE: BACKGROUND SWAP (optional) ----
@app.post("/bg-swap")
def bg_swap():
    """
    MVP behavior:
    - If BG_* env vars are set, try:
        1) remove background -> subject PNG
        2) compose a new background from text prompt (text2img)
       (You will still receive a list of image URLs.)
    - If models are not configured, return 501 but NOT 404.
    """
    try:
        data = request.get_json(force=True, silent=True) or {}
        img_b64 = data.get("image_base64")
        prompt = data.get("prompt", "")

        require(img_b64, "image_base64")
        require(prompt, "prompt")

        if not (BG_REMOVE_MODEL and (BG_REMOVE_VERSION or ":" not in BG_REMOVE_MODEL)):
            return err(501, "bg_swap_not_configured", "set BG_REMOVE_MODEL/BG_REMOVE_VERSION & BG_COMPOSE_MODEL/BG_COMPOSE_VERSION")

        if not (BG_COMPOSE_MODEL and (BG_COMPOSE_VERSION or ":" not in BG_COMPOSE_MODEL)):
            return err(501, "bg_swap_not_configured", "set BG_COMPOSE_MODEL/BG_COMPOSE_VERSION")

        # 1) Remove background
        remove_model = f"{BG_REMOVE_MODEL}:{BG_REMOVE_VERSION}" if BG_REMOVE_VERSION else BG_REMOVE_MODEL
        cut = replicate.run(remove_model, input={"image": img_b64 if b64_is_data_url(img_b64) else str(img_b64)})
        cut_urls = str_urls(cut)
        require(cut_urls, "background removal output")

        # 2) Generate new background (text2img)
        compose_model = f"{BG_COMPOSE_MODEL}:{BG_COMPOSE_VERSION}" if BG_COMPOSE_VERSION else BG_COMPOSE_MODEL
        bg = replicate.run(compose_model, input={"prompt": prompt, "width": 1024, "height": 1024})
        bg_urls = str_urls(bg)
        require(bg_urls, "background compose output")

        # NOTE: For a pure server-side composite you’d need a separate compositor step.
        # Returning both URLs lets the frontend overlay subject PNG onto bg (quick MVP).
        return jsonify({"ok": True, "subject_png": cut_urls[:1], "background": bg_urls[:1]})

    except replicate.exceptions.ReplicateError as e:
        return err(422, "replicate_error", e)
    except Exception as e:
        return err(500, "server_error", e)

# ---------- main ----------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
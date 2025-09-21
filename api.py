# api.py — Droxion backend (Director Mode: prompt → best pipeline)
# Chat (with fallbacks) + Smart Image (/smart-image) + classic routes.
# Replicate outputs normalized to string URLs. CORS enabled.

import os
from flask import Flask, request, jsonify
from flask_cors import CORS

# Providers (install from requirements.txt)
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

# Core edit models
IMG_REPIX_MODEL   = os.getenv("IMG_REPIX_MODEL", "timothybrooks/instruct-pix2pix")
IMG_REPIX_VERSION = os.getenv("IMG_REPIX_VERSION", "")
IMG_INPAINT_MODEL   = os.getenv("IMG_INPAINT_MODEL", "stability-ai/stable-diffusion-inpainting")
IMG_INPAINT_VERSION = os.getenv("IMG_INPAINT_VERSION", "")

# Identity lock (optional but recommended)
FACE_LOCK_MODEL   = os.getenv("FACE_LOCK_MODEL", "")        # e.g. "tencentarc/instantid"
FACE_LOCK_VERSION = os.getenv("FACE_LOCK_VERSION", "")

# Face restore (optional tidy-up)
FACE_RESTORE_MODEL   = os.getenv("FACE_RESTORE_MODEL", "")  # e.g. "sczhou/codeformer"
FACE_RESTORE_VERSION = os.getenv("FACE_RESTORE_VERSION", "")

# Background swap pipeline (optional)
BG_REMOVE_MODEL   = os.getenv("BG_REMOVE_MODEL", "")        # e.g. "cjwbw/rembg"
BG_REMOVE_VERSION = os.getenv("BG_REMOVE_VERSION", "")
BG_COMPOSE_MODEL   = os.getenv("BG_COMPOSE_MODEL", "")      # e.g. "black-forest-labs/flux-schnell"
BG_COMPOSE_VERSION = os.getenv("BG_COMPOSE_VERSION", "")

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
    """Normalize Replicate outputs → List[str] URLs."""
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

# ===== Health =====
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

# ===== CHAT (GPT-4o → Claude 3.5 → Gemini 1.5) =====
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
                sys_prompt, convo = "", []
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

# ---------- SMART PLANNER ----------
def plan_pipeline(prompt: str):
    """Return dict describing best pipeline for this prompt."""
    p = (prompt or "").lower()

    wants_bg = any(w in p for w in [
        "background", "new scene", "replace bg", "beach", "forest", "city", "tokyo",
        "mountain", "desert", "studio backdrop", "sky"
    ])
    wants_inpaint = any(w in p for w in [
        "remove", "erase", "logo", "text", "change color", "add", "replace", "fix", "mask"
    ])
    wants_style = any(w in p for w in ["pixar", "ghibli", "anime", "cyberpunk", "3d", "cartoon", "comic"])
    cinematic = any(w in p for w in ["cinematic", "film", "bokeh", "85mm", "f1.8", "kodak", "arri"])

    if wants_bg:
        intent, reason = "bg_swap", "prompt asks for new scene/background"
    elif wants_inpaint:
        intent, reason = "inpaint", "prompt asks for local edits"
    elif wants_style or cinematic:
        intent = "face_locked" if FACE_LOCK_MODEL else "remix"
        reason = "style change" + (" with identity lock" if intent == "face_locked" else "")
    else:
        intent, reason = "remix", "default remix"

    # strength
    style_strength = 0.55
    if any(x in p for x in ["pixar", "anime", "ghibli", "cyberpunk"]):
        style_strength = 0.65
    if cinematic:
        style_strength = 0.45

    # quality/safety add-ons
    must = [
        "keep face identity",
        "high quality, detailed skin texture, sharp details",
        "negative: extra limbs, distorted face, deformed, blurry, low resolution"
    ]
    final_prompt = prompt or ""
    for t in must:
        if t.lower() not in final_prompt.lower():
            final_prompt += (", " if final_prompt else "") + t

    return {"intent": intent, "reason": reason, "style_strength": style_strength, "prompt": final_prompt}

# ---------- /smart-image ----------
@app.post("/smart-image")
def smart_image():
    """
    Body: { image_base64, prompt, mask_base64? }
    Auto-picks: bg_swap / inpaint / face_locked / remix
    """
    try:
        data = request.get_json(force=True, silent=True) or {}
        img_b64 = data.get("image_base64")
        mask_b64 = data.get("mask_base64")
        user_prompt = data.get("prompt", "").strip()
        require(img_b64, "image_base64")
        require(user_prompt, "prompt")

        plan = plan_pipeline(user_prompt)
        intent = plan["intent"]
        prompt = plan["prompt"]
        strength = plan["style_strength"]

        # Background Swap
        if intent == "bg_swap":
            if not (BG_REMOVE_MODEL and (BG_REMOVE_VERSION or ":" not in BG_REMOVE_MODEL)):
                return err(501, "bg_swap_not_configured", "Set BG_REMOVE_* and BG_COMPOSE_* envs.")
            if not (BG_COMPOSE_MODEL and (BG_COMPOSE_VERSION or ":" not in BG_COMPOSE_MODEL)):
                return err(501, "bg_swap_not_configured", "Set BG_COMPOSE_* envs.")
            rm_ref = f"{BG_REMOVE_MODEL}:{BG_REMOVE_VERSION}" if BG_REMOVE_VERSION else BG_REMOVE_MODEL
            cut = replicate.run(rm_ref, input={"image": img_b64})
            cut_urls = str_urls(cut)
            require(cut_urls, "background removal output")

            bg_ref = f"{BG_COMPOSE_MODEL}:{BG_COMPOSE_VERSION}" if BG_COMPOSE_VERSION else BG_COMPOSE_MODEL
            bg = replicate.run(bg_ref, input={"prompt": prompt, "width": 1024, "height": 1024})
            bg_urls = str_urls(bg)
            require(bg_urls, "background compose output")

            return jsonify({"ok": True, "mode": "bg", "reason": plan["reason"], "subject_png": cut_urls[:1], "background": bg_urls[:1], "images": bg_urls[:1]})

        # Inpaint
        if intent == "inpaint":
            if not mask_b64:
                return err(400, "mask_base64 required for inpaint")
            model_ref = f"{IMG_INPAINT_MODEL}:{IMG_INPAINT_VERSION}" if IMG_INPAINT_VERSION else IMG_INPAINT_MODEL
            out = replicate.run(model_ref, input={"image": img_b64, "mask": mask_b64, "prompt": prompt})
            urls = str_urls(out)
            if not urls: return err(502, "no image returned from inpaint")
            return jsonify({"ok": True, "mode": "inpaint", "reason": plan["reason"], "images": urls})

        # Face-locked remix
        if intent == "face_locked":
            model_ref = f"{FACE_LOCK_MODEL}:{FACE_LOCK_VERSION}" if FACE_LOCK_VERSION else FACE_LOCK_MODEL
            gen = replicate.run(model_ref, input={
                "image": img_b64,
                "id_image": img_b64,
                "prompt": prompt,
                "denoise_strength": max(0.2, min(strength, 0.8)),
                "num_outputs": 1,
                "guidance_scale": 7.5
            })
            urls = str_urls(gen)
            if not urls: return err(502, "no image returned from face_lock model")
            out_url = urls[0]
            if FACE_RESTORE_MODEL:
                fr_ref = f"{FACE_RESTORE_MODEL}:{FACE_RESTORE_VERSION}" if FACE_RESTORE_VERSION else FACE_RESTORE_MODEL
                fr = replicate.run(fr_ref, input={"image": out_url, "fidelity": 0.7})
                fr_urls = str_urls(fr)
                if fr_urls: out_url = fr_urls[0]
            return jsonify({"ok": True, "mode": "face_locked", "reason": plan["reason"], "images": [out_url]})

        # Default Remix (Instruct-Pix2Pix)
        model_ref = f"{IMG_REPIX_MODEL}:{IMG_REPIX_VERSION}" if IMG_REPIX_VERSION else IMG_REPIX_MODEL
        out = replicate.run(model_ref, input={
            "image": img_b64,
            "prompt": prompt,
            "num_outputs": 1,
            "guidance_scale": 8.0,
            "image_guidance_scale": max(0.3, min(strength, 0.75)),
            "num_inference_steps": 30,      # smoother quality
            "scheduler": "K_EULER"          # nicer render curve
        })
        urls = str_urls(out)
        if not urls: return err(502, "no image returned from remix")
        return jsonify({"ok": True, "mode": "remix", "reason": plan["reason"], "images": urls})

    except replicate.exceptions.ReplicateError as e:
        return err(422, "replicate_error", e)
    except Exception as e:
        return err(500, "server_error", e)

# ---------- Classic routes kept for manual use ----------
@app.post("/remix-image")
def remix_image():
    try:
        data = request.get_json(force=True, silent=True) or {}
        img_b64 = data.get("image_base64")
        prompt = data.get("prompt", "")
        style_strength = float(data.get("style_strength", 0.55))
        require(img_b64, "image_base64")
        require(prompt, "prompt")
        model_ref = f"{IMG_REPIX_MODEL}:{IMG_REPIX_VERSION}" if IMG_REPIX_VERSION else IMG_REPIX_MODEL
        out = replicate.run(model_ref, input={
            "image": img_b64,
            "prompt": prompt,
            "num_outputs": 1,
            "guidance_scale": 8.0,
            "image_guidance_scale": max(0.3, min(style_strength, 0.75)),
            "num_inference_steps": 30,
            "scheduler": "K_EULER"
        })
        urls = str_urls(out)
        if not urls: return err(502, "no image returned from replicate")
        return jsonify({"ok": True, "images": urls})
    except replicate.exceptions.ReplicateError as e:
        return err(422, "replicate_error", e)
    except Exception as e:
        return err(500, "server_error", e)

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
        out = replicate.run(model_ref, input={"image": img_b64, "mask": mask_b64, "prompt": prompt})
        urls = str_urls(out)
        if not urls: return err(502, "no image returned from replicate")
        return jsonify({"ok": True, "images": urls})
    except replicate.exceptions.ReplicateError as e:
        return err(422, "replicate_error", e)
    except Exception as e:
        return err(500, "server_error", e)

@app.post("/bg-swap")
def bg_swap():
    try:
        data = request.get_json(force=True, silent=True) or {}
        img_b64 = data.get("image_base64")
        prompt = data.get("prompt", "")
        require(img_b64, "image_base64")
        require(prompt, "prompt")

        if not (BG_REMOVE_MODEL and (BG_REMOVE_VERSION or ":" not in BG_REMOVE_MODEL)):
            return err(501, "bg_swap_not_configured", "Set BG_REMOVE_* and BG_COMPOSE_* envs.")
        if not (BG_COMPOSE_MODEL and (BG_COMPOSE_VERSION or ":" not in BG_COMPOSE_MODEL)):
            return err(501, "bg_swap_not_configured", "Set BG_COMPOSE_* envs.")

        rm_ref = f"{BG_REMOVE_MODEL}:{BG_REMOVE_VERSION}" if BG_REMOVE_VERSION else BG_REMOVE_MODEL
        cut = replicate.run(rm_ref, input={"image": img_b64})
        cut_urls = str_urls(cut)
        require(cut_urls, "background removal output")

        bg_ref = f"{BG_COMPOSE_MODEL}:{BG_COMPOSE_VERSION}" if BG_COMPOSE_VERSION else BG_COMPOSE_MODEL
        bg = replicate.run(bg_ref, input={"prompt": prompt, "width": 1024, "height": 1024})
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
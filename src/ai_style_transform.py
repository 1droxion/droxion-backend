import replicate
import os
from dotenv import load_dotenv
import requests
import sys
from PIL import Image
import io

# Load .env
load_dotenv()
os.environ["REPLICATE_API_TOKEN"] = os.getenv("REPLICATE_API_TOKEN")

# Paths
INPUT_IMAGE_URL = "http://localhost:5000/style_input.png"
OUTPUT_PATH = "public/styled_output.png"

# Style prompts
STYLE_PROMPTS = {
    "Ghibli": "a Ghibli anime-style portrait",
    "Sketch": "a pencil sketch of the face",
    "3D": "3D Pixar-style character",
    "Cartoon": "cartoon face character",
    "Pixel": "pixel art face portrait"
}

def apply_style(style="Ghibli"):
    print("🎨 Style requested:", style)

    if style not in STYLE_PROMPTS:
        print(f"⚠️ Unknown style: {style}, using default Ghibli")
        style = "Ghibli"

    prompt = STYLE_PROMPTS[style]

    try:
        print("🚀 Calling Replicate model...")
        output = replicate.run(
            "tstramer/anime-art-diffusion:db21e45f7b774df4ba0fa8f3eb8edcb64c7206e28df18c53c6eec58c49f3d505",
            input={
                "image": INPUT_IMAGE_URL,
                "prompt": prompt,
                "strength": 0.5,
                "guidance_scale": 7.5
            }
        )

        # ✅ Save output image
        image_url = output[0] if isinstance(output, list) else output
        img = Image.open(io.BytesIO(requests.get(image_url).content))
        img.save(OUTPUT_PATH)
        print("✅ Image saved:", OUTPUT_PATH)

    except Exception as e:
        print("❌ Error during style generation:", e)
        raise

if __name__ == "__main__":
    style = sys.argv[1] if len(sys.argv) > 1 else "Ghibli"
    apply_style(style)

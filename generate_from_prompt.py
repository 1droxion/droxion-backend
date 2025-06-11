import json

# Ask user for a prompt
prompt = input("📝 Enter your reel topic (e.g., Never Give Up, Power of AI): ").strip()

# Auto-fill config based on prompt
config = {
    "topic": prompt,
    "language": "Hindi",
    "voice": "onyx",
    "voiceSpeed": 0.95,
    "clipCount": 10,
    "fontSize": 80,
    "subtitleColor": "white",
    "subtitlePosition": "bottom",
    "musicVolume": "medium",
    "tone": "cinematic",
    "lengthSec": 25,
    "filenameMode": "auto",
    "customFilename": "",
    "manualScript": "no",
    "userScript": "",
    "captionStyle": "word",
    "branding": "yes"
}

# Save to config.json
with open("config.json", "w") as f:
    json.dump(config, f, indent=2)

print(f"✅ Config saved! Topic: {prompt}")
print("▶️ Generating reel...")

# Run your auto_reel script
import subprocess
subprocess.run(["python", "auto_reel_final.py"])

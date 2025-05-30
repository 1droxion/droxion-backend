import os, time, random, requests, gc, datetime, platform, re, json
from openai import OpenAI
from moviepy.editor import (
    AudioFileClip, CompositeAudioClip, CompositeVideoClip,
    ImageClip, VideoFileClip, concatenate_videoclips, vfx
)
from PIL import Image, ImageDraw, ImageFont
import numpy as np
from dotenv import load_dotenv

# === Load environment variables ===
load_dotenv()
openai_api_key = os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key=openai_api_key)

# === Load config from UI ===
with open("config.json", "r") as f:
    config = json.load(f)

topic = config.get("topic", "Success")
language = config.get("language", "Hindi")
voice_choice = config.get("voice", "onyx")
voice_speed = float(config.get("voiceSpeed", 0.95))
clip_count = int(config.get("clipCount", 10))
font_size = int(config.get("fontSize", 80))
subtitle_color = config.get("subtitleColor", "white")
subtitle_position = config.get("subtitlePosition", "bottom").lower()
volume_raw = config.get("musicVolume", "medium").lower()

music_volume = 0.25
if "low" in volume_raw:
    music_volume = 0.15
elif "high" in volume_raw:
    music_volume = 0.4

tone = config.get("tone", "cinematic")
length_sec = int(config.get("lengthSec", 25))
filename_mode = config.get("filenameMode", "auto")
custom_filename = config.get("customFilename", "")
manual_script = config.get("manualScript", "no")
user_script = config.get("userScript", "")
caption_style = config.get("captionStyle", "word")
branding = config.get("branding", "no")

voice_file = "voice.mp3"
background_folder = "pixabay_downloads"
tracks_folder = "pixabay_downloads"
font_path = "NotoSansDevanagari-Regular.ttf"

# === Create Output Filename ===
if filename_mode == "manual" and custom_filename:
    output_video = f"{custom_filename}.mp4"
else:
    now = datetime.datetime.now().strftime("%Y%m%d_%H%M")
    output_video = f"{topic}_{language}_{now}.mp4"

# === Generate Script ===
if manual_script == "yes" and user_script.strip():
    script_text = user_script.strip()
else:
    prompt = f"Write a {length_sec}-second {tone} motivational speech in {language} about '{topic}' for a social media video."
    response = client.chat.completions.create(
        model="gpt-4",
        messages=[{"role": "user", "content": prompt}]
    )
    script_text = response.choices[0].message.content.strip()

# === Generate Voice ===
print("🔊 Generating voice...")
voice_response = client.audio.speech.create(
    model="tts-1-hd", voice=voice_choice, input=script_text,
    response_format="mp3", speed=voice_speed
)
with open(voice_file, "wb") as f:
    f.write(voice_response.content)

voice_audio = AudioFileClip(voice_file)
duration = voice_audio.duration

# === Prepare Background Video ===
video_files = [f for f in os.listdir(background_folder) if f.endswith(".mp4")]
random.shuffle(video_files)
bg_clips = []
for vid in video_files[:clip_count]:
    path = os.path.join(background_folder, vid)
    clip = VideoFileClip(path).resize((1080, 1920)).subclip(0, min(4, VideoFileClip(path).duration))
    bg_clips.append(clip)

merged_bg = concatenate_videoclips(bg_clips, method="compose")
if merged_bg.duration < duration:
    loop_count = int(duration / merged_bg.duration) + 1
    bg_clip = merged_bg.loop(n=loop_count).subclip(0, duration)
else:
    bg_clip = merged_bg.subclip(0, duration)

# === Background Music ===
track_files = [f for f in os.listdir(tracks_folder) if f.endswith(".mp3")]
selected_track = random.choice(track_files)
music_clip = AudioFileClip(os.path.join(tracks_folder, selected_track)).subclip(0, duration).volumex(music_volume).audio_fadein(1).audio_fadeout(1)
final_audio = CompositeAudioClip([music_clip, voice_audio])
bg_clip = bg_clip.set_audio(final_audio)

# === Subtitle Lines ===
if caption_style == "sentence":
    lines = re.split(r'(?<=[.?!])\s+', script_text.strip()) if any(p in script_text for p in ".!?") else [" ".join(script_text.strip().split()[i:i+6]) for i in range(0, len(script_text.split()), 6)]
else:
    lines = script_text.strip().split()

word_duration = duration / len(lines)
caption_clips = []

# === Generate Subtitle Clips with Shadow ===
for i, chunk in enumerate(lines):
    start = i * word_duration
    end = start + word_duration

    img = Image.new("RGBA", (1080, 200), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype(font_path, font_size)
    except:
        font = ImageFont.load_default()

    text_width, text_height = draw.textsize(chunk, font=font)
    text_x = (1080 - text_width) // 2
    text_y = (200 - text_height) // 2

    draw.text((text_x + 2, text_y + 2), chunk, font=font, fill="black")  # Shadow
    draw.text((text_x, text_y), chunk, font=font, fill=subtitle_color)

    np_img = np.array(img)
    txt_clip = ImageClip(np_img).set_position(("center", subtitle_position)).set_start(start).set_duration(word_duration)
    caption_clips.append(txt_clip)

# === Final Composition ===
final_core = CompositeVideoClip([bg_clip] + caption_clips)

video_parts = []
if branding == "yes":
    if os.path.exists("intro.mp4"):
        video_parts.append(VideoFileClip("intro.mp4").resize((1080, 1920)))
    video_parts.append(final_core)
    if os.path.exists("outro.mp4"):
        video_parts.append(VideoFileClip("outro.mp4").resize((1080, 1920)))
    final = concatenate_videoclips(video_parts, method="compose")
else:
    final = final_core

# === Save to Public Folder ===
save_path = os.path.join("C:/Users/16626/Downloads/droxion-ui-final/public", output_video)
final.write_videofile(save_path, fps=24, preset="ultrafast", threads=4)

# === Cleanup ===
final.close()
voice_audio.close()
gc.collect()

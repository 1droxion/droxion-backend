import os, random, requests, time
from gtts import gTTS
import subprocess

OPENAI_API_KEY = "sk-..."  # Add your OpenAI key
PEXELS_API_KEY = "563492ad6f91700001000001..."  # Add your Pexels key

# CONFIG
LANGUAGE = "hi"  # "hi" for Hindi, "en" for English
VOICE_TYPE = "male"  # User can select
USE_SUBTITLES = True

# Folders
background_folder = "background_videos"
music_folder = "background_music"
font_path = "fonts/NotoSansDevanagari-Regular.ttf"
output_video = "final_video.mp4"

os.makedirs(background_folder, exist_ok=True)
os.makedirs(music_folder, exist_ok=True)

# 1. Generate script using GPT
def generate_script():
    headers = {"Authorization": f"Bearer {OPENAI_API_KEY}"}
    payload = {
        "model": "gpt-4",
        "messages": [
            {"role": "system", "content": "You are a Hindi motivational scriptwriter."},
            {"role": "user", "content": "Give a 30-second Hindi motivational script."}
        ]
    }
    res = requests.post("https://api.openai.com/v1/chat/completions", json=payload, headers=headers)
    return res.json()["choices"][0]["message"]["content"]

# 2. Generate voice using gTTS fallback
def generate_voice(text, lang=LANGUAGE):
    tts = gTTS(text, lang=lang)
    tts.save("voice.mp3")

# 3. Download 5 background videos from Pexels
def download_videos():
    headers = {"Authorization": PEXELS_API_KEY}
    for i in range(5):
        res = requests.get("https://api.pexels.com/videos/search?query=nature&per_page=15", headers=headers)
        videos = res.json()["videos"]
        choice = random.choice(videos)
        url = choice["video_files"][0]["link"]
        filename = f"{background_folder}/bg{i+1}.mp4"
        with open(filename, "wb") as f:
            f.write(requests.get(url).content)

# 4. Merge all videos using FFmpeg
def merge_videos():
    input_list = "inputs.txt"
    with open(input_list, "w") as f:
        for i in range(5):
            f.write(f"file '{background_folder}/bg{i+1}.mp4'\n")
    subprocess.call(f"ffmpeg -f concat -safe 0 -i {input_list} -c copy merged.mp4", shell=True)

# 5. Download random music
def download_music():
    # Example royalty-free track (or use your own)
    music_url = "https://files.freemusicarchive.org/storage-freemusicarchive-org/music/no_curator/Scott_Holmes_Music/Motivational/Scott_Holmes_Music_-_Inspiring_Corporate.mp3"
    music_path = f"{music_folder}/bg_music.mp3"
    with open(music_path, "wb") as f:
        f.write(requests.get(music_url).content)
    return music_path

# 6. Generate subtitles file
def generate_subtitles(text):
    with open("subs.srt", "w", encoding="utf-8") as f:
        lines = text.split(". ")
        for idx, line in enumerate(lines, 1):
            start = f"00:00:{idx*5 - 5:02},000"
            end = f"00:00:{idx*5:02},000"
            f.write(f"{idx}\n{start} --> {end}\n{line.strip()}\n\n")

# 7. Final video render with FFmpeg
def create_final_video():
    subtitle_cmd = "-vf subtitles=subs.srt:force_style='FontName=NotoSansDevanagari-Regular,FontSize=24'" if USE_SUBTITLES else ""
    cmd = f"""
    ffmpeg -i merged.mp4 -i voice.mp3 -i {music_folder}/bg_music.mp3 -filter_complex \
    "[1]adelay=1000|1000[a]; [2]volume=0.2[b]; [a][b]amix=inputs=2[mix]" \
    -map 0:v -map "[mix]" {subtitle_cmd} -shortest -y {output_video}
    """
    subprocess.call(cmd, shell=True)

# MAIN
if __name__ == "__main__":
    print("📝 Generating script...")
    script_text = generate_script()

    print("🗣️ Generating voice...")
    generate_voice(script_text)

    print("📥 Downloading background videos...")
    download_videos()

    print("🎞️ Merging background videos...")
    merge_videos()

    print("🎵 Downloading music...")
    download_music()

    if USE_SUBTITLES:
        print("📝 Creating subtitles...")
        generate_subtitles(script_text)

    print("🎬 Final rendering...")
    create_final_video()
    print("✅ Final video ready:", output_video)

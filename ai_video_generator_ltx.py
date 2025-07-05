import os, time, requests, json, uuid
from openai import OpenAI
from moviepy.editor import (
    AudioFileClip, CompositeAudioClip, CompositeVideoClip,
    VideoFileClip, concatenate_videoclips
)
from dotenv import load_dotenv

load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def generate_ltx_scenes(prompt):
    system_msg = "You are a cinematic AI scene planner. Given a video idea, break it into 3-5 short, visual scenes in JSON format with brief descriptions."
    res = client.chat.completions.create(
        model="gpt-4",
        messages=[
            {"role": "system", "content": system_msg},
            {"role": "user", "content": f"Break this prompt into scenes: {prompt}"}
        ]
    )
    scenes = json.loads(res.choices[0].message.content)
    return scenes

def download_background_clips(scenes, save_dir="backgrounds"):
    os.makedirs(save_dir, exist_ok=True)
    for i, scene in enumerate(scenes):
        topic = scene["description"]
        print(f"🔍 Downloading background for Scene {i+1}: {topic}")
        response = requests.get(
            f"https://pixabay.com/api/videos/",
            params={
                "key": os.getenv("PIXABAY_API_KEY"),
                "q": topic,
                "orientation": "vertical"
            }
        )
        data = response.json()
        if data["hits"]:
            video_url = data["hits"][0]["videos"]["medium"]["url"]
            with open(f"{save_dir}/scene_{i+1}.mp4", "wb") as f:
                f.write(requests.get(video_url).content)
        else:
            print(f"⚠️ No video found for: {topic}")

def generate_voice_script(scene_desc):
    prompt = f"Write a short cinematic narration (1-2 lines) for this scene: '{scene_desc}'"
    res = client.chat.completions.create(
        model="gpt-4",
        messages=[{"role": "user", "content": prompt}]
    )
    return res.choices[0].message.content.strip()

def generate_voice(text, output_file):
    speech = client.audio.speech.create(
        model="tts-1", voice="onyx", input=text,
        response_format="mp3"
    )
    with open(output_file, "wb") as f:
        f.write(speech.content)

def generate_video_from_prompt(prompt):
    scenes = generate_ltx_scenes(prompt)
    download_background_clips(scenes)

    clips = []
    for i, scene in enumerate(scenes):
        desc = scene["description"]
        print(f"🎤 Generating voice for Scene {i+1}...")
        voice_text = generate_voice_script(desc)
        voice_file = f"voice_{i}.mp3"
        generate_voice(voice_text, voice_file)

        print(f"🎞️ Editing Scene {i+1}...")
        voice_audio = AudioFileClip(voice_file)
        bg_clip = VideoFileClip(f"backgrounds/scene_{i+1}.mp4").subclip(0, min(6, voice_audio.duration)).resize((1080, 1920))
        bg_clip = bg_clip.set_audio(voice_audio)
        clips.append(bg_clip)

    final = concatenate_videoclips(clips, method="compose")
    output_name = f"{uuid.uuid4().hex}.mp4"
    output_path = os.path.join("static/generated", output_name)
    os.makedirs("static/generated", exist_ok=True)
    print("💾 Saving final video...")
    final.write_videofile(output_path, fps=24, preset="ultrafast")
    return output_name

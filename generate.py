import sys
import os
import torch
from diffusers import DiffusionPipeline
from PIL import Image
import moviepy.editor as mpy

def save_video(frames, out_path="output/video.mp4", fps=8):
    os.makedirs("output", exist_ok=True)
    clip = mpy.ImageSequenceClip(frames, fps=fps)
    clip.write_videofile(out_path, codec="libx264")

def generate_frames(prompt):
    pipe = DiffusionPipeline.from_pretrained("CompVis/stable-diffusion-v1-4", torch_dtype=torch.float32)
    pipe = pipe.to("cpu")

    frames = []
    for i in range(8):
        image = pipe(prompt).images[0]
        frame_path = f"output/frame_{i}.png"
        image.save(frame_path)
        frames.append(frame_path)
    return frames

if __name__ == "__main__":
    prompt = " ".join(sys.argv[1:])
    frames = generate_frames(prompt)
    save_video(frames)

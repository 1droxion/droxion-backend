import os
import random
import requests

PEXELS_API_KEY = "ANcj7aGX0gxLbGfxOaNUkuw99pnMv8t6Lc2cgXOedD8LnUEYRkH3Pdwz"
HEADERS = {
    "Authorization": PEXELS_API_KEY
}

def download_random_video(query="nature", output_folder="pixabay_downloads"):
    os.makedirs(output_folder, exist_ok=True)
    page = random.randint(1, 10)
    url = f"https://api.pexels.com/videos/search?query={query}&per_page=10&page={page}"

    response = requests.get(url, headers=HEADERS)
    data = response.json()

    if not data.get("videos"):
        raise Exception("❌ No videos found from Pexels API.")

    video = random.choice(data["videos"])
    video_url = video["video_files"][0]["link"]

    filename = os.path.join(output_folder, "background.mp4")
    with open(filename, "wb") as f:
        f.write(requests.get(video_url).content)

    print("✅ Background video downloaded.")
    return filename

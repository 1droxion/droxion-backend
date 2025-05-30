import os
import random
import requests
from bs4 import BeautifulSoup

BASE_URL = "https://freepd.com/music/"
OUTPUT_FOLDER = "pixabay_downloads"

def download_random_music_freepd():
    os.makedirs(OUTPUT_FOLDER, exist_ok=True)

    response = requests.get(BASE_URL)
    soup = BeautifulSoup(response.text, "html.parser")

    links = soup.find_all("a", href=True)
    mp3_links = [link['href'] for link in links if link['href'].endswith(".mp3")]

    if not mp3_links:
        raise Exception("❌ No MP3 links found on FreePD.")

    chosen = random.choice(mp3_links)
    download_url = BASE_URL + chosen
    output_path = os.path.join(OUTPUT_FOLDER, f"music_{random.randint(1000,9999)}.mp3")

    with open(output_path, "wb") as f:
        f.write(requests.get(download_url).content)

    print(f"✅ Music downloaded: {output_path}")
    return output_path

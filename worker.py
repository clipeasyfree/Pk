import os
import sys
import glob
import json
import subprocess

print("[*] Initializing Studio-Grade Master Slicer (Maximum Quality)...")

# 1. Setup Cookies
cookies_path = None
cookies_env = os.environ.get('COOKIES_DATA', '').strip()
if cookies_env and len(cookies_env) > 20:
    cookies_path = "temp/youtube_cookies.txt"
    os.makedirs('temp', exist_ok=True)
    sanitized = []
    for line in cookies_env.splitlines():
        l = line.strip()
        if not l or l.startswith("#"):
            sanitized.append(line)
            continue
        p = line.split("\t")
        if len(p) >= 7:
            p[1] = "TRUE" if p[0].startswith(".") else "FALSE"
            sanitized.append("\t".join(p))
        else:
            sanitized.append(line)
    with open(cookies_path, "w", encoding="utf-8") as f:
        f.write("\n".join(sanitized) + "\n")

# 2. Parse Payload
payload_env = os.environ.get('JOB_PAYLOAD', '')
payload = json.loads(payload_env) if payload_env and payload_env != 'null' else {}

url = payload.get('url', '')
clips = payload.get('clips', [])

if not url:
    print("[!] Error: No URL provided.")
    sys.exit(1)

if "youtu.be/" in url:
    url = f"https://www.youtube.com/watch?v={url.split('youtu.be/')[1].split('?')[0]}"
elif "watch?v=" in url:
    url = f"https://www.youtube.com/watch?v={url.split('watch?v=')[1].split('&')[0]}"

if not clips:
    clips = [{"id": 1, "start": "00:04", "end": "00:35", "label": "clip_1"}]

os.makedirs('output', exist_ok=True)
os.makedirs('temp', exist_ok=True)
for f in glob.glob("output/*"):
    try: os.remove(f)
    except: pass

# 3. Download Pristine Master Stream (Uncapped Resolution: 4K / 1440p / 1080p60)
master_file = "temp/master_video.mp4"
print("\n[*] Fetching highest available source stream from YouTube...")

cmd_dl = [
    "yt-dlp",
    "--remote-components", "ejs:github",
    "--extractor-args", "youtube:player_client=default,web_embedded",
    "-f", "bestvideo+bestaudio/best",
    "--merge-output-format", "mp4",
    "--no-check-certificates"
]
if cookies_path and os.path.exists(cookies_path):
    cmd_dl.extend(["--cookies", cookies_path])
cmd_dl.extend([url, "-o", master_file])

subprocess.run(cmd_dl, check=True)

if not os.path.exists(master_file):
    matches = glob.glob("temp/master_video.*")
    if matches:
        master_file = matches[0]
    else:
        raise FileNotFoundError("Master video download failed.")

print(f"[✓] Pristine master stream captured: {master_file}")

# 4. Slicing with Visually Lossless Mastering Settings
print(f"\n[*] Slicing {len(clips)} clips at maximum quality (CRF 16, 320k AAC, High Profile)...")

for idx, clip_item in enumerate(clips, start=1):
    cid = clip_item.get('id', idx)
    start = clip_item.get('start', '00:00')
    end = clip_item.get('end', '00:30')
    clean_label = clip_item.get('label', f'clip_{cid}').replace(' ', '_').replace(':', '')

    out_mp4 = f"output/clip_{cid}_{clean_label}.mp4"
    print(f"[{idx}/{len(clips)}] Mastering {start} -> {end}: {out_mp4}")

    cmd_slice = [
        "ffmpeg", "-y",
        "-ss", start,
        "-to", end,
        "-i", master_file,
        "-c:v", "libx264",
        "-preset", "slow",
        "-crf", "16",
        "-profile:v", "high",
        "-level", "4.2",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-b:a", "320k",
        "-movflags", "+faststart",
        out_mp4
    ]
    subprocess.run(cmd_slice, check=True)

print(f"\n[✓] All {len(clips)} studio-master clips encoded successfully!")

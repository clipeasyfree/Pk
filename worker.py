import os
import sys
import glob
import json
import subprocess

print("[*] Initializing Ultra-Fast Video Slicer...")

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

# 3. Process Clips with Ultrafast Transcoding
for clip_item in clips:
    cid = clip_item.get('id', 1)
    start = clip_item.get('start', '00:04')
    end = clip_item.get('end', '00:35')
    clean_label = clip_item.get('label', f'clip_{cid}').replace(' ', '_').replace(':', '')

    dl_output = f"temp/raw_{cid}.%(ext)s"
    out_mp4 = f"output/clip_{cid}_{clean_label}.mp4"

    print(f"\n[*] Slicing Clip #{cid} ({start} -> {end})...")

    cmd_dl = [
        "yt-dlp",
        "--remote-components", "ejs:github",
        "--extractor-args", "youtube:player_client=default,web_embedded",
        "--download-sections", f"*{start}-{end}",
        "-f", "bv*[vcodec^=avc1][height<=1080]+ba[acodec^=mp4a]/bv*[height<=1080]+ba/b[height<=1080]/best",
        "--merge-output-format", "mp4",
        "--force-keyframes-at-cuts",
        "--no-check-certificates"
    ]
    if cookies_path and os.path.exists(cookies_path):
        cmd_dl.extend(["--cookies", cookies_path])
    cmd_dl.extend([url, "-o", dl_output])
    subprocess.run(cmd_dl, check=True)

    downloaded = [f for f in glob.glob(f"temp/raw_{cid}.*") if not f.endswith(".part") and not f.endswith(".ytdl")]
    if not downloaded:
        raise FileNotFoundError(f"Could not find download file for clip {cid}")
    source_video = downloaded[0]

    # Ultrafast CapCut H.264 remux with faststart headers
    cmd_render = [
        "ffmpeg", "-y", "-i", source_video,
        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "22",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "160k",
        "-movflags", "+faststart",
        out_mp4
    ]
    subprocess.run(cmd_render, check=True)
    print(f"[✓] Finished: {out_mp4}")

print("\n[*] All clips processed successfully!")

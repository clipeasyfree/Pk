import os
import sys
import glob
import json
import subprocess

print("[*] Initializing Cloud Anti-Bot Direct Slicer...")

# 1. Setup Cookies (if provided in GitHub Secrets)
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
    print("[✓] Custom YouTube session cookies loaded.")
else:
    print("[!] No session cookies found. Relying on Android/iOS mobile client bypass.")

# 2. Parse Payload & Quality Settings
payload_env = os.environ.get('JOB_PAYLOAD', '')
payload = json.loads(payload_env) if payload_env and payload_env != 'null' else {}

url = payload.get('url', '')
clips = payload.get('clips', [])
quality_mode = payload.get('quality', 'balanced').lower()

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
for f in glob.glob("temp/*"):
    try: os.remove(f)
    except: pass

# Configure Quality Settings
if quality_mode == 'fast':
    ytdl_format = "bv*[height<=720]+ba/b[height<=720]/best"
    ffmpeg_crf = "23"
    ffmpeg_preset = "ultrafast"
    audio_br = "128k"
elif quality_mode == 'master':
    ytdl_format = "bv*[height<=1080]+ba/b[height<=1080]/best"
    ffmpeg_crf = "16"
    ffmpeg_preset = "faster"
    audio_br = "320k"
else:  # balanced
    ytdl_format = "bv*[height<=1080]+ba/b[height<=1080]/best"
    ffmpeg_crf = "19"
    ffmpeg_preset = "faster"
    audio_br = "192k"

# 3. Direct Section Download (Android/iOS client bypasses cloud IP bot checks)
for idx, clip_item in enumerate(clips, start=1):
    cid = clip_item.get('id', idx)
    start = clip_item.get('start', '00:00')
    end = clip_item.get('end', '00:30')
    clean_label = clip_item.get('label', f'clip_{cid}').replace(' ', '_').replace(':', '')

    out_mp4 = f"output/clip_{cid}_{clean_label}.mp4"
    temp_target = f"temp/raw_{cid}.%(ext)s"

    print(f"\n[*] [{idx}/{len(clips)}] Extracting {start} -> {end} via mobile client bypass...")

    cmd_dl = [
        "yt-dlp",
        "--remote-components", "ejs:github",
        "--extractor-args", "youtube:player_client=android,ios",
        "--download-sections", f"*{start}-{end}",
        "-f", ytdl_format,
        "--merge-output-format", "mp4",
        "--force-keyframes-at-cuts",
        "--no-check-certificates"
    ]
    if cookies_path and os.path.exists(cookies_path):
        cmd_dl.extend(["--cookies", cookies_path])
    cmd_dl.extend([url, "-o", temp_target])

    subprocess.run(cmd_dl, check=True)

    downloaded = [f for f in glob.glob(f"temp/raw_{cid}.*") if not f.endswith(".part") and not f.endswith(".ytdl")]
    if not downloaded:
        raise FileNotFoundError(f"Download failed for clip {cid}")
    source_file = downloaded[0]

    # Remux to standard CapCut H.264 MP4
    print(f"[*] Remuxing to CapCut MP4 (CRF {ffmpeg_crf})...")
    cmd_remux = [
        "ffmpeg", "-y",
        "-i", source_file,
        "-c:v", "libx264",
        "-preset", ffmpeg_preset,
        "-crf", ffmpeg_crf,
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-b:a", audio_br,
        "-movflags", "+faststart",
        out_mp4
    ]
    subprocess.run(cmd_remux, check=True)
    print(f"[✓] Clip {cid} ready: {out_mp4}")

print(f"\n[✓] All {len(clips)} clips extracted successfully!")

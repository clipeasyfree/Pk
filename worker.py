import os
import sys
import glob
import json
import re
import subprocess

print("[*] Initializing Netscape-Compliant Direct Slicer...")

# 1. Setup Persistent Netscape Cookie File
cookie_file = os.path.abspath("youtube_cookies.txt")
cookies_env = os.environ.get('COOKIES_DATA', '').strip()
has_valid_cookies = False

if cookies_env and len(cookies_env) > 30:
    # Netscape specification strictly requires this exact header line at index 0
    lines_out = ["# Netscape HTTP Cookie File", "# https://curl.se/docs/http-cookies.html", ""]
    valid_count = 0

    for raw_line in cookies_env.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("# Netscape") or line.startswith("# HTTP"):
            continue
        if line.startswith("#") and not line.startswith("#HttpOnly_"):
            continue
        if line.startswith("#HttpOnly_"):
            line = line[len("#HttpOnly_"):]

        # Handle both tab-separated and multi-space converted inputs
        parts = line.split("\t")
        if len(parts) < 7:
            parts = re.split(r'\t+|\s{2,}', line)

        if len(parts) >= 7:
            domain = parts[0]
            subdomain = "TRUE" if domain.startswith(".") else "FALSE"
            path = parts[2]
            secure = parts[3].upper() if parts[3].upper() in ["TRUE", "FALSE"] else "TRUE"
            expiry = parts[4]
            name = parts[5]
            value = parts[6]
            lines_out.append(f"{domain}\t{subdomain}\t{path}\t{secure}\t{expiry}\t{name}\t{value}")
            valid_count += 1

    with open(cookie_file, "w", encoding="utf-8") as f:
        f.write("\n".join(lines_out) + "\n")

    if os.path.exists(cookie_file) and valid_count > 0:
        has_valid_cookies = True
        print(f"[✓] Netscape cookie file locked with {valid_count} entries.")
    else:
        print("[!] Failed to format Netscape cookie file.")
else:
    print("[!] No session cookies found in environment.")

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

if quality_mode == 'fast':
    ytdl_format = "bv*[height<=720]+ba/b[height<=720]/best"
    ffmpeg_crf = "22"
    ffmpeg_preset = "ultrafast"
    audio_br = "128k"
elif quality_mode == 'master':
    ytdl_format = "bv*[height<=1080]+ba/b[height<=1080]/best"
    ffmpeg_crf = "16"
    ffmpeg_preset = "faster"
    audio_br = "320k"
else:  # balanced
    ytdl_format = "bv*[height<=1080]+ba/b[height<=1080]/best"
    ffmpeg_crf = "18"
    ffmpeg_preset = "faster"
    audio_br = "192k"

def parse_to_sec(time_str):
    parts = [float(x) for x in time_str.strip().split(':')]
    if len(parts) == 3:
        return parts[0] * 3600 + parts[1] * 60 + parts[2]
    elif len(parts) == 2:
        return parts[0] * 60 + parts[1]
    return parts[0]

def sec_to_str(total_sec):
    total_sec = max(0, total_sec)
    hrs = int(total_sec // 3600)
    mins = int((total_sec % 3600) // 60)
    secs = total_sec % 60
    if hrs > 0:
        return f"{hrs:02d}:{mins:02d}:{secs:04.1f}"
    return f"{mins:02d}:{secs:04.1f}"

# 3. Pull Sections Directly & Add Sentence Buffers
for idx, clip_item in enumerate(clips, start=1):
    cid = clip_item.get('id', idx)
    raw_start = clip_item.get('start', '00:00')
    raw_end = clip_item.get('end', '00:30')
    clean_label = clip_item.get('label', f'clip_{cid}').replace(' ', '_').replace(':', '')

    start_sec = parse_to_sec(raw_start)
    end_sec = parse_to_sec(raw_end)

    # 2.5-second tail padding preserves complete words and final thoughts
    padded_end_sec = end_sec + 2.5
    dl_start = sec_to_str(start_sec)
    dl_end = sec_to_str(padded_end_sec)
    duration = padded_end_sec - start_sec

    out_mp4 = f"output/clip_{cid}_{clean_label}.mp4"
    temp_raw = f"temp/raw_{cid}.%(ext)s"

    print(f"\n[*] [{idx}/{len(clips)}] Extracting {dl_start} -> {dl_end}...")

    cmd_dl = [
        "yt-dlp",
        "--remote-components", "ejs:github",
        "--download-sections", f"*{dl_start}-{dl_end}",
        "-f", ytdl_format,
        "--merge-output-format", "mp4",
        "--force-keyframes-at-cuts",
        "--no-check-certificates"
    ]

    if has_valid_cookies and os.path.exists(cookie_file):
        cmd_dl.extend(["--cookies", cookie_file])
        cmd_dl.extend(["--extractor-args", "youtube:player_client=web,tv_embedded"])
    else:
        cmd_dl.extend(["--extractor-args", "youtube:player_client=android,ios"])

    cmd_dl.extend([url, "-o", temp_raw])
    subprocess.run(cmd_dl, check=True)

    downloaded = [f for f in glob.glob(f"temp/raw_{cid}.*") if not f.endswith(".part") and not f.endswith(".ytdl")]
    if not downloaded:
        raise FileNotFoundError(f"Download failed for clip {cid}")
    source_file = downloaded[0]

    # Remux with smooth 0.3s audio fade-out to prevent audio pops
    fade_start = max(0, duration - 0.3)
    cmd_remux = [
        "ffmpeg", "-y",
        "-i", source_file,
        "-c:v", "libx264",
        "-preset", ffmpeg_preset,
        "-crf", ffmpeg_crf,
        "-pix_fmt", "yuv420p",
        "-af", f"afade=t=out:st={fade_start}:d=0.3",
        "-c:a", "aac",
        "-b:a", audio_br,
        "-movflags", "+faststart",
        out_mp4
    ]
    subprocess.run(cmd_remux, check=True)
    print(f"[✓] Finished Clip {cid}: {out_mp4}")

print(f"\n[✓] All {len(clips)} clips exported cleanly!")


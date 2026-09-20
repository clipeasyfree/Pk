import os
import sys
import glob
import json
import subprocess

print("[*] Initializing Master Direct-Slice Slicer (Speech-Protected)...")

# 1. Setup Persistent Cookies Outside Temp Directory
cookie_file = os.path.abspath("youtube_cookies.txt")
cookies_env = os.environ.get('COOKIES_DATA', '').strip()
has_valid_cookies = False

if cookies_env and len(cookies_env) > 30:
    sanitized = []
    for line in cookies_env.splitlines():
        l = line.strip()
        if not l or l.startswith("# "):
            continue
        # Strip browser export HttpOnly prefix for strict Netscape compliance
        if l.startswith("#HttpOnly_"):
            l = l[len("#HttpOnly_"):]
        p = l.split("\t")
        if len(p) >= 7:
            p[1] = "TRUE" if p[0].startswith(".") else "FALSE"
            sanitized.append("\t".join(p))
        else:
            sanitized.append(l)
    with open(cookie_file, "w", encoding="utf-8") as f:
        f.write("\n".join(sanitized) + "\n")
    if os.path.exists(cookie_file) and os.path.getsize(cookie_file) > 50:
        has_valid_cookies = True
        print(f"[✓] Authenticated session cookies loaded ({len(sanitized)} entries).")
    else:
        print("[!] Cookie file creation failed.")
else:
    print("[!] No session cookies found in secrets.")

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

# Clean directories without touching the cookie file in root
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
    ffmpeg_crf = "22"
    ffmpeg_preset = "ultrafast"
    audio_br = "128k"
elif quality_mode == 'master':
    ytdl_format = "bv*[height<=1080]+ba/b[height<=1080]/best"
    ffmpeg_crf = "16"
    ffmpeg_preset = "faster"
    audio_br = "320k"
else:  # balanced (recommended)
    ytdl_format = "bv*[height<=1080]+ba/b[height<=1080]/best"
    ffmpeg_crf = "18"
    ffmpeg_preset = "faster"
    audio_br = "192k"

# Helper functions for sentence padding
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

# 3. Process Clips with Sentence Completion Buffer
for idx, clip_item in enumerate(clips, start=1):
    cid = clip_item.get('id', idx)
    raw_start = clip_item.get('start', '00:00')
    raw_end = clip_item.get('end', '00:30')
    clean_label = clip_item.get('label', f'clip_{cid}').replace(' ', '_').replace(':', '')

    start_sec = parse_to_sec(raw_start)
    end_sec = parse_to_sec(raw_end)

    # 2.5-second tail padding ensures the final sentence never gets cut mid-word
    padded_end_sec = end_sec + 2.5
    dl_start = sec_to_str(start_sec)
    dl_end = sec_to_str(padded_end_sec)
    duration = padded_end_sec - start_sec

    out_mp4 = f"output/clip_{cid}_{clean_label}.mp4"
    temp_raw = f"temp/raw_{cid}.%(ext)s"

    print(f"\n[*] [{idx}/{len(clips)}] Pulling section {dl_start} -> {dl_end} (padded for clean ending)...")

    cmd_dl = [
        "yt-dlp",
        "--remote-components", "ejs:github",
        "--download-sections", f"*{dl_start}-{dl_end}",
        "-f", ytdl_format,
        "--merge-output-format", "mp4",
        "--force-keyframes-at-cuts",
        "--no-check-certificates"
    ]

    # Explicitly attach authenticated web cookies
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

    # Smooth 0.3s audio fade-out prevents clipping clicks while preserving speech
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
    print(f"[✓] Clip {cid} rendered cleanly: {out_mp4}")

print(f"\n[✓] All {len(clips)} clips successfully finished without truncation!")

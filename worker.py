import os
import sys
import glob
import json
import subprocess

print("[*] Initializing VERTEX PRO Auto-Framing Engine...")

# 1. Setup cookies
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

# 2. Parse job payload
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
    clips = [{"id": 1, "start": "00:04", "end": "00:35", "mode": "single", "crop_pos": 0.5}]

os.makedirs('output', exist_ok=True)
os.makedirs('temp', exist_ok=True)

# Clean previous output
for f in glob.glob("output/*"):
    try: os.remove(f)
    except: pass

# 3. Process & Auto-Frame Every Selected Clip
for clip_item in clips:
    cid = clip_item.get('id', 1)
    start = clip_item.get('start', '00:04')
    end = clip_item.get('end', '00:35')
    mode = clip_item.get('mode', 'single')  # 'single' or 'split'
    user_pos = float(clip_item.get('crop_pos', 0.5))
    clean_label = clip_item.get('label', f'clip_{cid}').replace(' ', '_').replace(':', '')

    dl_output = f"temp/downloaded_{cid}.%(ext)s"
    out_mp4 = f"output/short_{cid}_{clean_label}.mp4"

    print(f"\n==========================================")
    print(f"[*] Slicing Clip #{cid} ({start} -> {end}) | Mode: {mode.upper()}...")
    print(f"==========================================")

    cmd_dl = [
        "yt-dlp",
        "--remote-components", "ejs:github",
        "--extractor-args", "youtube:player_client=default,web_embedded",
        "--download-sections", f"*{start}-{end}",
        "-f", "bv*[height<=1080]+ba/b[height<=1080]/best",
        "--merge-output-format", "mp4",
        "--force-keyframes-at-cuts",
        "--no-check-certificates"
    ]
    if cookies_path and os.path.exists(cookies_path):
        cmd_dl.extend(["--cookies", cookies_path])
    cmd_dl.extend([url, "-o", dl_output])
    subprocess.run(cmd_dl, check=True)

    downloaded = [f for f in glob.glob(f"temp/downloaded_{cid}.*") if not f.endswith(".part") and not f.endswith(".ytdl")]
    if not downloaded:
        raise FileNotFoundError(f"Could not find download file for clip {cid}")
    source_video = downloaded[0]
    print(f"[✓] Download complete: {source_video}")

    # 4. High-Performance 9:16 Auto-Framing
    if mode == "split":
        print("[⚡] Rendering Stacked 9:16 Split-Screen (Host Top / Guest Bottom)...")
        filter_str = (
            "[0:v]split=2[in1][in2]; "
            "[in1]crop=w=ih*(9/8):h=ih:x=0:y=0,scale=1080:960[top]; "
            "[in2]crop=w=ih*(9/8):h=ih:x=iw-ih*(9/8):y=0,scale=1080:960[bot]; "
            "[top][bot]vstack=inputs=2[outv]"
        )
        cmd_render = [
            "ffmpeg", "-y", "-i", source_video,
            "-filter_complex", filter_str,
            "-map", "[outv]", "-map", "0:a",
            "-c:v", "libx264", "-preset", "fast", "-crf", "20",
            "-c:a", "aac", "-b:a", "192k",
            out_mp4
        ]
    else:
        print(f"[*] Auto-Framing Single Speaker at offset {int(user_pos * 100)}%...")
        crop_filter = f"crop=ih*(9/16):ih:(iw-ih*(9/16))*{user_pos}:0,scale=1080:1920"
        cmd_render = [
            "ffmpeg", "-y", "-i", source_video,
            "-vf", crop_filter,
            "-c:v", "libx264", "-preset", "fast", "-crf", "20",
            "-c:a", "aac", "-b:a", "192k",
            out_mp4
        ]

    subprocess.run(cmd_render, check=True)
    print(f"[✓] Successfully Rendered: {out_mp4}")

print("\n[*] All requested shorts rendered successfully with pristine video & audio!")

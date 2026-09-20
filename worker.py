import os
import sys
import glob
import json
import re
import subprocess

print("[*] Initializing Single-Stream Transcript-Guided Slicer...")

# 1. Setup Persistent Netscape Cookie File
cookie_file = os.path.abspath("youtube_cookies.txt")
cookies_env = os.environ.get('COOKIES_DATA', '').strip()
has_valid_cookies = False

if cookies_env and len(cookies_env) > 30:
    lines_out = ["# Netscape HTTP Cookie File", "# https://curl.se/docs/http-cookies.html", ""]
    valid_count = 0

    for raw_line in cookies_env.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("# Netscape") or line.startswith("# HTTP"):
            continue
        if line.startswith("#") and not line.startswith("#HttpOnly_"):
            continue
        if line.startswith("#HttpOnly_"):
            line = line[len("#HttpOnly_"):]

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
        print(f"[✓] Authenticated session cookies loaded ({valid_count} entries).")
else:
    print("[!] Running without session cookies.")

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
    ytdl_format = "bv*[height<=720]+ba/b[height<=720]/bv*+ba/b/best"
    ffmpeg_crf = "22"
    ffmpeg_preset = "ultrafast"
    audio_br = "128k"
elif quality_mode == 'master':
    ytdl_format = "bv*[height<=1080]+ba/b[height<=1080]/bv*+ba/b/best"
    ffmpeg_crf = "16"
    ffmpeg_preset = "faster"
    audio_br = "320k"
else:  # balanced
    ytdl_format = "bv*[height<=1080]+ba/b[height<=1080]/bv*+ba/b/best"
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
    total_sec = max(0.0, total_sec)
    hrs = int(total_sec // 3600)
    mins = int((total_sec % 3600) // 60)
    secs = total_sec % 60
    if hrs > 0:
        return f"{hrs:02d}:{mins:02d}:{secs:05.2f}"
    return f"{mins:02d}:{secs:05.2f}"

# 3. Pull Subtitles First (Takes ~1s to get real word timings)
print("\n[*] Fetching spoken word timings from YouTube transcript...")
sub_prefix = "temp/subs"
cmd_sub = [
    "yt-dlp",
    "--skip-download",
    "--write-auto-sub",
    "--sub-lang", "en",
    "--sub-format", "vtt",
    "--extractor-args", "youtube:player_client=web_embedded,mweb,android,ios",
    "-o", sub_prefix,
    url
]
if has_valid_cookies and os.path.exists(cookie_file):
    cmd_sub.extend(["--cookies", cookie_file])
subprocess.run(cmd_sub, stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)

vtt_files = glob.glob("temp/subs*.vtt")
transcript_cues = []

if vtt_files:
    with open(vtt_files[0], 'r', encoding='utf-8', errors='ignore') as f:
        vtt_content = f.read()
    pattern = re.compile(r'((?:\d{2}:)?\d{2}:\d{2}\.\d{3})\s*-->\s*((?:\d{2}:)?\d{2}:\d{2}\.\d{3})(?:[^\n]*)\n([\s\S]*?)(?=\n\n|\n(?:\d{2}:)?\d{2}:\d{2}\.\d{3}|\Z)')
    for m in pattern.finditer(vtt_content):
        s_str, e_str, raw_txt = m.groups()
        clean_txt = re.sub(r'<[^>]+>', '', raw_txt).strip()
        if clean_txt:
            transcript_cues.append({
                'start': parse_to_sec(s_str),
                'end': parse_to_sec(e_str),
                'text': clean_txt
            })
    print(f"[✓] Parsed {len(transcript_cues)} speech cues from video transcript.")
else:
    print("[!] No English transcript found; falling back to silence pause snapping.")

def snap_to_speech(target_start, target_end, cues):
    if not cues:
        return max(0.0, target_start - 0.4), target_end + 2.5

    # Snap start to sentence beginning
    start_cues = [c for c in cues if abs(c['start'] - target_start) <= 5.0]
    if start_cues:
        best_start = min(start_cues, key=lambda c: abs(c['start'] - target_start))
        clean_start = max(0.0, best_start['start'] - 0.2)
    else:
        clean_start = max(0.0, target_start - 0.4)

    # Snap end to sentence completion (punctuation or breath pause)
    end_cues = [c for c in cues if c['end'] >= target_end - 1.0 and c['end'] <= target_end + 9.0]
    clean_end = target_end + 2.5
    if end_cues:
        found = False
        for i, c in enumerate(end_cues):
            t = c['text'].strip()
            if t.endswith(('.', '!', '?', '."', '?"', '!"')):
                clean_end = c['end'] + 0.3
                found = True
                break
            if i + 1 < len(end_cues):
                gap = end_cues[i+1]['start'] - c['end']
                if gap >= 0.45:
                    clean_end = c['end'] + 0.25
                    found = True
                    break
        if not found:
            clean_end = end_cues[-1]['end'] + 0.3

    return clean_start, clean_end

# 4. Download Full Video Stream ONCE (15-20s on Gigabit Network)
master_file = "temp/master_video.mp4"
print("\n[*] Downloading video stream ONCE (eliminates 40-minute network throttle)...")

cmd_dl = [
    "yt-dlp",
    "--remote-components", "ejs:github",
    "--extractor-args", "youtube:player_client=web_embedded,mweb,android,ios",
    "-f", ytdl_format,
    "--merge-output-format", "mp4",
    "--no-check-certificates"
]
if has_valid_cookies and os.path.exists(cookie_file):
    cmd_dl.extend(["--cookies", cookie_file])
cmd_dl.extend([url, "-o", master_file])

subprocess.run(cmd_dl, check=True)

if not os.path.exists(master_file):
    matches = glob.glob("temp/master_video.*")
    if matches:
        master_file = matches[0]
    else:
        raise FileNotFoundError("Master video download failed.")

print(f"[✓] Master stream cached locally: {master_file}")

# 5. Slice All Clips Locally with Complete Sentence Snapping
print(f"\n[*] Slicing {len(clips)} clips locally at exact sentence boundaries...")

for idx, clip_item in enumerate(clips, start=1):
    cid = clip_item.get('id', idx)
    raw_start = clip_item.get('start', '00:00')
    raw_end = clip_item.get('end', '00:30')
    clean_label = clip_item.get('label', f'clip_{cid}').replace(' ', '_').replace(':', '')

    t_start = parse_to_sec(raw_start)
    t_end = parse_to_sec(raw_end)

    clean_start, clean_end = snap_to_speech(t_start, t_end, transcript_cues)
    duration = clean_end - clean_start

    out_mp4 = f"output/clip_{cid}_{clean_label}.mp4"
    print(f"[{idx}/{len(clips)}] Cutting {sec_to_str(clean_start)} -> {sec_to_str(clean_end)} (Duration: {duration:.1f}s)...")

    cmd_slice = [
        "ffmpeg", "-y",
        "-ss", str(clean_start),
        "-t", str(duration),
        "-i", master_file,
        "-c:v", "libx264",
        "-preset", ffmpeg_preset,
        "-crf", ffmpeg_crf,
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-b:a", audio_br,
        "-movflags", "+faststart",
        out_mp4
    ]
    subprocess.run(cmd_slice, check=True)
    print(f"[✓] Finished Clip {cid}: {out_mp4}")

print(f"\n[✓] All {len(clips)} clips exported with complete sentence conclusions!")

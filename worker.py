import os
import sys
import json
import subprocess
from faster_whisper import WhisperModel

print("[*] Starting Clip Studio Engine...")

# 1. Setup cookies from GitHub Secrets or environment
cookies_path = None
cookies_env = os.environ.get('COOKIES_DATA', '').strip()
if cookies_env and len(cookies_env) > 20:
    cookies_path = "temp/youtube_cookies.txt"
    os.makedirs('temp', exist_ok=True)
    with open(cookies_path, "w", encoding="utf-8") as f:
        f.write(cookies_env)
    print("[*] Secure YouTube cookies loaded successfully.")
else:
    print("[!] No cookies found or COOKIES_DATA was empty. Using mobile client bypass.")

# 2. Parse payload
payload_env = os.environ.get('JOB_PAYLOAD', '')
payload = {}
if payload_env and payload_env != 'null':
    try:
        payload = json.loads(payload_env)
    except Exception as e:
        print(f"[!] Warning parsing payload JSON: {e}")

url = payload.get('url') or (sys.argv[1] if len(sys.argv) > 1 else None)
timestamps = payload.get('timestamps', [])
style = payload.get('style', 'hormozi')

if not url:
    print("[!] No URL provided. Exiting.")
    sys.exit(1)

# Clean tracking IDs from URL
if "youtu.be/" in url:
    video_id = url.split("youtu.be/")[1].split("?")[0]
    url = f"https://www.youtube.com/watch?v={video_id}"
elif "watch?v=" in url:
    video_id = url.split("watch?v=")[1].split("&")[0]
    url = f"https://www.youtube.com/watch?v={video_id}"

if not timestamps:
    timestamps = [{"start": "00:00", "end": "00:30", "label": "Clip 1"}]

os.makedirs('output', exist_ok=True)
os.makedirs('temp', exist_ok=True)

# 5 Trending Caption Presets
STYLES = {
    "gold": {"primary": "&HFFFFFF&", "highlight": "&H00D7FF&", "font": "Arial", "size": "65", "bold": "-1", "border": "4"},
    "hormozi": {"primary": "&H00FFFF&", "highlight": "&H00FF00&", "font": "Impact", "size": "75", "bold": "-1", "border": "6"},
    "mrbeast": {"primary": "&HFFFFFF&", "highlight": "&H00FFFF&", "font": "Impact", "size": "72", "bold": "-1", "border": "5"},
    "neon": {"primary": "&HFFFFFF&", "highlight": "&HFF00FF&", "font": "Arial", "size": "68", "bold": "-1", "border": "4"},
    "minimal": {"primary": "&HFFFFFF&", "highlight": "&H888888&", "font": "Arial", "size": "50", "bold": "0", "border": "2"}
}

active_cfg = STYLES.get(style, STYLES["hormozi"])

print(f"[*] Target video: {url}")
print(f"[*] Processing {len(timestamps)} clips with preset: {style}")

print("[*] Loading AI Whisper model...")
model = WhisperModel("base.en", device="cpu", compute_type="int8")

for idx, item in enumerate(timestamps):
    clip_id = idx + 1
    start = item.get('start', '00:00')
    end = item.get('end', '00:30')
    label = item.get('label', f'Clip {clip_id}')
    clean_label = "".join(c if c.isalnum() else "_" for c in label)

    raw_mp4 = f"temp/raw_{clip_id}.mp4"
    wav_path = f"temp/audio_{clip_id}.wav"
    ass_file = f"temp/sub_{clip_id}.ass"
    final_mp4 = f"output/{clip_id}_{clean_label}.mp4"

    print(f"\n[*] Slicing Clip #{clip_id} ({start} -> {end})...")
    
    # Android client bypass to prevent bot verification errors
    cmd_download = [
        "yt-dlp",
        "--extractor-args", "youtube:player-client=android,ios,web",
        "--download-sections", f"*{start}-{end}",
        "-f", "bv*[height<=1080]+ba/b[height<=1080]/best",
        "--force-keyframes-at-cuts",
        "--no-check-certificates",
        "--geo-bypass"
    ]
    
    if cookies_path and os.path.exists(cookies_path):
        cmd_download.extend(["--cookies", cookies_path])
        
    cmd_download.extend([url, "-o", raw_mp4])

    print(f"[*] Running command: {' '.join(cmd_download)}")
    subprocess.run(cmd_download, check=True)

    print(f"[*] Transcribing audio for Clip #{clip_id}...")
    subprocess.run(["ffmpeg", "-y", "-i", raw_mp4, "-vn", "-ar", "16000", "-ac", "1", wav_path], check=True)
    segments, _ = model.transcribe(wav_path, word_timestamps=True)

    print(f"[*] Creating {style.upper()} animated captions...")
    with open(ass_file, "w", encoding="utf-8") as f:
        f.write("[Script Info]\nScriptType: v4.00+\nPlayResX: 1080\nPlayResY: 1920\n\n")
        f.write("[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, OutlineColour, BackColour, Bold, Italic, Alignment, MarginV, Outline\n")
        f.write(f"Style: Default,{active_cfg['font']},{active_cfg['size']},{active_cfg['primary']},&H000000&,&H80000000,{active_cfg['bold']},0,2,240,{active_cfg['border']}\n\n")
        f.write("[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n")
        
        for seg in segments:
            for w in seg.words:
                def fmt(sec):
                    return f"0:{int(sec//60):02d}:{sec%60:05.2f}"
                word_clean = w.word.strip().upper()
                if word_clean:
                    f.write(f"Dialogue: 0,{fmt(w.start)},{fmt(w.end)},Default,,0,0,0,,{{\\c{active_cfg['highlight']}}}{word_clean}{{\\c{active_cfg['primary']}}}\n")

    print(f"[*] Rendering vertical 9:16 video...")
    cmd_render = [
        "ffmpeg", "-y", "-i", raw_mp4,
        "-vf", f"crop=ih*(9/16):ih,subtitles={ass_file}",
        "-c:v", "libx264", "-preset", "fast", "-crf", "22",
        "-c:a", "aac", "-b:a", "128k",
        final_mp4
    ]
    subprocess.run(cmd_render, check=True)
    print(f"[✓] Clip #{clip_id} complete: {final_mp4}")

print("[*] All tasks finished successfully!")

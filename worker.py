import os
import sys
import glob
import json
import subprocess
from faster_whisper import WhisperModel

print("[*] Starting Atelier Clip Studio Mobile Cloud Engine...")

# 1. Setup & sanitize cookies
cookies_path = None
cookies_env = os.environ.get('COOKIES_DATA', '').strip()

if cookies_env and len(cookies_env) > 20:
    cookies_path = "temp/youtube_cookies.txt"
    os.makedirs('temp', exist_ok=True)
    sanitized_lines = []
    for line in cookies_env.splitlines():
        line_clean = line.strip()
        if not line_clean or line_clean.startswith("#"):
            sanitized_lines.append(line)
            continue
        parts = line.split("\t")
        if len(parts) >= 7:
            if parts[0].startswith("."):
                parts[1] = "TRUE"
            else:
                parts[1] = "FALSE"
            sanitized_lines.append("\t".join(parts))
        else:
            sanitized_lines.append(line)

    with open(cookies_path, "w", encoding="utf-8") as f:
        f.write("\n".join(sanitized_lines) + "\n")
    print("[*] Secure YouTube cookies loaded successfully.")
else:
    print("[*] No custom cookies found.")

# 2. Parse job parameters
payload_env = os.environ.get('JOB_PAYLOAD', '')
payload = {}
if payload_env and payload_env != 'null':
    try:
        payload = json.loads(payload_env)
    except Exception as e:
        print(f"[!] Warning parsing JSON: {e}")

url = payload.get('url') or (sys.argv[1] if len(sys.argv) > 1 else None)
timestamps = payload.get('timestamps', [])
style = payload.get('style', 'hormozi')

if not url:
    print("[!] Error: No URL supplied.")
    sys.exit(1)

if "youtu.be/" in url:
    video_id = url.split("youtu.be/")[1].split("?")[0]
    url = f"https://www.youtube.com/watch?v={video_id}"
elif "watch?v=" in url:
    video_id = url.split("watch?v=")[1].split("&")[0]
    url = f"https://www.youtube.com/watch?v={video_id}"

if not timestamps:
    timestamps = [{"start": "00:00", "end": "00:30", "label": "Clip_1", "mode": "single", "crop_pos": 0.5}]

os.makedirs('output', exist_ok=True)
os.makedirs('temp', exist_ok=True)

STYLES = {
    "hormozi": {"primary": "&H00FFFFFF&", "highlight": "&H0024FF00&", "font": "Impact", "size": "72", "bold": "-1", "border": "6", "back": "&H00000000&"},
    "gold": {"primary": "&H00FFFFFF&", "highlight": "&H00D4AF37&", "font": "Georgia", "size": "64", "bold": "-1", "border": "4", "back": "&H80000000&"},
    "minimal": {"primary": "&H00FFFFFF&", "highlight": "&H00E2DFD6&", "font": "Arial", "size": "56", "bold": "-1", "border": "3", "back": "&HCC000000&"},
    "mrbeast": {"primary": "&H0000FFFF&", "highlight": "&H00FFFF00&", "font": "Impact", "size": "75", "bold": "-1", "border": "7", "back": "&H00000000&"},
    "neon": {"primary": "&H00FFFFFF&", "highlight": "&H00FF007F&", "font": "Arial", "size": "68", "bold": "-1", "border": "5", "back": "&H80000000&"},
    "vogue": {"primary": "&H00EEEEEE&", "highlight": "&H00FFFFFF&", "font": "Arial", "size": "54", "bold": "0", "border": "2", "back": "&H60000000&"}
}

active_cfg = STYLES.get(style, STYLES["hormozi"])
print(f"[*] Target video: {url}")
print("[*] Loading AI Whisper model...")
model = WhisperModel("base.en", device="cpu", compute_type="int8")

for idx, item in enumerate(timestamps):
    clip_id = idx + 1
    start = item.get('start', '00:00')
    end = item.get('end', '00:30')
    label = item.get('label', f'Clip_{clip_id}')
    clean_label = "".join(c if c.isalnum() else "_" for c in label)

    mode = item.get('mode', 'single')
    pos_single = float(item.get('crop_pos', 0.5))
    face_top = float(item.get('face_top', 0.2))
    face_bot = float(item.get('face_bot', 0.8))

    out_template = f"temp/raw_{clip_id}.%(ext)s"
    wav_path = f"temp/audio_{clip_id}.wav"
    ass_file = f"temp/sub_{clip_id}.ass"
    final_mp4 = f"output/{clip_id}_{clean_label}.mp4"

    print(f"\n[*] Slicing Clip #{clip_id} ({start} -> {end})...")
    cmd_download = [
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
        cmd_download.extend(["--cookies", cookies_path])
    cmd_download.extend([url, "-o", out_template])
    subprocess.run(cmd_download, check=True)

    downloaded_files = glob.glob(f"temp/raw_{clip_id}.*")
    valid_raw_files = [f for f in downloaded_files if not f.endswith(".part") and not f.endswith(".ytdl")]
    if not valid_raw_files:
        raise FileNotFoundError(f"Could not find slice file for clip {clip_id}")
    actual_raw_video = valid_raw_files[0]

    print(f"[*] Transcribing audio with word-level timestamps...")
    subprocess.run(["ffmpeg", "-y", "-i", actual_raw_video, "-vn", "-ar", "16000", "-ac", "1", wav_path], check=True)
    segments, _ = model.transcribe(wav_path, word_timestamps=True)

    print(f"[*] Generating {style.upper()} animated subtitles...")
    italic_flag = "-1" if style == "gold" else "0"
    with open(ass_file, "w", encoding="utf-8") as f:
        f.write("[Script Info]\nScriptType: v4.00+\nPlayResX: 1080\nPlayResY: 1920\n\n")
        f.write("[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, OutlineColour, BackColour, Bold, Italic, Alignment, MarginV, Outline\n")
        f.write(f"Style: Default,{active_cfg['font']},{active_cfg['size']},{active_cfg['primary']},&H000000&,{active_cfg['back']},{active_cfg['bold']},{italic_flag},2,260,{active_cfg['border']}\n\n")
        f.write("[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n")
        for seg in segments:
            for w in seg.words:
                def fmt(sec):
                    return f"0:{int(sec//60):02d}:{sec%60:05.2f}"
                word = w.word.strip().upper()
                if word:
                    f.write(f"Dialogue: 0,{fmt(w.start)},{fmt(w.end)},Default,,0,0,0,,{{\\c{active_cfg['highlight']}}}{word}{{\\c{active_cfg['primary']}}}\n")

    print(f"[*] Rendering vertical 9:16 short in {mode.upper()} mode...")
    if mode == "split":
        # Stacked Dual-Face Mode (Top/Bottom 1080x1920)
        filter_str = (
            f"[0:v]split=2[in1][in2]; "
            f"[in1]crop=w=ih*(9/8):h=ih:x=(iw-ih*(9/8))*{face_top}:y=0,scale=1080:960[top]; "
            f"[in2]crop=w=ih*(9/8):h=ih:x=(iw-ih*(9/8))*{face_bot}:y=0,scale=1080:960[bot]; "
            f"[top][bot]vstack=inputs=2[v_stacked]; "
            f"[v_stacked]subtitles='{ass_file}'[outv]"
        )
        cmd_render = [
            "ffmpeg", "-y", "-i", actual_raw_video,
            "-filter_complex", filter_str,
            "-map", "[outv]", "-map", "0:a",
            "-c:v", "libx264", "-preset", "fast", "-crf", "22",
            "-c:a", "aac", "-b:a", "128k",
            final_mp4
        ]
    else:
        # Single Centered Speaker Mode (Standard 9:16)
        crop_filter = f"crop=ih*(9/16):ih:(iw-ih*(9/16))*{pos_single}:0,scale=1080:1920,subtitles={ass_file}"
        cmd_render = [
            "ffmpeg", "-y", "-i", actual_raw_video,
            "-vf", crop_filter,
            "-c:v", "libx264", "-preset", "fast", "-crf", "22",
            "-c:a", "aac", "-b:a", "128k",
            final_mp4
        ]

    subprocess.run(cmd_render, check=True)
    print(f"[✓] Finished Clip #{clip_id}: {final_mp4}")

print("[*] All jobs finished successfully!")


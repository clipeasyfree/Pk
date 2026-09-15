import os
import sys
import glob
import json
import subprocess
from faster_whisper import WhisperModel

print("[*] Starting Atelier Studio Cloud Engine...")

# 1. Setup cookies
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
            parts[1] = "TRUE" if parts[0].startswith(".") else "FALSE"
            sanitized_lines.append("\t".join(parts))
        else:
            sanitized_lines.append(line)
    with open(cookies_path, "w", encoding="utf-8") as f:
        f.write("\n".join(sanitized_lines) + "\n")

# 2. Parse job parameters
payload_env = os.environ.get('JOB_PAYLOAD', '')
payload = json.loads(payload_env) if payload_env and payload_env != 'null' else {}

action = payload.get('action', 'render')  # 'slice' or 'render'
url = payload.get('url', '')
start = payload.get('start', '00:00')
end = payload.get('end', '00:30')
label = payload.get('label', 'Clip_1')
style = payload.get('style', 'captions_pill')
crop_pos = float(payload.get('crop_pos', 0.5))

if not url:
    print("[!] Error: No URL supplied.")
    sys.exit(1)

if "youtu.be/" in url:
    vid = url.split("youtu.be/")[1].split("?")[0]
    url = f"https://www.youtube.com/watch?v={vid}"
elif "watch?v=" in url:
    vid = url.split("watch?v=")[1].split("&")[0]
    url = f"https://www.youtube.com/watch?v={vid}"

os.makedirs('output', exist_ok=True)
os.makedirs('temp', exist_ok=True)

raw_slice_template = "temp/raw_slice.%(ext)s"
raw_mp4 = "output/raw_preview.mp4"
final_mp4 = f"output/{label}.mp4"

# Step A: Slice & Download Raw Segment
print(f"[*] Downloading slice ({start} -> {end}) from {url}...")
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
cmd_download.extend([url, "-o", raw_slice_template])
subprocess.run(cmd_download, check=True)

downloaded = glob.glob("temp/raw_slice.*")
valid_raw = [f for f in downloaded if not f.endswith(".part") and not f.endswith(".ytdl")]
if not valid_raw:
    raise FileNotFoundError("Could not find downloaded slice.")
source_file = valid_raw[0]

# Standardize to raw_preview.mp4
subprocess.run(["ffmpeg", "-y", "-i", source_file, "-c", "copy", raw_mp4], check=True)

if action == "slice":
    print("[✓] Raw slice ready for mobile face inspection.")
    sys.exit(0)

# Step B: Final 9:16 Render with Captions.ai Style Subtitles
print("[*] Transcribing audio with Whisper AI...")
wav_path = "temp/audio.wav"
ass_file = "temp/subtitles.ass"
subprocess.run(["ffmpeg", "-y", "-i", raw_mp4, "-vn", "-ar", "16000", "-ac", "1", wav_path], check=True)

model = WhisperModel("base.en", device="cpu", compute_type="int8")
segments, _ = model.transcribe(wav_path, word_timestamps=True)

# Captions.ai & Luxury Subtitle Presets
PRESETS = {
    # Captions.ai Signature: Rounded dark pill box with bright neon active word
    "captions_pill": {"primary": "&H00FFFFFF&", "highlight": "&H0024FF00&", "font": "Arial", "size": "60", "bold": "-1", "border": "4", "back": "&H80000000&", "borderstyle": "3"},
    # Hormozi Pop: Heavy outline, bold comic contrast
    "hormozi": {"primary": "&H0000FFFF&", "highlight": "&H0024FF00&", "font": "Impact", "size": "72", "bold": "-1", "border": "6", "back": "&H00000000&", "borderstyle": "1"},
    # Luxury Silk & Gold: Italicized serif with pure champagne gold highlight
    "luxury_gold": {"primary": "&H00FFFFFF&", "highlight": "&H0037AFD4&", "font": "Georgia", "size": "62", "bold": "-1", "border": "3", "back": "&H90000000&", "borderstyle": "3"},
    # Cyber Glow: Vibrant magenta karaoke tracking
    "cyber_glow": {"primary": "&H00FFFFFF&", "highlight": "&H00FF00A0&", "font": "Arial", "size": "66", "bold": "-1", "border": "5", "back": "&H00000000&", "borderstyle": "1"}
}

cfg = PRESETS.get(style, PRESETS["captions_pill"])

with open(ass_file, "w", encoding="utf-8") as f:
    f.write("[Script Info]\nScriptType: v4.00+\nPlayResX: 1080\nPlayResY: 1920\n\n")
    f.write("[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, OutlineColour, BackColour, Bold, Italic, Alignment, MarginV, Outline, BorderStyle\n")
    f.write(f"Style: Default,{cfg['font']},{cfg['size']},{cfg['primary']},&H00000000&,{cfg['back']},{cfg['bold']},0,2,300,{cfg['border']},{cfg['borderstyle']}\n\n")
    f.write("[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n")
    for seg in segments:
        for w in seg.words:
            def fmt(sec): return f"0:{int(sec//60):02d}:{sec%60:05.2f}"
            word = w.word.strip().upper()
            if word:
                f.write(f"Dialogue: 0,{fmt(w.start)},{fmt(w.end)},Default,,0,0,0,,{{\\c{cfg['highlight']}}}{word}{{\\c{cfg['primary']}}}\n")

print(f"[*] Rendering vertical 9:16 short centered at {int(crop_pos*100)}%...")
crop_filter = f"crop=ih*(9/16):ih:(iw-ih*(9/16))*{crop_pos}:0,scale=1080:1920,subtitles={ass_file}"

cmd_render = [
    "ffmpeg", "-y", "-i", raw_mp4,
    "-vf", crop_filter,
    "-c:v", "libx264", "-preset", "fast", "-crf", "22",
    "-c:a", "aac", "-b:a", "128k",
    final_mp4
]
subprocess.run(cmd_render, check=True)
print(f"[✓] Short completed: {final_mp4}")

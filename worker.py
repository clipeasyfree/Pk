import os
import sys
import glob
import json
import subprocess
from faster_whisper import WhisperModel

print("[*] Initializing Atelier Studio Engine...")

# 1. Sanitize cookies
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

# 2. Parse job parameters
payload_env = os.environ.get('JOB_PAYLOAD', '')
payload = json.loads(payload_env) if payload_env and payload_env != 'null' else {}

url = payload.get('url', '')
start = payload.get('start', '00:04')
end = payload.get('end', '00:35')
style = payload.get('style', 'captions_pill')
crop_pos = float(payload.get('crop_pos', 0.5))

if not url:
    print("[!] No URL provided.")
    sys.exit(1)

if "youtu.be/" in url:
    url = f"https://www.youtube.com/watch?v={url.split('youtu.be/')[1].split('?')[0]}"
elif "watch?v=" in url:
    url = f"https://www.youtube.com/watch?v={url.split('watch?v=')[1].split('&')[0]}"

os.makedirs('output', exist_ok=True)
os.makedirs('temp', exist_ok=True)

raw_template = "temp/slice.%(ext)s"
wav_path = "temp/audio.wav"
ass_file = "temp/subtitles.ass"
final_mp4 = "output/viral_short.mp4"

print(f"[*] Downloading slice ({start} -> {end})...")
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
cmd_dl.extend([url, "-o", raw_template])
subprocess.run(cmd_dl, check=True)

files = [f for f in glob.glob("temp/slice.*") if not f.endswith(".part") and not f.endswith(".ytdl")]
if not files:
    raise FileNotFoundError("Could not find downloaded slice.")
source_video = files[0]

# 3. Whisper Audio Transcription
print("[*] Transcribing speech with Whisper AI...")
subprocess.run(["ffmpeg", "-y", "-i", source_video, "-vn", "-ar", "16000", "-ac", "1", wav_path], check=True)
model = WhisperModel("base.en", device="cpu", compute_type="int8")
segments, _ = model.transcribe(wav_path, word_timestamps=True)

# 4. Captions.ai Style Presets
PRESETS = {
    # 1. Captions.ai Signature: Translucent dark matte box, neon lime active pop
    "captions_pill": {"primary": "&H00FFFFFF&", "highlight": "&H0024FF00&", "font": "Arial", "size": "62", "bold": "-1", "border": "4", "back": "&H99000000&", "style": "3"},
    # 2. Iman Gadzhi Silk: Italicized luxury serif, champagne gold highlight
    "luxury_gold": {"primary": "&H00FFFFFF&", "highlight": "&H0037AFD4&", "font": "Georgia", "size": "60", "bold": "-1", "border": "3", "back": "&HA0000000&", "style": "3"},
    # 3. Hormozi Kinetic: High contrast yellow & green pop, thick outline
    "hormozi": {"primary": "&H0000FFFF&", "highlight": "&H0024FF00&", "font": "Impact", "size": "72", "bold": "-1", "border": "6", "back": "&H00000000&", "style": "1"},
    # 4. Cyber Glow: Electric magenta karaoke tracking
    "cyber_glow": {"primary": "&H00FFFFFF&", "highlight": "&H00FF00A0&", "font": "Arial", "size": "64", "bold": "-1", "border": "5", "back": "&H00000000&", "style": "1"}
}

cfg = PRESETS.get(style, PRESETS["captions_pill"])
italic_flag = "-1" if style == "luxury_gold" else "0"

with open(ass_file, "w", encoding="utf-8") as f:
    f.write("[Script Info]\nScriptType: v4.00+\nPlayResX: 1080\nPlayResY: 1920\n\n")
    f.write("[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, OutlineColour, BackColour, Bold, Italic, Alignment, MarginV, Outline, BorderStyle\n")
    f.write(f"Style: Default,{cfg['font']},{cfg['size']},{cfg['primary']},&H00000000&,{cfg['back']},{cfg['bold']},{italic_flag},2,320,{cfg['border']},{cfg['style']}\n\n")
    f.write("[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n")
    for seg in segments:
        for w in seg.words:
            def fmt(s): return f"0:{int(s//60):02d}:{s%60:05.2f}"
            cleaned = w.word.strip().upper()
            if cleaned:
                f.write(f"Dialogue: 0,{fmt(w.start)},{fmt(w.end)},Default,,0,0,0,,{{\\c{cfg['highlight']}}}{cleaned}{{\\c{cfg['primary']}}}\n")

# 5. Render 9:16 Vertical Video
print(f"[*] Rendering vertical 9:16 short centered at {int(crop_pos*100)}%...")
crop_filter = f"crop=ih*(9/16):ih:(iw-ih*(9/16))*{crop_pos}:0,scale=1080:1920,subtitles={ass_file}"

cmd_render = [
    "ffmpeg", "-y", "-i", source_video,
    "-vf", crop_filter,
    "-c:v", "libx264", "-preset", "fast", "-crf", "22",
    "-c:a", "aac", "-b:a", "128k",
    final_mp4
]
subprocess.run(cmd_render, check=True)
print(f"[✓] Successfully finished: {final_mp4}")

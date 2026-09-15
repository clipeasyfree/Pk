import os
import sys
import glob
import json
import subprocess
from faster_whisper import WhisperModel

print("[*] Initializing Studio Captik Typography Engine...")

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

# 2. Parse job parameters
payload_env = os.environ.get('JOB_PAYLOAD', '')
payload = json.loads(payload_env) if payload_env and payload_env != 'null' else {}

url = payload.get('url', '')
start = payload.get('start', '00:04')
end = payload.get('end', '00:35')
style = payload.get('style', 'captik_glow')
crop_pos = float(payload.get('crop_pos', 0.5))
clip_id = payload.get('clip_id', 1)

if not url:
    print("[!] Error: No URL supplied.")
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
final_mp4 = f"output/viral_short_{clip_id}.mp4"

for f in glob.glob("output/*"):
    try: os.remove(f)
    except: pass

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

# 4. Authentic Captik & Captions.ai Style Presets (ASS BGR Color Mapping)
STYLES = {
    # 1. Captik Glow: Neon electric lime glow on active word
    "captik_glow": {"font": "Impact", "size": "70", "primary": "&H00FFFFFF&", "highlight": "&H0033FF33&", "border": "2", "blur": "8", "shadow": "0", "italic": "0", "scale": "115"},
    # 2. Captik Shadow: Ultra-bold white with deep solid drop shadow
    "captik_shadow": {"font": "Arial", "size": "72", "primary": "&H00FFFFFF&", "highlight": "&H00FFFFFF&", "border": "0", "blur": "0", "shadow": "6", "italic": "0", "scale": "120"},
    # 3. Delhi: Editorial luxury italic serif with soft moonlight aura
    "delhi": {"font": "Georgia", "size": "64", "primary": "&H00FFFFFF&", "highlight": "&H00FFFFFF&", "border": "1", "blur": "6", "shadow": "0", "italic": "-1", "scale": "110"},
    # 4. Illusion: Kinetic giant scale pop (1.4x scale on keyword)
    "illusion": {"font": "Arial", "size": "66", "primary": "&H00FFFFFF&", "highlight": "&H00FFFFFF&", "border": "3", "blur": "0", "shadow": "2", "italic": "0", "scale": "140"},
    # 5. Editor Masala: Clean text with bright canary yellow punch
    "editor_masala": {"font": "Impact", "size": "75", "primary": "&H00FFFFFF&", "highlight": "&H0000E5FF&", "border": "4", "blur": "0", "shadow": "2", "italic": "0", "scale": "120"},
    # 6. Aura: Editorial italic serif paired with vibrant sky-blue active sans
    "aura": {"font": "Georgia", "size": "68", "primary": "&H00FFFFFF&", "highlight": "&H00FFC266&", "border": "2", "blur": "3", "shadow": "0", "italic": "-1", "scale": "120"},
    # 7. Swiss: Modernist Helvetica/Arial Black, stacked canary yellow & white
    "swiss": {"font": "Arial", "size": "70", "primary": "&H00FFFFFF&", "highlight": "&H0000D4FF&", "border": "4", "blur": "0", "shadow": "3", "italic": "0", "scale": "115"},
    # 8. The Big Red: Dramatic cinematic crimson red
    "the_big_red": {"font": "Georgia", "size": "72", "primary": "&H00FFFFFF&", "highlight": "&H003333E6&", "border": "2", "blur": "4", "shadow": "0", "italic": "0", "scale": "130"},
    # 9. Clean Glow: Luminous pure white with diffused ambient drop glow
    "clean_glow": {"font": "Arial", "size": "62", "primary": "&H00FFFFFF&", "highlight": "&H00FFFFFF&", "border": "2", "blur": "10", "shadow": "0", "italic": "0", "scale": "105"}
}

cfg = STYLES.get(style, STYLES["captik_glow"])

with open(ass_file, "w", encoding="utf-8") as f:
    f.write("[Script Info]\nScriptType: v4.00+\nPlayResX: 1080\nPlayResY: 1920\n\n")
    f.write("[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, OutlineColour, BackColour, Bold, Italic, Alignment, MarginV, Outline, Shadow, BorderStyle\n")
    f.write(f"Style: Default,{cfg['font']},{cfg['size']},{cfg['primary']},&H00000000&,&H80000000&,-1,{cfg['italic']},2,360,{cfg['border']},{cfg['shadow']},1\n\n")
    f.write("[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n")
    
    for seg in segments:
        for w in seg.words:
            def fmt(sec): return f"0:{int(sec//60):02d}:{sec%60:05.2f}"
            word_clean = w.word.strip()
            if word_clean:
                # Apply word-level kinetic scale, highlight color, and glow blur
                highlight_tag = f"{{\\c{cfg['highlight']}\\3c{cfg['highlight']}\\blur{cfg['blur']}\\fscx{cfg['scale']}\\fscy{cfg['scale']}}}"
                reset_tag = f"{{\\c{cfg['primary']}\\3c&H00000000&\\blur0\\fscx100\\fscy100}}"
                f.write(f"Dialogue: 0,{fmt(w.start)},{fmt(w.end)},Default,,0,0,0,,{highlight_tag}{word_clean}{reset_tag}\n")

# 5. Render 9:16 Vertical Video with Selected Style
print(f"[*] Rendering 9:16 Short with style: {style.upper()}...")
crop_filter = f"crop=ih*(9/16):ih:(iw-ih*(9/16))*{crop_pos}:0,scale=1080:1920,subtitles={ass_file}"

cmd_render = [
    "ffmpeg", "-y", "-i", source_video,
    "-vf", crop_filter,
    "-c:v", "libx264", "-preset", "fast", "-crf", "22",
    "-c:a", "aac", "-b:a", "128k",
    final_mp4
]
subprocess.run(cmd_render, check=True)
print(f"[✓] Short completed: {final_mp4}")


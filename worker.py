import os
import sys
import glob
import json
import subprocess
from faster_whisper import WhisperModel

print("[*] Initializing VERTEX PRO Studio Engine...")

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

# 2. Parse payload
payload_env = os.environ.get('JOB_PAYLOAD', '')
payload = json.loads(payload_env) if payload_env and payload_env != 'null' else {}

url = payload.get('url', '')
clips = payload.get('clips', [])
style = payload.get('style', 'neon_lime')

if not url:
    print("[!] Error: No URL provided.")
    sys.exit(1)

if "youtu.be/" in url:
    url = f"https://www.youtube.com/watch?v={url.split('youtu.be/')[1].split('?')[0]}"
elif "watch?v=" in url:
    url = f"https://www.youtube.com/watch?v={url.split('watch?v=')[1].split('&')[0]}"

if not clips:
    clips = [{"id": 1, "start": "00:04", "end": "00:35", "crop_pos": 0.5, "mode": "single"}]

os.makedirs('output', exist_ok=True)
os.makedirs('temp', exist_ok=True)

for f in glob.glob("output/*"):
    try: os.remove(f)
    except: pass

# 3. Authentic Captik Typography Presets (90pt Bold with ASS &H00BBGGRR& Colors)
STYLES = {
    # 1. Captik Glow (Neon Lime active glow on Anton bold)
    "neon_lime": {
        "font": "Anton", "size": "92", "primary": "&H00FFFFFF&", "highlight": "&H0014FF39&",
        "border": "4", "blur": "14", "shadow": "0", "italic": "0", "scale": "115"
    },
    # 2. Captik Shadow (Montserrat Black with 8px drop shadow)
    "bold_shadow": {
        "font": "Montserrat", "size": "88", "primary": "&H00FFFFFF&", "highlight": "&H00FFFFFF&",
        "border": "0", "blur": "0", "shadow": "8", "italic": "0", "scale": "110"
    },
    # 3. Delhi (Editorial luxury italic Playfair Display)
    "moonlight_serif": {
        "font": "Playfair Display", "size": "82", "primary": "&H00FFFFFF&", "highlight": "&H00FFFFFF&",
        "border": "2", "blur": "10", "shadow": "0", "italic": "-1", "scale": "108"
    },
    # 4. Illusion (Kinetic 135% Scale Pop)
    "kinetic_scale": {
        "font": "Montserrat", "size": "84", "primary": "&H00FFFFFF&", "highlight": "&H00FFFFFF&",
        "border": "3", "blur": "0", "shadow": "4", "italic": "0", "scale": "135"
    },
    # 5. Editor Masala (Canary yellow punch)
    "canary_punch": {
        "font": "Anton", "size": "92", "primary": "&H00FFFFFF&", "highlight": "&H0000E5FF&",
        "border": "4", "blur": "0", "shadow": "4", "italic": "0", "scale": "115"
    },
    # 6. Aura (Editorial Playfair with Cyan accent)
    "sky_dual": {
        "font": "Playfair Display", "size": "84", "primary": "&H00FFFFFF&", "highlight": "&H00FFC266&",
        "border": "2", "blur": "4", "shadow": "0", "italic": "-1", "scale": "118"
    },
    # 7. Swiss (Modernist Anton with bright gold accent)
    "modernist_swiss": {
        "font": "Anton", "size": "90", "primary": "&H00FFFFFF&", "highlight": "&H0000D4FF&",
        "border": "4", "blur": "0", "shadow": "4", "italic": "0", "scale": "115"
    },
    # 8. The Big Red (Playfair Display with deep red accent)
    "crimson_cinematic": {
        "font": "Playfair Display", "size": "88", "primary": "&H00FFFFFF&", "highlight": "&H003333E6&",
        "border": "2", "blur": "6", "shadow": "0", "italic": "0", "scale": "125"
    },
    # 9. Clean Glow (Soft ambient white glow)
    "ambient_white": {
        "font": "Montserrat", "size": "80", "primary": "&H00FFFFFF&", "highlight": "&H00FFFFFF&",
        "border": "2", "blur": "16", "shadow": "0", "italic": "0", "scale": "105"
    }
}
cfg = STYLES.get(style, STYLES["neon_lime"])
print(f"[*] Subtitle Preset: {style.upper()} ({cfg['font']})")

print("[*] Loading Faster-Whisper AI model...")
model = WhisperModel("base.en", device="cpu", compute_type="int8")

# 4. Render All Selected Clips
for clip_item in clips:
    cid = clip_item.get('id', 1)
    start = clip_item.get('start', '00:04')
    end = clip_item.get('end', '00:35')
    mode = clip_item.get('mode', 'single')
    user_pos = float(clip_item.get('crop_pos', 0.5))
    clean_label = clip_item.get('label', f'clip_{cid}').replace(' ', '_').replace(':', '')

    dl_output = f"temp/raw_{cid}.%(ext)s"
    wav_path = f"temp/audio_{cid}.wav"
    ass_file = f"temp/sub_{cid}.ass"
    out_mp4 = f"output/short_{cid}_{clean_label}.mp4"

    print(f"\n==========================================")
    print(f"[*] Processing Clip #{cid} ({start} -> {end}) | Mode: {mode.upper()}...")
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

    downloaded = [f for f in glob.glob(f"temp/raw_{cid}.*") if not f.endswith(".part") and not f.endswith(".ytdl")]
    if not downloaded:
        raise FileNotFoundError(f"Could not find downloaded file for clip {cid}")
    source_video = downloaded[0]

    # Transcribe speech
    print(f"[*] Transcribing audio for Clip #{cid}...")
    subprocess.run(["ffmpeg", "-y", "-i", source_video, "-vn", "-ar", "16000", "-ac", "1", wav_path], check=True)
    segments, _ = model.transcribe(wav_path, word_timestamps=True)

    # Generate rhythmic 3-word phrase subtitles
    print(f"[*] Burning {style.upper()} stacked typography...")
    with open(ass_file, "w", encoding="utf-8") as f:
        f.write("[Script Info]\nScriptType: v4.00+\nPlayResX: 1080\nPlayResY: 1920\n\n")
        f.write("[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n")
        f.write(f"Style: Default,{cfg['font']},{cfg['size']},{cfg['primary']},&H000000FF&,&H00000000&,&H80000000&,-1,{cfg['italic']},0,0,100,100,0,0,1,{cfg['border']},{cfg['shadow']},2,40,40,420,1\n\n")
        f.write("[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n")

        all_words = []
        for s in segments:
            for w in s.words:
                cleaned = w.word.strip()
                if cleaned:
                    all_words.append({"word": cleaned.upper(), "start": w.start, "end": w.end})

        # Group words into 3-word chunks
        chunk_size = 3
        for i in range(0, len(all_words), chunk_size):
            chunk = all_words[i:i+chunk_size]
            for target_idx, active_word in enumerate(chunk):
                phrase_parts = []
                for idx, w in enumerate(chunk):
                    if idx == target_idx:
                        phrase_parts.append(f"{{\\c{cfg['highlight']}\\3c{cfg['highlight']}\\blur{cfg['blur']}\\fscx{cfg['scale']}\\fscy{cfg['scale']}}}{w['word']}{{\\c{cfg['primary']}\\3c&H00000000&\\blur0\\fscx100\\fscy100}}")
                    else:
                        phrase_parts.append(w['word'])

                def fmt(sec): return f"0:{int(sec//60):02d}:{sec%60:05.2f}"
                line_text = " ".join(phrase_parts)
                f.write(f"Dialogue: 0,{fmt(active_word['start'])},{fmt(active_word['end'])},Default,,0,0,0,,{line_text}\n")

    # Render: Stacked Split-Screen or Single Centered Speaker
    if mode == "split":
        print(f"[*] Rendering Stacked 9:16 Split-Screen (Host Top / Guest Bottom)...")
        filter_str = (
            f"[0:v]split=2[in1][in2]; "
            f"[in1]crop=w=ih*(9/8):h=ih:x=0:y=0,scale=1080:960[top]; "
            f"[in2]crop=w=ih*(9/8):h=ih:x=iw-ih*(9/8):y=0,scale=1080:960[bot]; "
            f"[top][bot]vstack=inputs=2[v_stacked]; "
            f"[v_stacked]subtitles='{ass_file}':fontsdir='fonts'[outv]"
        )
        cmd_render = [
            "ffmpeg", "-y", "-i", source_video,
            "-filter_complex", filter_str,
            "-map", "[outv]", "-map", "0:a",
            "-c:v", "libx264", "-preset", "fast", "-crf", "22",
            "-c:a", "aac", "-b:a", "128k",
            out_mp4
        ]
    else:
        print(f"[*] Rendering Single Speaker 9:16 at offset {int(user_pos * 100)}%...")
        crop_filter = f"crop=ih*(9/16):ih:(iw-ih*(9/16))*{user_pos}:0,scale=1080:1920,subtitles='{ass_file}':fontsdir='fonts'"
        cmd_render = [
            "ffmpeg", "-y", "-i", source_video,
            "-vf", crop_filter,
            "-c:v", "libx264", "-preset", "fast", "-crf", "22",
            "-c:a", "aac", "-b:a", "128k",
            out_mp4
        ]

    subprocess.run(cmd_render, check=True)
    print(f"[✓] Rendered: {out_mp4}")

print("\n[*] All requested shorts rendered successfully!")

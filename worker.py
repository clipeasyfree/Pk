import os
import sys
import glob
import json
import subprocess
import cv2
import numpy as np
from faster_whisper import WhisperModel

print("[*] Initializing VERTEX PRO AI Studio Engine...")

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
    clips = [{"id": 1, "start": "00:04", "end": "00:35", "crop_pos": 0.5}]

os.makedirs('output', exist_ok=True)
os.makedirs('temp', exist_ok=True)

for f in glob.glob("output/*"):
    try: os.remove(f)
    except: pass

# 3. Authentic Captik Style Definitions (using installed Google Fonts)
# ASS colors: &H00BBGGRR&
STYLES = {
    # 1. Captik Glow (Neon Lime active glow + Anton bold)
    "neon_lime": {
        "font": "Anton", "size": "76", "primary": "&H00FFFFFF&", "highlight": "&H0014FF39&",
        "border": "3", "blur": "12", "shadow": "0", "italic": "0", "scale": "115"
    },
    # 2. Captik Shadow (Ultra bold Montserrat Black with heavy 3D drop shadow)
    "bold_shadow": {
        "font": "Montserrat-Black", "size": "72", "primary": "&H00FFFFFF&", "highlight": "&H00FFFFFF&",
        "border": "0", "blur": "0", "shadow": "7", "italic": "0", "scale": "110"
    },
    # 3. Delhi (Editorial luxury italic Playfair Display)
    "moonlight_serif": {
        "font": "PlayfairDisplay-BoldItalic", "size": "66", "primary": "&H00FFFFFF&", "highlight": "&H00FFFFFF&",
        "border": "1", "blur": "8", "shadow": "0", "italic": "-1", "scale": "108"
    },
    # 4. Illusion (Kinetic Zoom with 135% scale pop)
    "kinetic_scale": {
        "font": "Montserrat-Black", "size": "68", "primary": "&H00FFFFFF&", "highlight": "&H00FFFFFF&",
        "border": "3", "blur": "0", "shadow": "3", "italic": "0", "scale": "135"
    },
    # 5. Editor Masala (Canary yellow punch on Anton)
    "canary_punch": {
        "font": "Anton", "size": "78", "primary": "&H00FFFFFF&", "highlight": "&H0000E5FF&",
        "border": "4", "blur": "0", "shadow": "3", "italic": "0", "scale": "115"
    },
    # 6. Aura (Editorial Playfair Display with Cyan text)
    "sky_dual": {
        "font": "PlayfairDisplay-BoldItalic", "size": "70", "primary": "&H00FFFFFF&", "highlight": "&H00FFC266&",
        "border": "2", "blur": "4", "shadow": "0", "italic": "-1", "scale": "118"
    },
    # 7. Swiss (Modernist Anton with bright gold accent)
    "modernist_swiss": {
        "font": "Anton", "size": "74", "primary": "&H00FFFFFF&", "highlight": "&H0000D4FF&",
        "border": "4", "blur": "0", "shadow": "3", "italic": "0", "scale": "115"
    },
    # 8. The Big Red (Playfair Display Black with deep red accent)
    "crimson_cinematic": {
        "font": "PlayfairDisplay-Black", "size": "74", "primary": "&H00FFFFFF&", "highlight": "&H003333E6&",
        "border": "2", "blur": "5", "shadow": "0", "italic": "0", "scale": "125"
    },
    # 9. Clean Glow (Soft ambient white diffusion)
    "ambient_white": {
        "font": "Montserrat-Black", "size": "64", "primary": "&H00FFFFFF&", "highlight": "&H00FFFFFF&",
        "border": "2", "blur": "14", "shadow": "0", "italic": "0", "scale": "105"
    }
}
cfg = STYLES.get(style, STYLES["neon_lime"])
print(f"[*] Applying Selected Style Profile: {style.upper()} ({cfg['font']})")

# 4. Computer Vision AI: Auto-Framing & Split-Screen Detector
def analyze_shots_and_faces(video_path):
    """Analyzes video to detect scene cuts and whether shots contain 1 or 2 people."""
    cap = cv2.VideoCapture(video_path)
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30

    face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
    
    frame_idx = 0
    shots = []
    current_shot = {"start": 0, "faces": []}
    prev_gray = None

    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break

        # Check every 6th frame for efficiency
        if frame_idx % 6 == 0:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            
            # Simple scene cut detection
            if prev_gray is not None:
                diff = cv2.absdiff(gray, prev_gray)
                non_zero = np.count_nonzero(diff > 30)
                ratio = non_zero / (w * h)
                if ratio > 0.40: # Camera cut
                    current_shot["end"] = frame_idx / fps
                    shots.append(current_shot)
                    current_shot = {"start": frame_idx / fps, "faces": []}
            prev_gray = gray

            # Detect faces
            detected = face_cascade.detectMultiScale(gray, scaleFactor=1.2, minNeighbors=5, minSize=(60, 60))
            if len(detected) > 0:
                current_shot["faces"].append(detected)

        frame_idx += 1

    current_shot["end"] = frame_idx / fps
    shots.append(current_shot)
    cap.release()
    return w, h, fps, shots

print("[*] Loading Faster-Whisper AI model...")
model = WhisperModel("base.en", device="cpu", compute_type="int8")

# 5. Process Each Selected Clip
for clip_item in clips:
    cid = clip_item.get('id', 1)
    start = clip_item.get('start', '00:04')
    end = clip_item.get('end', '00:35')
    clean_label = clip_item.get('label', f'clip_{cid}').replace(' ', '_').replace(':', '')

    raw_template = f"temp/raw_{cid}.%(ext)s"
    final_raw = f"temp/raw_{cid}.mp4"
    wav_path = f"temp/audio_{cid}.wav"
    ass_file = f"temp/sub_{cid}.ass"
    out_mp4 = f"output/short_{cid}_{clean_label}.mp4"

    print(f"\n==========================================")
    print(f"[*] Slicing Clip #{cid} ({start} -> {end})...")
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
    cmd_dl.extend([url, "-o", raw_template])
    subprocess.run(cmd_dl, check=True)

    downloaded = [f for f in glob.glob(f"temp/raw_{cid}.*") if not f.endswith(".part") and not f.endswith(".ytdl")]
    if not downloaded:
        raise FileNotFoundError(f"Could not find slice file for clip {cid}")
    subprocess.run(["ffmpeg", "-y", "-i", downloaded[0], "-c", "copy", final_raw], check=True)

    # Audio Transcription
    print(f"[*] Transcribing speech for Clip #{cid}...")
    subprocess.run(["ffmpeg", "-y", "-i", final_raw, "-vn", "-ar", "16000", "-ac", "1", wav_path], check=True)
    segments, _ = model.transcribe(wav_path, word_timestamps=True)

    # Build Captik Stacked Phrase Subtitles
    print(f"[*] Generating Captik-tier animated typography for Clip #{cid}...")
    with open(ass_file, "w", encoding="utf-8") as f:
        f.write("[Script Info]\nScriptType: v4.00+\nPlayResX: 1080\nPlayResY: 1920\n\n")
        f.write("[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, OutlineColour, BackColour, Bold, Italic, Alignment, MarginV, Outline, Shadow, BorderStyle\n")
        f.write(f"Style: Default,{cfg['font']},{cfg['size']},{cfg['primary']},&H00000000&,&H80000000&,-1,{cfg['italic']},2,360,{cfg['border']},{cfg['shadow']},1\n\n")
        f.write("[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n")

        # Group words into natural 2-4 word rhythmic phrases
        all_words = []
        for s in segments:
            for w in s.words:
                cleaned = w.word.strip()
                if cleaned:
                    all_words.append({"word": cleaned.upper(), "start": w.start, "end": w.end})

        chunk_size = 3
        for i in range(0, len(all_words), chunk_size):
            chunk = all_words[i:i+chunk_size]
            for target_idx, active_word in enumerate(chunk):
                phrase_parts = []
                for idx, w in enumerate(chunk):
                    if idx == target_idx:
                        # Active pop / kinetic glow
                        phrase_parts.append(f"{{\\c{cfg['highlight']}\\3c{cfg['highlight']}\\blur{cfg['blur']}\\fscx{cfg['scale']}\\fscy{cfg['scale']}}}{w['word']}{{\\c{cfg['primary']}\\3c&H00000000&\\blur0\\fscx100\\fscy100}}")
                    else:
                        phrase_parts.append(w['word'])

                def fmt(sec): return f"0:{int(sec//60):02d}:{sec%60:05.2f}"
                line_text = " ".join(phrase_parts)
                f.write(f"Dialogue: 0,{fmt(active_word['start'])},{fmt(active_word['end'])},Default,,0,0,0,,{line_text}\n")

    # Run AI Auto-Framing & Split Screen
    print(f"[*] Running AI Computer Vision & Shot Detection...")
    vid_w, vid_h, fps, shots = analyze_shots_and_faces(final_raw)

    # Determine if the scene has two people (wide shot) or single speaker
    two_people_detected = False
    for s in shots:
        for f_batch in s["faces"]:
            if len(f_batch) >= 2:
                two_people_detected = True
                break

    if two_people_detected:
        print("[⚡] Wide 2-person shot detected! Rendering Stacked 9:16 Split-Screen (Host Top / Guest Bottom)...")
        filter_str = (
            f"[0:v]split=2[in1][in2]; "
            f"[in1]crop=w=ih*(9/8):h=ih:x=0:y=0,scale=1080:960[top]; "
            f"[in2]crop=w=ih*(9/8):h=ih:x=iw-ih*(9/8):y=0,scale=1080:960[bot]; "
            f"[top][bot]vstack=inputs=2[v_stacked]; "
            f"[v_stacked]subtitles='{ass_file}':fontsdir='fonts'[outv]"
        )
        cmd_render = [
            "ffmpeg", "-y", "-i", final_raw,
            "-filter_complex", filter_str,
            "-map", "[outv]", "-map", "0:a",
            "-c:v", "libx264", "-preset", "fast", "-crf", "22",
            "-c:a", "aac", "-b:a", "128k",
            out_mp4
        ]
    else:
        # Dynamic Speaker Tracking with Automatic Camera Cuts
        user_pos = float(clip_item.get('crop_pos', 0.5))
        crop_w = int(vid_h * (9 / 16))
        print(f"[*] Rendering Single Speaker 9:16 with Center Offset: {int(user_pos * 100)}%...")
        crop_filter = f"crop=ih*(9/16):ih:(iw-ih*(9/16))*{user_pos}:0,scale=1080:1920,subtitles='{ass_file}':fontsdir='fonts'"
        cmd_render = [
            "ffmpeg", "-y", "-i", final_raw,
            "-vf", crop_filter,
            "-c:v", "libx264", "-preset", "fast", "-crf", "22",
            "-c:a", "aac", "-b:a", "128k",
            out_mp4
        ]

    subprocess.run(cmd_render, check=True)
    print(f"[✓] Rendered: {out_mp4}")

print("\n[*] All requested clips finished successfully!")


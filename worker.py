import os
import sys
import glob
import json
import subprocess
import cv2
import numpy as np

print("[*] Starting VERTEX PRO Neural Auto-Framer...")

# 1. Cookies Setup
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

# 2. Parse Payload
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
    clips = [{"id": 1, "start": "00:04", "end": "00:35", "label": "clip_1"}]

os.makedirs('output', exist_ok=True)
os.makedirs('temp', exist_ok=True)
for f in glob.glob("output/*"):
    try: os.remove(f)
    except: pass

# 3. Load YuNet Face Detector
model_path = "models/face_detection_yunet.onnx"
detector = None

def get_face_center_x(frame, w, h):
    global detector
    if detector is None and os.path.exists(model_path):
        detector = cv2.FaceDetectorYN.create(model_path, "", (w, h), score_threshold=0.5)
    
    if detector is not None:
        detector.setInputSize((w, h))
        _, faces = detector.detect(frame)
        if faces is not None and len(faces) > 0:
            # Find largest face (dominant speaker)
            best_face = max(faces, key=lambda f: f[2] * f[3])
            fx, fy, fw, fh = best_face[0:4]
            return int(fx + fw / 2)
    return w // 2

# 4. Shot Detection & Dynamic Speaker Tracking
def detect_shots_and_frame(video_path):
    cap = cv2.VideoCapture(video_path)
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)) or 1920
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) or 1080
    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    duration = max(0.1, total_frames / fps)

    # Detect camera cuts via color histogram difference
    shot_boundaries = [0.0]
    prev_hist = None
    frame_idx = 0

    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break
        if frame_idx % 4 == 0:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            hist = cv2.calcHist([gray], [0], None, [64], [0, 256])
            cv2.normalize(hist, hist)
            if prev_hist is not None:
                correlation = cv2.compareHist(prev_hist, hist, cv2.HISTCMP_CORREL)
                if correlation < 0.62:
                    cut_time = frame_idx / fps
                    if cut_time - shot_boundaries[-1] > 1.0:
                        shot_boundaries.append(cut_time)
            prev_hist = hist
        frame_idx += 1
    shot_boundaries.append(duration)

    crop_w = int(height * (9 / 16))
    max_x = max(0, width - crop_w)
    shots_info = []

    for i in range(len(shot_boundaries) - 1):
        s_start = shot_boundaries[i]
        s_end = shot_boundaries[i + 1]
        mid_sec = (s_start + s_end) / 2
        mid_frame = int(mid_sec * fps)

        cap.set(cv2.CAP_PROP_POS_FRAMES, mid_frame)
        ret, frame = cap.read()
        target_crop_x = (width - crop_w) // 2

        if ret:
            face_x = get_face_center_x(frame, width, height)
            target_crop_x = max(0, min(max_x, face_x - (crop_w // 2)))

        shots_info.append({"start": s_start, "end": s_end, "crop_x": target_crop_x})

    cap.release()
    return width, height, crop_w, shots_info

# 5. Process Each Clip
for clip_item in clips:
    cid = clip_item.get('id', 1)
    start = clip_item.get('start', '00:04')
    end = clip_item.get('end', '00:35')
    clean_label = clip_item.get('label', f'clip_{cid}').replace(' ', '_').replace(':', '')

    dl_output = f"temp/raw_{cid}.%(ext)s"
    out_mp4 = f"output/short_{cid}_{clean_label}.mp4"

    print(f"\n[*] Downloading Clip #{cid} ({start} -> {end})...")
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
        raise FileNotFoundError(f"Could not find download file for clip {cid}")
    source_video = downloaded[0]

    # Run AI Camera-Cut & Speaker Tracking
    print(f"[*] Running Scene-Aware Auto-Framing...")
    vid_w, vid_h, crop_w, shots = detect_shots_and_frame(source_video)

    # Build Multi-Shot FFmpeg Filter (Trimming video + audio together prevents desync)
    v_parts = []
    a_parts = []
    v_tags = ""
    a_tags = ""

    for idx, s in enumerate(shots):
        v_parts.append(
            f"[0:v]trim=start={s['start']:.3f}:end={s['end']:.3f},setpts=PTS-STARTPTS,"
            f"crop={crop_w}:{vid_h}:{s['crop_x']}:0,scale=1080:1920[v{idx}];"
        )
        a_parts.append(
            f"[0:a]atrim=start={s['start']:.3f}:end={s['end']:.3f},asetpts=PTS-STARTPTS[a{idx}];"
        )
        v_tags += f"[v{idx}]"
        a_tags += f"[a{idx}]"

    filter_complex = (
        "".join(v_parts) + "".join(a_parts) +
        f"{v_tags}concat=n={len(shots)}:v=1:a=0[outv];" +
        f"{a_tags}concat=n={len(shots)}:v=0:a=1[outa]"
    )

    print(f"[*] Rendering {len(shots)} framed shots to 9:16 vertical short...")
    cmd_render = [
        "ffmpeg", "-y", "-i", source_video,
        "-filter_complex", filter_complex,
        "-map", "[outv]", "-map", "[outa]",
        "-c:v", "libx264", "-preset", "fast", "-crf", "20",
        "-c:a", "aac", "-b:a", "192k",
        out_mp4
    ]
    subprocess.run(cmd_render, check=True)
    print(f"[✓] Rendered Clean 9:16 Short: {out_mp4}")

print("\n[*] All clips processed successfully with Auto-Framing!")


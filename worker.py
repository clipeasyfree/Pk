import os
import sys
import glob
import json
import subprocess
import cv2
import numpy as np
import mediapipe as mp

print("[*] Starting VERTEX PRO Scene-Aware Auto-Framer...")

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

# 3. Computer Vision: Scene-Cut & Face Tracking Engine
def detect_shots_and_faces(video_path):
    cap = cv2.VideoCapture(video_path)
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)) or 1920
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) or 1080
    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    duration = total_frames / fps

    mp_face = mp.solutions.face_detection.FaceDetection(model_selection=1, min_detection_confidence=0.45)

    # A. Detect Camera Cuts via Color Histogram Shifts
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
                if correlation < 0.60:  # Camera cut threshold
                    cut_time = frame_idx / fps
                    if cut_time - shot_boundaries[-1] > 1.2:  # Min shot length: 1.2s
                        shot_boundaries.append(cut_time)
            prev_hist = hist
        frame_idx += 1
    shot_boundaries.append(duration)

    # B. Track Speaker Center for Each Shot
    crop_w = int(height * (9 / 16))
    max_x = width - crop_w
    shots_info = []

    for i in range(len(shot_boundaries) - 1):
        s_start = shot_boundaries[i]
        s_end = shot_boundaries[i + 1]
        mid_sec = (s_start + s_end) / 2
        mid_frame = int(mid_sec * fps)

        cap.set(cv2.CAP_PROP_POS_FRAMES, mid_frame)
        ret, frame = cap.read()
        target_crop_x = (width - crop_w) // 2  # Default: center

        if ret:
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            results = mp_face.process(rgb)
            if results.detections:
                # Pick largest face in this camera angle
                best_face = max(results.detections, key=lambda d: d.location_data.relative_bounding_box.width * d.location_data.relative_bounding_box.height)
                bbox = best_face.location_data.relative_bounding_box
                face_center_x = int((bbox.xmin + bbox.width / 2) * width)
                target_crop_x = max(0, min(max_x, face_center_x - (crop_w // 2)))

        shots_info.append({"start": s_start, "end": s_end, "crop_x": target_crop_x})

    cap.release()
    mp_face.close()
    return width, height, crop_w, shots_info

# 4. Process Each Clip
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

    # Run AI Auto-Framing Analysis
    print(f"[*] Running Camera-Cut & Speaker Tracking...")
    vid_w, vid_h, crop_w, shots = detect_shots_and_faces(source_video)

    # Build Dynamic Multi-Shot Stitching Filter
    filter_parts = []
    concat_tags = ""
    for idx, s in enumerate(shots):
        tag = f"v{idx}"
        filter_parts.append(
            f"[0:v]trim=start={s['start']:.3f}:end={s['end']:.3f},setpts=PTS-STARTPTS,"
            f"crop={crop_w}:{vid_h}:{s['crop_x']}:0,scale=1080:1920[{tag}];"
        )
        concat_tags += f"[{tag}]"

    filter_complex = "".join(filter_parts) + f"{concat_tags}concat=n={len(shots)}:v=1:a=0[outv]"

    print(f"[*] Rendering {len(shots)} auto-framed shots to 9:16 vertical short...")
    cmd_render = [
        "ffmpeg", "-y", "-i", source_video,
        "-filter_complex", filter_complex,
        "-map", "[outv]", "-map", "0:a",
        "-c:v", "libx264", "-preset", "fast", "-crf", "20",
        "-c:a", "aac", "-b:a", "192k",
        out_mp4
    ]
    subprocess.run(cmd_render, check=True)
    print(f"[✓] Rendered Clean 9:16 Short: {out_mp4}")

print("\n[*] All clips processed successfully with Auto-Framing!")

import os
import sys
import glob
import json
import re
import urllib.request
import subprocess

print("[*] Initializing Autonomous Transcript-Driven AI Clipper...")

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

# 2. Parse Payload
payload_env = os.environ.get('JOB_PAYLOAD', '')
payload = json.loads(payload_env) if payload_env and payload_env != 'null' else {}

url = payload.get('url', '')
campaign_instructions = payload.get('instructions', 'Cold-open viral rules and complete conversational points.')
quality_mode = payload.get('quality', 'balanced').lower()

if not url:
    print("[!] Error: No URL provided.")
    sys.exit(1)

if "youtu.be/" in url:
    url = f"https://www.youtube.com/watch?v={url.split('youtu.be/')[1].split('?')[0]}"
elif "watch?v=" in url:
    url = f"https://www.youtube.com/watch?v={url.split('watch?v=')[1].split('&')[0]}"

os.makedirs('output', exist_ok=True)
os.makedirs('temp', exist_ok=True)
for f in glob.glob("output/*"):
    try: os.remove(f)
    except: pass
for f in glob.glob("temp/*"):
    try: os.remove(f)
    except: pass

# 3. Pull Subtitles / Spoken Words Directly from YouTube
print("\n[*] Fetching spoken word transcript directly from YouTube...")
sub_prefix = "temp/subs"
cmd_sub = [
    "yt-dlp",
    "--skip-download",
    "--write-auto-sub",
    "--write-sub",
    "--sub-lang", "en",
    "--sub-format", "vtt",
    "--extractor-args", "youtube:player_client=web_embedded,mweb,android,ios",
    "-o", sub_prefix,
    url
]
if has_valid_cookies and os.path.exists(cookie_file):
    cmd_sub.extend(["--cookies", cookie_file])

subprocess.run(cmd_sub, stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)

def parse_to_sec(time_str):
    parts = [float(x) for x in time_str.strip().split(':')]
    if len(parts) == 3:
        return parts[0] * 3600 + parts[1] * 60 + parts[2]
    elif len(parts) == 2:
        return parts[0] * 60 + parts[1]
    return parts[0]

vtt_files = glob.glob("temp/subs*.vtt")
transcript_text = []

if vtt_files:
    with open(vtt_files[0], 'r', encoding='utf-8', errors='ignore') as f:
        vtt_raw = f.read()
    pattern = re.compile(r'((?:\d{2}:)?\d{2}:\d{2}\.\d{3})\s*-->\s*((?:\d{2}:)?\d{2}:\d{2}\.\d{3})(?:[^\n]*)\n([\s\S]*?)(?=\n\n|\n(?:\d{2}:)?\d{2}:\d{2}\.\d{3}|\Z)')
    for m in pattern.finditer(vtt_raw):
        s_str, e_str, raw_txt = m.groups()
        clean = re.sub(r'<[^>]+>', '', raw_txt).strip().replace('\n', ' ')
        if clean:
            s_sec = int(parse_to_sec(s_str))
            m_sec = s_sec // 60
            sec_rem = s_sec % 60
            timestamp_fmt = f"{m_sec:02d}:{sec_rem:02d}"
            transcript_text.append(f"[{timestamp_fmt}] {clean}")

full_transcript_str = "\n".join(transcript_text[:1200])
print(f"[✓] Captured {len(transcript_text)} spoken dialogue cues.")

# 4. Feed Transcript to Gemini to Find Genuine Moments
gemini_key = os.environ.get('GEMINI_API_KEY', '').strip()
clips_to_cut = []

if gemini_key and len(full_transcript_str) > 100:
    print("\n[*] Sending genuine spoken transcript to Google Gemini for contextual analysis...")
    ai_prompt = f"""You are an elite video editor. Below is the ACTUAL spoken transcript of the video with timestamps:

TRANSCRIPT:
{full_transcript_str}

CAMPAIGN TONE:
{campaign_instructions}

TASK:
Analyze the actual words spoken above. Identify the 3 to 5 MOST VIRAL, coherent moments in the conversation.
RULES:
1. NEVER cut off speech mid-sentence.
2. The 'start' MUST be when the speaker starts their point.
3. The 'end' MUST be when the speaker completes their thought or punchline.
4. Duration must be between 30 and 70 seconds.
5. Create an authentic hook title based on what they ACTUALLY said.

Return ONLY a JSON array:
[
  {{"id": 1, "title": "Real Hook Title", "start": "MM:SS", "end": "MM:SS"}},
  ...
]"""

    models = ['gemini-2.5-flash', 'gemini-2.0-flash', 'gemini-1.5-flash']
    for m in models:
        try:
            req_data = json.dumps({
                "contents": [{"parts": [{"text": ai_prompt}]}],
                "generationConfig": {"response_mime_type": "application/json"}
            }).encode('utf-8')
            
            req = urllib.request.Request(
                f"https://generativelanguage.googleapis.com/v1beta/models/{m}:generateContent?key={gemini_key}",
                data=req_data,
                headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req) as response:
                res_body = json.loads(response.read().decode('utf-8'))
                raw_json = res_body['candidates'][0]['content']['parts'][0]['text']
                clips_to_cut = json.loads(raw_json)
                print(f"[✓] Gemini ({m}) selected {len(clips_to_cut)} genuine spoken moments!")
                break
        except Exception as e:
            print(f"[!] Model {m} error: {e}")
            continue

if not clips_to_cut:
    print("[!] Falling back to default moment selection.")
    clips_to_cut = [{"id": 1, "title": "Highlight_1", "start": "00:15", "end": "01:00"}]

# 5. Download Master Video Once
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
else:
    ytdl_format = "bv*[height<=1080]+ba/b[height<=1080]/bv*+ba/b/best"
    ffmpeg_crf = "18"
    ffmpeg_preset = "faster"
    audio_br = "192k"

master_file = "temp/master_video.mp4"
print("\n[*] Downloading master video stream once...")
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

# 6. Slice the Real Contextual Moments
print(f"\n[*] Slicing {len(clips_to_cut)} verified conversational moments...")
for idx, clip in enumerate(clips_to_cut, start=1):
    cid = clip.get('id', idx)
    s_sec = max(0.0, parse_to_sec(clip.get('start', '00:00')) - 0.3)
    e_sec = parse_to_sec(clip.get('end', '00:45')) + 0.8
    duration = e_sec - s_sec
    label = re.sub(r'[^a-zA-Z0-9_-]', '_', clip.get('title', f'clip_{cid}'))[:30]

    out_mp4 = f"output/clip_{cid}_{label}.mp4"
    print(f"[{idx}/{len(clips_to_cut)}] Slicing \"{clip.get('title')}\" ({duration:.1f}s)...")

    cmd_slice = [
        "ffmpeg", "-y",
        "-ss", str(s_sec),
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
    print(f"[✓] Saved: {out_mp4}")

print(f"\n[✓] All clips finished based on genuine spoken dialogue!")

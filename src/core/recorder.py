import subprocess
import os
from datetime import datetime
import pytz

def record_stream(username, output_file):
    est = pytz.timezone('US/Eastern')
    now = datetime.now(est)
    os.makedirs(os.path.dirname(output_file), exist_ok=True)

    # ffmpeg command to record livestream
    ffmpeg_cmd = [
        "ffmpeg", "-y",
        "-i", f"https://pull-hls.tiktokcdn.com/stream/{username}.m3u8",
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-s", "854x480",
        "-c:a", "aac",
        output_file
    ]

    print(f"[FFMPEG] Starting recording for {username} to {output_file}...")
    subprocess.run(ffmpeg_cmd)

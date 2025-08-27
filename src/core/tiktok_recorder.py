import os
import subprocess
import time

def record_stream(username, output_path):
    try:
        print(f"[INFO] Starting recording for {username}...")

        if not os.path.exists(output_path):
            os.makedirs(output_path)

        timestamp = time.strftime("%Y-%m-%d_%H-%M-%S")
        filename = f"{username}_{timestamp}.mp4"
        filepath = os.path.join(output_path, filename)

        subprocess.run([
            "python3",
            "TikTokLiveRecorder/src/core/recorder.py",
            "-u", username,
            "--output", filepath
        ])
        print(f"[INFO] Finished recording for {username}. File saved to {filepath}")

    except Exception as e:
        print(f"[ERROR] Recording failed for {username}: {e}")
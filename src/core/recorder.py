import os
import subprocess
import datetime
from src.utils.status_tracker import status_tracker

class Recorder:
    def __init__(self, username, drive_service):
        self.username = username
        self.drive_service = drive_service
        self.recording_process = None

    def start_recording(self, stream_url):
        date_str = datetime.datetime.now().strftime("%Y-%m-%d")
        folder = f"recordings/{self.username}/{date_str}"
        os.makedirs(folder, exist_ok=True)

        index = 1
        while True:
            filename = f"{folder}/{self.username}-{date_str}-{index}.mp4"
            if not os.path.exists(filename):
                break
            index += 1

        command = [
            "ffmpeg", "-y", "-i", stream_url,
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "28",
            "-c:a", "aac", "-b:a", "128k",
            filename
        ]
        self.recording_process = subprocess.Popen(command)
        status_tracker.update(self.username, online=True, recording="YES")

    def stop_recording(self):
        if self.recording_process:
            self.recording_process.terminate()
            self.recording_process = None
        status_tracker.update(self.username, online=False, recording="NO")

    def update_status(self, is_live):
        if is_live:
            if not self.recording_process:
                # Replace with actual TikTok stream URL retrieval
                stream_url = f"https://fake-tiktok-stream/{self.username}.m3u8"
                self.start_recording(stream_url)
        else:
            if self.recording_process:
                self.stop_recording()
            status_tracker.update(self.username, online=False, recording="NO")

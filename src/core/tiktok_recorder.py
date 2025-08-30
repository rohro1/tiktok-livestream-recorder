import subprocess
import threading

class TikTokLiveRecorder:
    def __init__(self, api, resolution="480p"):
        self.api = api
        self.resolution = resolution
        self._thread = None
        self._running = False

    def start_recording(self, out_file):
        self._running = True
        def _record():
            # Replace with actual livestream URL from TikTok API
            url = f"https://example.com/live/{self.api.username}.m3u8"
            cmd = ["ffmpeg", "-y", "-i", url, "-c", "copy", out_file]
            try:
                subprocess.run(cmd)
            except Exception as e:
                print("Recording failed:", e)
            self._running = False

        self._thread = threading.Thread(target=_record, daemon=True)
        self._thread.start()
        return True

    def is_running(self):
        return self._running

    def stop_recording(self):
        # Terminate thread is not safe, use flag in real implementation
        self._running = False

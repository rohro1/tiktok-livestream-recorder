class TikTokRecorder:
    def __init__(self, status_tracker=None):
        self.status_tracker = status_tracker
        self.recording = False
        self.current_username = None
        # ...existing code...
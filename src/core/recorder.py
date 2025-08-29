# src/recorder.py
import time
from TikTokLive import TikTokLiveClient
from TikTokLive.types.events import LiveStart, LiveEnd
from datetime import datetime
from src.utils.status_tracker import status_tracker

class TikTokRecorder:
    def __init__(self, username, tracker):
        self.username = username
        self.tracker = tracker
        self.is_live = False
        self.recording_start = None

    def run(self):
        while True:
            try:
                client = TikTokLiveClient(unique_id=self.username)

                @client.on("live_start")
                async def on_live_start(event: LiveStart):
                    print(f"{self.username} is live!")
                    self.is_live = True
                    self.recording_start = datetime.now()
                    self.tracker.update(
                        self.username,
                        last_online=self.recording_start.strftime("%Y-%m-%d %H:%M:%S"),
                        online=True,
                        live_duration=0,
                        recording_duration=0
                    )

                @client.on("live_end")
                async def on_live_end(event: LiveEnd):
                    print(f"{self.username} ended the livestream.")
                    self.is_live = False
                    end_time = datetime.now()
                    duration = int((end_time - self.recording_start).total_seconds())
                    self.tracker.update(
                        self.username,
                        last_online=end_time.strftime("%Y-%m-%d %H:%M:%S"),
                        online=False,
                        live_duration=duration,
                        recording_duration=duration
                    )

                # periodically update live/recording duration
                async def update_status():
                    while True:
                        if self.is_live and self.recording_start:
                            duration = int((datetime.now() - self.recording_start).total_seconds())
                            self.tracker.update(
                                self.username,
                                online=True,
                                live_duration=duration,
                                recording_duration=duration,
                                last_online=self.recording_start.strftime("%Y-%m-%d %H:%M:%S")
                            )
                        await asyncio.sleep(5)

                import asyncio
                loop = asyncio.get_event_loop()
                loop.create_task(update_status())
                client.run()

            except Exception as e:
                print(f"Error recording {self.username}: {e}")
                time.sleep(60)  # retry in 1 min

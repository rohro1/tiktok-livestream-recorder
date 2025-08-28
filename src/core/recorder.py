import os
import datetime
import ffmpeg
from src.utils.google_drive_uploader import upload_to_drive

def record_livestream(username, url, status_tracker):
    date_str = datetime.datetime.now().strftime("%m-%d-%Y")
    folder_path = os.path.join("recordings", username, date_str)
    os.makedirs(folder_path, exist_ok=True)

    count = len(os.listdir(folder_path)) + 1
    filename = f"{username}-{count}.mp4"
    filepath = os.path.join(folder_path, filename)

    status_tracker.start_recording(username)
    try:
        # Actual recording command using ffmpeg
        (
            ffmpeg
            .input(url)
            .output(filepath, format="mp4", video_bitrate="480k", vcodec="libx264")
            .run(overwrite_output=True)
        )
        upload_to_drive(username, date_str, filepath)
    finally:
        status_tracker.stop_recording(username)

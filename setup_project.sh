#!/bin/bash
# TikTok Livestream Recorder Project Setup
# Run this from your project root

# Create folder structure
mkdir -p src/core
mkdir -p src/utils
mkdir -p templates
mkdir -p recordings

# Create main.py
cat > main.py << 'EOF'
import os
from flask import Flask, redirect, url_for, render_template
from src.utils.oauth_drive import GoogleDriveOAuth
from src.utils.status_tracker import StatusTracker
from src.core.tiktok_recorder import TikTokRecorderWorker
import threading

app = Flask(__name__, template_folder=os.path.join(os.path.dirname(__file__), 'templates'))
app.secret_key = "super-secret-key"

drive_oauth = GoogleDriveOAuth()
status_tracker = StatusTracker()

recorder_worker = TikTokRecorderWorker(status_tracker=status_tracker)
threading.Thread(target=recorder_worker.start, daemon=True).start()

@app.route("/")
def home():
    drive_connected = drive_oauth.is_authenticated()
    return f"✅ TikTok Recorder running. Drive connected: {drive_connected}. <a href='/authorize'>Connect Google Drive</a> | <a href='/disconnect'>Disconnect</a>"

@app.route("/authorize")
def authorize():
    return redirect(drive_oauth.get_authorize_url())

@app.route("/oauth2callback")
def oauth2callback():
    if drive_oauth.fetch_token():
        return redirect(url_for("status"))
    return "OAuth failed. Try again."

@app.route("/disconnect")
def disconnect():
    drive_oauth.disconnect()
    return redirect(url_for("home"))

@app.route("/status")
def status():
    status_data = status_tracker.get_all_status()
    return render_template("status.html", status_data=status_data)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
EOF

# Create a simple status.html
cat > templates/status.html << 'EOF'
<!DOCTYPE html>
<html>
<head><title>TikTok Live Status</title></head>
<body>
<h1>TikTok Live Status</h1>
<table border="1">
<tr><th>Username</th><th>Online</th><th>Recording</th><th>Last Online</th></tr>
{% for username, data in status_data.items() %}
<tr>
<td>{{ username }}</td>
<td>{{ data.online }}</td>
<td>{{ data.recording }}</td>
<td>{{ data.last_online }}</td>
</tr>
{% endfor %}
</table>
</body>
</html>
EOF

# Create __init__.py files
touch src/__init__.py
touch src/core/__init__.py
touch src/utils/__init__.py

# Add placeholder core files
touch src/core/recorder.py
touch src/core/tiktok_api.py
touch src/core/tiktok_recorder.py

# Add placeholder utils files
touch src/utils/folder_manager.py
touch src/utils/google_drive_uploader.py
touch src/utils/oauth_drive.py
touch src/utils/status_tracker.py

# Create requirements.txt
cat > requirements.txt << 'EOF'
Flask==2.3.3
google-auth==2.22.0
google-auth-oauthlib==1.0.0
google-api-python-client==2.100.0
requests==2.34.0
pytz==2025.8
ffmpeg-python==0.2.0
EOF

echo "✅ Project structure created. Place your actual recorder and OAuth code in src/core and src/utils."

from flask import Flask, request, redirect, render_template_string
from src.utils.oauth_drive import fetch_and_store_credentials, get_drive_service
from src.utils.status_tracker import get_all_statuses

app = Flask(__name__)

CREDENTIALS_FILE = "credentials.json"
SCOPES = ["https://www.googleapis.com/auth/drive"]
REDIRECT_URI = "https://tiktok-livestream-recorder.onrender.com/oauth2callback"

# Homepage
@app.route("/")
def index():
    auth_url = f"https://accounts.google.com/o/oauth2/auth?client_id=<YOUR_CLIENT_ID>&redirect_uri={REDIRECT_URI}&scope={' '.join(SCOPES)}&response_type=code&access_type=offline&prompt=consent"
    return f'<h2>Authorize Google Drive Access</h2><a href="{auth_url}">Click here to authorize</a>'

# OAuth callback route
@app.route("/oauth2callback")
def oauth2callback():
    request_url = request.url
    fetch_and_store_credentials(
        credentials_file=CREDENTIALS_FILE,
        scopes=SCOPES,
        redirect_uri=REDIRECT_URI,
        request_url=request_url
    )
    # After successful auth, redirect to status page
    return redirect("/status")

# Status page
@app.route("/status")
def status():
    all_statuses = get_all_statuses()
    html = "<h1>TikTok Livestream Status</h1>"
    if not all_statuses:
        html += "<p>No data yet.</p>"
    else:
        html += "<table border='1' cellpadding='5'><tr><th>Username</th><th>Online</th><th>Current Duration (s)</th><th>Last Online</th></tr>"
        for user, info in all_statuses.items():
            html += f"<tr><td>{user}</td><td>{info['online']}</td><td>{info['current_duration']}</td><td>{info['last_online']}</td></tr>"
        html += "</table>"
    return render_template_string(html)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))

🚀 Complete Deployment Guide
Quick Start Checklist
 Google Cloud Project with Drive API enabled
 OAuth2 credentials downloaded
 GitHub repository set up
 Render account created
 Environment variables configured
 TikTok usernames added
🔧 Detailed Setup
1. Google Cloud Configuration
Create Google Cloud Project
Go to Google Cloud Console
Click "New Project" or select existing project
Note your Project ID
Enable Google Drive API
bash
# Via Google Cloud Console:
# 1. Go to "APIs & Services" > "Library"
# 2. Search "Google Drive API"
# 3. Click "Enable"
Create OAuth2 Credentials
Go to "APIs & Services" > "Credentials"
Click "Create Credentials" > "OAuth client ID"
If prompted, configure OAuth consent screen first:
User Type: External
App name: TikTok Livestream Recorder
User support email: your email
Developer contact: your email
Create OAuth client ID:
Application type: Web application
Name: TikTok Recorder
Authorized redirect URIs: https://your-app-name.onrender.com/auth/callback
Download credentials as JSON
2. Repository Setup
Fork or Clone
bash
git clone https://github.com/rohro1/tiktok-livestream-recorder.git
cd tiktok-livestream-recorder
Configure Usernames
Edit usernames.txt:

username1
username2
username3
Test Locally (Optional)
bash
# Install dependencies
pip install -r requirements.txt

# Set environment variables
export GOOGLE_CREDENTIALS_JSON='{"web":{"client_id":"..."}}'
export SECRET_KEY="your-secret-key"
export OAUTH_REDIRECT_URI="http://localhost:8000/auth/callback"

# Run locally
python main.py
3. Render Deployment
Create Web Service
Go to Render Dashboard
Click "New" > "Web Service"
Connect your GitHub repository
Configure settings:
Service Details:

Name: tiktok-livestream-recorder
Region: Choose closest to you
Branch: main
Runtime: Python 3
Build & Deploy:

Build Command: pip install -r requirements.txt
Start Command: gunicorn main:app --workers 1 --bind 0.0.0.0:$PORT --timeout 300
Environment Variables
Add these in Render dashboard:

Key	Value	Notes
GOOGLE_CREDENTIALS_JSON	{"web":{"client_id":"...","client_secret":"...","auth_uri":"https://accounts.google.com/o/oauth2/auth","token_uri":"https://oauth2.googleapis.com/token","redirect_uris":["https://your-app.onrender.com/auth/callback"]}}	Paste entire credentials.json content
SECRET_KEY	Generate random string	Use: python -c "import secrets; print(secrets.token_hex(32))"
OAUTH_REDIRECT_URI	https://your-app-name.onrender.com/auth/callback	Replace with your actual Render URL
Deploy
Click "Create Web Service"
Wait for deployment to complete
Note your app URL: https://your-app-name.onrender.com
4. Post-Deployment Setup
Update OAuth Redirect URI
Go back to Google Cloud Console
Edit your OAuth client ID
Update redirect URI to match your Render URL
Save changes
Authorize Google Drive
Visit your deployed app
Click "Setup Google Drive"
Complete OAuth flow
Grant Drive permissions
Start Monitoring
Go to dashboard
Click "Start Monitoring"
Verify users are being checked
🔍 Verification Steps
Check Deployment
bash
# Test health endpoint
curl https://your-app-name.onrender.com/health

# Expected response:
{
  "status": "healthy",
  "timestamp": "2025-08-30T...",
  "monitoring_active": true,
  "active_recordings": 0
}
Test Recording
Add a username that frequently goes live
Wait for them to start streaming
Check dashboard for recording status
Verify file appears in Google Drive
Monitor Logs
Check Render logs for:

Successful startup
User monitoring activity
Recording events
Upload confirmations
🐛 Common Issues & Solutions
Issue: "Module not found" errors
Solution: Ensure all init.py files are present and src/ directory structure is correct

Issue: "Google credentials invalid"
Solution:

Verify credentials.json format
Check environment variable is set correctly
Ensure OAuth client is configured for web application
Issue: "Recording fails immediately"
Solution:

Check if user is actually live
Verify ffmpeg is available
Check network connectivity
Review TikTok rate limiting
Issue: "Drive upload fails"
Solution:

Re-authorize Google Drive access
Check Drive storage quota
Verify internet connectivity
Check file permissions
Issue: "App sleeps on Render free tier"
Solution:

This is normal behavior after 15 minutes of inactivity
App will wake up on next request
Consider upgrading to paid plan for 24/7 operation
📊 Monitoring & Maintenance
Health Monitoring
bash
# Check app status
curl https://your-app-name.onrender.com/api/status

# Monitor logs
# View in Render dashboard under "Logs" tab
Regular Maintenance
Check Google Drive storage usage
Review and update usernames list
Monitor Render resource usage
Check for failed recordings
Backup Configuration
Keep backup of credentials.json
Document environment variables
Save usernames.txt regularly
🔄 Updates & Scaling
Updating Code
Push changes to GitHub
Render auto-deploys from main branch
Monitor deployment logs
Test functionality after deployment
Scaling Considerations
Free tier: 1 worker, limited resources
Paid tier: Multiple workers, more resources
Consider external worker processes for heavy recording
📞 Support
Debugging Steps
Check Render deployment logs
Verify environment variables
Test Google Drive connection
Check TikTok username validity
Monitor resource usage
Log Analysis
Key log messages to look for:

"Monitoring started" - System is active
"Found live stream for {username}" - Detection working
"Recording completed" - Successful recording
"Uploaded to Drive" - Backup successful
🎯 Production Tips
Resource Management: Clean up old recordings regularly
Error Handling: Monitor failed recordings and retry logic
Rate Limiting: Respect TikTok's rate limits
Storage: Monitor Google Drive quota usage
Monitoring: Set up external monitoring for uptime
Your TikTok Livestream Recorder should now be fully operational! 🎉


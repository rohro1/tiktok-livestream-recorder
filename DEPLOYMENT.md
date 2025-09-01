# 🚀 TikTok Livestream Recorder - Fixed Deployment Guide

## 🔧 Quick Fix for OAuth Error

The "redirect_uri_mismatch" error occurs because your Google OAuth credentials are configured for the wrong callback URL. Here's how to fix it:

### 1. Update Google Cloud Console

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Navigate to "APIs & Services" > "Credentials"
3. Find your OAuth 2.0 Client ID
4. Click "Edit"
5. Under "Authorized redirect URIs", **replace** the existing URI with:
   ```
   https://tiktok-livestream-recorder.onrender.com/oauth2callback
   ```
   ⚠️ **Note**: Changed from `/auth/callback` to `/oauth2callback`
6. Click "Save"

### 2. Update Environment Variables

In your Render dashboard, update these environment variables:

```bash
OAUTH_REDIRECT_URI=https://tiktok-livestream-recorder.onrender.com/oauth2callback
```

## 🆕 Key Fixes Applied

### ✅ OAuth Redirect URI Fixed
- Changed callback endpoint from `/auth/callback` to `/oauth2callback`
- Added auto-detection of deployment URL
- Enhanced error handling for OAuth flow

### ✅ Enhanced TikTok Live Detection
- **Removed broken API endpoint** (`/api/live/detail/`)
- Added **4 new detection methods**:
  1. Profile page HTML analysis with regex patterns
  2. Direct live URL access checking
  3. Mobile API approach for different responses
  4. yt-dlp verification as fallback
- Improved reliability with multiple fallback methods

### ✅ Auto-Start Features
- Monitoring starts automatically after Google Drive authorization
- Folder structure created automatically for all users
- Real-time username updates in dashboard

### ✅ Enhanced User Management
- Auto-save usernames to file when added via web interface
- Remove users functionality with automatic cleanup
- Live preview of monitored users on authorization page

## 🚀 Complete Deployment Steps

### 1. Google Cloud Setup

#### Create OAuth Credentials
1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create new project or select existing
3. Enable Google Drive API
4. Go to "APIs & Services" > "Credentials"
5. Click "Create Credentials" > "OAuth client ID"
6. Configure OAuth consent screen (if needed)
7. Create OAuth client ID:
   - **Application type**: Web application
   - **Name**: TikTok Livestream Recorder
   - **Authorized redirect URIs**: `https://YOUR-APP-NAME.onrender.com/oauth2callback`
8. Download credentials JSON

### 2. Render Deployment

#### Create Web Service
1. Go to [Render Dashboard](https://dashboard.render.com/)
2. Click "New" > "Web Service"
3. Connect your GitHub repository
4. Configure:
   - **Name**: `tiktok-livestream-recorder`
   - **Region**: Choose closest to you
   - **Branch**: `main`
   - **Runtime**: Python 3
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `gunicorn main:app --workers 1 --bind 0.0.0.0:$PORT --timeout 300`

#### Environment Variables
Add these in Render dashboard:

| Variable | Value | Notes |
|----------|-------|-------|
| `GOOGLE_CREDENTIALS_JSON` | `{"web":{"client_id":"...","client_secret":"...","auth_uri":"https://accounts.google.com/o/oauth2/auth","token_uri":"https://oauth2.googleapis.com/token","redirect_uris":["https://YOUR-APP.onrender.com/oauth2callback"]}}` | Your complete credentials.json content |
| `SECRET_KEY` | `your-random-secret-key` | Generate with: `python -c "import secrets; print(secrets.token_hex(32))"` |
| `OAUTH_REDIRECT_URI` | `https://YOUR-APP.onrender.com/oauth2callback` | Must match Google Cloud setting |

### 3. Post-Deployment Setup

#### Run Setup Script
After deployment, the app will automatically run the setup configuration. You can also run it manually:

```bash
python deployment_setup.py
```

#### Add Users and Authorize
1. Visit your deployed app URL
2. Add TikTok usernames on the homepage
3. Click "Setup Google Drive & Start Monitoring"
4. Complete Google OAuth authorization
5. Monitoring will start automatically

## 🔧 Advanced Configuration

### Auto-Commit Schedule
The system automatically commits changes every 30 minutes. To modify:

```yaml
# In .github/workflows/auto_commit.yml
schedule:
  - cron: '*/15 * * * *'  # Every 15 minutes
```

### Recording Quality Settings
Modify in `main.py` > `StreamRecorder` class:

```python
ydl_opts = {
    'format': 'best[height<=1080]/best',  # Change from 720p to 1080p
    # ... other options
}
```

### Monitoring Intervals
Adjust in `main.py` > `monitoring_loop()`:

```python
check_interval = 20  # seconds between full cycles (default: 30)
user_check_interval = 2  # seconds between users (default: 3)
```

## 🐛 Troubleshooting

### OAuth Issues
**Error**: `redirect_uri_mismatch`
**Solution**: 
1. Verify redirect URI in Google Cloud Console matches exactly: `https://your-app.onrender.com/oauth2callback`
2. Update `OAUTH_REDIRECT_URI` environment variable in Render
3. Redeploy the application

**Error**: `invalid_client`
**Solution**: Check that `GOOGLE_CREDENTIALS_JSON` is properly formatted and contains all required fields

### Live Detection Issues
**Problem**: Not detecting live streams
**Solution**: The new detection system uses multiple methods. Check logs for specific detection method results:
- Profile page analysis
- Direct live URL checking
- Mobile API approach
- yt-dlp verification

### Recording Issues
**Problem**: Recordings fail or are empty
**Solution**: 
1. Verify ffmpeg is available (pre-installed on Render)
2. Check if user is actually live when recording starts
3. Review yt-dlp error logs
4. Ensure sufficient disk space

### Drive Upload Issues
**Problem**: Files not uploading to Drive
**Solution**:
1. Re-authorize Google Drive access
2. Check Drive storage quota
3. Verify internet connectivity
4. Check file permissions

## 📊 Monitoring & Maintenance

### Health Monitoring
```bash
# Check app status
curl https://your-app.onrender.com/health

# Expected response:
{
  "status": "healthy",
  "timestamp": "2025-09-01T...",
  "monitoring_active": true,
  "active_recordings": 0,
  "drive_connected": true,
  "usernames_count": 3
}
```

### Dashboard Features
- **Real-time status updates**: Auto-refreshes every 30 seconds
- **Live indicators**: Visual indicators for live users
- **Recording status**: Shows active recordings
- **User management**: Add/remove users via web interface
- **Drive integration**: Direct links to uploaded videos

### Log Analysis
Key log messages to monitor:
- `"Monitoring started"` - System is active
- `"✅ Profile Analysis: {username} is LIVE!"` - Live detection working
- `"🎬 Started recording {username}"` - Recording initiated
- `"📁 Uploaded {filename} to Google Drive"` - Upload successful

## 🔄 Automated Features

### What Happens Automatically:
1. **After Google authorization**:
   - Monitoring starts immediately
   - Folder structure created in Google Drive for all users
   - Auto-commit system activates

2. **During monitoring**:
   - Users checked every 30 seconds
   - Live streams detected and recorded automatically
   - Files uploaded to Drive and local copies removed
   - Status updates in real-time dashboard

3. **Background processes**:
   - Auto-commit every 30 minutes
   - Folder organization by user and month
   - Error recovery and retry logic

## 🎯 Production Tips

### Resource Optimization
- **Render Free Tier**: App sleeps after 15 minutes of inactivity
- **Storage**: Local recordings are deleted after Drive upload
- **Memory**: Uses threading for concurrent recordings
- **CPU**: Optimized for minimal resource usage

### Scaling Considerations
- **Multiple users**: System handles concurrent recordings
- **Long streams**: Uses chunked upload for large files
- **Rate limiting**: Built-in delays between API calls
- **Error recovery**: Automatic retry logic for failed operations

Your TikTok Livestream Recorder is now fully configured with enhanced detection methods and auto-start functionality! 🎉

## 🔄 Migration from Old Version

If you're updating from the previous version:

1. **Update OAuth redirect URI** in Google Cloud Console
2. **Update environment variables** in Render dashboard
3. **Redeploy** the application
4. **Re-authorize** Google Drive access
5. **Test live detection** with known active streamers

The new system is much more reliable and will automatically handle user management and folder creation!

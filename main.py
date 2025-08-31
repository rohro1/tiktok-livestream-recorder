#!/usr/bin/env python3
"""
TikTok Livestream Recorder - Main Flask Application
Compatible with Render Free Tier
"""

import os
import json
import threading
import time
from datetime import datetime, timedelta
from flask import Flask, render_template, jsonify, request, redirect, url_for, session
import logging
from src.core.tiktok_recorder import TikTokRecorder
from src.utils.status_tracker import StatusTracker
from src.utils.google_drive_uploader import GoogleDriveUploader
from src.utils.oauth_drive import DriveOAuth

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'your-secret-key-change-this')

# Global instances
status_tracker = StatusTracker()
recorder = TikTokRecorder(status_tracker)
oauth_helper = DriveOAuth()
drive_uploader = None

# Global state
recording_threads = {}
monitoring_active = False

def load_usernames():
    """Load usernames from file"""
    try:
        with open('usernames.txt', 'r') as f:
            usernames = [line.strip() for line in f if line.strip()]
        logger.info(f"Loaded {len(usernames)} usernames")
        return usernames
    except FileNotFoundError:
        logger.warning("usernames.txt not found, creating empty file")
        with open('usernames.txt', 'w') as f:
            f.write("")
        return []

def monitoring_loop():
    """Main monitoring loop that runs in background"""
    global monitoring_active
    monitoring_active = True
    
    while monitoring_active:
        try:
            usernames = load_usernames()
            
            for username in usernames:
                if not monitoring_active:
                    break
                    
                try:
                    # Check if user is live
                    is_live = recorder.is_user_live(username)
                    
                    # Update last checked time
                    status_tracker.update_user_status(
                        username, 
                        is_live=is_live,
                        last_check=datetime.now()
                    )
                    
                    if is_live and username not in recording_threads:
                        # Start recording
                        logger.info(f"Starting recording for {username}")
                        thread = threading.Thread(
                            target=record_user_stream,
                            args=(username,),
                            daemon=True
                        )
                        thread.start()
                        recording_threads[username] = thread
                        
                    elif not is_live and username in recording_threads:
                        # User went offline, recording will stop automatically
                        logger.info(f"User {username} went offline")
                        
                except Exception as e:
                    logger.error(f"Error checking {username}: {e}")
                    
                time.sleep(2)  # Small delay between users
                
            # Wait 30 seconds before next check cycle
            time.sleep(30)
            
        except Exception as e:
            logger.error(f"Error in monitoring loop: {e}")
            time.sleep(60)  # Wait longer on error

def record_user_stream(username):
    """Record a user's livestream"""
    try:
        # Start recording
        output_file = recorder.record_stream(username)
        
        if output_file and os.path.exists(output_file):
            logger.info(f"Recording completed for {username}: {output_file}")
            
            # Upload to Google Drive if configured
            global drive_uploader
            if drive_uploader:
                try:
                    drive_url = drive_uploader.upload_video(output_file, username)
                    if drive_url:
                        status_tracker.update_user_status(
                            username,
                            last_recording=output_file,
                            drive_link=drive_url
                        )
                        logger.info(f"Uploaded {username}'s recording to Drive: {drive_url}")
                    else:
                        logger.error(f"Failed to upload {username}'s recording to Drive")
                except Exception as e:
                    logger.error(f"Drive upload error for {username}: {e}")
        else:
            logger.error(f"Recording failed for {username}")
            
    except Exception as e:
        logger.error(f"Error recording {username}: {e}")
    finally:
        # Remove from active recordings
        if username in recording_threads:
            del recording_threads[username]

@app.route('/')
def home():
    """Home page redirect to status"""
    return redirect(url_for('status'))

@app.route('/status')
def status():
    """Main dashboard showing user statuses"""
    usernames = load_usernames()
    user_statuses = []
    
    for username in usernames:
        user_data = status_tracker.get_user_status(username)
        user_data['username'] = username
        user_data['is_recording'] = username in recording_threads
        user_statuses.append(user_data)
    
    return render_template('status.html', 
                         users=user_statuses, 
                         monitoring_active=monitoring_active)

@app.route('/api/status')
def api_status():
    """API endpoint for status data"""
    usernames = load_usernames()
    user_statuses = []
    
    for username in usernames:
        user_data = status_tracker.get_user_status(username)
        user_data['username'] = username
        user_data['is_recording'] = username in recording_threads
        user_statuses.append(user_data)
    
    return jsonify({
        'users': user_statuses,
        'monitoring_active': monitoring_active,
        'total_users': len(usernames),
        'active_recordings': len(recording_threads)
    })

@app.route('/authorize')
def authorize():
    """Google Drive authorization page"""
    return render_template('authorize.html')

@app.route('/auth/google')
def auth_google():
    """Start Google OAuth flow"""
    try:
        auth_url = oauth_helper.get_authorization_url()
        return redirect(auth_url)
    except Exception as e:
        logger.error(f"OAuth error: {e}")
        return f"Authorization error: {e}", 500

@app.route('/auth/callback')
def auth_callback():
    """Handle Google OAuth callback"""
    try:
        code = request.args.get('code')
        if not code:
            return "No authorization code received", 400
        
        # Exchange code for credentials
        creds = oauth_helper.handle_callback(code)
        
        if creds:
            # Initialize Drive uploader
            global drive_uploader
            drive_uploader = GoogleDriveUploader(creds)
            session['drive_authorized'] = True
            logger.info("Google Drive authorization successful")
            return redirect(url_for('status'))
        else:
            return "Authorization failed", 400
            
    except Exception as e:
        logger.error(f"Callback error: {e}")
        return f"Callback error: {e}", 500

@app.route('/start_monitoring', methods=['POST'])
def start_monitoring():
    """Start the monitoring system"""
    global monitoring_active
    
    if not monitoring_active:
        thread = threading.Thread(target=monitoring_loop, daemon=True)
        thread.start()
        logger.info("Monitoring started")
    
    return jsonify({'success': True, 'monitoring_active': True})

@app.route('/stop_monitoring', methods=['POST'])
def stop_monitoring():
    """Stop the monitoring system"""
    global monitoring_active
    monitoring_active = False
    logger.info("Monitoring stopped")
    
    return jsonify({'success': True, 'monitoring_active': False})

@app.route('/health')
def health():
    """Health check endpoint for Render"""
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat(),
        'monitoring_active': monitoring_active,
        'active_recordings': len(recording_threads)
    })

if __name__ == '__main__':
    # Create required directories
    os.makedirs('recordings', exist_ok=True)
    os.makedirs('logs', exist_ok=True)
    
    # Load existing credentials if available
    try:
        if os.path.exists('credentials.json'):
            creds = oauth_helper.load_credentials()
            if creds and creds.valid:
                drive_uploader = GoogleDriveUploader(creds)
                logger.info("Loaded existing Google Drive credentials")
    except Exception as e:
        logger.warning(f"Could not load existing credentials: {e}")
    
    # Auto-start monitoring if usernames exist
    usernames = load_usernames()
    if usernames and not monitoring_active:
        thread = threading.Thread(target=monitoring_loop, daemon=True)
        thread.start()
        logger.info("Auto-started monitoring")
    
    # Run Flask app
    port = int(os.environ.get('PORT', 8000))
    app.run(host='0.0.0.0', port=port, debug=False)
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

# Initialize components
status_tracker = StatusTracker()
recorder = TikTokRecorder(status_tracker)  # This will now work correctly
oauth_helper = DriveOAuth()

# Global instances
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
    logger.info("Starting monitoring loop")
    
    while monitoring_active:
        try:
            usernames = load_usernames()
            
            if not usernames:
                logger.warning("No usernames to monitor")
                time.sleep(60)
                continue
            
            for username in usernames:
                if not monitoring_active:
                    break
                    
                try:
                    # Check if user is live using reliable method
                    is_live = recorder.is_user_live(username)
                    
                    # Update last checked time
                    status_tracker.update_user_status(
                        username, 
                        is_live=is_live,
                        last_check=datetime.now()
                    )
                    
                    if is_live:
                        # Only start recording if not already recording
                        if username not in recording_threads:
                            logger.info(f"Starting recording for {username}")
                            thread = threading.Thread(
                                target=record_user_stream,
                                args=(username,),
                                daemon=True
                            )
                            thread.start()
                            recording_threads[username] = thread
                        else:
                            logger.debug(f"Already recording {username}")
                    else:
                        # User is offline
                        if username in recording_threads:
                            logger.info(f"User {username} went offline")
                        
                except Exception as e:
                    logger.error(f"Error checking {username}: {e}")
                    # Mark as offline on error
                    status_tracker.update_user_status(
                        username, 
                        is_live=False,
                        last_check=datetime.now()
                    )
                    
                time.sleep(3)  # Delay between users to avoid rate limiting
                
            # Wait 45 seconds before next check cycle (longer to be more respectful)
            logger.debug(f"Monitoring cycle complete. Active recordings: {len(recording_threads)}")
            time.sleep(45)
            
        except Exception as e:
            logger.error(f"Error in monitoring loop: {e}")
            time.sleep(120)  # Wait longer on error

def record_user_stream(username):
    """Record a user's livestream"""
    try:
        # Double-check if user is still live before recording
        if not recorder.is_user_live(username):
            logger.warning(f"User {username} is no longer live, skipping recording")
            return
        
        # Start recording
        output_file = recorder.record_stream(username)
        
        if output_file and os.path.exists(output_file):
            # Check if file has actual content (> 1MB)
            file_size = os.path.getsize(output_file)
            if file_size > 1024 * 1024:  # 1MB minimum
                logger.info(f"Recording completed for {username}: {output_file} ({file_size} bytes)")
                
                # Upload to Google Drive if configured
                global drive_uploader
                if drive_uploader:
                    try:
                        drive_url = drive_uploader.upload_video(output_file, username)
                        if drive_url:
                            status_tracker.update_user_status(
                                username,
                                last_recording=output_file,
                                drive_link=drive_url,
                                recording_end=datetime.now()
                            )
                            logger.info(f"Uploaded {username}'s recording to Drive: {drive_url}")
                            
                            # Remove local file after successful upload
                            try:
                                os.remove(output_file)
                                logger.info(f"Cleaned up local file: {output_file}")
                            except Exception as e:
                                logger.warning(f"Could not remove local file: {e}")
                        else:
                            logger.error(f"Failed to upload {username}'s recording to Drive")
                    except Exception as e:
                        logger.error(f"Drive upload error for {username}: {e}")
                else:
                    logger.info(f"No Drive uploader configured, keeping local: {output_file}")
                    status_tracker.update_user_status(
                        username,
                        last_recording=output_file,
                        recording_end=datetime.now()
                    )
            else:
                logger.warning(f"Recording too small for {username}, removing: {file_size} bytes")
                try:
                    os.remove(output_file)
                except Exception:
                    pass
        else:
            logger.error(f"Recording failed for {username}")
            
    except Exception as e:
        logger.error(f"Error recording {username}: {e}")
    finally:
        # Always remove from active recordings
        if username in recording_threads:
            del recording_threads[username]
        
        # Update status to not recording
        status_tracker.update_user_status(
            username,
            is_live=False,
            recording_end=datetime.now()
        )

@app.route('/')
def home():
    """Home page redirect to status"""
    return redirect(url_for('status'))

@app.route('/status')
def status():
    """Main dashboard showing user statuses"""
    usernames = load_usernames()
    user_statuses = {}
    
    for username in usernames:
        user_data = status_tracker.get_user_status(username)
        user_data['username'] = username
        user_data['is_recording'] = username in recording_threads
        # Ensure boolean values are properly set
        user_data['is_live'] = bool(user_data.get('is_live', False))
        user_statuses[username] = user_data
    
    return render_template('status.html', 
                         users=user_statuses, 
                         monitoring_active=monitoring_active,
                         now=datetime.now())  # Add current time for duration calculations

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

@app.route('/oauth2callback')
def oauth2callback():
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

@app.route('/start_monitoring', methods=['GET', 'POST'])
def start_monitoring():
    """Start the monitoring system"""
    global monitoring_active
    
    if request.method == 'POST':
        if not monitoring_active:
            thread = threading.Thread(target=monitoring_loop, daemon=True)
            thread.start()
            monitoring_active = True
            logger.info("Monitoring started")
        return jsonify({'success': True, 'monitoring_active': True})
    
    return jsonify({'monitoring_active': monitoring_active})

@app.route('/test_google_drive')
def test_google_drive():
    """Test Google Drive connection"""
    if not drive_uploader:
        return jsonify({
            'status': 'error',
            'message': 'Google Drive not configured. Please authorize first.'
        }), 400
    
    try:
        drive_uploader.test_connection()
        return jsonify({
            'status': 'success',
            'message': 'Drive connection successful'
        })
    except Exception as e:
        logger.error(f"Drive test failed: {e}")
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

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
        creds = oauth_helper.load_credentials()
        if creds and creds.valid:
            drive_uploader = GoogleDriveUploader(creds)
            logger.info("Loaded existing Google Drive credentials")
    except Exception as e:
        logger.warning(f"Could not load existing credentials: {e}")
    
    # Don't auto-start monitoring - let user control it
    logger.info("Application ready - visit /status to start monitoring")
    
    # Run Flask app
    port = int(os.environ.get('PORT', 8000))
    app.run(host='0.0.0.0', port=port, debug=False)
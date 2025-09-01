#!/usr/bin/env python3
"""
TikTok Livestream Recorder - Main Flask Application
Compatible with Render Free Tier
"""

import os
import json
import threading
import time
import subprocess
from datetime import datetime, timedelta
from flask import Flask, render_template, jsonify, request, redirect, url_for, session
import logging
import yt_dlp
from functools import lru_cache

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'your-secret-key-change-this')

# Global state
recording_threads = {}
monitoring_active = False
status_tracker = {}
drive_uploader = None

class SimpleStatusTracker:
    def __init__(self):
        self.status = {}
        self.lock = threading.Lock()
    
    def update_user_status(self, username, **kwargs):
        with self.lock:
            if username not in self.status:
                self.status[username] = {}
            self.status[username].update(kwargs)
            self.status[username]['last_updated'] = datetime.now().isoformat()
    
    def get_user_status(self, username):
        with self.lock:
            return self.status.get(username, {})
    
    def get_all_statuses(self):
        with self.lock:
            return self.status.copy()

class TikTokRecorder:
    def __init__(self):
        self.recording_processes = {}
        
    def is_user_live(self, username):
        """Check if user is live using yt-dlp"""
        try:
            url = f"https://www.tiktok.com/@{username}/live"
            
            # Use yt-dlp to check if live
            ydl_opts = {
                'quiet': True,
                'no_warnings': True,
                'extract_flat': True,
            }
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                try:
                    info = ydl.extract_info(url, download=False)
                    return info is not None and info.get('is_live', False)
                except:
                    return False
                    
        except Exception as e:
            logger.error(f"Error checking if {username} is live: {e}")
            return False
    
    def record_stream(self, username):
        """Record a livestream"""
        try:
            # Create output directory
            output_dir = os.path.join('recordings', username)
            os.makedirs(output_dir, exist_ok=True)
            
            # Generate filename
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            output_file = os.path.join(output_dir, f'{username}_{timestamp}.mp4')
            
            # Use yt-dlp to download
            url = f"https://www.tiktok.com/@{username}/live"
            
            ydl_opts = {
                'outtmpl': output_file,
                'format': 'best',
                'quiet': False,
                'no_warnings': False,
            }
            
            logger.info(f"Starting recording for {username}")
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
            
            logger.info(f"Recording completed for {username}: {output_file}")
            
            # Check if file was created and has content
            if os.path.exists(output_file) and os.path.getsize(output_file) > 1024:
                return output_file
            else:
                if os.path.exists(output_file):
                    os.remove(output_file)
                return None
                
        except Exception as e:
            logger.error(f"Error recording {username}: {e}")
            return None

# Initialize components
status_tracker = SimpleStatusTracker()
recorder = TikTokRecorder()

def load_usernames():
    """Load usernames from file"""
    try:
        with open('usernames.txt', 'r') as f:
            usernames = [line.strip() for line in f if line.strip() and not line.startswith('#')]
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
                time.sleep(30)
                continue

            # Check all users
            for username in usernames:
                if not monitoring_active:
                    break
                
                try:
                    is_live = recorder.is_user_live(username)
                    
                    status_tracker.update_user_status(
                        username,
                        is_live=is_live,
                        last_check=datetime.now().isoformat()
                    )
                    
                    if is_live and username not in recording_threads:
                        # Start recording in a new thread
                        thread = threading.Thread(
                            target=record_user_stream,
                            args=(username,),
                            daemon=True
                        )
                        thread.start()
                        recording_threads[username] = thread
                        logger.info(f"Started recording thread for {username}")
                        
                except Exception as e:
                    logger.error(f"Error checking {username}: {e}")
                
                time.sleep(5)  # Small delay between users
                    
            time.sleep(60)  # Check every minute
            
        except Exception as e:
            logger.error(f"Error in monitoring loop: {e}")
            time.sleep(60)

def record_user_stream(username):
    """Record a user's livestream"""
    try:
        logger.info(f"Starting to record {username}")
        
        # Update status
        status_tracker.update_user_status(
            username,
            is_recording=True,
            recording_start=datetime.now().isoformat()
        )
        
        # Start recording
        output_file = recorder.record_stream(username)
        
        if output_file and os.path.exists(output_file):
            file_size = os.path.getsize(output_file)
            logger.info(f"Recording completed for {username}: {output_file} ({file_size} bytes)")
            
            status_tracker.update_user_status(
                username,
                last_recording=output_file,
                recording_end=datetime.now().isoformat(),
                last_recording_size=file_size
            )
            
            # Upload to Google Drive if configured
            if drive_uploader:
                try:
                    logger.info(f"Uploading {username}'s recording to Drive...")
                    drive_url = upload_to_drive(output_file, username)
                    if drive_url:
                        status_tracker.update_user_status(
                            username,
                            drive_link=drive_url
                        )
                        logger.info(f"Uploaded to Drive: {drive_url}")
                        
                        # Remove local file after successful upload
                        try:
                            os.remove(output_file)
                            logger.info(f"Cleaned up local file: {output_file}")
                        except Exception as e:
                            logger.warning(f"Could not remove local file: {e}")
                except Exception as e:
                    logger.error(f"Drive upload error for {username}: {e}")
        else:
            logger.error(f"Recording failed for {username}")
            
    except Exception as e:
        logger.error(f"Error recording {username}: {e}")
    finally:
        # Always remove from active recordings
        if username in recording_threads:
            del recording_threads[username]
        
        # Update status
        status_tracker.update_user_status(
            username,
            is_recording=False,
            recording_end=datetime.now().isoformat()
        )

def upload_to_drive(file_path, username):
    """Upload file to Google Drive (placeholder)"""
    # This would use the Google Drive API
    # For now, just return None
    return None

@app.route('/')
def home():
    """Home page redirect to status"""
    return redirect(url_for('status'))

@app.route('/status')
def status():
    """Main dashboard showing user statuses"""
    try:
        usernames = load_usernames()
        user_statuses = {}
        
        # Check live status if needed
        for username in usernames:
            try:
                user_data = status_tracker.get_user_status(username) or {}
                
                # Check if we need to update status
                last_check = user_data.get('last_check')
                if not last_check or (datetime.now() - datetime.fromisoformat(last_check)).seconds > 300:
                    is_live = recorder.is_user_live(username)
                    status_tracker.update_user_status(
                        username,
                        is_live=is_live,
                        last_check=datetime.now().isoformat()
                    )
                    user_data = status_tracker.get_user_status(username)
                
                user_data['username'] = username
                user_data['is_recording'] = username in recording_threads
                
                # Format timestamps
                if 'last_updated' in user_data:
                    try:
                        dt = datetime.fromisoformat(user_data['last_updated'])
                        user_data['last_updated_formatted'] = dt.strftime('%Y-%m-%d %H:%M:%S')
                    except:
                        pass
                
                if 'recording_start' in user_data:
                    try:
                        dt = datetime.fromisoformat(user_data['recording_start'])
                        user_data['recording_start_formatted'] = dt.strftime('%Y-%m-%d %H:%M:%S')
                    except:
                        pass
                
                user_statuses[username] = user_data
                
            except Exception as e:
                logger.error(f"Error getting status for {username}: {e}")
                user_statuses[username] = {
                    'username': username,
                    'error': str(e)
                }
        
        return render_template('status.html', 
                             users=user_statuses, 
                             monitoring_active=monitoring_active,
                             drive_authorized=bool(drive_uploader),
                             now=datetime.now())
    except Exception as e:
        logger.error(f"Error in status page: {e}")
        return f"Error loading status page: {str(e)}", 500

@app.route('/api/status')
def api_status():
    """API endpoint for status data"""
    usernames = load_usernames()
    user_statuses = []
    
    for username in usernames:
        user_data = status_tracker.get_user_status(username) or {}
        user_data['username'] = username
        user_data['is_recording'] = username in recording_threads
        user_statuses.append(user_data)
    
    return jsonify({
        'users': user_statuses,
        'monitoring_active': monitoring_active,
        'total_users': len(usernames),
        'active_recordings': len(recording_threads)
    })

@app.route('/start_monitoring', methods=['GET', 'POST'])
def start_monitoring():
    """Start the monitoring system"""
    global monitoring_active
    
    if request.method == 'POST':
        if not monitoring_active:
            thread = threading.Thread(target=monitoring_loop, daemon=True)
            thread.start()
            logger.info("Monitoring started via web request")
        return jsonify({'success': True, 'monitoring_active': True})
    
    return jsonify({'monitoring_active': monitoring_active})

@app.route('/stop_monitoring', methods=['POST'])
def stop_monitoring():
    """Stop the monitoring system"""
    global monitoring_active
    monitoring_active = False
    logger.info("Monitoring stopped")
    return jsonify({'success': True, 'monitoring_active': False})

@app.route('/add_user', methods=['POST'])
def add_user():
    """Add a new user to monitor"""
    username = request.form.get('username', '').strip().replace('@', '')
    if not username:
        return jsonify({'error': 'Username is required'}), 400
    
    try:
        usernames = load_usernames()
        if username not in usernames:
            with open('usernames.txt', 'a') as f:
                if usernames:  # If file not empty, add newline
                    f.write('\n')
                f.write(username)
            
            # Immediately check live status
            is_live = recorder.is_user_live(username)
            status_tracker.update_user_status(
                username,
                is_live=is_live,
                last_check=datetime.now().isoformat()
            )
            
            logger.info(f"Added new user: {username} (live: {is_live})")
            
        return jsonify({
            'success': True,
            'message': f'Added user {username}'
        })
    except Exception as e:
        logger.error(f"Error adding user: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/remove_user', methods=['POST'])
def remove_user():
    """Remove a user from monitoring"""
    username = request.form.get('username', '').strip()
    if not username:
        return jsonify({'error': 'Username is required'}), 400
    
    try:
        usernames = load_usernames()
        if username in usernames:
            usernames.remove(username)
            with open('usernames.txt', 'w') as f:
                f.write('\n'.join(usernames))
            logger.info(f"Removed user: {username}")
        
        return redirect(url_for('status'))
    except Exception as e:
        logger.error(f"Error removing user: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/health')
def health():
    """Health check endpoint for Render"""
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat(),
        'monitoring_active': monitoring_active,
        'active_recordings': len(recording_threads)
    })

@app.route('/authorize')
def authorize():
    """Google Drive authorization page (placeholder)"""
    return render_template('authorize.html')

if __name__ == '__main__':
    # Create required directories
    os.makedirs('recordings', exist_ok=True)
    os.makedirs('logs', exist_ok=True)
    os.makedirs('templates', exist_ok=True)
    
    # Start monitoring automatically in development
    if not monitoring_active:
        thread = threading.Thread(target=monitoring_loop, daemon=True)
        thread.start()
        logger.info("Auto-started monitoring in development mode")
    
    # Development mode
    app.run(debug=True, host='0.0.0.0', port=5000)
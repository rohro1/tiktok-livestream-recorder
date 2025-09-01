#!/usr/bin/env python3
"""
TikTok Livestream Recorder - Deployment Setup Script
Automatically configures OAuth settings and environment variables
"""

import os
import json
import sys
import requests
from urllib.parse import urlparse

def detect_deployment_url():
    """Auto-detect the deployment URL"""
    try:
        # Check for Render environment
        if os.environ.get('RENDER'):
            service_name = os.environ.get('RENDER_SERVICE_NAME', 'tiktok-livestream-recorder')
            return f"https://{service_name}.onrender.com"
        
        # Check for Heroku environment
        if os.environ.get('DYNO'):
            app_name = os.environ.get('HEROKU_APP_NAME')
            if app_name:
                return f"https://{app_name}.herokuapp.com"
        
        # Check for Railway environment
        if os.environ.get('RAILWAY_ENVIRONMENT'):
            project_name = os.environ.get('RAILWAY_PROJECT_NAME', 'tiktok-recorder')
            return f"https://{project_name}.railway.app"
        
        # Fallback to localhost for development
        return "http://localhost:5000"
        
    except Exception as e:
        print(f"Error detecting deployment URL: {e}")
        return "http://localhost:5000"

def update_oauth_credentials():
    """Update OAuth credentials with correct redirect URI"""
    try:
        # Get deployment URL
        base_url = detect_deployment_url()
        redirect_uri = f"{base_url}/oauth2callback"
        
        print(f"🔗 Detected deployment URL: {base_url}")
        print(f"🔄 Setting redirect URI: {redirect_uri}")
        
        # Load existing credentials
        creds_json = os.environ.get('GOOGLE_CREDENTIALS_JSON')
        if creds_json:
            creds = json.loads(creds_json)
        elif os.path.exists('credentials.json'):
            with open('credentials.json', 'r') as f:
                creds = json.load(f)
        else:
            print("❌ No Google credentials found!")
            return False
        
        # Update redirect URIs
        if 'web' in creds:
            if 'redirect_uris' not in creds['web']:
                creds['web']['redirect_uris'] = []
            
            # Clear old URIs and add new one
            creds['web']['redirect_uris'] = [redirect_uri]
            
            # Also update authorized redirect URIs if present
            if 'authorized_redirect_uris' in creds['web']:
                creds['web']['authorized_redirect_uris'] = [redirect_uri]
        
        # Set environment variable for the app
        os.environ['OAUTH_REDIRECT_URI'] = redirect_uri
        
        # Save updated credentials if using file
        if not os.environ.get('GOOGLE_CREDENTIALS_JSON'):
            with open('credentials.json', 'w') as f:
                json.dump(creds, f, indent=2)
        
        print(f"✅ OAuth redirect URI updated: {redirect_uri}")
        return True
        
    except Exception as e:
        print(f"❌ Error updating OAuth credentials: {e}")
        return False

def create_default_usernames():
    """Create default usernames.txt if it doesn't exist"""
    try:
        if not os.path.exists('usernames.txt'):
            with open('usernames.txt', 'w', encoding='utf-8') as f:
                f.write("# TikTok Livestream Recorder - Usernames Configuration\n")
                f.write("# Add TikTok usernames here (one per line, without @)\n")
                f.write("# Lines starting with # are comments and will be ignored\n\n")
                f.write("# Example usernames (remove # to activate):\n")
                f.write("# charlidamelio\n")
                f.write("# addisonre\n")
                f.write("# khaby.lame\n\n")
                f.write("# Add your usernames below:\n")
            
            print("✅ Created default usernames.txt file")
        else:
            print("ℹ️ usernames.txt already exists")
        
        return True
    except Exception as e:
        print(f"❌ Error creating usernames.txt: {e}")
        return False

def verify_environment():
    """Verify all required environment variables and dependencies"""
    print("🔍 Verifying environment...")
    
    # Check required environment variables
    required_env_vars = {
        'SECRET_KEY': 'Flask secret key',
        'GOOGLE_CREDENTIALS_JSON': 'Google OAuth credentials (JSON)',
    }
    
    missing_vars = []
    for var, description in required_env_vars.items():
        if not os.environ.get(var):
            missing_vars.append(f"  - {var}: {description}")
    
    if missing_vars:
        print("⚠️ Missing environment variables:")
        for var in missing_vars:
            print(var)
        print("\nPlease set these in your deployment platform's environment variables section.")
        return False
    
    # Check Python dependencies
    try:
        import flask
        import google.auth
        import googleapiclient
        import yt_dlp
        import psutil
        import schedule
        print("✅ All Python dependencies available")
    except ImportError as e:
        print(f"❌ Missing Python dependency: {e}")
        return False
    
    # Check for ffmpeg (required for recording)
    try:
        import subprocess
        result = subprocess.run(['ffmpeg', '-version'], capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            print("✅ FFmpeg is available")
        else:
            print("⚠️ FFmpeg not found - recordings may fail")
    except Exception:
        print("⚠️ FFmpeg not found - recordings may fail")
    
    return True

def create_directories():
    """Create required directories"""
    try:
        directories = ['recordings', 'logs', 'templates']
        
        for directory in directories:
            os.makedirs(directory, exist_ok=True)
            print(f"📁 Directory ready: {directory}")
        
        # Create .gitkeep in recordings directory
        gitkeep_path = os.path.join('recordings', '.gitkeep')
        if not os.path.exists(gitkeep_path):
            with open(gitkeep_path, 'w') as f:
                f.write("# This file ensures the recordings directory is tracked by git\n")
                f.write("# Actual recording files are ignored but the directory structure is preserved\n")
        
        return True
    except Exception as e:
        print(f"❌ Error creating directories: {e}")
        return False

def test_oauth_configuration():
    """Test OAuth configuration"""
    try:
        print("🧪 Testing OAuth configuration...")
        
        creds_json = os.environ.get('GOOGLE_CREDENTIALS_JSON')
        if not creds_json:
            print("⚠️ GOOGLE_CREDENTIALS_JSON not found in environment")
            return False
        
        creds = json.loads(creds_json)
        
        # Validate credential structure
        if 'web' not in creds:
            print("❌ Invalid credentials format - 'web' key not found")
            return False
        
        web_creds = creds['web']
        required_fields = ['client_id', 'client_secret', 'auth_uri', 'token_uri']
        
        for field in required_fields:
            if field not in web_creds:
                print(f"❌ Missing required field in credentials: {field}")
                return False
        
        print("✅ OAuth credentials format is valid")
        
        # Check redirect URIs
        redirect_uris = web_creds.get('redirect_uris', [])
        oauth_redirect = os.environ.get('OAUTH_REDIRECT_URI')
        
        if oauth_redirect and oauth_redirect in redirect_uris:
            print(f"✅ Redirect URI configured correctly: {oauth_redirect}")
        else:
            print(f"⚠️ Redirect URI mismatch:")
            print(f"   Environment: {oauth_redirect}")
            print(f"   Credentials: {redirect_uris}")
        
        return True
        
    except Exception as e:
        print(f"❌ OAuth configuration test failed: {e}")
        return False

def main():
    """Main setup function"""
    print("🚀 TikTok Livestream Recorder - Deployment Setup")
    print("=" * 60)
    
    success_steps = []
    
    # Step 1: Create directories
    if create_directories():
        success_steps.append("📁 Directories created")
    
    # Step 2: Create default usernames file
    if create_default_usernames():
        success_steps.append("👥 Default usernames.txt created")
    
    # Step 3: Update OAuth configuration
    if update_oauth_credentials():
        success_steps.append("🔗 OAuth credentials updated")
    
    # Step 4: Verify environment
    if verify_environment():
        success_steps.append("🔍 Environment verified")
    
    # Step 5: Test OAuth configuration
    if test_oauth_configuration():
        success_steps.append("🧪 OAuth configuration tested")
    
    print("\n" + "=" * 60)
    print("📋 Setup Summary:")
    for step in success_steps:
        print(f"✅ {step}")
    
    if len(success_steps) >= 4:
        print("\n🎉 Setup completed successfully!")
        print("\n📝 Next steps:")
        print("   1. Add TikTok usernames to usernames.txt")
        print("   2. Start the application")
        print("   3. Visit /auth/google to authorize Google Drive")
        print("   4. Monitoring will start automatically after authorization")
        
        # Print the correct redirect URI for Google Cloud Console
        redirect_uri = os.environ.get('OAUTH_REDIRECT_URI') or detect_deployment_url() + "/oauth2callback"
        print(f"\n🔧 Google Cloud Console Setup:")
        print(f"   Add this redirect URI: {redirect_uri}")
        
        return True
    else:
        print(f"\n⚠️ Setup completed with {5 - len(success_steps)} warnings")
        print("   Please check the errors above and fix them before deploying")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)

#!/usr/bin/env python3
"""
TikTok Live Recorder - Autonomous Setup Script
This script automatically sets up the environment and checks all dependencies.
"""

import os
import sys
import json
import subprocess
import logging

def setup_logging():
    """Setup logging for setup process"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - SETUP - %(message)s'
    )

def check_python_version():
    """Check Python version"""
    version = sys.version_info
    if version.major < 3 or (version.major == 3 and version.minor < 7):
        logging.error("❌ Python 3.7+ required")
        return False
    logging.info(f"✅ Python {version.major}.{version.minor}.{version.micro}")
    return True

def check_ffmpeg():
    """Check if FFmpeg is installed"""
    try:
        result = subprocess.run(['ffmpeg', '-version'], 
                              capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            logging.info("✅ FFmpeg is installed")
            return True
    except FileNotFoundError:
        logging.error("❌ FFmpeg not found")
        logging.info("💡 Install FFmpeg:")
        logging.info("   Ubuntu/Debian: sudo apt update && sudo apt install ffmpeg")
        logging.info("   macOS: brew install ffmpeg")
        logging.info("   Windows: Download from https://ffmpeg.org/download.html")
        return False
    except subprocess.TimeoutExpired:
        logging.error("❌ FFmpeg check timed out")
        return False
    except Exception as e:
        logging.error(f"❌ Error checking FFmpeg: {e}")
        return False

def check_yt_dlp():
    """Check if yt-dlp is available"""
    try:
        result = subprocess.run(['yt-dlp', '--version'], 
                              capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            logging.info("✅ yt-dlp is available")
            return True
    except FileNotFoundError:
        logging.info("📦 yt-dlp will be installed via pip")
        return True
    except Exception as e:
        logging.warning(f"⚠️ yt-dlp check failed: {e}")
        return True

def check_credentials():
    """Check for Google OAuth credentials"""
    if os.path.exists('credentials.json'):
        try:
            with open('credentials.json', 'r') as f:
                creds = json.load(f)
            
            required_keys = ['web']
            if all(key in creds for key in required_keys):
                web_config = creds['web']
                if all(key in web_config for key in ['client_id', 'client_secret']):
                    logging.info("✅ Google OAuth credentials found")
                    return True
            
            logging.error("❌ Invalid credentials.json format")
            return False
            
        except json.JSONDecodeError:
            logging.error("❌ credentials.json is not valid JSON")
            return False
    else:
        logging.warning("⚠️ credentials.json not found")
        logging.info("💡 To enable Google Drive uploads:")
        logging.info("   1. Go to Google Cloud Console")
        logging.info("   2. Create OAuth 2.0 credentials")
        logging.info("   3. Download as credentials.json")
        return False

def install_requirements():
    """Install Python requirements"""
    try:
        logging.info("📦 Installing Python packages...")
        result = subprocess.run([
            sys.executable, '-m', 'pip', 'install', '-r', 'requirements.txt'
        ], check=True, capture_output=True, text=True)
        logging.info("✅ Python packages installed")
        return True
    except subprocess.CalledProcessError as e:
        logging.error(f"❌ Failed to install packages: {e}")
        logging.error(e.stderr)
        return False
    except FileNotFoundError:
        logging.error("❌ requirements.txt not found")
        return False

def create_initial_files():
    """Create initial configuration files"""
    # Create usernames.txt if it doesn't exist
    if not os.path.exists('usernames.txt'):
        with open('usernames.txt', 'w') as f:
            f.write('')
        logging.info("✅ Created usernames.txt")
    
    # Create recordings directory
    os.makedirs('recordings', exist_ok=True)
    logging.info("✅ Created recordings directory")
    
    # Create templates directory
    os.makedirs('templates', exist_ok=True)
    logging.info("✅ Created templates directory")

def test_tiktok_access():
    """Test TikTok API access"""
    try:
        import requests
        
        # Test with a known public profile
        test_url = "https://www.tiktok.com/@tiktok"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        response = requests.get(test_url, headers=headers, timeout=10)
        if response.status_code == 200:
            logging.info("✅ TikTok access working")
            return True
        else:
            logging.warning(f"⚠️ TikTok returned {response.status_code}")
            return False
            
    except Exception as e:
        logging.error(f"❌ TikTok access test failed: {e}")
        return False

def main():
    """Main setup function"""
    setup_logging()
    logging.info("🚀 Starting TikTok Live Recorder Setup")
    
    checks = [
        ("Python Version", check_python_version),
        ("FFmpeg", check_ffmpeg),
        ("yt-dlp", check_yt_dlp),
        ("Initial Files", lambda: (create_initial_files(), True)[1]),
        ("Requirements", install_requirements),
        ("Google Credentials", check_credentials),
        ("TikTok Access", test_tiktok_access)
    ]
    
    results = {}
    for name, check_func in checks:
        logging.info(f"🔍 Checking {name}...")
        try:
            results[name] = check_func()
        except Exception as e:
            logging.error(f"❌ {name} check failed: {e}")
            results[name] = False
    
    # Summary
    logging.info("\n" + "="*50)
    logging.info("📋 SETUP SUMMARY")
    logging.info("="*50)
    
    all_passed = True
    for name, passed in results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        logging.info(f"{status} {name}")
        if not passed:
            all_passed = False
    
    logging.info("="*50)
    
    if all_passed:
        logging.info("🎉 Setup completed successfully!")
        logging.info("🚀 You can now run: python app.py")
    else:
        logging.warning("⚠️ Some checks failed. The app may still work with limited functionality.")
        logging.info("🔧 Fix the failed checks and run setup again")
    
    logging.info("="*50)
    return all_passed

if __name__ == '__main__':
    main()

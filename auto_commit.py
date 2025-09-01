#!/usr/bin/env python3
"""
Enhanced Auto-commit script for TikTok Livestream Recorder
Automatically commits and pushes changes to GitHub with robust error handling
"""

import os
import subprocess
import sys
import json
import time
import signal
import psutil
from datetime import datetime
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def run_command(command, cwd=None, timeout=45):
    """Run a shell command with timeout and return the result"""
    try:
        logger.debug(f"Running command: {command}")
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            cwd=cwd,
            timeout=timeout
        )
        return result.returncode == 0, result.stdout.strip(), result.stderr.strip()
    except subprocess.TimeoutExpired:
        logger.error(f"Command timed out after {timeout} seconds: {command}")
        return False, "", f"Command timed out after {timeout} seconds"
    except Exception as e:
        logger.error(f"Command execution error: {e}")
        return False, "", str(e)

def kill_git_processes():
    """Kill any hanging git processes"""
    try:
        killed_count = 0
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                if proc.info['name'] == 'git' or (proc.info['cmdline'] and 'git' in ' '.join(proc.info['cmdline'])):
                    logger.info(f"🔪 Killing git process: {proc.info['pid']}")
                    proc.kill()
                    proc.wait(timeout=5)
                    killed_count += 1
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.TimeoutExpired):
                pass
        
        if killed_count > 0:
            logger.info(f"✅ Killed {killed_count} git processes")
            time.sleep(2)  # Give time for cleanup
    except Exception as e:
        logger.error(f"Error killing git processes: {e}")

def cleanup_git_locks():
    """Remove git lock files comprehensively"""
    lock_patterns = [
        '.git/index.lock',
        '.git/refs/heads/*.lock',
        '.git/refs/remotes/*/*.lock',
        '.git/config.lock',
        '.git/HEAD.lock',
        '.git/logs/refs/heads/*.lock',
        '.git/logs/refs/remotes/*/*.lock'
    ]
    
    removed_count = 0
    
    # Remove standard lock files
    for pattern in lock_patterns:
        if '*' in pattern:
            # Handle wildcard patterns
            import glob
            for lock_file in glob.glob(pattern):
                if os.path.exists(lock_file):
                    try:
                        os.remove(lock_file)
                        logger.info(f"🗑️ Removed lock file: {lock_file}")
                        removed_count += 1
                    except Exception as e:
                        logger.warning(f"Failed to remove {lock_file}: {e}")
        else:
            if os.path.exists(pattern):
                try:
                    os.remove(pattern)
                    logger.info(f"🗑️ Removed lock file: {pattern}")
                    removed_count += 1
                except Exception as e:
                    logger.warning(f"Failed to remove {pattern}: {e}")
    
    if removed_count > 0:
        logger.info(f"✅ Removed {removed_count} lock files")

def setup_git_config():
    """Setup git configuration with enhanced reliability"""
    logger.info("🔧 Setting up git configuration...")
    
    # Kill any hanging git processes first
    kill_git_processes()
    cleanup_git_locks()
    
    # Wait for cleanup
    time.sleep(3)
    
    # Set git configuration
    config_commands = [
        'git config user.name "TikTok Recorder Bot"',
        'git config user.email "recorder@github-actions.com"',
        'git config push.default simple',
        'git config pull.rebase false',
        'git config core.autocrlf false',
        'git config core.filemode false',
        'git config --global --add safe.directory "*"',
        'git config http.postBuffer 524288000',  # 500MB buffer
        'git config http.timeout 60'
    ]
    
    for cmd in config_commands:
        for attempt in range(2):
            success, stdout, stderr = run_command(cmd, timeout=15)
            if success:
                break
            elif attempt == 0:
                logger.warning(f"Config retry: {cmd}")
                time.sleep(1)
            else:
                logger.error(f"Config failed: {cmd} - {stderr}")
    
    logger.info("✅ Git configuration completed")

def check_git_status():
    """Check if there are any changes to commit with enhanced reliability"""
    logger.info("🔍 Checking for changes...")
    
    for attempt in range(5):
        # Clean up before each attempt
        if attempt > 0:
            cleanup_git_locks()
            kill_git_processes()
            time.sleep(2)
        
        success, stdout, stderr = run_command("git status --porcelain", timeout=20)
        
        if success:
            changes = []
            for line in stdout.split('\n'):
                if line.strip():
                    status = line[:2]
                    filename = line[3:].strip()
                    changes.append({'status': status, 'file': filename})
            
            logger.info(f"✅ Git status check successful - {len(changes)} changes found")
            return True, changes
        
        if "lock" in stderr.lower() or "unable to create" in stderr.lower():
            logger.warning(f"🔄 Attempt {attempt + 1}: Git lock detected - {stderr}")
            continue
        else:
            logger.error(f"❌ Git status error (attempt {attempt + 1}): {stderr}")
            if attempt == 4:  # Last attempt
                break
            time.sleep(2)
    
    logger.error("❌ Failed to get git status after all attempts")
    return False, []

def force_git_reset():
    """Comprehensive git state reset"""
    logger.info("🔄 Performing comprehensive git reset...")
    
    # Kill processes and clean locks first
    kill_git_processes()
    cleanup_git_locks()
    time.sleep(3)
    
    reset_commands = [
        "git gc --prune=now",  # Clean up repository
        "git remote prune origin",  # Clean remote references
        "git fetch origin main --force",  # Force fetch latest
        "git reset --hard HEAD",  # Reset to HEAD
        "git clean -fd",  # Remove untracked files
        "git checkout main",  # Ensure on main branch
        "git pull origin main --allow-unrelated-histories --force"  # Force pull
    ]
    
    for cmd in reset_commands:
        success, stdout, stderr = run_command(cmd, timeout=45)
        if not success:
            logger.warning(f"Reset command warning: {cmd} - {stderr}")
        else:
            logger.debug(f"Reset command success: {cmd}")
    
    logger.info("✅ Git reset completed")

def commit_and_push_changes():
    """Enhanced commit and push with multiple strategies"""
    logger.info("🚀 Starting commit and push process...")
    
    # Setup git config
    setup_git_config()
    
    # Check for changes
    success, changes = check_git_status()
    if not success:
        logger.warning("⚠️ Git status failed, attempting reset...")
        force_git_reset()
        success, changes = check_git_status()
        if not success:
            logger.error("❌ Cannot recover git repository state")
            return False
    
    if not changes:
        logger.info("✅ No changes to commit")
        return True
    
    logger.info(f"📝 Processing {len(changes)} changes:")
    for change in changes:
        logger.info(f"  {change['status']} {change['file']}")
    
    # Add all changes with robust retry logic
    logger.info("➕ Adding changes to staging...")
    for attempt in range(5):
        cleanup_git_locks()
        time.sleep(1)
        
        success, stdout, stderr = run_command("git add .", timeout=30)
        
        if success:
            logger.info("✅ Changes added successfully")
            break
        
        if "lock" in stderr.lower():
            logger.warning(f"🔄 Add attempt {attempt + 1}: Lock detected, cleaning...")
            kill_git_processes()
            time.sleep(3)
        else:
            logger.error(f"❌ Add failed (attempt {attempt + 1}): {stderr}")
            if attempt == 4:
                return False
    
    # Create detailed commit message
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC")
    file_types = {}
    for change in changes:
        ext = os.path.splitext(change['file'])[1] or 'other'
        file_types[ext] = file_types.get(ext, 0) + 1
    
    file_summary = ", ".join([f"{count} {ext}" for ext, count in file_types.items()])
    commit_message = f"Auto-commit: {timestamp} - Updated {len(changes)} files ({file_summary})"
    
    # Commit changes with retry
    logger.info("💾 Committing changes...")
    for attempt in range(5):
        cleanup_git_locks()
        time.sleep(1)
        
        success, stdout, stderr = run_command(f'git commit -m "{commit_message}"', timeout=30)
        
        if success:
            logger.info("✅ Commit successful")
            break
        
        if "nothing to commit" in stderr or "working tree clean" in stderr:
            logger.info("✅ Nothing new to commit")
            return True
        
        if "lock" in stderr.lower():
            logger.warning(f"🔄 Commit attempt {attempt + 1}: Lock detected, cleaning...")
            kill_git_processes()
            time.sleep(3)
        else:
            logger.error(f"❌ Commit failed (attempt {attempt + 1}): {stderr}")
            if attempt == 4:
                return False
    
    # Push to GitHub with multiple strategies
    logger.info("🚀 Pushing to GitHub...")
    
    push_strategies = [
        ("git push origin main", "Standard push"),
        ("git push origin main --force-with-lease", "Force with lease"),
        ("git push origin main --force", "Force push")
    ]
    
    for strategy_cmd, strategy_name in push_strategies:
        logger.info(f"📤 Trying: {strategy_name}")
        
        for attempt in range(3):
            cleanup_git_locks()
            time.sleep(2)
            
            success, stdout, stderr = run_command(strategy_cmd, timeout=90)
            
            if success:
                logger.info(f"✅ Push successful with {strategy_name}!")
                return True
            
            if "lock" in stderr.lower():
                logger.warning(f"🔄 Push attempt {attempt + 1}: Lock detected, cleaning...")
                kill_git_processes()
                time.sleep(5)
            elif "non-fast-forward" in stderr or "rejected" in stderr:
                logger.warning(f"⚠️ Push rejected: {stderr}")
                break  # Try next strategy
            else:
                logger.error(f"❌ {strategy_name} attempt {attempt + 1} failed: {stderr}")
                if attempt < 2:
                    time.sleep(5)
    
    logger.error("❌ All push strategies failed")
    return False

def emergency_backup():
    """Create emergency backup of important files"""
    try:
        logger.info("🆘 Creating emergency backup...")
        
        backup_files = ['usernames.txt', 'app.log', 'credentials.json']
        backup_dir = f"backup_{int(time.time())}"
        
        os.makedirs(backup_dir, exist_ok=True)
        
        for file in backup_files:
            if os.path.exists(file):
                success, stdout, stderr = run_command(f"cp {file} {backup_dir}/", timeout=10)
                if success:
                    logger.info(f"📋 Backed up: {file}")
        
        # Try to add backup to git
        run_command(f"git add {backup_dir}", timeout=10)
        logger.info(f"✅ Emergency backup created in {backup_dir}")
        
    except Exception as e:
        logger.error(f"❌ Emergency backup failed: {e}")

def main():
    """Main function with comprehensive error handling and recovery"""
    logger.info("🚀 TikTok Livestream Recorder - Enhanced Auto Commit")
    logger.info("=" * 60)
    
    # Verify we're in a git repository
    if not os.path.exists('.git'):
        logger.error("❌ Not in a git repository")
        sys.exit(1)
    
    # Check git installation
    success, stdout, stderr = run_command("git --version", timeout=10)
    if not success:
        logger.error("❌ Git is not installed or not accessible")
        sys.exit(1)
    
    logger.info(f"📋 Git version: {stdout}")
    
    # Initial comprehensive cleanup
    logger.info("🧹 Performing initial cleanup...")
    cleanup_git_locks()
    kill_git_processes()
    time.sleep(3)
    
    # Main execution with retries
    max_retries = 3
    for main_attempt in range(max_retries):
        logger.info(f"\n🔄 Main attempt {main_attempt + 1} of {max_retries}")
        
        try:
            success = commit_and_push_changes()
            
            if success:
                logger.info("✅ Auto-commit completed successfully!")
                sys.exit(0)
            else:
                logger.error(f"❌ Attempt {main_attempt + 1} failed")
                
                if main_attempt < max_retries - 1:
                    logger.info("🔄 Attempting recovery...")
                    
                    # Try emergency backup
                    emergency_backup()
                    
                    # More aggressive cleanup
                    kill_git_processes()
                    cleanup_git_locks()
                    
                    # Wait longer between retries
                    wait_time = (main_attempt + 1) * 15
                    logger.info(f"⏳ Waiting {wait_time} seconds before retry...")
                    time.sleep(wait_time)
                    
                    # Try force reset if this isn't the last attempt
                    if main_attempt == 1:
                        force_git_reset()
        
        except KeyboardInterrupt:
            logger.info("🛑 Process interrupted by user")
            sys.exit(1)
        except Exception as e:
            logger.error(f"❌ Unexpected error in attempt {main_attempt + 1}: {e}")
            if main_attempt < max_retries - 1:
                time.sleep(10)
    
    # Final emergency attempt
    logger.warning("🚨 All standard attempts failed, trying emergency commit...")
    try:
        emergency_backup()
        
        # Emergency commit with minimal checks
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        emergency_commands = [
            "git add .",
            f'git commit -m "Emergency commit: {timestamp}" --allow-empty',
            "git push origin main --force"
        ]
        
        for cmd in emergency_commands:
            success, stdout, stderr = run_command(cmd, timeout=60)
            if not success:
                logger.error(f"Emergency command failed: {cmd} - {stderr}")
            else:
                logger.info(f"Emergency command success: {cmd}")
        
        logger.info("🆘 Emergency commit attempt completed")
        
    except Exception as e:
        logger.error(f"❌ Emergency commit failed: {e}")
    
    logger.error("❌ Auto-commit failed after all attempts!")
    sys.exit(1)

if __name__ == "__main__":
    # Handle graceful shutdown
    def signal_handler(sig, frame):
        logger.info("🛑 Received shutdown signal")
        kill_git_processes()
        cleanup_git_locks()
        sys.exit(1)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    main()

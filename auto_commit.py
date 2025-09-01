
#!/usr/bin/env python3
"""
Auto-commit script for TikTok Livestream Recorder
Automatically commits and pushes changes to GitHub with enhanced error handling
"""

import os
import subprocess
import sys
import json
import time
import signal
import psutil
from datetime import datetime

def run_command(command, cwd=None, timeout=30):
    """Run a shell command with timeout and return the result"""
    try:
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
        return False, "", f"Command timed out after {timeout} seconds"
    except Exception as e:
        return False, "", str(e)

def kill_git_processes():
    """Kill any hanging git processes"""
    try:
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                if proc.info['name'] == 'git' or (proc.info['cmdline'] and 'git' in ' '.join(proc.info['cmdline'])):
                    print(f"🔪 Killing git process: {proc.info['pid']}")
                    proc.kill()
                    proc.wait(timeout=5)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
    except Exception as e:
        print(f"Error killing git processes: {e}")

def cleanup_git_locks():
    """Remove git lock files"""
    lock_files = [
        '.git/index.lock',
        '.git/refs/heads/main.lock',
        '.git/refs/remotes/origin/main.lock',
        '.git/config.lock',
        '.git/HEAD.lock'
    ]
    
    for lock_file in lock_files:
        if os.path.exists(lock_file):
            try:
                os.remove(lock_file)
                print(f"🗑️ Removed lock file: {lock_file}")
            except Exception as e:
                print(f"❌ Failed to remove {lock_file}: {e}")

def setup_git_config():
    """Setup git configuration with retry logic"""
    print("🔧 Setting up git configuration...")
    
    # Kill any hanging git processes first
    kill_git_processes()
    cleanup_git_locks()
    
    # Wait a moment
    time.sleep(2)
    
    # Set user name and email
    commands = [
        'git config user.name "TikTok Recorder Bot"',
        'git config user.email "recorder@github-actions.com"',
        'git config push.default simple',
        'git config pull.rebase false'
    ]
    
    for cmd in commands:
        success, stdout, stderr = run_command(cmd, timeout=10)
        if not success:
            print(f"⚠️ Config command failed: {cmd} - {stderr}")
    
    print("✅ Git configuration ready")

def check_git_status():
    """Check if there are any changes to commit with retry logic"""
    for attempt in range(3):
        success, stdout, stderr = run_command("git status --porcelain", timeout=15)
        
        if success:
            changes = []
            for line in stdout.split('\n'):
                if line.strip():
                    status = line[:2]
                    filename = line[3:].strip()
                    changes.append({'status': status, 'file': filename})
            return True, changes
        
        if "lock" in stderr.lower():
            print(f"🔄 Attempt {attempt + 1}: Git lock detected, cleaning up...")
            cleanup_git_locks()
            kill_git_processes()
            time.sleep(3)
        else:
            print(f"❌ Git status error: {stderr}")
            break
    
    return False, []

def force_git_reset():
    """Force reset git state if needed"""
    print("🔄 Performing force reset...")
    
    commands = [
        "git reset --hard HEAD",
        "git clean -fd",
        "git fetch origin main",
        "git reset --hard origin/main"
    ]
    
    for cmd in commands:
        success, stdout, stderr = run_command(cmd, timeout=30)
        if not success and "lock" not in stderr.lower():
            print(f"⚠️ Reset command failed: {cmd} - {stderr}")

def commit_and_push_changes():
    """Commit and push changes to GitHub with enhanced error handling"""
    print("🔍 Checking for changes...")
    
    # Setup git config first
    setup_git_config()
    
    success, changes = check_git_status()
    if not success:
        print("❌ Failed to check git status, attempting force reset...")
        force_git_reset()
        success, changes = check_git_status()
        if not success:
            print("❌ Cannot recover git status")
            return False
    
    if not changes:
        print("✅ No changes to commit")
        return True
    
    print(f"📝 Found {len(changes)} changes:")
    for change in changes:
        print(f"  {change['status']} {change['file']}")
    
    # Add all changes with retry
    print("➕ Adding changes...")
    for attempt in range(3):
        cleanup_git_locks()
        success, stdout, stderr = run_command("git add .", timeout=20)
        
        if success:
            break
        
        if "lock" in stderr.lower():
            print(f"🔄 Add attempt {attempt + 1}: Lock detected, retrying...")
            kill_git_processes()
            time.sleep(3)
        else:
            print(f"❌ Failed to add changes: {stderr}")
            if attempt == 2:
                return False
    
    # Create commit message
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    commit_message = f"Auto-commit: Updated recordings and status at {timestamp}"
    
    # Commit changes with retry
    print("💾 Committing changes...")
    for attempt in range(3):
        cleanup_git_locks()
        success, stdout, stderr = run_command(f'git commit -m "{commit_message}"', timeout=20)
        
        if success:
            break
        
        if "nothing to commit" in stderr:
            print("✅ Nothing new to commit")
            return True
        
        if "lock" in stderr.lower():
            print(f"🔄 Commit attempt {attempt + 1}: Lock detected, retrying...")
            kill_git_processes()
            time.sleep(3)
        else:
            print(f"❌ Failed to commit: {stderr}")
            if attempt == 2:
                return False
    
    # Push to GitHub with retry
    print("🚀 Pushing to GitHub...")
    for attempt in range(3):
        cleanup_git_locks()
        success, stdout, stderr = run_command("git push origin main --force-with-lease", timeout=60)
        
        if success:
            print("✅ Successfully pushed changes to GitHub!")
            return True
        
        if "lock" in stderr.lower():
            print(f"🔄 Push attempt {attempt + 1}: Lock detected, retrying...")
            kill_git_processes()
            time.sleep(5)
        elif "non-fast-forward" in stderr or "rejected" in stderr:
            print("🔄 Push rejected, trying force push...")
            success, stdout, stderr = run_command("git push origin main --force", timeout=60)
            if success:
                print("✅ Force push successful!")
                return True
        else:
            print(f"❌ Push attempt {attempt + 1} failed: {stderr}")
    
    print("❌ All push attempts failed")
    return False

def main():
    """Main function with comprehensive error handling"""
    print("🚀 TikTok Livestream Recorder - Auto Commit")
    print("=" * 50)
    
    # Check if we're in a git repository
    if not os.path.exists('.git'):
        print("❌ Not in a git repository")
        sys.exit(1)
    
    # Initial cleanup
    cleanup_git_locks()
    kill_git_processes()
    
    # Run the commit and push process
    max_retries = 3
    for attempt in range(max_retries):
        print(f"\n🔄 Attempt {attempt + 1} of {max_retries}")
        
        success = commit_and_push_changes()
        
        if success:
            print("✅ Auto-commit completed successfully!")
            sys.exit(0)
        
        if attempt < max_retries - 1:
            print(f"⏳ Waiting 10 seconds before retry...")
            time.sleep(10)
    
    print("❌ Auto-commit failed after all retries!")
    sys.exit(1)

if __name__ == "__main__":
    main()


#!/usr/bin/env python3
"""
Auto-commit script for TikTok Livestream Recorder
Automatically commits and pushes changes to GitHub
"""

import os
import subprocess
import sys
import json
import time
from datetime import datetime

def run_command(command, cwd=None):
    """Run a shell command and return the result"""
    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            cwd=cwd
        )
        return result.returncode == 0, result.stdout.strip(), result.stderr.strip()
    except Exception as e:
        return False, "", str(e)

def check_git_status():
    """Check if there are any changes to commit"""
    success, stdout, stderr = run_command("git status --porcelain")
    if not success:
        print(f"Error checking git status: {stderr}")
        return False, []
    
    # Parse git status output
    changes = []
    for line in stdout.split('\n'):
        if line.strip():
            status = line[:2]
            filename = line[3:].strip()
            changes.append({'status': status, 'file': filename})
    
    return True, changes

def get_last_commit_info():
    """Get information about the last commit"""
    success, stdout, stderr = run_command("git log -1 --format='%H|%s|%ai'")
    if not success:
        return None
    
    parts = stdout.split('|')
    if len(parts) >= 3:
        return {
            'hash': parts[0],
            'message': parts[1],
            'date': parts[2]
        }
    return None

def commit_and_push_changes():
    """Commit and push changes to GitHub"""
    print("🔍 Checking for changes...")
    
    success, changes = check_git_status()
    if not success:
        print("❌ Failed to check git status")
        return False
    
    if not changes:
        print("✅ No changes to commit")
        return True
    
    print(f"📝 Found {len(changes)} changes:")
    for change in changes:
        print(f"  {change['status']} {change['file']}")
    
    # Add all changes
    print("➕ Adding changes...")
    success, stdout, stderr = run_command("git add .")
    if not success:
        print(f"❌ Failed to add changes: {stderr}")
        return False
    
    # Create commit message
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    commit_message = f"Auto-commit: Updated recordings and status at {timestamp}"
    
    # Check if this is just a timestamp update
    recording_changes = [c for c in changes if 'recordings/' in c['file'] or 'app.log' in c['file']]
    if recording_changes:
        commit_message = f"Auto-commit: New recordings and updates at {timestamp}"
    
    # Commit changes
    print("💾 Committing changes...")
    success, stdout, stderr = run_command(f'git commit -m "{commit_message}"')
    if not success:
        if "nothing to commit" in stderr:
            print("✅ Nothing new to commit")
            return True
        print(f"❌ Failed to commit: {stderr}")
        return False
    
    # Push to GitHub
    print("🚀 Pushing to GitHub...")
    success, stdout, stderr = run_command("git push origin main")
    if not success:
        print(f"❌ Failed to push: {stderr}")
        return False
    
    print("✅ Successfully pushed changes to GitHub!")
    return True

def setup_git_config():
    """Setup git configuration if needed"""
    print("🔧 Setting up git configuration...")
    
    # Set user name and email if not already set
    success, stdout, stderr = run_command("git config user.name")
    if not success or not stdout:
        run_command('git config user.name "TikTok Recorder Bot"')
    
    success, stdout, stderr = run_command("git config user.email")
    if not success or not stdout:
        run_command('git config user.email "recorder@github-actions.com"')
    
    print("✅ Git configuration ready")

def main():
    """Main function"""
    print("🚀 TikTok Livestream Recorder - Auto Commit")
    print("=" * 50)
    
    # Check if we're in a git repository
    if not os.path.exists('.git'):
        print("❌ Not in a git repository")
        sys.exit(1)
    
    # Setup git configuration
    setup_git_config()
    
    # Show current repository status
    last_commit = get_last_commit_info()
    if last_commit:
        print(f"📋 Last commit: {last_commit['hash'][:8]} - {last_commit['message']}")
        print(f"📅 Date: {last_commit['date']}")
    
    # Commit and push changes
    success = commit_and_push_changes()
    
    if success:
        print("✅ Auto-commit completed successfully!")
        sys.exit(0)
    else:
        print("❌ Auto-commit failed!")
        sys.exit(1)

if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Enhanced Auto-commit script for TikTok Livestream Recorder
Ultra-reliable Git operations with comprehensive error handling and recovery
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
import threading
import hashlib
import tempfile
import shutil

# Enhanced logging configuration
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('git_operations.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Global configuration
MAX_RETRIES = 5
COMMAND_TIMEOUT = 60
CLEANUP_DELAY = 3
FORCE_PUSH_THRESHOLD = 3  # After 3 failed attempts, use force push

class GitOperationError(Exception):
    """Custom exception for Git operations"""
    pass

class EnhancedGitManager:
    """Enhanced Git manager with bulletproof operations"""
    
    def __init__(self):
        self.repo_path = os.getcwd()
        self.lock_files_cleaned = 0
        self.processes_killed = 0
        self.operation_count = 0
        
    def run_command_with_retry(self, command, max_retries=MAX_RETRIES, timeout=COMMAND_TIMEOUT):
        """Run command with comprehensive retry logic"""
        for attempt in range(max_retries):
            try:
                logger.debug(f"🔄 Attempt {attempt + 1}: {command}")
                
                # Clean environment before each attempt
                if attempt > 0:
                    self.comprehensive_cleanup()
                    time.sleep(CLEANUP_DELAY * attempt)  # Progressive delay
                
                # Execute command
                result = subprocess.run(
                    command,
                    shell=True,
                    capture_output=True,
                    text=True,
                    cwd=self.repo_path,
                    timeout=timeout,
                    env=self._get_clean_env()
                )
                
                # Check for success
                if result.returncode == 0:
                    logger.debug(f"✅ Command succeeded: {command}")
                    return True, result.stdout.strip(), result.stderr.strip()
                
                # Analyze error for retry decision
                stderr_lower = result.stderr.lower()
                
                # Certain errors should not be retried
                if any(phrase in stderr_lower for phrase in [
                    "nothing to commit",
                    "working tree clean",
                    "up to date",
                    "already exists"
                ]):
                    logger.info(f"ℹ️ Command completed (no retry needed): {result.stderr}")
                    return True, result.stdout.strip(), result.stderr.strip()
                
                # Log retry reason
                if "lock" in stderr_lower:
                    logger.warning(f"🔒 Lock detected on attempt {attempt + 1}: {result.stderr}")
                elif "timeout" in stderr_lower or "connection" in stderr_lower:
                    logger.warning(f"🌐 Network issue on attempt {attempt + 1}: {result.stderr}")
                else:
                    logger.warning(f"❌ Command failed on attempt {attempt + 1}: {result.stderr}")
                
                # Don't retry on last attempt
                if attempt == max_retries - 1:
                    break
                    
            except subprocess.TimeoutExpired:
                logger.error(f"⏰ Command timed out on attempt {attempt + 1}: {command}")
                self.kill_hanging_processes()
                if attempt == max_retries - 1:
                    break
            except Exception as e:
                logger.error(f"💥 Command exception on attempt {attempt + 1}: {e}")
                if attempt == max_retries - 1:
                    break
        
        # All attempts failed
        logger.error(f"❌ Command failed after {max_retries} attempts: {command}")
        return False, "", f"Failed after {max_retries} attempts"
    
    def _get_clean_env(self):
        """Get clean environment for Git operations"""
        env = os.environ.copy()
        
        # Set Git-specific environment variables
        env.update({
            'GIT_TERMINAL_PROMPT': '0',
            'GIT_ASKPASS': 'echo',
            'GIT_SSH_COMMAND': 'ssh -o BatchMode=yes -o ConnectTimeout=10',
            'LANG': 'C',
            'LC_ALL': 'C'
        })
        
        return env
    
    def comprehensive_cleanup(self):
        """Comprehensive cleanup of Git locks and processes"""
        try:
            # Kill hanging Git processes
            self.kill_hanging_processes()
            
            # Clean lock files
            self.cleanup_all_git_locks()
            
            # Reset Git index if corrupted
            self.reset_git_index()
            
            logger.info(f"🧹 Cleanup completed (locks: {self.lock_files_cleaned}, processes: {self.processes_killed})")
            
        except Exception as e:
            logger.error(f"❌ Cleanup error: {e}")
    
    def kill_hanging_processes(self):
        """Kill all hanging Git processes comprehensively"""
        try:
            killed_count = 0
            
            for proc in psutil.process_iter(['pid', 'name', 'cmdline', 'create_time']):
                try:
                    proc_info = proc.info
                    
                    # Check if it's a Git process
                    is_git = False
                    if proc_info['name'] == 'git':
                        is_git = True
                    elif proc_info['cmdline']:
                        cmdline = ' '.join(proc_info['cmdline']).lower()
                        if 'git' in cmdline and any(cmd in cmdline for cmd in ['push', 'pull', 'fetch', 'commit', 'add']):
                            is_git = True
                    
                    if is_git:
                        # Check if process is old (running for more than 2 minutes)
                        process_age = time.time() - proc_info['create_time']
                        if process_age > 120:  # 2 minutes
                            logger.info(f"🔪 Killing old git process: PID {proc_info['pid']} (age: {process_age:.0f}s)")
                            proc.kill()
                            proc.wait(timeout=10)
                            killed_count += 1
                        
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.TimeoutExpired):
                    continue
                except Exception as e:
                    logger.debug(f"Process check error: {e}")
                    continue
            
            self.processes_killed += killed_count
            if killed_count > 0:
                logger.info(f"✅ Killed {killed_count} hanging git processes")
                time.sleep(CLEANUP_DELAY)
                
        except Exception as e:
            logger.error(f"❌ Error killing git processes: {e}")
    
    def cleanup_all_git_locks(self):
        """Remove all Git lock files comprehensively"""
        lock_patterns = [
            '.git/index.lock',
            '.git/refs/heads/*.lock',
            '.git/refs/remotes/*/*.lock',
            '.git/refs/tags/*.lock',
            '.git/config.lock',
            '.git/HEAD.lock',
            '.git/shallow.lock',
            '.git/logs/refs/heads/*.lock',
            '.git/logs/refs/remotes/*/*.lock',
            '.git/logs/HEAD.lock',
            '.git/packed-refs.lock',
            '.git/COMMIT_EDITMSG.lock',
            '.git/MERGE_HEAD.lock',
            '.git/FETCH_HEAD.lock'
        ]
        
        removed_count = 0
        
        try:
            # Remove pattern-based lock files
            import glob
            for pattern in lock_patterns:
                try:
                    if '*' in pattern:
                        for lock_file in glob.glob(pattern):
                            if os.path.exists(lock_file):
                                os.remove(lock_file)
                                logger.debug(f"🗑️ Removed: {lock_file}")
                                removed_count += 1
                    else:
                        if os.path.exists(pattern):
                            os.remove(pattern)
                            logger.debug(f"🗑️ Removed: {pattern}")
                            removed_count += 1
                except Exception as e:
                    logger.debug(f"Lock removal error for {pattern}: {e}")
            
            # Find and remove any other .lock files in .git directory
            if os.path.exists('.git'):
                for root, dirs, files in os.walk('.git'):
                    for file in files:
                        if file.endswith('.lock'):
                            lock_path = os.path.join(root, file)
                            try:
                                os.remove(lock_path)
                                logger.debug(f"🗑️ Removed additional lock: {lock_path}")
                                removed_count += 1
                            except Exception as e:
                                logger.debug(f"Additional lock removal error: {e}")
            
            self.lock_files_cleaned += removed_count
            if removed_count > 0:
                logger.info(f"✅ Removed {removed_count} lock files")
                
        except Exception as e:
            logger.error(f"❌ Error cleaning lock files: {e}")
    
    def reset_git_index(self):
        """Reset Git index if corrupted"""
        try:
            index_path = '.git/index'
            if os.path.exists(index_path):
                # Check if index is corrupted
                result = subprocess.run(
                    'git status --porcelain',
                    shell=True,
                    capture_output=True,
                    text=True,
                    timeout=10
                )
                
                if result.returncode != 0 and "index" in result.stderr.lower():
                    logger.warning("🔧 Resetting corrupted Git index...")
                    
                    # Backup and reset index
                    backup_path = f"{index_path}.backup.{int(time.time())}"
                    shutil.copy2(index_path, backup_path)
                    
                    # Reset index
                    subprocess.run('git read-tree HEAD', shell=True, timeout=15)
                    logger.info("✅ Git index reset completed")
                    
        except Exception as e:
            logger.debug(f"Index reset error: {e}")
    
    def setup_git_config(self):
        """Setup Git configuration with enhanced settings"""
        logger.info("🔧 Configuring Git for optimal performance...")
        
        # Perform initial cleanup
        self.comprehensive_cleanup()
        
        config_commands = [
            'git config user.name "TikTok Recorder Bot"',
            'git config user.email "recorder@github-actions.com"',
            'git config push.default simple',
            'git config pull.rebase false',
            'git config core.autocrlf false',
            'git config core.filemode false',
            'git config core.safecrlf false',
            'git config --global --add safe.directory "*"',
            'git config http.postBuffer 1048576000',  # 1GB buffer
            'git config http.timeout 120',            # 2 minute timeout
            'git config http.lowSpeedLimit 1000',     # 1KB/s minimum speed
            'git config http.lowSpeedTime 60',        # For 60 seconds
            'git config pack.windowMemory 256m',      # Optimize packing
            'git config pack.packSizeLimit 2g',       # Large pack limit
            'git config receive.fsckObjects false',   # Skip fsck for speed
            'git config fetch.fsckObjects false',
            'git config transfer.fsckObjects false'
        ]
        
        for cmd in config_commands:
            success, stdout, stderr = self.run_command_with_retry(cmd, max_retries=2, timeout=20)
            if not success:
                logger.warning(f"⚠️ Config warning: {cmd} - {stderr}")
        
        logger.info("✅ Git configuration completed")
    
    def check_git_status(self):
        """Enhanced Git status check with better error handling"""
        logger.info("🔍 Checking repository status...")
        
        # Ensure we're in a git repository
        if not os.path.exists('.git'):
            logger.error("❌ Not in a Git repository")
            return False, []
        
        # Check Git status with retries
        success, stdout, stderr = self.run_command_with_retry(
            "git status --porcelain --untracked-files=all",
            timeout=30
        )
        
        if not success:
            logger.error(f"❌ Git status failed: {stderr}")
            return False, []
        
        # Parse changes
        changes = []
        for line in stdout.split('\n'):
            if line.strip():
                status = line[:2]
                filename = line[3:].strip()
                changes.append({'status': status, 'file': filename})
        
        logger.info(f"✅ Git status successful - {len(changes)} changes found")
        return True, changes
    
    def add_changes_safely(self):
        """Add changes with comprehensive error handling"""
        logger.info("➕ Adding changes to staging area...")
        
        # Try different add strategies
        add_strategies = [
            ("git add .", "Standard add all"),
            ("git add -A", "Add all tracked and untracked"),
            ("git add --ignore-errors .", "Add with error ignore")
        ]
        
        for strategy_cmd, strategy_name in add_strategies:
            logger.info(f"📦 Trying: {strategy_name}")
            
            success, stdout, stderr = self.run_command_with_retry(strategy_cmd, timeout=45)
            
            if success:
                logger.info(f"✅ Add successful with {strategy_name}")
                return True
            else:
                logger.warning(f"⚠️ {strategy_name} failed: {stderr}")
                
                # If it's a lock error, clean and continue to next strategy
                if "lock" in stderr.lower():
                    self.comprehensive_cleanup()
                    continue
        
        logger.error("❌ All add strategies failed")
        return False
    
    def create_smart_commit(self, changes):
        """Create intelligent commit message based on changes"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC")
        
        # Analyze changes
        file_types = {}
        new_files = 0
        modified_files = 0
        deleted_files = 0
        
        for change in changes:
            status = change['status'].strip()
            filename = change['file']
            
            # Count change types
            if status.startswith('A') or status.startswith('?'):
                new_files += 1
            elif status.startswith('M'):
                modified_files += 1
            elif status.startswith('D'):
                deleted_files += 1
            
            # Count file types
            ext = os.path.splitext(filename)[1].lower() or 'other'
            file_types[ext] = file_types.get(ext, 0) + 1
        
        # Build commit message
        change_summary = []
        if new_files > 0:
            change_summary.append(f"{new_files} new")
        if modified_files > 0:
            change_summary.append(f"{modified_files} modified")
        if deleted_files > 0:
            change_summary.append(f"{deleted_files} deleted")
        
        change_text = ", ".join(change_summary) if change_summary else "misc changes"
        
        # File type summary
        file_summary = ", ".join([f"{count} {ext}" for ext, count in sorted(file_types.items())])
        
        commit_message = f"Auto-commit: {timestamp} - {change_text} ({file_summary})"
        
        # Limit message length
        if len(commit_message) > 200:
            commit_message = f"Auto-commit: {timestamp} - {len(changes)} files updated"
        
        return commit_message
    
    def commit_changes(self, commit_message):
        """Commit changes with enhanced error handling"""
        logger.info("💾 Committing changes...")
        
        # Escape commit message properly
        escaped_message = commit_message.replace('"', '\\"').replace('`', '\\`')
        
        commit_strategies = [
            (f'git commit -m "{escaped_message}"', "Standard commit"),
            (f'git commit -m "{escaped_message}" --no-verify', "Commit without hooks"),
            (f'git commit -m "Auto-commit: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}" --allow-empty', "Simple commit")
        ]
        
        for strategy_cmd, strategy_name in commit_strategies:
            logger.info(f"💾 Trying: {strategy_name}")
            
            success, stdout, stderr = self.run_command_with_retry(strategy_cmd, timeout=30)
            
            if success:
                logger.info(f"✅ Commit successful with {strategy_name}")
                return True
            else:
                stderr_lower = stderr.lower()
                if "nothing to commit" in stderr_lower or "working tree clean" in stderr_lower:
                    logger.info("✅ Nothing to commit (working tree clean)")
                    return True
                
                logger.warning(f"⚠️ {strategy_name} failed: {stderr}")
        
        logger.error("❌ All commit strategies failed")
        return False
    
    def push_to_remote(self):
        """Enhanced push with multiple strategies and recovery"""
        logger.info("🚀 Pushing to remote repository...")
        
        # Get current branch
        success, current_branch, _ = self.run_command_with_retry("git branch --show-current", max_retries=2)
        if not success or not current_branch:
            current_branch = "main"
        
        logger.info(f"📤 Pushing branch: {current_branch}")
        
        push_strategies = [
            (f"git push origin {current_branch}", "Standard push"),
            (f"git push origin {current_branch} --no-verify", "Push without hooks"),
            (f"git push origin {current_branch} --force-with-lease", "Force with lease"),
            (f"git push origin {current_branch} --force", "Force push (last resort)")
        ]
        
        for i, (strategy_cmd, strategy_name) in enumerate(push_strategies):
            logger.info(f"📤 Attempting: {strategy_name}")
            
            # Use force strategies only after failures
            if i >= FORCE_PUSH_THRESHOLD:
                logger.warning(f"⚠️ Using aggressive strategy: {strategy_name}")
            
            success, stdout, stderr = self.run_command_with_retry(
                strategy_cmd, 
                max_retries=3, 
                timeout=120
            )
            
            if success:
                logger.info(f"✅ Push successful with {strategy_name}!")
                return True
            else:
                stderr_lower = stderr.lower()
                
                # Check for specific errors
                if "up to date" in stderr_lower:
                    logger.info("✅ Repository already up to date")
                    return True
                elif "non-fast-forward" in stderr_lower or "rejected" in stderr_lower:
                    logger.warning(f"⚠️ Push rejected, trying next strategy: {stderr}")
                    
                    # Try to fetch and merge before next strategy
                    if i < len(push_strategies) - 1:
                        logger.info("🔄 Attempting fetch and merge...")
                        self.run_command_with_retry("git fetch origin", max_retries=2, timeout=60)
                        self.run_command_with_retry(f"git merge origin/{current_branch} --no-edit", max_retries=2)
                        
                elif "timeout" in stderr_lower or "connection" in stderr_lower:
                    logger.warning(f"🌐 Network issue: {stderr}")
                    time.sleep(10)  # Wait for network recovery
                else:
                    logger.error(f"❌ {strategy_name} failed: {stderr}")
        
        logger.error("❌ All push strategies failed")
        return False
    
    def emergency_recovery(self):
        """Emergency recovery procedure"""
        logger.warning("🆘 Starting emergency recovery procedure...")
        
        try:
            # Create backup of current state
            self.create_emergency_backup()
            
            # Nuclear cleanup
            self.nuclear_cleanup()
            
            # Re-initialize repository
            self.reinitialize_repository()
            
            # Try emergency commit
            return self.emergency_commit()
            
        except Exception as e:
            logger.error(f"❌ Emergency recovery failed: {e}")
            return False
    
    def create_emergency_backup(self):
        """Create backup of important files"""
        try:
            backup_dir = f"emergency_backup_{int(time.time())}"
            os.makedirs(backup_dir, exist_ok=True)
            
            important_files = [
                'usernames.txt',
                'app.log',
                'git_operations.log',
                'requirements.txt',
                'render.yaml'
            ]
            
            for file in important_files:
                if os.path.exists(file):
                    try:
                        shutil.copy2(file, backup_dir)
                        logger.info(f"📋 Backed up: {file}")
                    except Exception as e:
                        logger.warning(f"⚠️ Backup failed for {file}: {e}")
            
            logger.info(f"✅ Emergency backup created: {backup_dir}")
            
        except Exception as e:
            logger.error(f"❌ Emergency backup failed: {e}")
    
    def nuclear_cleanup(self):
        """Nuclear cleanup - most aggressive cleanup"""
        logger.warning("☢️ Performing nuclear cleanup...")
        
        try:
            # Kill ALL git processes
            subprocess.run("pkill -f git", shell=True, timeout=10)
            
            # Remove ALL lock files
            subprocess.run("find .git -name '*.lock' -delete", shell=True, timeout=10)
            
            # Reset file permissions
            subprocess.run("chmod -R 755 .git", shell=True, timeout=10)
            
            time.sleep(5)  # Wait for cleanup
            
            logger.info("✅ Nuclear cleanup completed")
            
        except Exception as e:
            logger.error(f"❌ Nuclear cleanup error: {e}")
    
    def reinitialize_repository(self):
        """Reinitialize repository if corrupted"""
        try:
            logger.warning("🔄 Reinitializing repository...")
            
            # Try to reset to a good state
            reset_commands = [
                "git reset --hard HEAD",
                "git clean -fd",
                "git checkout main",
                "git fetch origin main --force",
                "git reset --hard origin/main"
            ]
            
            for cmd in reset_commands:
                self.run_command_with_retry(cmd, max_retries=2, timeout=30)
            
            logger.info("✅ Repository reinitialization completed")
            
        except Exception as e:
            logger.error(f"❌ Repository reinitialization failed: {e}")
    
    def emergency_commit(self):
        """Emergency commit with minimal validation"""
        try:
            timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            
            emergency_commands = [
                "git add . --force",
                f'git commit -m "Emergency commit: {timestamp}" --allow-empty --no-verify',
                "git push origin main --force --no-verify"
            ]
            
            for cmd in emergency_commands:
                success, stdout, stderr = self.run_command_with_retry(cmd, max_retries=2, timeout=90)
                if success:
                    logger.info(f"✅ Emergency command successful: {cmd}")
                else:
                    logger.error(f"❌ Emergency command failed: {cmd} - {stderr}")
                    return False
            
            logger.info("✅ Emergency commit completed successfully")
            return True
            
        except Exception as e:
            logger.error(f"❌ Emergency commit failed: {e}")
            return False

def main():
    """Enhanced main function with bulletproof execution"""
    logger.info("🚀 TikTok Livestream Recorder - BULLETPROOF Auto Commit")
    logger.info("=" * 70)
    
    # Initialize Git manager
    git_manager = EnhancedGitManager()
    
    # Verify Git repository
    if not os.path.exists('.git'):
        logger.error("❌ Not in a Git repository")
        sys.exit(1)
    
    # Test Git installation
    success, git_version, _ = git_manager.run_command_with_retry("git --version", max_retries=2, timeout=10)
    if not success:
        logger.error("❌ Git is not installed or accessible")
        sys.exit(1)
    
    logger.info(f"📋 {git_version}")
    
    # Setup Git configuration
    git_manager.setup_git_config()
    
    # Main execution with comprehensive error handling
    max_main_attempts = 3
    
    for main_attempt in range(max_main_attempts):
        logger.info(f"\n🔄 Main execution attempt {main_attempt + 1} of {max_main_attempts}")
        
        try:
            # Check for changes
            status_success, changes = git_manager.check_git_status()
            
            if not status_success:
                logger.error(f"❌ Cannot check Git status on attempt {main_attempt + 1}")
                if main_attempt < max_main_attempts - 1:
                    git_manager.comprehensive_cleanup()
                    time.sleep(10)
                    continue
                else:
                    # Last attempt - try emergency recovery
                    logger.warning("🆘 Attempting emergency recovery...")
                    if git_manager.emergency_recovery():
                        sys.exit(0)
                    else:
                        sys.exit(1)
            
            if not changes:
                logger.info("✅ No changes to commit - repository is clean")
                sys.exit(0)
            
            logger.info(f"📝 Found {len(changes)} changes to process:")
            for change in changes[:10]:  # Show first 10
                logger.info(f"  {change['status']} {change['file']}")
            if len(changes) > 10:
                logger.info(f"  ... and {len(changes) - 10} more files")
            
            # Add changes
            if not git_manager.add_changes_safely():
                logger.error(f"❌ Failed to add changes on attempt {main_attempt + 1}")
                if main_attempt < max_main_attempts - 1:
                    continue
                else:
                    break
            
            # Create commit message
            commit_message = git_manager.create_smart_commit(changes)
            logger.info(f"📝 Commit message: {commit_message}")
            
            # Commit changes
            if not git_manager.commit_changes(commit_message):
                logger.error(f"❌ Failed to commit on attempt {main_attempt + 1}")
                if main_attempt < max_main_attempts - 1:
                    continue
                else:
                    break
            
            # Push to remote
            if not git_manager.push_to_remote():
                logger.error(f"❌ Failed to push on attempt {main_attempt + 1}")
                if main_attempt < max_main_attempts - 1:
                    # Try to recover by fetching latest
                    logger.info("🔄 Attempting recovery before retry...")
                    git_manager.run_command_with_retry("git fetch origin main", max_retries=2)
                    git_manager.run_command_with_retry("git rebase origin/main", max_retries=2)
                    continue
                else:
                    break
            
            # Success!
            logger.info("✅ Auto-commit completed successfully!")
            logger.info(f"📊 Statistics: {git_manager.processes_killed} processes killed, {git_manager.lock_files_cleaned} locks cleaned")
            sys.exit(0)
            
        except KeyboardInterrupt:
            logger.info("🛑 Process interrupted by user")
            git_manager.comprehensive_cleanup()
            sys.exit(1)
            
        except Exception as e:
            logger.error(f"❌ Unexpected error in attempt {main_attempt + 1}: {e}")
            logger.error(f"📍 Error traceback: {str(e)}")
            
            if main_attempt < max_main_attempts - 1:
                logger.info("🔄 Preparing for retry...")
                git_manager.comprehensive_cleanup()
                time.sleep(15 * (main_attempt + 1))  # Progressive delay
    
    # If we reach here, all standard attempts failed
    logger.warning("🚨 All standard attempts failed - attempting emergency recovery...")
    
    if git_manager.emergency_recovery():
        logger.info("✅ Emergency recovery successful!")
        sys.exit(0)
    else:
        logger.error("❌ Complete failure - emergency recovery also failed")
        
        # Final attempt - create a simple status file
        try:
            with open('git_operation_status.txt', 'w') as f:
                f.write(f"Git operation failed at {datetime.now()}\n")
                f.write(f"Processes killed: {git_manager.processes_killed}\n")
                f.write(f"Locks cleaned: {git_manager.lock_files_cleaned}\n")
            
            logger.info("📝 Created failure status file")
            
        except Exception as e:
            logger.error(f"❌ Even status file creation failed: {e}")
        
        sys.exit(1)

def signal_handler(sig, frame):
    """Enhanced signal handler"""
    logger.info("🛑 Received shutdown signal - performing cleanup...")
    
    try:
        # Kill git processes
        subprocess.run("pkill -f git", shell=True, timeout=5)
        
        # Remove lock files
        subprocess.run("find .git -name '*.lock' -delete", shell=True, timeout=5)
        
    except Exception as e:
        logger.error(f"❌ Cleanup error during shutdown: {e}")
    
    logger.info("✅ Cleanup completed")
    sys.exit(1)

if __name__ == "__main__":
    # Register enhanced signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Add timeout for the entire script
    def timeout_handler():
        logger.error("⏰ Script timeout reached - forcing exit")
        os._exit(1)
    
    # Set 10-minute timeout for entire script
    timer = threading.Timer(600, timeout_handler)
    timer.daemon = True
    timer.start()
    
    try:
        main()
    except Exception as e:
        logger.error(f"❌ Script crashed: {e}")
        sys.exit(1)
    finally:
        timer.cancel()
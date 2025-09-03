#!/usr/bin/env python3
"""
Production Startup Manager for TikTok Livestream Recorder
Ensures proper initialization and 24/7 reliability on Render
"""

import os
import sys
import time
import logging
import subprocess
import threading
import signal
import psutil
from datetime import datetime
import json

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('startup.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class ProductionManager:
    """Manages production deployment and ensures 24/7 operation"""
    
    def __init__(self):
        self.main_process = None
        self.auto_commit_process = None
        self.monitoring_active = True
        self.restart_count = 0
        self.max_restarts = 10
        
    def verify_environment(self):
        """Verify all required dependencies and environment"""
        logger.info("🔍 Verifying production environment...")
        
        # Check Python version
        python_version = sys.version
        logger.info(f"🐍 Python version: {python_version}")
        
        # Check FFmpeg
        try:
            result = subprocess.run(['ffmpeg', '-version'], capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                version_line = result.stdout.split('\n')[0]
                logger.info(f"🎬 FFmpeg: {version_line}")
            else:
                logger.error("❌ FFmpeg not found or not working")
                return False
        except Exception as e:
            logger.error(f"❌ FFmpeg check failed: {e}")
            return False
        
        # Check Git
        try:
            result = subprocess.run(['git', '--version'], capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                logger.info(f"📋 Git: {result.stdout.strip()}")
            else:
                logger.error("❌ Git not found")
                return False
        except Exception as e:
            logger.error(f"❌ Git check failed: {e}")
            return False
        
        # Check required Python packages
        required_packages = [
            'flask', 'requests', 'yt_dlp', 'google.auth', 'psutil'
        ]
        
        for package in required_packages:
            try:
                __import__(package.replace('.', '_'))
                logger.info(f"✅ {package} imported successfully")
            except ImportError as e:
                logger.error(f"❌ Missing package {package}: {e}")
                return False
        
        # Check environment variables
        required_env_vars = ['PORT']
        for var in required_env_vars:
            if var in os.environ:
                logger.info(f"✅ Environment variable {var}: {os.environ[var]}")
            else:
                logger.warning(f"⚠️ Missing environment variable: {var}")
        
        # Create required directories
        directories = ['recordings', 'templates']
        for directory in directories:
            os.makedirs(directory, exist_ok=True)
            logger.info(f"📁 Directory ensured: {directory}")
        
        # Verify disk space
        disk_usage = psutil.disk_usage('.')
        free_gb = disk_usage.free / (1024**3)
        logger.info(f"💾 Available disk space: {free_gb:.2f} GB")
        
        if free_gb < 0.1:  # Less than 100MB
            logger.warning("⚠️ Low disk space - may affect recording")
        
        logger.info("✅ Environment verification completed")
        return True
    
    def setup_git_repository(self):
        """Setup Git repository for auto-commits"""
        logger.info("🔧 Setting up Git repository...")
        
        try:
            # Verify we're in a Git repository
            if not os.path.exists('.git'):
                logger.error("❌ Not in a Git repository")
                return False
            
            # Configure Git for production
            git_commands = [
                'git config user.name "TikTok Recorder Bot"',
                'git config user.email "recorder@production.com"',
                'git config --global --add safe.directory "*"',
                'git config http.postBuffer 524288000',
                'git config http.timeout 60',
                'git config core.autocrlf false',
                'git config core.filemode false'
            ]
            
            for cmd in git_commands:
                try:
                    result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=15)
                    if result.returncode != 0:
                        logger.warning(f"⚠️ Git config warning: {cmd} - {result.stderr}")
                except Exception as e:
                    logger.warning(f"⚠️ Git config error: {cmd} - {e}")
            
            logger.info("✅ Git repository setup completed")
            return True
            
        except Exception as e:
            logger.error(f"❌ Git setup failed: {e}")
            return False
    
    def start_main_application(self):
        """Start the main application with monitoring"""
        logger.info("🚀 Starting main application...")
        
        try:
            # Start main.py
            self.main_process = subprocess.Popen(
                [sys.executable, 'main.py'],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                universal_newlines=True,
                bufsize=1
            )
            
            logger.info(f"✅ Main application started (PID: {self.main_process.pid})")
            
            # Start output monitoring
            threading.Thread(
                target=self.monitor_main_output,
                daemon=True,
                name="MainOutputMonitor"
            ).start()
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to start main application: {e}")
            return False
    
    def monitor_main_output(self):
        """Monitor main application output"""
        logger.info("👁️ Starting main application output monitor...")
        
        try:
            for line in iter(self.main_process.stdout.readline, ''):
                if line:
                    # Log application output
                    line = line.strip()
                    if line:
                        print(f"[MAIN] {line}")
                        
                        # Check for critical errors
                        if any(error in line.lower() for error in [
                            'critical error',
                            'application crashed',
                            'out of memory',
                            'segmentation fault'
                        ]):
                            logger.error(f"🚨 Critical error detected: {line}")
                            self.restart_application()
                            break
            
        except Exception as e:
            logger.error(f"❌ Output monitoring error: {e}")
    
    def start_auto_commit(self):
        """Start periodic auto-commit process"""
        logger.info("📝 Setting up auto-commit process...")
        
        def auto_commit_loop():
            """Auto-commit loop that runs every 5 minutes"""
            while self.monitoring_active:
                try:
                    # Wait 5 minutes between commits
                    for _ in range(300):  # 5 minutes = 300 seconds
                        if not self.monitoring_active:
                            break
                        time.sleep(1)
                    
                    if not self.monitoring_active:
                        break
                    
                    logger.info("📝 Running auto-commit...")
                    
                    # Run auto-commit script
                    result = subprocess.run(
                        [sys.executable, 'auto_commit.py'],
                        capture_output=True,
                        text=True,
                        timeout=600  # 10 minute timeout
                    )
                    
                    if result.returncode == 0:
                        logger.info("✅ Auto-commit completed successfully")
                    else:
                        logger.warning(f"⚠️ Auto-commit warning: {result.stderr}")
                    
                except subprocess.TimeoutExpired:
                    logger.error("⏰ Auto-commit timed out")
                except Exception as e:
                    logger.error(f"❌ Auto-commit error: {e}")
        
        # Start auto-commit thread
        auto_commit_thread = threading.Thread(
            target=auto_commit_loop,
            daemon=True,
            name="AutoCommitLoop"
        )
        auto_commit_thread.start()
        
        logger.info("✅ Auto-commit process started")
    
    def monitor_system_resources(self):
        """Monitor system resources and restart if needed"""
        logger.info("📊 Starting system resource monitor...")
        
        def resource_monitor_loop():
            while self.monitoring_active:
                try:
                    # Check every 2 minutes
                    time.sleep(120)
                    
                    if not self.monitoring_active:
                        break
                    
                    # Get system stats
                    memory = psutil.virtual_memory()
                    disk = psutil.disk_usage('.')
                    cpu = psutil.cpu_percent(interval=1)
                    
                    memory_percent = memory.percent
                    disk_free_gb = disk.free / (1024**3)
                    
                    logger.info(f"📊 Resources - CPU: {cpu:.1f}%, Memory: {memory_percent:.1f}%, Disk: {disk_free_gb:.2f}GB free")
                    
                    # Check for resource issues
                    if memory_percent > 90:
                        logger.warning("⚠️ High memory usage detected")
                        self.cleanup_resources()
                    
                    if disk_free_gb < 0.05:  # Less than 50MB
                        logger.warning("⚠️ Low disk space - cleaning up old files")
                        self.cleanup_old_files()
                    
                    # Check if main process is still alive
                    if self.main_process and self.main_process.poll() is not None:
                        logger.error("💀 Main application process died - restarting...")
                        self.restart_application()
                        break
                    
                except Exception as e:
                    logger.error(f"❌ Resource monitoring error: {e}")
        
        # Start resource monitor thread
        resource_thread = threading.Thread(
            target=resource_monitor_loop,
            daemon=True,
            name="ResourceMonitor"
        )
        resource_thread.start()
    
    def cleanup_resources(self):
        """Clean up system resources"""
        try:
            logger.info("🧹 Performing resource cleanup...")
            
            # Force garbage collection
            import gc
            gc.collect()
            
            # Clean up temporary files
            temp_patterns = [
                '/tmp/tmp*',
                '/tmp/ffmpeg*',
                '/tmp/youtube-dl*',
                'recordings/*.tmp'
            ]
            
            for pattern in temp_patterns:
                try:
                    subprocess.run(f'rm -f {pattern}', shell=True, timeout=10)
                except:
                    pass
            
            logger.info("✅ Resource cleanup completed")
            
        except Exception as e:
            logger.error(f"❌ Resource cleanup error: {e}")
    
    def cleanup_old_files(self):
        """Clean up old recording files if disk space is low"""
        try:
            logger.info("🗑️ Cleaning up old files...")
            
            # Don't clean if recordings directory doesn't exist
            if not os.path.exists('recordings'):
                return
            
            # Find files older than 1 hour
            current_time = time.time()
            files_removed = 0
            space_freed = 0
            
            for root, dirs, files in os.walk('recordings'):
                for file in files:
                    filepath = os.path.join(root, file)
                    try:
                        file_stat = os.stat(filepath)
                        file_age = current_time - file_stat.st_mtime
                        
                        # Remove files older than 1 hour
                        if file_age > 3600:  # 1 hour in seconds
                            file_size = file_stat.st_size
                            os.remove(filepath)
                            files_removed += 1
                            space_freed += file_size
                            logger.info(f"🗑️ Removed old file: {filepath} ({file_size/1024/1024:.1f}MB)")
                            
                    except Exception as e:
                        logger.debug(f"File cleanup error: {e}")
            
            if files_removed > 0:
                logger.info(f"✅ Cleaned {files_removed} files, freed {space_freed/1024/1024:.1f}MB")
            
        except Exception as e:
            logger.error(f"❌ Old file cleanup error: {e}")
    
    def restart_application(self):
        """Restart the main application"""
        if self.restart_count >= self.max_restarts:
            logger.error(f"❌ Maximum restart limit reached ({self.max_restarts})")
            self.shutdown()
            return
        
        logger.warning(f"🔄 Restarting application (attempt {self.restart_count + 1})")
        
        try:
            # Stop current process
            if self.main_process:
                try:
                    self.main_process.terminate()
                    self.main_process.wait(timeout=30)
                except subprocess.TimeoutExpired:
                    self.main_process.kill()
                except:
                    pass
            
            # Wait for cleanup
            time.sleep(10)
            
            # Restart
            if self.start_main_application():
                self.restart_count += 1
                logger.info(f"✅ Application restarted successfully")
            else:
                logger.error("❌ Failed to restart application")
                self.shutdown()
        
        except Exception as e:
            logger.error(f"❌ Restart error: {e}")
            self.shutdown()
    
    def run_health_checks(self):
        """Run periodic health checks"""
        logger.info("🏥 Starting health check monitor...")
        
        def health_check_loop():
            while self.monitoring_active:
                try:
                    time.sleep(180)  # Check every 3 minutes
                    
                    if not self.monitoring_active:
                        break
                    
                    # Check if main process is responsive
                    if self.main_process:
                        if self.main_process.poll() is not None:
                            logger.error("💀 Main process died - triggering restart")
                            self.restart_application()
                            break
                        
                        # Try to check if Flask is responding (simple check)
                        try:
                            import requests
                            port = os.environ.get('PORT', 5000)
                            response = requests.get(f'http://localhost:{port}/health', timeout=10)
                            if response.status_code == 200:
                                logger.info("✅ Health check passed")
                            else:
                                logger.warning(f"⚠️ Health check returned: {response.status_code}")
                        except Exception as health_error:
                            logger.warning(f"⚠️ Health check failed: {health_error}")
                    
                except Exception as e:
                    logger.error(f"❌ Health check error: {e}")
        
        # Start health check thread
        health_thread = threading.Thread(
            target=health_check_loop,
            daemon=True,
            name="HealthChecker"
        )
        health_thread.start()
    
    def setup_signal_handlers(self):
        """Setup signal handlers for graceful shutdown"""
        def signal_handler(sig, frame):
            logger.info(f"🛑 Received signal {sig} - shutting down gracefully...")
            self.shutdown()
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
    
    def shutdown(self):
        """Graceful shutdown"""
        logger.info("🛑 Starting graceful shutdown...")
        
        self.monitoring_active = False
        
        # Stop main process
        if self.main_process:
            try:
                logger.info("🛑 Stopping main application...")
                self.main_process.terminate()
                self.main_process.wait(timeout=30)
                logger.info("✅ Main application stopped")
            except subprocess.TimeoutExpired:
                logger.warning("🔪 Force killing main application...")
                self.main_process.kill()
            except Exception as e:
                logger.error(f"❌ Error stopping main application: {e}")
        
        # Final cleanup
        try:
            subprocess.run('pkill -f python', shell=True, timeout=10)
        except:
            pass
        
        logger.info("✅ Shutdown completed")
        sys.exit(0)
    
    def start(self):
        """Start the production manager"""
        logger.info("🚀 TikTok Livestream Recorder - Production Manager")
        logger.info("=" * 60)
        
        # Setup signal handlers
        self.setup_signal_handlers()
        
        # Verify environment
        if not self.verify_environment():
            logger.error("❌ Environment verification failed")
            sys.exit(1)
        
        # Setup Git repository
        if not self.setup_git_repository():
            logger.error("❌ Git setup failed")
            sys.exit(1)
        
        # Start main application
        if not self.start_main_application():
            logger.error("❌ Failed to start main application")
            sys.exit(1)
        
        # Start auto-commit process
        self.start_auto_commit()
        
        # Start resource monitoring
        self.monitor_system_resources()
        
        # Start health checks
        self.run_health_checks()
        
        logger.info("✅ Production manager fully initialized")
        logger.info("🔄 Monitoring application health and auto-committing changes...")
        
        # Main monitoring loop
        try:
            while self.monitoring_active:
                time.sleep(60)  # Check every minute
                
                # Log status periodically
                if datetime.now().minute % 10 == 0:  # Every 10 minutes
                    self.log_status()
                
        except KeyboardInterrupt:
            logger.info("🛑 Received keyboard interrupt")
        except Exception as e:
            logger.error(f"❌ Monitoring loop error: {e}")
        finally:
            self.shutdown()
    
    def log_status(self):
        """Log current system status"""
        try:
            uptime = time.time() - psutil.boot_time()
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage('.')
            
            logger.info(f"📊 Status - Uptime: {uptime/3600:.1f}h, Memory: {memory.percent:.1f}%, "
                       f"Disk: {disk.free/1024**3:.2f}GB free, Restarts: {self.restart_count}")
            
        except Exception as e:
            logger.debug(f"Status logging error: {e}")

def main():
    """Main entry point"""
    try:
        # Change to script directory
        script_dir = os.path.dirname(os.path.abspath(__file__))
        os.chdir(script_dir)
        
        # Initialize and start production manager
        manager = ProductionManager()
        manager.start()
        
    except Exception as e:
        logger.error(f"❌ Startup manager crashed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
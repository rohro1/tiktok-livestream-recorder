#!/usr/bin/env python3
"""
Production Launcher for TikTok Livestream Recorder
Ultimate reliability wrapper for 24/7 operation on Render
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
import tempfile
import shutil

# Configure logging for production
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - [%(levelname)s] - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),  # Use stdout for Render logs
        logging.FileHandler('production.log', mode='a')
    ]
)
logger = logging.getLogger(__name__)

class ProductionLauncher:
    """Production launcher with ultimate reliability features"""
    
    def __init__(self):
        self.start_time = datetime.now()
        self.restart_count = 0
        self.max_restarts = 20  # More restarts allowed
        self.main_process = None
        self.running = True
        
    def pre_flight_checks(self):
        """Comprehensive pre-flight checks"""
        logger.info("🔍 Running pre-flight checks...")
        
        checks = [
            self._check_python(),
            self._check_ffmpeg(),
            self._check_git(),
            self._check_dependencies(),
            self._check_disk_space(),
            self._setup_directories(),
            self._clean_environment()
        ]
        
        if all(checks):
            logger.info("✅ All pre-flight checks passed")
            return True
        else:
            logger.error("❌ Pre-flight checks failed")
            return False
    
    def _check_python(self):
        """Check Python installation"""
        try:
            version = sys.version
            logger.info(f"🐍 Python: {version.split()[0]}")
            return True
        except:
            logger.error("❌ Python check failed")
            return False
    
    def _check_ffmpeg(self):
        """Check FFmpeg installation"""
        try:
            result = subprocess.run(['ffmpeg', '-version'], 
                                  capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                version_line = result.stdout.split('\n')[0]
                logger.info(f"🎬 {version_line}")
                return True
            else:
                logger.error("❌ FFmpeg not working")
                return False
        except FileNotFoundError:
            logger.error("❌ FFmpeg not installed")
            return False
        except Exception as e:
            logger.error(f"❌ FFmpeg check error: {e}")
            return False
    
    def _check_git(self):
        """Check Git installation"""
        try:
            result = subprocess.run(['git', '--version'], 
                                  capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                logger.info(f"📋 {result.stdout.strip()}")
                return True
            else:
                logger.error("❌ Git not working")
                return False
        except Exception as e:
            logger.error(f"❌ Git check error: {e}")
            return False
    
    def _check_dependencies(self):
        """Check Python dependencies"""
        try:
            required_modules = [
                'flask', 'requests', 'yt_dlp', 'google.auth', 
                'psutil', 'google.oauth2', 'googleapiclient'
            ]
            
            for module in required_modules:
                try:
                    __import__(module.replace('.', '_'))
                    logger.info(f"✅ {module}")
                except ImportError:
                    logger.error(f"❌ Missing: {module}")
                    return False
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Dependency check error: {e}")
            return False
    
    def _check_disk_space(self):
        """Check available disk space"""
        try:
            disk = psutil.disk_usage('.')
            free_gb = disk.free / (1024**3)
            
            logger.info(f"💾 Disk space: {free_gb:.2f}GB free")
            
            if free_gb < 0.1:  # Less than 100MB
                logger.warning("⚠️ Very low disk space")
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Disk space check error: {e}")
            return False
    
    def _setup_directories(self):
        """Setup required directories"""
        try:
            directories = ['recordings', 'templates', 'logs']
            
            for directory in directories:
                os.makedirs(directory, exist_ok=True)
                logger.info(f"📁 Directory ready: {directory}")
            
            # Create usernames.txt if missing
            if not os.path.exists('usernames.txt'):
                with open('usernames.txt', 'w') as f:
                    f.write("# TikTok usernames to monitor (one per line)\n")
                logger.info("📝 Created usernames.txt")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Directory setup error: {e}")
            return False
    
    def _clean_environment(self):
        """Clean environment for fresh start"""
        try:
            logger.info("🧹 Cleaning environment...")
            
            # Kill any existing git processes
            try:
                subprocess.run('pkill -f git', shell=True, timeout=5)
            except:
                pass
            
            # Remove git lock files
            try:
                subprocess.run('find .git -name "*.lock" -delete', shell=True, timeout=10)
            except:
                pass
            
            # Clean temporary files
            temp_patterns = [
                '/tmp/tmp*',
                '/tmp/ffmpeg*',
                'recordings/*.tmp'
            ]
            
            for pattern in temp_patterns:
                try:
                    subprocess.run(f'rm -f {pattern}', shell=True, timeout=5)
                except:
                    pass
            
            time.sleep(2)  # Wait for cleanup
            
            logger.info("✅ Environment cleaned")
            return True
            
        except Exception as e:
            logger.error(f"❌ Environment cleanup error: {e}")
            return False
    
    def start_application(self):
        """Start the main application"""
        try:
            logger.info("🚀 Starting main application...")
            
            # Start main.py with proper buffering
            self.main_process = subprocess.Popen(
                [sys.executable, '-u', 'main.py'],  # -u for unbuffered output
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                universal_newlines=True,
                bufsize=1,
                env=dict(os.environ, PYTHONUNBUFFERED='1')
            )
            
            logger.info(f"✅ Application started (PID: {self.main_process.pid})")
            
            # Start output monitoring
            threading.Thread(
                target=self._monitor_output,
                daemon=True,
                name="OutputMonitor"
            ).start()
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to start application: {e}")
            return False
    
    def _monitor_output(self):
        """Monitor application output for issues"""
        logger.info("👁️ Starting application output monitor...")
        
        try:
            error_patterns = [
                'traceback',
                'error:',
                'exception:',
                'critical:',
                'fatal:',
                'crashed',
                'out of memory'
            ]
            
            success_patterns = [
                'server running',
                'application started',
                'monitoring started',
                'recording started'
            ]
            
            for line in iter(self.main_process.stdout.readline, ''):
                if not line:
                    break
                    
                line = line.strip()
                if line:
                    # Forward all output to our logger
                    print(f"[APP] {line}")
                    
                    # Check for error patterns
                    line_lower = line.lower()
                    
                    if any(pattern in line_lower for pattern in error_patterns):
                        logger.warning(f"⚠️ Error detected in app output: {line}")
                    
                    if any(pattern in line_lower for pattern in success_patterns):
                        logger.info(f"✅ Success indicator: {line}")
                        self.restart_count = 0  # Reset restart count on success
        
        except Exception as e:
            logger.error(f"❌ Output monitoring error: {e}")
    
    def health_check_loop(self):
        """Continuous health checking"""
        logger.info("🏥 Starting health check loop...")
        
        while self.running:
            try:
                # Wait 3 minutes between health checks
                time.sleep(180)
                
                if not self.running:
                    break
                
                # Check if main process is still alive
                if self.main_process:
                    if self.main_process.poll() is not None:
                        logger.error("💀 Main process died - restarting...")
                        self.restart_application()
                        continue
                
                # Try to check application health via HTTP
                try:
                    port = os.environ.get('PORT', 5000)
                    import requests
                    
                    response = requests.get(f'http://localhost:{port}/health', timeout=15)
                    
                    if response.status_code == 200:
                        health_data = response.json()
                        logger.info(f"✅ Health check OK - Status: {health_data.get('status')}")
                    else:
                        logger.warning(f"⚠️ Health check returned: {response.status_code}")
                        
                except Exception as health_error:
                    logger.warning(f"⚠️ Health endpoint unreachable: {health_error}")
                
                # Check system resources
                self._log_system_stats()
                
            except Exception as e:
                logger.error(f"❌ Health check loop error: {e}")
                time.sleep(60)  # Wait before retrying
    
    def _log_system_stats(self):
        """Log system statistics"""
        try:
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage('.')
            cpu = psutil.cpu_percent()
            uptime = datetime.now() - self.start_time
            
            logger.info(f"📊 System - CPU: {cpu:.1f}%, Memory: {memory.percent:.1f}%, "
                       f"Disk: {disk.free/1024**3:.2f}GB, Uptime: {str(uptime).split('.')[0]}")
            
        except Exception as e:
            logger.debug(f"Stats logging error: {e}")
    
    def restart_application(self):
        """Restart the application with exponential backoff"""
        if self.restart_count >= self.max_restarts:
            logger.error(f"❌ Maximum restarts reached ({self.max_restarts}) - giving up")
            self.shutdown()
            return False
        
        self.restart_count += 1
        backoff_time = min(30 * self.restart_count, 300)  # Max 5 minutes
        
        logger.warning(f"🔄 Restarting application (attempt {self.restart_count}) - waiting {backoff_time}s...")
        
        try:
            # Stop current process
            if self.main_process:
                try:
                    self.main_process.terminate()
                    self.main_process.wait(timeout=30)
                except subprocess.TimeoutExpired:
                    self.main_process.kill()
                    self.main_process.wait()
                except:
                    pass
            
            # Clean environment
            self._clean_environment()
            
            # Wait with backoff
            time.sleep(backoff_time)
            
            # Restart
            if self.start_application():
                logger.info(f"✅ Application restarted successfully (restart #{self.restart_count})")
                return True
            else:
                logger.error(f"❌ Failed to restart application (attempt {self.restart_count})")
                return False
                
        except Exception as e:
            logger.error(f"❌ Restart error: {e}")
            return False
    
    def setup_auto_commit(self):
        """Setup automatic Git commits"""
        def auto_commit_loop():
            logger.info("📝 Auto-commit loop started")
            
            while self.running:
                try:
                    # Wait 10 minutes between commits
                    for _ in range(600):
                        if not self.running:
                            break
                        time.sleep(1)
                    
                    if not self.running:
                        break
                    
                    logger.info("📝 Running auto-commit...")
                    
                    # Run auto-commit script
                    result = subprocess.run(
                        [sys.executable, 'auto_commit.py'],
                        capture_output=True,
                        text=True,
                        timeout=600,  # 10 minutes max
                        cwd=os.getcwd()
                    )
                    
                    if result.returncode == 0:
                        logger.info("✅ Auto-commit successful")
                    else:
                        logger.warning(f"⚠️ Auto-commit warning: {result.stderr}")
                    
                except subprocess.TimeoutExpired:
                    logger.error("⏰ Auto-commit timed out")
                except Exception as e:
                    logger.error(f"❌ Auto-commit error: {e}")
                
                # Small delay before next cycle
                time.sleep(60)
        
        # Start auto-commit thread
        auto_commit_thread = threading.Thread(
            target=auto_commit_loop,
            daemon=True,
            name="AutoCommitLoop"
        )
        auto_commit_thread.start()
        logger.info("✅ Auto-commit loop started")
    
    def setup_signal_handlers(self):
        """Setup graceful shutdown handlers"""
        def signal_handler(sig, frame):
            logger.info(f"🛑 Received signal {sig} - shutting down...")
            self.shutdown()
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
    
    def shutdown(self):
        """Graceful shutdown"""
        logger.info("🛑 Starting graceful shutdown...")
        
        self.running = False
        
        # Stop main process
        if self.main_process:
            try:
                logger.info("🛑 Stopping main application...")
                self.main_process.terminate()
                
                # Wait for graceful shutdown
                try:
                    self.main_process.wait(timeout=30)
                    logger.info("✅ Main application stopped gracefully")
                except subprocess.TimeoutExpired:
                    logger.warning("🔪 Force killing main application...")
                    self.main_process.kill()
                    self.main_process.wait()
                    
            except Exception as e:
                logger.error(f"❌ Error stopping main application: {e}")
        
        # Final cleanup
        try:
            # Kill any remaining Python processes
            subprocess.run('pkill -f "python.*main.py"', shell=True, timeout=10)
            
            # Clean up Git locks
            subprocess.run('find .git -name "*.lock" -delete', shell=True, timeout=5)
            
        except:
            pass
        
        uptime = datetime.now() - self.start_time
        logger.info(f"✅ Shutdown completed - Total uptime: {str(uptime).split('.')[0]}")
        logger.info(f"📊 Total restarts: {self.restart_count}")
        
        sys.exit(0)
    
    def run(self):
        """Main run method"""
        logger.info("🚀 TikTok Livestream Recorder - Production Launcher")
        logger.info("=" * 70)
        logger.info(f"🕐 Start time: {self.start_time}")
        logger.info(f"📍 Working directory: {os.getcwd()}")
        logger.info(f"🔧 Environment: {os.environ.get('RENDER', 'Unknown')}")
        
        # Setup signal handlers
        self.setup_signal_handlers()
        
        # Run pre-flight checks
        if not self.pre_flight_checks():
            logger.error("❌ Pre-flight checks failed - cannot start")
            sys.exit(1)
        
        # Start main application
        if not self.start_application():
            logger.error("❌ Failed to start application")
            sys.exit(1)
        
        # Setup auto-commit
        self.setup_auto_commit()
        
        # Start health monitoring
        health_thread = threading.Thread(
            target=self.health_check_loop,
            daemon=True,
            name="HealthMonitor"
        )
        health_thread.start()
        
        logger.info("✅ Production launcher fully initialized")
        logger.info("🔄 Monitoring application health...")
        
        # Main monitoring loop
        try:
            while self.running:
                # Log status every 30 minutes
                if datetime.now().minute % 30 == 0:
                    uptime = datetime.now() - self.start_time
                    memory = psutil.virtual_memory()
                    logger.info(f"📊 Status - Uptime: {str(uptime).split('.')[0]}, "
                               f"Memory: {memory.percent:.1f}%, Restarts: {self.restart_count}")
                
                time.sleep(60)  # Check every minute
                
        except KeyboardInterrupt:
            logger.info("🛑 Received keyboard interrupt")
        except Exception as e:
            logger.error(f"❌ Main loop error: {e}")
        finally:
            self.shutdown()

def main():
    """Entry point"""
    try:
        # Ensure we're in the right directory
        script_dir = os.path.dirname(os.path.abspath(__file__))
        os.chdir(script_dir)
        
        # Start production launcher
        launcher = ProductionLauncher()
        launcher.run()
        
    except Exception as e:
        logger.error(f"❌ Production launcher crashed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()

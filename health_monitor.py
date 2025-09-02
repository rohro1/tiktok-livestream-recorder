#!/usr/bin/env python3
"""
Health Monitor for TikTok Livestream Recorder
Monitors system health and automatically fixes common issues
"""

import os
import time
import logging
import psutil
import subprocess
import requests
from datetime import datetime, timedelta
import threading
import json

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('health_monitor.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class HealthMonitor:
    """24/7 Health monitoring and auto-recovery system"""
    
    def __init__(self):
        self.monitoring_active = True
        self.last_health_check = datetime.now()
        self.consecutive_failures = 0
        self.max_failures = 5
        
    def check_application_health(self):
        """Check if the main application is healthy"""
        try:
            port = os.environ.get('PORT', 5000)
            
            # Try to connect to health endpoint
            response = requests.get(f'http://localhost:{port}/health', timeout=15)
            
            if response.status_code == 200:
                health_data = response.json()
                
                if health_data.get('status') == 'healthy':
                    self.consecutive_failures = 0
                    logger.info("✅ Application health check passed")
                    return True
                else:
                    logger.warning(f"⚠️ Application status: {health_data.get('status')}")
                    return False
            else:
                logger.warning(f"⚠️ Health endpoint returned: {response.status_code}")
                return False
                
        except requests.exceptions.ConnectionError:
            logger.error("❌ Cannot connect to application - may be down")
            return False
        except Exception as e:
            logger.error(f"❌ Health check error: {e}")
            return False
    
    def check_system_resources(self):
        """Check system resource usage"""
        try:
            # Memory check
            memory = psutil.virtual_memory()
            if memory.percent > 95:
                logger.warning(f"⚠️ High memory usage: {memory.percent:.1f}%")
                self.cleanup_memory()
            
            # Disk check
            disk = psutil.disk_usage('.')
            free_gb = disk.free / (1024**3)
            if free_gb < 0.1:  # Less than 100MB
                logger.warning(f"⚠️ Low disk space: {free_gb:.3f}GB")
                self.cleanup_disk_space()
            
            # CPU check
            cpu_percent = psutil.cpu_percent(interval=1)
            if cpu_percent > 95:
                logger.warning(f"⚠️ High CPU usage: {cpu_percent:.1f}%")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ System resource check error: {e}")
            return False
    
    def cleanup_memory(self):
        """Clean up memory usage"""
        try:
            logger.info("🧹 Performing memory cleanup...")
            
            # Kill unnecessary processes
            for proc in psutil.process_iter(['pid', 'name', 'memory_percent']):
                try:
                    if proc.info['memory_percent'] > 10 and proc.info['name'] in ['chrome', 'firefox']:
                        proc.terminate()
                        logger.info(f"🔪 Terminated high-memory process: {proc.info['name']}")
                except:
                    pass
            
            # Python garbage collection
            import gc
            collected = gc.collect()
            logger.info(f"🗑️ Garbage collected: {collected} objects")
            
        except Exception as e:
            logger.error(f"❌ Memory cleanup error: {e}")
    
    def cleanup_disk_space(self):
        """Clean up disk space"""
        try:
            logger.info("🗑️ Performing disk cleanup...")
            
            # Clean temporary files
            cleanup_commands = [
                'find /tmp -type f -mtime +1 -delete',
                'find recordings -name "*.tmp" -delete',
                'find . -name "*.log" -size +10M -mtime +7 -delete'
            ]
            
            for cmd in cleanup_commands:
                try:
                    subprocess.run(cmd, shell=True, timeout=30)
                except:
                    pass
            
            logger.info("✅ Disk cleanup completed")
            
        except Exception as e:
            logger.error(f"❌ Disk cleanup error: {e}")
    
    def fix_git_issues(self):
        """Fix common Git issues"""
        try:
            logger.info("🔧 Checking and fixing Git issues...")
            
            # Kill hanging git processes
            subprocess.run('pkill -f git', shell=True, timeout=10)
            
            # Remove lock files
            subprocess.run('find .git -name "*.lock" -delete', shell=True, timeout=10)
            
            # Reset Git state if needed
            result = subprocess.run('git status', shell=True, capture_output=True, text=True, timeout=15)
            if result.returncode != 0:
                logger.warning("🔄 Resetting Git state...")
                subprocess.run('git reset --hard HEAD', shell=True, timeout=30)
            
            logger.info("✅ Git issues fixed")
            
        except Exception as e:
            logger.error(f"❌ Git fix error: {e}")
    
    def auto_recovery(self):
        """Attempt automatic recovery"""
        try:
            logger.warning("🚑 Attempting automatic recovery...")
            
            # Step 1: Fix Git issues
            self.fix_git_issues()
            
            # Step 2: Clean resources
            self.cleanup_memory()
            self.cleanup_disk_space()
            
            # Step 3: Wait and test
            time.sleep(30)
            
            if self.check_application_health():
                logger.info("✅ Auto-recovery successful")
                self.consecutive_failures = 0
                return True
            else:
                logger.error("❌ Auto-recovery failed")
                return False
                
        except Exception as e:
            logger.error(f"❌ Auto-recovery error: {e}")
            return False
    
    def monitor_loop(self):
        """Main monitoring loop"""
        logger.info("🔄 Health monitoring started")
        
        while self.monitoring_active:
            try:
                # Update last check time
                self.last_health_check = datetime.now()
                
                # Check application health
                app_healthy = self.check_application_health()
                
                # Check system resources
                system_healthy = self.check_system_resources()
                
                if not app_healthy:
                    self.consecutive_failures += 1
                    logger.warning(f"⚠️ Application unhealthy (failure {self.consecutive_failures})")
                    
                    if self.consecutive_failures >= self.max_failures:
                        logger.error("🚨 Too many consecutive failures - attempting recovery")
                        
                        if not self.auto_recovery():
                            logger.error("💀 Recovery failed - system may need manual intervention")
                            # Don't exit - keep trying
                            self.consecutive_failures = 0  # Reset to continue trying
                
                # Log periodic status
                if datetime.now().minute % 15 == 0:  # Every 15 minutes
                    memory = psutil.virtual_memory()
                    disk = psutil.disk_usage('.')
                    logger.info(f"📊 System Status - Memory: {memory.percent:.1f}%, "
                               f"Disk: {disk.free/1024**3:.2f}GB free, "
                               f"Failures: {self.consecutive_failures}")
                
                # Sleep before next check
                time.sleep(120)  # Check every 2 minutes
                
            except Exception as e:
                logger.error(f"❌ Monitor loop error: {e}")
                time.sleep(60)  # Wait before retrying
    
    def start(self):
        """Start the health monitor"""
        logger.info("🏥 Starting 24/7 health monitor...")
        
        try:
            # Start monitoring in separate thread
            monitor_thread = threading.Thread(
                target=self.monitor_loop,
                daemon=True,
                name="HealthMonitor"
            )
            monitor_thread.start()
            
            # Keep main thread alive
            while self.monitoring_active:
                time.sleep(60)
                
        except KeyboardInterrupt:
            logger.info("🛑 Health monitor interrupted")
        except Exception as e:
            logger.error(f"❌ Health monitor error: {e}")
        finally:
            self.monitoring_active = False

def main():
    """Main entry point for health monitor"""
    try:
        monitor = HealthMonitor()
        monitor.start()
        
    except Exception as e:
        logger.error(f"❌ Health monitor startup failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()

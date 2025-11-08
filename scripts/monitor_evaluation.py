#!/usr/bin/env python3
"""Real-time monitor for evaluation backtest.

Monitors the log file for errors, progress updates, and provides alerts.
Can run in the background or foreground.
"""

import os
import re
import sys
import time
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict
from collections import deque


class EvaluationMonitor:
    """Monitor evaluation backtest log file for errors and progress."""
    
    ERROR_PATTERNS = [
        r'✗\s+ERROR',
        r'ERROR:',
        r'Exception:',
        r'Traceback',
        r'ImportError',
        r'ValueError',
        r'KeyError',
        r'AttributeError',
        r'TypeError',
        r'RuntimeError',
        r'Failed',
        r'failed',
        r'FATAL',
    ]
    
    WARNING_PATTERNS = [
        r'⚠',
        r'WARNING',
        r'Warning',
        r'warning',
    ]
    
    PROGRESS_PATTERNS = [
        r'Progress:\s+(\d+\.?\d*)%',
        r'Progress:\s+(\d+)/(\d+)',
    ]
    
    COMPLETION_PATTERNS = [
        r'✓.*completed successfully',
        r'Evaluation completed',
        r'Backtest complete',
    ]
    
    def __init__(self, log_file: Path = Path("/tmp/full_evaluation.log")):
        """Initialize monitor.
        
        Args:
            log_file: Path to log file to monitor
        """
        self.log_file = log_file
        self.error_count = 0
        self.warning_count = 0
        self.last_position = 0
        self.error_history: deque = deque(maxlen=50)
        self.warning_history: deque = deque(maxlen=50)
        self.progress_updates: deque = deque(maxlen=20)
        self.start_time = datetime.now()
        self.last_update_time = datetime.now()
        
    def check_process_running(self) -> tuple[bool, Optional[List[str]]]:
        """Check if evaluation process is running.
        
        Returns:
            Tuple of (is_running, list of PIDs)
        """
        try:
            result = subprocess.run(
                ['pgrep', '-f', 'run_evaluation_backtest.py'],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if result.returncode == 0 and result.stdout.strip():
                pids = [p.strip() for p in result.stdout.strip().split('\n') if p.strip()]
                return True, pids
            return False, []
        except Exception:
            return False, []
    
    def get_process_stats(self, pid: str) -> Optional[Dict]:
        """Get process statistics.
        
        Args:
            pid: Process ID
            
        Returns:
            Dictionary with process stats or None
        """
        try:
            result = subprocess.run(
                ['ps', '-p', pid, '-o', 'pcpu,pmem,etime,state'],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if result.returncode == 0:
                lines = result.stdout.strip().split('\n')
                if len(lines) > 1:
                    parts = lines[1].split()
                    if len(parts) >= 4:
                        return {
                            'cpu_pct': float(parts[0]),
                            'mem_pct': float(parts[1]),
                            'elapsed': parts[2],
                            'state': parts[3],
                        }
        except Exception:
            pass
        return None
    
    def scan_log(self) -> Dict:
        """Scan log file for new content.
        
        Returns:
            Dictionary with scan results
        """
        if not self.log_file.exists():
            return {
                'new_lines': [],
                'errors': [],
                'warnings': [],
                'progress': [],
                'completion': False,
            }
        
        try:
            with open(self.log_file, 'r', encoding='utf-8', errors='ignore') as f:
                # Seek to last position
                f.seek(self.last_position)
                new_lines = f.readlines()
                self.last_position = f.tell()
                
                errors = []
                warnings = []
                progress = []
                completion = False
                
                for line in new_lines:
                    line = line.rstrip()
                    
                    # Check for errors
                    for pattern in self.ERROR_PATTERNS:
                        if re.search(pattern, line):
                            errors.append(line)
                            self.error_count += 1
                            self.error_history.append({
                                'time': datetime.now(),
                                'line': line,
                            })
                            break
                    
                    # Check for warnings
                    for pattern in self.WARNING_PATTERNS:
                        if re.search(pattern, line):
                            warnings.append(line)
                            self.warning_count += 1
                            self.warning_history.append({
                                'time': datetime.now(),
                                'line': line,
                            })
                            break
                    
                    # Check for progress
                    for pattern in self.PROGRESS_PATTERNS:
                        match = re.search(pattern, line)
                        if match:
                            progress.append(line)
                            self.progress_updates.append({
                                'time': datetime.now(),
                                'line': line,
                            })
                            break
                    
                    # Check for completion
                    for pattern in self.COMPLETION_PATTERNS:
                        if re.search(pattern, line):
                            completion = True
                            break
                
                if new_lines:
                    self.last_update_time = datetime.now()
                
                return {
                    'new_lines': new_lines,
                    'errors': errors,
                    'warnings': warnings,
                    'progress': progress,
                    'completion': completion,
                }
        except Exception as e:
            return {
                'new_lines': [],
                'errors': [f"Error reading log: {e}"],
                'warnings': [],
                'progress': [],
                'completion': False,
            }
    
    def print_status(self, scan_result: Dict, process_running: bool, process_stats: Optional[Dict] = None):
        """Print current status.
        
        Args:
            scan_result: Result from scan_log()
            process_running: Whether process is running
            process_stats: Optional process statistics
        """
        # Clear screen (optional - comment out if you want to keep history)
        # os.system('clear')
        
        print("\n" + "=" * 80)
        print(f"EVALUATION BACKTEST MONITOR - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 80)
        
        # Process status
        if process_running:
            print(f"✓ Process Status: RUNNING")
            if process_stats:
                print(f"  CPU: {process_stats['cpu_pct']:.1f}% | "
                      f"Memory: {process_stats['mem_pct']:.1f}% | "
                      f"Elapsed: {process_stats['elapsed']} | "
                      f"State: {process_stats['state']}")
        else:
            print(f"✗ Process Status: NOT RUNNING")
        
        # Log file status
        if self.log_file.exists():
            size = self.log_file.stat().st_size
            print(f"✓ Log File: {self.log_file} ({size/1024:.1f} KB)")
        else:
            print(f"✗ Log File: NOT FOUND")
        
        # Statistics
        uptime = datetime.now() - self.start_time
        time_since_update = datetime.now() - self.last_update_time
        
        print(f"\nMonitor Uptime: {uptime}")
        print(f"Last Log Update: {time_since_update.total_seconds():.0f} seconds ago")
        print(f"Total Errors: {self.error_count}")
        print(f"Total Warnings: {self.warning_count}")
        
        # Recent progress
        if self.progress_updates:
            print(f"\n📊 Recent Progress Updates:")
            for update in list(self.progress_updates)[-5:]:
                time_str = update['time'].strftime('%H:%M:%S')
                print(f"  [{time_str}] {update['line']}")
        
        # New errors
        if scan_result['errors']:
            print(f"\n🚨 NEW ERRORS ({len(scan_result['errors'])}):")
            for error in scan_result['errors'][-10:]:
                print(f"  ✗ {error}")
        
        # New warnings
        if scan_result['warnings']:
            print(f"\n⚠️  NEW WARNINGS ({len(scan_result['warnings'])}):")
            for warning in scan_result['warnings'][-5:]:
                print(f"  ⚠ {warning}")
        
        # Recent errors from history
        if self.error_history:
            print(f"\n📋 Recent Error History (last 5):")
            for error in list(self.error_history)[-5:]:
                time_str = error['time'].strftime('%H:%M:%S')
                print(f"  [{time_str}] {error['line'][:100]}")
        
        # Completion status
        if scan_result['completion']:
            print(f"\n🎉 BACKTEST COMPLETED!")
        
        # Stale log warning
        if time_since_update.total_seconds() > 300 and process_running:  # 5 minutes
            print(f"\n⚠️  WARNING: Log file hasn't been updated in {time_since_update.total_seconds()/60:.1f} minutes")
            print("   Process may be hung or waiting on something")
        
        print("\n" + "=" * 80)
        print("Press Ctrl+C to stop monitoring")
        print("=" * 80)
    
    def monitor(self, interval: float = 5.0, alert_on_error: bool = True):
        """Monitor log file continuously.
        
        Args:
            interval: Seconds between checks
            alert_on_error: Whether to alert on errors
        """
        print("Starting evaluation monitor...")
        print(f"Monitoring: {self.log_file}")
        print(f"Check interval: {interval} seconds")
        print(f"Press Ctrl+C to stop\n")
        
        try:
            while True:
                # Check if process is running
                process_running, pids = self.check_process_running()
                process_stats = None
                if pids:
                    process_stats = self.get_process_stats(pids[0])
                
                # Scan log for new content
                scan_result = self.scan_log()
                
                # Print status
                self.print_status(scan_result, process_running, process_stats)
                
                # Alert on errors
                if alert_on_error and scan_result['errors']:
                    print("\n🔔 ALERT: ERRORS DETECTED!")
                    for error in scan_result['errors']:
                        print(f"   {error}")
                    print()  # Extra line for visibility
                
                # Check if completed
                if scan_result['completion']:
                    print("\n✓ Backtest completed successfully!")
                    break
                
                # Check if process stopped
                if not process_running and self.error_count == 0:
                    print("\n⚠️  Process stopped but no errors detected.")
                    print("   Check log file for completion message.")
                    break
                
                # Wait before next check
                time.sleep(interval)
                
        except KeyboardInterrupt:
            print("\n\nMonitor stopped by user")
            print(f"Total errors detected: {self.error_count}")
            print(f"Total warnings detected: {self.warning_count}")


def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Monitor evaluation backtest log file"
    )
    parser.add_argument(
        '--log-file',
        type=Path,
        default=Path("/tmp/full_evaluation.log"),
        help="Path to log file (default: /tmp/full_evaluation.log)"
    )
    parser.add_argument(
        '--interval',
        type=float,
        default=5.0,
        help="Check interval in seconds (default: 5.0)"
    )
    parser.add_argument(
        '--no-alert',
        action='store_true',
        help="Don't alert on errors"
    )
    parser.add_argument(
        '--once',
        action='store_true',
        help="Check once and exit (don't monitor continuously)"
    )
    
    args = parser.parse_args()
    
    monitor = EvaluationMonitor(log_file=args.log_file)
    
    if args.once:
        # Single check
        process_running, pids = monitor.check_process_running()
        process_stats = None
        if pids:
            process_stats = monitor.get_process_stats(pids[0])
        scan_result = monitor.scan_log()
        monitor.print_status(scan_result, process_running, process_stats)
    else:
        # Continuous monitoring
        monitor.monitor(
            interval=args.interval,
            alert_on_error=not args.no_alert
        )


if __name__ == "__main__":
    main()

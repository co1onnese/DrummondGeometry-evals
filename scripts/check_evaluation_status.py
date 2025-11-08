#!/usr/bin/env python3
"""Check status of evaluation backtest process."""

import subprocess
import sys
from pathlib import Path

def check_process_status():
    """Check if evaluation process is running and its CPU usage."""
    try:
        # Check for running processes
        result = subprocess.run(
            ['pgrep', '-f', 'run_evaluation_backtest.py'],
            capture_output=True,
            text=True
        )
        
        if result.returncode != 0:
            print("❌ No evaluation process found running")
            return False
        
        pids = result.stdout.strip().split('\n')
        pids = [p for p in pids if p]
        
        if not pids:
            print("❌ No evaluation process found running")
            return False
        
        print(f"✓ Found {len(pids)} evaluation process(es)")
        print()
        
        # Get detailed info for each process
        for pid in pids:
            try:
                ps_result = subprocess.run(
                    ['ps', '-p', pid, '-o', 'pid,pcpu,pmem,etime,state,cmd'],
                    capture_output=True,
                    text=True
                )
                if ps_result.returncode == 0:
                    lines = ps_result.stdout.strip().split('\n')
                    if len(lines) > 1:
                        print("Process Details:")
                        print(f"  {lines[0]}")  # Header
                        print(f"  {lines[1]}")   # Data
                        
                        # Parse CPU usage
                        parts = lines[1].split()
                        if len(parts) >= 2:
                            cpu_pct = float(parts[1])
                            mem_pct = float(parts[2])
                            elapsed = parts[3]
                            state = parts[4]
                            
                            print()
                            print(f"CPU Usage: {cpu_pct}%")
                            print(f"Memory Usage: {mem_pct}%")
                            print(f"Elapsed Time: {elapsed}")
                            print(f"State: {state}")
                            
                            if cpu_pct < 10:
                                print("⚠ WARNING: CPU usage is very low - process may be hung or waiting")
                            elif cpu_pct > 50:
                                print("✓ CPU usage is good - process is actively working")
                            else:
                                print("ℹ CPU usage is moderate")
            except Exception as e:
                print(f"Error getting details for PID {pid}: {e}")
        
        return True
        
    except Exception as e:
        print(f"Error checking process: {e}")
        return False

def check_log_file():
    """Check evaluation log file for progress."""
    log_file = Path("/tmp/full_evaluation.log")
    
    if not log_file.exists():
        print("\n❌ No log file found at /tmp/full_evaluation.log")
        return
    
    print(f"\n=== Log File Status ===")
    print(f"File: {log_file}")
    print(f"Size: {log_file.stat().st_size / 1024:.1f} KB")
    
    # Read last 50 lines
    try:
        with open(log_file, 'r') as f:
            lines = f.readlines()
            if lines:
                print(f"Total lines: {len(lines)}")
                print("\nLast 30 lines:")
                print("".join(lines[-30:]))
            else:
                print("Log file is empty")
    except Exception as e:
        print(f"Error reading log: {e}")

def check_cpu_count():
    """Check available CPUs."""
    try:
        import os
        cpu_count = os.cpu_count()
        print(f"\n=== System Info ===")
        print(f"Available CPUs: {cpu_count}")
        
        # Check how many workers the code would use
        print(f"\nExpected worker configuration:")
        print(f"  Indicator calculation: min(cpu_count, symbol_count, 8)")
        print(f"  For 101 symbols: min({cpu_count}, 101, 8) = {min(cpu_count, 101, 8)} workers")
    except Exception as e:
        print(f"Error checking CPU count: {e}")

if __name__ == "__main__":
    print("=" * 80)
    print("EVALUATION BACKTEST STATUS CHECK")
    print("=" * 80)
    print()
    
    check_cpu_count()
    print()
    
    is_running = check_process_status()
    print()
    
    if is_running:
        check_log_file()
    else:
        print("\nTo start the evaluation:")
        print("  cd /opt/DrummondGeometry-evals")
        print("  source .venv/bin/activate")
        print("  nohup python -u scripts/run_evaluation_backtest.py > /tmp/full_evaluation.log 2>&1 &")

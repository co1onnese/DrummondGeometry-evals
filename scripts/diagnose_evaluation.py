#!/usr/bin/env python3
"""Diagnose evaluation backtest process status."""

import os
import sys
import subprocess
from pathlib import Path

def check_process():
    """Check if evaluation process is running."""
    try:
        result = subprocess.run(
            ['pgrep', '-f', 'run_evaluation_backtest.py'],
            capture_output=True,
            text=True,
            timeout=5
        )
        
        if result.returncode == 0 and result.stdout.strip():
            pids = [p.strip() for p in result.stdout.strip().split('\n') if p.strip()]
            print(f"✓ Found {len(pids)} process(es) running")
            for pid in pids:
                try:
                    ps_result = subprocess.run(
                        ['ps', '-p', pid, '-o', 'pid,pcpu,pmem,etime,state,cmd'],
                        capture_output=True,
                        text=True,
                        timeout=5
                    )
                    if ps_result.returncode == 0:
                        print(f"\nProcess {pid}:")
                        print(ps_result.stdout)
                except Exception as e:
                    print(f"Error getting details for PID {pid}: {e}")
            return True, pids
        else:
            print("✗ No evaluation process found running")
            return False, []
    except Exception as e:
        print(f"Error checking process: {e}")
        return False, []

def check_log_file():
    """Check log file status."""
    log_path = Path("/tmp/full_evaluation.log")
    
    if not log_path.exists():
        print(f"\n✗ Log file does not exist: {log_path}")
        return False
    
    try:
        size = log_path.stat().st_size
        print(f"\n✓ Log file exists: {log_path}")
        print(f"  Size: {size:,} bytes ({size/1024:.1f} KB)")
        
        if size == 0:
            print("  ⚠ WARNING: Log file is empty!")
            return False
        
        # Read last 100 lines
        with open(log_path, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()
            print(f"  Lines: {len(lines)}")
            
            if lines:
                print(f"\n  Last 30 lines:")
                print("  " + "-" * 76)
                for line in lines[-30:]:
                    print(f"  {line.rstrip()}")
                print("  " + "-" * 76)
            else:
                print("  ⚠ WARNING: Log file appears empty!")
                return False
        
        return True
    except Exception as e:
        print(f"  ✗ Error reading log file: {e}")
        return False

def check_stderr():
    """Check for stderr output."""
    stderr_path = Path("/tmp/full_evaluation_stderr.log")
    if stderr_path.exists():
        print(f"\n✓ Found stderr log: {stderr_path}")
        try:
            with open(stderr_path, 'r', encoding='utf-8', errors='ignore') as f:
                stderr_lines = f.readlines()
                if stderr_lines:
                    print(f"  Last 20 stderr lines:")
                    print("  " + "-" * 76)
                    for line in stderr_lines[-20:]:
                        print(f"  {line.rstrip()}")
                    print("  " + "-" * 76)
        except Exception as e:
            print(f"  Error reading stderr: {e}")

def check_script():
    """Check if script file exists and is executable."""
    script_path = Path(__file__).parent / "run_evaluation_backtest.py"
    if script_path.exists():
        print(f"\n✓ Script exists: {script_path}")
        return True
    else:
        print(f"\n✗ Script not found: {script_path}")
        return False

def check_imports():
    """Check if script can be imported (syntax check)."""
    script_path = Path(__file__).parent / "run_evaluation_backtest.py"
    try:
        import ast
        with open(script_path, 'r') as f:
            ast.parse(f.read())
        print("✓ Script syntax is valid")
        return True
    except SyntaxError as e:
        print(f"✗ Script has syntax error: {e}")
        return False
    except Exception as e:
        print(f"✗ Error checking script: {e}")
        return False

def test_early_execution():
    """Test if script can execute up to first print statement."""
    script_path = Path(__file__).parent / "run_evaluation_backtest.py"
    try:
        # Try to import and run just the initial setup
        result = subprocess.run(
            [sys.executable, str(script_path)],
            capture_output=True,
            text=True,
            timeout=30,
            cwd=str(script_path.parent.parent)
        )
        
        print(f"\nTest execution (first 30 seconds):")
        print(f"  Return code: {result.returncode}")
        if result.stdout:
            print(f"  Stdout ({len(result.stdout)} chars):")
            print("  " + "-" * 76)
            for line in result.stdout.split('\n')[:20]:
                print(f"  {line}")
            print("  " + "-" * 76)
        if result.stderr:
            print(f"  Stderr ({len(result.stderr)} chars):")
            print("  " + "-" * 76)
            for line in result.stderr.split('\n')[:20]:
                print(f"  {line}")
            print("  " + "-" * 76)
            
    except subprocess.TimeoutExpired:
        print("  ⚠ Script is still running after 30 seconds (this is expected)")
    except Exception as e:
        print(f"  ✗ Error testing execution: {e}")

if __name__ == "__main__":
    print("=" * 80)
    print("EVALUATION BACKTEST DIAGNOSTIC")
    print("=" * 80)
    
    # Check script
    script_ok = check_script()
    if script_ok:
        check_imports()
    
    # Check process
    is_running, pids = check_process()
    
    # Check log
    log_ok = check_log_file()
    
    # Check stderr
    check_stderr()
    
    # Summary
    print("\n" + "=" * 80)
    print("DIAGNOSIS SUMMARY")
    print("=" * 80)
    
    if not is_running:
        print("\n❌ PROBLEM: Process is not running")
        print("   Possible causes:")
        print("   1. Process crashed or was killed")
        print("   2. Process never started")
        print("   3. Process finished (check log for completion)")
        
        if not log_ok:
            print("\n⚠ Log file is empty or missing - process likely never started or crashed immediately")
            print("\nRecommendation: Try running the script directly to see errors:")
            print("  cd /opt/DrummondGeometry-evals")
            print("  source .venv/bin/activate")
            print("  python -u scripts/run_evaluation_backtest.py")
    else:
        if not log_ok:
            print("\n⚠ PROBLEM: Process is running but log file is empty or not updating")
            print("   Possible causes:")
            print("   1. Output buffering (should be fixed with -u flag)")
            print("   2. Process is hung/deadlocked")
            print("   3. Process is waiting on something (database, I/O)")
            print("   4. Process crashed but hasn't exited yet")
            print("\nRecommendation: Check process state and CPU usage above")
        else:
            print("\n✓ Process is running and log file has content")
            print("   Check log output above for progress or errors")

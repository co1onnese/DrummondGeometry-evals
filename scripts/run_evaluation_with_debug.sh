#!/bin/bash
# Wrapper script to run evaluation with better error capture

set -e

cd /opt/DrummondGeometry-evals
source .venv/bin/activate

# Set unbuffered output
export PYTHONUNBUFFERED=1

# Run with both stdout and stderr captured
echo "Starting evaluation backtest at $(date)" | tee -a /tmp/full_evaluation.log
echo "PID: $$" | tee -a /tmp/full_evaluation.log
echo "---" | tee -a /tmp/full_evaluation.log

python3 -u scripts/run_evaluation_backtest.py >> /tmp/full_evaluation.log 2>&1
EXIT_CODE=$?

echo "---" | tee -a /tmp/full_evaluation.log
echo "Evaluation completed at $(date) with exit code: $EXIT_CODE" | tee -a /tmp/full_evaluation.log

exit $EXIT_CODE

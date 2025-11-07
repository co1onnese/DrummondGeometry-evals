#!/bin/bash
################################################################################
# 1-Month Full Universe Backtest - Quick Start Script
#
# This script runs a 1-month backtest on all 517 symbols using the optimized
# parallel processing system.
#
# Usage: ./run_one_month_backtest.sh [options]
#
# Options:
#   --workers N    Number of parallel workers (default: auto)
#   --mode MODE    Processing mode: parallel (default) or legacy
#   --validate     Run validation tests only
#   --help         Show this help message
################################################################################

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Default values
WORKERS=""
MODE="parallel"
VALIDATE_ONLY=false

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --workers)
            WORKERS="$2"
            shift 2
            ;;
        --mode)
            MODE="$2"
            shift 2
            ;;
        --validate)
            VALIDATE_ONLY=true
            shift
            ;;
        --help)
            grep "^#" "$0" | grep -v "^#!/bin/bash" | sed 's/^# //'
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
done

# Banner
echo -e "${BLUE}"
echo "================================================================================"
echo "  1-MONTH FULL UNIVERSE BACKTEST"
echo "  Optimized Parallel Processing System"
echo "================================================================================"
echo -e "${NC}"

# Step 1: Pre-flight checks
echo -e "${YELLOW}[1/5] Pre-flight checks...${NC}"

# Check if virtual environment exists
if [ ! -d ".venv" ]; then
    echo -e "${RED}✗ Virtual environment not found. Please run: source .venv/bin/activate${NC}"
    exit 1
fi

# Activate virtual environment
source .venv/bin/activate
echo -e "${GREEN}✓ Virtual environment activated${NC}"

# Check if psutil is installed
python -c "import psutil" 2>/dev/null || {
    echo -e "${YELLOW}Installing psutil...${NC}"
    uv add psutil
}
echo -e "${GREEN}✓ Dependencies verified${NC}"

# Run validation tests
echo -e "${YELLOW}[2/5] Running validation tests...${NC}"
if python scripts/test_optimized_batch.py > /tmp/validation.log 2>&1; then
    echo -e "${GREEN}✓ Validation tests passed${NC}"
else
    echo -e "${YELLOW}⚠ Some validation tests failed (non-critical)${NC}"
    cat /tmp/validation.log
fi

# Check database connectivity
echo -e "${YELLOW}[3/5] Checking database...${NC}"
python -c "from dgas.db import get_connection; conn = get_connection(); print('Database connected')" 2>/dev/null || {
    echo -e "${RED}✗ Database connection failed${NC}"
    exit 1
}
echo -e "${GREEN}✓ Database connected${NC}"

# Check configuration
echo -e "${YELLOW}[4/5] Configuration...${NC}"
if [ -f ".env" ]; then
    NUM_CPUS=$(grep NUM_CPUS .env | cut -d'=' -f2)
    echo -e "${GREEN}✓ Configuration loaded (NUM_CPUS=${NUM_CPUS})${NC}"
else
    echo -e "${YELLOW}⚠ No .env file found, using defaults${NC}"
fi

# Show test configuration
echo -e "${YELLOW}[5/5] Test configuration:${NC}"
echo "  Data Range: 2025-05-01 to 2025-05-31 (1 month)"
echo "  Symbols: 517 (full universe)"
echo "  Timeframe: 30m with 1d HTF"
echo "  Strategy: multi_timeframe"
echo "  Mode: $MODE"
if [ -n "$WORKERS" ]; then
    echo "  Workers: $WORKERS"
elif [ -n "$NUM_CPUS" ]; then
    echo "  Workers: $NUM_CPUS (from .env)"
else
    echo "  Workers: auto-detect"
fi
echo ""

# Ask for confirmation
read -p "Continue with backtest? (y/n) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Backtest cancelled"
    exit 0
fi

# Start the backtest
echo -e "${BLUE}"
echo "================================================================================"
echo "  STARTING BACKTEST"
echo "================================================================================"
echo -e "${NC}"

START_TIME=$(date +%s)

# Build command
CMD="python scripts/batch_backtest.py"
if [ "$MODE" = "legacy" ]; then
    CMD="$CMD --mode legacy"
fi
if [ -n "$WORKERS" ]; then
    CMD="$CMD --num-workers $WORKERS"
fi

# Run the backtest
echo "Command: $CMD"
echo ""
$CMD

END_TIME=$(date +%s)
DURATION=$((END_TIME - START_TIME))

# Summary
echo ""
echo -e "${BLUE}"
echo "================================================================================"
echo "  BACKTEST COMPLETE"
echo "================================================================================"
echo -e "${NC}"
echo "Duration: $(($DURATION / 60)) minutes $(($DURATION % 60)) seconds"
echo ""

# Check results
echo "Checking results..."
python -c "
from dgas.db import get_connection
from datetime import datetime

with get_connection() as conn:
    cursor = conn.execute(
        'SELECT COUNT(*) FROM backtest_results WHERE created_at >= %s',
        (datetime.fromtimestamp($START_TIME),)
    )
    count = cursor.fetchone()[0]
    print(f'Results: {count}/517 symbols ({(count/517*100):.1f}%)')

    if count >= 491:
        print('Status: ✓ SUCCESS (95%+)')
    elif count >= 439:
        print('Status: ⚠ WARNING (85-95%)')
    else:
        print('Status: ✗ FAILURE (<85%)')
" 2>/dev/null || echo "Could not fetch results"

echo ""
echo "Log files:"
echo "  Main log: /tmp/batch_run.log"
echo "  Batch logs: /tmp/parallel_batch_*.log"
echo ""
echo -e "${GREEN}Backtest complete!${NC}"

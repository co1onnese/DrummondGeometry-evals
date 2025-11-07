#!/usr/bin/env python3
"""Dashboard launcher script.

This script starts the Streamlit dashboard application.
"""

import sys
import subprocess
from pathlib import Path


def main():
    """Launch the dashboard."""
    dashboard_path = Path(__file__).parent / "src" / "dgas" / "dashboard" / "app.py"

    if not dashboard_path.exists():
        print(f"Error: Dashboard not found at {dashboard_path}")
        sys.exit(1)

    print("Starting DGAS Dashboard...")
    print(f"Dashboard path: {dashboard_path}")
    print("Press Ctrl+C to stop the dashboard")
    print("-" * 50)

    # Run streamlit
    subprocess.run([
        sys.executable, "-m", "streamlit", "run",
        str(dashboard_path),
        "--server.port=8501",
        "--server.address=0.0.0.0",
    ])


if __name__ == "__main__":
    main()

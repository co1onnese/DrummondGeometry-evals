#!/usr/bin/env python3
"""Dashboard CLI entry point.

This module provides the command-line interface for starting the DGAS dashboard.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def build_parser() -> argparse.ArgumentParser:
    """Build argument parser for dashboard command."""
    parser = argparse.ArgumentParser(
        prog="dgas-dashboard",
        description="Start the DGAS Streamlit dashboard",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8501,
        help="Port to run the dashboard on (default: 8501)",
    )
    parser.add_argument(
        "--address",
        type=str,
        default="0.0.0.0",
        help="Address to bind to (default: 0.0.0.0)",
    )
    parser.add_argument(
        "--browser",
        action="store_true",
        default=True,
        help="Open browser automatically (default: True)",
    )
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="Don't open browser automatically",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Start the dashboard."""
    parser = build_parser()
    args = parser.parse_args(argv)

    # Determine browser setting
    browser = not args.no_browser if args.no_browser else args.browser

    # Get dashboard path
    dashboard_path = Path(__file__).parent / "app.py"

    if not dashboard_path.exists():
        print(f"Error: Dashboard not found at {dashboard_path}", file=sys.stderr)
        return 1

    print("=" * 60)
    print("DGAS Dashboard")
    print("=" * 60)
    print(f"Dashboard path: {dashboard_path}")
    print(f"URL: http://{args.address}:{args.port}")
    print("=" * 60)
    print("Press Ctrl+C to stop the dashboard")
    print("=" * 60)

    # Import subprocess here to avoid issues if not available
    import subprocess

    # Build streamlit command
    cmd = [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        str(dashboard_path),
        f"--server.port={args.port}",
        f"--server.address={args.address}",
    ]

    # Add browser flags
    if not browser:
        cmd.append("--server.headless=true")

    # Run streamlit
    try:
        return subprocess.run(cmd).returncode
    except KeyboardInterrupt:
        print("\nDashboard stopped.")
        return 0
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        print("Streamlit is not installed. Install it with:", file=sys.stderr)
        print("  pip install -e .[dashboard]", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

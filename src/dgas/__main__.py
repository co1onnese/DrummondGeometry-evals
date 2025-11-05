"""Entry point for running the Drummond Geometry toolkit."""

from __future__ import annotations

import argparse

from . import get_version


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="dgas",
        description="Drummond Geometry Analysis System",
    )
    parser.add_argument(
        "--version",
        action="store_true",
        help="Display version information and exit.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.version:
        print(f"Drummond Geometry Analysis System {get_version()}")
        return 0

    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

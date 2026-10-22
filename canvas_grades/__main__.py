# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Canvas Grades contributors
import argparse
from importlib.metadata import version
from .app import GradesApp


def main():
    parser = argparse.ArgumentParser(description="Canvas grade ceilings and submission dashboard")
    parser.add_argument("--version", action="version", version=version("canvas-grades"))
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--demo", action="store_true", help="Preview synthetic results without a token")
    mode.add_argument("--offline", action="store_true", help="Read the last complete snapshot without contacting Canvas")
    args = parser.parse_args()
    GradesApp(demo_mode=args.demo, offline=args.offline).run()


if __name__ == "__main__":
    main()

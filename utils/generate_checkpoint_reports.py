#!/usr/bin/env python3
"""Generate preflop report text files for every snapshot .player dump under a directory."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
REPORT_SCRIPT = REPO_ROOT / "utils" / "preflop_frequency_report.py"


def discover_player_files(base_dirs):
    files = []
    seen = set()
    for raw_dir in base_dirs:
        root = Path(raw_dir)
        if not root.exists():
            continue
        for candidate in sorted(root.rglob("*.player")):
            resolved = candidate.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            files.append(candidate)
    return files


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate preflop report files for all snapshot checkpoints under a directory tree.")
    parser.add_argument("paths", nargs="*", default=["./output", "./archive"], help="Directories to scan for .player snapshot files. Default: ./output ./archive")
    parser.add_argument("--label", default="all", help="Report label to generate. Default: all")
    parser.add_argument("--nir-threshold", type=float, default=95.0, help="NIR threshold for the report. Default: 95")
    args = parser.parse_args()

    players = discover_player_files(args.paths)
    if not players:
        print(f"No .player snapshot files found under: {args.paths}", file=sys.stderr)
        return 1

    for player in players:
        cmd = [
            sys.executable,
            str(REPORT_SCRIPT),
            str(player),
            "--label",
            args.label,
            "--nir-threshold",
            str(args.nir_threshold),
        ]
        print(f"Generating report for {player}")
        subprocess = __import__("subprocess")
        completed = subprocess.run(cmd, cwd=str(REPO_ROOT), capture_output=True, text=True)
        if completed.returncode != 0:
            print(completed.stderr or completed.stdout, file=sys.stderr)
            return completed.returncode

    print(f"Generated reports for {len(players)} snapshot(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

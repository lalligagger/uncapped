#!/usr/bin/env python3
"""Summarize bucket-level call/raise percentages from a generated .player file.

This is meant as a lightweight diagnostic pass for the reduced flop abstraction:
- per-state bucket count
- bucket call/raise percentages
- min / max / mean across buckets

Usage:
    python3 utils/diagnose_player_buckets.py path/to/file.player
    python3 utils/diagnose_player_buckets.py --latest test.holdem.pio25_trunc3_diag
"""

from __future__ import annotations

import argparse
import re
import subprocess
from pathlib import Path

BUCKET_PAT = re.compile(r"Bucket\s+(\d+):\s*(.*)")
PERCENT_PAT = re.compile(r"([0-9]+(?:\.[0-9]+)?(?:[eE][-+]?\d+)?)%([fcr])")


def parse_bucket_line(line: str):
    m = BUCKET_PAT.match(line.strip())
    if not m:
        return None
    bucket = int(m.group(1))
    payload = m.group(2)
    entries = PERCENT_PAT.findall(payload)
    if not entries:
        return None
    mapped = {k: float(v) for v, k in entries}
    call = mapped.get("c", 0.0)
    raise_pct = mapped.get("r", 0.0)
    return bucket, call, raise_pct


def parse_printed_strategy(stdout: str):
    state_map = {}
    current_state = None
    for raw in stdout.splitlines():
        line = raw.rstrip("\n")
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("=== PLAYER"):
            current_state = None
            continue
        if stripped.startswith("STATE:"):
            current_state = stripped
            state_map.setdefault(current_state, [])
            continue
        if current_state is None:
            continue
        if stripped.startswith("Bucket "):
            parsed = parse_bucket_line(stripped)
            if parsed is not None:
                bucket, call, raise_pct = parsed
                state_map[current_state].append({
                    "bucket": bucket,
                    "call": call,
                    "raise": raise_pct,
                })

    summary = []
    for state, entries in sorted(state_map.items()):
        if not entries:
            continue
        calls = [entry["call"] for entry in entries]
        raises = [entry["raise"] for entry in entries]
        summary.append({
            "state": state,
            "bucket_count": len(entries),
            "call_min": min(calls),
            "call_max": max(calls),
            "call_mean": sum(calls) / len(calls),
            "raise_min": min(raises),
            "raise_max": max(raises),
            "raise_mean": sum(raises) / len(raises),
            "entries": entries,
        })
    return summary


def find_latest_player_file(prefix: str):
    base = Path(".")
    matches = sorted(base.glob(f"{prefix}.iter-*.player"))
    if not matches:
        raise FileNotFoundError(f"No files matching {prefix}.iter-*.player were found in {base}")
    return matches[-1]


def main():
    parser = argparse.ArgumentParser(description="Summarize bucket-level policy diagnostics from the final CFR strategy output.")
    parser.add_argument("player_file", nargs="?", help="Path to a generated .player file; if omitted, use the newest matching prefix.")
    parser.add_argument("--latest-prefix", default=None, help="Optional prefix to locate the newest matching .player file, e.g. test.holdem.pio25_trunc3_diag")
    parser.add_argument("--max-round", type=int, default=3, help="Max round to print from the strategy dump.")
    args = parser.parse_args()

    if args.player_file:
        path = Path(args.player_file)
    elif args.latest_prefix:
        path = find_latest_player_file(args.latest_prefix)
    else:
        path = find_latest_player_file("test.holdem.pio25_trunc3_diag")

    cmd = ["./print_player_strategy", str(path), f"--max-round={args.max_round}"]
    completed = subprocess.run(cmd, capture_output=True, text=True, check=True)
    summary = parse_printed_strategy(completed.stdout)

    print(f"Diagnostics for: {path}")
    print(f"States with bucket summaries: {len(summary)}")
    for row in summary:
        print(
            f"{row['state']} | buckets={row['bucket_count']} | "
            f"call_min={row['call_min']:.4f} | call_max={row['call_max']:.4f} | call_mean={row['call_mean']:.4f} | "
            f"raise_min={row['raise_min']:.4f} | raise_max={row['raise_max']:.4f} | raise_mean={row['raise_mean']:.4f}"
        )
        sample = row["entries"][:5]
        if sample:
            print("  sample = " + " | ".join(f"B{e['bucket']}:{e['call']:.2f}%c/{e['raise']:.2f}%r" for e in sample))


if __name__ == "__main__":
    main()

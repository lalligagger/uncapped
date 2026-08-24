#!/usr/bin/env python3
"""Create a single text summary for the reduced-flop strategy dump.

This script reads the strategy output from print_player_strategy for the current
reduced model and writes one text summary that contains:
  1) action-history-only summaries (aggregate over all buckets for a given state)
  2) bucket-level breakdowns (individual bucket call/raise frequencies)

Usage:
  python3 utils/action_summary.py test.holdem.pio25_trunc3.iter-2364k.secs-30.player
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

PERCENT_RE = re.compile(r"([0-9]+(?:\.[0-9]+)?(?:[eE][-+]?\d+)?)%([a-z])")


def parse_bucket_line(line: str):
    m = re.match(r"Bucket\s+(\d+):\s*(.*)", line.strip())
    if not m:
        return None
    bucket = int(m.group(1))
    payload = m.group(2)
    vals = {label: float(value) for value, label in PERCENT_RE.findall(payload)}
    return {
        "bucket": bucket,
        "call": vals.get("c", 0.0),
        "raise": vals.get("r", 0.0),
        "fold": vals.get("f", 0.0),
    }


def parse_strategy_stdout(stdout: str):
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
                state_map[current_state].append(parsed)
    return state_map


def summarize_history(state_map):
    rows = []
    for state, entries in sorted(state_map.items()):
        if not entries:
            continue
        calls = [e["call"] for e in entries]
        raises = [e["raise"] for e in entries]
        rows.append({
            "state": state,
            "buckets": len(entries),
            "call_min": min(calls),
            "call_max": max(calls),
            "call_mean": sum(calls) / len(calls),
            "raise_min": min(raises),
            "raise_max": max(raises),
            "raise_mean": sum(raises) / len(raises),
            "sample": entries[:5],
        })
    return rows


def write_summary(player_file: Path, output_file: Path):
    cmd = ["./print_player_strategy", str(player_file), "--max-round=3"]
    completed = subprocess.run(cmd, capture_output=True, text=True, check=True)
    state_map = parse_strategy_stdout(completed.stdout)
    history = summarize_history(state_map)

    lines = []
    lines.append("Pure CFR reduced-flop action summary")
    lines.append(f"Player file: {player_file}")
    lines.append(f"States with bucket summaries: {len(history)}")
    lines.append("")
    lines.append("1) Action-history summary only (aggregated over all buckets for each state)")
    lines.append("------------------------------------------------------------------------------")
    for row in history:
        lines.append(
            f"{row['state']} | buckets={row['buckets']} | "
            f"call_min={row['call_min']:.4f} | call_max={row['call_max']:.4f} | call_mean={row['call_mean']:.4f} | "
            f"raise_min={row['raise_min']:.4f} | raise_max={row['raise_max']:.4f} | raise_mean={row['raise_mean']:.4f}"
        )
        if row["sample"]:
            lines.append(
                "  sample = " + " | ".join(
                    f"B{e['bucket']}:{e['call']:.2f}%c/{e['raise']:.2f}%r" for e in row["sample"]
                )
            )
    lines.append("")
    lines.append("2) Bucket breakdown (all 25 flops / buckets when present)")
    lines.append("----------------------------------------------------------")
    for state, entries in sorted(state_map.items()):
        if not entries:
            continue
        lines.append(state)
        for entry in entries:
            lines.append(
                f"  Bucket {entry['bucket']}: {entry['call']:.4f}%c | {entry['raise']:.4f}%r | {entry['fold']:.4f}%f"
            )
        lines.append("")

    output_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote summary to {output_file}")
    print(f"Historic states: {len(history)}")


def main():
    import sys
    if len(sys.argv) < 2:
        raise SystemExit("Usage: python3 utils/action_summary.py <player_file>")
    player_file = Path(sys.argv[1]).resolve()
    if not player_file.exists():
        raise FileNotFoundError(f"Player file not found: {player_file}")
    summary_file = player_file.with_suffix(".txt")
    write_summary(player_file, summary_file)


if __name__ == "__main__":
    main()

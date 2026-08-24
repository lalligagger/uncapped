#!/usr/bin/env python3
"""Regression checks for the preflop report semantics.

These checks are intentionally narrow: the expected behavior is locked to the
public-history semantics that have been validated against archive/run6.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PLAYER = REPO_ROOT / "archive" / "run6" / "run6_pre13x13_10m.iter-557411k.secs-6000.player"

EXPECTED_SNIPPETS = {
    "23o": r"23o.*\[preflop_open\].*0\.00%.*0\.00%.*100\.00%.*0\.00%.*1",
    "23s": r"23s.*\[preflop_open\].*7\.95%.*0\.01%.*92\.04%.*0\.00%.*1",
    "24o": r"24o.*\[preflop_open\].*0\.00%.*0\.00%.*99\.99%.*0\.00%.*1",
    "24s": r"24s.*\[preflop_open\].*0\.19%.*0\.07%.*99\.73%.*0\.00%.*1",
    "25o": r"25o.*\[preflop_open\].*0\.00%.*0\.00%.*100\.00%.*0\.00%.*1",
    "25s": r"25s.*\[preflop_open\].*99\.85%.*0\.11%.*0\.04%.*0\.00%.*1",
    "respond_to_open_zero_nir_23o": r"23o\s+\|\s+r \[respond_to_open\]\s+\|\s+99\.91%\s+\|\s+0\.00%\s+\|\s+0\.09%\s+\|\s+0\.00%\s+\|\s+1",
    "respond_to_open_zero_nir_23s": r"23s\s+\|\s+r \[respond_to_open\]\s+\|\s+99\.99%\s+\|\s+0\.01%\s+\|\s+0\.00%\s+\|\s+0\.00%\s+\|\s+1",
    "default_report_has_zero_nir": r"23o\s+\|\s+r \[respond_to_open\]\s+\|\s+99\.91%\s+\|\s+0\.00%\s+\|\s+0\.09%\s+\|\s+0\.00%\s+\|\s+1",
}


def parse_rows(stdout: str):
    rows = {}
    for line in stdout.splitlines():
        if '|' not in line or 'hand' in line:
            continue
        pieces = [p.strip() for p in line.split('|')]
        if len(pieces) < 8:
            continue
        hand = pieces[0]
        history_part = pieces[1]
        if not hand or not history_part:
            continue
        history = history_part.split('[', 1)[0].strip()
        try:
            call = float(pieces[3].rstrip('%'))
            raisev = float(pieces[4].rstrip('%'))
            fold = float(pieces[5].rstrip('%'))
        except ValueError:
            continue
        rows[(hand, history)] = (call, raisev, fold)
    return rows


def main() -> int:
    completed = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "utils" / "preflop_frequency_report.py"),
            str(PLAYER),
            "--label",
            "all",
            "--nir-threshold",
            "95",
        ],
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout
    output = completed.stdout
    for label, pattern in EXPECTED_SNIPPETS.items():
        assert re.search(pattern, output), f"Missing expected {label} regression: {pattern}\n---OUTPUT---\n{output[:1500]}"

    base_rows = parse_rows(output)
    experimental = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "utils" / "preflop_frequency_report.py"),
            str(PLAYER),
            "--label",
            "respond_to_3bet",
            "--compute-nir",
            "--nir-threshold",
            "95",
        ],
        capture_output=True,
        text=True,
    )
    assert experimental.returncode == 0, experimental.stderr or experimental.stdout
    experimental_rows = parse_rows(experimental.stdout)
    for key, base_vals in base_rows.items():
        if key not in experimental_rows:
            continue
        exp_vals = experimental_rows[key]
        assert abs(exp_vals[0] - base_vals[0]) < 1e-9, f"call mismatch for {key}: {base_vals} vs {exp_vals}"
        assert abs(exp_vals[1] - base_vals[1]) < 1e-9, f"raise mismatch for {key}: {base_vals} vs {exp_vals}"
        assert abs(exp_vals[2] - base_vals[2]) < 1e-9, f"fold mismatch for {key}: {base_vals} vs {exp_vals}"
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

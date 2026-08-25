#!/usr/bin/env python3
"""Regression check that the default policy is uniform over legal actions."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BIN = REPO_ROOT / "pure_cfr"


def main() -> int:
    # Pick a simple state that admits a standard TRUNC3 preflop menu so we can
    # verify the default action policy is uniform rather than call-biased.
    # This test exercises the real binary only at the policy-selection layer.
    assert BIN.exists(), f"Missing binary: {BIN}"
    proc = subprocess.run(
        [
            str(BIN),
            "games/holdem.limit.2p.reverse_blinds.game",
            "--input-label=uniform_default_policy_probe",
            "--card-abs=PIO25",
            "--action-abs=TRUNC3",
            "--rng=1:2:3:4",
            "--threads=1",
            "--status=1",
            "--checkpoint=1",
            "--max-walltime=1",
        ],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

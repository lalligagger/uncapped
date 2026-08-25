#!/usr/bin/env python3
"""Dashboard for viewing solver snapshots directly from player dumps.

This version reads raw snapshot files from the output tree, extracts the exact
state strategy for each public-history state, and renders a preflop range matrix
with fold/call/raise split by hand. The internal representation is kept in plain
Python dicts so it remains JSON-exportable later if we want to move to a real API.
"""

from __future__ import annotations

import argparse
import html as html_lib
import json
import re
import subprocess
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

PAIR_RANKS = list("23456789TJQKA")
GRID_RANKS = list("AKQJT98765432")
DEFAULT_SPOTS = [
    "preflop_open",
    "respond_to_open",
    "respond_to_limp",
    "respond_to_3bet",
    "limper_respond_to_raise",
    "respond_to_limp_3bet",
    "limper_respond_to_4bet",
    "respond_to_4bet",
]
TARGET_PREFLOP_HISTORIES = {
    "": "preflop_open",
    "r": "respond_to_open",
    "c": "respond_to_limp",
    "rr": "respond_to_3bet",
    "cr": "limper_respond_to_raise",
    "crr": "respond_to_limp_3bet",
    "crrr": "limper_respond_to_4bet",
    "rrr": "respond_to_4bet",
}
DEFAULT_NIR_THRESHOLD = 95.0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Render a checkpoint dashboard from raw solver snapshots (.player files)."
    )
    parser.add_argument(
        "--snapshot-dir",
        action="append",
        default=[],
        help="Directory containing solver snapshot .player files. Repeat if needed.",
    )
    parser.add_argument(
        "--report-dir",
        action="append",
        default=[],
        help="Deprecated compatibility alias: same as --snapshot-dir.",
    )
    parser.add_argument(
        "--output",
        default="dashboard_preview.html",
        help="Output HTML path for the generated dashboard.",
    )
    parser.add_argument(
        "--spot",
        default="preflop_open",
        help="Initial spot to display. Default: %(default)s",
    )
    parser.add_argument(
        "--watch",
        action="store_true",
        help="Poll the snapshot dir for new checkpoint files and refresh the dashboard.",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=10.0,
        help="Seconds between dashboard refreshes when using --watch. Default: %(default)s",
    )
    parser.add_argument(
        "--browser-refresh",
        type=float,
        default=0.0,
        help="Seconds between auto-reloads of the generated HTML page in the browser. Default: disabled (0).",
    )
    return parser.parse_args()


def bucket_label(bucket_id: int) -> str:
    if bucket_id < 13:
        rank = PAIR_RANKS[bucket_id]
        return f"{rank}{rank}"

    pair_index = (bucket_id - 13) // 2
    suited = ((bucket_id - 13) % 2) == 1

    seen = 0
    for high_idx in range(1, len(PAIR_RANKS)):
        for low_idx in range(high_idx):
            if seen == pair_index:
                low_rank = PAIR_RANKS[low_idx]
                high_rank = PAIR_RANKS[high_idx]
                suffix = "s" if suited else "o"
                return f"{low_rank}{high_rank}{suffix}"
            seen += 1
    raise ValueError(f"Could not decode bucket {bucket_id}")


def parse_bucket_line(line: str):
    m = re.match(r"\s*Bucket\s+(\d+):\s*(.*)", line)
    if not m:
        return None
    bucket = int(m.group(1))
    payload = m.group(2)
    vals = {}
    for value, letter in re.findall(r"([0-9]+(?:\.[0-9]+)?(?:[eE][-+]?\d+)?)%([fcr])", payload):
        vals[letter] = float(value)
    return {
        "bucket": bucket,
        "fold": vals.get("f", 0.0),
        "call": vals.get("c", 0.0),
        "raise": vals.get("r", 0.0),
    }


def parse_state_history_and_cards(line: str):
    segs = line.split(":")
    if len(segs) < 3:
        return None, None
    public_tokens = segs[1:-1]
    raw_history = "".join(public_tokens)
    raw_history = raw_history.replace("/", "")
    if raw_history.startswith("0"):
        raw_history = raw_history[1:]
    private_cards = segs[-1]
    return raw_history, private_cards


def parse_strategy_dump(stdout: str):
    state_map = {}
    current_state_key = None
    current_entries = None
    for raw in stdout.splitlines():
        line = raw.rstrip("\n")
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("=== PLAYER"):
            current_state_key = None
            continue
        if stripped.startswith("STATE:"):
            history, hole_cards = parse_state_history_and_cards(stripped)
            if history is None or hole_cards is None:
                current_state_key = None
                current_entries = None
                continue
            state_map.setdefault((history, hole_cards), [])
            current_state_key = (history, hole_cards)
            current_entries = state_map[current_state_key]
            continue
        if current_state_key is None:
            continue
        if stripped.startswith("Bucket "):
            bucket = parse_bucket_line(stripped)
            if bucket is not None:
                current_entries.append(
                    {
                        "history": current_state_key[0],
                        "hole_cards": current_state_key[1],
                        "friendly": TARGET_PREFLOP_HISTORIES.get(current_state_key[0], "ignore"),
                        **bucket,
                    }
                )
    return state_map


def normalize_snapshot_path(path: Path) -> str:
    return path.name


def infer_checkpoint_name(path: Path) -> str:
    text = path.name
    m = re.search(r"(iter-[^./]+(?:\.secs-[^./]+)?)", text)
    if m:
        return m.group(1)
    return path.stem


def build_grid_labels() -> List[str]:
    labels: List[str] = []
    for row in range(len(GRID_RANKS)):
        for col in range(len(GRID_RANKS)):
            if row == col:
                labels.append(f"{GRID_RANKS[row]}{GRID_RANKS[col]}")
                continue
            if row < col:
                high_rank = GRID_RANKS[row]
                low_rank = GRID_RANKS[col]
                labels.append(f"{low_rank}{high_rank}s")
            else:
                low_rank = GRID_RANKS[row]
                high_rank = GRID_RANKS[col]
                labels.append(f"{low_rank}{high_rank}o")
    return labels


def cell_label_to_index(label: str) -> Optional[Tuple[int, int]]:
    text = str(label or "").strip()
    if not text:
        return None
    if len(text) == 2 and text[0] == text[1]:
        rank = text[0]
        return RANKS.index(rank), RANKS.index(rank)
    if len(text) == 3 and text[2] in {"s", "o"}:
        a, b = text[0], text[1]
        if a == b:
            return RANKS.index(a), RANKS.index(a)
        hi_rank = max(a, b, key=lambda ch: RANKS.index(ch))
        lo_rank = min(a, b, key=lambda ch: RANKS.index(ch))
        row = RANKS.index(hi_rank)
        col = RANKS.index(lo_rank)
        return row, col
    return None


def aggregate_history_rows(state_map: Dict[Tuple[str, str], List[Dict[str, Any]]], history: str) -> Dict[str, Dict[str, float]]:
    rows: Dict[str, Dict[str, float]] = defaultdict(lambda: {"fold": 0.0, "call": 0.0, "raise": 0.0, "count": 0})
    for (state_history, _), entries in state_map.items():
        if state_history != history:
            continue
        for entry in entries:
            hand_label = bucket_label(int(entry["bucket"]))
            bucket = rows[hand_label]
            bucket["fold"] += float(entry["fold"])
            bucket["call"] += float(entry["call"])
            bucket["raise"] += float(entry["raise"])
            bucket["count"] += 1

    normalized: Dict[str, Dict[str, float]] = {}
    for hand_label, bucket in rows.items():
        total = bucket["fold"] + bucket["call"] + bucket["raise"]
        if total <= 0:
            normalized[hand_label] = {"fold": 0.0, "call": 0.0, "raise": 0.0, "nir": 0.0}
        else:
            normalized[hand_label] = {
                "fold": bucket["fold"] / total * 100.0,
                "call": bucket["call"] / total * 100.0,
                "raise": bucket["raise"] / total * 100.0,
                "nir": 0.0,
            }

    if history in ("", "r", "c"):
        return normalized

    if history == "rr":
        root_rows = aggregate_history_rows(state_map, "")
        for hand_label in normalized:
            root_row = root_rows.get(hand_label, {})
            normalized[hand_label]["nir"] = float(root_row.get("fold", 0.0))
        return normalized

    if history == "rrr":
        respond_to_open_rows = aggregate_history_rows(state_map, "r")
        for hand_label in normalized:
            r_row = respond_to_open_rows.get(hand_label, {})
            normalized[hand_label]["nir"] = float(r_row.get("call", 0.0) + r_row.get("fold", 0.0))
        return normalized

    for hand_label in normalized:
        normalized[hand_label]["nir"] = 0.0
    return normalized


def build_snapshot_data(player_file: Path) -> Dict[str, Any]:
    repo_root = Path(__file__).resolve().parents[1]
    binary = repo_root / "print_player_strategy"
    if not binary.exists():
        raise FileNotFoundError(f"Missing print_player_strategy binary at {binary}")

    completed = subprocess.run(
        [str(binary), str(player_file), "--show-private", "--max-round=2"],
        capture_output=True,
        check=True,
        cwd=str(repo_root),
    )
    stdout = completed.stdout.decode("utf-8", errors="replace")
    state_map = parse_strategy_dump(stdout)

    spot_data: Dict[str, Dict[str, Dict[str, float]]] = {}
    for history, friendly in TARGET_PREFLOP_HISTORIES.items():
        spot_data[friendly] = aggregate_history_rows(state_map, history)

    snapshot = {
        "checkpoint": infer_checkpoint_name(player_file),
        "file": str(player_file),
        "spots": spot_data,
        "generated_at": time.time(),
    }
    return snapshot


def checkpoint_sort_key(path: Path) -> Tuple[int, int]:
    name = path.name
    m = re.search(r"iter-(\d+)([kK])?\.secs-(\d+)", name)
    if m:
        iter_count = int(m.group(1))
        if m.group(2):
            iter_count *= 1000
        return (iter_count, int(m.group(3)))
    m = re.search(r"iter-(\d+)", name)
    if m:
        return (int(m.group(1)), 0)
    return (0, 0)


def default_snapshot_dirs() -> List[str]:
    output_root = Path("output")
    if output_root.exists():
        numbered = sorted(
            [p for p in output_root.iterdir() if p.is_dir() and p.name.isdigit()],
            key=lambda p: int(p.name),
            reverse=True,
        )
        if numbered:
            return [str(numbered[0])]
    return ["output"]


def discover_snapshot_files(base_dirs: Iterable[str]) -> List[Path]:
    matches: List[Path] = []
    seen = set()
    for base in base_dirs:
        path = Path(base)
        if not path.exists():
            continue
        for file in sorted(path.rglob("*.player")):
            if file in seen:
                continue
            seen.add(file)
            matches.append(file)
    return sorted(matches, key=checkpoint_sort_key)


def build_stability_series(snapshots: List[Dict[str, Any]], spots: List[str]) -> Dict[str, List[Dict[str, Any]]]:
    series_by_spot: Dict[str, List[Dict[str, Any]]] = {spot: [] for spot in spots}
    for spot in spots:
        prior = None
        for snapshot in snapshots:
            rows = snapshot.get("spots", {}).get(spot, {})
            if not rows:
                continue
            values = list(rows.values())
            if not values:
                continue
            fold = sum(float(v.get("fold", 0.0)) for v in values) / len(values)
            call = sum(float(v.get("call", 0.0)) for v in values) / len(values)
            raise_pct = sum(float(v.get("raise", 0.0)) for v in values) / len(values)
            nir = sum(float(v.get("nir", 0.0)) for v in values) / len(values)
            point = {
                "checkpoint": snapshot["checkpoint"],
                "fold": fold,
                "call": call,
                "raise": raise_pct,
                "nir": nir,
            }
            if prior is not None:
                series_by_spot[spot].append(
                    {
                        "checkpoint": snapshot["checkpoint"],
                        "fold": abs(fold - prior["fold"]),
                        "call": abs(call - prior["call"]),
                        "raise": abs(raise_pct - prior["raise"]),
                        "nir": abs(nir - prior["nir"]),
                    }
                )
            prior = point
    return {spot: entries for spot, entries in series_by_spot.items() if entries}


def summarize_policy_deltas(snapshots: List[Dict[str, Any]], spot: str) -> Dict[str, Any]:
    action_names = ["fold", "call", "raise"]
    global_points: List[Dict[str, float]] = []
    for snapshot in snapshots:
        rows = snapshot.get("spots", {}).get(spot, {})
        if not rows:
            continue
        values = list(rows.values())
        if not values:
            continue
        point = {
            "checkpoint": snapshot["checkpoint"],
            "fold": sum(float(v.get("fold", 0.0)) for v in values) / len(values),
            "call": sum(float(v.get("call", 0.0)) for v in values) / len(values),
            "raise": sum(float(v.get("raise", 0.0)) for v in values) / len(values),
        }
        global_points.append(point)

    global_deltas: List[float] = []
    for prev, curr in zip(global_points, global_points[1:]):
        for action in action_names:
            global_deltas.append(abs(float(curr[action]) - float(prev[action])))

    latest_rows = snapshots[-1].get("spots", {}).get(spot, {}) if snapshots else {}
    hand_dominance: List[Tuple[str, str, float]] = []
    for hand_label, actions in latest_rows.items():
        values = {name: float(actions.get(name, 0.0)) for name in action_names}
        dominant_name = max(action_names, key=lambda name: values[name])
        hand_dominance.append((hand_label, dominant_name, values[dominant_name]))

    selected_hands = [hand for hand, _, _ in sorted(hand_dominance, key=lambda x: x[2])[:20]]
    hand_delta_values: List[float] = []
    hand_detail: List[Dict[str, Any]] = []
    for hand_label in selected_hands:
        values_by_checkpoint: List[float] = []
        for snapshot in snapshots:
            rows = snapshot.get("spots", {}).get(spot, {})
            actions = rows.get(hand_label, {})
            if not actions:
                continue
            dist = {name: float(actions.get(name, 0.0)) for name in action_names}
            dominant_name = max(action_names, key=lambda name: dist[name])
            values_by_checkpoint.append(dist[dominant_name])
        for prev, curr in zip(values_by_checkpoint, values_by_checkpoint[1:]):
            hand_delta_values.append(abs(float(curr) - float(prev)))
        latest_dist = {}
        latest_snapshot = snapshots[-1].get("spots", {}).get(spot, {}).get(hand_label, {}) if snapshots else {}
        if latest_snapshot:
            latest_dist = {name: float(latest_snapshot.get(name, 0.0)) for name in action_names}
        hand_detail.append(
            {
                "hand": hand_label,
                "dominant_action": max(action_names, key=lambda name: latest_dist.get(name, 0.0)),
                "dominant_pct": max(latest_dist.values()) if latest_dist else 0.0,
            }
        )

    return {
        "global_policy": {
            "max_delta": max(global_deltas) if global_deltas else 0.0,
            "avg_delta": sum(global_deltas) / len(global_deltas) if global_deltas else 0.0,
        },
        "low_dominance_hands": {
            "max_delta": max(hand_delta_values) if hand_delta_values else 0.0,
            "avg_delta": sum(hand_delta_values) / len(hand_delta_values) if hand_delta_values else 0.0,
            "hands": hand_detail,
        },
    }


def build_dashboard_data(base_dirs: Iterable[str]) -> Dict[str, Any]:
    snapshots = []
    for path in discover_snapshot_files(base_dirs):
        try:
            snapshots.append(build_snapshot_data(path))
        except Exception as exc:  # pragma: no cover - runtime safeguard for malformed snapshots
            print(f"Skipping snapshot {path}: {exc}", file=sys.stderr)
    spots = [spot for spot in DEFAULT_SPOTS if any(spot in snap["spots"] for snap in snapshots)]
    if not spots:
        spots = list(DEFAULT_SPOTS)
    first_snapshot = snapshots[0] if snapshots else None
    default_spot = first_snapshot["spots"].keys().__iter__().__next__() if first_snapshot else DEFAULT_SPOTS[0]
    stability = build_stability_series(snapshots, spots)
    spot_metrics = {spot: summarize_policy_deltas(snapshots, spot) for spot in spots}
    return {
        "snapshots": snapshots,
        "spots": spots,
        "default_spot": default_spot,
        "grid_labels": build_grid_labels(),
        "stability": stability,
        "spot_metrics": spot_metrics,
    }


def matrix_from_rows(rows: Dict[str, Dict[str, float]], labels: Optional[List[str]] = None) -> Dict[str, Dict[str, float]]:
    label_list = labels or build_grid_labels()
    matrix = {}
    for label in label_list:
        matrix[label] = {"fold": 0.0, "call": 0.0, "raise": 0.0}
    for label, actions in rows.items():
        matrix[label] = {
            "fold": float(actions.get("fold", 0.0)),
            "call": float(actions.get("call", 0.0)),
            "raise": float(actions.get("raise", 0.0)),
        }
    return matrix


def render_dashboard_html(dashboard_data: Dict[str, Any], output_path: Path, browser_refresh_seconds: float = 10.0) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(dashboard_data, separators=(",", ":"))
    template = """<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    __META_REFRESH__
    <title>Preflop snapshot dashboard</title>
    <style>
      :root {
        --bg: #f8fafc;
        --panel: #ffffff;
        --line: #dfe7f1;
        --muted: #475569;
        --text: #0f172a;
        --fold: #dbeafe;
        --call: #bbf7d0;
        --raise: #fecaca;
        --nir: rgba(148, 163, 184, 0.8);
      }
      body { margin: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: var(--bg); color: var(--text); }
      .topbar { display: flex; gap: 12px; align-items: center; padding: 14px 18px; background: #fff; border-bottom: 1px solid var(--line); }
      label { font-size: 12px; color: var(--muted); text-transform: uppercase; letter-spacing: 0.08em; font-weight: 600; }
      select { padding: 8px 10px; border: 1px solid var(--line); border-radius: 8px; background: white; color: var(--text); font-size: 13px; }
      .wrap { max-width: 1180px; margin: 18px auto 40px; }
      .panel { background: var(--panel); border: 1px solid var(--line); border-radius: 14px; padding: 14px; box-shadow: 0 1px 2px rgba(15,23,42,0.03); }
      .grid-wrap { display: grid; grid-template-columns: repeat(13, 1fr); gap: 2px; margin-top: 18px; }
      .cell { position: relative; aspect-ratio: 1; border: 1px solid rgba(15,23,42,0.12); background: #f8fafc; display: flex; align-items: center; justify-content: center; font-size: 10px; font-weight: 600; color: #0f172a; overflow: hidden; }
      .range-stack { position: absolute; inset: 0; display: flex; flex-direction: column-reverse; }
      .segment { width: 100%; }
      .segment.nir { background: var(--nir); }
      .segment.fold { background: var(--fold); }
      .segment.call { background: var(--call); }
      .segment.raise { background: var(--raise); }
      .cell .label { position: relative; z-index: 2; mix-blend-mode: multiply; background: rgba(255,255,255,0.45); padding: 2px 3px; border-radius: 4px; }
      .legend { display: flex; gap: 18px; margin-top: 12px; font-size: 12px; color: var(--muted); }
      .legend-swatch { display: inline-block; width: 14px; height: 14px; border-radius: 4px; border: 1px solid rgba(15,23,42,0.18); margin-right: 6px; vertical-align: middle; }
      .muted { color: var(--muted); }
      .chart-panel { margin-top: 18px; }
      #stabilityChart { width: 100%; height: 360px; }
      .metric-grid { display: grid; grid-template-columns: repeat(2, minmax(180px, 1fr)); gap: 12px; margin-top: 12px; }
      .metric-box { background: #f8fafc; border: 1px solid var(--line); border-radius: 10px; padding: 10px 12px; }
      .metric-title { font-size: 11px; letter-spacing: 0.08em; text-transform: uppercase; color: var(--muted); margin-bottom: 6px; }
      .metric-value { font-size: 26px; font-weight: 700; }
      .metric-sub { font-size: 12px; color: var(--muted); }
    </style>
    <script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>
  </head>
  <body>
    <div class="topbar">
      <div>
        <label for="snapshotSelect">Snapshot</label><br />
        <select id="snapshotSelect"></select>
      </div>
      <div>
        <label for="spotSelect">Spot</label><br />
        <select id="spotSelect"></select>
      </div>
    </div>
    <div class="wrap">
      <div class="panel">
        <div id="snapshotMeta" class="muted">Loading…</div>
        <div id="grid" class="grid-wrap"></div>
        <div class="legend">
          <div><span class="legend-swatch" style="background: var(--fold);"></span>fold</div>
          <div><span class="legend-swatch" style="background: var(--call);"></span>call</div>
          <div><span class="legend-swatch" style="background: var(--raise);"></span>raise</div>
        </div>
      </div>
      <div class="panel chart-panel">
        <div class="muted" style="margin-bottom: 8px;">Stability view</div>
        <div id="stabilityChart"></div>
        <div id="metricGrid" class="metric-grid"></div>
      </div>
    </div>
    <script>
      const data = __PAYLOAD__;
      const refreshSeconds = __REFRESH_SECONDS__;
      const snapshotSelect = document.getElementById('snapshotSelect');
      const spotSelect = document.getElementById('spotSelect');
      const grid = document.getElementById('grid');
      const snapshotMeta = document.getElementById('snapshotMeta');

      function fmtPct(value) {
        return Number(value * 100).toFixed(2) + '%';
      }

      function renderMetrics() {
        const spot = spotSelect.value;
        const metrics = (data.spot_metrics && data.spot_metrics[spot]) || { global_policy: { max_delta: 0, avg_delta: 0 }, low_dominance_hands: { max_delta: 0, avg_delta: 0 } };
        const container = document.getElementById('metricGrid');
        container.innerHTML = `
          <div class="metric-box">
            <div class="metric-title">Global policy max delta</div>
            <div class="metric-value">${Number(metrics.global_policy.max_delta || 0).toFixed(2)}%</div>
            <div class="metric-sub">Across call/raise/fold frequencies between checkpoints</div>
          </div>
          <div class="metric-box">
            <div class="metric-title">Global policy avg delta</div>
            <div class="metric-value">${Number(metrics.global_policy.avg_delta || 0).toFixed(2)}%</div>
            <div class="metric-sub">Mean absolute action shift</div>
          </div>
          <div class="metric-box">
            <div class="metric-title">Top-20 hand max delta</div>
            <div class="metric-value">${Number(metrics.low_dominance_hands.max_delta || 0).toFixed(2)}%</div>
            <div class="metric-sub">Lowest-dominance dominant-action drift</div>
          </div>
          <div class="metric-box">
            <div class="metric-title">Top-20 hand avg delta</div>
            <div class="metric-value">${Number(metrics.low_dominance_hands.avg_delta || 0).toFixed(2)}%</div>
            <div class="metric-sub">Average dominant-action movement</div>
          </div>
        `;
      }

      function renderStabilityChart() {
        const spot = spotSelect.value;
        const series = (data.stability && data.stability[spot]) || [];
        const checkpoints = series.map((entry) => entry.checkpoint);
        const traces = [
          { name: 'fold delta', x: checkpoints, y: series.map((entry) => entry.fold), mode: 'lines+markers', line: { color: '#93c5fd', width: 2 }, hovertemplate: '%{x}<br>fold delta=%{y:.2f}pp<extra></extra>' },
          { name: 'call delta (vs 3bet)', x: checkpoints, y: series.map((entry) => entry.call), mode: 'lines+markers', line: { color: '#86efac', width: 2 }, hovertemplate: '%{x}<br>call delta (vs 3bet)=%{y:.2f}pp<extra></extra>' },
          { name: 'raise delta (4bet)', x: checkpoints, y: series.map((entry) => entry.raise), mode: 'lines+markers', line: { color: '#fca5a5', width: 2 }, hovertemplate: '%{x}<br>raise delta (4bet)=%{y:.2f}pp<extra></extra>' },
        ];
        const layout = {
          margin: { l: 50, r: 18, t: 24, b: 40 },
          paper_bgcolor: 'rgba(0,0,0,0)',
          plot_bgcolor: 'rgba(0,0,0,0)',
          xaxis: { title: 'checkpoint', tickangle: -35 },
          yaxis: { title: 'absolute delta (pp)', range: [0, 100] },
          legend: { orientation: 'h', y: 1.15 },
          hovermode: 'closest',
        };
        if (series.length === 0) {
          document.getElementById('stabilityChart').innerHTML = '<div class="muted">No stability data for this spot.</div>';
          return;
        }
        Plotly.newPlot('stabilityChart', traces, layout, { responsive: true, displayModeBar: false });
      }

      function dataKeyForCell(row, col) {
        const rankOrder = ['A', 'K', 'Q', 'J', 'T', '9', '8', '7', '6', '5', '4', '3', '2'];
        if (row === col) {
          return rankOrder[row] + rankOrder[col];
        }
        if (row < col) {
          const highRank = rankOrder[row];
          const lowRank = rankOrder[col];
          return lowRank + highRank + 's';
        }
        const lowRank = rankOrder[row];
        const highRank = rankOrder[col];
        return lowRank + highRank + 'o';
      }

      function renderGrid() {
        const snapshotIndex = Number(snapshotSelect.value);
        const spot = spotSelect.value;
        const snapshot = data.snapshots[snapshotIndex];
        if (!snapshot) return;
        const rows = snapshot.spots[spot] || {};
        const labels = data.grid_labels || [];
        snapshotMeta.textContent = 'Checkpoint: ' + snapshot.checkpoint + ' · Spot: ' + spot;
        grid.innerHTML = '';

        for (let row = 0; row < 13; row++) {
          for (let col = 0; col < 13; col++) {
            const key = dataKeyForCell(row, col);
            const actions = rows[key] || { fold: 0, call: 0, raise: 0, nir: 0 };
            const fold = Number(actions.fold || 0);
            const call = Number(actions.call || 0);
            const raise = Number(actions.raise || 0);
            const nir = Number(actions.nir || 0);
            const aliveTotal = Math.max(0, 100 - nir);
            const foldAlive = aliveTotal > 0 ? (fold / 100) * aliveTotal : 0;
            const callAlive = aliveTotal > 0 ? (call / 100) * aliveTotal : 0;
            const raiseAlive = aliveTotal > 0 ? (raise / 100) * aliveTotal : 0;
            const cell = document.createElement('div');
            cell.className = 'cell';
            const liveFoldPct = aliveTotal > 0 ? fold / 100 : 0;
            const liveCallPct = aliveTotal > 0 ? call / 100 : 0;
            const liveRaisePct = aliveTotal > 0 ? raise / 100 : 0;
            cell.title = key + ' · nir ' + fmtPct(nir / 100) + ' · fold ' + fmtPct(liveFoldPct) + ' · call ' + fmtPct(liveCallPct) + ' · raise ' + fmtPct(liveRaisePct);

            const stack = document.createElement('div');
            stack.className = 'range-stack';
            const nirSeg = document.createElement('div');
            const foldSeg = document.createElement('div');
            const callSeg = document.createElement('div');
            const raiseSeg = document.createElement('div');
            nirSeg.className = 'segment nir';
            foldSeg.className = 'segment fold';
            callSeg.className = 'segment call';
            raiseSeg.className = 'segment raise';
            nirSeg.style.height = nir + '%';
            foldSeg.style.height = foldAlive + '%';
            callSeg.style.height = callAlive + '%';
            raiseSeg.style.height = raiseAlive + '%';
            stack.appendChild(nirSeg);
            stack.appendChild(foldSeg);
            stack.appendChild(callSeg);
            stack.appendChild(raiseSeg);
            cell.appendChild(stack);

            const labelNode = document.createElement('span');
            labelNode.className = 'label';
            labelNode.textContent = key;
            cell.appendChild(labelNode);
            grid.appendChild(cell);
          }
        }
      }

      function populateSelectors() {
        snapshotSelect.innerHTML = '';
        if (!data.snapshots || data.snapshots.length === 0) {
          const option = document.createElement('option');
          option.value = '-1';
          option.textContent = 'No snapshots found';
          snapshotSelect.appendChild(option);
          snapshotSelect.value = '-1';
        } else {
          data.snapshots.forEach((snapshot, index) => {
            const option = document.createElement('option');
            option.value = String(index);
            option.textContent = snapshot.checkpoint;
            snapshotSelect.appendChild(option);
          });
          snapshotSelect.value = String(Math.max(0, data.snapshots.length - 1));
        }

        spotSelect.innerHTML = '';
        if (!data.spots || data.spots.length === 0) {
          const option = document.createElement('option');
          option.value = 'none';
          option.textContent = 'No spots available';
          spotSelect.appendChild(option);
          spotSelect.value = 'none';
        } else {
          data.spots.forEach((spot) => {
            const option = document.createElement('option');
            option.value = spot;
            option.textContent = spot;
            spotSelect.appendChild(option);
          });
          spotSelect.value = data.default_spot || data.spots[0];
        }
      }

      function renderEmptyState(message) {
        snapshotMeta.textContent = message;
        grid.innerHTML = '';
      }

      snapshotSelect.addEventListener('change', () => { renderGrid(); renderStabilityChart(); renderMetrics(); });
      spotSelect.addEventListener('change', () => { renderGrid(); renderStabilityChart(); renderMetrics(); });
      populateSelectors();
      if (!data.snapshots || data.snapshots.length === 0) {
        renderEmptyState('No snapshots found. Check the snapshot directory and try again.');
      } else {
        renderGrid();
        renderStabilityChart();
        renderMetrics();
      }
      if (refreshSeconds > 0) {
        setInterval(() => location.reload(), refreshSeconds * 1000);
      }
      window.addEventListener('resize', () => Plotly.Plots.resize(document.getElementById('stabilityChart')));
    </script>
  </body>
</html>
"""
    html_text = template.replace("__PAYLOAD__", payload)
    html_text = html_text.replace("__REFRESH_SECONDS__", str(float(browser_refresh_seconds)))
    if browser_refresh_seconds > 0:
        refresh_seconds = max(1.0, float(browser_refresh_seconds))
        html_text = html_text.replace("__META_REFRESH__", f'<meta http-equiv="refresh" content="{refresh_seconds}" />')
    else:
        html_text = html_text.replace("__META_REFRESH__", "")
    output_path.write_text(html_text, encoding="utf-8")


def main() -> None:
    args = parse_args()
    base_dirs = args.snapshot_dir or args.report_dir or default_snapshot_dirs()
    output_path = Path(args.output)

    browser_refresh_seconds = args.browser_refresh if args.browser_refresh > 0 else 0.0

    def refresh_once() -> None:
        data = build_dashboard_data(base_dirs)
        render_dashboard_html(data, output_path, browser_refresh_seconds=browser_refresh_seconds)
        print(f"Built dashboard from {len(data['snapshots'])} snapshot(s): {output_path}")

    if args.watch:
        print(f"Watching {base_dirs} for new .player snapshots; writing {output_path}")
        while True:
            try:
                refresh_once()
                time.sleep(args.interval)
            except KeyboardInterrupt:
                print("Stopping snapshot watch.")
                return
        return

    refresh_once()


if __name__ == "__main__":
    main()

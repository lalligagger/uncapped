#!/usr/bin/env python3
"""No-limit Hold'em dashboard explorer.

This version intentionally avoids the fixed dropdown tree. Instead it renders a
small text navigator, where each node shows all legal actions explicitly,
including distinct raise sizes, and uses darker red shades for larger raises.
"""

from __future__ import annotations

import argparse
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
SUPPORTED_PREFLOP_HISTORIES = {"", "c", "f", "r300", "r20000"}
TARGET_PREFLOP_HISTORY_LABELS = {
    "": "preflop_open",
    "c": "respond_to_limp",
    "f": "hand_over",
    "r300": "respond_to_raise_300",
    "r20000": "respond_to_raise_20000",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Render an NLH checkpoint dashboard with a text action navigator."
    )
    parser.add_argument("--snapshot-dir", action="append", default=[], help="Snapshot directory to inspect.")
    parser.add_argument("--report-dir", action="append", default=[], help="Deprecated alias for --snapshot-dir.")
    parser.add_argument("--output", default="dashboard_nlh_preview.html", help="HTML output path.")
    parser.add_argument("--watch", action="store_true", help="Refresh the dashboard on new snapshots.")
    parser.add_argument("--interval", type=float, default=10.0, help="Refresh interval in seconds.")
    parser.add_argument("--browser-refresh", type=float, default=0.0, help="Auto-refresh generated HTML in browser.")
    return parser.parse_args()


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
    return sorted(matches, key=lambda p: p.name)


def infer_checkpoint_name(path: Path) -> str:
    text = path.name
    m = re.search(r"(iter-[^./]+(?:\.secs-[^./]+)?)", text)
    if m:
        return m.group(1)
    return path.stem


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


def is_valid_preflop_bucket(bucket_id: int) -> bool:
    return 0 <= bucket_id < 169


def aggregate_history_rows(state_map: Dict[Tuple[str, str], List[Dict[str, Any]]], history: str) -> Dict[str, Dict[str, float]]:
    rows: Dict[str, Dict[str, float]] = defaultdict(lambda: {"fold": 0.0, "call": 0.0, "raise": 0.0})
    for (state_history, _), entries in state_map.items():
        if state_history != history:
            continue
        for entry in entries:
            bucket_id = int(entry["bucket"])
            if not is_valid_preflop_bucket(bucket_id):
                continue
            hand_label = bucket_label(bucket_id)
            for action_key, value in entry["actions"].items():
                if action_key == "fold":
                    rows[hand_label]["fold"] += float(value)
                elif action_key == "call":
                    rows[hand_label]["call"] += float(value)
                elif action_key.startswith("raise:"):
                    rows[hand_label]["raise"] += float(value)

    normalized: Dict[str, Dict[str, float]] = {}
    for hand_label, bucket in rows.items():
        total = bucket["fold"] + bucket["call"] + bucket["raise"]
        if total <= 0:
            normalized[hand_label] = {"fold": 0.0, "call": 0.0, "raise": 0.0}
        else:
            normalized[hand_label] = {
                "fold": bucket["fold"] / total * 100.0,
                "call": bucket["call"] / total * 100.0,
                "raise": bucket["raise"] / total * 100.0,
            }
    return normalized


def normalize_history(history: Optional[str]) -> str:
    if history is None:
        return ""
    normalized = (history or "").replace("/", "")
    if normalized.startswith("0"):
        normalized = normalized[1:]
    return normalized


def parse_state_history_and_cards(line: str):
    segs = line.split(":")
    if len(segs) < 3:
        return None, None
    public_tokens = segs[1:-1]
    raw_history = normalize_history("".join(public_tokens))
    private_cards = segs[-1]
    return raw_history, private_cards


def parse_bucket_line(line: str):
    """Parse a strategy line and preserve distinct raise sizes as separate actions."""
    m = re.match(r"\s*Bucket\s+(\d+):\s*(.*)", line.strip())
    if not m:
        return None

    bucket_id = int(m.group(1))
    payload = m.group(2)
    actions: Dict[str, float] = {}

    for value, action_type, action_size in re.findall(
        r"([0-9]+(?:\.[0-9]+)?(?:[eE][-+]?\d+)?)%(f|c|r)([0-9]*)",
        payload,
    ):
        amount = float(value)
        if action_type == "f":
            actions["fold"] = amount
        elif action_type == "c":
            actions["call"] = amount
        elif action_type == "r":
            key = f"raise:{action_size if action_size else 'pot'}"
            actions[key] = amount

    return {
        "bucket": bucket_id,
        "actions": actions,
    }


def parse_strategy_dump(stdout: str):
    state_map: Dict[Tuple[str, str], List[Dict[str, Any]]] = {}
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
            if history not in SUPPORTED_PREFLOP_HISTORIES:
                current_state_key = None
                current_entries = None
                continue
            current_state_key = (history, hole_cards)
            state_map.setdefault(current_state_key, [])
            current_entries = state_map[current_state_key]
            continue
        if current_state_key is None or current_entries is None:
            continue
        if stripped.startswith("Bucket "):
            parsed = parse_bucket_line(stripped)
            if parsed is not None:
                current_entries.append({
                    "history": current_state_key[0],
                    "hole_cards": current_state_key[1],
                    "bucket": parsed["bucket"],
                    "actions": parsed["actions"],
                })

    return state_map


def default_root_actions() -> List[Dict[str, Any]]:
    return [
        {"label": "fold", "key": "f", "history_key": "f", "value": 0.0},
        {"label": "call", "key": "c", "history_key": "c", "value": 0.0},
        {"label": "raise 300", "key": "r", "history_key": "r300", "size": "300", "value": 0.0},
        {"label": "raise 20000", "key": "r", "history_key": "r20000", "size": "20000", "value": 0.0},
    ]


def aggregate_action_probabilities(state_map: Dict[Tuple[str, str], List[Dict[str, Any]]], history: str) -> List[Dict[str, Any]]:
    if history == "":
        return default_root_actions()

    totals: Dict[str, float] = defaultdict(float)
    for (state_history, _), entries in state_map.items():
        if state_history != history:
            continue
        for entry in entries:
            for action_key, value in entry["actions"].items():
                totals[action_key] += float(value)

    action_rows: List[Dict[str, Any]] = []
    for action_key, value in sorted(totals.items(), key=lambda item: (item[0].startswith("raise"), item[0])):
        if action_key == "fold":
            action_rows.append({"label": "fold", "key": "f", "history_key": "f", "value": value})
        elif action_key == "call":
            action_rows.append({"label": "call", "key": "c", "history_key": "c", "value": value})
        elif action_key.startswith("raise:"):
            size = action_key.split(":", 1)[1]
            pretty = "pot" if size == "pot" else str(size)
            action_rows.append({
                "label": f"raise {pretty}",
                "key": "r",
                "history_key": f"r{pretty if pretty != 'pot' else ''}",
                "size": pretty,
                "value": value,
            })
    return action_rows or default_root_actions() if history == "" else action_rows


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
    histories = sorted({history for (history, _) in state_map}, key=lambda h: (h == "", h == "f", h == "c", h == "r300", h == "r20000"))

    states = {}
    for history in histories:
        states[history] = {
            "history": history,
            "actions": aggregate_action_probabilities(state_map, history),
            "range_rows": aggregate_history_rows(state_map, history),
        }

    if "" not in states:
        states[""] = {
            "history": "",
            "actions": default_root_actions(),
            "range_rows": aggregate_history_rows(state_map, "c") or aggregate_history_rows(state_map, "r300") or aggregate_history_rows(state_map, "r20000") or {},
        }

    all_supported = {"", "c", "f", "r300", "r20000"}
    for history in list(states):
        if history not in all_supported:
            del states[history]

    return {
        "checkpoint": infer_checkpoint_name(player_file),
        "file": str(player_file),
        "states": states,
        "range_rows": aggregate_history_rows(state_map, ""),
        "grid_labels": build_grid_labels(),
        "generated_at": time.time(),
    }


def build_dashboard_data(base_dirs: Iterable[str]) -> Dict[str, Any]:
    snapshots = []
    for path in discover_snapshot_files(base_dirs):
        try:
            snapshots.append(build_snapshot_data(path))
        except Exception as exc:  # pragma: no cover
            print(f"Skipping snapshot {path}: {exc}", file=sys.stderr)

    return {
        "snapshots": snapshots,
        "default_history": "",
    }


def render_dashboard_html(dashboard_data: Dict[str, Any], output_path: Path, browser_refresh_seconds: float = 0.0) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(dashboard_data, separators=(",", ":"))
    template = """<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    __META_REFRESH__
    <title>NLH action navigator</title>
    <style>
      body {
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
        background: #f8fafc;
        color: #0f172a;
        margin: 0;
      }
      .topbar {
        background: white;
        border-bottom: 1px solid #dfe7f1;
        padding: 16px 18px;
      }
      .wrap {
        max-width: 1200px;
        margin: 18px auto;
        padding: 0 16px 30px;
      }
      .panel {
        background: white;
        border: 1px solid #dfe7f1;
        border-radius: 14px;
        padding: 16px;
        box-shadow: 0 1px 3px rgba(15, 23, 42, 0.04);
      }
      .nav {
        font-size: 13px;
        margin-bottom: 16px;
        line-height: 1.8;
      }
      .nav .crumb {
        display: inline;
        margin-right: 8px;
      }
      .nav a, .nav button {
        color: #1d4ed8;
        text-decoration: none;
        background: none;
        border: 0;
        padding: 0;
        font: inherit;
        cursor: pointer;
      }
      .nav .plain {
        color: #0f172a;
        font-weight: 600;
      }
      .actions {
        margin-top: 12px;
        display: flex;
        flex-wrap: wrap;
        gap: 10px;
      }
      .action-link {
        text-decoration: none;
        color: #0f172a;
        background: #eef2ff;
        border: 1px solid #c7d2fe;
        border-radius: 999px;
        padding: 6px 10px;
        font-size: 12px;
        font-weight: 600;
      }
      .action-raise {
        background: #fee2e2;
        border-color: #fca5a5;
      }
      .action-call {
        background: #dcfce7;
        border-color: #86efac;
      }
      .action-fold {
        background: #f1f5f9;
        border-color: #cbd5e1;
      }
      .meta {
        font-size: 12px;
        color: #475569;
        margin-bottom: 12px;
      }
      .grid {
        display: grid;
        grid-template-columns: repeat(13, minmax(0, 1fr));
        gap: 2px;
        margin-top: 16px;
      }
      .cell {
        aspect-ratio: 1;
        position: relative;
        border: 1px solid rgba(15, 23, 42, 0.12);
        background: #f8fafc;
        overflow: hidden;
      }
      .cell .stack {
        position: absolute;
        inset: 0;
        display: flex;
        flex-direction: column-reverse;
      }
      .cell .seg {
        width: 100%;
      }
      .cell .label {
        position: absolute;
        inset: auto 4px 4px 4px;
        font-size: 9px;
        font-weight: 700;
        text-align: center;
        background: rgba(255,255,255,0.55);
        border-radius: 4px;
      }
      .legend {
        display: flex;
        gap: 16px;
        flex-wrap: wrap;
        margin-top: 12px;
        font-size: 12px;
        color: #475569;
      }
      .swatch {
        display: inline-block;
        width: 12px;
        height: 12px;
        border-radius: 4px;
        border: 1px solid rgba(15, 23, 42, 0.14);
        margin-right: 6px;
        vertical-align: middle;
      }
    </style>
  </head>
  <body>
    <div class="topbar">
      <strong>NLH action navigator</strong>
    </div>
    <div class="wrap">
      <div class="panel">
        <div id="nav" class="nav"></div>
        <div id="actions" class="actions"></div>
        <div id="meta" class="meta"></div>
        <div id="grid" class="grid"></div>
        <div id="legend" class="legend"></div>
      </div>
    </div>
    <script>
      const data = __PAYLOAD__;
      const state = {
        snapshotIndex: 0,
        historyPath: [
          { label: 'preflop_open', key: '' }
        ],
      };

      function currentSnapshot() {
        const snapshots = data.snapshots || [];
        if (!snapshots.length) return null;
        return snapshots[Math.min(state.snapshotIndex, snapshots.length - 1)];
      }

      function currentHistoryKey() {
        const last = state.historyPath[state.historyPath.length - 1];
        return last ? last.key : '';
      }

      function currentState() {
        const snapshot = currentSnapshot();
        if (!snapshot) return null;
        const history = currentHistoryKey();
        return snapshot.states && snapshot.states[history] ? snapshot.states[history] : { history, actions: [], range_rows: {} };
      }

      function historyLabel(historyKey) {
        if (!historyKey) return 'preflop_open';
        if (historyKey === 'c') return 'respond_to_limp';
        if (historyKey === 'f') return 'hand_over';
        if (historyKey.startsWith('r')) return `respond_to_raise_${historyKey.slice(1)}`;
        return historyKey;
      }

      function raiseShade(sizeText) {
        if (sizeText === 'pot' || sizeText === 'pot-size') return '#ef4444';
        const numeric = Number.parseFloat(sizeText);
        if (!Number.isFinite(numeric)) return '#dc2626';
        const maxVal = 20000;
        const ratio = Math.min(1, numeric / maxVal);
        const hue = Math.round(220 + ratio * 35);
        const lightness = 85 - ratio * 32;
        return `hsl(${hue}, 75%, ${lightness}%)`;
      }

      function renderNavigator() {
        const nav = document.getElementById('nav');
        const path = state.historyPath;
        nav.innerHTML = '';
        path.forEach((crumb, idx) => {
          const segment = document.createElement('span');
          segment.className = 'crumb';
          const label = historyLabel(crumb.key);
          if (idx === path.length - 1) {
            const txt = document.createElement('span');
            txt.className = 'plain';
            txt.textContent = label;
            segment.appendChild(txt);
          } else {
            const link = document.createElement('button');
            link.textContent = label;
            link.addEventListener('click', () => {
              state.historyPath = path.slice(0, idx + 1);
              render();
            });
            segment.appendChild(link);
          }
          if (idx < path.length - 1) {
            const sep = document.createElement('span');
            sep.textContent = ' > ';
            segment.appendChild(sep);
          }
          nav.appendChild(segment);
        });
      }

      function renderActions() {
        const actionsEl = document.getElementById('actions');
        actionsEl.innerHTML = '';
        const stateData = currentState();
        const actions = stateData ? stateData.actions : [];
        const path = state.historyPath;

        if (currentHistoryKey() === 'f') {
          const msg = document.createElement('div');
          msg.textContent = 'Hand Over.';
          msg.style.fontSize = '32px';
          msg.style.fontWeight = '700';
          msg.style.padding = '20px 0';
          actionsEl.appendChild(msg);
          return;
        }

        if (!actions.length) {
          actionsEl.innerHTML = '<span class="muted">No action entries for this node.</span>';
          return;
        }
        actions.forEach((action) => {
          const btn = document.createElement('button');
          btn.className = 'action-link ' + (action.key === 'f' ? 'action-fold' : action.key === 'c' ? 'action-call' : 'action-raise');
          btn.textContent = action.label;
          btn.title = `Action value: ${action.value.toFixed(2)}`;
          btn.addEventListener('click', () => {
            const nextKey = action.history_key || action.key;
            const chosen = { label: historyLabel(nextKey), key: nextKey };
            state.historyPath = path.concat([chosen]);
            render();
          });
          actionsEl.appendChild(btn);
        });
      }

      function bucketLabel(bucketId) {
        if (bucketId < 13) {
          const rank = PAIR_RANKS[bucketId];
          return `${rank}${rank}`;
        }
        const pairIndex = (bucketId - 13) // 2;
        const suited = ((bucketId - 13) % 2) === 1;
        let seen = 0;
        for (let high = 1; high < PAIR_RANKS.length; high++) {
          for (let low = 0; low < high; low++) {
            if (seen === pairIndex) {
              const lowRank = PAIR_RANKS[low];
              const highRank = PAIR_RANKS[high];
              return `${lowRank}${highRank}${suited ? 's' : 'o'}`;
            }
            seen += 1;
          }
        }
        return `B${bucketId}`;
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
        const snapshot = currentSnapshot();
        if (!snapshot) return;
        const grid = document.getElementById('grid');
        grid.innerHTML = '';

        if (currentHistoryKey() === 'f') {
          const msg = document.createElement('div');
          msg.textContent = 'Hand Over.';
          msg.style.fontSize = '30px';
          msg.style.fontWeight = '700';
          msg.style.padding = '22px';
          grid.appendChild(msg);
          return;
        }

        const stateData = currentState();
        const activeRows = stateData && stateData.range_rows ? stateData.range_rows : (snapshot.states && snapshot.states[''] ? snapshot.states[''].range_rows : (snapshot.range_rows || {}));
        const rowOrder = ['A', 'K', 'Q', 'J', 'T', '9', '8', '7', '6', '5', '4', '3', '2'];

        for (let i = 0; i < rowOrder.length; i++) {
          for (let j = 0; j < rowOrder.length; j++) {
            const label = dataKeyForCell(i, j);
            const cell = document.createElement('div');
            cell.className = 'cell';

            const actions = activeRows[label] || { fold: 0, call: 0, raise: 0 };
            const fold = Number(actions.fold || 0);
            const call = Number(actions.call || 0);
            const raise = Number(actions.raise || 0);
            const total = Math.max(1, fold + call + raise);

            const fill = document.createElement('div');
            fill.className = 'stack';

            const foldSeg = document.createElement('div');
            foldSeg.className = 'seg';
            foldSeg.style.background = '#cbd5e1';
            foldSeg.style.height = `${(fold / total) * 100}%`;

            const callSeg = document.createElement('div');
            callSeg.className = 'seg';
            callSeg.style.background = '#86efac';
            callSeg.style.height = `${(call / total) * 100}%`;

            const raiseSeg = document.createElement('div');
            raiseSeg.className = 'seg';
            raiseSeg.style.background = '#ef4444';
            raiseSeg.style.height = `${(raise / total) * 100}%`;

            fill.appendChild(raiseSeg);
            fill.appendChild(callSeg);
            fill.appendChild(foldSeg);
            cell.appendChild(fill);

            const labelEl = document.createElement('div');
            labelEl.className = 'label';
            labelEl.textContent = label;
            cell.appendChild(labelEl);
            grid.appendChild(cell);
          }
        }
      }

      function stateMapForCurrentNode(snapshot) {
        const currentKey = currentHistoryKey();
        const current = snapshot.states && snapshot.states[currentKey] ? snapshot.states[currentKey] : { actions: [] };
        return current.actions || [];
      }

      function renderMeta() {
        const snapshot = currentSnapshot();
        const meta = document.getElementById('meta');
        if (!snapshot) {
          meta.textContent = 'No snapshots found.';
          return;
        }
        const history = currentHistoryKey();
        const actions = stateMapForCurrentNode(snapshot);
        meta.textContent = `checkpoint ${snapshot.checkpoint} · history ${historyLabel(history)} · actions ${actions.length}`;
      }

      function renderLegend() {
        const legend = document.getElementById('legend');
        legend.innerHTML = '';
        const items = [
          ['fold', '#cbd5e1'],
          ['call', '#86efac'],
          ['raise 300', '#ef4444'],
          ['raise 20000', '#7f1d1d'],
        ];
        items.forEach(([label, color]) => {
          const row = document.createElement('div');
          const swatch = document.createElement('span');
          swatch.className = 'swatch';
          swatch.style.background = color;
          row.appendChild(swatch);
          row.appendChild(document.createTextNode(label));
          legend.appendChild(row);
        });
      }

      function render() {
        renderNavigator();
        renderActions();
        renderMeta();
        renderGrid();
        renderLegend();
      }

      if (!data.snapshots || data.snapshots.length === 0) {
        document.getElementById('meta').textContent = 'No snapshots found.';
      } else {
        render();
      }
      if (__REFRESH_SECONDS__ > 0) {
        setInterval(() => location.reload(), __REFRESH_SECONDS__ * 1000);
      }
    </script>
  </body>
</html>
"""
    html = template.replace("__PAYLOAD__", payload)
    html = html.replace("__REFRESH_SECONDS__", str(float(browser_refresh_seconds)))
    if browser_refresh_seconds > 0:
        html = html.replace("__META_REFRESH__", f'<meta http-equiv="refresh" content="{max(1.0, float(browser_refresh_seconds))}" />')
    else:
        html = html.replace("__META_REFRESH__", "")
    output_path.write_text(html, encoding="utf-8")


def main() -> None:
    args = parse_args()
    base_dirs = args.snapshot_dir or args.report_dir or default_snapshot_dirs()
    output_path = Path(args.output)
    browser_refresh_seconds = args.browser_refresh if args.browser_refresh > 0 else 0.0

    def refresh_once() -> None:
        data = build_dashboard_data(base_dirs)
        render_dashboard_html(data, output_path, browser_refresh_seconds=browser_refresh_seconds)
        print(f"Built NLH dashboard from {len(data['snapshots'])} snapshot(s): {output_path}")

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

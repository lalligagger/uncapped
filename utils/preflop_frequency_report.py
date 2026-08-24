#!/usr/bin/env python3
"""Summarize preflop strategy by starting hand and action history.

This script reads the exact-state strategy dump and reports per-starting-hand
frequencies for the preflop open / respond-to-open states.

It prints a human-friendly label next to the raw betting-history string, e.g.
    history=c [preflop_open]  hand=23s  call=72.4% raise=27.6%
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

VALUE_TO_RANK = {idx: rank for idx, rank in enumerate("23456789TJQKA")}
DEFAULT_NOT_IN_RANGE_FOLD_THRESHOLD = 95.0


def bucket_label(bucket_id: int) -> str:
    if bucket_id < 13:
        rank = VALUE_TO_RANK[bucket_id]
        return f"{rank}{rank}"

    pair_index = (bucket_id - 13) // 2
    suited = ((bucket_id - 13) % 2) == 1

    seen = 0
    for high in range(2, 15):
        for low in range(2, high):
            if seen == pair_index:
                suffix = "s" if suited else "o"
                return f"{VALUE_TO_RANK[low - 2]}{VALUE_TO_RANK[high - 2]}{suffix}"
            seen += 1
    raise ValueError(f"Could not decode bucket {bucket_id}")


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


def friendly_history_label(raw_history: str) -> str:
    history = raw_history or ""
    return TARGET_PREFLOP_HISTORIES.get(history, "ignore")


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
                current_entries.append({
                    "history": current_state_key[0],
                    "hole_cards": current_state_key[1],
                    "friendly": friendly_history_label(current_state_key[0]),
                    **bucket,
                })

    return state_map


def is_preflop_state(history: str, hole_cards: str) -> bool:
    history = history or ""
    return history in TARGET_PREFLOP_HISTORIES


def history_slug(history: str) -> str:
    history = history or ""
    return TARGET_PREFLOP_HISTORIES.get(history, f"history_{history}")


def history_display_name(history: str) -> str:
    return history_slug(history)


def summarize_preflop(state_map, nir_threshold: float = DEFAULT_NOT_IN_RANGE_FOLD_THRESHOLD, compute_nir: bool = False):
    rows = defaultdict(list)
    for (history, hole_cards), entries in state_map.items():
        if not entries:
            continue
        if not is_preflop_state(history, hole_cards):
            continue

        if len(entries) == 0:
            continue
        # Count exact private-card combinations for the same hand class rather than
        # counting abstract bucket hits from the reduced-state dump.
        for entry in entries:
            bucket_id = entry["bucket"]
            hand_label = bucket_label(bucket_id)
            rows[(hand_label, history, friendly_history_label(history))].append({
                **entry,
                "hole_cards": hole_cards,
            })

    output_rows = []
    for key, values in sorted(rows.items()):
        hand_label, history, friendly = key
        exact_hands = {v["hole_cards"] for v in values}
        call = sum(v["call"] for v in values) / len(values)
        raise_pct = sum(v["raise"] for v in values) / len(values)
        fold = sum(v["fold"] for v in values) / len(values)
        output_rows.append({
            "hand": hand_label,
            "history": history,
            "friendly": friendly,
            "call": call,
            "raise": raise_pct,
            "fold": fold,
            "count": len(exact_hands),
        })

    if not compute_nir:
        for row in output_rows:
            row["nir"] = 0.0
        output_rows.sort(key=lambda row: (row["hand"], row["history"]))
        return output_rows

    row_by_hand_history = {(row["hand"], row["history"]): row for row in output_rows}
    for row in output_rows:
        history = row["history"]

        # Public-history semantics: deeper states require the immediately preceding
        # public-action prefix. If that prefix never existed, the hand is not in range
        # for this state. The root and the first responder states have no required
        # public prefix, so their NIR is zero by definition.
        if history in ("", "r", "c"):
            row["nir"] = 0.0
            continue

        required_prefix = history[:-1]
        parent_row = row_by_hand_history.get((row["hand"], required_prefix))
        if parent_row is None:
            row["nir"] = 100.0
            continue

        chosen_action = history[-1]
        if chosen_action == "c":
            chosen_mass = parent_row["call"]
        elif chosen_action == "r":
            chosen_mass = parent_row["raise"]
        elif chosen_action == "f":
            chosen_mass = parent_row["fold"]
        else:
            chosen_mass = 0.0

        # If a hand never reached the required public-history prefix, it is NIR.
        # This matches the actual betting-pattern semantics: `rr` requires prior `r`,
        # `cr` requires prior `c`, `crr` requires prior `cr`, etc.
        nir = 100.0 - chosen_mass
        if nir >= nir_threshold:
            nir = 100.0
        row["nir"] = nir

    output_rows.sort(key=lambda row: (row["hand"], row["history"]))
    return output_rows


def main():
    if len(sys.argv) < 2:
        raise SystemExit("Usage: python3 utils/preflop_frequency_report.py <player_file> [--label <all|preflop_open|respond_to_open|respond_to_limp|respond_to_raise|history_xxx>] ")

    player_arg = sys.argv[1]
    player_file = Path(player_arg).resolve()
    if not player_file.exists():
        raise FileNotFoundError(player_file)

    label_filter = "all"
    nir_threshold = DEFAULT_NOT_IN_RANGE_FOLD_THRESHOLD
    compute_nir = False
    argv = sys.argv[1:]
    if "--label" in argv:
        idx = argv.index("--label")
        if idx + 1 < len(argv):
            label_filter = argv[idx + 1]
    if "--nir-threshold" in argv:
        idx = argv.index("--nir-threshold")
        if idx + 1 < len(argv):
            nir_threshold = float(argv[idx + 1])
    if "--compute-nir" in argv:
        compute_nir = True

    # Some archived checkpoints keep an embedded BINARY_FILENAME_PREFIX that points
    # to an older output directory. If that prefix is missing, copy the live dump
    # files there so print_player_strategy can resolve the avg-strategy file.
    embedded_prefix = None
    with player_file.open("r", encoding="utf-8") as fh:
        for line in fh:
            if line.startswith("BINARY_FILENAME_PREFIX "):
                embedded_prefix = line.split(" ", 1)[1].strip()
                break
    repo_root = Path(__file__).resolve().parents[1]
    if embedded_prefix:
        expected_prefix = (repo_root / embedded_prefix).resolve()
        expected_strategy = expected_prefix.with_name(expected_prefix.name + ".avg-strategy")
        expected_player = expected_prefix.with_name(expected_prefix.name + ".player")
        if not expected_strategy.exists() and not expected_player.exists():
            expected_prefix.parent.mkdir(parents=True, exist_ok=True)
            sibling_strategy = player_file.with_suffix(".avg-strategy")
            if sibling_strategy.exists():
                shutil.copy2(sibling_strategy, expected_strategy)
            if player_file.exists():
                shutil.copy2(player_file, expected_player)

    binary = repo_root / "print_player_strategy"
    embedded_prefix = None
    with player_file.open("r", encoding="utf-8") as fh:
        for line in fh:
            if line.startswith("BINARY_FILENAME_PREFIX "):
                embedded_prefix = line.split(" ", 1)[1].strip()
                break
    if embedded_prefix:
        expected_prefix = (repo_root / embedded_prefix).resolve()
        expected_strategy = expected_prefix.with_name(expected_prefix.name + ".avg-strategy")
        expected_regrets = expected_prefix.with_name(expected_prefix.name + ".regrets")
        expected_player = expected_prefix.with_name(expected_prefix.name + ".player")
        if not expected_strategy.exists() or not expected_regrets.exists() or not expected_player.exists():
            expected_prefix.parent.mkdir(parents=True, exist_ok=True)
            for suffix, target in ((".avg-strategy", expected_strategy), (".regrets", expected_regrets), (".player", expected_player)):
                source = player_file.with_suffix(suffix)
                if source.exists() and not target.exists():
                    shutil.copy2(source, target)

    completed = subprocess.run([str(binary), str(player_file), "--show-private", "--max-round=2"], capture_output=True, check=True)
    stdout = completed.stdout.decode("utf-8", errors="replace")
    state_map = parse_strategy_dump(stdout)
    rows = summarize_preflop(state_map, nir_threshold=nir_threshold, compute_nir=compute_nir)

    def filter_rows(rows, requested):
        if requested == "all":
            return rows
        if requested == "open":
            requested = "preflop_open"
        if requested == "respond_to_open":
            return [row for row in rows if row["history"] == "r"]
        if requested == "respond_to_limp":
            return [row for row in rows if row["history"] == "c"]
        if requested == "respond_to_3bet":
            return [row for row in rows if row["history"] == "rr"]
        if requested == "limper_respond_to_raise":
            return [row for row in rows if row["history"] == "cr"]
        if requested == "respond_to_limp_3bet":
            return [row for row in rows if row["history"] == "crr"]
        if requested == "limper_respond_to_4bet":
            return [row for row in rows if row["history"] == "crrr"]
        if requested == "respond_to_4bet":
            return [row for row in rows if row["history"] == "rrr"]
        if requested.startswith("history_"):
            return [row for row in rows if row["history"] == requested.replace("history_", "")]
        return [row for row in rows if row["friendly"] == requested]

    rows = filter_rows(rows, label_filter)

    title = "Preflop hand frequency summary"
    if label_filter != "all":
        title = f"Preflop hand frequency summary ({label_filter})"

    print(title)
    print("hand | history | label | call% | raise% | fold% | nir | n")
    for row in rows:
        label = f"{row['history']} [{row['friendly']}]"
        print(f"{row['hand']:>5} | {label:<18} | {row['call']:.2f}% | {row['raise']:.2f}% | {row['fold']:.2f}% | {row['nir']:.2f}% | {row['count']}")

    suffix = ""
    if label_filter != "all":
        suffix = f".{label_filter}"
    output_path = player_file.with_name(player_file.stem + f".preflop_report{suffix}.txt")
    with output_path.open("w", encoding="utf-8") as fh:
        fh.write(f"{title}\n")
        fh.write("hand | history | label | call% | raise% | fold% | nir | n\n")
        for row in rows:
            label = f"{row['history']} [{row['friendly']}]"
            fh.write(f"{row['hand']:>5} | {label:<18} | {row['call']:.2f}% | {row['raise']:.2f}% | {row['fold']:.2f}% | {row['nir']:.2f}% | {row['count']}\n")
    print(f"Wrote {output_path}")

    if label_filter == "all":
        by_history = defaultdict(list)
        for row in rows:
            by_history[row["history"]].append(row)
        for history, grouped_rows in sorted(by_history.items()):
            report_name = history_slug(history)
            specific_path = player_file.with_name(player_file.stem + f".preflop_report.{report_name}.txt")
            title_for_history = f"Preflop hand frequency summary ({report_name})"
            with specific_path.open("w", encoding="utf-8") as fh:
                fh.write(f"{title_for_history}\n")
                fh.write("hand | history | label | call% | raise% | fold% | nir | n\n")
                for row in sorted(grouped_rows, key=lambda r: r["hand"]):
                    label = f"{row['history']} [{row['friendly']}]"
                    fh.write(f"{row['hand']:>5} | {label:<18} | {row['call']:.2f}% | {row['raise']:.2f}% | {row['fold']:.2f}% | {row['nir']:.2f}% | {row['count']}\n")
            print(f"Wrote {specific_path}")


if __name__ == "__main__":
    main()

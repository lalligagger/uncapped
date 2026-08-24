#!/usr/bin/env python3
"""Print human-readable bucket labels for the current reduced abstractions.

Preflop bucketing is intended to distinguish:
- pocket pairs: 22, 33, ..., AA
- unique rank pairs: 23, 24, ..., AK
- suited vs offsuit variants for the same rank pair

This matches the ACPC internal card model and avoids duplicate labels like 23 and
32 being treated as different buckets.
"""

from __future__ import annotations

RANKS = "23456789TJQKA"
VALUE_TO_RANK = {idx: rank for idx, rank in enumerate(RANKS)}

PIO25_FLOP_LANDMARKS = [
    "KhKdTs",
    "Kh8s7s",
    "9s8s5h",
    "AsQs9h",
    "KsTsTh",
    "Js5h4d",
    "9s6s2s",
    "AsQhQd",
    "6s4h2d",
    "8s6h2d",
    "Ts8h3s",
    "As6s5s",
    "AsAhKs",
    "7s5h2s",
    "QhJs8s",
    "Ks9h3d",
    "As7h3d",
    "Ah5s4s",
    "Js9h6s",
    "QsTs2h",
    "9s7h4d",
    "8h4s3s",
    "Qs7h5d",
    "JhTs6s",
    "Js4h3s",
]


def preflop_bucket_label(bucket_id: int) -> str:
    """Convert a preflop bucket index to a readable hand label."""
    if not 0 <= bucket_id < 169:
        raise ValueError(f"bucket_id must be in [0, 168], got {bucket_id}")

    if bucket_id < 13:
        rank = VALUE_TO_RANK[bucket_id]
        return f"{rank}{rank}"

    pair_index = (bucket_id - 13) // 2
    suited = ((bucket_id - 13) % 2) == 1

    seen = 0
    for high in range(2, 15):
        for low in range(2, high):
            if seen == pair_index:
                low_rank = low
                high_rank = high
                suffix = "s" if suited else "o"
                return f"{VALUE_TO_RANK[low_rank - 2]}{VALUE_TO_RANK[high_rank - 2]}{suffix}"
            seen += 1

    raise ValueError(f"Could not decode bucket id {bucket_id}")


def print_preflop_mapping() -> None:
    print("Preflop bucket ids (unique rank pair + suited/offsuit):")
    print("bucket_id  label")
    for b in range(169):
        label = preflop_bucket_label(b)
        print(f"{b:>3}      {label}")
    print()


def print_flop_mapping() -> None:
    print("PIO25 flop bucket ids (representative landmark flops):")
    print("bucket_id  representative_flop")
    for b, flop in enumerate(PIO25_FLOP_LANDMARKS):
        print(f"{b:>3}      {flop}")
    print()


def main() -> None:
    print_preflop_mapping()
    print_flop_mapping()


if __name__ == "__main__":
    main()

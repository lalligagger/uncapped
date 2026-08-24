#!/usr/bin/env python3
"""Generate the PIO25 25-bucket flop lookup map.

This script uses a landmark set of 25 representative flops and assigns every
canonical 3-card flop in the full 22,100-flop space to the nearest landmark.
The output is a flat text file containing one integer bucket ID per canonical
flop, so the C++ loader can use it directly.
"""

from __future__ import annotations

from collections import Counter
from itertools import combinations
from pathlib import Path

NUM_BUCKETS = 25
TOTAL_CANONICAL_FLOPS = 22_100

# These are the 25 landmark flops from the poker benchmark outline.
# They are intentionally stored as strings like "KhKdTs" and are used as the
# bucket prototypes.  The assignment logic compares each physical flop against
# all landmarks using a suit-agnostic feature vector.
LANDMARKS_25 = [
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

RANK_ORDER = "23456789TJQKA"
SUIT_ORDER = {"c": 0, "d": 1, "h": 2, "s": 3}
RANK_TO_VALUE = {rank: idx + 2 for idx, rank in enumerate(RANK_ORDER)}


def parse_card(card: str) -> tuple[int, int]:
    rank = card[:-1]
    suit = card[-1]
    return RANK_TO_VALUE[rank], SUIT_ORDER[suit]


def flop_signature(flop_cards: tuple[int, int, int]) -> tuple[int, ...]:
    """A suit-agnostic signature used for nearest-landmark assignment.

    The goal is to match flop families by rank structure and texture, while being
    invariant to suit color and ordering.
    """
    ranks = sorted(score_card(card) for card in flop_cards)
    rank_counts = Counter(ranks)
    suit_counts = Counter(card_suit(card) for card in flop_cards)

    # Build a compact feature vector.
    # 1) sorted ranks, 2) rank histogram, 3) suit histogram, 4) spread.
    feature = []
    feature.extend(ranks)
    for rank in range(2, 15):
        feature.append(rank_counts.get(rank, 0))
    for suit in range(4):
        feature.append(suit_counts.get(suit, 0))
    feature.append(max(ranks) - min(ranks))
    feature.append(len(set(ranks)))
    return tuple(feature)


def score_card(card: int) -> int:
    return (card % 13) + 2


def card_suit(card: int) -> int:
    return card // 13


def canonical_card_indices_from_flop_str(flop_str: str) -> tuple[int, int, int]:
    cards = []
    for i in range(0, len(flop_str), 2):
        c = flop_str[i : i + 2]
        rank_char = c[:-1]
        suit_char = c[-1]
        rank_val = RANK_TO_VALUE[rank_char]
        suit_val = SUIT_ORDER[suit_char]
        card_idx = (suit_val * 13) + (rank_val - 2)
        cards.append(card_idx)
    return tuple(sorted(cards))


def canonical_index_for_flop(flop: tuple[int, int, int]) -> int:
    """Return the canonical index in the full 22,100-flop set."""
    sorted_flop = tuple(sorted(flop))
    idx = 0
    for combo in combinations(range(52), 3):
        if combo == sorted_flop:
            return idx
        idx += 1
    raise ValueError(f"Flop {sorted_flop} not found in canonical set")


def landmark_signatures() -> list[tuple[int, ...]]:
    landmarks = []
    for landmark in LANDMARKS_25:
        if len(landmark) != 6:
            raise ValueError(f"Bad landmark string: {landmark!r}")
        cards = canonical_card_indices_from_flop_str(landmark)
        landmarks.append(flop_signature(cards))
    return landmarks


def euclidean_distance(a: tuple[int, ...], b: tuple[int, ...]) -> float:
    return sum((x - y) ** 2 for x, y in zip(a, b)) ** 0.5


def generate_bucket_map() -> list[int]:
    landmarks = landmark_signatures()
    bucket_map = [0] * TOTAL_CANONICAL_FLOPS

    all_flops = list(combinations(range(52), 3))
    for canonical_idx, flop in enumerate(all_flops):
        sig = flop_signature(flop)
        best_bucket = min(
            range(len(landmarks)),
            key=lambda i: euclidean_distance(sig, landmarks[i]),
        )
        bucket_map[canonical_idx] = best_bucket

    return bucket_map


def write_map(path: Path, bucket_map: list[int]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        fh.write("\n".join(str(v) for v in bucket_map))
        fh.write("\n")


def main() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    out_path = repo_root / "pio25_flop_map.dat"
    bucket_map = generate_bucket_map()
    assert len(bucket_map) == TOTAL_CANONICAL_FLOPS
    write_map(out_path, bucket_map)
    print(f"Wrote {len(bucket_map)} bucket IDs to {out_path}")
    counts = [sum(1 for v in bucket_map if v == i) for i in range(NUM_BUCKETS)]
    print(f"Bucket counts: {counts}")


if __name__ == "__main__":
    main()

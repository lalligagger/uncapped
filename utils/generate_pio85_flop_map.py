#!/usr/bin/env python3
"""Generate a PIO85 85-bucket flop lookup map from a custom landmark set."""

from __future__ import annotations

from collections import Counter
from itertools import combinations
from pathlib import Path

NUM_BUCKETS = 85
TOTAL_CANONICAL_FLOPS = 22_100

LANDMARKS_85 = [
    "AsKhQs",
    "Ks6h4d",
    "Ts7h4d",
    "As7h4s",
    "9h8s5s",
    "7h6s3s",
    "Ts4h3s",
    "QhQdTs",
    "Js6s5h",
    "KhTs8s",
    "Qs9h4s",
    "9h4s3s",
    "7h6s2s",
    "Ts9s8s",
    "QsJh2d",
    "KhKd9s",
    "Th3s2s",
    "JsTh9s",
    "Kh7s2s",
    "Ts8h5d",
    "AsTh8d",
    "As6h3s",
    "9h7s5s",
    "AsKhJd",
    "QsJh7d",
    "KhQs6s",
    "Js8h2d",
    "JsTh2d",
    "Js4s3h",
    "As5h3s",
    "KhQs5s",
    "8s7s6h",
    "Qs9h9d",
    "5s4s2s",
    "QsJs6h",
    "Qs7h2d",
    "KsQh5s",
    "QsThTd",
    "AsKh3d",
    "As9h6d",
    "KhKd3s",
    "As6h5s",
    "As4h2s",
    "Ts7h6s",
    "9s6h3d",
    "Qs8h3d",
    "JsJh2s",
    "Kh5s3s",
    "8s6h6d",
    "Js9h8s",
    "4s2s2h",
    "7s7h2s",
    "AsTh9d",
    "9s3s3h",
    "Ts6h2s",
    "JsTh5s",
    "8s8h2s",
    "Js8h5d",
    "As8h7s",
    "Qs9s2h",
    "AsTh5d",
    "3s3h3d",
    "8h5s2s",
    "As8h8d",
    "Js4s4h",
    "AsJh8s",
    "9h6s4s",
    "As6h4d",
    "KsJs4h",
    "Qs5h3s",
    "Ks8s3s",
    "8s2s2h",
    "Ks5h4d",
    "Qs4h4d",
    "7s4h3d",
    "Ks9h7d",
    "Ks9s7s",
    "Ks3h2s",
    "AsQh7d",
    "5h5d2s",
    "KsTs6h",
    "Js7s3h",
    "AhJs3s",
    "8s6h4s",
    "Ts8h7d",
]

RANK_ORDER = "23456789TJQKA"
SUIT_ORDER = {"c": 0, "d": 1, "h": 2, "s": 3}
RANK_TO_VALUE = {rank: idx + 2 for idx, rank in enumerate(RANK_ORDER)}


def score_card(card: int) -> int:
    return (card % 13) + 2


def card_suit(card: int) -> int:
    return card // 13


def parse_card(card: str) -> tuple[int, int]:
    rank = card[:-1]
    suit = card[-1]
    return RANK_TO_VALUE[rank], SUIT_ORDER[suit]


def flop_signature(flop_cards: tuple[int, int, int]) -> tuple[int, ...]:
    ranks = sorted(score_card(card) for card in flop_cards)
    rank_counts = Counter(ranks)
    suit_counts = Counter(card_suit(card) for card in flop_cards)

    feature: list[int] = []
    feature.extend(ranks)
    for rank in range(2, 15):
        feature.append(rank_counts.get(rank, 0))
    for suit in range(4):
        feature.append(suit_counts.get(suit, 0))
    feature.append(max(ranks) - min(ranks))
    feature.append(len(set(ranks)))
    return tuple(feature)


def canonical_card_indices_from_flop_str(flop_str: str) -> tuple[int, int, int]:
    cards = []
    for i in range(0, len(flop_str), 2):
        c = flop_str[i : i + 2]
        rank_char = c[:-1]
        suit_char = c[-1]
        rank_val = RANK_TO_VALUE[rank_char]
        suit_val = SUIT_ORDER[suit_char]
        cards.append((suit_val * 13) + (rank_val - 2))
    return tuple(sorted(cards))


def landmark_signatures() -> list[tuple[int, ...]]:
    landmarks = []
    for landmark in LANDMARKS_85:
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
    out_path = repo_root / "pio85_flop_map.dat"
    bucket_map = generate_bucket_map()
    assert len(bucket_map) == TOTAL_CANONICAL_FLOPS
    write_map(out_path, bucket_map)
    print(f"Wrote {len(bucket_map)} bucket IDs to {out_path}")
    counts = [sum(1 for v in bucket_map if v == i) for i in range(NUM_BUCKETS)]
    print(f"Bucket counts: {counts}")


if __name__ == "__main__":
    main()

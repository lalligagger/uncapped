#!/usr/bin/env python3

from utils.preflop_frequency_report import parse_bucket_line


def test_merge_pot_and_all_in_raises_into_single_raise_band():
    payload = "Bucket 0: 20.4315%c 46.9543%r300 32.6142%r20000"
    parsed = parse_bucket_line(payload)
    assert parsed["bucket"] == 0
    assert parsed["call"] == 20.4315
    assert parsed["raise"] == 46.9543 + 32.6142
    assert parsed["fold"] == 0.0


if __name__ == "__main__":
    test_merge_pot_and_all_in_raises_into_single_raise_band()
    print("merged raise reporting test passed")

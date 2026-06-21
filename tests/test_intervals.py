"""Unit tests for the interval-union merge logic."""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from datetime import datetime, timezone
from analysis import merge_intervals, total_hours_from_merged


def dt(h, m=0):
    return datetime(2024, 1, 1, h, m, tzinfo=timezone.utc)


def test_no_overlap():
    merged = merge_intervals([dt(10), dt(14)], [dt(12), dt(16)])
    assert merged == [(dt(10), dt(12)), (dt(14), dt(16))]
    assert total_hours_from_merged(merged) == 4.0


def test_full_overlap():
    merged = merge_intervals([dt(10), dt(11)], [dt(16), dt(14)])
    assert merged == [(dt(10), dt(16))]
    assert total_hours_from_merged(merged) == 6.0


def test_partial_overlap():
    # 10-13, 12-15 -> 10-15 = 5h
    merged = merge_intervals([dt(10), dt(12)], [dt(13), dt(15)])
    assert merged == [(dt(10), dt(15))]
    assert total_hours_from_merged(merged) == 5.0


def test_touching():
    # 10-12, 12-14 -> 10-14 = 4h (touching intervals merge)
    merged = merge_intervals([dt(10), dt(12)], [dt(12), dt(14)])
    assert merged == [(dt(10), dt(14))]
    assert total_hours_from_merged(merged) == 4.0


def test_empty():
    assert merge_intervals([], []) == []


def test_single():
    merged = merge_intervals([dt(8)], [dt(10)])
    assert merged == [(dt(8), dt(10))]
    assert total_hours_from_merged(merged) == 2.0


def test_three_intervals_two_groups():
    # 10-12, 11-13, 15-17 -> (10-13), (15-17) = 3+2 = 5h
    merged = merge_intervals([dt(10), dt(11), dt(15)], [dt(12), dt(13), dt(17)])
    assert merged == [(dt(10), dt(13)), (dt(15), dt(17))]
    assert total_hours_from_merged(merged) == 5.0


if __name__ == "__main__":
    test_no_overlap()
    test_full_overlap()
    test_partial_overlap()
    test_touching()
    test_empty()
    test_single()
    test_three_intervals_two_groups()
    print("All interval-union tests passed.")

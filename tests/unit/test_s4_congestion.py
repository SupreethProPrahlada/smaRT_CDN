import random

import pytest

from scripts.congestion import adaptive_rate, random_rate


@pytest.mark.parametrize(
    "current,utilization,expected",
    [(10, 0.2, 20), (40, 0.6, 40), (80, 0.9, 70), (100, 0.1, 100), (10, 0.9, 10)],
)
def test_s4_adaptive_congestion_adjusts_rate_with_utilization(current, utilization, expected):
    assert adaptive_rate(current, utilization) == expected


def test_s4_random_congestion_is_reproducible_for_fixed_seed():
    first_rng = random.Random(1)
    first = [random_rate(first_rng) for _ in range(5)]
    second_rng = random.Random(1)
    second = [random_rate(second_rng) for _ in range(5)]
    assert first == second

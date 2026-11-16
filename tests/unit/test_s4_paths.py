import pytest

from controller.paths import should_use_detour


@pytest.mark.parametrize(
    "rtt_ms,link_up,expected",
    [
        (59.9, True, False),
        (60.0, True, True),
        (500.0, False, True),
        (10.0, True, False),
    ],
)
def test_s4_detour_decision_obeys_latency_delta_and_link_state(rtt_ms, link_up, expected):
    assert should_use_detour(rtt_ms, 10.0, link_up) is expected

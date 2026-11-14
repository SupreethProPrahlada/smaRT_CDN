import pytest

pytestmark = [pytest.mark.integration, pytest.mark.system]


def test_tc22_dynamic_static_comparison():
    """TC22 FR-11: compare routes for same client mix under dynamic/static modes."""
    pytest.skip("Requires repeatable multi-client Mininet experiment and agreed comparison metrics")


def test_tc24_all_servers_down_policy():
    """TC24 FR-4: no healthy backend is handled according to stakeholder policy."""
    pytest.skip("Expected all-down behavior is unresolved; selector currently falls back to srv1")

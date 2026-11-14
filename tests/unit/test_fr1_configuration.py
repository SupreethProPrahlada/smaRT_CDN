from config.settings import (
    VIP_IP, VIP_MAC, HB_LISTEN_IP, HB_PORT, HEARTBEAT_INTERVAL, CHUNK_SIZE,
    PROBE_ETHERTYPE, PROBE_INTERVAL, STATS_INTERVAL, EMA_ALPHA, SELECTION_WEIGHTS,
    CLIENT_IPS, SERVERS, CONTENT_PORT, OFP_CONTROLLER_PORT,
)


def test_tc01_vip_configuration():
    """TC01 FR-1: configured VIP identity is stable."""
    assert (VIP_IP, VIP_MAC) == ("10.0.0.100", "00:00:00:00:01:00")


def test_tc29_heartbeat_endpoint_and_period_constants():
    """TC29 FR-4: configured heartbeat destination and sender period."""
    assert (HB_LISTEN_IP, HB_PORT, HEARTBEAT_INTERVAL) == ("10.0.0.254", 9000, 2.0)


def test_tc25_probe_configuration():
    """TC25 FR-2: probe packet type, interval, and EMA alpha match the contract."""
    assert PROBE_ETHERTYPE == 0x88B5
    assert PROBE_INTERVAL == 1.0
    assert STATS_INTERVAL == 1.0
    assert EMA_ALPHA == 0.5


def test_tc26_selection_weight_configuration():
    """TC26 FR-5: balanced selection uses the specified three weights."""
    assert SELECTION_WEIGHTS == {"latency": 0.4, "utilization": 0.4, "load": 0.2}


def test_tc27_chunk_size_configuration():
    """TC27 FR-7: the server/client chunk size is 64 KiB."""
    assert CHUNK_SIZE == 65536


def test_tc28_address_and_port_configuration():
    """TC28 FR-1: client/server addresses and application/control ports match contracts."""
    assert set(CLIENT_IPS.values()) == {f"10.0.0.{i}" for i in range(1, 7)}
    assert {server["ip"] for server in SERVERS.values()} == {"10.0.0.11", "10.0.0.12", "10.0.0.13"}
    assert (CONTENT_PORT, OFP_CONTROLLER_PORT) == (8000, 6653)

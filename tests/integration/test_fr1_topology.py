import pytest


@pytest.mark.integration
def test_tc34_topology_builds_required_switches_hosts_and_trunks():
    """TC34 Sprint 1: topology declares s1-s4, six clients, three servers and shaped trunks."""
    pytest.importorskip("mininet.topo")
    from topology.topo import SmartCDNTopo

    topo = SmartCDNTopo()

    assert set(topo.switches()) == {"s1", "s2", "s3", "s4"}
    assert set(topo.hosts()) == {f"c{i}" for i in range(1, 7)} | {"srv1", "srv2", "srv3"}
    assert topo.nodeInfo("s1")["protocols"] == "OpenFlow13"
    links = {(src, dst): info for src, dst, info in topo.links(withInfo=True)}
    assert links[("s1", "s2")]["bw"] == 100
    assert links[("s1", "s2")]["delay"] == "5ms"
    assert links[("s1", "s3")]["bw"] == 50
    assert links[("s1", "s3")]["delay"] == "20ms"
    assert links[("s1", "s4")]["bw"] == 10
    assert links[("s1", "s4")]["delay"] == "50ms"

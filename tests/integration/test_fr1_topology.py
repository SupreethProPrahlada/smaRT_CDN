import pytest


@pytest.mark.integration
def test_tc34_topology_builds_required_switches_hosts_and_trunks():
    """TC34 Sprint 1/4: topology declares s1-s5, six clients, three servers, bg and shaped trunks."""
    pytest.importorskip("mininet.topo")
    from topology.topo import SmartCDNTopo

    topo = SmartCDNTopo()

    assert set(topo.switches()) == {"s1", "s2", "s3", "s4", "s5"}
    assert set(topo.hosts()) == {f"c{i}" for i in range(1, 7)} | {"srv1", "srv2", "srv3", "bg"}
    assert topo.nodeInfo("s1")["protocols"] == "OpenFlow13"
    links = {(src, dst): info for src, dst, info in topo.links(withInfo=True)}
    assert links[("s1", "s2")]["bw"] == 100
    assert links[("s1", "s2")]["delay"] == "5ms"
    assert links[("s1", "s3")]["bw"] == 50
    assert links[("s1", "s3")]["delay"] == "20ms"
    assert links[("s1", "s4")]["bw"] == 10
    assert links[("s1", "s4")]["delay"] == "50ms"
    # Sprint 4 detour s1 -> s5 -> s2 on the ports the controller expects.
    assert links[("s1", "s5")]["bw"] == 100 and links[("s1", "s5")]["delay"] == "10ms"
    assert (links[("s1", "s5")]["port1"], links[("s1", "s5")]["port2"]) == (10, 1)
    assert links[("s5", "s2")]["delay"] == "5ms"
    assert (links[("s5", "s2")]["port1"], links[("s5", "s2")]["port2"]) == (2, 3)

import pytest


@pytest.mark.integration
def test_tc34_topology_builds_required_switches_hosts_and_trunks():
    """TC34: topology declares all switches/hosts and retains shaped Sprint 1 trunks."""
    pytest.importorskip("mininet.topo")
    from topology.topo import SmartCDNTopo

    topo = SmartCDNTopo()

    assert set(topo.switches()) == {"s1", "s2", "s3", "s4", "s5"}
    assert set(topo.hosts()) == {f"c{i}" for i in range(1, 7)} | {"srv1", "srv2", "srv3", "loadsrc"}
    assert topo.nodeInfo("s1")["protocols"] == "OpenFlow13"
    links = {(src, dst): info for src, dst, info in topo.links(withInfo=True)}
    assert links[("s1", "s2")]["bw"] == 100
    assert links[("s1", "s2")]["delay"] == "5ms"
    assert links[("s1", "s3")]["bw"] == 50
    assert links[("s1", "s3")]["delay"] == "20ms"
    assert links[("s1", "s4")]["bw"] == 10
    assert links[("s1", "s4")]["delay"] == "50ms"


@pytest.mark.integration
def test_s4_topology_adds_detour_and_congestion_source():
    """Sprint 4 FR-9/FR-12: s5 detour and loadsrc attach to the primary edge."""
    pytest.importorskip("mininet.topo")
    from topology.topo import SmartCDNTopo

    topo = SmartCDNTopo()

    assert "s5" in topo.switches()
    assert "loadsrc" in topo.hosts()
    links = {(src, dst): info for src, dst, info in topo.links(withInfo=True)}
    assert ("s1", "s5") in links
    assert ("s5", "s2") in links
    assert ("loadsrc", "s1") in links
    assert topo.port("s1", "s2") == (7, 2)
    assert topo.port("s1", "s5") == (10, 1)
    assert topo.port("s5", "s2") == (2, 3)
    assert topo.port("s1", "loadsrc") == (11, 0)

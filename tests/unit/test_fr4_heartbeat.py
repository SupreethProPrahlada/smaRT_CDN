import socket

import app.server as server_module
from app.server import ContentServer


def test_tc08_heartbeat_datagram_contract(monkeypatch):
    """TC08 FR-4: sender emits the status datagram to the configured endpoint every 2s."""
    sent = []
    sleeps = []

    class FakeDatagramSocket:
        def sendto(self, payload, address):
            sent.append((payload, address))

        def close(self):
            sent.append(("closed", None))

    server = ContentServer("srv2", "127.0.0.1")
    server.active_connections = 3
    monkeypatch.setattr(server_module.socket, "socket", lambda *args: FakeDatagramSocket())
    monkeypatch.setattr(server_module.time, "time", lambda: 1234.5)

    def sleep_once(seconds):
        sleeps.append(seconds)
        server.running = False

    monkeypatch.setattr(server_module.time, "sleep", sleep_once)
    server.heartbeat_loop()

    assert sent[0] == (b"STATUS srv2 3 1234.500\n", ("10.0.0.254", 9000))
    assert (server_module.HB_LISTEN_IP, server_module.HB_PORT) == ("10.0.0.254", 9000)
    assert server_module.HEARTBEAT_INTERVAL == 2.0
    assert sent[-1] == ("closed", None)
    assert sleeps == [2.0]

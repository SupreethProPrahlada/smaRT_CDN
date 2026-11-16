"""Sprint 3 (Developer 2): FR-7 byte-offset retry/resume and traversal defence."""

import hashlib
import os
import socket
import threading

import pytest

import app.client as client_module
import app.server as server_module
import config.transfer_logger as transfer_logger
from app.server import ContentServer


class ScriptedSocket:
    """One connection: records the request and replays scripted recv() results."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.request = None

    def settimeout(self, value):
        pass

    def connect(self, address):
        pass

    def sendall(self, data):
        self.request = data

    def recv(self, size):
        if not self.responses:
            return b""
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    def close(self):
        pass


@pytest.fixture
def connections(monkeypatch, tmp_path):
    """Feed the client one ScriptedSocket per connection attempt."""
    monkeypatch.setattr(client_module, "CLIENT_DOWNLOAD_DIR", str(tmp_path / "downloads"))
    monkeypatch.setattr(transfer_logger, "CLIENT_TRANSFERS_CSV", str(tmp_path / "metrics.csv"))
    monkeypatch.setattr(client_module, "CLIENT_RETRY_DELAY", 0)
    made = []

    def install(*scripts):
        queue = [ScriptedSocket(s) for s in scripts]

        def factory(*args):
            sock = queue.pop(0) if queue else ScriptedSocket([])
            made.append(sock)
            return sock

        monkeypatch.setattr(client_module.socket, "socket", factory)
        return made

    return install


def test_tc42_client_resumes_from_received_offset(connections, tmp_path, capsys):
    """TC42 FR-7: after a dropped connection the client asks for the rest and verifies the whole file."""
    payload = b"0123456789"
    made = connections(
        [b"OK 10 10\n0123", b""],                 # connection breaks after 4 bytes
        [b"OK 10 6\n456789"],                     # resumed from byte 4
    )

    client_module.download("c1", "f.bin", hashlib.sha256(payload).hexdigest(), "127.0.0.1", 8000)

    out = capsys.readouterr().out
    assert [s.request for s in made] == [b"GET f.bin 0\n", b"GET f.bin 4\n"]
    assert (tmp_path / "downloads" / "c1_f.bin").read_bytes() == payload
    assert "PASS" in out and "retries=1" in out


def test_tc43_client_resumes_after_timeout(connections, capsys):
    """TC43 FR-7: a stalled connection (socket timeout) is retried like a closed one."""
    payload = b"abcdef"
    made = connections([b"OK 6 6\nab", socket.timeout("timed out")], [b"OK 6 4\ncdef"])

    client_module.download("c1", "f.bin", hashlib.sha256(payload).hexdigest(), "127.0.0.1", 8000)

    assert made[1].request == b"GET f.bin 2\n"
    assert "PASS" in capsys.readouterr().out


def test_tc44_resume_rejects_a_different_file_size(connections, capsys):
    """TC44 FR-7: a resumed response for a different file size fails instead of splicing data."""
    made = connections([b"OK 10 10\n0123", b""], [b"OK 99 95\nxxxx"])

    client_module.download("c1", "f.bin", None, "127.0.0.1", 8000)

    out = capsys.readouterr().out
    assert len(made) == 2
    assert "FAIL" in out and "does not match" in out


def test_tc45_server_error_is_not_retried(connections, capsys):
    """TC45 FR-7: an ERR reply (e.g. missing file) fails at once; retrying cannot help."""
    made = connections([b"ERR File_Not_Found f.bin\n"])

    client_module.download("c1", "f.bin", None, "127.0.0.1", 8000)

    assert len(made) == 1
    assert "File_Not_Found" in capsys.readouterr().out


def test_tc46_client_gives_up_after_max_retries(connections, monkeypatch, capsys):
    """TC46 FR-7: the client stops after CLIENT_MAX_RETRIES and reports an incomplete download."""
    monkeypatch.setattr(client_module, "CLIENT_MAX_RETRIES", 2)
    made = connections([b"OK 10 10\n01", b""])   # later connections close immediately

    client_module.download("c1", "f.bin", None, "127.0.0.1", 8000)

    out = capsys.readouterr().out
    assert len(made) == 3
    assert "FAIL" in out and "received 2 of 10 bytes" in out


def _server_request(monkeypatch, content_dir, request):
    monkeypatch.setattr(server_module, "CONTENT_DIR", str(content_dir))
    left, right = socket.socketpair()
    thread = threading.Thread(target=ContentServer("srv1", "127.0.0.1").handle_client, args=(left, None))
    thread.start()
    right.sendall(request)
    right.shutdown(socket.SHUT_WR)
    response = bytearray()
    while True:
        part = right.recv(4096)
        if not part:
            break
        response.extend(part)
    thread.join(timeout=2)
    right.close()
    return bytes(response)


def test_tc47_server_streams_from_requested_offset(monkeypatch, tmp_path):
    """TC47 FR-7: GET with an offset returns the remaining bytes and the full size."""
    (tmp_path / "f.bin").write_bytes(b"0123456789")

    assert _server_request(monkeypatch, tmp_path, b"GET f.bin 4\n") == b"OK 10 6\n456789"


@pytest.mark.parametrize("name", ["..", ".", "../../etc/passwd/.."])
def test_tc48_server_rejects_directory_names(monkeypatch, tmp_path, name):
    """TC48 FR-7: names that resolve to a directory are refused (traversal defence)."""
    assert _server_request(monkeypatch, tmp_path, f"GET {name} 0\n".encode()) == b"ERR Bad_Request\n"


def test_tc49_server_rejects_symlink_escaping_content_dir(monkeypatch, tmp_path):
    """TC49 FR-7: a symlink inside the content directory cannot expose a file outside it."""
    secret = tmp_path / "secret.txt"
    secret.write_text("private")
    content = tmp_path / "content"
    content.mkdir()
    os.symlink(secret, content / "link.bin")

    assert _server_request(monkeypatch, content, b"GET link.bin 0\n") == b"ERR Bad_Request\n"

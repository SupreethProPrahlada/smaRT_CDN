import csv
import hashlib

import pytest
import app.client as client_module


class FakeStreamSocket:
    def __init__(self, responses):
        self.responses = list(responses)
        self.connected = None
        self.request = None
        self.closed = False

    def connect(self, address):
        self.connected = address

    def sendall(self, data):
        self.request = data

    def recv(self, size):
        return self.responses.pop(0) if self.responses else b""

    def close(self):
        self.closed = True


def _client_paths(monkeypatch, tmp_path):
    monkeypatch.setattr(client_module, "CLIENT_DOWNLOAD_DIR", str(tmp_path / "downloads"))
    monkeypatch.setattr(client_module, "CLIENT_TRANSFERS_CSV", str(tmp_path / "metrics.csv"))


def test_tc30_client_download_saves_verified_bytes(monkeypatch, tmp_path, capsys):
    """TC30 FR-7: client saves exact downloaded bytes and verifies SHA-256."""
    payload = b"sample payload crossing normal TCP boundaries"
    response = f"OK {len(payload)} {len(payload)}\n".encode() + payload
    sock = FakeStreamSocket([response])
    _client_paths(monkeypatch, tmp_path)
    monkeypatch.setattr(client_module.socket, "socket", lambda *args: sock)

    client_module.download("c1", "sample.bin", hashlib.sha256(payload).hexdigest(), "127.0.0.1", 8123)

    assert sock.connected == ("127.0.0.1", 8123)
    assert sock.request == b"GET sample.bin 0\n"
    assert sock.closed
    assert (tmp_path / "downloads" / "c1_sample.bin").read_bytes() == payload
    assert "PASS" in capsys.readouterr().out


def test_tc31_client_hash_mismatch_is_reported(monkeypatch, tmp_path, capsys):
    """TC31 FR-7: a supplied nonmatching SHA-256 is reported as a failure."""
    payload = b"actual bytes"
    sock = FakeStreamSocket([f"OK {len(payload)} {len(payload)}\n".encode() + payload])
    _client_paths(monkeypatch, tmp_path)
    monkeypatch.setattr(client_module.socket, "socket", lambda *args: sock)

    client_module.download("c2", "sample.bin", "0" * 64, "127.0.0.1", 8123)

    assert "FAIL" in capsys.readouterr().out


def test_tc_s3_client_retries_from_last_written_byte(monkeypatch, tmp_path, capsys):
    """Sprint 3 FR-7: resume retries request precisely the persisted offset."""
    payload = b"0123456789"
    first = FakeStreamSocket([b"OK 10 10\n0123", b""])
    second = FakeStreamSocket([b"OK 10 6\n456789"])
    sockets = iter((first, second))
    delays = []
    _client_paths(monkeypatch, tmp_path)
    monkeypatch.setattr(client_module.socket, "socket", lambda *args: next(sockets))
    monkeypatch.setattr(client_module.time, "sleep", delays.append)

    client_module.download(
        "c3", "resume.bin", hashlib.sha256(payload).hexdigest(), "127.0.0.1", 8123
    )

    assert first.request == b"GET resume.bin 0\n"
    assert second.request == b"GET resume.bin 4\n"
    assert delays == [1.0]
    assert (tmp_path / "downloads" / "c3_resume.bin").read_bytes() == payload
    assert "PASS" in capsys.readouterr().out


def test_tc_s3_client_stops_after_twelve_retries(monkeypatch, tmp_path):
    """Sprint 3 FR-7: retry count is bounded to twelve reconnects."""
    sockets = []
    delays = []

    def make_socket(*_args):
        response = b"OK 8 8\nx" if not sockets else b"OK 8 7\n"
        sock = FakeStreamSocket([response, b""])
        sockets.append(sock)
        return sock

    _client_paths(monkeypatch, tmp_path)
    monkeypatch.setattr(client_module.socket, "socket", make_socket)
    monkeypatch.setattr(client_module.time, "sleep", delays.append)

    client_module.download("c3", "retry.bin", None, "127.0.0.1", 8123)

    assert len(sockets) == 13
    assert delays == [1.0] * 12


def test_tc32_client_rejects_truncated_payload_without_expected_hash(monkeypatch, tmp_path, capsys):
    """TC32 FR-7: truncated transfer must not be reported successful without a supplied hash."""
    sock = FakeStreamSocket([b"OK 8 8\nabcd", b""])
    _client_paths(monkeypatch, tmp_path)
    monkeypatch.setattr(client_module.socket, "socket", lambda *args: sock)
    monkeypatch.setattr(client_module.time, "sleep", lambda _seconds: None)

    client_module.download("c3", "partial.bin", None, "127.0.0.1", 8123)

    output = capsys.readouterr().out
    with (tmp_path / "metrics.csv").open(newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert ("FAIL" in output, rows[0]["sha256_match"]) == (True, "False")


def test_tc41_client_handles_missing_file_response(monkeypatch, tmp_path):
    """TC41 FR-7: a closed connection for a missing file should be a controlled failure."""
    sock = FakeStreamSocket([b""])
    _client_paths(monkeypatch, tmp_path)
    monkeypatch.setattr(client_module.socket, "socket", lambda *args: sock)
    monkeypatch.setattr(client_module.time, "sleep", lambda _seconds: None)

    client_module.download("c5", "missing.bin", None, "127.0.0.1", 8123)


def test_tc18_client_csv_header_and_metrics(monkeypatch, tmp_path):
    """TC18 FR-8: client logs the documented transfer metrics to CSV."""
    payload = b"csv payload"
    sock = FakeStreamSocket([f"OK {len(payload)} {len(payload)}\n".encode() + payload])
    _client_paths(monkeypatch, tmp_path)
    monkeypatch.setattr(client_module.socket, "socket", lambda *args: sock)

    client_module.download("c4", "csv.bin", hashlib.sha256(payload).hexdigest(), "127.0.0.1", 8123)

    with (tmp_path / "metrics.csv").open(newline="") as stream:
        reader = csv.DictReader(stream)
        rows = list(reader)
        assert reader.fieldnames == [
            "timestamp", "client_id", "target_ip", "filename", "size_bytes",
            "ttfb_ms", "duration_s", "throughput_mbps", "sha256_match",
        ]
    assert len(rows) == 1
    assert rows[0]["client_id"] == "c4"
    assert rows[0]["sha256_match"] == "True"
    assert rows[0]["size_bytes"] == str(len(payload))

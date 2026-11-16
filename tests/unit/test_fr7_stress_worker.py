import hashlib

import pytest
import scripts.stress_test as stress_module


class FakeStreamSocket:
    def __init__(self, responses):
        self.responses = list(responses)

    def settimeout(self, seconds):
        self.timeout = seconds

    def connect(self, address):
        self.address = address

    def sendall(self, data):
        self.request = data

    def recv(self, size):
        return self.responses.pop(0) if self.responses else b""

    def close(self):
        pass


def test_tc36_stress_worker_hash_matches_received_payload(monkeypatch):
    """TC36 FR-7: stress worker records the digest of the exact received bytes."""
    payload = b"parallel stream payload"
    stress_module.worker_results.clear()
    sock = FakeStreamSocket([f"OK {len(payload)} {len(payload)}\n".encode() + payload, b""])
    monkeypatch.setattr(stress_module.socket, "socket", lambda *args: sock)

    stress_module.download_worker(1, "file.bin", "127.0.0.1", 8000)

    result = stress_module.worker_results[-1]
    assert result["success"] is True
    assert result["bytes"] == len(payload)
    assert result["sha256"] == hashlib.sha256(payload).hexdigest()


def test_tc37_stress_worker_rejects_truncated_payload(monkeypatch):
    """TC37 FR-7: stress worker must reject payload shorter than the server header total."""
    stress_module.worker_results.clear()
    sock = FakeStreamSocket([b"OK 8 8\nabcd", b""])
    monkeypatch.setattr(stress_module.socket, "socket", lambda *args: sock)

    stress_module.download_worker(1, "file.bin", "127.0.0.1", 8000)

    assert stress_module.worker_results[-1]["success"] is False


def test_fr8_stress_worker_csv_uses_shared_client_schema(monkeypatch, tmp_path):
    """FR-8: the stress tester appends rows with exactly the client CSV schema."""
    import csv

    from config.settings import CLIENT_TRANSFER_FIELDS

    path = tmp_path / "metrics.csv"
    monkeypatch.setattr(stress_module, "CLIENT_TRANSFERS_CSV", str(path))
    stress_module.worker_results.clear()
    stress_module.worker_results.append({
        "worker_id": 1,
        "filename": "file.bin",
        "vip": "10.0.0.100",
        "bytes": 10,
        "expected_bytes": 10,
        "duration": 1.0,
        "ttfb_ms": 2.0,
        "mbps": 0.08,
        "sha256": "0" * 64,
        "sha256_match": True,
        "success": True,
        "status": "PASS",
        "error": None,
    })

    stress_module.log_to_csv()

    with path.open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        rows = list(reader)
    assert reader.fieldnames == CLIENT_TRANSFER_FIELDS
    assert len(rows) == 1 and rows[0]["client_id"] == "worker_1"

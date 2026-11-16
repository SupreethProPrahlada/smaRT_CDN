import hashlib
import socket
import threading

import pytest
import app.server as server_module
from app.server import ContentServer


def _request(monkeypatch, tmp_path, request, filename="payload.bin", payload=b"abc"):
    monkeypatch.setattr(server_module, "CONTENT_DIR", str(tmp_path))
    (tmp_path / filename).write_bytes(payload)
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


def test_tc14_non_aligned_binary_payload(monkeypatch, tmp_path):
    """TC14 FR-7: exact non-64KiB-multiple binary stream and SHA-256."""
    payload = bytes(range(256)) * 258  # 66048 bytes, one chunk plus 512 bytes
    response = _request(monkeypatch, tmp_path, b"GET payload.bin 0\n", payload=payload)
    header, body = response.split(b"\n", 1)
    assert header == f"OK {len(payload)} {len(payload)}".encode()
    assert body == payload
    assert hashlib.sha256(body).hexdigest() == hashlib.sha256(payload).hexdigest()


def test_tc15_empty_file_stream(monkeypatch, tmp_path):
    """TC15 FR-7: empty file returns zero-length successful payload."""
    response = _request(monkeypatch, tmp_path, b"GET payload.bin 0\n", payload=b"")
    assert response == b"OK 0 0\n"


def test_tc16_missing_file_is_not_reported_as_success(monkeypatch, tmp_path):
    """TC16 FR-7: a missing content file must not receive a success header."""
    monkeypatch.setattr(server_module, "CONTENT_DIR", str(tmp_path))
    server = ContentServer("srv1", "127.0.0.1")
    left, right = socket.socketpair()
    thread = threading.Thread(target=server.handle_client, args=(left, None))
    thread.start()
    right.sendall(b"GET absent.bin 0\n")
    right.shutdown(socket.SHUT_WR)
    response = right.recv(128)
    assert not response.startswith(b"OK ")
    right.close()
    thread.join(timeout=2)
    assert not thread.is_alive()


def test_tc23_simultaneous_server_streams_remain_independent(monkeypatch, tmp_path):
    """TC23 FR-7: concurrent connections receive their own complete file bytes."""
    monkeypatch.setattr(server_module, "CONTENT_DIR", str(tmp_path))
    payloads = {f"item{i}.bin": bytes([i]) * (1000 + i) for i in range(1, 4)}
    for name, payload in payloads.items():
        (tmp_path / name).write_bytes(payload)

    server = ContentServer("srv1", "127.0.0.1")
    peers = []
    threads = []
    results = {}

    for name in payloads:
        left, right = socket.socketpair()
        peers.append(right)
        thread = threading.Thread(target=server.handle_client, args=(left, None))
        threads.append(thread)
        thread.start()
        right.sendall(f"GET {name} 0\n".encode())
        right.shutdown(socket.SHUT_WR)

    for (name, _), right, thread in zip(payloads.items(), peers, threads):
        response = bytearray()
        while True:
            chunk = right.recv(4096)
            if not chunk:
                break
            response.extend(chunk)
        results[name] = bytes(response).split(b"\n", 1)[1]
        right.close()
        thread.join(timeout=2)
        assert not thread.is_alive()

    assert results == payloads
    assert server.active_connections == 0

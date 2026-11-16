import argparse
import hashlib
import os
import socket
import sys
import time
from datetime import datetime

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from config.transfer_logger import append_transfer

from config.settings import (
    VIP_IP,
    CONTENT_PORT,
    CHUNK_SIZE,
    CLIENT_DOWNLOAD_DIR,
    CLIENT_MAX_RETRIES,
    CLIENT_RETRY_DELAY,
    CLIENT_SOCKET_TIMEOUT,
)


class ServerError(RuntimeError):
    """The server answered with ERR: retrying the same request cannot help."""


def _read_header(sock):
    """Return (total, remaining, bytes already received after the header)."""
    header_buffer = b""
    while b"\n" not in header_buffer:
        chunk = sock.recv(1024)
        if not chunk:
            raise ConnectionError("server closed before sending a response")
        header_buffer += chunk

    header, _, data = header_buffer.partition(b"\n")
    parts = header.decode(errors="replace").split()
    if not parts or parts[0] != "OK":
        message = " ".join(parts[1:]) if parts else "empty response"
        raise ServerError(f"server error: {message}")
    if len(parts) != 3:
        raise ServerError("invalid success header")
    try:
        total_bytes, remaining = int(parts[1]), int(parts[2])
    except ValueError as exc:
        raise ServerError("invalid byte count in server header") from exc
    if total_bytes < 0 or remaining < 0 or remaining > total_bytes:
        raise ServerError("invalid byte count in server header")
    if len(data) > remaining:
        raise ServerError("server sent more data than advertised")
    return total_bytes, remaining, data


def download(client_id, filename, expected_hash=None, target_ip=VIP_IP, port=CONTENT_PORT):
    """Download through the VIP, reconnecting and resuming at the received byte offset.

    Sprint 3 (FR-7): when a connection breaks (server crash, path change that
    resets it), the client reconnects up to CLIENT_MAX_RETRIES times and sends
    `GET <file> <bytes received>`, so the controller can steer it to a healthy
    replica and the transfer continues where it stopped. The SHA-256 covers the
    whole file across all connections.
    """
    os.makedirs(CLIENT_DOWNLOAD_DIR, exist_ok=True)
    out_path = os.path.join(CLIENT_DOWNLOAD_DIR, f"{client_id}_{filename}")

    start = time.time()
    ttfb = 0.0
    received = 0
    total_bytes = None
    retries = 0
    duration = 0.0
    mbps = 0.0
    hash_match = None
    status = "FAIL"
    error_message = None
    hasher = hashlib.sha256()

    with open(out_path, "wb") as output_file:
        while True:
            sock = None
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                if hasattr(sock, "settimeout"):
                    sock.settimeout(CLIENT_SOCKET_TIMEOUT)
                sock.connect((target_ip, port))
                sock.sendall(f"GET {filename} {received}\n".encode())

                total, remaining, data = _read_header(sock)
                if total_bytes is None:
                    total_bytes = total
                    ttfb = (time.time() - start) * 1000.0
                elif total != total_bytes or remaining != total - received:
                    raise ServerError("resumed response does not match the file being downloaded")

                target = received + remaining
                while True:
                    if data:
                        output_file.write(data)
                        hasher.update(data)
                        received += len(data)
                    if received >= target:
                        break
                    data = sock.recv(min(CHUNK_SIZE, target - received))
                    if not data:
                        raise ConnectionError(
                            f"connection closed at {received} of {total_bytes} bytes")
                error_message = None
                break
            except ServerError as exc:
                error_message = str(exc)
                break
            except (OSError, ConnectionError) as exc:
                error_message = str(exc) or type(exc).__name__
                if retries >= CLIENT_MAX_RETRIES:
                    break
                retries += 1
                print(f"[{client_id}] connection lost ({error_message}); "
                      f"retry {retries}/{CLIENT_MAX_RETRIES} from byte {received}")
                time.sleep(CLIENT_RETRY_DELAY)
            finally:
                if sock is not None:
                    sock.close()

    duration = time.time() - start
    mbps = (received * 8) / (duration * 1_000_000) if duration > 0 else 0.0

    if error_message is None:
        if expected_hash is not None:
            hash_match = hasher.hexdigest().lower() == expected_hash.lower()
        if expected_hash is None:
            status = "UNVERIFIED"
        elif hash_match:
            status = "PASS"
        else:
            error_message = "SHA-256 hash mismatch"
    elif total_bytes is not None and received < total_bytes:
        hash_match = False
        error_message = (f"incomplete download: received {received} of "
                         f"{total_bytes} bytes ({error_message})")

    if error_message:
        status = "FAIL"
        print(f"[{client_id}] Download FAIL: {error_message}")
    else:
        print(
            f"[{client_id}] Download {status}: {received} bytes "
            f"in {duration:.2f}s ({mbps:.2f} Mbps), retries={retries}"
        )

    append_transfer({
        "timestamp": datetime.now().isoformat(),
        "client_id": client_id,
        "target_ip": target_ip,
        "filename": filename,
        "size_bytes": received,
        "ttfb_ms": round(ttfb, 2),
        "duration_s": round(duration, 3),
        "throughput_mbps": round(mbps, 2),
        "sha256_match": hash_match,
        "status": status,
    })


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--id", default="c1")
    parser.add_argument("--file", required=True)
    parser.add_argument("--hash", default=None)
    args = parser.parse_args()

    download(args.id, args.file, args.hash)

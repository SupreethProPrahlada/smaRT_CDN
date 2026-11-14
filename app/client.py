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
)


def download(client_id, filename, expected_hash=None, target_ip=VIP_IP, port=CONTENT_PORT):
    os.makedirs(CLIENT_DOWNLOAD_DIR, exist_ok=True)
    out_path = os.path.join(CLIENT_DOWNLOAD_DIR, f"{client_id}_{filename}")

    start = time.time()
    ttfb = 0.0
    received = 0
    duration = 0.0
    mbps = 0.0
    hash_match = None
    status = "FAIL"
    error_message = None
    hasher = hashlib.sha256()

    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        if hasattr(sock, "settimeout"):
            sock.settimeout(15)
        sock.connect((target_ip, port))
        try:
            sock.sendall(f"GET {filename} 0\n".encode())

            header_buffer = b""
            while b"\n" not in header_buffer:
                chunk = sock.recv(1024)
                if not chunk:
                    raise ConnectionError("server closed before sending a response")
                header_buffer += chunk

            ttfb = (time.time() - start) * 1000.0
            header, _, data = header_buffer.partition(b"\n")
            parts = header.decode(errors="replace").split()

            if not parts or parts[0] != "OK":
                message = " ".join(parts[1:]) if parts else "empty response"
                raise RuntimeError(f"server error: {message}")

            if len(parts) != 3:
                raise RuntimeError("invalid success header")

            try:
                total_bytes = int(parts[1])
                expected_bytes = int(parts[2])
            except ValueError as exc:
                raise RuntimeError("invalid byte count in server header") from exc

            if total_bytes < 0 or expected_bytes < 0 or expected_bytes > total_bytes:
                raise RuntimeError("invalid byte count in server header")

            if len(data) > expected_bytes:
                raise RuntimeError("server sent more data than advertised")

            with open(out_path, "wb") as output_file:
                if data:
                    output_file.write(data)
                    hasher.update(data)
                    received += len(data)

                while received < expected_bytes:
                    chunk = sock.recv(min(CHUNK_SIZE, expected_bytes - received))
                    if not chunk:
                        break
                    output_file.write(chunk)
                    hasher.update(chunk)
                    received += len(chunk)

            duration = time.time() - start
            mbps = (received * 8) / (duration * 1_000_000) if duration > 0 else 0.0

            complete = received == expected_bytes
            if expected_hash is not None:
                hash_match = hasher.hexdigest().lower() == expected_hash.lower()

            if not complete:
                hash_match = False
                status = "FAIL"
                error_message = (
                    f"incomplete download: received {received} of "
                    f"{expected_bytes} bytes"
                )
            elif expected_hash is None:
                status = "UNVERIFIED"
            elif hash_match:
                status = "PASS"
            else:
                status = "FAIL"
                error_message = "SHA-256 hash mismatch"

        finally:
            sock.close()
    except (OSError, RuntimeError, ConnectionError) as exc:
        duration = time.time() - start
        mbps = (received * 8) / (duration * 1_000_000) if duration > 0 else 0.0
        error_message = str(exc)

    if error_message:
        print(f"[{client_id}] Download FAIL: {error_message}")
    else:
        print(
            f"[{client_id}] Download {status}: {received} bytes "
            f"in {duration:.2f}s ({mbps:.2f} Mbps)"
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

import argparse
import csv
import hashlib
import os
import socket
import sys
import time
from datetime import datetime

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from config.settings import (
    VIP_IP,
    CONTENT_PORT,
    CHUNK_SIZE,
    MAX_RETRIES,
    CLIENT_RETRY_DELAY,
    CLIENT_DOWNLOAD_DIR,
    CLIENT_TRANSFERS_CSV,
    CLIENT_TRANSFER_FIELDS,
)


def download(client_id, filename, expected_hash=None, target_ip=VIP_IP, port=CONTENT_PORT):
    os.makedirs(CLIENT_DOWNLOAD_DIR, exist_ok=True)
    out_path = os.path.join(CLIENT_DOWNLOAD_DIR, f"{client_id}_{filename}")

    start = time.time()
    ttfb = 0.0
    received = 0
    total_bytes = None
    duration = 0.0
    mbps = 0.0
    hash_match = None
    status = "FAIL"
    error_message = None
    hasher = hashlib.sha256()
    retries = 0

    with open(out_path, "wb") as output_file:
        while total_bytes is None or received < total_bytes:
            sock = None
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                if hasattr(sock, "settimeout"):
                    sock.settimeout(15)
                sock.connect((target_ip, port))
                sock.sendall(f"GET {filename} {received}\n".encode())

                header_buffer = b""
                while b"\n" not in header_buffer:
                    chunk = sock.recv(1024)
                    if not chunk:
                        raise ConnectionError("server closed before sending a response")
                    header_buffer += chunk
                    if len(header_buffer) > 4096:
                        raise RuntimeError("response header is too large")

                if not ttfb:
                    ttfb = (time.time() - start) * 1000.0
                header, _, data = header_buffer.partition(b"\n")
                parts = header.decode(errors="replace").split()

                if not parts or parts[0] != "OK":
                    message = " ".join(parts[1:]) if parts else "empty response"
                    raise RuntimeError(f"server error: {message}")
                if len(parts) != 3:
                    raise RuntimeError("invalid success header")
                try:
                    reported_total, remaining = int(parts[1]), int(parts[2])
                except ValueError as exc:
                    raise RuntimeError("invalid byte count in server header") from exc

                if reported_total < 0 or remaining < 0 or received + remaining != reported_total:
                    raise RuntimeError("invalid byte count in server header")
                if total_bytes is not None and total_bytes != reported_total:
                    raise RuntimeError("server changed total size during resume")
                total_bytes = reported_total
                if len(data) > remaining:
                    raise RuntimeError("server sent more data than advertised")

                if data:
                    output_file.write(data)
                    hasher.update(data)
                    received += len(data)
                while received < total_bytes:
                    chunk = sock.recv(min(CHUNK_SIZE, total_bytes - received))
                    if not chunk:
                        raise ConnectionError(
                            f"incomplete download: received {received} of {total_bytes} bytes"
                        )
                    output_file.write(chunk)
                    hasher.update(chunk)
                    received += len(chunk)
                output_file.flush()
            except (OSError, ConnectionError) as exc:
                error_message = str(exc)
                if retries >= MAX_RETRIES:
                    break
                retries += 1
                time.sleep(CLIENT_RETRY_DELAY)
            except RuntimeError as exc:
                error_message = str(exc)
                break
            finally:
                if sock is not None:
                    sock.close()

    duration = time.time() - start
    mbps = (received * 8) / (duration * 1_000_000) if duration > 0 else 0.0
    complete = total_bytes is not None and received == total_bytes
    if expected_hash is not None:
        hash_match = complete and hasher.hexdigest().lower() == expected_hash.lower()

    if not complete:
        hash_match = False
        status = "FAIL"
        if error_message is None:
            error_message = f"incomplete download: received {received} of {total_bytes or 0} bytes"
    elif expected_hash is None:
        status = "UNVERIFIED"
        error_message = None
    elif hash_match:
        status = "PASS"
        error_message = None
    else:
        status = "FAIL"
        error_message = "SHA-256 hash mismatch"

    if error_message:
        print(f"[{client_id}] Download FAIL: {error_message}")
    else:
        print(
            f"[{client_id}] Download {status}: {received} bytes "
            f"in {duration:.2f}s ({mbps:.2f} Mbps)"
        )

    os.makedirs(os.path.dirname(CLIENT_TRANSFERS_CSV), exist_ok=True)
    write_header = not os.path.isfile(CLIENT_TRANSFERS_CSV)

    with open(CLIENT_TRANSFERS_CSV, "a", newline="", encoding="utf-8") as csv_file:
        writer = csv.writer(csv_file)
        if write_header:
            writer.writerow(CLIENT_TRANSFER_FIELDS)

        writer.writerow(
            [
                datetime.now().isoformat(),
                client_id,
                target_ip,
                filename,
                received,
                round(ttfb, 2),
                round(duration, 3),
                round(mbps, 2),
                hash_match,
            ]
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--id", default="c1")
    parser.add_argument("--file", required=True)
    parser.add_argument("--hash", default=None)
    args = parser.parse_args()

    download(args.id, args.file, args.hash)

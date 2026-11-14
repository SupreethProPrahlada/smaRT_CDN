#!/usr/bin/env python3

import argparse
import csv
import hashlib
import os
import socket
import sys
import threading
import time
from datetime import datetime

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from config.settings import (
    VIP_IP,
    CONTENT_PORT,
    CHUNK_SIZE,
    CLIENT_TRANSFERS_CSV,
)

results_lock = threading.Lock()
worker_results = []


def download_worker(worker_id, filename, vip, port, expected_hash=None):
    start = time.time()
    ttfb_ms = 0.0
    received = 0
    expected_bytes = None
    hasher = hashlib.sha256()
    error = None
    hash_match = None

    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        if hasattr(sock, "settimeout"):
            sock.settimeout(30)
        sock.connect((vip, port))
        try:
            sock.sendall(f"GET {filename} 0\n".encode("utf-8"))

            header_buffer = b""
            while b"\n" not in header_buffer:
                chunk = sock.recv(1024)
                if not chunk:
                    raise ConnectionError("server closed before sending a response")
                header_buffer += chunk

            ttfb_ms = (time.time() - start) * 1000.0
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

            if (
                total_bytes < 0
                or expected_bytes < 0
                or expected_bytes > total_bytes
            ):
                raise RuntimeError("invalid byte count in server header")

            if len(data) > expected_bytes:
                raise RuntimeError("server sent more data than advertised")

            received = len(data)
            hasher.update(data)

            while received < expected_bytes:
                chunk = sock.recv(min(CHUNK_SIZE, expected_bytes - received))
                if not chunk:
                    break
                received += len(chunk)
                hasher.update(chunk)

            digest = hasher.hexdigest()
            complete = received == expected_bytes

            if expected_hash is not None:
                hash_match = digest.lower() == expected_hash.lower()

            if not complete:
                status = "FAIL"
                error = f"incomplete: received {received} of {expected_bytes} bytes"
            elif expected_hash is None:
                status = "UNVERIFIED"
            elif hash_match:
                status = "PASS"
            else:
                status = "FAIL"
                error = "SHA-256 hash mismatch"

        finally:
            sock.close()
    except (OSError, RuntimeError, ConnectionError) as exc:
        digest = hasher.hexdigest()
        status = "FAIL"
        error = str(exc)
        if expected_hash is not None:
            hash_match = digest.lower() == expected_hash.lower()

    duration = time.time() - start
    mbps = (received * 8.0) / (duration * 1_000_000.0) if duration > 0 else 0.0

    result = {
        "worker_id": worker_id,
        "filename": filename,
        "vip": vip,
        "bytes": received,
        "expected_bytes": expected_bytes,
        "duration": duration,
        "ttfb_ms": ttfb_ms,
        "mbps": mbps,
        "sha256": digest,
        "sha256_match": hash_match,
        "success": status in ("PASS", "UNVERIFIED"),
        "status": status,
        "error": error,
    }

    with results_lock:
        worker_results.append(result)


def log_to_csv():
    os.makedirs(os.path.dirname(CLIENT_TRANSFERS_CSV), exist_ok=True)
    write_header = not os.path.isfile(CLIENT_TRANSFERS_CSV)

    with open(CLIENT_TRANSFERS_CSV, "a", newline="", encoding="utf-8") as csv_file:
        writer = csv.writer(csv_file)

        if write_header:
            writer.writerow(
                [
                    "timestamp",
                    "client_id",
                    "target_ip",
                    "filename",
                    "size_bytes",
                    "ttfb_ms",
                    "duration_s",
                    "throughput_mbps",
                    "sha256_match",
                    "status",
                ]
            )

        timestamp = datetime.now().isoformat()

        for result in sorted(worker_results, key=lambda item: item["worker_id"]):
            writer.writerow(
                [
                    timestamp,
                    f"worker_{result['worker_id']}",
                    result["vip"],
                    result["filename"],
                    result["bytes"],
                    round(result["ttfb_ms"], 2),
                    round(result["duration"], 3),
                    round(result["mbps"], 2),
                    result["sha256_match"],
                    result["status"],
                ]
            )


def main():
    parser = argparse.ArgumentParser(description="CDN concurrency stress tester")
    parser.add_argument("--concurrency", type=int, default=3)
    parser.add_argument("--file", default="test_10M.bin")
    parser.add_argument("--vip", default=VIP_IP)
    parser.add_argument("--port", type=int, default=CONTENT_PORT)
    parser.add_argument(
        "--hash",
        default=None,
        help="Expected SHA-256 hash for verifying each downloaded file",
    )
    args = parser.parse_args()

    if args.concurrency < 1:
        parser.error("--concurrency must be at least 1")

    worker_results.clear()

    print(f"Target: {args.vip}:{args.port}")
    print(f"File: {args.file}")
    print(f"Launching {args.concurrency} concurrent streams")

    threads = []
    wall_start = time.time()

    for worker_id in range(1, args.concurrency + 1):
        thread = threading.Thread(
            target=download_worker,
            args=(worker_id, args.file, args.vip, args.port, args.hash),
        )
        threads.append(thread)
        thread.start()

    for thread in threads:
        thread.join()

    wall_time = time.time() - wall_start
    total_bytes = sum(result["bytes"] for result in worker_results)
    aggregate_mbps = (
        (total_bytes * 8.0) / (wall_time * 1_000_000.0)
        if wall_time > 0
        else 0.0
    )

    all_pass = True

    print()
    print(f"{'STREAM':<10}{'BYTES':<14}{'TIME (s)':<12}{'THROUGHPUT':<16}{'STATUS'}")

    for result in sorted(worker_results, key=lambda item: item["worker_id"]):
        print(
            f"Worker {result['worker_id']:<3}"
            f"{result['bytes']:<14}"
            f"{result['duration']:<12.2f}"
            f"{result['mbps']:.2f} Mbps     "
            f"{result['status']}"
        )

        if result["status"] != "PASS":
            all_pass = False

        if result["error"]:
            print(f"  Error: {result['error']}")

    print()
    print(f"Total transferred: {total_bytes / (1024 * 1024):.2f} MB")
    print(f"Wall clock time:   {wall_time:.2f} seconds")
    print(f"Aggregate rate:    {aggregate_mbps:.2f} Mbps")

    if args.hash is None:
        print("Integrity:         UNVERIFIED (no expected hash supplied)")
    elif all_pass:
        print("Integrity:         PASS (all sizes and hashes verified)")
    else:
        print("Integrity:         FAIL")

    log_to_csv()
    print(f"Results appended to: {CLIENT_TRANSFERS_CSV}")


if __name__ == "__main__":
    main()

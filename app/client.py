"""
Smart CDN - Content Client
Requests files through Virtual IP (10.0.0.100), measures speed, verifies SHA-256.
Owned by Developer 1 (Supreeth Prahalada) - Sprint 1.
"""

import socket
import hashlib
import time
import os
import sys
import argparse
import csv
from datetime import datetime

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from config.settings import VIP_IP, CONTENT_PORT, CHUNK_SIZE, CLIENT_DOWNLOAD_DIR, CLIENT_TRANSFERS_CSV


def log_transfer_metrics(client_id, server_ip, filename, file_size, ttfb_ms, duration_s, throughput_mbps, verified):
    """Appends download metrics to results/data/client-transfers.csv (FR-8)."""
    os.makedirs(os.path.dirname(CLIENT_TRANSFERS_CSV), exist_ok=True)
    file_exists = os.path.isfile(CLIENT_TRANSFERS_CSV)

    with open(CLIENT_TRANSFERS_CSV, 'a', newline='') as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow([
                'timestamp', 'client_id', 'target_ip', 'filename',
                'file_size_bytes', 'ttfb_ms', 'duration_s', 'throughput_mbps',
                'retries', 'sha256_verified'
            ])
        writer.writerow([
            datetime.now().isoformat(),
            client_id,
            server_ip,
            filename,
            file_size,
            round(ttfb_ms, 2),
            round(duration_s, 4),
            round(throughput_mbps, 2),
            0, # 0 retries in Sprint 1 baseline
            verified
        ])


def download_file(client_id: str, filename: str, expected_hash: str = None, target_ip: str = VIP_IP, port: int = CONTENT_PORT):
    os.makedirs(CLIENT_DOWNLOAD_DIR, exist_ok=True)
    output_path = os.path.join(CLIENT_DOWNLOAD_DIR, f"{client_id}_{filename}")

    print(f"[{client_id}] Connecting to CDN VIP {target_ip}:{port} for file '{filename}'...")
    start_time = time.time()
    ttfb = 0.0

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(10.0)

    try:
        sock.connect((target_ip, port))
        req = f"GET {filename} 0\n"
        sock.sendall(req.encode('utf-8'))

        # Read header response until \n
        header_data = b""
        while b"\n" not in header_data:
            chunk = sock.recv(1024)
            if not chunk:
                break
            header_data += chunk

        ttfb = (time.time() - start_time) * 1000.0 # milliseconds

        header_line = header_data.split(b"\n")[0].decode('utf-8')
        if not header_line.startswith("OK"):
            print(f"[{client_id}] Server error response: {header_line}")
            return False

        _, total_str, remaining_str = header_line.split()
        remaining_bytes = int(remaining_str)

        # Remaining bytes from header chunk
        initial_payload = header_data[len(header_line) + 1:]

        hasher = hashlib.sha256()
        bytes_received = 0

        with open(output_path, 'wb') as f:
            if initial_payload:
                f.write(initial_payload)
                hasher.update(initial_payload)
                bytes_received += len(initial_payload)

            while bytes_received < remaining_bytes:
                chunk = sock.recv(CHUNK_SIZE)
                if not chunk:
                    break
                f.write(chunk)
                hasher.update(chunk)
                bytes_received += len(chunk)

        total_duration = time.time() - start_time
        calc_hash = hasher.hexdigest()
        throughput_mbps = (bytes_received * 8) / (total_duration * 1_000_000)

        verified = (expected_hash.lower() == calc_hash.lower()) if expected_hash else True

        print(f"\n[{client_id}] --- Download Summary ---")
        print(f"  Target:          {target_ip}:{port}")
        print(f"  Bytes Received:  {bytes_received} / {remaining_bytes}")
        print(f"  TTFB:            {ttfb:.2f} ms")
        print(f"  Total Duration:  {total_duration:.3f} s")
        print(f"  Throughput:      {throughput_mbps:.2f} Mbps")
        print(f"  SHA-256 Hash:    {calc_hash}")
        if expected_hash:
            print(f"  Integrity Check: {'PASS (100% Match)' if verified else 'FAIL (Hash Mismatch!)'}")

        # Log metrics to CSV
        log_transfer_metrics(client_id, target_ip, filename, bytes_received, ttfb, total_duration, throughput_mbps, verified)
        return verified

    except Exception as e:
        print(f"[{client_id}] Error during download: {e}")
        return False
    finally:
        sock.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Smart CDN Client Downloader")
    parser.add_argument('--id', default='c1', help="Client ID (e.g. c1)")
    parser.add_argument('--file', required=True, help="File to download")
    parser.add_argument('--hash', default=None, help="Expected SHA-256 checksum for verification")
    parser.add_argument('--ip', default=VIP_IP, help="Target IP (default: 10.0.0.100)")
    parser.add_argument('--port', type=int, default=CONTENT_PORT, help="Target port")
    args = parser.parse_args()

    download_file(client_id=args.id, filename=args.file, expected_hash=args.hash, target_ip=args.ip, port=args.port)

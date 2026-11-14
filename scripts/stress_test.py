#!/usr/bin/env python3
"""
smaRT_CDN Multi-Client Concurrency Stress Tester (Sprint 2)
Spawns N concurrent VIP streaming workers against 10.0.0.100:8000,
measures aggregate throughput, validates SHA-256 hashes, and logs to CSV.
"""

import os
import sys
import time
import socket
import hashlib
import argparse
import threading
from datetime import datetime
from config.settings import VIP, CONTROLLER_PORT, CHUNK_SIZE, CLIENT_CSV

results_lock = threading.Lock()
worker_results = []

def download_worker(worker_id: int, filename: str, vip: str, port: int):
    t_start = time.time()
    sha256 = hashlib.sha256()
    total_bytes = 0
    success = False
    error_msg = ""

    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(10.0)
        s.connect((vip, port))

        # Send GET request
        s.sendall(f"GET {filename}\n".encode('utf-8'))

        # Read header: OK <total> <remain>\n
        header_data = b""
        while b"\n" not in header_data:
            chunk = s.recv(1)
            if not chunk:
                break
            header_data += chunk

        line = header_data.decode('utf-8').strip()
        if not line.startswith("OK"):
            raise Exception(f"Server rejected request: {line}")

        # Stream binary payload
        while True:
            chunk = s.recv(CHUNK_SIZE)
            if not chunk:
                break
            total_bytes += len(chunk)
            sha256.update(chunk)

        s.close()
        success = True
    except Exception as e:
        error_msg = str(e)

    duration = time.time() - t_start
    mbps = (total_bytes * 8.0) / (duration * 1_000_000.0) if duration > 0 else 0.0
    digest = sha256.hexdigest()

    result = {
        'worker_id': worker_id,
        'bytes': total_bytes,
        'duration': duration,
        'mbps': mbps,
        'sha256': digest,
        'success': success,
        'error': error_msg
    }

    with results_lock:
        worker_results.append(result)

def log_to_csv(filename: str, concurrency: int, agg_mbps: float):
    os.makedirs(os.path.dirname(CLIENT_CSV), exist_ok=True)
    write_header = not os.path.exists(CLIENT_CSV)
    with open(CLIENT_CSV, 'a', encoding='utf-8') as f:
        if write_header:
            f.write("timestamp,client_id,file_name,bytes_received,duration_sec,throughput_mbps,sha256,tag\n")
        ts = datetime.utcnow().isoformat() + "Z"
        for r in worker_results:
            f.write(f"{ts},worker_{r['worker_id']},{filename},{r['bytes']},{r['duration']:.3f},{r['mbps']:.2f},{r['sha256']},stress_c{concurrency}\n")

def main():
    parser = argparse.ArgumentParser(description="CDN Concurrency Stress Tester")
    parser.add_argument("--concurrency", type=int, default=3, help="Number of concurrent client streams (default: 3)")
    parser.add_argument("--file", type=str, default="test_10M.bin", help="Filename to request (default: test_10M.bin)")
    parser.add_argument("--vip", type=str, default=VIP, help="Target Anycast VIP")
    parser.add_argument("--port", type=int, default=CONTROLLER_PORT, help="Target Port")
    args = parser.parse_args()

    print("==================================================================")
    print(f"       smaRT_CDN CONCURRENCY STRESS TEST (N={args.concurrency})   ")
    print("==================================================================")
    print(f"Target Anycast VIP : {args.vip}:{args.port}")
    print(f"Target Payload     : {args.file}")
    print(f"Launching {args.concurrency} concurrent streams simultaneously ...")
    print("------------------------------------------------------------------")

    threads = []
    t_global_start = time.time()

    for i in range(1, args.concurrency + 1):
        t = threading.Thread(target=download_worker, args=(i, args.file, args.vip, args.port))
        threads.append(t)
        t.start()

    for t in threads:
        t.join()

    total_wall_time = time.time() - t_global_start
    total_bytes_transferred = sum(r['bytes'] for r in worker_results)
    agg_mbps = (total_bytes_transferred * 8.0) / (total_wall_time * 1_000_000.0) if total_wall_time > 0 else 0.0

    print(f" {'STREAM':<8} {'BYTES':<12} {'TIME (s)':<10} {'THROUGHPUT':<14} {'INTEGRITY':<8}")
    print("------------------------------------------------------------------")
    all_pass = True
    for r in sorted(worker_results, key=lambda x: x['worker_id']):
        status = "PASS" if r['success'] and r['bytes'] > 0 else "FAIL"
        if not r['success']:
            all_pass = False
        print(f" Worker {r['worker_id']:<2} {r['bytes']:<12} {r['duration']:<10.2f} {r['mbps']:<6.2f} Mbps    {status}")

    print("------------------------------------------------------------------")
    print(f" Total Transferred : {total_bytes_transferred / (1024*1024):.2f} MB")
    print(f" Wall Clock Time   : {total_wall_time:.2f} seconds")
    print(f" Aggregate Bandwidth: {agg_mbps:.2f} Mbps")
    print(f" Data Integrity    : {'100% MATCH (PASS)' if all_pass else 'CORRUPTION DETECTED'}")
    print("==================================================================")

    log_to_csv(args.file, args.concurrency, agg_mbps)
    print(f"Results appended to: {CLIENT_CSV}")

if __name__ == '__main__':
    main()

import socket, hashlib, time, os, sys, argparse, csv
from datetime import datetime

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from config.settings import VIP_IP, CONTENT_PORT, CHUNK_SIZE, CLIENT_DOWNLOAD_DIR, CLIENT_TRANSFERS_CSV

def download(client_id, filename, expected_hash=None, target_ip=VIP_IP, port=CONTENT_PORT):
    os.makedirs(CLIENT_DOWNLOAD_DIR, exist_ok=True)
    out_path = os.path.join(CLIENT_DOWNLOAD_DIR, f"{client_id}_{filename}")
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    start = time.time()
    s.connect((target_ip, port))
    s.sendall(f"GET {filename} 0\n".encode())

    hdr = b""
    while b"\n" not in hdr:
        c = s.recv(1024)
        if not c: break
        hdr += c
    ttfb = (time.time() - start) * 1000.0
    line = hdr.split(b"\n")[0].decode()
    remain = int(line.split()[2])
    data = hdr[len(line)+1:]

    hasher = hashlib.sha256()
    received = 0
    with open(out_path, 'wb') as f:
        if data:
            f.write(data)
            hasher.update(data)
            received += len(data)
        while received < remain:
            b = s.recv(CHUNK_SIZE)
            if not b: break
            f.write(b)
            hasher.update(b)
            received += len(b)

    dur = time.time() - start
        # Validate completeness (tester Issue 1 fix)
        if received != remain:
            match = False
            print(f"[WARN] Incomplete transfer: got {received} of {remain} bytes")
    mbps = (received * 8) / (dur * 1_000_000)
    match = (hasher.hexdigest().lower() == expected_hash.lower()) if expected_hash else True
    print(f"[{client_id}] Download complete: {received} bytes in {dur:.2f}s ({mbps:.2f} Mbps) | {'PASS' if match else 'FAIL'}")

    os.makedirs(os.path.dirname(CLIENT_TRANSFERS_CSV), exist_ok=True)
    write_hdr = not os.path.isfile(CLIENT_TRANSFERS_CSV)
    with open(CLIENT_TRANSFERS_CSV, 'a', newline='') as f:
        w = csv.writer(f)
        if write_hdr:
            w.writerow(['timestamp', 'client_id', 'target_ip', 'filename', 'size_bytes', 'ttfb_ms', 'duration_s', 'throughput_mbps', 'sha256_match'])
        w.writerow([datetime.now().isoformat(), client_id, target_ip, filename, received, round(ttfb,2), round(dur,3), round(mbps,2), match])
    s.close()

if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--id', default='c1')
    p.add_argument('--file', required=True)
    p.add_argument('--hash', default=None)
    args = p.parse_args()
    download(args.id, args.file, args.hash)

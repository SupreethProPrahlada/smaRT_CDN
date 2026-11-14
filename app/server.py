#!/usr/bin/env python3
"""Content streaming server with diagnostic PING and UDP heartbeats (FR-4, FR-7)."""
import socket, threading, os, sys, argparse, time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from config.settings import CONTENT_PORT, CHUNK_SIZE, CONTENT_DIR, HB_LISTEN_IP, HB_PORT, HEARTBEAT_INTERVAL

class ContentServer:
    def __init__(self, server_id, bind_ip, port=CONTENT_PORT):
        self.server_id = server_id
        self.bind_ip = bind_ip
        self.port = port
        self.active_connections = 0
        self.lock = threading.Lock()
        self.running = True
        os.makedirs(CONTENT_DIR, exist_ok=True)

    def heartbeat_loop(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        while self.running:
            try:
                with self.lock: c = self.active_connections
                sock.sendto(f"STATUS {self.server_id} {c} {time.time():.3f}\n".encode(), (HB_LISTEN_IP, HB_PORT))
            except Exception: pass
            time.sleep(HEARTBEAT_INTERVAL)
        sock.close()

    def handle_client(self, sock, addr):
        with self.lock: self.active_connections += 1
        try:
            req = b""
            while b"\n" not in req:
                c = sock.recv(1024)
                if not c: break
                req += c
            parts = req.decode(errors='ignore').strip().split()
            if not parts: return

            # Reference feature: PING diagnostic
            if len(parts) == 1 and parts[0] == "PING":
                with self.lock: c = self.active_connections
                sock.sendall(f"PONG {self.server_id} {c}\n".encode())
                return

            if len(parts) >= 3 and parts[0] == "GET":
                filename, offset = os.path.basename(parts[1]), int(parts[2])
                path = os.path.join(CONTENT_DIR, filename)
                if os.path.isfile(path):
                    total = os.path.getsize(path)
                    remain = total - offset
                    sock.sendall(f"OK {total} {remain}\n".encode())
                    with open(path, 'rb') as f:
                        f.seek(offset)
                        while True:
                            b = f.read(CHUNK_SIZE)
                            if not b: break
                            sock.sendall(b)
        finally:
            with self.lock: self.active_connections = max(0, self.active_connections - 1)
            sock.close()

    def start(self):
        threading.Thread(target=self.heartbeat_loop, daemon=True).start()
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind((self.bind_ip, self.port))
        s.listen(50)
        while self.running:
            conn, addr = s.accept()
            threading.Thread(target=self.handle_client, args=(conn, addr), daemon=True).start()

if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--id', required=True)
    p.add_argument('--ip', required=True)
    p.add_argument('--port', type=int, default=CONTENT_PORT)
    args = p.parse_args()
    ContentServer(args.id, args.ip, args.port).start()

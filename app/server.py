"""
Smart CDN - Content Streaming Server with Heartbeat Reporting
Streams files in 64 KB binary chunks and emits health heartbeats (FR-4, FR-7).
Owned by Developer 1 (Supreeth Prahalada) - Sprint 2.
"""

import socket
import threading
import os
import sys
import argparse
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from config.settings import (
    CONTENT_PORT, CHUNK_SIZE, CONTENT_DIR, HB_LISTEN_IP, HB_PORT, HEARTBEAT_INTERVAL
)


class ContentServer:
    def __init__(self, server_id: str, bind_ip: str, port: int = CONTENT_PORT):
        self.server_id = server_id
        self.bind_ip = bind_ip
        self.port = port
        self.active_connections = 0
        self.lock = threading.Lock()
        self.running = True

        os.makedirs(CONTENT_DIR, exist_ok=True)

    def heartbeat_loop(self):
        """Emits STATUS heartbeat to controller every 2.0s via UDP (FR-4)."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        print(f"[{self.server_id}] Heartbeat thread started -> target {HB_LISTEN_IP}:{HB_PORT} every {HEARTBEAT_INTERVAL}s")

        while self.running:
            try:
                with self.lock:
                    conns = self.active_connections
                timestamp = time.time()
                # Wire format from SRS Appendix A: STATUS <id> <conns> <timestamp>\n
                msg = f"STATUS {self.server_id} {conns} {timestamp:.3f}\n"
                sock.sendto(msg.encode('utf-8'), (HB_LISTEN_IP, HB_PORT))
            except Exception as e:
                # Controller might be booting up, keep trying
                pass
            time.sleep(HEARTBEAT_INTERVAL)

        sock.close()

    def handle_client(self, client_sock: socket.socket, client_addr):
        with self.lock:
            self.active_connections += 1

        print(f"[{self.server_id}] Connection started from {client_addr} (Active: {self.active_connections})")

        try:
            req_data = b""
            while b"\n" not in req_data:
                chunk = client_sock.recv(1024)
                if not chunk:
                    break
                req_data += chunk

            if not req_data:
                return

            request_line = req_data.decode('utf-8', errors='ignore').strip()
            parts = request_line.split()

            if len(parts) < 3 or parts[0] != "GET":
                client_sock.sendall(b"ERR BAD_REQUEST\n")
                return

            filename = os.path.basename(parts[1])
            offset = int(parts[2])
            filepath = os.path.join(CONTENT_DIR, filename)

            if not os.path.isfile(filepath):
                client_sock.sendall(b"ERR NOT_FOUND\n")
                print(f"[{self.server_id}] File not found: {filepath}")
                return

            total_size = os.path.getsize(filepath)
            if offset > total_size or offset < 0:
                client_sock.sendall(b"ERR INVALID_OFFSET\n")
                return

            remaining_bytes = total_size - offset
            header = f"OK {total_size} {remaining_bytes}\n"
            client_sock.sendall(header.encode('utf-8'))

            with open(filepath, 'rb') as f:
                f.seek(offset)
                bytes_sent = 0
                while bytes_sent < remaining_bytes:
                    chunk = f.read(CHUNK_SIZE)
                    if not chunk:
                        break
                    client_sock.sendall(chunk)
                    bytes_sent += len(chunk)

            print(f"[{self.server_id}] Streamed {bytes_sent} bytes of {filename} to {client_addr}")

        except Exception as e:
            print(f"[{self.server_id}] Stream error: {e}")
        finally:
            with self.lock:
                self.active_connections = max(0, self.active_connections - 1)
            try:
                client_sock.close()
            except Exception:
                pass
            print(f"[{self.server_id}] Connection closed for {client_addr} (Active: {self.active_connections})")

    def start(self):
        # Start heartbeat sender daemon thread
        hb_thread = threading.Thread(target=self.heartbeat_loop, daemon=True)
        hb_thread.start()

        server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server_sock.bind((self.bind_ip, self.port))
        server_sock.listen(50)

        print(f"[{self.server_id}] Content server listening on {self.bind_ip}:{self.port}")

        try:
            while self.running:
                client_sock, client_addr = server_sock.accept()
                t = threading.Thread(target=self.handle_client, args=(client_sock, client_addr), daemon=True)
                t.start()
        except KeyboardInterrupt:
            print(f"\n[{self.server_id}] Shutting down server...")
            self.running = False
        finally:
            server_sock.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Smart CDN Content Server")
    parser.add_argument('--id', required=True, help="Server ID (e.g. srv1)")
    parser.add_argument('--ip', required=True, help="Bind IP address (e.g. 10.0.0.11)")
    parser.add_argument('--port', type=int, default=CONTENT_PORT, help="Port (default: 8000)")
    args = parser.parse_args()

    server = ContentServer(server_id=args.id, bind_ip=args.ip, port=args.port)
    server.start()

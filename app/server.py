"""
Smart CDN - Content Streaming Server
Streams files in 64 KB binary chunks with byte-offset support.
Owned by Developer 1 (Supreeth Prahalada) - Sprint 1.
"""

import socket
import threading
import os
import sys
import argparse
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from config.settings import CONTENT_PORT, CHUNK_SIZE, CONTENT_DIR


class ContentServer:
    def __init__(self, server_id: str, bind_ip: str, port: int = CONTENT_PORT):
        self.server_id = server_id
        self.bind_ip = bind_ip
        self.port = port
        self.active_connections = 0
        self.lock = threading.Lock()
        self.running = True

        # Ensure content directory exists
        os.makedirs(CONTENT_DIR, exist_ok=True)

    def handle_client(self, client_sock: socket.socket, client_addr):
        with self.lock:
            self.active_connections += 1

        print(f"[{self.server_id}] New connection from {client_addr} (Active: {self.active_connections})")

        try:
            # Read request line until newline
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

            # Send protocol header line
            header = f"OK {total_size} {remaining_bytes}\n"
            client_sock.sendall(header.encode('utf-8'))

            # Stream binary data in 64 KB pieces
            with open(filepath, 'rb') as f:
                f.seek(offset)
                bytes_sent = 0
                while bytes_sent < remaining_bytes:
                    chunk = f.read(CHUNK_SIZE)
                    if not chunk:
                        break
                    client_sock.sendall(chunk)
                    bytes_sent += len(chunk)

            print(f"[{self.server_id}] Completed stream of {filename} ({bytes_sent} bytes sent to {client_addr})")

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
        server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server_sock.bind((self.bind_ip, self.port))
        server_sock.listen(50)

        print(f"[{self.server_id}] Content server listening on {self.bind_ip}:{self.port}")
        print(f"[{self.server_id}] Content directory: {CONTENT_DIR}")

        try:
            while self.running:
                client_sock, client_addr = server_sock.accept()
                t = threading.Thread(target=self.handle_client, args=(client_sock, client_addr), daemon=True)
                t.start()
        except KeyboardInterrupt:
            print(f"\n[{self.server_id}] Shutting down server...")
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

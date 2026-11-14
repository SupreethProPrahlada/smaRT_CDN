import socket
import threading
import os
import sys
import argparse
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from config.settings import (
    CONTENT_PORT,
    CHUNK_SIZE,
    CONTENT_DIR,
    HB_LISTEN_IP,
    HB_PORT,
    HEARTBEAT_INTERVAL,
)


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
                with self.lock:
                    connections = self.active_connections

                message = (
                    f"STATUS {self.server_id} {connections} "
                    f"{time.time():.3f}\n"
                )
                sock.sendto(message.encode(), (HB_LISTEN_IP, HB_PORT))
            except OSError:
                pass

            time.sleep(HEARTBEAT_INTERVAL)

        sock.close()

    def handle_client(self, sock, addr):
        with self.lock:
            self.active_connections += 1

        try:
            req = b""

            while b"\n" not in req:
                chunk = sock.recv(1024)
                if not chunk:
                    return
                req += chunk

            parts = req.decode(errors="ignore").strip().split()

            if len(parts) < 3 or parts[0] != "GET":
                sock.sendall(b"ERR Bad_Request\n")
                return

            filename = os.path.basename(parts[1])

            try:
                offset = int(parts[2])
            except ValueError:
                sock.sendall(b"ERR Bad_Offset\n")
                return

            if offset < 0:
                sock.sendall(b"ERR Bad_Offset\n")
                return

            path = os.path.join(CONTENT_DIR, filename)

            if not os.path.isfile(path):
                sock.sendall(f"ERR File_Not_Found {filename}\n".encode())
                return

            total = os.path.getsize(path)

            if offset > total:
                sock.sendall(b"ERR Bad_Offset\n")
                return

            remain = total - offset
            sock.sendall(f"OK {total} {remain}\n".encode())

            with open(path, "rb") as content_file:
                content_file.seek(offset)

                while True:
                    chunk = content_file.read(CHUNK_SIZE)
                    if not chunk:
                        break
                    sock.sendall(chunk)

        except (ConnectionError, OSError):
            pass
        finally:
            with self.lock:
                self.active_connections = max(0, self.active_connections - 1)
            sock.close()

    def start(self):
        threading.Thread(target=self.heartbeat_loop, daemon=True).start()

        server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_socket.setsockopt(
            socket.SOL_SOCKET, socket.SO_REUSEADDR, 1
        )
        server_socket.bind((self.bind_ip, self.port))
        server_socket.listen(50)

        print(
            f"{self.server_id} listening on "
            f"{self.bind_ip}:{self.port}"
        )

        while self.running:
            conn, addr = server_socket.accept()
            threading.Thread(
                target=self.handle_client,
                args=(conn, addr),
                daemon=True,
            ).start()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--id", required=True)
    parser.add_argument("--ip", required=True)
    parser.add_argument("--port", type=int, default=CONTENT_PORT)
    args = parser.parse_args()

    ContentServer(args.id, args.ip, args.port).start()

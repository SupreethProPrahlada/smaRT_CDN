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
    SERVERS,
)


def _detect_bind_ip():
    """Return the local address this host would use to reach the heartbeat listener."""
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.connect((HB_LISTEN_IP, HB_PORT))
        return probe.getsockname()[0]
    finally:
        probe.close()


def _resolve_identity(server_id, bind_ip, parser):
    """Resolve --id/--ip to a canonical (srvN, address) pair.

    Accepts srv1/srv2/srv3 or the matching server IP, and auto-detects both when
    omitted, so ``python3 app/server.py`` is enough inside a Mininet host.
    """
    if bind_ip is None:
        try:
            bind_ip = _detect_bind_ip()
        except OSError as exc:
            parser.error(f"could not detect the local server IP ({exc}); pass --ip")

    if server_id not in SERVERS:
        by_ip = next(
            (sid for sid, info in SERVERS.items() if info["ip"] == (server_id or bind_ip)),
            None,
        )
        if by_ip is None:
            choices = ", ".join(sorted(SERVERS))
            parser.error(
                f"--id must be one of {choices} or the matching server IP "
                f"(got {server_id!r})"
            )
        server_id = by_ip

    expected_ip = SERVERS[server_id]["ip"]
    if bind_ip != expected_ip:
        parser.error(f"--ip for {server_id} must be {expected_ip} (got {bind_ip})")
    return server_id, bind_ip


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
        failing = False

        while self.running:
            try:
                with self.lock:
                    connections = self.active_connections

                message = (
                    f"STATUS {self.server_id} {connections} "
                    f"{time.time():.3f}\n"
                )
                sock.sendto(message.encode(), (HB_LISTEN_IP, HB_PORT))
                if failing:
                    print(f"{self.server_id} heartbeat sending again", flush=True)
                failing = False
            except OSError as exc:
                if not failing:
                    print(f"{self.server_id} heartbeat send failed: {exc}", flush=True)
                failing = True

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

            # Sprint 3 traversal defence: only a plain file name inside CONTENT_DIR is served.
            filename = os.path.basename(parts[1])
            content_root = os.path.realpath(CONTENT_DIR)
            if (
                filename in ("", ".", "..")
                or os.path.dirname(os.path.realpath(os.path.join(content_root, filename))) != content_root
            ):
                sock.sendall(b"ERR Bad_Request\n")
                return

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
        pid_path = f"/tmp/smartcdn_{self.server_id}.pid"
        with open(pid_path, "w") as pid_file:
            pid_file.write(f"{os.getpid()}\n")

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

        try:
            while self.running:
                conn, addr = server_socket.accept()
                threading.Thread(
                    target=self.handle_client,
                    args=(conn, addr),
                    daemon=True,
                ).start()
        finally:
            server_socket.close()
            try:
                os.unlink(pid_path)
            except OSError:
                pass


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description=(
            "Smart CDN content server. Run it inside its Mininet host; the "
            "server identity and bind address are detected automatically."
        )
    )
    parser.add_argument(
        "--id", help="server ID (srv1/srv2/srv3 or its IP); auto-detected if omitted"
    )
    parser.add_argument("--ip", help="bind address; auto-detected if omitted")
    parser.add_argument("--port", type=int, default=CONTENT_PORT)
    args = parser.parse_args()

    server_id, bind_ip = _resolve_identity(args.id, args.ip, parser)
    ContentServer(server_id, bind_ip, args.port).start()

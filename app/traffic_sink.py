#!/usr/bin/env python3
"""Receive UDP packets from the Sprint 4 load generator."""

import argparse
import socket


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bind", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=9001)
    args = parser.parse_args()
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((args.bind, args.port))
    try:
        while True:
            sock.recvfrom(65535)
    except KeyboardInterrupt:
        pass
    finally:
        sock.close()


if __name__ == "__main__":
    main()

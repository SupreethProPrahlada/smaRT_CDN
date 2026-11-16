#!/usr/bin/env python3
"""Generate reproducible UDP cross-traffic from Mininet's loadsrc host."""

import argparse
import json
import random
import socket
import time

RATE_LEVELS_MBPS = (10, 25, 50, 75, 100)
MIN_RATE_MBPS = 10
MAX_RATE_MBPS = 100
RATE_STEP_MBPS = 10
PACKET_BYTES = 1400


def adaptive_rate(current_mbps, utilization):
    if utilization < 0.5:
        return min(MAX_RATE_MBPS, current_mbps + RATE_STEP_MBPS)
    if utilization >= 0.8:
        return max(MIN_RATE_MBPS, current_mbps - RATE_STEP_MBPS)
    return current_mbps


def random_rate(rng):
    return rng.choice(RATE_LEVELS_MBPS)


def read_srv1_utilization(path):
    try:
        with open(path, "r", encoding="utf-8") as stream:
            data = json.load(stream)
        return float(data["servers"]["srv1"]["utilization"])
    except (OSError, ValueError, KeyError, TypeError):
        return 0.0


def run(mode, target, port, duration, seed, telemetry_path):
    rng = random.Random(seed)
    rate = MIN_RATE_MBPS
    history = []
    packet = b"x" * PACKET_BYTES
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        end = time.monotonic() + duration
        while time.monotonic() < end:
            interval_start = time.monotonic()
            utilization = read_srv1_utilization(telemetry_path)
            rate = adaptive_rate(rate, utilization) if mode == "adaptive" else random_rate(rng)
            history.append(rate)
            packets = max(1, int(rate * 1_000_000 / 8 / PACKET_BYTES))
            delay = 1.0 / packets
            for _ in range(packets):
                sock.sendto(packet, (target, port))
                time.sleep(delay)
            remaining = 1.0 - (time.monotonic() - interval_start)
            if remaining > 0:
                time.sleep(min(remaining, max(0.0, end - time.monotonic())))
    finally:
        sock.close()
    return history


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("adaptive", "random"), required=True)
    parser.add_argument("--target", default="10.0.0.11")
    parser.add_argument("--port", type=int, default=9001)
    parser.add_argument("--duration", type=int, default=30)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--telemetry", default="results/live_routes.json")
    args = parser.parse_args()
    if args.duration <= 0:
        parser.error("--duration must be positive")
    history = run(args.mode, args.target, args.port, args.duration, args.seed, args.telemetry)
    print(json.dumps({"mode": args.mode, "seed": args.seed, "rates_mbps": history}))


if __name__ == "__main__":
    main()

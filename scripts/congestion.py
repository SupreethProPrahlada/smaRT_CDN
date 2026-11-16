"""FR-12 congestion generator (Sprint 4).

Two modes are available:

* ``iperf`` (default): run on the ``loadsrc`` host behind s2 and send
  constant-rate UDP to a client sink, so the traffic crosses srv1's primary
  trunk (s1-s2) without touching srv1's own link. The controller sees this
  "other traffic" on the primary path and moves srv1 flows to the detour s5.

    mininet> c6 iperf -s -u &
    mininet> loadsrc python3 scripts/congestion.py --target 10.0.0.6 --mbps 90 --seconds 30

* ``adaptive`` / ``random``: send UDP packets directly and vary the rate from
  the controller's exported srv1 utilisation (``results/live_routes.json``).
  ``random`` is reproducible for a fixed ``--seed``.

    mininet> loadsrc python3 scripts/congestion.py --mode random --seed 42 \
        --target 10.0.0.6 --port 9001 --duration 30
"""

import argparse
import json
import random
import shutil
import socket
import subprocess
import sys
import time

RATE_LEVELS_MBPS = (10, 25, 50, 75, 100)
MIN_RATE_MBPS = 10
MAX_RATE_MBPS = 100
RATE_STEP_MBPS = 10
PACKET_BYTES = 1400


def build_command(target, mbps, seconds):
    return ["iperf", "-c", target, "-u", "-b", f"{mbps}M", "-t", str(seconds), "-i", "5"]


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


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--target", default="10.0.0.6", help="client sink (default c6)")
    parser.add_argument("--mbps", type=float, default=90.0, help="iperf offered load in Mbit/s (default 90)")
    parser.add_argument("--seconds", type=int, default=30, help="iperf duration in seconds (default 30)")
    parser.add_argument("--mode", choices=("adaptive", "random"), help="use the UDP generator instead of iperf")
    parser.add_argument("--port", type=int, default=9001, help="UDP sink port for --mode (default 9001)")
    parser.add_argument("--duration", type=int, default=30, help="UDP generator duration for --mode (default 30)")
    parser.add_argument("--seed", type=int, default=1, help="random seed for --mode random")
    parser.add_argument("--telemetry", default="results/live_routes.json", help="controller export used by --mode adaptive")
    args = parser.parse_args(argv)

    if args.mode:
        if args.duration <= 0:
            parser.error("--duration must be positive")
        history = run(args.mode, args.target, args.port, args.duration, args.seed, args.telemetry)
        print(json.dumps({"mode": args.mode, "seed": args.seed, "rates_mbps": history}))
        return 0

    if args.mbps <= 0 or args.seconds <= 0:
        parser.error("--mbps and --seconds must be positive")
    if shutil.which("iperf") is None:
        print("iperf is not installed (sudo apt install iperf)", file=sys.stderr)
        return 1

    command = build_command(args.target, args.mbps, args.seconds)
    print(f"[congestion] {args.mbps:g} Mbit/s UDP to {args.target} for {args.seconds}s: {' '.join(command)}", flush=True)
    return subprocess.call(command)


if __name__ == "__main__":
    sys.exit(main())

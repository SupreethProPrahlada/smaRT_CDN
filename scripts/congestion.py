"""FR-12 congestion generator (Sprint 4, Developer 2).

Run on the `bg` host behind s2. It sends constant-rate UDP to a client sink,
so the traffic crosses srv1's primary trunk (s1-s2) without touching srv1's
own link. The controller sees this "other traffic" on the primary path and
moves srv1 flows to the detour through s5.

Inside the Mininet CLI:
    mininet> c6 iperf -s -u &
    mininet> bg python3 scripts/congestion.py --target 10.0.0.6 --mbps 90 --seconds 30
"""

import argparse
import shutil
import subprocess
import sys


def build_command(target, mbps, seconds):
    return ["iperf", "-c", target, "-u", "-b", f"{mbps}M", "-t", str(seconds), "-i", "5"]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--target", default="10.0.0.6", help="client running `iperf -s -u` (default c6)")
    parser.add_argument("--mbps", type=float, default=90.0, help="offered load in Mbit/s (default 90)")
    parser.add_argument("--seconds", type=int, default=30, help="duration in seconds (default 30)")
    args = parser.parse_args(argv)

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

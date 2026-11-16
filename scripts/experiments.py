#!/usr/bin/env python3
"""Run a supplied JSON-reporting scenario in dynamic and static modes."""

import argparse
import csv
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

FIELDS = (
    "run_id", "mode", "seed", "throughput_mbps", "ttfb_ms",
    "completed", "total", "completion_rate", "timestamp",
)


def append_result(path, run_id, mode, seed, metrics):
    if mode not in ("dynamic", "static"):
        raise ValueError("mode must be dynamic or static")
    completed, total = int(metrics["completed"]), int(metrics["total"])
    if completed < 0 or total < 0 or completed > total:
        raise ValueError("completed/total counts are invalid")
    row = {
        "run_id": run_id,
        "mode": mode,
        "seed": seed,
        "throughput_mbps": float(metrics["throughput_mbps"]),
        "ttfb_ms": float(metrics["ttfb_ms"]),
        "completed": completed,
        "total": total,
        "completion_rate": "{:.6f}".format(completed / total if total else 0.0),
        "timestamp": datetime.now().isoformat(),
    }
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    write_header = not path.exists() or path.stat().st_size == 0
    with path.open("a", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=FIELDS)
        if write_header:
            writer.writeheader()
        writer.writerow(row)
    return row


def execute_comparison(command, output_path, runs=1, seed=1):
    if not command:
        raise ValueError("a scenario command is required")
    results = []
    for run_number in range(1, runs + 1):
        run_id = "{}-{}".format(seed, run_number)
        for mode in ("dynamic", "static"):
            env = os.environ.copy()
            env.update({"CDN_MODE": mode, "CDN_SEED": str(seed), "CDN_RUN_ID": run_id})
            completed = subprocess.run(command, env=env, check=True, capture_output=True, text=True)
            output_lines = [line for line in completed.stdout.splitlines() if line.strip()]
            if not output_lines:
                raise RuntimeError("scenario produced no JSON metrics")
            metrics = json.loads(output_lines[-1])
            results.append(append_result(output_path, run_id, mode, seed, metrics))
    return results


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", default="results/data/experiments.csv")
    parser.add_argument("--runs", type=int, default=1)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if args.runs < 1:
        parser.error("--runs must be at least 1")
    if not command:
        parser.error("provide a scenario command after --")
    result = execute_comparison(command, args.results, args.runs, args.seed)
    print(json.dumps({"rows_appended": len(result), "results": args.results}))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Create deterministic binary content plus a SHA-256 manifest."""

import argparse
import hashlib
import json
import random
from pathlib import Path


def generate_content(directory, size_bytes, seed=1, filename="payload.bin"):
    if size_bytes < 0:
        raise ValueError("size_bytes must be non-negative")
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / filename
    rng = random.Random(seed)
    digest = hashlib.sha256()
    remaining = size_bytes
    with path.open("wb") as output:
        while remaining:
            block_size = min(65536, remaining)
            block = bytes(rng.getrandbits(8) for _ in range(block_size))
            output.write(block)
            digest.update(block)
            remaining -= block_size
    manifest = {
        "filename": filename,
        "size_bytes": size_bytes,
        "seed": seed,
        "sha256": digest.hexdigest(),
    }
    (directory / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dir", default="/tmp/cdn_content")
    parser.add_argument("--size-mb", type=int, default=10)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--filename", default="payload.bin")
    args = parser.parse_args()
    if args.size_mb < 0:
        parser.error("--size-mb must be non-negative")
    result = generate_content(args.dir, args.size_mb * 1024 * 1024, args.seed, args.filename)
    print(json.dumps(result))


if __name__ == "__main__":
    main()

"""
Smart CDN - Content Generator
Creates random binary payload files and outputs reference SHA-256 checksums.
Owned by Developer 1 / Tester - Sprint 1.
"""

import os
import hashlib
import argparse
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from config.settings import CONTENT_DIR


def generate_file(filename: str, size_mb: int):
    os.makedirs(CONTENT_DIR, exist_ok=True)
    filepath = os.path.join(CONTENT_DIR, filename)

    print(f"Generating {size_mb} MB test file at {filepath}...")
    hasher = hashlib.sha256()

    # Generate repeatable pseudo-random data in 1 MB blocks
    with open(filepath, 'wb') as f:
        for i in range(size_mb):
            chunk = os.urandom(1024 * 1024)
            f.write(chunk)
            hasher.update(chunk)

    expected_hash = hasher.hexdigest()
    print(f"[OK] Created: {filepath} ({os.path.getsize(filepath)} bytes)")
    print(f"[OK] SHA-256: {expected_hash}")
    return expected_hash


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Generate Smart CDN test files")
    parser.add_argument('--name', default='test_10M.bin', help="File name")
    parser.add_argument('--size', type=int, default=10, help="File size in MB")
    args = parser.parse_args()

    generate_file(args.name, args.size)

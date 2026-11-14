#!/usr/bin/env python3
"""Generate random test files with reference SHA-256 checksums."""
import os, hashlib, argparse, sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from config.settings import CONTENT_DIR

def generate_file(filename, size_mb):
    os.makedirs(CONTENT_DIR, exist_ok=True)
    filepath = os.path.join(CONTENT_DIR, filename)
    hasher = hashlib.sha256()
    with open(filepath, 'wb') as f:
        for _ in range(size_mb):
            chunk = os.urandom(1024 * 1024)
            f.write(chunk)
            hasher.update(chunk)
    digest = hasher.hexdigest()
    print(f"[OK] Generated {filepath} ({size_mb} MB) | SHA-256: {digest}")
    return digest

if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--name', default='test_10M.bin')
    p.add_argument('--size', type=int, default=10)
    args = p.parse_args()
    generate_file(args.name, args.size)

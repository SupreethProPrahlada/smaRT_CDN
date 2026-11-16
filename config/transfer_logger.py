"""Shared, process-safe transfer logging for the smaRT_CDN clients."""

import csv
import fcntl
import os

from config.settings import CLIENT_TRANSFERS_CSV

FIELDNAMES = [
    "timestamp",
    "client_id",
    "target_ip",
    "filename",
    "size_bytes",
    "ttfb_ms",
    "duration_s",
    "throughput_mbps",
    "sha256_match",
    "status",
]


def append_transfer(row):
    """Append one normalized CSV row while holding an OS-level file lock."""
    path = CLIENT_TRANSFERS_CSV
    directory = os.path.dirname(path)
    os.makedirs(directory, exist_ok=True)

    lock_path = path + ".lock"
    with open(lock_path, "a", encoding="utf-8") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        try:
            # Remove NUL bytes left by older/interrupted writers before parsing.
            if os.path.exists(path):
                with open(path, "rb") as source:
                    content = source.read()
                cleaned = content.replace(b"\x00", b"")
                if cleaned != content:
                    temp_path = path + ".repair"
                    with open(temp_path, "wb") as repaired:
                        repaired.write(cleaned)
                        repaired.flush()
                        os.fsync(repaired.fileno())
                    os.replace(temp_path, path)

            existing_rows = []
            if os.path.exists(path) and os.path.getsize(path) > 0:
                with open(path, "r", newline="", encoding="utf-8") as source:
                    reader = csv.DictReader(source)
                    if reader.fieldnames:
                        existing_rows = [
                            row for row in reader
                            if row and any(value not in (None, "") for value in row.values())
                        ]

            normalized = []
            for old in existing_rows:
                normalized.append({
                    "timestamp": old.get("timestamp", ""),
                    "client_id": old.get("client_id", ""),
                    "target_ip": old.get("target_ip", old.get("vip", "")),
                    "filename": old.get("filename", ""),
                    "size_bytes": old.get("size_bytes", old.get("bytes_received", old.get("bytes", "0"))),
                    "ttfb_ms": old.get("ttfb_ms", ""),
                    "duration_s": old.get("duration_s", old.get("duration_sec", old.get("duration", ""))),
                    "throughput_mbps": old.get("throughput_mbps", old.get("mbps", "")),
                    "sha256_match": old.get("sha256_match", ""),
                    "status": old.get("status", ""),
                })

            normalized.append({field: row.get(field, "") for field in FIELDNAMES})

            temp_path = path + ".tmp"
            with open(temp_path, "w", newline="", encoding="utf-8") as destination:
                writer = csv.DictWriter(destination, fieldnames=FIELDNAMES)
                writer.writeheader()
                writer.writerows(normalized)
                destination.flush()
                os.fsync(destination.fileno())
            os.replace(temp_path, path)
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)

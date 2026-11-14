import csv

import scripts.dashboard as dashboard_module


def test_tc35_dashboard_reads_recent_transfer_rows(monkeypatch, tmp_path):
    """TC35 FR-8: dashboard helper reads the most recent three CSV transfer records."""
    csv_path = tmp_path / "transfers.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=["client_id", "throughput_mbps"])
        writer.writeheader()
        for index in range(5):
            writer.writerow({"client_id": f"c{index + 1}", "throughput_mbps": index + 1})
    monkeypatch.setattr(dashboard_module, "CSV_FILE", str(csv_path))

    recent = dashboard_module.get_recent_transfers()

    assert [row["client_id"] for row in recent] == ["c3", "c4", "c5"]


def test_tc38_dashboard_safe_float_handles_bad_input():
    """TC38 Sprint 2 dashboard helper uses fallback on malformed numeric metrics."""
    assert dashboard_module.safe_float("bad", default=7.5) == 7.5
    assert dashboard_module.safe_float("12.25") == 12.25

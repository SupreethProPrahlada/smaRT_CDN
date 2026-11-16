import csv
import sys

from scripts.experiments import append_result, execute_comparison


def test_s4_experiment_results_append_dynamic_and_static_rows_once(tmp_path):
    path = tmp_path / "experiments.csv"
    metrics = {"throughput_mbps": 42.5, "ttfb_ms": 12.0, "completed": 5, "total": 6}

    append_result(path, "r1", "dynamic", 1, metrics)
    append_result(path, "r1", "static", 1, metrics)

    with path.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    assert [row["mode"] for row in rows] == ["dynamic", "static"]
    assert [row["completion_rate"] for row in rows] == ["0.833333"] * 2
    assert path.read_text(encoding="utf-8").count("run_id,mode") == 1


def test_s4_comparison_runs_scenario_in_both_explicit_modes(tmp_path):
    command = [
        sys.executable,
        "-c",
        "import json; print(json.dumps({'throughput_mbps': 10, 'ttfb_ms': 2, 'completed': 1, 'total': 1}))",
    ]
    rows = execute_comparison(command, tmp_path / "experiments.csv", runs=1, seed=5)

    assert [row["mode"] for row in rows] == ["dynamic", "static"]
    assert [row["run_id"] for row in rows] == ["5-1", "5-1"]

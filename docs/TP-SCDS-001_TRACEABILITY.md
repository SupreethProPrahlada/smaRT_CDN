# TP-SCDS-001 — Official Test Case Traceability

Companion to `Smart_CDN_IEEE829_Test_Plan.docx` (TP-SCDS-001, Version 1.1) and
`Smart_CDN_SRS_Agile_Plan.docx` (SRS Version 0.1).

The repository's pytest docstrings use the IDs from `docs/test_plan.md`
(`TC01`–`TC41`). Those are **not** the official TP-SCDS-001 IDs. This table is
the authoritative mapping from the official 24 cases to repository evidence so
the two numbering schemes are not confused.

Status vocabulary: **PASS** = executed and matches the expected result;
**PARTIAL** = executed proxy or exploratory evidence, but the live acceptance
step named by the case is missing; **NOT EXECUTED** = no run yet.

| Official TC | Expected result | Repository evidence | Status |
|---|---|---|---|
| TC01 | Binary payloads created in `content/` | `tests/make_content.py` + `scripts/content.py`; `test_s3_content_generator_writes_repeatable_bytes_and_manifest`; every scenario generates deterministic content + manifest | PASS |
| TC02 | c1–c6, loadsrc (c7), srv1–srv3, s1–s5 start | `test_tc34_topology_builds_required_switches_hosts_and_trunks`, `test_s4_topology_adds_detour_and_congestion_source`; topology started in every live scenario | PASS (declaration + live startup) |
| TC03 | Ports 6653 and 9000 reachable | `tests/run_scenarios.start_controller` waits for 6653. **9000 is UDP heartbeat traffic delivered by switch packet-in, not a bound socket**, so the case as written cannot pass. Reword required. | PARTIAL / SRS–implementation mismatch |
| TC04 | Single download, checksum OK | `tests/run_scenarios.py smoke`; `results/data/client-transfers.csv` rows with `sha256_match=True` (62.40 Mbps smoke run) | PASS |
| TC05 | Six simultaneous downloads, checksum OK | New `tests/run_scenarios.py concurrent` drives c1–c6 in parallel and verifies all six digests. Harness added; run with `sudo -E .venv/bin/python tests/run_scenarios.py concurrent`. | NOT EXECUTED (ready) |
| TC06 | All three servers healthy | `test_tc08_heartbeat_datagram_contract`, `test_tc09_valid_heartbeat_updates_known_server_load`; live telemetry shows srv1–srv3 UP | PASS |
| TC07 | New connections go to least-loaded healthy server | `test_tc11_numeric_dynamic_selection`, `test_tc12_single_healthy_server_selected`; controller `[Route Decision]` logs | PASS (unit + live route) |
| TC08 | Fixed server assignment used | `test_tc20_static_client_mapping`, `test_tc21_dynamic_and_static_mode_instances`; `CDN_MODE=static` experiment rows | PASS |
| TC09 | Server DOWN within 10–12 s; new connections to healthy server | `test_tc09_heartbeat_timeout_marks_server_down_and_flushes_rules`; live failover run (32 MiB, srv1 terminated, digest matched). DOWN transition was inferred from recovery, not captured in an event log. | PASS (with evidence caveat) |
| TC10 | Resume from last byte within 12 retries, checksum OK | `test_tc_s3_client_retries_from_last_written_byte`, `test_tc_s3_client_stops_after_twelve_retries`; live failover transfer | PASS |
| TC11 | CDN flow rules visible on switches | `test_tc02_vip_arp_and_bidirectional_nat_rules` checks the exact forward/reverse FlowMods; no `ovs-ofctl dump-flows` capture was archived | PARTIAL |
| TC12 | Live flow moved to s5 with no client reconnect | `test_s4_link_status_event_switches_detour_and_recovers`, `test_s4_detour_keeps_srv1_return_path_bidirectional`; live link-failure run matched SHA-256. Return direction now moves to s5 too (fix in this audit). | PASS (live hash + unit flow evidence) |
| TC13 | Delay 5 → 100 ms moves the flow | `test_s4_detour_decision_obeys_latency_delta_and_link_state` (thresholds) and congestion runs; no live `tc qdisc` delay-increase scenario | PARTIAL |
| TC14 | New connections use the direct route again | `test_s4_link_status_event_switches_detour_and_recovers`; live link-failure scenario restores s1-s2 after 1 s | PASS |
| TC15 | Adaptive congestion: direct → backup → direct | `test_s4_adaptive_congestion_adjusts_rate_with_utilization`; live adaptive congestion run (89.77 Mbps, digest matched). Route event sequence not archived. | PASS (exploratory) |
| TC16 | Random congestion repeatable with seed | `test_s4_random_congestion_is_reproducible_for_fixed_seed`; live `--seed 42` run | PASS |
| TC17 | RTT/utilization/state logged every 5 s | Constant + `test_tc39_controller_status_log_contains_telemetry`; live 5 s cadence not timed | PARTIAL |
| TC18 | Route colours/decision update every second | `tools/route_map.html`; `test_tc18_route_map_refreshes_and_colours_links_by_load`; browser render not exercised | PARTIAL |
| TC19 | Rows appended to `results/data/experiments.csv` | `test_s4_experiment_results_append_dynamic_and_static_rows_once`, `test_s4_comparison_runs_scenario_in_both_explicit_modes`; live file `results/data/experiments-live-20261116.csv` | PASS (exploratory) |
| TC20 | All scenarios run and report generated | Runner supports smoke, failover, link-failure, congestion and concurrent; the first four ran live. No single all-in-one run and the concurrent case is still pending. | PARTIAL |
| TC21 | Single download ≥85 Mbps on clean 100 Mbps link | Live row: 89.72 Mbps; experiments mean 84.27 Mbps. No automated threshold assertion (host-dependent). | PARTIAL (evidence, not regression) |
| TC22 | Flow rules <20 ms; JSON export <50 ms | `test_tc22_flow_rule_installation_within_twenty_ms`; `test_tc17_json_export_contains_current_mode_and_servers` now asserts <50 ms | PASS (in-process proxy; live controller timing not instrumented) |
| TC23 | `../` rejected; only content dir served | `test_tc_s3_server_rejects_directory_traversal`, `test_tc16_missing_file_is_not_reported_as_success`; network-level attack not executed | PASS (unit) |
| TC24 | Bad source/syntax heartbeat ignored | `test_tc10_malformed_and_unknown_heartbeats_are_ignored` (bad syntax, unknown id, wrong source IP, negative count, non-numeric time, extra token); live forged datagram not executed | PASS (integration) |

## Requirements not covered by a numbered case

- **NFR-4 (85 Mbps)** is only covered by TC21, which remains exploratory.
- **NFR-5** is covered by TC22 (in-process only).
- **FR-5 all-down fallback** is documented as a deterministic `srv1` fallback;
  the end-to-end system test remains skipped in
  `tests/system/test_fr7_fr11_scenarios.py`.

## How to run

```
uv sync
uv run pytest -q                       # 67 passed, 2 skipped at this baseline
sudo -E .venv/bin/python tests/run_scenarios.py smoke
sudo -E .venv/bin/python tests/run_scenarios.py concurrent
```

The two skipped tests are the end-to-end placeholders TC22 (multi-client
comparison) and TC24 (all-down policy); they are not passes.

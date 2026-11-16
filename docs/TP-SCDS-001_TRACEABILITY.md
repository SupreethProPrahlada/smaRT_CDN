# TP-SCDS-001 — Official Test Case Traceability

Companion to `Smart_CDN_IEEE829_Test_Plan.docx` (TP-SCDS-001, Version 1.1) and
`Smart_CDN_SRS_Agile_Plan.docx` (SRS Version 0.1).

The repository's pytest docstrings use the IDs from `docs/test_plan.md`
(`TC01`–`TC63`). Those are **not** the official TP-SCDS-001 IDs. This table is
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
| TC04 | Single download, checksum OK | `tests/run_scenarios.py smoke`; live run 8ac206a7b4 completed 16 MiB at 90.07 Mbps; SHA-256 matched | PASS (live, 2026-11-16) |
| TC05 | Six simultaneous downloads, checksum OK | Live `concurrent --size-mb 8 --duration 60`; CSV records c1–c6 all have `sha256_match=True`; the six-client harness verified each output digest | PASS (live, 2026-11-16) |
| TC06 | All three servers healthy | `test_tc08_heartbeat_datagram_contract`, `test_tc09_valid_heartbeat_updates_known_server_load`; live telemetry shows srv1–srv3 UP | PASS |
| TC07 | New connections go to least-loaded healthy server | `test_tc11_numeric_dynamic_selection`, `test_tc12_single_healthy_server_selected`; controller `[Route Decision]` logs | PASS (unit + live route) |
| TC08 | Fixed server assignment used | `test_tc20_static_client_mapping`, `test_tc21_dynamic_and_static_mode_instances`; `CDN_MODE=static` experiment rows | PASS |
| TC09 | Server DOWN within 10–12 s; new connections to healthy server | `test_tc50_silent_server_goes_down_and_flows_are_flushed`; live failover run (32 MiB, srv1 terminated, digest matched). DOWN transition was inferred from recovery, not captured in an event log. | PASS (with evidence caveat) |
| TC10 | Resume from last byte within 12 retries, checksum OK | `test_tc42_client_resumes_from_received_offset`, `test_tc46_client_gives_up_after_max_retries`; live failover transfer | PASS |
| TC11 | CDN flow rules visible on switches | `test_tc02_vip_arp_and_bidirectional_nat_rules` checks the exact forward/reverse FlowMods; no `ovs-ofctl dump-flows` capture was archived | PARTIAL |
| TC12 | Live flow moved to s5 with no client reconnect | `test_tc53_primary_link_down_moves_live_flow_to_detour`; live link-failure run matched SHA-256. Return direction moves to s5 too (s2 detour egress rule). | PASS (live hash + unit flow evidence) |
| TC13 | Delay 5 → 100 ms moves the flow | `test_s4_detour_decision_obeys_latency_delta_and_link_state` (thresholds) and congestion runs; no live `tc qdisc` delay-increase scenario | PARTIAL |
| TC14 | New connections use the direct route again | `test_tc56_recovered_primary_takes_new_flows`; live link-failure scenario restores s1-s2 after 1 s | PASS |
| TC15 | Adaptive congestion: direct → backup → direct | `test_s4_adaptive_congestion_adjusts_rate_with_utilization`; live adaptive congestion run (89.77 Mbps, digest matched). Route event sequence not archived. | PASS (exploratory) |
| TC16 | Random congestion repeatable with seed | `test_s4_random_congestion_is_reproducible_for_fixed_seed`; live `--seed 42` run | PASS |
| TC17 | RTT/utilization/state logged every 5 s | Constant + `test_tc39_controller_status_log_contains_telemetry`; live 5 s cadence not timed | PARTIAL |
| TC18 | Route colours/decision update every second | `tools/route_map.html`; `test_tc18_route_map_refreshes_and_colours_links_by_load`; browser render not exercised | PARTIAL |
| TC19 | Rows appended to `results/data/experiments.csv` | `test_s4_experiment_results_append_dynamic_and_static_rows_once`, `test_s4_comparison_runs_scenario_in_both_explicit_modes`; live file `results/data/experiments-live-20261116.csv` | PASS (exploratory) |
| TC20 | All scenarios run and report generated | One approved-root batch executed smoke, failover, link-failure, random congestion (seed 1), and concurrent; individual JSON outputs are in `/tmp/opencode/live/*.log`. No consolidated report generator was run. | PARTIAL |
| TC21 | Single download ≥85 Mbps on clean 100 Mbps link | Smoke measured 90.07 Mbps on this run; failover 15.88, link-failure 46.69, congestion 43.45 Mbps. One clean-link sample exceeds threshold; no automated threshold assertion or repeatability evidence. | PARTIAL (single exploratory sample) |
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
uv run pytest -q                       # 79 passed, 2 skipped at this baseline
sudo -E .venv/bin/python tests/run_scenarios.py smoke
sudo -E .venv/bin/python tests/run_scenarios.py concurrent --size-mb 8 --duration 60
```

The two skipped tests are the end-to-end placeholders TC22 (multi-client
comparison) and TC24 (all-down policy); they are not passes.

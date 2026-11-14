# IEEE 829 Test Plan — Smart CDN Sprints 1 and 2

1 Test Plan Identifier

Test Plan ID: TP-SCDN-S12-001
Project: Smart CDN (`smaRT_CDN`)
Scope: Sprint 1 and Sprint 2 implementation on `main`
Requirements baseline: Smart CDN SRS, Version 0.1 (Draft), supplied as `Smart_CDN_SRS_Agile_Plan.docx`
Plan template/reference: `Smart_CDN_IEEE829_Test_Plan.docx`

2 References

- `README.md` at the tested repository revision.
- `docs/SPRINT_0.md`, `docs/SPRINT_1.md`, `docs/SPRINT_2.md`.
- `docs/INTERFACE_CONTRACTS.md`.
- `config/settings.py`, `app/`, `controller/`, `topology/`, and `scripts/`.
- Smart CDN SRS Version 0.1 (Draft), supplied by the user.
- IEEE 829 Test Plan template, supplied by the user.
- Latest fetched `main` revision at test start: `fe32a0d`.

3 Introduction

This plan verifies the repository's Sprint 1 and Sprint 2 work against the supplied SRS and IEEE 829 template. It follows a phase-based sequence: inspect requirements and code, design and implement cases, run unit tests, run available integration tests, then record evidence and remaining work. Sprints 3 and 4 are outside this execution scope. A test is not considered passed merely because a constant or a mock matches an expectation; integration and system acceptance remains open unless the relevant production behavior is exercised. Ambiguous or absent acceptance details are listed as questions rather than invented.

4 Test Items

- VIP address/MAC configuration, ARP handling, and forward/reverse NAT in `config/settings.py` and `controller/cdn_controller.py`.
- Mininet topology definition in `topology/topo.py`.
- TCP content server/client streaming and SHA-256 reporting in `app/server.py` and `app/client.py`.
- Server heartbeat sender and controller heartbeat parsing in `app/server.py` and `controller/cdn_controller.py`.
- Probe/EMA and port-stat utilization handlers in `controller/cdn_controller.py`.
- Dynamic/static server selection in `controller/selector.py`.
- Live JSON export and 5-second status logging in `controller/cdn_controller.py`; client-transfer CSV in `app/client.py`.
- Sprint 2 terminal dashboard and concurrency stress utility in `scripts/dashboard.py` and `scripts/stress_test.py`.
- Pytest suite in `tests/`.

5 Software Risk Issues

- Ryu is not installed in the current environment; controller packet handlers and live export tests are conditionally skipped.
- The manifest pins Python 3.9, but only Python 3.14.9 is available here. Unit results therefore do not establish compatibility with the declared runtime. Pytest is also not declared in `pyproject.toml`; the current host provides pytest 9.2.0.
- Mininet and OVS commands are present, but no Ryu manager is available and non-interactive sudo is unavailable; live topology/controller tests cannot be run here.
- The client accepts short responses as successful when `expected_hash` is omitted; a supplied hash is optional in the API/CLI.
- The stress worker treats clean EOF as success without comparing received byte count with the advertised total or comparing its digest with a trusted expected digest.
- The client assumes a response header exists; the server closes the connection without an error response for a missing file, producing an unhandled `IndexError` in the client.
- The controller parses heartbeat server IDs but does not validate that the datagram source IP is authorized for that ID; an unauthorized host can forge load/status updates.
- Probe forwarding needs live verification: the controller injects a probe toward each server switch, while that switch's probe rule outputs to the same trunk port the probe arrived on; no server-side echo responder is implemented.
- The dashboard labels every logged transfer `PASS (100% Hash Match)` without inspecting the logged verification result, and labels the lowest-RTT server optimal even though dynamic selection uses three factors.
- The client and stress tester append different CSV schemas to the same configured transfer-log path, so a shared log can have a mismatched header and rows.
- Live-route JSON export writes directly to the destination and suppresses all exceptions; concurrent dashboard reads can see partial JSON and export failures are silent.
- The all-servers-down selector path currently returns `srv1`; the SRS does not specify the required policy.
- Selector normalization and tie-breaking are not specified numerically in the SRS.
- Sprint 2 documentation claims `gaming`, `bulk_video`, and `balanced` policy profiles, but the current `controller/selector.py` has only the fixed weight map and no profile-selection API. Confirm whether those claims remain requirements.
- `CDN_MODE`/profile activation for a running controller is not clearly wired: `DEFAULT_CDN_MODE` is fixed in settings and the controller constructs its selector from that constant.

6 Features to be Tested

- FR-1: VIP `10.0.0.100`, ARP reply, and bidirectional header translation for TCP service traffic.
- FR-2: 1-second EtherType `0x88B5` latency probing and EMA smoothing with alpha 0.5.
- FR-3: 1-second OpenFlow port statistics polling and utilization bounded to 0%-100%.
- NFR-3: one-second latency and port-stat polling cadence (constant check is unit-tested; live cadence requires Ryu).
- FR-4 Sprint 2 scope: server sends UDP `STATUS <id> <active_connections> <timestamp>` to `10.0.0.254:9000` every 2 seconds; controller parses valid heartbeats and tracks load. Crash timeout/DOWN transitions are Sprint 3 scope and are not accepted here.
- FR-5: dynamic server selection using weights 0.4 latency, 0.4 utilization, 0.2 active connections, as implemented with per-candidate normalization.
- FR-7 Sprint 1 scope: binary streaming in 65,536-byte chunks and SHA-256 reporting. Retry/resume is Sprint 3 scope.
- FR-8 Sprint 2 scope: route JSON export, 5-second controller status logs, and client CSV transfer records.
- FR-11: fixed client-to-server static map and dynamic/static selector behavior.
- Sprint 2 documented dashboard and concurrency stress tester, with the limitations in Section 5 evaluated explicitly.

7 Features not to be Tested

- FR-6 congestion rerouting; FR-9 path failure migration; FR-10 path recovery; FR-12 congestion generator. These are Sprint 4 scope in the supplied SRS.
- FR-4 crash detection/flow flushing and FR-7 byte-offset retry/resume or directory traversal defense. These are Sprint 3 scope.
- NFR acceptance thresholds assigned to later sprints, physical-network performance, and third-party Ryu/OVS/Mininet internals.
- Live dashboard rendering over a running controller, beyond the dashboard's testable CSV/numeric helpers.
- Dynamic/static network performance comparison, which needs a live Mininet/Ryu environment and agreed comparison metrics.

8 Approach

Phase 1 — Read the repository, Sprint records, interface contracts, supplied SRS, and IEEE 829 template; map Sprints 1-2 requirements to code. Phase 2 — Implement unit tests using production code without Mininet or root. Phase 3 — Run `pytest -m "not integration"`. Phase 4 — Run marked integration/system cases only when Ryu, OVS, Mininet, and safe privileges are available. Phase 5 — reconcile each test case against observed output and record evidence and remaining tasks. Tests use temporary paths and local socket pairs/fakes where appropriate; no production source changes are included in this test-only work.

9 Item Pass/Fail Criteria

PASS: the tested production behavior meets the SRS/interface contract for the case. FAIL: the exercised behavior contradicts that requirement. XFAIL in pytest means the test deliberately documents a known failing requirement; it is not a product pass. NOT EXECUTED: dependency/environment block or no live execution evidence. For ambiguous behavior, the test is characterization only and is not acceptance sign-off. Static or mocked evidence does not substitute for live OpenFlow/Mininet evidence.

10 Suspension Criteria and Resumption Requirements

Suspend network tests if Ryu/OpenFlow connectivity is unavailable, Mininet/OVS cannot create an isolated topology, privilege approval is unavailable, the host's existing OVS state could be affected, or the controller/test process becomes unstable. Resume only after confirming a disposable topology and safe cleanup path, verifying controller connectivity, and retaining prior test output. Do not use `sudo -n` as a substitute for an approved interactive privilege path.

11 Test Deliverables

- This IEEE 829-style plan and its test-case/status table.
- Unit, integration, and system pytest sources under `tests/`.
- Actual pytest command output and environment notes.
- Defect/requirement questions in Sections 5, 12, and 20.

12 Remaining Test Tasks

- Run the real Ryu controller packet-in, probe, port-stat, heartbeat, and JSON-export tests in a Python 3.9/Ryu environment.
- Run the controller status-logging integration case and measure the configured 5-second cadence in that environment.
- Run Mininet/OVS end-to-end checks for ARP/NAT and actual client downloads through VIP.
- Run a live dynamic/static comparison and verify route choice under the approved mode-selection mechanism.
- Clarify behavior for all servers unavailable, selector normalization/ties, missing content, and profile activation before acceptance.
- Resolve the three client/transfer error-handling defects (truncated-transfer false success in both clients and missing-file client crash) in a separate implementation task; remove strict xfail markers only after regression tests pass.
- Verify probe round-trip behavior in a live Mininet/Ryu topology; the current forwarding path appears not to return probe packets to the controller.
- Verify TC10 against Ryu and restrict accepted heartbeat source IPs to each server's configured address.
- The supplied test-plan document references `tests/run_scenarios.py` and `tests/make_content.py`; neither file is present in this checkout. Confirm whether they are expected in Sprint 1/2 or later.

13 Environmental Needs

Unit: Python with pytest; pytest 9.2.0 is installed on this host but is not listed in `pyproject.toml`; no Mininet or root. Current execution uses Python 3.14.9 and pytest 9.2.0. Integration: declared Python 3.9 runtime, Ryu, Mininet, Open vSwitch/OpenFlow 1.3, and a safe approved privilege path. Current host has Mininet and `ovs-vsctl`, but lacks Python 3.9, Ryu, and `ryu-manager`; `sudo -n true` fails. Current test artifacts are written only under pytest temporary directories.

14 Staffing and Training Needs

Tester: Shreyansh Tandon. Developers: Supreeth Prahalada and Shyam Sooraj. Project Guide and Supervisor: names not supplied; retain `[Name]`. Network-test staff need Python/pytest, TCP, OpenFlow 1.3, Ryu, Mininet, and safe disposable-topology operation knowledge.

15 Responsibilities

- Shreyansh Tandon (Tester): test design, execution, evidence, defect reporting, and status reconciliation.
- Supreeth Prahalada (Developer): clarify Sprint 1-2 implementation and support defect diagnosis.
- Shyam Sooraj (Developer): review/clarify implementation and support defect diagnosis.
- Project Guide: [Name], review/approval.
- Supervisor: [Name], review/approval.

16 Schedule

Phase 1 — Requirements/code review and case design: completed before implementation of this test suite. Phase 2 — Unit test authoring: completed for available Sprint 1-2 behaviors. Phase 3 — Unit execution: performed on current host. Phase 4 — Ryu/Mininet integration and full-system execution: deferred until required runtime and privilege environment is available. Phase 5 — stakeholder clarification, defect resolution, and final acceptance: remaining.

17 Planning Risks and Contingencies

The SRS is a draft for the larger system and assigns some behaviors to later sprints; this plan limits claims to Sprints 1-2. If test runtime dependencies cannot be installed or privileges approved, retain integration cases as NOT EXECUTED. If expected behavior is unclear, preserve the open question and do not encode an invented acceptance rule. Where test evidence exposes a code defect, preserve the failing regression as strict xfail and report it for a separate fix.

18 Test Case Specification

`Actual Result` and `Status` reflect observed test output. The two strict-xfail cases were executed and demonstrate requirements not met; they are recorded as FAIL, not PASS. Cases skipped for missing Ryu or live testbed remain NOT EXECUTED.

| TC ID | Description | Expected Result | Actual Result | Status |
|---|---|---|---|---|
| TC01 | FR-1 VIP identity configuration | VIP IP/MAC match SRS | `10.0.0.100` / `00:00:00:00:01:00` asserted | Pass |
| TC02 | FR-1 VIP ARP plus forward/reverse NAT flow installation | VIP ARP reply, both translation directions, and 60-second flow idle timeout | Ryu unavailable; integration case skipped | Not Executed |
| TC03 | FR-1 unrelated-address ARP negative case | Controller does not claim unrelated IP | Ryu unavailable; integration case skipped | Not Executed |
| TC04 | FR-2 probe RTT EMA, alpha 0.5 | Sample old 10 ms/new 20 ms yields about 15 ms | Ryu unavailable; integration case skipped | Not Executed |
| TC05 | FR-2 malformed probe negative case | Invalid probe leaves telemetry unchanged | Ryu unavailable; integration case skipped | Not Executed |
| TC06 | FR-3 zero and normal port-stat samples | Zero delta yields 0%; 50 Mbps on 100 Mbps trunk yields 50% | Ryu unavailable; integration case skipped | Not Executed |
| TC07 | FR-3 utilization upper boundary | Throughput above capacity clamps to 100% | Ryu unavailable; integration case skipped | Not Executed |
| TC08 | FR-4 server heartbeat message and 2-second period | Correct STATUS payload sent to 10.0.0.254:9000 every 2 seconds | Captured `STATUS srv2 3 1234.500`; destination and 2.0-second delay asserted | Pass |
| TC09 | FR-4 valid heartbeat updates known server load | Known server state/load updates from valid datagram | Ryu unavailable; integration case skipped | Not Executed |
| TC10 | FR-4 malformed/unknown/unauthorized heartbeat negative case | Malformed, unknown, or non-server source datagrams leave known telemetry unchanged | Ryu unavailable; integration case skipped; source-IP validation is absent in current handler | Not Executed |
| TC11 | FR-5 known numeric dynamic-selection inputs | Lowest calculated normalized score wins | For known telemetry, selector chose `srv1` as expected | Pass |
| TC12 | FR-5 exactly one healthy server | Sole healthy server is selected | `srv2` selected when it alone was UP | Pass |
| TC13 | FR-5 all servers DOWN characterization | Follow stakeholder-approved no-healthy-server policy | Current implementation returned `srv1`; stakeholder policy still unresolved | Pass (characterization only) |
| TC14 | FR-7 non-64-KiB-multiple binary payload | Exact bytes and SHA-256 match | Exact 66,048-byte payload and digest matched | Pass |
| TC15 | FR-7 empty content | Zero-byte stream is handled correctly | Response was `OK 0 0` with empty body | Pass |
| TC16 | FR-7 missing-file negative case | Missing file is not advertised as a successful stream | Server closed without an `OK` response; thread terminated | Pass |
| TC17 | FR-8 live-route JSON schema | Valid snapshot contains timestamp, mode, and server telemetry | Ryu unavailable; integration case skipped | Not Executed |
| TC18 | FR-8 client CSV header and row | Header/metrics written once in documented schema | CSV header/row matched expected fields; SHA status was `True` | Pass |
| TC20 | FR-11 fixed static mapping | Each client maps to assigned server | All six client-to-server assignments matched configured mapping | Pass |
| TC21 | FR-11 dynamic versus static selector instances | Selected mode changes server choice for the same client/input | Same client selected `srv1` dynamically and `srv2` statically | Pass |
| TC22 | FR-11 live dynamic/static comparison | Same scenario executed in both modes and results captured | Ryu/Mininet and approved metrics unavailable | Not Executed |
| TC23 | FR-7 concurrent server streams | Concurrent clients receive independent complete payloads | Three simultaneous streams returned their exact distinct payloads | Pass |
| TC24 | FR-5 all servers down end-to-end policy | Request follows stakeholder-approved behavior | Policy unresolved; live scenario skipped | Not Executed |
| TC25 | FR-2/NFR-3 probe and port-stat intervals | `0x88B5`, 1-second probe/stat intervals, alpha 0.5 | Constants matched; runtime cadence not exercised without Ryu | Pass (configuration only) |
| TC26 | FR-5 three selection weights | 0.4/0.4/0.2 weights configured | Weight map matched `{latency: 0.4, utilization: 0.4, load: 0.2}` | Pass |
| TC27 | FR-7 chunk size | Chunk size is 65,536 bytes | Configured chunk size is 65,536 bytes | Pass |
| TC28 | FR-1 addressing and ports | Client/server addresses and ports match contracts | Six client IPs, three server IPs, TCP 8000 and OpenFlow 6653 asserted | Pass |
| TC29 | FR-4 heartbeat endpoint constants | Heartbeat destination and period match contract | `10.0.0.254:9000`, interval 2.0 seconds asserted | Pass |
| TC30 | FR-7 client saves/verifies complete content | File equals payload and correct SHA-256 reports PASS | Saved bytes matched payload and SHA-256; client printed PASS | Pass |
| TC31 | FR-7 wrong-hash negative case | Incorrect supplied digest reports FAIL | Client printed FAIL for an incorrect expected digest | Pass |
| TC32 | FR-7 truncated payload without expected hash | Partial transfer must not be reported as success | Client reports PASS and CSV `sha256_match=True` for partial bytes | Fail (strict xfail) |
| TC34 | FR-1 topology construction | s1-s4, c1-c6, srv1-srv3, OpenFlow13 and shaped trunks declared | Topology object had expected nodes, OpenFlow13, and trunk shapes | Pass |
| TC35 | FR-8 dashboard recent CSV rows | Dashboard helper returns latest three rows | Helper returned records c3, c4, c5 from five-row sample | Pass |
| TC36 | FR-7 stress worker digest | Worker digest equals received payload digest | Worker digest matched exact received payload | Pass |
| TC37 | FR-7 stress tester truncated payload | Truncated transfer must be rejected | Worker records success for 4 of 8 advertised bytes | Fail (strict xfail) |
| TC38 | FR-8 dashboard malformed numeric input | Invalid number uses configured fallback | `safe_float("bad", 7.5)` returned 7.5; numeric input parsed | Pass |
| TC39 | FR-8 controller status log | Log output contains mode, RTT, utilization, and active connections | Ryu unavailable; integration case skipped | Not Executed |
| TC41 | FR-7 client handles missing-file error response | Missing file produces a controlled client failure, not an uncaught exception | Client raises `IndexError` when the server closes without a response header | Fail (strict xfail) |

19 Test Execution Summary

`pytest -m "not integration" -q`: 22 passed, 3 xfailed, 13 deselected; exit code 0. The three xfailed cases are known product defects, not passes. `pytest -m integration -q`: 1 passed, 12 skipped, 25 deselected; exit code 0. The topology declaration test passed; Ryu-dependent controller tests skipped because `ryu` is not installed, and system scenarios skipped because a live environment/approved acceptance policy is unavailable. Full suite: `pytest -q` reported 23 passed, 12 skipped, 3 xfailed (38 collected); exit code 0. Re-running the three strict-xfail assertions without xfail handling using `PYTHONPATH=. pytest --runxfail -q tests/unit/test_fr7_client_download.py::test_tc32_client_rejects_truncated_payload_without_expected_hash tests/unit/test_fr7_stress_worker.py::test_tc37_stress_worker_rejects_truncated_payload tests/unit/test_fr7_client_download.py::test_tc41_client_handles_missing_file_response` produced three failures (exit code 1): client reported PASS and `sha256_match=True` after 4/8 bytes; stress worker marked 4/8 bytes successful; client raised `IndexError` on an empty response header. `python -m compileall -q app config controller topology scripts tests` and `git diff --check` both exited 0. Requirement-level count across 38 plan cases: 26 executed (23 passed, 3 failed), 12 not executed.

20 Conclusion

The suite exercises Sprint 1-2 configuration, selection, streaming, heartbeat sending, client CSV logging, dashboard helpers, and stress-worker behavior. It also contains Ryu-dependent controller tests and Mininet topology tests, but those cannot all execute in the current environment. Executed regressions expose false success on truncated transfers and an uncaught client exception for an empty server response. Code review also found missing heartbeat source authentication, an apparently incomplete probe return path, misleading dashboard verification/selection labels, incompatible CSV schemas, non-atomic silent JSON export, and selector profiles claimed by documentation but absent from the current implementation. Full Sprint 1-2 acceptance therefore remains incomplete. Questions for the team:

1. For the all-servers-down case, should selection return an explicit no-server result, raise/reject the request, or use a fallback?
2. What exact normalization and tie-breaking rule should FR-5 use? Is the raw or normalized score normative?
3. Are `gaming` and `bulk_video` profiles still required, and what API/environment variable and exact weights select them?
4. How should the running controller receive `CDN_MODE=static`? Should it read an environment variable, command-line setting, or configuration edit?
5. What error response should missing files and invalid offsets produce? Missing-file behavior is not specified in the interface contract; offset resume belongs to Sprint 3.
6. Is FR-4 heartbeat timeout/DOWN detection intentionally deferred to Sprint 3, despite its broader wording in the SRS?
7. Should client and stress-test downloads fail when received bytes differ from the advertised total even without a caller-supplied hash? Is a trusted expected digest required for every run?
8. The supplied test-plan template refers to `tests/run_scenarios.py` and `tests/make_content.py`; are those expected deliverables for this repository and these sprints?
9. Is live Mininet/Ryu test execution expected on this host, and which Python 3.9/Ryu/Mininet versions and privilege workflow should be used?

21 Approvals

Tester: Shreyansh Tandon — Signature: __________________ Date: __________
Developer: Supreeth Prahalada — Signature: __________________ Date: __________
Developer: Shyam Sooraj — Signature: __________________ Date: __________
Project Guide: [Name] — Signature: __________________ Date: __________
Supervisor: [Name] — Signature: __________________ Date: __________

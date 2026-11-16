## Developer Environment Setup

### One environment, one command
`uv` provisions Python 3.9 and installs Ryu 4.34, Mininet and the project
dependencies from `pyproject.toml` into `.venv`. Both the applications and
`ryu-manager` therefore run from the same interpreter.

### One-Time Setup
```
uv sync                 # create/update .venv from pyproject.toml + uv.lock
source .venv/bin/activate
```
`ryu-manager` and `pytest` are available inside `.venv`; running `uv run <cmd>`
uses it without activation.

---

# Smart CDN (Software-Defined Content Delivery Network)
**Course:** Software Engineering 3K04 / 3M04 — McMaster University  
**Team:** Supreeth Prahlada (Developer 1) · Shyam Sooraj (Developer 2) · Shreyansh Tandon (Tester)
**Delivered Sprints:** Sprint 0, 1, 2, 3 and 4 (implemented on `test/sprint-1-2-coverage`)
---
## 📖 Executive Summary
Smart CDN is an intelligent, Software-Defined Content Delivery Network built on **OpenFlow 1.3**, the **Ryu SDN Controller**, and **Mininet**. 
Instead of requiring clients to know physical backend server IP addresses, clients communicate with a single **Anycast Virtual IP (VIP: `10.0.0.100:8000`)**. Ingress switch `s1` dynamically inspects live network telemetry (RTT latency, trunk port utilization, and active server load) and rewrites Layer 4 bidirectional NAT flow rules to seamlessly direct traffic to the optimal backend server replica with zero data corruption.
---
## 🏗️ System Architecture & Topology
```text
                  +-----------------------------------+
                  |   Ryu SDN Controller (OpenFlow)   |
                  |  - Active Probes (0x88B5)          |
                  |  - Port Stats Poller (1s)         |
                  |  - 3-Factor Cost Selection Engine |
                  +-----------------+-----------------+
                                    | OpenFlow 1.3 (Port 6653)
                                    v
+------------------+         +--------------+ (100M/5ms)  +----+        +------+
| Client Pool      |=======> | Ingress (s1) |------------>| s2 |------->| srv1 | (10.0.0.11)
| c1 - c6          | (VIP)   | L4 Anycast   | (50M/20ms)  +----+        +------+
| (10.0.0.1-6)     |         | VIP NAT      |------------>| s3 |------->| srv2 | (10.0.0.12)
+------------------+         +--------------+             +----+        +------+
                                    | (10M/50ms)          +----+        +------+
                                    +-------------------->| s4 |------->| srv3 | (10.0.0.13)
                                                          +----+        +------+
```
### Network Topology Specifications
| Node | Role | IP Address | MAC Address | Link Characteristics |
| :--- | :--- | :--- | :--- | :--- |
| **VIP** | Anycast Gateway | `10.0.0.100` | `00:00:00:00:01:00` | Port 8000 (TCP Streaming) |
| **s1** | Ingress L4 NAT Switch | — | `00:00:00:00:00:01` | OpenFlow 1.3 Gateway |
| **srv1** | Primary Edge Replica | `10.0.0.11` | `00:00:00:00:00:11` | `s1-s2`: 100 Mbps, 5 ms delay |
| **srv2** | Secondary Edge Replica | `10.0.0.12` | `00:00:00:00:00:12` | `s1-s3`: 50 Mbps, 20 ms delay |
| **srv3** | Backup Edge Replica | `10.0.0.13` | `00:00:00:00:00:13` | `s1-s4`: 10 Mbps, 50 ms delay |
| **c1 - c6** | Client Request Pool | `10.0.0.1` – `10.0.0.6` | `00:00:00:00:00:01-06` | Edge access links (100 Mbps, 1 ms) |
---
## 🎯 Developer 1 Deliverables (Sprints 0 - 2)
### 1. Sprint 0: Foundations & Architecture
* **Standard Repository Scaffold:** Structured tree separating `config/`, `topology/`, `controller/`, `app/`, `tests/`, `results/`, `scripts/`, and `docs/`.
* **Central Data Dictionary (`config/settings.py`):** Single source of truth for VIPs, hardware MACs, streaming ports (8000), telemetry ports (9000), and link profiles.
* **Interface Contracts (`docs/INTERFACE_CONTRACTS.md`):** Formal specifications for OpenFlow flow tables, UDP telemetry schemas, and chunk protocols.
### 2. Sprint 1: Baseline Architecture & VIP Streaming
* **Mininet Software-Defined Topology (`topology/topo.py`):** Multi-tier topology with shaped asymmetric links, auto-inheriting the virtual environment PATH.
* **Chunked Binary Server (`app/server.py`):** High-throughput TCP server delivering files in 64 KB binary chunks with protocol headers (`OK <total_bytes> <remain_bytes>`).
* **VIP Client Application (`app/client.py`):** Client connecting exclusively to `10.0.0.100:8000`, running real-time streaming SHA-256 verification and writing CSV transfer metrics.
* **OpenFlow Ingress Controller (`controller/cdn_controller.py` & `controller/paths.py`):**
  * Custom ARP handler resolving VIP queries to `00:00:00:00:01:00`.
  * Dynamic bidirectional OpenFlow 1.3 Layer 4 NAT flows rewriting VIP <-> server IPs and MACs.
### 3. Sprint 2: Real-Time Telemetry & Smart Server Selection
* **3-Factor Cost Selection Engine (`controller/selector.py`):**
  Dynamically evaluates candidate servers using normalized weights:
  Score = w_rtt * Norm(RTT) + w_util * Norm(Util) + w_load * Norm(Load)
* **Selection Weights:** `balanced` only — 40% latency, 40% utilization, 20% load
  (`SELECTION_WEIGHTS` in `config/settings.py`). Earlier draft `gaming` /
  `bulk_video` profile presets were removed in the final selector; changing the
  weights is a one-line edit in `selector.py`/`settings.py`.
* **Active SDN Probing:** Controller injects custom EtherType `0x88B5` probe frames every 1.0s to measure path RTT, smoothed via Exponential Moving Average (alpha = 0.5).
* **Live Bandwidth Monitoring:** Polls OpenFlow port statistics (`OFPPortStatsRequest`) every 1.0s to calculate real-time trunk utilization (peaked at 33% - 55% during transfers).
* **Out-of-Band Server Telemetry:** Server daemon broadcasts UDP heartbeats (`STATUS <id> <active_conns> <ts>`) to `10.0.0.254:9000` every 2.0s.
* **Live NOC Terminal Dashboard (`scripts/dashboard.py`):** Real-time ASCII dashboard with colored Unicode meters, server IPs, link characteristics, and transfer history.
* **Multi-Stream Concurrency Stress Tester (`scripts/stress_test.py`):** Multi-threaded VIP load generator measuring aggregate throughput and validating SHA-256 integrity.
### 4. Sprint 3: Failover & Byte-Offset Resume
* **Crash detection (`controller/cdn_controller.py`):** A silent server is marked `DOWN` after the 10 s heartbeat timeout and its OpenFlow rules are flushed; heartbeats must come from the configured server IP.
* **Client resume (`app/client.py`):** Reconnects from the last persisted byte with up to 12 one-second retries; a partial transfer is never reported as a pass.
* **Content safety (`app/server.py`):** Directory-traversal syntax and symlink escapes are rejected; missing files and bad offsets return `ERR` responses.
### 5. Sprint 4: Detour, Link Failure, Visualizer & Experiments
* **Detour switch s5:** topology adds s5 (100M/15 ms) and `loadsrc` (c7); active srv1 flows move to s5 when the s1-s2 RTT rises by 50 ms or more, and the return direction is moved to s5 as well (FR-6/FR-9).
* **Link failure and recovery:** OpenFlow port-status events move live flows to s5 when s1-s2 goes down and restore the direct path when it recovers (FR-10).
* **Congestion generator (`scripts/congestion.py`):** adaptive and seeded-random UDP cross-traffic on the s1-s2 trunk (FR-12).
* **Live route map (`tools/route_map.html`):** browser dashboard with green/orange/red utilization bands and dashed grey dead links, refreshing every second.
* **Experiment runner (`scripts/experiments.py`):** appends paired dynamic/static rows to `results/data/experiments.csv`.
---
## 📊 Live Verification & Benchmarks
| Metric | Dynamic Smart Selection (Sprint 2) | Static Baseline (`CDN_MODE=static`) |
| :--- | :--- | :--- |
| **Server Selected** | **srv1** (Lowest Latency: 10 ms RTT) | **srv2** (Enforced: 40 ms RTT) |
| **Single Client Throughput**| **34.30 Mbps** (10 MB in 2.45s) | **14.48 Mbps** (10 MB in 5.79s) |
| **Multi-Stream Stress Test**| **44.45 Mbps** aggregate bandwidth across 3 concurrent streams (30 MB in 5.40s) | Single-stream bound |
| **Data Integrity** | `PASS` (SHA-256: 100% Match) | `PASS` (SHA-256: 100% Match) |
| **Peak Trunk Utilization** | **33.4% – 55.0%** captured live on `s1-s2` during active transfer | Link-bound on `s1-s3` |

### Sprint 3–4 live verification (2026-11-16)
| Scenario | Evidence |
| :--- | :--- |
| Smoke (2 MiB) | SHA-256 pass, 62.40 Mbps |
| Server failover (32 MiB, srv1 killed mid-transfer) | SHA-256 pass in 16.94 s (15.85 Mbps), client resumed without restarting at 0% |
| Link failure/recovery (16 MiB, s1-s2 down for 1 s) | SHA-256 pass in 3.155 s (42.55 Mbps) |
| Random congestion (16 MiB, `--seed 42`) | SHA-256 pass, 89.72 Mbps |
| Adaptive congestion (16 MiB) | SHA-256 pass, 89.77 Mbps |
| Paired dynamic/static experiments (3 × 8 MiB) | `results/data/experiments-live-20261116.csv`, all 1/1 complete |

Raw transfer rows are appended to `results/data/client-transfers.csv`. These are
exploratory runs: one client only, and the draft SRS does not define an
experiment sample size, so they are not a statistical policy comparison.
---
## 🚀 Execution & Quickstart Guide
### 1. Start Ryu Controller (Terminal 1)
```
cd ~/smaRT_CDN
source .venv/bin/activate
# Run in Default Dynamic Mode (control port bound to loopback):
uv run ryu-manager --ofp-listen-host 127.0.0.1 controller/cdn_controller.py
# OR run the static baseline:
# CDN_MODE=static uv run ryu-manager --ofp-listen-host 127.0.0.1 controller/cdn_controller.py
```
### 2. Launch Mininet Topology & Servers (Terminal 2)
```
cd ~/smaRT_CDN
source .venv/bin/activate
sudo -E .venv/bin/python topology/topo.py
# Inside the Mininet CLI (python3 now resolves to the venv interpreter):
mininet> srv1 python3 app/server.py --id srv1 --ip 10.0.0.11 &
mininet> srv2 python3 app/server.py --id srv2 --ip 10.0.0.12 &
mininet> srv3 python3 app/server.py --id srv3 --ip 10.0.0.13 &
# Optional, for the congestion scenario:
mininet> srv1 python3 app/traffic_sink.py --bind 10.0.0.11 &
```
### 3. Launch Live NOC Dashboard (Terminal 3)
```
cd ~/smaRT_CDN
python3 scripts/dashboard.py
```
### 4. Run Client Downloads & Stress Tests (Inside Mininet CLI)
```
# Generate deterministic content + manifest (host shell):
uv run python tests/make_content.py --size-mb 10 --filename test_10M.bin
# Single client download via Anycast VIP:
mininet> c1 python3 app/client.py --id c1 --file test_10M.bin
# 3 concurrent streams against Anycast VIP:
mininet> c1 python3 scripts/stress_test.py --concurrency 3 --file test_10M.bin
```
### 5. Route Map, Scenarios and Experiments (host shell)
```
# Serve the project root so the browser can fetch results/live_routes.json:
uv run python -m http.server 8080
# Then open http://localhost:8080/tools/route_map.html
# One-command scenarios (root + Mininet/OVS required):
sudo -E .venv/bin/python tests/run_scenarios.py smoke
sudo -E .venv/bin/python tests/run_scenarios.py failover --size-mb 32
sudo -E .venv/bin/python tests/run_scenarios.py link-failure
sudo -E .venv/bin/python tests/run_scenarios.py congestion --congestion-mode random --seed 1
sudo -E .venv/bin/python tests/run_scenarios.py concurrent
# Paired dynamic/static rows appended to results/data/experiments.csv:
uv run python scripts/experiments.py --runs 3 -- sudo -E .venv/bin/python tests/run_scenarios.py smoke --size-mb 8
```
---
## Automated Test Suite (Sprints 1–4)
`pytest` is declared in the `dev` dependency group, so no separate install is
needed:
```
uv run pytest -q
```
The unit suite needs neither Mininet nor root. Integration cases use Ryu
packet/controller objects; system scenarios need Mininet, Open vSwitch and an
approved privileged environment. Skipped tests are not acceptance passes. See
[`docs/test_plan.md`](docs/test_plan.md) for the tester's report and
[`docs/TP-SCDS-001_TRACEABILITY.md`](docs/TP-SCDS-001_TRACEABILITY.md) for the
TC01–TC24 mapping to the official IEEE 829 Test Plan.
---
## 📁 Repository Structure
```text
smaRT_CDN/
├── config/
│   └── settings.py              # Central IP, MAC, port & link settings
├── topology/
│   └── topo.py                  # Mininet topology (5 switches, c1-c6 + loadsrc, 3 servers)
├── controller/
│   ├── cdn_controller.py        # Ryu OpenFlow 1.3 VIP NAT, telemetry, failover/detour
│   ├── selector.py              # 3-Factor cost selection and static mode
│   └── paths.py                 # Flow install/delete helpers and port map
├── app/
│   ├── server.py                # 64 KB chunk server with UDP heartbeats
│   ├── client.py                # VIP client with resume and SHA-256 verification
│   └── traffic_sink.py          # UDP sink for the congestion generator
├── scripts/
│   ├── content.py               # Deterministic content + SHA-256 manifest
│   ├── congestion.py            # Adaptive/seeded-random UDP cross-traffic
│   ├── experiments.py           # Dynamic vs static CSV experiment runner
│   ├── dashboard.py             # Live ASCII NOC telemetry monitor
│   └── stress_test.py           # Multi-threaded concurrent VIP stress tester
├── tests/
│   ├── run_scenarios.py         # smoke/failover/link-failure/congestion/concurrent
│   ├── make_content.py          # Test-plan entry point for scripts/content.py
│   ├── unit/ integration/ system/
├── tools/
│   └── route_map.html           # Browser route visualizer (serve over HTTP)
├── docs/
│   ├── SPRINT_0.md … SPRINT_2.md
│   ├── INTERFACE_CONTRACTS.md
│   ├── test_plan.md
│   └── TP-SCDS-001_TRACEABILITY.md
├── results/
│   ├── live_routes.json         # Live atomic controller telemetry export
│   └── data/
│       ├── client-transfers.csv # Shared download benchmark log
│       └── experiments*.csv     # Dynamic/static experiment rows
```

### Replica Selection & All-Down Fallback Policy
- **Dynamic Mode (`cdn_mode="dynamic"`):** Scores all replicas with `status == "UP"` using normalized RTT latency, link utilization, and active connection count.
- **All-Servers-Down Fallback:** If all replicas report `status != "UP"`, `ServerSelector` deterministically falls back to the primary replica (`srv1`, `10.0.0.11`) so VIP NAT flows continue routing without dropping requests.

---
## 👥 Course Team Responsibilities
* **Developer 1 (Supreeth Prahlada):** Sprints 0–2 — architecture, VIP NAT, telemetry probing, 3-factor selection engine, dashboard and stress tester. *(COMPLETED)*
* **Developer 2 (Shyam Sooraj):** Sprints 3–4 — crash detection, byte-offset resume, traversal defence, detour switch s5, link-failure/recovery, congestion generator, route map and experiments. *(COMPLETED)*
* **Tester (Shreyansh Tandon):** Test plan TP-SCDS-001, scenario runner, unit/integration coverage, live verification and defect log. *(COMPLETED; see `docs/test_plan.md`)*

> **Branch note:** the Sprint 3–4 work is currently on `test/sprint-1-2-coverage`
> and is **not yet merged into `main`**. Per the SRS Definition of Done, merge it
> by pull request only after the regression suite passes.

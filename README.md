## Developer Environment Setup

### One Python Environment with uv
This repository is configured for **one Python 3.9 environment managed by uv**. The `pyproject.toml` and `uv.lock` include the project dependencies, Ryu, Mininet's Python package, and development test tools. Do not create or activate a separate `ryu-env` for this repository.

Ubuntu system packages are still required for Mininet/Open vSwitch. `uv` manages Python packages; it does not install or replace system networking services.

### One-Time Setup
From the repository root:

```bash
# Install uv if it is not already installed:
curl -LsSf https://astral.sh/uv/install.sh | sh

# Open a new terminal if needed, then:
# Clone the repository:
git clone https://github.com/SupreethProPrahlada/smaRT_CDN.git

cd ./smaRT_CDN
uv sync --all-groups
```

This creates or updates the local `.venv` from the locked dependencies. Use `uv run ...` for commands, or activate that same environment with `source .venv/bin/activate`.

---

# Smart CDN (Software-Defined Content Delivery Network)
**Course:** Software Engineering 3K04 / 3M04 — McMaster University
**Team:** Supreeth Prahlada (Developer 1) · Shyam Sooraj (Developer 2) · Shreyansh Tandon (Tester)
**Delivered Sprints:** Sprint 0, 1, 2, 3 and 4 (merged into `main`)
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
| **s5** | Detour Switch (Sprint 4) | — | — | srv1's second path: `s1-s5` 100 Mbps/10 ms + `s5-s2` 100 Mbps/5 ms |
| **bg** | Congestion Generator (Sprint 4) | `10.0.0.20` | `00:00:00:00:00:20` | Behind `s2`; its traffic crosses the primary `s1-s2` trunk |
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
* **Dynamic CDN Policy Profiles:**
  * `balanced` (Default): 40% Latency, 40% Utilization, 20% Load.
  * `gaming`: 80% Latency, 10% Utilization, 10% Load (Low-latency optimization).
  * `bulk_video`: 20% Latency, 70% Utilization, 10% Load (High-throughput optimization).
* **Active SDN Probing:** Controller injects custom EtherType `0x88B5` probe frames every 1.0s to measure path RTT, smoothed via Exponential Moving Average (alpha = 0.5).
* **Live Bandwidth Monitoring:** Polls OpenFlow port statistics (`OFPPortStatsRequest`) every 1.0s to calculate real-time trunk utilization (peaked at 33% - 55% during transfers).
* **Out-of-Band Server Telemetry:** Server daemon broadcasts UDP heartbeats (`STATUS <id> <active_conns> <ts>`) to `10.0.0.254:9000` every 2.0s.
* **Live NOC Terminal Dashboard (`scripts/dashboard.py`):** Real-time ASCII dashboard with colored Unicode meters, server IPs, link characteristics, and transfer history.
* **Multi-Stream Concurrency Stress Tester (`scripts/stress_test.py`):** Multi-threaded VIP load generator measuring aggregate throughput and validating SHA-256 integrity.
---
## 🎯 Developer 2 Deliverables (Sprints 3 - 4)
### 4. Sprint 3: 10 s Server Failover & Byte-Offset Client Resume ([`docs/SPRINT_3.md`](docs/SPRINT_3.md))
* **Crash Detection (FR-4):** A replica silent for 10 s (five missed heartbeats) is marked `DOWN` and its NAT flows on `s1` are deleted, so its clients are steered to a healthy replica. The next heartbeat brings it back `UP`. Heartbeats are accepted only from the server's own IP.
* **Byte-Offset Resume (FR-7):** The client reconnects up to 12 times, 1 s apart, sending `GET <file> <bytes received>`, and verifies SHA-256 over the whole file across connections.
* **Traversal Defence:** The server only serves plain file names inside `CONTENT_DIR`; `..`, `.` and escaping symlinks get `ERR Bad_Request`.
### 5. Sprint 4: Detour Switch `s5`, Congestion Rerouting & HTML Route Map ([`docs/SPRINT_4.md`](docs/SPRINT_4.md))
* **Second Path to srv1:** Detour switch `s5` (`s1 -> s5 -> s2`, 15 ms), probed every second like the trunks and watched through OpenFlow port-status messages.
* **Path Failure Migration (FR-9):** When `s1-s2` fails, live srv1 downloads are moved onto `s5` by rewriting their flow rules. The TCP connection is unchanged, so they continue with no reconnect.
* **Congestion Rerouting (FR-6):** When other traffic fills at least 50% more of the primary than of the detour, srv1 flows move to `s5`. Each flow's own rate (from flow statistics) is excluded, so a busy download never reroutes itself.
* **Path Recovery (FR-10):** Once the primary is healthy again, new srv1 flows use it.
* **Congestion Generator (FR-12, `scripts/congestion.py`):** Constant-rate UDP iperf load from `bg` across the primary trunk, plus adaptive and seeded-random `--mode` generators for reproducible experiments (`app/traffic_sink.py` is the UDP sink).
* **Live HTML Route Map (`scripts/route_map.py`):** Self-refreshing `results/route_map.html` showing every path's state, RTT and utilization, srv1's active path, and live flows. A browser dashboard at `tools/route_map.html` polls `results/live_routes.json` every second with green/orange/red load bands and dashed dead links.
### Tester tooling (TP-SCDS-001)
* **Scenario runner (`tests/run_scenarios.py`):** one command each for `smoke`, `failover`, `link-failure`, `congestion --congestion-mode random --seed 1`, and six-client `concurrent` runs, writing transfer rows and digest results.
* **Deterministic content (`scripts/content.py`, `tests/make_content.py`):** repeatable binary payloads plus manifest for checksum comparisons.
* **Experiment runner (`scripts/experiments.py`):** paired dynamic/static scenario rows appended to `results/data/experiments.csv`.
* **Traceability (`docs/TP-SCDS-001_TRACEABILITY.md`):** maps the official TP-SCDS-001 TC01–TC24 cases to repository evidence and status.
---
## 📊 Live Verification & Benchmarks
| Metric | Dynamic Smart Selection (Sprint 2) | Static Baseline (`CDN_MODE=static`) |
| :--- | :--- | :--- |
| **Server Selected** | **srv1** (Lowest Latency: 10 ms RTT) | **srv2** (Enforced: 40 ms RTT) |
| **Single Client Throughput**| **34.30 Mbps** (10 MB in 2.45s) | **14.48 Mbps** (10 MB in 5.79s) |
| **Multi-Stream Stress Test**| **44.45 Mbps** aggregate bandwidth across 3 concurrent streams (30 MB in 5.40s) | Single-stream bound |
| **Data Integrity** | `PASS` (SHA-256: 100% Match) | `PASS` (SHA-256: 100% Match) |
| **Peak Trunk Utilization** | **33.4% – 55.0%** captured live on `s1-s2` during active transfer | Link-bound on `s1-s3` |
---
## 🚀 Execution & Quickstart Guide

All Python commands use the same uv-managed `.venv`. Run Ryu and the dashboard as your normal Ubuntu user. Mininet needs root privileges, so launch its topology with the explicit Python interpreter from `.venv`.

### 1. Start Ryu Controller (Terminal 1)
```bash
# Clone the repository:
git clone https://github.com/SupreethProPrahlada/smaRT_CDN.git

cd ./smaRT_CDN
uv run ryu-manager controller/cdn_controller.py
```
Keep this terminal running.

### 2. Launch Mininet Topology (Terminal 2)
```bash
# Clone the repository:
git clone https://github.com/SupreethProPrahlada/smaRT_CDN.git

cd ./smaRT_CDN
sudo mn -c
sudo env "PATH=$PWD/.venv/bin:$PATH" "$PWD/.venv/bin/python" topology/topo.py
```

### 3. Start Edge Replica Servers (inside the Mininet CLI)
```text
mininet> srv1 python3 app/server.py --id srv1 --ip 10.0.0.11 &
mininet> srv2 python3 app/server.py --id srv2 --ip 10.0.0.12 &
mininet> srv3 python3 app/server.py --id srv3 --ip 10.0.0.13 &
```

### 4. Launch Live NOC Dashboard (Terminal 3)
```bash
# Clone the repository:
git clone https://github.com/SupreethProPrahlada/smaRT_CDN.git

cd ./smaRT_CDN
uv run python scripts/dashboard.py
```

### 5. Run Downloads and Integrity-Checked Stress Tests (inside Mininet CLI)
The Mininet hosts in this setup share the filesystem. Create the test file once:
```text
mininet> srv1 mkdir -p /tmp/cdn_content
mininet> srv1 dd if=/dev/urandom of=/tmp/cdn_content/test_10M.bin bs=1M count=10
mininet> srv1 sha256sum /tmp/cdn_content/test_10M.bin
```

Copy the 64-character SHA-256 digest from the output and use it in these commands:

Single download:
```text
mininet> c1 python3 app/client.py --id c1 --file test_10M.bin --hash <SHA256>
```

Six concurrent streams:
```text
mininet> c1 python3 scripts/stress_test.py --concurrency 6 --file test_10M.bin --hash <SHA256>
```

Replace `<SHA256>` with the actual digest. `PASS` means the transfer completed and its content matched the expected SHA-256 hash.

### 6. Sprint 3-4 Demo: Failover, Path Failure, Congestion and Route Map
Start the live route map (Terminal 4) and open `results/route_map.html` in a browser:
```bash
cd ~/smaRT_CDN
uv run python scripts/route_map.py
```
Create a larger file so there is time to act during a download:
```text
mininet> srv1 dd if=/dev/urandom of=/tmp/cdn_content/test_100M.bin bs=1M count=100
mininet> srv1 sha256sum /tmp/cdn_content/test_100M.bin
```
**Server failover (FR-4, FR-7).** Start a download, then kill the replica it uses (check the route map or the `[Route Decision]` log):
```text
mininet> c2 python3 app/client.py --id c2 --file test_100M.bin --hash <SHA256> &
mininet> srv1 pkill -f "server.py --id srv1"
```
About 10 s later the controller logs `[Failover] srv1 DOWN`, and the client finishes on another replica: `Download PASS ... retries=N`. Restart srv1 with the Step 3 command; the controller logs `[Failover] srv1 UP`.

**Path failure (FR-9, FR-10).** Start a download from a client that goes to srv1, then cut the primary link:
```text
mininet> c1 python3 app/client.py --id c1 --file test_100M.bin --hash <SHA256> &
mininet> link s1 s2 down
```
The controller logs `[Path] Moved c1 ... from srv1 primary to detour`. The client finishes with `PASS` and `retries=0`, meaning the same TCP connection was kept. Run `link s1 s2 up`; new srv1 flows return to the primary.

**Congestion (FR-6, FR-12).** Start a UDP sink and a download, then generate 90 Mbit/s across the primary trunk:
```text
mininet> c6 iperf -s -u &
mininet> c4 python3 app/client.py --id c4 --file test_100M.bin --hash <SHA256> &
mininet> bg python3 scripts/congestion.py --target 10.0.0.6 --mbps 90 --seconds 30
```
The controller logs `primary congested: other traffic NN% vs 0%` and moves srv1 flows to `s5`. The route map shows the detour drawn thick.

### 7. Stop the Experiment
Exit the Mininet CLI with `exit`, then clean up Mininet from a normal terminal:
```bash
sudo mn -c
```
Stop Ryu and the dashboard with `Ctrl+C` in their respective terminals.

---

## Automated Test Suite (Sprints 1–4)
`pytest` is in the `dev` dependency group, so `uv sync --all-groups` installs it. From the repository root:
```
uv run pytest -m "not integration"   # unit tests: no Ryu, Mininet or root needed
uv run pytest                        # everything, including controller integration tests (need Ryu)
```
Controller integration cases need Ryu (installed by `uv sync`); topology/system scenarios additionally require Mininet, Open vSwitch, and a safe privileged test environment. Skipped tests are not acceptance passes. See [`docs/test_plan.md`](docs/test_plan.md) for requirement traceability, real run counts, known failures, and open questions.
---
## 📁 Repository Structure
```text
smaRT_CDN/
├── config/
│   └── settings.py              # Central IP, MAC, port & link settings
├── topology/
│   └── topo.py                  # Mininet SDN topology (5 switches, 6 clients, 3 servers, bg)
├── controller/
│   ├── cdn_controller.py        # Ryu OpenFlow 1.3 VIP NAT & telemetry collector
│   ├── selector.py              # 3-Factor Cost Selection with Policy Profiles
│   └── paths.py                 # OpenFlow flow rule installation helpers
├── app/
│   ├── server.py                # 64 KB chunk server with UDP heartbeats & PING/PONG
│   └── client.py                # VIP client with real-time SHA-256 verification
├── scripts/
│   ├── dashboard.py             # Live ASCII NOC telemetry monitor
│   ├── stress_test.py           # Multi-threaded concurrent VIP stress tester
│   ├── congestion.py            # FR-12 congestion generator (iperf UDP from bg)
│   └── route_map.py             # Live HTML route map (results/route_map.html)
├── docs/
│   ├── SPRINT_0.md              # Sprint 0 architecture & foundations log
│   ├── SPRINT_1.md              # Sprint 1 baseline streaming log
│   ├── SPRINT_2.md              # Sprint 2 telemetry & selection log
│   ├── SPRINT_3.md              # Sprint 3 server failover & client resume log
│   ├── SPRINT_4.md              # Sprint 4 detour path, congestion & route map log
│   └── INTERFACE_CONTRACTS.md   # OpenFlow packet formats & interface contracts
├── results/
│   ├── live_routes.json         # Live atomic controller telemetry export
│   └── data/
│       └── client-transfers.csv # Automated download benchmark logs
```

### Replica Selection & All-Down Fallback Policy
- **Dynamic Mode (`cdn_mode="dynamic"`):** Scores all replicas with `status == "UP"` using normalized RTT latency, link utilization, and active connection count.
- **All-Servers-Down Fallback:** If all replicas report `status != "UP"`, `ServerSelector` deterministically falls back to the primary replica (`srv1`, `10.0.0.11`) so VIP NAT flows continue routing without dropping requests.

---
## 👥 Course Team Responsibilities
* **Developer 1 (Supreeth Prahlada):** Sprints 0, 1, 2 — Lead Architecture, VIP NAT, Telemetry Probing, 3-Factor Selection Engine, Profiles, Dashboard, Stress Tester. *(COMPLETED)*
* **Developer 2 (Shyam Sooraj):** Sprints 3, 4 — 10s Server Failover, Byte-Offset Client Resume, Detour Switch s5 Congestion Rerouting, HTML Route Map. *(COMPLETED)*
* **Tester (Shreyansh Tandon):** Test Scenarios (TC01 - TC18), Automated Verification Scripts, CI/CD Pipelines. *(NEXT UP)*

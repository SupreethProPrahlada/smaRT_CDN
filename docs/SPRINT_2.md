# Sprint 2: Telemetry & Smart Server Selection (Nov 23 - Nov 29)
**Owner:** Supreeth Prahlada (Developer 1)  
**Status:** COMPLETED & VERIFIED
## Objectives
Measure network latency and bandwidth live, manage switch flow lifetimes, and route clients to the best server via 3-Factor Cost scoring with live NOC monitoring and concurrency stress testing.
## Deliverables & Files Created
1. `controller/selector.py`:
   - 3-Factor Cost Algorithm: `Score = w_rtt * Norm(RTT) + w_util * Norm(Util) + w_load * Norm(Load)`
   - **Selection weights (balanced):** 40% Latency, 40% Utilization, 20% Load (`SELECTION_WEIGHTS`).
   - Note: the earlier `gaming` / `bulk_video` profile drafts were removed in the
     final selector; only the balanced weights remain, and changing them is a
     single configuration edit.
   - Static Baseline Mode (`CDN_MODE=static`): fixed mapping `c1/c4->srv1`, `c2/c5->srv2`, `c3/c6->srv3`.
2. `scripts/dashboard.py`:
   - Real-time ASCII NOC terminal dashboard displaying live RTT meters, bandwidth utilization bars, real IP mappings (`10.0.0.11-13`), optimal replica markers, and recent transfer logs from CSV.
3. `scripts/stress_test.py`:
   - Multi-threaded VIP load generator spawning concurrent streaming workers against `10.0.0.100:8000`, measuring aggregate throughput and validating streaming SHA-256 integrity.
## Files Updated / Incremented from Sprint 1
1. `controller/cdn_controller.py`:
   - Added active `probe_loop()` sending raw Ethernet frames (`0x88B5`) every 1.0s, smoothed via EMA (\alpha = 0.5).
   - Added `OFPPortStatsRequest` polling every 1.0s to measure real trunk bandwidth utilization (captured live at 33.4% - 55.0%).
   - Added UDP heartbeat frames (`STATUS`) delivered to the controller through the switch table-miss/packet-in path; no separate TCP listener is bound on 9000.
   - Integrated `ServerSelector` for dynamic smart routing with the balanced weight set.
   - Added atomic `results/live_routes.json` export and 5-second status console table.
2. `app/server.py`:
   - Added `heartbeat_loop()` daemon thread sending UDP `STATUS <id> <active_conns> <timestamp>` to `10.0.0.254:9000` every 2.0s (FR-4).
## Verification Evidence (Live Benchmarks)
- **Single Client VIP Download:**
  - `c1` downloaded 10 MB in **2.45s** (**34.30 Mbps**) routed to `srv1` with `PASS (100% Match)`.
- **Multi-Stream Concurrency Stress Test (N=3):**
  - Worker 1: 10 MB in 3.62s (23.15 Mbps) | PASS
  - Worker 2: 10 MB in 4.93s (17.01 Mbps) | PASS
  - Worker 3: 10 MB in 5.40s (14.02 Mbps) | PASS
  - **Total Transferred:** 30.00 MB in 5.40 seconds.
  - **Aggregate Bandwidth:** **44.45 Mbps**.
  - **Data Integrity:** 100% SHA-256 match across all workers.
- **Port Utilization Telemetry:**
  - Live port stats polling on switch `s1` captured utilization on `srv1` (`s1-s2`) spiking to **33.4% - 55.0%** during transfers, returning to 0.0% when idle.
- **Live NOC Dashboard:**
  - Validated live auto-refreshing UI in `scripts/dashboard.py`.

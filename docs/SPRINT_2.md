# Sprint 2: Telemetry & Smart Server Selection (Nov 23 - Nov 29)
**Owner:** Supreeth Prahlada (Developer 1)  
**Status:** COMPLETED & VERIFIED

## Objectives
Measure network latency and bandwidth live, manage switch flow lifetimes, and route clients to the best server via 3-Factor Cost scoring with configurable Policy Profiles.

## Deliverables & Files Created
1. `controller/selector.py`:
   - 3-Factor Cost Algorithm: `Score = w_rtt * Norm(RTT) + w_util * Norm(Util) + w_load * Norm(Load)`
   - **Dynamic CDN Policy Profiles:**
     - `balanced` (Default): 40% Latency, 40% Utilization, 20% Load.
     - `gaming`: 80% Latency, 10% Utilization, 10% Load (Low-latency focus).
     - `bulk_video`: 20% Latency, 70% Utilization, 10% Load (High-throughput focus).
   - Static Baseline Mode (`CDN_MODE=static`): Enforced mapping `c1->srv1`, `c2->srv2`, `c3->srv3`.
2. `scripts/dashboard.py`:
   - Real-time terminal ASCII dashboard rendering live RTT meters, link utilization, server load, and active profile weights from `results/live_routes.json`.

## Files Updated / Incremented from Sprint 1
1. `controller/cdn_controller.py`:
   - **TCAM Flow Aging:** Configured `idle_timeout=15` and `hard_timeout=60` on OpenFlow 1.3 NAT flows on switch `s1` to ensure switch flow table lifecycle management.
   - Added active `probe_loop()` sending raw Ethernet frames (`0x88B5`) every 1.0s, smoothed via EMA (\alpha = 0.5).
   - Added `OFPPortStatsRequest` polling every 1.0s to measure real trunk bandwidth utilization (captured live at 37.2%).
   - Added UDP heartbeat listener on port 9000 tracking server status and load.
   - Integrated `ServerSelector` for dynamic smart routing.
   - Added atomic `results/live_routes.json` export and 5-second status console table.
2. `app/server.py`:
   - Added `heartbeat_loop()` daemon thread sending UDP `STATUS <id> <active_conns> <timestamp>` to `10.0.0.254:9000` every 2.0s (FR-4).
   - Added diagnostic `PING / PONG` handler on port 8000.

## Verification Evidence
- Dynamic mode routed `c1` to `srv1` (lowest latency: 10ms, 39.26 Mbps).
- Static mode routed `c2` to `srv2` (14.48 Mbps on 50M link).
- Policy profiles verified for `gaming`, `bulk_video`, and `balanced` weights.
- TCAM flow entries verify automatic expiry after 15s of idle traffic.

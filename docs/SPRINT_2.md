# Sprint 2: Telemetry & Smart Server Selection (Nov 23 – Nov 29)
**Owner:** Supreeth Prahalada (Developer 1)  
**Status:** COMPLETED & VERIFIED

## Objectives
Measure network latency and bandwidth live, and route clients to the best server via 3-Factor Cost scoring.

## New Files Created
1. `controller/selector.py`:
   - Normalizes latency, port utilization, and active server connections.
   - 3-Factor formula: Score = (0.4 * Latency) + (0.4 * Utilization) + (0.2 * Load).
   - Implements Static Baseline Mode (`CDN_MODE=static`) mapping `c1->srv1`, `c2->srv2`, `c3->srv3`.

## Files Updated / Incremented from Sprint 1
1. `app/server.py`:
   - **Update:** Added `heartbeat_loop()` daemon thread sending UDP `STATUS <id> <active_conns> <timestamp>` to `10.0.0.254:9000` every 2.0s (FR-4).
   - **Update:** Added diagnostic `PING / PONG` handler on port 8000.
2. `controller/cdn_controller.py`:
   - **Update (FR-2):** Added `_probe_loop()` sending raw Ethernet frames (`0x88B5`) every 1.0s, smoothed via EMA ($\alpha = 0.5$).
   - **Update (FR-3):** Added `OFPPortStatsRequest` polling every 1.0s to measure real trunk bandwidth utilization (captured live at 37.2%).
   - **Update (FR-4):** Added UDP heartbeat listener on port 9000 tracking server status and load.
   - **Update (FR-5):** Integrated `ServerSelector` for dynamic smart routing.
   - **Update (FR-8):** Added atomic `results/live_routes.json` export and 5-second status console table.

## Verification Evidence
- Controller printed live 5s logs showing RTT, 37.2% utilization, and heartbeats.
- Dynamic mode routed `c1` to `srv1` (lowest latency: 10ms, 39.26 Mbps).
- Static mode routed `c2` to `srv2` (14.48 Mbps on 50M link).

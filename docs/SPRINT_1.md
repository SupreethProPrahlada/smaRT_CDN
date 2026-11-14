# Sprint 1: Baseline Architecture (Nov 16 – Nov 22)
**Owner:** Supreeth Prahalada (Developer 1)  
**Status:** COMPLETED & VERIFIED

## Objectives
Deliver the first end-to-end download through the Anycast Virtual IP `10.0.0.100`.

## Files Created
1. `topology/topo.py`:
   - Mininet network with 4 OpenFlow 1.3 switches (`s1-s4`), 6 clients (`c1-c6`), and 3 servers (`srv1-srv3`).
   - Shaped links: Primary (`s1-s2`, 100M/5ms), Secondary (`s1-s3`, 50M/20ms), Backup (`s1-s4`, 10M/50ms).
2. `app/server.py`:
   - Basic TCP streaming server on port 8000.
   - 64 KB chunk binary streaming with `OK <total> <remain>` header.
3. `app/client.py`:
   - Connects to VIP `10.0.0.100:8000`.
   - Downloads chunks and verifies 100% data integrity with real-time SHA-256 hash.
   - Appends download metrics to `results/data/client-transfers.csv`.
4. `controller/paths.py`:
   - Switch port mappings and OpenFlow 1.3 `add_flow` helper.
5. `controller/cdn_controller.py`:
   - Answers ARP requests for `10.0.0.100` (`VIP_MAC = 00:00:00:00:01:00`).
   - Installs two-way OpenFlow 1.3 NAT rules on switch `s1` (Client <-> VIP <-> Server).

## Verification Evidence
- Client `c1` downloaded 10 MB in 3.28s (25.53 Mbps).
- SHA-256 Checksum: `414c37d3... PASS (100% Match)`.

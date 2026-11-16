# Sprint 4: Detour Path, Congestion Rerouting & HTML Route Map
**Owner:** Shyam Sooraj (Developer 2)  
**Status:** COMPLETED & VERIFIED

## Objectives
Give srv1 a second path through a detour switch `s5`, and move live srv1 downloads onto it when the primary path fails (FR-9) or is congested by other traffic (FR-6). Return new traffic to the primary when it recovers (FR-10). Provide a congestion generator (FR-12) and a live HTML route map.

## Topology Additions (`topology/topo.py`, `config/settings.py`)
```text
c1-c6 --- s1 --(100M/5ms, s1:7 - s2:2)----------------- s2 --- srv1
           |                                            |  \
           +--(100M/10ms, s1:10 - s5:1) s5 (s5:2 - s2:3, 100M/5ms)   bg (10.0.0.20, s2:4)
```
- **Detour switch `s5`:** srv1's second path, 15 ms one way instead of 5 ms.
- **Traffic host `bg`** (`10.0.0.20`) behind s2: generates load that crosses the primary trunk without touching srv1's own link.

## Deliverables & Files Created / Updated
1. `controller/cdn_controller.py`:
   - **Path telemetry.**
     - A probe tagged `srv1d` is also sent out of s1 port 10 and returns through s5, so both srv1 paths have a measured RTT (EMA, alpha 0.5).
     - Port statistics give each path's utilization.
     - Flow statistics on s1 give each live flow's own rate.
     - **Other traffic** on a path is the link rate minus our CDN flows on it.
     - Port-status messages report link failures immediately.
     - A path is DOWN when one of its ports is down or no probe has returned for 3 s.
   - **Flow tracking.** Each client's NAT flow is recorded with its server and path; flows are forgotten when the s1 rule idles out.
   - **FR-9 path failure.**
     - When the primary goes DOWN, every live srv1 flow is moved to the detour:
       - s1's forward rule is rewritten to port 10;
       - a reverse rule for port 10 is installed;
       - s2 gets a per-client rule sending srv1's replies to s5.
     - The TCP endpoints do not change, so the download continues on the same connection.
     - s2's default egress for srv1 also switches, so srv1's heartbeats keep reaching the controller.
   - **FR-6 congestion.** When other traffic fills at least 50% more of the primary than of the detour (`CONGESTION_SHIFT`), live srv1 flows move to the detour and new srv1 flows use it.
     - A flow's own traffic is excluded, so a single busy download cannot make its own path look congested and bounce between paths.
     - A new flow is not judged until its rate has been measured.
   - **FR-10 recovery.**
     - Once the primary is up and uncongested, new srv1 flows use it again and s2's default egress reverts.
     - Live flows on the detour stay there rather than being reordered mid-transfer.
   - The selector sees srv1 measured on the path it would use, and `live_routes.json` gains `srv1_path`, `paths` and `flows`.
2. `scripts/congestion.py` (FR-12): constant-rate UDP iperf load from `bg` to a client sink.
3. `scripts/route_map.py`: writes `results/route_map.html` every second. It is a self-refreshing SVG of s1-s5 and the servers:
   - paths coloured by state and utilization;
   - srv1's active path drawn thick;
   - DOWN servers in red;
   - a table of live flows.

## Assumptions (no SRS text was available)
- The detour serves srv1 only.
- Live flows are moved off a failed or congested primary but are not moved back on recovery. A flow on a path that goes DOWN always moves to the working path, including back to the primary if the detour fails.
- Path rerouting applies in static mode too. Static mode fixes the server, not the network path.

## Verification Evidence (live Mininet run)
- **Primary link cut during a 100 MB download by c1:**
  - The flow moved from `srv1/primary` to `srv1/detour`.
  - The download finished `PASS` with `retries=0` (same TCP connection).
  - After the link was restored, a new download by c3 went to `srv1/primary`.
- **Congestion generator** (`bg` -> c6, 90 Mbit/s UDP) during a 100 MB download by c4:
  - The controller logged `primary congested: other traffic 52% vs 0%` and moved c4 to the detour.
  - The download finished `PASS` with `retries=0`.
  - When the generator stopped, srv1 returned to the primary.
- **Measured RTTs:** primary 12.7 ms, detour 32.8 ms. The sandbox added nominal delay because it has no link-delay emulation, so re-check these on a real Mininet host.
- **Automated tests:** TC53-TC57, TC62 and TC63 (path failure, detour failure, congestion, own traffic is not congestion, unmeasured new flow, recovery, detour probe) and TC59-TC61 (generator, route map). See `docs/test_plan.md`.

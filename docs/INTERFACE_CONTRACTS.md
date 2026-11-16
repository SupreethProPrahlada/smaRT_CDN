# Smart CDN Interface Contracts Specification
**Version:** 1.0 (Sprint 0 Baseline)  
**Authors:** Supreeth Prahalada (Developer 1), Shyam Sooraj (Developer 2), Shreyansh Tandon (Tester)

## 1. Network Addressing
- Virtual IP: `10.0.0.100` | MAC: `00:00:00:00:01:00`
- Clients `c1-c6`: `10.0.0.1` - `10.0.0.6`
- Servers `srv1-srv3`: `10.0.0.11` - `10.0.0.13`
- Controller HB Listener: `10.0.0.254:9000`

## 2. Protocols
- Streaming: TCP 8000 -> `GET <filename> <offset>\n` -> `OK <total> <remain>\n<binary chunks>`
- Heartbeat: UDP 9000 -> `STATUS <id> <active_connections> <timestamp>\n`
- Latency Probes: EtherType `0x88B5` every 1.0s, smoothed via EMA ($\alpha = 0.5$)

## 3. Sprint 3-4 Additions (Developer 2)
- Detour switch `s5`: s1 port 10 <-> s5 port 1, s5 port 2 <-> s2 port 3 (srv1's second path).
- Congestion host `bg`: `10.0.0.20` / `00:00:00:00:00:20` on s2 port 4.
- Detour probe: EtherType `0x88B5` with tag `srv1d`, sent out of s1 port 10 and returned by s2.
- Server failover: a server with no valid heartbeat for 10 s is `DOWN`, and its NAT flows are deleted.
- Resume: a client that has received N bytes reconnects and sends `GET <filename> <N>\n`.
  - The server answers `OK <total> <total - N>\n` and the remaining bytes.
  - The client rejects a different total.
  - `ERR` replies are final, so they are not retried.
- Server errors: `ERR Bad_Request`, `ERR Bad_Offset`, `ERR File_Not_Found <name>`.
- `results/live_routes.json` adds:
  - `srv1_path` (`primary` or `detour`);
  - `paths.{primary,detour}` with `status`, `rtt_ms`, `utilization`, `background` (other traffic, 0-1);
  - `flows[]` with `client`, `server`, `path`, `rate_mbps`.

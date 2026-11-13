# Smart CDN Interface Contracts Specification
**Version:** 1.0 (Sprint 0 Baseline)  
**Authors:** Supreeth Prahalada (Developer 1), Shyam Sooraj (Developer 2), Shreyansh Tandon (Tester)

---

## 1. Network Addressing Plan
- **Virtual IP (VIP):** `10.0.0.100` | MAC: `00:00:00:00:01:00`
- **Clients (c1-c6):** `10.0.0.1` - `10.0.0.6` | MAC: `00:00:00:00:00:01` - `00:00:00:00:00:06`
- **Servers (srv1-srv3):** `10.0.0.11` - `10.0.0.13` | MAC: `00:00:00:00:00:11` - `00:00:00:00:00:13`
- **Controller Heartbeat Listener:** `10.0.0.254:9000`

---

## 2. Content Streaming Protocol (TCP Port 8000)
- **Client Request:** `GET <filename> <byte_offset>\n`
- **Server Response Header:** `OK <total_bytes> <remaining_bytes>\n`
- **Payload:** Raw binary stream sent in chunks of 64 KB (`65536` bytes).

---

## 3. Server Heartbeat Protocol (Port 9000)
- Every server transmits every 2.0s:
  `STATUS <server_id> <active_connections> <timestamp>\n`
- If no heartbeat is received within 10.0s, controller marks server `DOWN`.

---

## 4. Telemetry Probing Protocol
- Controller sends raw Ethernet frames with EtherType `0x88B5` every 1.0s.
- Smooths RTT with EMA: RTT_smoothed = (0.5 * RTT_measured) + (0.5 * RTT_smoothed).

---

## 5. Result File Schemas
- `results/live_routes.json`: Exported every 1.0s with links, server loads, and RTTs.
- `results/data/client-transfers.csv`: Appended by clients upon download completion with TTFB, duration, throughput, and SHA-256 match status.

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

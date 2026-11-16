# Sprint 3: Server Failover & Byte-Offset Client Resume
**Owner:** Shyam Sooraj (Developer 2)  
**Status:** COMPLETED & VERIFIED

## Objectives
Detect a crashed replica within 10 seconds, remove its flows, and let clients finish their downloads on a healthy replica from the byte where they stopped (FR-4, FR-7). Close the review items deferred to this sprint: heartbeat spoofing (issue 3) and the probe return path (issue 4).

## Deliverables & Files Updated
1. `controller/cdn_controller.py`:
   - Records the time of each server's last valid heartbeat. A server silent for `HEARTBEAT_TIMEOUT` (10 s, five missed 2-second heartbeats) is marked `DOWN` and logged as `[Failover] srvN DOWN`.
   - `flush_server()` deletes the failed server's NAT rules on `s1`: forward rules by output port (its trunk, plus the detour for srv1) and reverse rules by `ipv4_src = server, tcp_src = 8000`. The client's next packet is a packet-in, so the selector steers it to a healthy replica.
   - The next valid heartbeat marks the server `UP` again (`[Failover] srvN UP`).
   - Heartbeats are accepted only from the server's own IP (issue 3), so a spoofed heartbeat cannot keep a dead server alive.
2. `app/client.py` (FR-7 retry/resume):
   - On a closed, reset or timed-out connection, the client reconnects up to `CLIENT_MAX_RETRIES` (12) times, `CLIENT_RETRY_DELAY` (1 s) apart, and sends `GET <file> <bytes received>`. 12 x 1 s outlasts the 10 s detection, so a client survives a server crash.
   - The resumed response must advertise the same total size and exactly the remaining bytes; otherwise the download fails instead of splicing two files.
   - The SHA-256 is computed over the whole file across all connections. `ERR` replies (missing file, bad offset) are not retried.
   - Prints `retries=N`. The CSV schema is unchanged.
3. `app/server.py`: traversal defence. Only a plain file name whose real path is directly inside `CONTENT_DIR` is served; `..`, `.` and symlinks that point outside are refused with `ERR Bad_Request`.
4. `config/settings.py`: `HEARTBEAT_TIMEOUT`, `CLIENT_MAX_RETRIES`, `CLIENT_RETRY_DELAY`, `CLIENT_SOCKET_TIMEOUT`.

## Assumptions (no SRS text was available)
- The "10s Server Failover" in the README is the heartbeat timeout; flows are flushed at the moment of detection.
- With all replicas DOWN, Developer 1's all-down fallback policy (route to srv1) is unchanged.

## Verification Evidence
- **Live Mininet run (srv1 killed during a 100 MB download by c2):**
  - srv1 marked DOWN 9-10 s after the kill (three runs).
  - The client resumed on **srv2** after 10 retries and finished with `PASS` (SHA-256 match).
  - srv1 was marked UP again after restart.
- **Probe return path (issue 4), live:**
  - The `OFPP_IN_PORT` rule on s2-s4 returns every probe.
  - Measured RTTs: srv1 12.6 ms, srv2 42.6 ms, srv3 102.5 ms.
  - The sandbox added the topology's nominal delay because it cannot emulate link delay.
- **Automated tests:** TC42-TC49 (resume, timeouts, size mismatch, no retry on `ERR`, retry limit, offset streaming, traversal) and TC50-TC52 (timeout and flush, recovery, spoofed heartbeat). See `docs/test_plan.md`.

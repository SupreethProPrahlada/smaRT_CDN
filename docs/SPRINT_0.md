# Sprint 0: Foundations, Architecture & Data Contracts (Nov 09 - Nov 16)
**Owner:** Supreeth Prahlada (Developer 1)  
**Status:** COMPLETED & VERIFIED

## Objectives
Establish the repository structure, global network settings, OpenFlow interface contracts, data dictionary, and reproducible dependency environment.

## Directory Structure Established
- `config/`: Global network constants, MAC/IP mappings, port definitions.
- `topology/`: Mininet software-defined network definitions.
- `controller/`: OpenFlow 1.3 Ryu SDN controller and routing logic.
- `app/`: Content server and client streaming applications.
- `docs/`: Interface contracts, data dictionary, and sprint changelogs.
- `results/`: Live metrics output and automated client transfer logs.
- `tests/`: Payload generation and verification scripts.

## Files Created
1. `config/settings.py`:
   - Anycast VIP: `10.0.0.100`, VIP MAC: `00:00:00:00:01:00`.
   - Streaming Port: `8000`, Telemetry UDP Port: `9000`, OpenFlow Port: `6653`.
   - Custom Telemetry EtherType: `0x88B5`.
   - Trunk Link Capacities & Delays:
     - Primary (`s1-s2`): 100 Mbps, 5 ms
     - Secondary (`s1-s3`): 50 Mbps, 20 ms
     - Backup (`s1-s4`): 10 Mbps, 50 ms
2. `docs/INTERFACE_CONTRACTS.md`:
   - System Interface Specification (OpenFlow 1.3 packet format, REST API endpoints, UDP telemetry packet schema).
3. `pyproject.toml` & `uv.lock`:
   - Pinned project dependencies ensuring compatibility with Ryu and Mininet.

## Verification
- Clean environment import validation of `config.settings`.
- Interface contracts approved for team integration across Developer 1, Developer 2, and Tester.

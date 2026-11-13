# Smart CDN (Software-Defined Content Delivery Network)
**Course:** Software Engineering 3K04 / 3M04 — McMaster University  
**Specification:** IEEE 830 SRS Version 0.1  
**Team Members:**
- **Developer 1:** Supreeth Prahalada (First Half: Sprints 1 & 2)
- **Developer 2:** Shyam Sooraj (Second Half: Sprints 3 & 4)
- **Tester:** Shreyansh Tandon (IEEE 829 Test Plan & Automation)

---

## Architecture Overview
Smart CDN replaces static DNS load balancing with dynamic SDN switching:
- **Anycast Virtual IP (VIP):** `10.0.0.100` handled by Ryu via OpenFlow 1.3 NAT.
- **Dynamic 3-Factor Cost Routing:** Chooses servers based on Link Latency (40%), Link Bandwidth (40%), and Server Connections (20%).
- **Fault-Tolerant Resumption:** 64 KB chunk streaming with byte-offset resume and SHA-256 validation.

---

## Quick Start (Sprint 0)
1. Activate environment:
   ```bash
   source ~/ryu-env/bin/activate

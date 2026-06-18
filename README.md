```
   ██╗   ██╗███╗   ██╗██╗██████╗  ██████╗  █████╗ ███╗   ███╗
   ██║   ██║████╗  ██║██║██╔══██╗██╔═══██╗██╔══██╗████╗ ████║
   ██║   ██║██╔██╗ ██║██║██████╔╝██║   ██║███████║██╔████╔██║
   ██║   ██║██║╚██╗██║██║██╔══██╗██║   ██║██╔══██║██║╚██╔╝██║
   ╚██████╔╝██║ ╚████║██║██║  ██║╚██████╔╝██║  ██║██║ ╚═╝ ██║
    ╚═════╝ ╚═╝  ╚═══╝╚═╝╚═╝  ╚═╝ ╚═════╝ ╚═╝  ╚═╝╚═╝     ╚═╝
                        d e f a n g e d
```

<p align="center">
  <img src="https://img.shields.io/badge/Status-Defanged_Educational_Release-blue.svg" alt="Status">
  <img src="https://img.shields.io/badge/License-CC_BY--NC--SA_4.0-green.svg" alt="License">
  <img src="https://img.shields.io/badge/Python-3.10+-yellow.svg" alt="Python">
  <img src="https://img.shields.io/badge/Hardware_Required-None-brightgreen.svg" alt="Hardware">
</p>

**UniRoam (Defanged)** is an educational release of the UniRoam autonomous robot worm framework. The staged payload chain, propagation engine, persistence mechanisms, and swarm simulator are all preserved, but all exploit primitives, cryptographic keys, and weaponized payloads have been removed.

The original UniRoam was verified end-to-end on live Unitree Go2 hardware and presented at **WISCON 2026**. This version runs entirely against the included virtual simulator. No robot hardware is needed or targeted.

## Why release this?

There is almost no public material on worm design applied to robotics and IoT. Most worm research is either academic analysis of historical specimens (Mirai, Conficker, Stuxnet) or vendor advisories that describe impact without showing architecture. UniRoam is a modern, robotics-specific worm framework that security teams can study to understand what they're defending against.

Companion artifact to the WISCON 2026 talk: **"Walk This Way: The New Era of Motorized Malware."**

## What's included

| Component | Description |
|-----------|-------------|
| **Three-Stage Payload Chain** | Staged dropper, downloader, agent architecture (stub implementations, no live payloads) |
| **Propagation Engine** | Infection tracking, rate limiting, blacklisting, loop prevention |
| **Persistence Module** | systemd, cron, rc.local, and watchdog persistence patterns as applied to embedded Linux robots |
| **OpSec Module** | Process masquerading, timestamp manipulation, log management. Documented for blue-team awareness |
| **Virtual Swarm Simulator** | In-process BLE simulation that models multi-hop robot-to-robot propagation without any hardware |
| **Hunt State Machine** | Autonomous target-seeking: search, detect, bearing, approach, infect |
| **Defense Guide** | IOCs, detection rules, YARA signatures, and incident response procedures |
| **Test Suite** | Unit and integration tests against the simulated environment |

## What's removed

All exploit primitives, keys, and operational artifacts have been stripped:

- **BLE exploit chain** replaced with `ExploitStub` that logs actions without performing them
- **SDP heap overflow** removed entirely (CVE pending, patched upstream in AWS KVS WebRTC SDK)
- **WebRTC bridge exploitation** replaced with stub. LAN discovery logic retained (port scanning only)
- **Cryptographic keys** - hardcoded AES key, IV, and BLE handshake secret zeroed out
- **Production infrastructure** - deployment scripts, domain references, TLS keys, compiled binaries all removed
- **Self-contained agent** replaced with a simulator-compatible reference agent
- **Android app** removed (contained working BLE exploit in Kotlin)
- **C2 server and dashboard** not included. Architecture is documented in [ARCHITECTURE.md](docs/ARCHITECTURE.md)


## Quick start

```bash
git clone https://github.com/a-bissell/uniroam-defanged.git
cd uniroam-defanged
python3 -m venv .venv && source .venv/bin/activate
pip install -e .

# Launch virtual swarm (8 robots, auto-propagation)
python -m simulator.run --count 8 --auto-infect SIM_000

# Run tests
python -m pytest uniroam/test_worm.py -v
```

## Architecture

```
BLE / WiFi / DDS / WebRTC (stubbed)
         │
         ▼
┌── Stage 0 ──────────┐
│  Minimal dropper     │  Target appears in C2 dashboard
│  Downloads Stage 1   │
└────────┬─────────────┘
         ▼
┌── Stage 1 ──────────┐
│  Fetch agent binary  │  Writes to disk or memfd
│  Launch detached     │
└────────┬─────────────┘
         ▼
┌── Stage 2 ──────────┐
│  C2 beacon loop      │  Jittered intervals, dead man's switch
│  Task execution      │  EXECUTE_CMD, COLLECT_INTEL, SELF_DESTRUCT
│  Persistence         │  systemd + cron + rc.local + watchdog
│  Propagation         │  BLE scan → exploit nearby robots (stubbed)
│  OpSec               │  Process masquerade, log cleaning
└──────────────────────┘
         │
         ▼
┌── C2 Server ────────┐
│  Beacon ingestion    │  (not included in this release;
│  Task dispatch       │   see ARCHITECTURE.md for design)
│  Infection graph     │
│  Web dashboard       │
│  Propagation control │
└──────────────────────┘
```

## Repository structure

```
uniroam-defanged/
  uniroam/                     # Core framework
    config.py                  # Sanitized configuration (no keys, localhost only)
    payload_builder.py         # Three-stage payload construction (stub payloads)
    propagation_engine.py      # Infection tracking, rate limiting, propagation logic
    persistence.py             # Persistence mechanism implementations
    opsec_utils.py             # Operational security patterns
    exploit_stub.py            # Stub exploit interface (replaces real exploit chain)
    hunt_state_machine.py      # Autonomous target-seeking architecture
    test_worm.py               # Test suite

  simulator/                   # Virtual swarm environment
    virtual_ble.py             # In-process BLE simulation layer
    robot_simulator.py         # Simulated robot that responds to exploits
    run.py                     # Entry point for virtual swarm demos

  docs/
    ARCHITECTURE.md            # Detailed worm architecture walkthrough
    DEFENSE_GUIDE.md           # IOCs, detection, response procedures
    TALK_REFERENCES.md         # Links to WISCON 2026 talk and related work
```

## Related projects

- **[Canopy](https://github.com/a-bissell/canopy)** - Self-hosted fleet management for Unitree robots. From-scratch MQTT broker replacing Unitree's cloud, with RBAC, audit logging, and OTA package management.
- **[UnLeash Lite](https://github.com/a-bissell/UnLeash-Lite)** - WebRTC jailbreak tool for the Unitree Go2. Right-to-repair focused.

## Acknowledgments

UniRoam builds on vulnerability research by multiple independent teams:

- **Olivier Laflamme (Boschko) and Ruikai Peng** - `programming_actuator` RCE ([CVE-2026-27509](https://nvd.nist.gov/vuln/detail/CVE-2026-27509))
- **Andreas Makris (Bin4ry), Kevin Finisterre (h0stile), and Konstantin Severov (legion1581)** - Unitree security architecture ([CVE-2025-35027](https://nvd.nist.gov/vuln/detail/CVE-2025-35027), [arXiv:2509.14139](https://arxiv.org/abs/2509.14139))
- **legion1581** - [`unitree_webrtc_connect`](https://github.com/legion1581/unitree_webrtc_connect), foundational WebRTC data channel implementation

## Disclaimer

This software is released for **security research and education only**. It contains no functional exploit code. The virtual simulator operates entirely in-process with no network or hardware interaction. See [DISCLAIMER.md](DISCLAIMER.md) for full terms.

## License

CC BY-NC-SA 4.0

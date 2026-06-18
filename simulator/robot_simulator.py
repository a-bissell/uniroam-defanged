"""
Simulated robot - models a Unitree Go2 for virtual swarm testing.

Each simulated robot:
  - Registers on the virtual BLE bus
  - Can be "exploited" (marks itself as infected)
  - Once infected, runs a simulated worm agent that beacons to C2
    and scans for other robots to infect
  - Propagation spreads through the virtual swarm exactly as it would
    on real hardware, just without BLE/WiFi/network

This allows the full worm lifecycle to be demonstrated and tested
without any robot hardware.
"""

import asyncio
import json
import logging
import random
import time
from typing import Optional

from simulator.virtual_ble import VirtualBLEDevice, get_bus

logger = logging.getLogger("simulator.robot")


class SimulatedRobot:
    """A virtual Unitree Go2 robot."""

    infection_log: list = []

    def __init__(self, robot_id: str, name: str, address: str,
                 position: tuple[float, float] = (0.0, 0.0),
                 c2_url: str = "http://127.0.0.1:8443"):
        self.robot_id = robot_id
        self.name = name
        self.address = address
        self.position = position
        self.c2_url = c2_url
        self.infected = False
        self.infection_depth = 0
        self.parent_id: Optional[str] = None
        self._agent_task: Optional[asyncio.Task] = None
        self._ble_device = VirtualBLEDevice(
            name=name,
            address=address,
            position=position,
        )

    async def register(self):
        """Register on the virtual BLE bus (makes this robot discoverable)."""
        await get_bus().register(self._ble_device)
        logger.info("Robot %s registered at position (%.1f, %.1f)",
                     self.name, *self.position)

    async def infect(self, parent_id: str = "PATIENT_ZERO",
                     depth: int = 0, rssi: Optional[int] = None):
        """Mark this robot as infected and start the worm agent."""
        if self.infected:
            return

        self.infected = True
        self.parent_id = parent_id
        self.infection_depth = depth
        self._ble_device.is_infected = True
        await get_bus().mark_infected(self.address)

        SimulatedRobot.infection_log.append({
            "parent_id": parent_id,
            "child_id": self.robot_id,
            "rssi": rssi,
            "time": time.time(),
        })

        logger.info("Robot %s INFECTED (parent=%s, depth=%d)",
                     self.name, parent_id, depth)

        # Start the simulated agent
        self._agent_task = asyncio.create_task(self._agent_loop())

    async def _agent_loop(self):
        """Simulated worm agent - beacons and propagates."""
        # Initial beacon delay (simulates Stage 0 → 1 → 2 startup)
        await asyncio.sleep(random.uniform(2.0, 5.0))

        logger.info("[%s] Agent started, beaconing to C2", self.robot_id)

        await self._beacon("initial_compromise")

        while self.infected:
            # Beacon
            await self._beacon("heartbeat")

            # Scan for nearby robots
            nearby = await get_bus().scan(self.address, timeout=1.0)
            uninfected = [d for d in nearby if not d.is_infected]

            if uninfected:
                # Pick a random uninfected target
                target = random.choice(uninfected)
                logger.info("[%s] Found uninfected target: %s (RSSI %d)",
                             self.robot_id, target.name, target.rssi)

                # Simulate exploit execution time
                await asyncio.sleep(random.uniform(1.0, 3.0))

                # "Exploit" the target - find the SimulatedRobot instance
                # via the registry and call infect()
                from simulator.run import get_robot_by_address
                target_robot = get_robot_by_address(target.address)
                if target_robot and not target_robot.infected:
                    await target_robot.infect(
                        parent_id=self.robot_id,
                        depth=self.infection_depth + 1,
                        rssi=target.rssi,
                    )

            # Jittered sleep between propagation attempts
            await asyncio.sleep(random.uniform(5.0, 15.0))

    async def _beacon(self, event_type: str):
        """Send a beacon to C2 (best-effort, non-blocking)."""
        try:
            import urllib.request
            data = json.dumps({
                "robot_id": self.robot_id,
                "hostname": self.name,
                "platform": "simulator",
                "status": "active",
                "parent_id": self.parent_id or "NONE",
                "event_type": event_type,
                "is_simulator": True,
            }).encode()
            req = urllib.request.Request(
                f"{self.c2_url}/api/v1/beacon",
                data=data,
                headers={
                    "Content-Type": "application/json",
                    "X-API-KEY": "defanged-demo-key",
                },
            )
            urllib.request.urlopen(req, timeout=5)
        except Exception:
            pass  # C2 may not be running

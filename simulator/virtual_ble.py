"""
Virtual BLE adapter - in-process simulation of BLE device discovery and
robot-to-robot communication.

This replaces the Bleak BLE library for testing and demonstration.
Multiple simulated robots register with a shared VirtualBLEBus, and
any robot's scan returns other registered robots (optionally filtered
by simulated range/RSSI).

No actual Bluetooth hardware is used.
"""

import asyncio
import random
import logging
from typing import Dict, List, Optional, Set
from dataclasses import dataclass, field

logger = logging.getLogger("simulator.virtual_ble")


@dataclass
class VirtualBLEDevice:
    name: str
    address: str
    rssi: int = -60
    is_infected: bool = False
    position: tuple[float, float] = (0.0, 0.0)  # (x, y) in meters


class VirtualBLEBus:
    """Shared bus that all simulated robots register with.

    Acts as the "ether" - when a robot scans, it sees other robots
    on the same bus, filtered by simulated distance/RSSI.
    """

    def __init__(self):
        self.devices: Dict[str, VirtualBLEDevice] = {}
        self._lock = asyncio.Lock()

    async def register(self, device: VirtualBLEDevice):
        async with self._lock:
            self.devices[device.address] = device
            logger.debug("Registered %s (%s)", device.name, device.address)

    async def unregister(self, address: str):
        async with self._lock:
            self.devices.pop(address, None)

    async def scan(self, scanner_address: str,
                   timeout: float = 5.0,
                   max_range_m: float = 30.0) -> List[VirtualBLEDevice]:
        """Return devices visible to the scanner, simulating BLE range."""
        await asyncio.sleep(min(timeout, 0.1))  # Simulate scan duration

        async with self._lock:
            scanner = self.devices.get(scanner_address)
            if not scanner:
                return []

            visible = []
            for addr, device in self.devices.items():
                if addr == scanner_address:
                    continue

                # Simulate distance-based RSSI
                dx = device.position[0] - scanner.position[0]
                dy = device.position[1] - scanner.position[1]
                distance = (dx**2 + dy**2) ** 0.5

                if distance > max_range_m:
                    continue

                # RSSI model: -40 at 1m, -6dB per doubling of distance
                if distance < 1.0:
                    rssi = -40
                else:
                    import math
                    rssi = int(-40 - 20 * math.log10(distance))

                sim_device = VirtualBLEDevice(
                    name=device.name,
                    address=device.address,
                    rssi=rssi + random.randint(-3, 3),  # Jitter
                    is_infected=device.is_infected,
                    position=device.position,
                )
                visible.append(sim_device)

            return visible

    async def mark_infected(self, address: str):
        async with self._lock:
            if address in self.devices:
                self.devices[address].is_infected = True

    def get_infection_count(self) -> int:
        return sum(1 for d in self.devices.values() if d.is_infected)

    def get_total_count(self) -> int:
        return len(self.devices)


# Global bus instance for the simulator
_bus: Optional[VirtualBLEBus] = None


def get_bus() -> VirtualBLEBus:
    global _bus
    if _bus is None:
        _bus = VirtualBLEBus()
    return _bus


def reset_bus():
    global _bus
    _bus = VirtualBLEBus()

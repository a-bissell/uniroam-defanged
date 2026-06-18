"""
Virtual swarm simulator entry point.

Launches N simulated robots on the virtual BLE bus, infects a patient
zero, and lets the worm propagate through the swarm autonomously.
No hardware or network access required.

Usage:
  python -m simulator.run --count 8 --auto-infect SIM_000
  python -m simulator.run --count 12 --interactive
"""

import argparse
import asyncio
import logging
import random
import sys
from typing import Dict, Optional

from simulator.virtual_ble import get_bus, reset_bus, VirtualBLEDevice
from simulator.robot_simulator import SimulatedRobot

logger = logging.getLogger("simulator")

# Global registry so robots can find each other by address
_robots: Dict[str, SimulatedRobot] = {}


def get_robot_by_address(address: str) -> Optional[SimulatedRobot]:
    return _robots.get(address)


async def run_simulation(count: int = 8, auto_infect: str = None,
                          spread_radius: float = 50.0):
    """Set up and run the virtual swarm."""
    reset_bus()
    _robots.clear()

    # Create robots in a random cluster
    for i in range(count):
        robot_id = f"SIM_{i:03d}"
        name = f"Go2_{robot_id}"
        address = f"AA:BB:CC:DD:EE:{i:02X}"
        position = (
            random.uniform(-spread_radius, spread_radius),
            random.uniform(-spread_radius, spread_radius),
        )
        robot = SimulatedRobot(
            robot_id=robot_id,
            name=name,
            address=address,
            position=position,
        )
        _robots[address] = robot
        await robot.register()

    logger.info("Created %d simulated robots", count)

    bus = get_bus()

    # Infect patient zero
    if auto_infect:
        target = None
        for robot in _robots.values():
            if robot.robot_id == auto_infect:
                target = robot
                break

        if target:
            logger.info("Auto-infecting patient zero: %s", auto_infect)
            await target.infect(parent_id="OPERATOR", depth=0)
        else:
            logger.error("Robot %s not found", auto_infect)
            return

    # Monitor loop
    try:
        while True:
            infected = bus.get_infection_count()
            total = bus.get_total_count()
            pct = (infected / total * 100) if total > 0 else 0

            print(f"\r  Swarm: {infected}/{total} infected ({pct:.0f}%)  ", end="")

            if infected >= total:
                print(f"\n\n  Propagation complete: {total}/{total} infected")
                break

            await asyncio.sleep(2.0)

    except KeyboardInterrupt:
        infected = bus.get_infection_count()
        total = bus.get_total_count()
        print(f"\n\n  Stopped: {infected}/{total} infected")


def main():
    parser = argparse.ArgumentParser(
        prog="python -m simulator.run",
        description="UniRoam virtual swarm simulator",
    )
    parser.add_argument("--count", type=int, default=8,
                        help="Number of simulated robots (default: 8)")
    parser.add_argument("--auto-infect", metavar="ROBOT_ID",
                        help="Robot ID to infect as patient zero (e.g. SIM_000)")
    parser.add_argument("--spread-radius", type=float, default=50.0,
                        help="Cluster radius in meters (default: 50)")
    parser.add_argument("--interactive", action="store_true",
                        help="Don't auto-infect; wait for manual trigger")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="Enable debug logging")
    args = parser.parse_args()

    level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="  %(name)s: %(message)s",
        stream=sys.stderr,
    )

    if not args.interactive and not args.auto_infect:
        args.auto_infect = "SIM_000"

    print()
    print("  UniRoam (Defanged) - Virtual Swarm Simulator")
    print(f"  Robots: {args.count}  |  Radius: {args.spread_radius}m")
    if args.auto_infect:
        print(f"  Patient zero: {args.auto_infect}")
    print()

    asyncio.run(run_simulation(
        count=args.count,
        auto_infect=args.auto_infect,
        spread_radius=args.spread_radius,
    ))


if __name__ == "__main__":
    main()

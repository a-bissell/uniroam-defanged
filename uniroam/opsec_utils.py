"""
Operational security patterns - documented for blue-team awareness.

These techniques were used by the UniRoam agent to reduce its forensic
footprint on compromised robots.  They are documented here so that
defenders know exactly what to look for.

None of these methods are novel - they are standard Linux tradecraft.
The value of documenting them in a robotics context is that embedded
Linux systems (like the Go2's Ubuntu 20.04 on aarch64) often lack
the monitoring and EDR tooling that would catch these on a server.
"""

import os
import logging

logger = logging.getLogger("uniroam.opsec")


def obfuscate_process():
    """Rename the current process to look like a system daemon.

    Technique: prctl(PR_SET_NAME) via ctypes to set the kernel task name.
    The agent chose from a list of plausible names:

      [kworker/0:1]       - looks like a kernel worker thread
      systemd-udevd       - looks like the device manager
      systemd-journald    - looks like the journal daemon
      rsyslogd            - looks like the syslog daemon
      dbus-daemon         - looks like D-Bus

    This defeats casual `ps aux` inspection but not /proc/<pid>/exe
    readlink or /proc/<pid>/maps analysis.

    Detection: compare /proc/<pid>/comm with /proc/<pid>/exe - if comm
    says 'systemd-journald' but exe points to python3, it's masquerading.
    """
    logger.info("[OPSEC] Would masquerade process name via prctl(PR_SET_NAME)")
    logger.info("  Names: [kworker/0:1], systemd-udevd, systemd-journald, etc.")
    logger.info("  Detection: readlink /proc/<pid>/exe vs /proc/<pid>/comm mismatch")


def masquerade_timestamps(path: str):
    """Set file timestamps to match a reference system binary.

    Technique: stat a trusted reference file (e.g. /usr/bin/python3)
    and apply its mtime/atime to the worm binary via os.utime().

    This prevents the worm binary from standing out in `ls -lt` output
    or in timeline analysis.  The agent tried these references in order:
      /usr/bin/python3, /bin/bash, /usr/bin/curl, /usr/bin/systemctl

    Detection: compare file creation time (if available via statx/btime)
    against modification time.  Or hash all binaries and compare against
    a known-good baseline.
    """
    logger.info("[OPSEC] Would masquerade timestamps on %s", path)
    logger.info("  Reference: /usr/bin/python3 mtime/atime")
    logger.info("  Detection: btime vs mtime discrepancy, or hash baseline comparison")


def clean_logs():
    """Remove traces from system logs.

    The production agent cleaned:
      - ~/.bash_history (and root's)
      - /var/log/auth.log (removes SSH login records)
      - /var/log/syslog (removes service start/stop records)
      - journalctl vacuum (reduces journal to recent entries only)
      - /tmp/ cleanup (removes any staging artifacts)

    Detection: gaps in log continuity.  A log that jumps from 10:00 to
    10:15 with no entries was likely cleaned.  Ship logs off-device to
    a SIEM or remote syslog server that the worm can't reach.
    """
    logger.info("[OPSEC] Would clean system logs:")
    logger.info("  - bash_history (root)")
    logger.info("  - /var/log/auth.log")
    logger.info("  - /var/log/syslog")
    logger.info("  - journalctl --vacuum-time=1h")
    logger.info("  Detection: log continuity gaps; use remote syslog")


def dead_mans_switch(last_c2_contact: float, max_hours: float = 48.0) -> bool:
    """Check whether to auto-cleanup due to lost C2 contact.

    If the agent hasn't reached C2 in max_hours, it assumes the
    operation is blown and triggers self-destruct: remove persistence,
    clean logs, and exit.  This limits the forensic window.

    Design rationale: a worm that persists indefinitely after its C2
    goes down is just creating risk for the operator with no benefit.
    The 48-hour window was chosen to survive typical network outages
    and weekend gaps while limiting exposure.

    Detection: if you take down a suspected C2 domain, the agents will
    self-clean within 48 hours.  Image the device BEFORE you block C2,
    or you lose the forensic evidence.
    """
    import time
    hours_since = (time.time() - last_c2_contact) / 3600
    triggered = hours_since > max_hours

    if triggered:
        logger.info("[OPSEC] Dead man's switch TRIGGERED (%.1fh since last C2 contact)", hours_since)
        logger.info("  Would: remove_persistence() + clean_logs() + sys.exit(0)")
    else:
        logger.debug("[OPSEC] Dead man's switch OK (%.1fh / %.1fh)", hours_since, max_hours)

    return triggered


def memfd_loader_concept():
    """Document the memfd fileless execution technique.

    The production stub loader used this flow:

      1. fd = libc.memfd_create(b"", 0)  - creates anonymous file in memory
      2. os.write(fd, stage2_bytes)       - write Stage 2 to the fd
      3. exec(open(f"/proc/self/fd/{fd}").read())  - execute from memory

    This achieved fileless execution: Stage 2 ran from an anonymous
    memory-backed fd with no corresponding file on disk.  The stub
    itself was on disk (for persistence), but the actual agent code
    existed only in memory.

    Detection:
      - /proc/<pid>/exe pointing to /memfd:<name> (deleted)
      - /proc/<pid>/fd/ containing memfd entries
      - Open file descriptors with no filesystem path
      - Volatility/memory forensics on a live image
    """
    logger.info("[OPSEC] memfd fileless execution concept:")
    logger.info("  memfd_create() -> write stage2 -> exec from /proc/self/fd/<N>")
    logger.info("  Detection: /proc/<pid>/exe -> /memfd: or deleted path")

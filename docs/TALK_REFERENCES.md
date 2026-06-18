# Talk references

## WISCON 2026

**"Walk This Way: The New Era of Motorized Malware"**
Alexander Bissell - June 11, 2026

<!-- Update with recording link after the talk -->

## Related CVEs

| CVE | Description | Researcher(s) | Status |
|-----|-------------|----------------|--------|
| [CVE-2025-35027](https://nvd.nist.gov/vuln/detail/CVE-2025-35027) | Unitree BLE WiFi config command injection | Bin4ry, h0stile, legion1581 | Patched |
| [CVE-2026-27509](https://nvd.nist.gov/vuln/detail/CVE-2026-27509) | programming_actuator unauthenticated RCE (via DDS) | Boschko, Ruikai Peng | Patched |
| CVE pending | Unauthenticated WebRTC signaling (port 9991 LAN access) | Alexander Bissell | Reported 2026-05-04 |
| CVE pending | SDP attribute-name heap overflow (AWS KVS WebRTC SDK) | Alexander Bissell | Patched upstream |

## Related research

- Bin4ry, h0stile, legion1581 - [UniPwn: Unitree Security Architecture](https://arxiv.org/abs/2509.14139)
- Boschko, Ruikai Peng - [Unitree Go2 RCE](https://boschko.ca/unitree-go2-rce/)
- legion1581 - [unitree_webrtc_connect](https://github.com/legion1581/unitree_webrtc_connect)

## Companion projects

- [Canopy](https://github.com/a-bissell/canopy) - Self-hosted fleet management (defensive)
- [UnLeash Lite](https://github.com/a-bissell/UnLeash-Lite) - WebRTC jailbreak tool (right-to-repair)
- [go2-webrtc-signaling](https://github.com/a-bissell/go2-webrtc-signaling) - WebRTC signaling vulnerability disclosure and PoCs
- [UniRoam Defanged](https://github.com/a-bissell/uniroam-defanged) - This repository (educational)

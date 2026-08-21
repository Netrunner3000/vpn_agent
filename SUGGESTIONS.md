# VPN Agent — Suggestions

Status: `IDEA` · `CONSIDERING` · `PLANNED` · `DONE` · `REJECTED`

---

| # | Suggestion | Category | Effort | Status |
|---|---|---|---|---|
| 1 | Automated kill-switch leak test in CI | security | M | DONE |
| 2 | macOS teardown, or an explicit refusal | bug | M | DONE |
| 3 | Detect an overwritten `/etc/pf.conf` after a system update | bug | S | DONE |
| 4 | Peer key rotation without a server rebuild | feature | M | DONE |
| 5 | Multi-peer management for several devices on one server | feature | L | DONE |
| 9 | Live server status — who is connected, last handshake, transfer | design | M | DONE |
| 10 | Encrypted backup and restore of a site's keys | security | M | DONE |
| 11 | Pi-hole / AdGuard on the VPN for network-wide ad blocking | feature | L | IDEA |
| 15 | WireGuard-level obfuscation (udp2raw / wstunnel) — currently only OpenVPN can be wrapped | feature | L | IDEA |
| 16 | Route the app's own IP and DNS checks through the proxy chain | feature | S | IDEA |
| 12 | Auto-connect on untrusted wifi | feature | M | IDEA |
| 13 | Dynamic DNS updater for native mode | feature | S | IDEA |
| 14 | Lab Hub launchpad entry for VPN Agent | infra | S | IDEA |
| 6 | Raspberry Pi as the documented home-server target | infra | M | CONSIDERING |
| 17 | Route the app's own IP/DNS checks through the chain, so Monitor reports the chained exit | feature | S | IDEA |
| 18 | Per-network MAC profiles, mirroring what macOS does for Wi-Fi | feature | M | IDEA |
| 19 | Auto-connect on untrusted wifi (SSID allowlist) | feature | M | IDEA |
| 20 | Lab Hub launchpad entry for VPN Agent | infra | S | IDEA |
| 7 | Connection health graph — throughput, handshake age | design | M | IDEA |
| 8 | Per-app split tunnelling | feature | XL | IDEA |

## Done

| Suggestion | When |
|---|---|
| Two deployment modes, two protocols on one server | Aug 2026 |
| Kill switch, with pf-semantics leak tests | Aug 2026 |
| Live installer validation on Debian 12 — found the `pipefail`/SIGPIPE bug | Aug 2026 |
| Test suite (177), with regression guards for every shipped bug | Aug 2026 |
| macOS teardown, and `/etc/pf.conf` overwrite detection | Aug 2026 |
| Peer key rotation without a server rebuild | Aug 2026 |
| Live server status: handshake age, transfer, connected devices | Aug 2026 |
| Encrypted site backup and restore (scrypt + AES-256-GCM) | Aug 2026 |
| Privacy tab: Tor client, proxy chains, MAC randomisation | Aug 2026 |
| Server obfuscation: stunnel TLS wrap and Tor onion service | Aug 2026 |
| In-app docs: **? Docs** in the title bar, **? Server Guide** on the Build Server tab, tooltips on every control with a global toggle | Aug 2026 |

## Rejected

| Suggestion | Why |
|---|---|
| Marketing this as anonymity | It is not, and saying so would be the worst bug in the project |
| Guessing the package manager on non-apt systems | Better to stop than to half-install |
| Relying on proxychains for the app's own traffic | SIP strips its injection from every Apple-shipped binary, so it would fail silently on the one platform this app runs on. The chain is spoken natively instead. |
| Shipping obfuscation binaries (udp2raw, wstunnel) to the server | They come from GitHub releases, not apt. Pulling an unsigned binary onto a box that holds your keys is a worse trade than the obfuscation is worth. stunnel and tor are both in Debian. |
| Bundling Tor inside the .app | It would need updating on our release cadence rather than Homebrew's, and a stale Tor is a security problem rather than an inconvenience. |

## The one to remember

`producer | grep -q pattern` under `set -o pipefail` reports **141** (SIGPIPE), because
grep exits on its first match and the producer dies writing into a closed pipe. The test
therefore reads **false exactly when the pattern matched**. It shipped, skipped OpenVPN on
a host where it was installed, and was invisible to `bash -n` and to running the pipeline
by hand. Guarded now by `test_unit_detection_does_not_use_a_pipeline`, which forbids the
shape rather than the symptom.

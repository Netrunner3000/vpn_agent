# VPN Agent — TODO

> **Legend** — priority `P0` critical · `P1` high · `P2` normal · `P3` low
> categories `security` `bug` `feature` `performance` `design` `docs` `testing` `infra` `research`
> owner `@me` (needs you — accounts, keys, money, judgement) · `@ai` (Claude can do this)

---

## v2 — current

- [x] `P1` `security` `@ai` Kill-switch failure test — `tests/test_v2_hardening.py` evaluates the generated ruleset the way pf does and asserts nothing escapes a physical interface, including with the tunnel gone. Verified by mutation: punching a hole for `en0` fails three tests.
- [x] `P1` `bug` `@ai` macOS teardown implemented — cuts our block out of `/etc/pf.conf` by marker so Apple's anchors survive, brings the tunnel down, removes configs
- [x] `P2` `bug` `@ai` `/etc/pf.conf` overwrite detected on launch; a deployed native site whose marker has vanished warns that NAT is gone and the tunnel will carry nothing
- [x] `P2` `feature` `@ai` Key rotation — **Rotate Keys** reissues a peer's keys and certificate, keeping its address, so deploy applies it with `wg syncconf` and other devices' tunnels stay up
- [x] `P2` `testing` `@ai` The installer is executed against a non-apt host (this Mac) and asserted to stop rather than guess
- [x] `P3` `docs` `@ai` "Which mode do I want" decision tree at the top of the README
- [x] `P1` `feature` `@ai` Tor client (127.0.0.1:9250), verification against check.torproject.org, NEWNYM
- [x] `P1` `feature` `@ai` Proxy chains with a native SOCKS4a/5/HTTP-CONNECT client, so testing works despite macOS SIP
- [x] `P2` `feature` `@ai` Obfuscation: stunnel TLS wrap (OpenVPN retreats to loopback) and a Tor onion service for CGNAT
- [x] `P2` `feature` `@ai` MAC randomisation, locally-administered or vendor-preserving, read back to catch adapters that ignore it
- [x] `P2` `docs` `@ai` PRIVACY_GUIDE.md, in-app guide, and a **? Privacy Guide** button

### Not yet exercised live — all @me

Everything left needs a real host, a password, or a `brew install`. None of it is code.

- [ ] `P1` `security` `@me` **Arm the kill switch once** with a tunnel up. Verified so far by
  rule generation, `pfctl -n` parse checks, and tests that evaluate the ruleset the way pf
  does — but never actually loaded. Keep the recovery command in a second terminal:
  `sudo pfctl -a vpn-agent-killswitch -F all && sudo pfctl -F all -f /etc/pf.conf`
- [ ] `P1` `testing` `@me` **Deploy with `obfuscation = stunnel`** and confirm a client
  connects through it. Config generation is tested; the deploy path is not.
- [ ] `P2` `testing` `@me` **Deploy with an onion service** and confirm the address is
  published and reachable.
- [ ] `P2` `testing` `@me` **Run a native macOS teardown once**, to confirm the
  `/etc/pf.conf` surgery behaves on a real file.
- [ ] `P2` `testing` `@me` **`brew install tor`**, then exercise Start / Verify / New Circuit.
- [ ] `P0` `security` `@me` **Understand what this is not.** The VPS is rented in your name
  and paid with your card. It hides traffic from your ISP and your IP from sites you visit —
  not from a subpoena to the hosting provider. For anonymity the tool is Tor Browser.

> The pattern worth remembering: the one bug that reached a real server —
> `grep -q` inverting under `pipefail` — was invisible to `bash -n`, to running the
> pipeline by hand, and to every test that did not actually deploy. Live-test the
> five items above before trusting them.

## v3 — later

- [ ] `P2` `feature` `@me` A Raspberry Pi as the home server target — macOS is a poor always-on server since it sleeps
- [x] `P2` `feature` `@ai` Multi-peer management UI — done in v2: the Build Server tab adds,
  disables, removes and rotates any number of devices, each with its own keypair, pre-shared
  key, address and certificate. (The kill switch stays per-Mac rather than per-peer; it is a
  local firewall, so there is nothing per-device to configure.)
- [ ] `P3` `feature` `@ai` Connection health graph — throughput and handshake age over time
- [ ] `P3` `research` `@ai` Whether a single-user VPS fingerprint can be meaningfully reduced, or whether that trade is simply the cost of not trusting a VPN company

## Honest limitations — documented, not bugs

- A single-user VPS is a fingerprint. Commercial VPNs mix hundreds of users behind one IP; yours has exactly one.
- The installer targets Debian/Ubuntu, checks for `apt-get`, and stops rather than guessing on anything else.
- The site file is the only copy of the server and CA keys. **Backup** writes an encrypted copy; without one, losing it is unrecoverable.
- macOS is a poor always-on server: it sleeps, and system updates rewrite `/etc/pf.conf`. The app warns when that happens, but a Raspberry Pi is the better host.
- Proxy chains carry TCP only; DNS and QUIC bypass them. proxychains-ng is largely defeated on macOS by SIP.
- A MAC address travels one hop. macOS already randomises Wi-Fi per network, so this is really for Ethernet and USB adapters.
- Stacking VPN + Tor + chains is not anonymity. For that the tool is Tor Browser.

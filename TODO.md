# VPN Agent — TODO

> **Legend** — priority `P0` critical · `P1` high · `P2` normal · `P3` low
> categories `security` `bug` `feature` `performance` `design` `docs` `testing` `infra` `research`
> owner `@me` (needs you — accounts, keys, money, judgement) · `@ai` (Claude can do this)

---

## v2 — current

- [ ] `P0` `security` `@me` **Understand what this is not.** The VPS is rented in your name and paid with your card. It hides traffic from your ISP and your IP from sites you visit — not from a subpoena to the hosting provider. For anonymity the tool is Tor.
- [x] `P1` `security` `@ai` Kill-switch failure test — `tests/test_v2_hardening.py` evaluates the generated ruleset the way pf does and asserts nothing escapes a physical interface, including with the tunnel gone. Verified by mutation: punching a hole for `en0` fails three tests.
- [x] `P1` `bug` `@ai` macOS teardown implemented — cuts our block out of `/etc/pf.conf` by marker so Apple's anchors survive, brings the tunnel down, removes configs
- [x] `P2` `bug` `@ai` `/etc/pf.conf` overwrite detected on launch; a deployed native site whose marker has vanished warns that NAT is gone and the tunnel will carry nothing
- [x] `P2` `feature` `@ai` Key rotation — **Rotate Keys** reissues a peer's keys and certificate, keeping its address, so deploy applies it with `wg syncconf` and other devices' tunnels stay up
- [x] `P2` `testing` `@ai` The installer is executed against a non-apt host (this Mac) and asserted to stop rather than guess
- [x] `P3` `docs` `@ai` "Which mode do I want" decision tree at the top of the README

### Not yet exercised live

- [ ] `P1` `security` `@me` Arm the kill switch once with a tunnel up. It needs an admin password and briefly interrupts networking, so it has only been verified by rule generation, `pfctl -n` parse checks and the pf semantics tests. Keep the recovery command in a second terminal: `sudo pfctl -a vpn-agent-killswitch -F all && sudo pfctl -F all -f /etc/pf.conf`
- [ ] `P2` `testing` `@me` Run a native macOS teardown once, to confirm the `/etc/pf.conf` surgery behaves on a real file

## v3 — later

- [ ] `P2` `feature` `@me` A Raspberry Pi as the home server target — macOS is a poor always-on server since it sleeps
- [ ] `P2` `feature` `@ai` Multi-peer management UI: several devices on one server, each with its own key and kill switch
- [ ] `P3` `feature` `@ai` Connection health graph — throughput and handshake age over time
- [ ] `P3` `research` `@ai` Whether a single-user VPS fingerprint can be meaningfully reduced, or whether that trade is simply the cost of not trusting a VPN company

## Honest limitations — documented, not bugs

- A single-user VPS is a fingerprint. Commercial VPNs mix hundreds of users behind one IP; yours has exactly one.
- The installer targets Debian/Ubuntu, checks for `apt-get`, and stops rather than guessing on anything else.
- The site file is the only copy of the server and CA keys. **Backup** writes an encrypted copy; without one, losing it is unrecoverable.
- macOS is a poor always-on server: it sleeps, and system updates rewrite `/etc/pf.conf`. The app warns when that happens, but a Raspberry Pi is the better host.

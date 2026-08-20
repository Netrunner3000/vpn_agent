# VPN Agent — v2 live verification runbook

The three v2 items in `TODO.md` that are `@me` (need you, an admin password, and
live networking). Everything else in v2 is code-complete and covered by the test
suite; these are the ones only a real run can close.

> **Keep this in a SECOND terminal the whole time — the one command that undoes
> everything the kill switch does:**
> ```bash
> sudo pfctl -a vpn-agent-killswitch -F all && sudo pfctl -F all -f /etc/pf.conf
> ```
> If the network ever goes dead while armed, run that and you're back.

---

## 1 · Kill switch — confirm armed, then prove fail-closed  (`P1 security`)

### 1a. Ground truth — is *this app's* kill switch actually armed?

The app infers armed-ness from two markers; the pf anchor itself needs root to read.

```bash
# App's view (no root): reads the armed marker + /etc/pf.conf registration
cd ~/Documents/lab/active/vpn_agent && .venv/bin/python -c \
  "from services import killswitch as ks; s=ks.status(); print('armed',s.armed,'| registered',s.registered,'| tunnel',s.interfaces)"

# pf's view (root) — the real answer
sudo pfctl -a vpn-agent-killswitch -s rules      # armed = lists block/pass rules; empty = not armed
sudo pfctl -s info | head -1                      # want: Status: Enabled
```

If the anchor is empty: arm it from the app first — **Monitor tab → Arm kill
switch** — with a tunnel up. Arming writes the `# >>> vpn-agent-killswitch >>>`
block into `/etc/pf.conf` and a `killswitch.armed` file under
`~/Library/Application Support/VPN Agent/`; if either is missing, the arm didn't
complete (usually the admin prompt was dismissed → it failed *open*).

### 1b. Fail-closed proof — the actual test

**Prereq:** this app's WireGuard tunnel is UP and the kill switch is ARMED.

```bash
# 1. Tunnel up + armed → traffic must exit at the SERVER
curl -s --max-time 8 https://api.ipify.org; echo          # expect: your VPS IP
scutil --dns | grep -m3 nameserver                        # DNS should be the tunnel's, not your ISP's

# 2. Drop ONLY the tunnel, leave the switch armed.
#    In the app: Disconnect.  (equivalently: sudo wg-quick down <iface>)

# 3. Re-check — THIS is the whole point of the item:
curl -s --max-time 8 https://api.ipify.org; echo
#    PASS  → times out / empty  (failed CLOSED — protected)
#    FAIL  → shows your ISP's home IP  (leaked — the bug this test hunts)

# 4. Bring the tunnel back up (app: Connect / sudo wg-quick up <iface>) → IP is the server again.
```

Then **Disarm** from the app. Note: disarm flushes the anchor rules and removes
the `killswitch.armed` file, but leaves the (now-empty) registration line in
`/etc/pf.conf` — harmless. To strip that too, run the recovery command above.

| Step | Expected |
|---|---|
| Armed + tunnel up | public IP = server, DNS = tunnel |
| Armed + tunnel down | **no** connectivity (curl times out) |
| Disarmed | normal browsing, ISP IP |

---

## 2 · Native macOS teardown — `/etc/pf.conf` surgery  (`P2 testing`)

Confirms the teardown cuts *our* block out of `/etc/pf.conf` by marker and leaves
Apple's anchors untouched. You currently have **no native site deployed on this
Mac**, so pick a path:

### Path A — surgery-only proof (recommended: no deploy, zero risk)

Exercises the exact `awk` line from `server/bootstrap.py: macos_teardown_script()`
against a *copy* of your real `/etc/pf.conf`. Nothing touches the live file.

```bash
cp /etc/pf.conf /tmp/pf.test.conf
printf '# >>> vpn-agent >>>\nanchor "vpn-agent"\nload anchor "vpn-agent" from "/etc/pf.anchors/vpn-agent"\n# <<< vpn-agent <<<\n' >> /tmp/pf.test.conf

awk '/vpn-agent >>>/ { skip = 1 } skip == 0 { print } /vpn-agent <<</ { skip = 0 }' \
    /tmp/pf.test.conf > /tmp/pf.after.conf

grep -c 'vpn-agent' /tmp/pf.after.conf        # expect 0  (our block gone)
grep -c 'com.apple' /tmp/pf.after.conf        # expect unchanged (Apple anchors kept)
diff /etc/pf.conf /tmp/pf.after.conf && echo "byte-identical to original ✓"
sudo pfctl -n -f /tmp/pf.after.conf           # parses clean, applies nothing
rm -f /tmp/pf.test.conf /tmp/pf.after.conf
```
*(Already run once on 2026-08-20: block removed, all 7 Apple anchors preserved,
result byte-identical to the original.)*

### Path B — full end-to-end (only if you want the whole path)

Invasive: deploys a real native server on this Mac (brew installs WireGuard/OpenVPN,
writes `/etc/pf.conf`, enables IP forwarding), then removes it.

```bash
cd ~/Documents/lab/active/vpn_agent
.venv/bin/python -m server.cli init home --mode native --host <your-ddns-hostname>
# ...deploy the site from the GUI or CLI, confirm the tunnel works...
.venv/bin/python -m server.cli teardown home      # or the GUI's "Remove server"
# Confirm afterwards:
grep -c vpn-agent /etc/pf.conf                     # expect 0
ls -l /etc/pf.conf.vpn-agent-teardown.bak          # backup was written
sudo pfctl -sr >/dev/null && echo "pf reloaded clean"
```

---

## 3 · "Understand what this is not"  (`P0 security` — awareness, not code)

The VPS is rented in your name and paid with your card. The tool hides your
traffic from your ISP and your IP from the sites you visit — **not** from a
subpoena to the hosting provider. For anonymity the tool is Tor. Acknowledge and
the item is closed.

---

## When done

Report the results and I'll close the items in `TODO.md` / `SUGGESTIONS.md` and
add a dated changelog entry. Until 1b actually shows fail-closed on a live drop,
the P1 box stays unchecked.

# VPN Agent

A PySide6 desktop app for running a VPN you own end to end. It has two halves:

- **Monitor** — watches a tunnel from this Mac: public IP, DNS leaks, latency,
  packet loss, connect / disconnect / restart, a background health monitor that
  warns when a tunnel drops, and a **kill switch** that makes a dropped tunnel
  fail closed instead of silently reverting to your ISP.
- **Build Server** — creates the server at the far end of that tunnel. Generates
  the keys, renders the configs, installs **WireGuard** and an **OpenVPN
  TCP/443 fallback** on a target host, sets up NAT, and verifies the result.

Unlike a commercial VPN, no third party sits in the path. You generate every key
and hold the certificate authority.

## Two deployment modes

|  | **Remote** | **Native** |
|---|---|---|
| Runs on | a rented VPS, over SSH | hardware you own on your LAN |
| Traffic exits at | the server | your own home ISP |
| Hides your IP | yes | **no** |
| Changes apparent country | yes | **no** |
| Good for | privacy, geo-shifting, public wifi | reaching your home network from outside |
| Default routing | full tunnel | split tunnel |

Native mode not changing your apparent location is the most common
misunderstanding — its exit IP *is* your home IP. If you want privacy from the
sites you visit, use remote.

## Two protocols, one server

**WireGuard** (UDP 51820) is the one you use — fast, modern, reconnects
instantly when you move between wifi and cellular.

**OpenVPN** (TCP 443) exists for one situation: networks that pass only what
looks like web browsing. Hotel wifi, corporate guest networks and some airports
block UDP outright, and there WireGuard simply cannot connect. Port 443 plus
`tls-crypt` means a scanner probing the port gets no OpenVPN handshake to
fingerprint. It is slower — reach for it only when the tunnel will not come up.

## Kill switch

Without one, a tunnel that dies takes your protection with it and says nothing:
macOS falls back to the ordinary route and traffic carries on over your ISP,
unencrypted, looking exactly as it did a second earlier.

Armed, everything that is not the tunnel is blocked — so a dead tunnel means no
traffic rather than unprotected traffic. Loopback, DHCP, your LAN, and reaching
the VPN server itself stay open, the last so the tunnel can always reconnect.

Rules load into a private pf anchor, never the main ruleset, so they cannot
disturb the anchors macOS ships. It deliberately **does not survive a reboot** —
a kill switch that comes back on its own leaves you with no network and no
explanation.

Recovery needs neither the app nor Python, and is printed every time it arms:

```bash
sudo pfctl -a vpn-agent-killswitch -F all && sudo pfctl -F all -f /etc/pf.conf
```

## Where the keys live

Site state — every private key, the certificate authority, and the device list —
is stored at:

```
~/Library/Application Support/VPN Agent/sites/<name>.json
```

Directory `700`, file `600`. The app refuses to load a site file that has become
readable by anyone else rather than loading it and hoping.

This is deliberately **outside the repo**, so it can never be swept into a
commit, and **outside the .app bundle**, since writing there would break the code
signature and a reinstall would wipe it. Point `VPN_AGENT_STATE_DIR` elsewhere —
an encrypted volume, say — to move it.

> That file is the **only copy** of the server and CA private keys. Lose it and
> every config you have issued is permanently dead, with no way to reissue.
> Back it up somewhere encrypted.

Keys are generated here and never on the server, which never sees the CA key at
all. If the VPS is compromised, the attacker sees the traffic it is carrying but
cannot mint new client certificates or impersonate the site after you rebuild it.

## Setup

```bash
uv venv && uv pip install -r requirements.txt
```

`wireguard-tools` (`brew install wireguard-tools`) is needed only to *connect*
from this Mac. Building a server does not require it — key generation happens in
Python, so you can set up a VPS from a machine with no WireGuard installed.

## Running

```bash
source .venv/bin/activate
python main.py
```

Verify a build — key generation, certificate issuance, QR rendering, bundled
assets:

```bash
python main.py --selftest
```

Build the standalone app. This runs the self-test against the packaged binary
and refuses to ship a bundle that fails it:

```bash
./build_app.sh --install
```

## Command line

Everything the GUI does is scriptable, sharing the same site files:

```bash
python -m server.cli init "Berlin VPS" --mode remote --host 1.2.3.4 --ssh root@1.2.3.4
python -m server.cli peer add "Berlin VPS" iphone
python -m server.cli check "Berlin VPS"
python -m server.cli deploy "Berlin VPS"
python -m server.cli export "Berlin VPS" --peer iphone --qr
```

`script` prints the installer without running it, and `deploy --dry-run` renders
what would be executed. Both are worth reading before letting anything near a
server.

## Layout

```
app/        Qt UI — gui.py (Monitor), server_tab.py (Build Server), guides
server/     the server-building engine, no Qt dependency
  keys.py       X25519 keypairs, pre-shared keys, tls-crypt
  pki.py        certificate authority on P-256
  render.py     the four config formats
  bootstrap.py  generates the installer script
  deploy.py     streams it over SSH, or runs it locally
  cli.py        command-line front end
services/   client-side monitoring — public IP, DNS, latency, health
docs/       GUIDE.md (Monitor), SERVER_GUIDE.md (Build Server)
```

The installer is streamed to the target on stdin and never written to its disk —
it embeds private keys, and a file in `/tmp` lives long enough for anything else
on the box to read it. It is idempotent, so adding a device is just another
deploy.

## Documentation

- [docs/GUIDE.md](docs/GUIDE.md) — the Monitor half, plus the manual VPS
  procedure the Build Server tab automates
- [docs/SERVER_GUIDE.md](docs/SERVER_GUIDE.md) — building, deploying and
  operating a server

Both are readable in the app: **? Docs** in the title bar, **? Server Guide** on
the Build Server tab. Every control has a tooltip explaining what it does and
why; the **Tooltips** toggle turns them all off.

## Honest limitations

- **This is not anonymity.** Your VPS is rented in your name and paid with your
  card. It hides your traffic from your ISP and your IP from the sites you visit,
  not from a subpoena to the hosting provider. For anonymity the tool is Tor.
- **A single-user VPS is a fingerprint.** Commercial VPNs mix hundreds of users
  behind one IP; yours has exactly one. That trades crowd-blending for not having
  to trust a VPN company.
- **The installer targets Debian/Ubuntu**, checks for `apt-get`, and stops rather
  than guessing on anything else.
- **macOS is a poor always-on server** — it sleeps, and the installer appends to
  `/etc/pf.conf`, which system updates overwrite. A Raspberry Pi is the better
  home server.
- **Teardown is Linux-only.**

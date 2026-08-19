# VPN Agent

A PySide6 desktop app for running a VPN you own end to end. It has two halves:

- **Monitor** — watches a tunnel from this Mac: public IP, DNS leaks, latency,
  packet loss, connect / disconnect / restart, a background health monitor that
  warns when a tunnel drops, and a **kill switch** that makes a dropped tunnel
  fail closed instead of silently reverting to your ISP.
- **Build Server** — creates the server at the far end of that tunnel. Generates
  the keys, renders the configs, installs **WireGuard** and an **OpenVPN
  TCP/443 fallback** on a target host, sets up NAT, and verifies the result.
- **Privacy** — a local **Tor** client, **proxy chains**, and **MAC address**
  randomisation, plus per-server **obfuscation** (stunnel, onion service).

Unlike a commercial VPN, no third party sits in the path. You generate every key
and hold the certificate authority.

## Which mode do I want?

```
Do you want to hide your IP, or look like you are somewhere else?
│
├─ YES ──► REMOTE.  Rent a small VPS (~€4/mo), deploy over SSH.
│          Traffic exits at the server, so that becomes your apparent
│          location. This is what "get a VPN" normally means.
│
└─ NO ───► Do you want to reach your home network from outside —
           NAS, printer, router — over an encrypted link?
           │
           ├─ YES ──► NATIVE.  Run it on a Raspberry Pi at home.
           │          Needs a port forward and dynamic DNS.
           │
           └─ NO ───► You may not need this tool.
```

**The one thing people get backwards:** native mode does *not* hide your IP and
does *not* change your apparent country. Its exit IP **is** your home IP. It buys
you an encrypted way *in*, not a new way *out*.

Both modes install WireGuard *and* an OpenVPN TCP/443 fallback, so you keep a way
through networks that block UDP.

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

## Privacy tools

Four tools that are often stacked in the belief the total is anonymity. It is
not — each narrows a different, specific exposure:

| Tool | Hides you from | Does **not** help with |
|---|---|---|
| VPN | your ISP, and the sites you visit | the VPS provider, or a subpoena to them |
| Tor | the site learning your server's IP | the exit node reading unencrypted traffic |
| Proxy chain | any single proxy knowing both ends | UDP, which bypasses it entirely |
| Obfuscation | a network that blocks or fingerprints VPNs | anyone who already has your traffic |
| MAC change | the wifi you are joined to | anything past the first router |

**For real anonymity the tool is Tor Browser** — its value is the fingerprinting
defences, and those live in the browser, not the network underneath.

Three things worth knowing before relying on any of it:

- **Chains carry TCP only.** UDP, and therefore ordinary DNS and QUIC, does not
  traverse SOCKS. Test Chain speaks SOCKS natively rather than shelling out, so
  it is a genuine end-to-end check.
- **proxychains-ng barely works on macOS.** SIP strips its library injection from
  everything Apple ships, so `/usr/bin/curl` connects directly while looking like
  it worked. The generated config carries the caveat.
- **macOS already randomises your Wi-Fi MAC** per network. This is for Ethernet
  and USB adapters, which get no such treatment.

Obfuscation is set per server on **Build Server**. `stunnel` fronts OpenVPN with
a real TLS listener on 443 and moves OpenVPN to loopback — so the direct port
cannot be used to bypass it. An **onion service** publishes the endpoint through
Tor, which is the only answer to CGNAT: with no reachable public address, no
amount of dynamic DNS helps.

See [docs/PRIVACY_GUIDE.md](docs/PRIVACY_GUIDE.md).

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

Use **Backup** rather than copying the file by hand: it writes a passphrase-encrypted
copy (scrypt + AES-256-GCM) that authenticates as well as encrypts, so a corrupted or
altered backup is refused instead of restoring a subtly wrong site. The passphrase is
never stored. This is the supported way to carry a server to a second machine —
copying the raw file leaves an unprotected CA key wherever you put it.

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

## Tests

```bash
uv pip install -r requirements-dev.txt
pytest
```

220 tests in about six seconds — no network, no server, no Qt. Most of that time
is scrypt, which the backup tests exercise for real rather than stubbing; making it
fast would mean making it weak. Every test runs against a throwaway state directory,
so the suite can never touch the real site files and their keys.

Several assertions are regression guards for bugs that actually shipped, and
each was verified by reintroducing the bug and confirming the test fails:

| Guard | The bug it caught |
|---|---|
| `test_unit_detection_does_not_use_a_pipeline` | `\| grep -q` under `set -o pipefail` inverts its result via SIGPIPE — OpenVPN was skipped on a host where it was installed |
| `test_openvpn_blocks_ipv6_on_a_v4_only_full_tunnel` | pushing `redirect-gateway ipv6` into a tunnel with no IPv6 address black-holed client v6 traffic |
| `test_protocols_are_paired_with_their_own_ports` | the kill switch opened TCP/51820 and UDP/443, holes serving nothing |
| `test_icmp_to_the_endpoint_stays_open` | arming the kill switch made the app report its own server unreachable |
| `test_no_packet_escapes_when_the_tunnel_drops` | evaluates the pf ruleset the way pf would, and asserts nothing leaks once the tunnel is gone |

The RFC 7748 vector in `test_keys.py` is the load-bearing one: it proves the
app's X25519 output is byte-identical to `wg pubkey`. If that ever breaks, every
key ever generated is wrong and no tunnel handshakes.

## Command line

Everything the GUI does is scriptable, sharing the same site files:

```bash
python -m server.cli init "Berlin VPS" --mode remote --host 1.2.3.4 --ssh root@1.2.3.4
python -m server.cli peer add "Berlin VPS" iphone
python -m server.cli check "Berlin VPS"
python -m server.cli deploy "Berlin VPS"
python -m server.cli export "Berlin VPS" --peer iphone --qr
python -m server.cli status "Berlin VPS"          # who is actually connected
python -m server.cli backup "Berlin VPS"          # encrypted copy of the keys
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
  backup.py     encrypted site export/import
  obfuscation.py stunnel TLS wrap and Tor onion service
  cli.py        command-line front end
services/   client-side — public IP, DNS, latency, health, kill switch
  tor.py        local Tor daemon, verification, new circuits
  proxychain.py chained proxies, tested natively rather than via proxychains
  socks_client.py  SOCKS4a/5/HTTP-CONNECT, written here to allow chaining
  macaddr.py    hardware address randomisation
tests/      pytest suite, incl. regression guards for shipped bugs
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
- [docs/PRIVACY_GUIDE.md](docs/PRIVACY_GUIDE.md) — Tor, proxy chains,
  obfuscation and MAC addresses, and what each is actually for

All three are readable in the app: **? Docs** in the title bar, **? Server Guide**
on the Build Server tab, **? Privacy Guide** on the Privacy tab. Every control has a tooltip explaining what it does and
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
- **The obfuscation and onion paths are not live-tested.** Config generation is
  covered by tests; the deploy path for those two has not been run against a real
  server.
- **macOS is a poor always-on server** — it sleeps, and the installer appends to
  `/etc/pf.conf`, which system updates overwrite. The app detects that and warns
  on the next launch, but a Raspberry Pi is still the better home server.

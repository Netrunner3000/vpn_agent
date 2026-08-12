# Building Your Own VPN — Server Guide

The **Build Server** tab creates the thing at the far end of the tunnel. The Monitor
tab watches a connection; this half makes the server that connection goes to.

Everything here is yours: you generate the keys, you hold the certificate authority,
and no third party is in the path. That is the whole point — a commercial VPN moves
your trust from your ISP to a company you know less about. This moves it to a machine
you rent or own.

---

## Contents

1. [Which mode do I want?](#1-which-mode-do-i-want)
2. [WireGuard and the OpenVPN fallback](#2-wireguard-and-the-openvpn-fallback)
3. [Getting a server](#3-getting-a-server)
4. [Building it, step by step](#4-building-it-step-by-step)
5. [Getting configs onto devices](#5-getting-configs-onto-devices)
6. [Adding and removing devices](#6-adding-and-removing-devices)
7. [Where your keys live](#7-where-your-keys-live)
8. [What the installer actually does](#8-what-the-installer-actually-does)
9. [Running it from the command line](#9-running-it-from-the-command-line)
10. [Troubleshooting](#10-troubleshooting)
11. [Honest limitations](#11-honest-limitations)

---

## 1. Which mode do I want?

This is the one decision that changes everything downstream, and it is easy to get
backwards.

### Remote — a rented host

The server runs on a VPS somewhere. Your traffic goes into the tunnel, comes out at
the VPS, and reaches the internet from **the VPS's IP address**.

Use this when you want to:
- hide your home IP from the sites you visit
- appear to be in another country
- be safe on hotel, airport or café wifi

### Native — hardware you own

The server runs on a Raspberry Pi, a spare Linux box, or this Mac, sitting on your
own LAN. Traffic goes into the tunnel and comes out at **your own home ISP
connection**.

Use this when you want to:
- reach your home NAS, printer, or router securely from outside
- browse through your home connection while travelling
- keep everything on hardware you physically possess

> **The trap:** native mode does **not** hide your IP and does **not** change your
> apparent country. Your exit IP *is* your home IP. If your goal is privacy from the
> sites you visit, or geo-shifting, native mode gives you none of it. Use remote.

Because of that, the two modes get different routing defaults: remote sends all
traffic through the tunnel, native sends only your LAN and the VPN subnet. You can
override either with the **Route all client traffic** checkbox.

---

## 2. WireGuard and the OpenVPN fallback

The app sets up **both**, on one server.

### WireGuard — the one you use

UDP, port 51820 by default. Fast, modern, about 4,000 lines of audited code. It
reconnects instantly when you move between wifi and cellular, because it has no
concept of a session to lose. This is your default, always.

### OpenVPN — the one that gets through

TCP, port **443** by default. Slower and heavier. It exists for one situation:
networks that allow only what looks like web browsing. Hotel wifi, corporate guest
networks, some airports and public hotspots block UDP outright, and there WireGuard
simply cannot connect — no error you can fix, it just never handshakes.

Port 443 is the HTTPS port, so the traffic passes where only web browsing is allowed.
The config also uses `tls-crypt`, which encrypts the TLS control channel, so a scanner
probing the port gets no OpenVPN handshake to fingerprint and unauthenticated packets
are dropped before they reach the TLS stack.

**Use WireGuard. Reach for the `.ovpn` profile only when the tunnel will not come up.**

You can turn the fallback off entirely with the **OpenVPN TCP fallback** checkbox if
you never expect to need it — that halves the moving parts on the server.

> If the server also serves real HTTPS on 443, move the fallback to another port —
> they cannot share.

---

## 3. Getting a server

Only needed for **remote** mode. Native mode uses hardware you already have.

### Choosing a provider

| Provider | Cheapest | Notes |
|---|---|---|
| Hetzner | ~€4/mo | Best value. EU and US locations. |
| DigitalOcean | ~$4–6/mo | Simple, many regions, good docs. |
| Vultr | ~$5/mo | Wide geographic spread. |
| Linode / Akamai | ~$5/mo | Reliable, long-standing. |

Any of them is fine. **Pick the location deliberately** — that is the country you
will appear to be browsing from, and it also decides your latency. A server two
countries away costs you 20–40 ms; one on another continent costs 150 ms+ and makes
video calls unpleasant.

### What to select

- **Debian 12** or **Ubuntu 22.04/24.04**. The installer targets `apt` and will
  refuse anything else.
- The smallest instance. A VPN moves packets; it barely uses CPU or RAM.
- **Add your SSH key during creation.** This is by far the easiest path — the app
  authenticates with keys only and never handles passwords.

If you have no SSH key yet:

```bash
ssh-keygen -t ed25519 -C "vpn-agent"
```

Then paste the contents of `~/.ssh/id_ed25519.pub` into the provider's SSH key field.

Confirm you can get in before touching the app:

```bash
ssh root@YOUR_SERVER_IP
```

### For native mode instead

- A **Raspberry Pi** running Raspberry Pi OS or Debian is the ideal home server. Low
  power, always on, cheap.
- Your **router** may already do this. A GL.iNet Flint 2 has a WireGuard server built
  into its firmware, and using that is simpler than anything here.
- **This Mac** works, but see [Honest limitations](#11-honest-limitations) — a laptop
  that sleeps is a poor always-on server.

For a home server to be reachable from outside you also need to forward the port on
your router and set up dynamic DNS. Without both, the tunnel only works on your own
LAN.

---

## 4. Building it, step by step

### Step 1 — New Server

Press **New Server**. Give it a name, choose the mode, and fill in:

- **Endpoint** — the public IP of your VPS, or a dynamic-DNS name for a home server.
  This is what clients dial.
- **SSH** — `root@YOUR_SERVER_IP` for remote mode.

This generates the server's WireGuard keypair and, if the fallback is enabled, a
certificate authority. All of it happens **on your machine**. Nothing is installed
anywhere yet.

### Step 2 — Add a device

Press **Add Device** and name it after the actual device: `iphone`, `work-laptop`,
`ipad`.

Give every device its own entry. Sharing one config across devices means you cannot
revoke a single lost phone without cutting off everything else.

Each device gets its own keypair, its own pre-shared key, and its own address.

### Step 3 — Check

Press **Check**. This changes nothing; it validates the configuration and tests the
connection. It catches the things that would otherwise fail halfway through an
install: a missing endpoint, overlapping subnets, an unreachable host, a key SSH will
not accept, a target that is not Debian or Ubuntu.

Fix anything it reports before continuing.

### Step 4 — Deploy

Press **Deploy** and confirm. Watch the Output pane.

The first deploy takes a minute or two, mostly `apt-get`. It ends with a verification
pass: WireGuard active, OpenVPN active, forwarding enabled, NAT rules present. If any
of those fail, the reason is right there in the output.

Deploy is **idempotent** — running it twice changes nothing the second time. That is
why adding a device later is just another deploy.

### Step 5 — Add to Profiles

Press **Add to Profiles** to register the server with the Monitor tab. It then appears
in the profile dropdown, and the latency test, tunnel indicator and health monitor all
start watching it.

---

## 5. Getting configs onto devices

### Phones — use the QR code

Select the device, press **Show QR**, then on the phone: WireGuard app → **Add
tunnel** → **Create from QR code**.

> The code encodes a private key. Anyone who photographs your screen has your tunnel.
> Do not project it, and do not screenshot it into a chat.

QR is WireGuard only. An `.ovpn` carries a whole certificate chain and will not fit.

### Computers — export the files

Select the device and press **Export Configs**. You get:

- `<device>.conf` — WireGuard. Import into the WireGuard app, or put it in
  `/etc/wireguard/` and run `wg-quick up`.
- `<device>.ovpn` — the fallback. Self-contained, with keys inlined. Import into
  Tunnelblick, OpenVPN Connect, or run `openvpn --config <file>`.

Both contain private keys and are written owner-readable only.

> **Delete them once the device has imported them.** Do not send them through email,
> Slack, or a cloud drive — that puts your tunnel's private key in somebody else's
> storage. AirDrop, a USB stick, or the QR code are all better.

### Verify it worked

Connect, then go to the Monitor tab and press **Refresh Status**:

- **Public IP** should show your server's IP, not your home one
- **Country** should show the server's location
- **DNS Status** should be green

If the IP did not change, the tunnel is up but not routing — check the
[Troubleshooting](#10-troubleshooting) section.

---

## 6. Adding and removing devices

Every change here is local until you **Deploy**. That is the step that rewrites the
server.

| Action | What it does |
|---|---|
| **Add Device** | New keypair, address, and certificate. |
| **Disable** | Leaves the device out of the server config but keeps its keys, so you can switch it back on without reissuing anything. |
| **Remove** | Deletes it and frees its address for reuse. |
| **Rotate Keys** | Fresh keys, same name and address. This is what you do when a device is lost or stolen. |

> **Removing a device does not revoke it by itself.** The device keeps working until
> you deploy. If a phone was stolen, remove or rotate it **and deploy immediately** —
> that is the moment access is actually cut.

---

## 7. Where your keys live

Site state — every private key, the certificate authority, and the device list — is
stored at:

```
~/Library/Application Support/VPN Agent/sites/<name>.json
```

Directory mode `700`, file mode `600`. The app refuses to load a site file that has
become readable by anyone else, rather than loading it and hoping.

This is **deliberately outside the project folder** so it can never be swept into a
git commit, and outside the `.app` bundle so a reinstall cannot wipe it.

### This matters more than it sounds

That file is the **only copy** of your server's private key and your certificate
authority key. There is no backup and no recovery:

- Lose it and every config you have issued is permanently dead. You would rebuild the
  server from scratch and re-deliver a new config to every device.
- **Deleting a server in the app destroys it.** The confirmation dialog says so.

Back it up somewhere encrypted. You can also point the app at a different location —
an encrypted volume, say — with an environment variable:

```bash
export VPN_AGENT_STATE_DIR=/Volumes/Encrypted/vpn-agent
```

### Why keys are generated locally

The server never creates its own identity and never sees the CA private key. It
receives only derived configuration, written over the encrypted SSH channel.

That inversion is the security design: if the VPS is compromised, the attacker sees
the traffic it is carrying right then, but **cannot mint new client certificates** and
cannot impersonate your site after you rebuild it.

---

## 8. What the installer actually does

Press **Save Installer Script** to read the exact script before letting it near a
server. It is plain bash and it is meant to be read.

On the target it:

1. Installs `wireguard`, `wireguard-tools`, `iptables`, and `openvpn` — only the ones
   actually missing.
2. Writes `/etc/wireguard/wg0.conf` (mode 600) and, for the fallback,
   `/etc/openvpn/server/`.
3. Enables IPv4 forwarding via `/etc/sysctl.d/99-vpn-agent.conf`. Without this the
   kernel silently drops every packet arriving on the tunnel and destined elsewhere —
   the tunnel comes up and carries nothing.
4. Installs a `vpn-agent-nat` systemd unit that applies masquerade and forwarding
   rules at boot. NAT lives here rather than in WireGuard's `PostUp` so the OpenVPN
   fallback shares the exact same rules instead of each transport carrying its own
   copy.
5. Opens the ports in `ufw` if it is active, and flips its forward policy to `ACCEPT`
   — ufw denies forwarding by default, which would silently break routing.
6. Starts both services, then verifies all four things and reports what failed.

The script is streamed over SSH on stdin and **never written to the target's disk** —
it embeds the server's private keys, and a file in `/tmp` lives long enough for
anything else on the box to read it.

Config payloads inside the script are base64-encoded. That is not obfuscation: it
means no key material can contain a character that would break shell quoting.

**Tear Down** reverses all of it, leaving the installed packages alone since removing
them could take out something else on the box.

---

## 9. Running it from the command line

Everything the GUI does is available from a terminal, which makes it scriptable:

```bash
python -m server.cli init "Berlin VPS" --mode remote --host 1.2.3.4 --ssh root@1.2.3.4
python -m server.cli peer add "Berlin VPS" iphone
python -m server.cli check "Berlin VPS"
python -m server.cli deploy "Berlin VPS"
python -m server.cli export "Berlin VPS" --peer iphone --qr
```

Other useful ones:

```bash
python -m server.cli list                      # every site you have built
python -m server.cli show "Berlin VPS"         # full summary
python -m server.cli script "Berlin VPS"       # print the installer, run nothing
python -m server.cli deploy "Berlin VPS" --dry-run
python -m server.cli peer rotate "Berlin VPS" iphone
python -m server.cli teardown "Berlin VPS"
```

The GUI and CLI share the same site files, so you can move between them freely.

---

## 10. Troubleshooting

### "Permission denied (publickey)"

The server will not accept your SSH key.

```bash
ssh root@YOUR_SERVER_IP          # must work before the app can deploy
ssh-copy-id root@YOUR_SERVER_IP  # if it does not
```

### "sudo: a password is required"

You connected as a non-root user without passwordless sudo. Either connect as `root`,
or configure `NOPASSWD` sudo for that user on the target.

### "Remote host has no apt-get"

The installer targets Debian, Ubuntu and Raspberry Pi OS. Rebuild the VPS with one of
those, or use **Save Installer Script** and adapt it.

### Tunnel connects, but no internet

The handshake works and traffic goes nowhere. In order of likelihood:

1. **Forwarding or NAT missing.** Re-deploy and read the verification lines at the end
   of the output — they check exactly this.
2. **Cloud firewall.** Many providers have a firewall in their web console that is
   *separate* from the server's own `ufw`. Allow UDP 51820 and TCP 443 there too.
3. **Wrong routing mode.** If **Route all client traffic** is off, only the listed
   subnets go through the tunnel — which is correct for native mode and usually wrong
   for a VPS.

### Tunnel connects, but public IP is unchanged

Split tunnel is on. Tick **Route all client traffic**, save, and deploy.

### WireGuard will not connect at all, on this network only

This is the case the fallback exists for. The network is blocking UDP. Import the
`.ovpn` profile instead.

### DNS Status shows a possible leak

Your queries are bypassing the tunnel. Check **Push DNS** is set (`1.1.1.1, 1.0.0.1`),
save, deploy, and re-import the config on the device — the DNS line lives in the
client config, so an old config keeps the old behaviour.

### Home server unreachable from outside

Almost always one of:
- the port is not forwarded on your router
- your home IP changed and you have no dynamic DNS
- your ISP uses CGNAT, so you have no reachable public IP at all

The third one cannot be fixed from this end. If your ISP uses CGNAT, a home server
cannot accept inbound connections — you need a VPS.

---

## 11. Honest limitations

**A self-hosted VPN is not anonymity.** Your VPS is rented in your name and paid with
your card. It hides your traffic from your ISP and your IP from the sites you visit.
It does not hide you from a subpoena to the hosting provider. For anonymity, the tool
is Tor, not this.

**A single-user VPS is a fingerprint.** Commercial VPNs mix hundreds of users behind
one IP. Your server has exactly one user, so all its traffic is trivially attributable
to one person — you. This trades crowd-blending for not having to trust a VPN company.

**Native mode does not change your apparent location.** Said three times in this
document because it is the most common misunderstanding.

**macOS is a poor always-on server.** It sleeps, `pf` state is cleared by some system
updates, and the tunnel drops with the lid. The macOS installer also appends to
`/etc/pf.conf`, which Apple owns and system updates overwrite — you must re-run it
after a major macOS update. A €50 Raspberry Pi is genuinely the better home server.

**Teardown is Linux-only.** For a native macOS install, remove the `vpn-agent` block
from `/etc/pf.conf` and run `sudo wg-quick down` yourself.

**The installer has not been run against every distro.** It targets Debian and Ubuntu
and checks for `apt-get` before doing anything. On anything else it stops rather than
guessing.

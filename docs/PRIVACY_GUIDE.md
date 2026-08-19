# Privacy Tools — Tor, Proxy Chains, Obfuscation, MAC

The **Privacy** tab and the obfuscation options on **Build Server** cover four
tools that are frequently stacked in the belief that the total is anonymity.

It is not. Each narrows a specific, different exposure, and it is worth knowing
which — because using the wrong one for your actual concern gives you nothing
while feeling like it gives you everything.

| Tool | Hides you from | Does **not** help with |
|---|---|---|
| **VPN** | your ISP, and the sites you visit | the VPS provider, or anyone who subpoenas them |
| **Tor** | the site you visit learning your server's IP | the exit node reading unencrypted traffic |
| **Proxy chain** | any single proxy knowing both ends | UDP traffic, which bypasses it entirely |
| **Obfuscation** | a network that blocks or fingerprints VPNs | anyone who already has your traffic |
| **MAC change** | the wifi you are joined to | literally anything past the first router |

**If you need real anonymity, the tool is Tor Browser.** Its value is the
fingerprinting defences — identical window sizes, blocked font enumeration,
disabled canvas — and those live in the browser. No amount of network plumbing
underneath substitutes for them.

---

## 1. Tor

Starts a Tor client on this Mac, listening on `127.0.0.1:9250`.

Ports 9250/9251 rather than the usual 9050/9051, so it never fights a system Tor
or Tor Browser (9150). It runs as an ordinary child process with its own config
under Application Support — no sudo, nothing installed system-wide.

```bash
brew install tor
```

### What combining it with the VPN actually does

Traffic enters the WireGuard tunnel, leaves at your server, and only then enters
Tor. So:

- Your ISP sees WireGuard to your server, and nothing else.
- Tor's guard node sees your **server's** address, not your home one.
- The exit node sees whatever you are doing, exactly as it always would.

That last point is the one people forget. Tor's exit is a stranger's machine, and
anything not end-to-end encrypted is readable there. Tor protects *who you are*,
not *what you are sending*.

### Verify, don't assume

**Verify** asks the Tor Project whether the traffic really is coming from a Tor
exit. A reachable SOCKS port is not proof it is Tor, and "I configured it" is not
the same as "it works".

### New Circuit

Requests fresh circuits, changing the exit you appear to come from. It does
**not** clear what a site already knows — cookies, a login session, a browser
fingerprint all survive. This is not a way to become a different person
mid-session.

---

## 2. Proxy chains

Route through several proxies in sequence, so no single one sees both who you are
and where you are going.

Each hop is reached *through* the previous one: the app connects to hop 1, asks it
for hop 2, then over that same socket asks hop 2 for hop 3. Every proxy learns
only the address of the next.

### Two limits that matter

**Chains carry TCP only.** UDP — and therefore ordinary DNS, and QUIC — does not
traverse SOCKS in any way these tools implement. It either fails or quietly goes
around the chain. Keep `proxy_dns` on so name resolution happens at the far end.

**On macOS, proxychains-ng barely works.** It functions by injecting a library
through `DYLD_INSERT_LIBRARIES`, and System Integrity Protection strips that from
everything Apple ships. `/usr/bin/curl` will ignore your config entirely and
connect directly — *which looks exactly like it worked*. It can still wrap a
Homebrew binary you installed yourself.

Because of that, **Test Chain does not use proxychains.** The app speaks SOCKS
itself, so the test is a genuine end-to-end check regardless of SIP, and reports
the address traffic actually comes out of.

### Chain modes

Only affect the generated `proxychains.conf`; the built-in test always walks the
full chain in order.

| Mode | Behaviour |
|---|---|
| `strict` | every proxy, in order. Fails if any is down. |
| `dynamic` | same order, skipping unreachable ones. |
| `random` | a random subset each time. |

> Credentials are stored in `~/Library/Application Support/VPN Agent/proxychain.json`,
> owner-readable only, alongside your server keys — never in the repository.

---

## 3. Obfuscation

Set on the **Build Server** tab, per server.

OpenVPN already uses `tls-crypt`, which hides the handshake's *contents*. But the
packet sizes and timing of an OpenVPN session remain recognisable to a
deep-packet inspector that is looking for them.

### stunnel

Puts a real TLS listener on the public port and forwards to OpenVPN bound to
loopback. What crosses the network is an ordinary TLS session on 443 — not
*resembling* HTTPS, actually being it as far as the wire is concerned.

OpenVPN retreats to `127.0.0.1:1194`. Binding to loopback is what makes that a
real boundary: without it OpenVPN would still answer on its own port and the
obfuscation would be bypassable by anyone who simply tried the direct connection.

**The cost is real.** Every device then needs stunnel running locally too:

```bash
brew install stunnel          # macOS
stunnel /path/to/stunnel-client.conf
```

Export bundles the config, the CA to verify the server against, and a
`READ-ME-FIRST.txt` with the order to do things in. The `.ovpn` is already
pointed at `127.0.0.1`.

WireGuard is unaffected and still connects directly.

### Onion service

Publishes the OpenVPN endpoint as a Tor hidden service.

This is the answer to **CGNAT**. If your ISP gives you no reachable public
address, no amount of dynamic DNS helps — there is nothing to dial. A hidden
service is reachable anyway, because the rendezvous happens inside the Tor
network. It also means the server's real address is never handed to a client.

Onion services carry TCP only, so this fronts the OpenVPN fallback rather than
WireGuard. Slower than the direct route — a path of last resort.

The address is generated on the server during the first deploy and captured from
the installer's output, so it appears in the app rather than only in a file on
the server.

---

## 4. Hardware address

The most over-estimated measure in common use, so plainly:

**A MAC address travels exactly one hop.** The café's access point sees it, your
home router sees it, and nothing beyond that ever does — it is stripped and
replaced at the first router. It has no bearing on what a website sees, on what
your ISP sees, or on anything the VPN is for.

**What it is genuinely good for:** not being trackable *by the network you are
joining*. Venue wifi that logs MAC addresses can otherwise recognise the same
laptop across visits, and across venues under the same operator.

### Check whether you need it at all

On recent macOS, Wi-Fi already does this for you. **Private Wi-Fi Address** is on
by default and gives every network its own stable random address — a better design
than one address you change by hand, because it is consistent per network and
cannot be correlated across them.

Settings › Wi-Fi › your network › Details.

If the Privacy tab shows your Wi-Fi interface as already differing from its
hardware address, that is almost certainly macOS's own feature, not something you
did.

Ethernet and USB adapters get no such treatment. That is where this earns its
place.

### Two generation modes

| Mode | Trade-off |
|---|---|
| **Locally administered** | Correct — sets the bit marking an address as belonging to no manufacturer, so it cannot collide with real hardware. That same bit tells anyone looking that it was made up. |
| **Keep vendor prefix** | Reuses the first three octets of your real address, so the interface still looks like the same make of hardware. Less conspicuous, at the cost of using an OUI that is not yours. |

### Caveats

- **Does not survive a reboot.**
- Wi-Fi is switched off and on to apply it, so you drop off the network and may
  need to rejoin.
- Some adapters and virtual interfaces silently ignore the change. The app reads
  the address back afterwards and tells you if it did not take.

---

## Honest limitations

- **None of this is anonymity.** Your VPS is rented in your name and paid with
  your card. Tor's protection is undermined by the browser you use it with.
- **Stacking has a cost.** Each layer adds latency and a way to fail. A chain
  through Tor and two proxies is slow enough to change what you can do with it.
- **Proxies you do not control are parties who can log you.** A chain of three
  free proxies is three strangers instead of one.
- **The obfuscation and onion paths have not been exercised against a live
  server.** Config generation is tested; the deploy path for these two is not.

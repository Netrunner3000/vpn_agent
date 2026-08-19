"""
privacy_doc_content.py — In-app guide for the Privacy tab.

The same content exists as docs/PRIVACY_GUIDE.md for standalone reading — keep
the two in step by hand.
"""

from app.doc_style import wrap

PRIVACY_DOC_HTML = wrap("""
<h1>Privacy Tools</h1>

<p>The <b>Privacy</b> tab and the obfuscation options on <b>Build Server</b> cover four
tools that are frequently stacked in the belief that the total is anonymity.</p>

<p>It is not. Each narrows a specific, different exposure, and it is worth knowing
which — because using the wrong one for your actual concern gives you nothing while
feeling like it gives you everything.</p>

<table>
<tr><th>Tool</th><th>Hides you from</th><th>Does <b>not</b> help with</th></tr>
<tr><td><b>VPN</b></td><td>your ISP, and the sites you visit</td><td>the VPS provider, or anyone who subpoenas them</td></tr>
<tr><td><b>Tor</b></td><td>the site learning your server's IP</td><td>the exit node reading unencrypted traffic</td></tr>
<tr><td><b>Proxy chain</b></td><td>any single proxy knowing both ends</td><td>UDP traffic, which bypasses it entirely</td></tr>
<tr><td><b>Obfuscation</b></td><td>a network that blocks or fingerprints VPNs</td><td>anyone who already has your traffic</td></tr>
<tr><td><b>MAC change</b></td><td>the wifi you are joined to</td><td>literally anything past the first router</td></tr>
</table>

<div class="warning-box"><b>If you need real anonymity, the tool is Tor Browser.</b>
Its value is the fingerprinting defences — identical window sizes, blocked font
enumeration, disabled canvas — and those live in the browser. No amount of network
plumbing underneath substitutes for them.</div>

<hr>

<h2><a name="tor"></a>1. Tor</h2>

<p>Starts a Tor client listening on <code>127.0.0.1:9250</code>. Ports 9250/9251 rather
than the usual 9050/9051, so it never fights a system Tor or Tor Browser (9150). It runs
as an ordinary child process with its own config — no sudo, nothing installed
system-wide.</p>

<pre>brew install tor</pre>

<h3>What combining it with the VPN actually does</h3>
<p>Traffic enters the WireGuard tunnel, leaves at your server, and only then enters Tor:</p>
<ul>
<li>Your ISP sees WireGuard to your server, and nothing else.</li>
<li>Tor's guard node sees your <b>server's</b> address, not your home one.</li>
<li>The exit node sees whatever you are doing, exactly as it always would.</li>
</ul>
<p>That last point is the one people forget. Tor's exit is a stranger's machine, and
anything not end-to-end encrypted is readable there. Tor protects <i>who you are</i>, not
<i>what you are sending</i>.</p>

<h3>Verify, don't assume</h3>
<p><b>Verify</b> asks the Tor Project whether the traffic really is coming from a Tor
exit. A reachable SOCKS port is not proof it is Tor, and "I configured it" is not the
same as "it works".</p>

<h3>New Circuit</h3>
<p>Requests fresh circuits, changing the exit you appear to come from. It does <b>not</b>
clear what a site already knows — cookies, a login, a browser fingerprint all survive.
This is not a way to become a different person mid-session.</p>

<hr>

<h2><a name="chain"></a>2. Proxy chains</h2>

<p>Route through several proxies in sequence, so no single one sees both who you are and
where you are going. Each hop is reached <i>through</i> the previous one, so every proxy
learns only the address of the next.</p>

<h3>Two limits that matter</h3>
<p><b>Chains carry TCP only.</b> UDP — and therefore ordinary DNS, and QUIC — does not
traverse SOCKS in any way these tools implement. It either fails or quietly goes around
the chain. Keep <code>proxy_dns</code> on so names are resolved at the far end.</p>

<div class="warning-box"><b>On macOS, proxychains-ng barely works.</b> It injects a
library through <code>DYLD_INSERT_LIBRARIES</code>, and System Integrity Protection
strips that from everything Apple ships. <code>/usr/bin/curl</code> will ignore your
config entirely and connect directly — <i>which looks exactly like it worked</i>. It can
still wrap a Homebrew binary you installed yourself.</div>

<p>Because of that, <b>Test Chain does not use proxychains.</b> The app speaks SOCKS
itself, so the test is a genuine end-to-end check regardless of SIP, and reports the
address traffic actually comes out of.</p>

<h3>Chain modes</h3>
<p>These only affect the generated <code>proxychains.conf</code>; the built-in test always
walks the full chain in order.</p>
<table>
<tr><th>Mode</th><th>Behaviour</th></tr>
<tr><td><code>strict</code></td><td>every proxy, in order. Fails if any is down.</td></tr>
<tr><td><code>dynamic</code></td><td>same order, skipping unreachable ones.</td></tr>
<tr><td><code>random</code></td><td>a random subset each time.</td></tr>
</table>

<p class="note">Credentials are stored owner-readable only, alongside your server keys —
never in the repository.</p>

<hr>

<h2><a name="obfs"></a>3. Obfuscation</h2>

<p>Set on the <b>Build Server</b> tab, per server.</p>

<p>OpenVPN already uses <code>tls-crypt</code>, which hides the handshake's
<i>contents</i>. But the packet sizes and timing of an OpenVPN session remain
recognisable to a deep-packet inspector that is looking for them.</p>

<h3>stunnel</h3>
<p>Puts a real TLS listener on the public port and forwards to OpenVPN bound to loopback.
What crosses the network is an ordinary TLS session on 443 — not <i>resembling</i> HTTPS,
actually being it as far as the wire is concerned.</p>

<p>OpenVPN retreats to <code>127.0.0.1:1194</code>. Binding to loopback is what makes that
a real boundary: without it OpenVPN would still answer on its own port and the obfuscation
would be bypassable by anyone who simply tried the direct connection.</p>

<div class="warning-box"><b>The cost is real.</b> Every device then needs stunnel running
locally too. Export bundles the config, the CA to verify the server against, and a
READ-ME-FIRST.txt with the order to do things in. The <code>.ovpn</code> is already
pointed at 127.0.0.1. WireGuard is unaffected and still connects directly.</div>

<h3>Onion service</h3>
<p>Publishes the OpenVPN endpoint as a Tor hidden service.</p>
<p>This is the answer to <b>CGNAT</b>. If your ISP gives you no reachable public address,
no amount of dynamic DNS helps — there is nothing to dial. A hidden service is reachable
anyway, because the rendezvous happens inside the Tor network. It also means the server's
real address is never handed to a client.</p>
<p>Onion services carry TCP only, so this fronts the OpenVPN fallback rather than
WireGuard. Slower than the direct route — a path of last resort.</p>

<hr>

<h2><a name="mac"></a>4. Hardware address</h2>

<div class="warning-box"><b>A MAC address travels exactly one hop.</b> The café's access
point sees it, your home router sees it, and nothing beyond that ever does — it is
stripped and replaced at the first router. It has no bearing on what a website sees, on
what your ISP sees, or on anything the VPN is for.</div>

<p><b>What it is genuinely good for:</b> not being trackable <i>by the network you are
joining</i>. Venue wifi that logs MAC addresses can otherwise recognise the same laptop
across visits, and across venues under the same operator.</p>

<h3>Check whether you need it at all</h3>
<p>On recent macOS, Wi-Fi already does this for you. <b>Private Wi-Fi Address</b> is on by
default and gives every network its own stable random address — a better design than one
address you change by hand, because it is consistent per network and cannot be correlated
across them. Settings › Wi-Fi › your network › Details.</p>
<p>If this tab shows your Wi-Fi interface already differing from its hardware address,
that is almost certainly macOS's own feature, not something you did. Ethernet and USB
adapters get no such treatment — that is where this earns its place.</p>

<h3>Two generation modes</h3>
<table>
<tr><th>Mode</th><th>Trade-off</th></tr>
<tr><td><b>Locally administered</b></td><td>Correct — sets the bit marking an address as
belonging to no manufacturer, so it cannot collide with real hardware. That same bit tells
anyone looking that it was made up.</td></tr>
<tr><td><b>Keep vendor prefix</b></td><td>Reuses the first three octets of your real
address, so the interface still looks like the same make of hardware. Less conspicuous, at
the cost of using an OUI that is not yours.</td></tr>
</table>

<h3>Caveats</h3>
<ul>
<li><b>Does not survive a reboot.</b></li>
<li>Wi-Fi is switched off and on to apply it, so you drop off the network.</li>
<li>Some adapters silently ignore the change. The app reads the address back afterwards
and tells you if it did not take.</li>
</ul>

<hr>

<h2><a name="limits"></a>Honest limitations</h2>
<ul>
<li><b>None of this is anonymity.</b> Your VPS is rented in your name and paid with your
card. Tor's protection is undermined by the browser you use it with.</li>
<li><b>Stacking has a cost.</b> Each layer adds latency and a way to fail. A chain through
Tor and two proxies is slow enough to change what you can do with it.</li>
<li><b>Proxies you do not control are parties who can log you.</b> A chain of three free
proxies is three strangers instead of one.</li>
<li><b>The obfuscation and onion paths have not been exercised against a live server.</b>
Config generation is tested; the deploy path for these two is not.</li>
</ul>

<hr>
<p style="color:#444444; font-size:11px; text-align:center;">VPN Agent — Privacy</p>
""")

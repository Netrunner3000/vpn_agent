"""
server_doc_content.py — In-app guide for the Build Server tab.

Rendered by QTextBrowser in doc_dialog.py. The same content exists as
docs/SERVER_GUIDE.md for standalone reading — keep the two in step by hand.
"""

from app.doc_style import wrap

SERVER_DOC_HTML = wrap("""
<h1>Building Your Own VPN</h1>

<p>The <b>Build Server</b> tab creates the thing at the far end of the tunnel. The
Monitor tab watches a connection; this half makes the server that connection goes to.</p>

<p>Everything here is yours: you generate the keys, you hold the certificate authority,
and no third party is in the path. That is the whole point — a commercial VPN moves
your trust from your ISP to a company you know less about. This moves it to a machine
you rent or own.</p>

<div class="toc">
<ol>
<li><a href="#mode">Which mode do I want?</a></li>
<li><a href="#protocols">WireGuard and the OpenVPN fallback</a></li>
<li><a href="#getserver">Getting a server</a></li>
<li><a href="#build">Building it, step by step</a></li>
<li><a href="#deliver">Getting configs onto devices</a></li>
<li><a href="#status">Seeing who is connected</a></li>
<li><a href="#devices">Adding and removing devices</a></li>
<li><a href="#keys">Where your keys live</a></li>
<li><a href="#backup">Backing up your keys</a></li>
<li><a href="#installer">What the installer actually does</a></li>
<li><a href="#cli">Running it from the command line</a></li>
<li><a href="#trouble">Troubleshooting</a></li>
<li><a href="#limits">Honest limitations</a></li>
</ol>
</div>

<hr>

<h2><a name="mode"></a>1. Which mode do I want?</h2>

<p>This is the one decision that changes everything downstream, and it is easy to get
backwards.</p>

<h3>Remote — a rented host</h3>
<p>The server runs on a VPS somewhere. Your traffic goes into the tunnel, comes out at
the VPS, and reaches the internet from <b>the VPS's IP address</b>.</p>
<p>Use this when you want to:</p>
<ul>
<li>hide your home IP from the sites you visit</li>
<li>appear to be in another country</li>
<li>be safe on hotel, airport or café wifi</li>
</ul>

<h3>Native — hardware you own</h3>
<p>The server runs on a Raspberry Pi, a spare Linux box, or this Mac, sitting on your
own LAN. Traffic goes into the tunnel and comes out at <b>your own home ISP
connection</b>.</p>
<p>Use this when you want to:</p>
<ul>
<li>reach your home NAS, printer, or router securely from outside</li>
<li>browse through your home connection while travelling</li>
<li>keep everything on hardware you physically possess</li>
</ul>

<div class="warning-box">
<span class="warn">The trap:</span> native mode does <b>not</b> hide your IP and does
<b>not</b> change your apparent country. Your exit IP <i>is</i> your home IP. If your
goal is privacy from the sites you visit, or geo-shifting, native mode gives you none
of it. Use remote.
</div>

<p>Because of that, the two modes get different routing defaults: remote sends all
traffic through the tunnel, native sends only your LAN and the VPN subnet. You can
override either with the <b>Route all client traffic</b> checkbox.</p>

<hr>

<h2><a name="protocols"></a>2. WireGuard and the OpenVPN fallback</h2>

<p>The app sets up <b>both</b>, on one server.</p>

<h3>WireGuard — the one you use</h3>
<p>UDP, port 51820 by default. Fast, modern, about 4,000 lines of audited code. It
reconnects instantly when you move between wifi and cellular, because it has no concept
of a session to lose. This is your default, always.</p>

<h3>OpenVPN — the one that gets through</h3>
<p>TCP, port <b>443</b> by default. Slower and heavier. It exists for one situation:
networks that allow only what looks like web browsing. Hotel wifi, corporate guest
networks, some airports and public hotspots block UDP outright, and there WireGuard
simply cannot connect — no error you can fix, it just never handshakes.</p>

<p>Port 443 is the HTTPS port, so the traffic passes where only web browsing is allowed.
The config also uses <code>tls-crypt</code>, which encrypts the TLS control channel, so
a scanner probing the port gets no OpenVPN handshake to fingerprint and unauthenticated
packets are dropped before they reach the TLS stack.</p>

<div class="tip">
<b>Use WireGuard.</b> Reach for the <code>.ovpn</code> profile only when the tunnel
will not come up.
</div>

<p>You can turn the fallback off entirely with the <b>OpenVPN TCP fallback</b> checkbox
if you never expect to need it — that halves the moving parts on the server.</p>

<p class="note">If the server also serves real HTTPS on 443, move the fallback to
another port — they cannot share.</p>

<hr>

<h2><a name="getserver"></a>3. Getting a server</h2>

<p>Only needed for <b>remote</b> mode. Native mode uses hardware you already have.</p>

<h3>Choosing a provider</h3>
<table>
<tr><th>Provider</th><th>Cheapest</th><th>Notes</th></tr>
<tr><td>Hetzner</td><td>~€4/mo</td><td>Best value. EU and US locations.</td></tr>
<tr><td>DigitalOcean</td><td>~$4–6/mo</td><td>Simple, many regions, good docs.</td></tr>
<tr><td>Vultr</td><td>~$5/mo</td><td>Wide geographic spread.</td></tr>
<tr><td>Linode / Akamai</td><td>~$5/mo</td><td>Reliable, long-standing.</td></tr>
</table>

<p>Any of them is fine. <b>Pick the location deliberately</b> — that is the country you
will appear to be browsing from, and it also decides your latency. A server two
countries away costs you 20–40 ms; one on another continent costs 150 ms+ and makes
video calls unpleasant.</p>

<h3>What to select</h3>
<ul>
<li><b>Debian 12</b> or <b>Ubuntu 22.04/24.04</b>. The installer targets <code>apt</code>
and will refuse anything else.</li>
<li>The smallest instance. A VPN moves packets; it barely uses CPU or RAM.</li>
<li><b>Add your SSH key during creation.</b> This is by far the easiest path — the app
authenticates with keys only and never handles passwords.</li>
</ul>

<p>If you have no SSH key yet:</p>
<pre>ssh-keygen -t ed25519 -C "vpn-agent"</pre>
<p>Then paste the contents of <code>~/.ssh/id_ed25519.pub</code> into the provider's SSH
key field. Confirm you can get in before touching the app:</p>
<pre>ssh root@YOUR_SERVER_IP</pre>

<h3>For native mode instead</h3>
<ul>
<li>A <b>Raspberry Pi</b> running Raspberry Pi OS or Debian is the ideal home server.
Low power, always on, cheap.</li>
<li>Your <b>router</b> may already do this. A GL.iNet Flint 2 has a WireGuard server
built into its firmware, and using that is simpler than anything here.</li>
<li><b>This Mac</b> works, but see <a href="#limits">Honest limitations</a> — a laptop
that sleeps is a poor always-on server.</li>
</ul>

<p>For a home server to be reachable from outside you also need to forward the port on
your router and set up dynamic DNS. Without both, the tunnel only works on your own
LAN.</p>

<hr>

<h2><a name="build"></a>4. Building it, step by step</h2>

<h3>Step 1 — New Server</h3>
<p>Press <b>New Server</b>. Give it a name, choose the mode, and fill in:</p>
<ul>
<li><b>Endpoint</b> — the public IP of your VPS, or a dynamic-DNS name for a home
server. This is what clients dial.</li>
<li><b>SSH</b> — <code>root@YOUR_SERVER_IP</code> for remote mode.</li>
</ul>
<p>This generates the server's WireGuard keypair and, if the fallback is enabled, a
certificate authority. All of it happens <b>on your machine</b>. Nothing is installed
anywhere yet.</p>

<h3>Step 2 — Add a device</h3>
<p>Press <b>Add Device</b> and name it after the actual device: <code>iphone</code>,
<code>work-laptop</code>, <code>ipad</code>.</p>
<p>Give every device its own entry. Sharing one config across devices means you cannot
revoke a single lost phone without cutting off everything else.</p>

<h3>Step 3 — Check</h3>
<p>Press <b>Check</b>. This changes nothing; it validates the configuration and tests
the connection. It catches the things that would otherwise fail halfway through an
install: a missing endpoint, overlapping subnets, an unreachable host, a key SSH will
not accept, a target that is not Debian or Ubuntu.</p>

<h3>Step 4 — Deploy</h3>
<p>Press <b>Deploy</b> and confirm. Watch the Output pane.</p>
<p>The first deploy takes a minute or two, mostly <code>apt-get</code>. It ends with a
verification pass: WireGuard active, OpenVPN active, forwarding enabled, NAT rules
present. If any of those fail, the reason is right there in the output.</p>
<p>Deploy is <b>idempotent</b> — running it twice changes nothing the second time. That
is why adding a device later is just another deploy.</p>

<h3>Step 5 — Add to Profiles</h3>
<p>Press <b>Add to Profiles</b> to register the server with the Monitor tab. It then
appears in the profile dropdown, and the latency test, tunnel indicator and health
monitor all start watching it.</p>

<hr>

<h2><a name="deliver"></a>5. Getting configs onto devices</h2>

<h3>Phones — use the QR code</h3>
<p>Select the device, press <b>Show QR</b>, then on the phone: WireGuard app →
<b>Add tunnel</b> → <b>Create from QR code</b>.</p>

<div class="warning-box">
The code encodes a private key. Anyone who photographs your screen has your tunnel.
Do not project it, and do not screenshot it into a chat.
</div>

<p>QR is WireGuard only. An <code>.ovpn</code> carries a whole certificate chain and
will not fit.</p>

<h3>Computers — export the files</h3>
<p>Select the device and press <b>Export Configs</b>. You get:</p>
<ul>
<li><code>&lt;device&gt;.conf</code> — WireGuard. Import into the WireGuard app, or put
it in <code>/etc/wireguard/</code> and run <code>wg-quick up</code>.</li>
<li><code>&lt;device&gt;.ovpn</code> — the fallback. Self-contained, with keys inlined.
Import into Tunnelblick, OpenVPN Connect, or run
<code>openvpn --config &lt;file&gt;</code>.</li>
</ul>

<div class="danger-box">
<span class="danger">Delete them once the device has imported them.</span> Do not send
them through email, Slack, or a cloud drive — that puts your tunnel's private key in
somebody else's storage. AirDrop, a USB stick, or the QR code are all better.
</div>

<h3>Verify it worked</h3>
<p>Connect, then go to the Monitor tab and press <b>Refresh Status</b>:</p>
<ul>
<li><b>Public IP</b> should show your server's IP, not your home one</li>
<li><b>Country</b> should show the server's location</li>
<li><b>DNS Status</b> should be green</li>
</ul>

<hr>

<h2><a name="status"></a>6. Seeing who is connected</h2>
<p><b>Status</b> asks the server what it is actually doing, rather than what you last
told it to do. For each device: when it last handshaked, how much it has transferred,
and which address it is connecting from.</p>
<p>WireGuard is connectionless, so "connected" really means "handshaked recently" —
an active device rekeys about every two minutes, so anything quiet for more than about
three minutes has gone away. The device list marks these ● and ○.</p>
<p>It also warns if the server has peers this app does not know about, which means the
server and your local state have drifted — redeploy to bring them back in line.</p>
<p class="note">Remote servers only.</p>

<hr>

<h2><a name="devices"></a>7. Adding and removing devices</h2>

<p>Every change here is local until you <b>Deploy</b>. That is the step that rewrites
the server.</p>

<table>
<tr><th>Action</th><th>What it does</th></tr>
<tr><td><b>Add Device</b></td><td>New keypair, address, and certificate.</td></tr>
<tr><td><b>Disable</b></td><td>Leaves the device out of the server config but keeps its
keys, so you can switch it back on without reissuing anything.</td></tr>
<tr><td><b>Remove</b></td><td>Deletes it and frees its address for reuse.</td></tr>
<tr><td><b>Rotate Keys</b></td><td>Fresh keys, same name and address. This is what you
do when a device is lost or stolen.</td></tr>
</table>

<div class="danger-box">
<span class="danger">Removing a device does not revoke it by itself.</span> The device
keeps working until you deploy. If a phone was stolen, remove or rotate it <b>and
deploy immediately</b> — that is the moment access is actually cut.
</div>

<hr>

<h2><a name="keys"></a>8. Where your keys live</h2>

<p>Site state — every private key, the certificate authority, and the device list — is
stored at:</p>
<pre>~/Library/Application Support/VPN Agent/sites/&lt;name&gt;.json</pre>

<p>Directory mode <code>700</code>, file mode <code>600</code>. The app refuses to load
a site file that has become readable by anyone else, rather than loading it and
hoping.</p>

<p>This is <b>deliberately outside the project folder</b> so it can never be swept into
a git commit, and outside the <code>.app</code> bundle so a reinstall cannot wipe it.</p>

<h3>This matters more than it sounds</h3>
<p>That file is the <b>only copy</b> of your server's private key and your certificate
authority key. There is no backup and no recovery:</p>
<ul>
<li>Lose it and every config you have issued is permanently dead. You would rebuild the
server from scratch and re-deliver a new config to every device.</li>
<li><b>Deleting a server in the app destroys it.</b> The confirmation dialog says so.</li>
</ul>

<p>Back it up somewhere encrypted. You can also point the app at a different location —
an encrypted volume, say — with an environment variable:</p>
<pre>export VPN_AGENT_STATE_DIR=/Volumes/Encrypted/vpn-agent</pre>

<h3>Why keys are generated locally</h3>
<p>The server never creates its own identity and never sees the CA private key. It
receives only derived configuration, written over the encrypted SSH channel.</p>
<p>That inversion is the security design: if the VPS is compromised, the attacker sees
the traffic it is carrying right then, but <b>cannot mint new client certificates</b>
and cannot impersonate your site after you rebuild it.</p>

<hr>

<h2><a name="backup"></a>9. Backing up your keys</h2>
<p>The site file is the only copy of the server key and the certificate authority.
<b>Backup</b> writes an encrypted copy of the whole site — keys, CA, and every
device.</p>
<ul>
<li>Encrypted with a passphrase you choose: scrypt to derive the key, AES-256-GCM to
seal it. scrypt is memory-hard, so a stolen backup cannot be attacked with cheap
parallel hardware.</li>
<li><b>The passphrase is never stored.</b> Lose it and the backup is as gone as the
original.</li>
<li>The file authenticates as well as encrypts, so a corrupted or altered backup is
refused rather than restoring a subtly wrong site.</li>
<li>The header — which site, which format version — is readable without the
passphrase, so you can identify a file before opening it.</li>
</ul>
<p><b>Restore</b> brings back the keys, the CA and every device, so the configs
already on your phones keep working. It refuses to overwrite an existing server of the
same name unless you confirm, because replacing its keys invalidates every config
issued from it.</p>
<div class="tip">This is the supported way to carry a server to another machine.
Copying the raw site file works too, but leaves an unprotected CA key sitting wherever
you copied it.</div>

<hr>

<h2><a name="installer"></a>10. What the installer actually does</h2>

<p>Press <b>Save Installer Script</b> to read the exact script before letting it near a
server. It is plain bash and it is meant to be read.</p>

<p>On the target it:</p>
<ol>
<li>Installs <code>wireguard</code>, <code>wireguard-tools</code>, <code>iptables</code>
and <code>openvpn</code> — only the ones actually missing.</li>
<li>Writes <code>/etc/wireguard/wg0.conf</code> (mode 600) and, for the fallback,
<code>/etc/openvpn/server/</code>.</li>
<li>Enables IPv4 forwarding. Without this the kernel silently drops every packet
arriving on the tunnel and destined elsewhere — the tunnel comes up and carries
nothing.</li>
<li>Installs a <code>vpn-agent-nat</code> systemd unit that applies masquerade and
forwarding rules at boot. NAT lives here rather than in WireGuard's <code>PostUp</code>
so the OpenVPN fallback shares the exact same rules.</li>
<li>Opens the ports in <code>ufw</code> if active, and flips its forward policy to
<code>ACCEPT</code> — ufw denies forwarding by default, which would silently break
routing.</li>
<li>Starts both services, then verifies all four things and reports what failed.</li>
</ol>

<p>The script is streamed over SSH on stdin and <b>never written to the target's
disk</b> — it embeds the server's private keys, and a file in <code>/tmp</code> lives
long enough for anything else on the box to read it.</p>

<p><b>Tear Down</b> reverses all of it, leaving the installed packages alone since
removing them could take out something else on the box.</p>

<hr>

<h2><a name="cli"></a>11. Running it from the command line</h2>

<p>Everything the GUI does is available from a terminal, which makes it scriptable:</p>
<pre>python -m server.cli init "Berlin VPS" --mode remote --host 1.2.3.4 --ssh root@1.2.3.4
python -m server.cli peer add "Berlin VPS" iphone
python -m server.cli check "Berlin VPS"
python -m server.cli deploy "Berlin VPS"
python -m server.cli export "Berlin VPS" --peer iphone --qr</pre>

<p>Other useful ones:</p>
<pre>python -m server.cli list
python -m server.cli show "Berlin VPS"
python -m server.cli script "Berlin VPS"
python -m server.cli deploy "Berlin VPS" --dry-run
python -m server.cli peer rotate "Berlin VPS" iphone
python -m server.cli status "Berlin VPS"
python -m server.cli backup "Berlin VPS" --out ~/berlin.vpnbackup
python -m server.cli restore ~/berlin.vpnbackup
python -m server.cli teardown "Berlin VPS"</pre>

<p>The GUI and CLI share the same site files, so you can move between them freely.</p>

<hr>

<h2><a name="trouble"></a>12. Troubleshooting</h2>

<h3>"Permission denied (publickey)"</h3>
<p>The server will not accept your SSH key.</p>
<pre>ssh root@YOUR_SERVER_IP          # must work before the app can deploy
ssh-copy-id root@YOUR_SERVER_IP  # if it does not</pre>

<h3>"sudo: a password is required"</h3>
<p>You connected as a non-root user without passwordless sudo. Either connect as
<code>root</code>, or configure <code>NOPASSWD</code> sudo for that user.</p>

<h3>"Remote host has no apt-get"</h3>
<p>The installer targets Debian, Ubuntu and Raspberry Pi OS. Rebuild the VPS with one
of those, or use <b>Save Installer Script</b> and adapt it.</p>

<h3>Tunnel connects, but no internet</h3>
<p>The handshake works and traffic goes nowhere. In order of likelihood:</p>
<ol>
<li><b>Forwarding or NAT missing.</b> Re-deploy and read the verification lines at the
end of the output — they check exactly this.</li>
<li><b>Cloud firewall.</b> Many providers have a firewall in their web console that is
<i>separate</i> from the server's own <code>ufw</code>. Allow UDP 51820 and TCP 443
there too.</li>
<li><b>Wrong routing mode.</b> If <b>Route all client traffic</b> is off, only the
listed subnets go through the tunnel.</li>
</ol>

<h3>Tunnel connects, but public IP is unchanged</h3>
<p>Split tunnel is on. Tick <b>Route all client traffic</b>, save, and deploy.</p>

<h3>WireGuard will not connect at all, on this network only</h3>
<p>This is the case the fallback exists for. The network is blocking UDP. Import the
<code>.ovpn</code> profile instead.</p>

<h3>DNS Status shows a possible leak</h3>
<p>Your queries are bypassing the tunnel. Check <b>Push DNS</b> is set, save, deploy,
and re-import the config on the device — the DNS line lives in the client config, so an
old config keeps the old behaviour.</p>

<h3>Home server unreachable from outside</h3>
<p>Almost always one of: the port is not forwarded on your router; your home IP changed
and you have no dynamic DNS; or your ISP uses CGNAT, so you have no reachable public IP
at all. The third cannot be fixed from this end — you need a VPS.</p>

<hr>

<h2><a name="limits"></a>13. Honest limitations</h2>

<p><b>A self-hosted VPN is not anonymity.</b> Your VPS is rented in your name and paid
with your card. It hides your traffic from your ISP and your IP from the sites you
visit. It does not hide you from a subpoena to the hosting provider. For anonymity, the
tool is Tor, not this.</p>

<p><b>A single-user VPS is a fingerprint.</b> Commercial VPNs mix hundreds of users
behind one IP. Your server has exactly one user, so all its traffic is trivially
attributable to one person — you. This trades crowd-blending for not having to trust a
VPN company.</p>

<p><b>Native mode does not change your apparent location.</b> Said three times in this
document because it is the most common misunderstanding.</p>

<p><b>macOS is a poor always-on server.</b> It sleeps, <code>pf</code> state is cleared
by some system updates, and the tunnel drops with the lid. The macOS installer also
appends to <code>/etc/pf.conf</code>, which Apple owns and system updates overwrite —
the app notices this and warns you on the next launch, but you still have to deploy
again to fix it. A €50 Raspberry Pi is genuinely the
better home server.</p>

<p><b>The installer has not been run against every distro.</b> It targets Debian and
Ubuntu and checks for <code>apt-get</code> before doing anything. On anything else it
stops rather than guessing.</p>

<hr>
<p style="color:#444444; font-size:11px; text-align:center;">VPN Agent — Build Server</p>
""")

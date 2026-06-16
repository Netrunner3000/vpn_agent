"""
doc_content.py — HTML documentation content for the in-app guide.
Rendered by QTextBrowser in doc_dialog.py.
The same content exists as docs/GUIDE.md for standalone reading.
"""

DOC_HTML = """<!DOCTYPE html>
<html>
<head>
<style>
body {
    background-color: #0f0f0f;
    color: #d0d0d0;
    font-family: -apple-system, "Helvetica Neue", Arial, sans-serif;
    font-size: 13px;
    line-height: 1.7;
    margin: 0;
    padding: 0 4px;
}
h1 { color: #00e5ff; font-size: 20px; border-bottom: 1px solid #1a2a2a; padding-bottom: 8px; margin-top: 24px; }
h2 { color: #90caf9; font-size: 16px; margin-top: 28px; border-bottom: 1px solid #1a1a1a; padding-bottom: 5px; }
h3 { color: #80cbc4; font-size: 13px; margin-top: 18px; font-weight: bold; }
h4 { color: #aaaaaa; font-size: 12px; margin-top: 14px; font-weight: bold; }
p  { margin: 8px 0; }
a  { color: #4fc3f7; }
code {
    background: #1a1a1a;
    color: #c5e1a5;
    padding: 2px 6px;
    border-radius: 3px;
    font-family: "Menlo", "Monaco", "Courier New", monospace;
    font-size: 11px;
}
pre {
    background: #111111;
    color: #c5e1a5;
    padding: 14px 16px;
    border-radius: 6px;
    border-left: 3px solid #2a3a2a;
    font-family: "Menlo", "Monaco", "Courier New", monospace;
    font-size: 11px;
    margin: 10px 0;
    white-space: pre-wrap;
}
ul, ol { padding-left: 22px; margin: 8px 0; }
li { margin: 4px 0; }
hr { border: none; border-top: 1px solid #1e1e1e; margin: 24px 0; }
table { border-collapse: collapse; width: 100%; margin: 12px 0; }
th { background: #1a1a1a; color: #90caf9; padding: 8px 12px; text-align: left; border: 1px solid #2a2a2a; font-size: 12px; }
td { padding: 7px 12px; border: 1px solid #1e1e1e; color: #cccccc; font-size: 12px; }
.warn  { color: #ff9800; font-weight: bold; }
.danger{ color: #f44336; font-weight: bold; }
.ok    { color: #66bb6a; font-weight: bold; }
.note  { color: #90caf9; }
.tip   { background: #0a1a0a; border-left: 3px solid #2e7d32; padding: 8px 12px; border-radius: 4px; margin: 10px 0; }
.warning-box { background: #1a0e00; border-left: 3px solid #ff6f00; padding: 8px 12px; border-radius: 4px; margin: 10px 0; }
.danger-box  { background: #1a0000; border-left: 3px solid #c62828; padding: 8px 12px; border-radius: 4px; margin: 10px 0; }
.toc { background: #111111; border: 1px solid #1e1e1e; border-radius: 6px; padding: 14px 18px; margin: 14px 0; }
.toc a { color: #80cbc4; text-decoration: none; }
.toc li { margin: 3px 0; font-size: 12px; }
</style>
</head>
<body>

<h1>VPN Agent — Complete Guide</h1>
<p>A personal VPN control center for managing WireGuard tunnels, monitoring health, and running your own private VPN infrastructure.</p>

<div class="toc">
<b style="color:#90caf9;">Contents</b>
<ol>
<li><a href="#overview">Overview</a></li>
<li><a href="#dashboard">Dashboard Reference</a></li>
<li><a href="#setup">First-Time Setup on macOS</a></li>
<li><a href="#profiles">VPN Profiles</a></li>
<li><a href="#vps">VPS Setup Guide</a></li>
<li><a href="#glinet">GL.iNet Router Integration</a></li>
<li><a href="#dns">DNS Leaks Explained</a></li>
<li><a href="#health">Health Monitor</a></li>
<li><a href="#killswitch">Kill Switch &amp; Safety</a></li>
<li><a href="#security">Security Best Practices</a></li>
<li><a href="#tips">Tips &amp; Tricks</a></li>
<li><a href="#troubleshoot">Troubleshooting</a></li>
</ol>
</div>

<hr>

<h2><a name="overview"></a>1. Overview</h2>
<p>VPN Agent is a standalone desktop app that gives you a control panel for your own WireGuard-based VPN infrastructure. Unlike commercial VPN apps, you own every server and hold every private key.</p>
<p><b>What it does:</b></p>
<ul>
<li>Shows your real-time public IP, country, and ISP</li>
<li>Detects which DNS resolvers your system is using (leak detection)</li>
<li>Measures latency to any VPN endpoint</li>
<li>Controls WireGuard tunnels (connect / disconnect / restart)</li>
<li>Monitors your connection health in the background and alerts you when things change</li>
<li>Supports multiple VPN profiles (home server, VPS nodes, routers)</li>
</ul>
<p><b>What it does NOT do:</b></p>
<ul>
<li>It is not a commercial VPN service</li>
<li>It does not manage VPN accounts or subscriptions</li>
<li>It does not provide servers — you bring your own (VPS, home server, GL.iNet router)</li>
</ul>

<hr>

<h2><a name="dashboard"></a>2. Dashboard Reference</h2>

<h3>Tunnel Indicator (top right)</h3>
<p>Shows which WireGuard interfaces are currently active on your system.</p>
<table>
<tr><th>Display</th><th>Meaning</th></tr>
<tr><td><span class="ok">● TUNNEL: WG0</span></td><td>Interface wg0 is active and traffic is routing through it</td></tr>
<tr><td><span class="note">● TUNNEL: NONE</span></td><td>No WireGuard tunnels detected — you are on your raw ISP connection</td></tr>
<tr><td><span class="note">● TUNNEL: UNKNOWN</span></td><td>Not yet checked — press Refresh Status</td></tr>
</table>
<div class="warning-box">If the indicator shows NONE when you expect a tunnel to be active, your traffic is NOT protected.</div>

<h3>Active Profile Dropdown</h3>
<p>Selects which VPN profile to use for Connect / Disconnect / Restart / Latency Test. Each profile maps to a WireGuard interface name and endpoint address. Add profiles by editing <code>config/vpn_profiles.json</code>.</p>

<h3>Public IP Panel</h3>
<ul>
<li><b>IP address</b> — Your outbound IP. When VPN is active, this should show your VPN server's IP, not your ISP's IP. If it still shows your home IP after connecting, your routing is not working.</li>
<li><b>Country</b> — Geographic location of the IP, detected via ipapi.co.</li>
<li><b>ISP</b> — The organisation that owns the IP. Should change to your VPS hosting provider when VPN is active.</li>
</ul>

<h3>DNS Status Panel</h3>
<ul>
<li><b>Status line</b> — Summary of the DNS check result. Green = known resolvers. Orange = possible leak risk.</li>
<li><b>Resolvers</b> — The actual DNS server IPs your system is sending queries to. When VPN is active, these should match what your WireGuard client config specifies under <code>DNS =</code>.</li>
</ul>
<div class="tip"><b>Tip:</b> If you see your ISP's DNS resolver IP here while VPN is connected, you have a DNS leak. Fix it by adding <code>DNS = 1.1.1.1</code> to your WireGuard client config.</div>

<h3>Latency Panel</h3>
<ul>
<li><b>Latency value</b> — Round-trip time to the selected profile's endpoint. Uses ICMP ping, falling back to TCP connect if ping is blocked.</li>
<li><b>Packet loss</b> — Percentage of ICMP packets that didn't return. Anything above 1% warrants investigation.</li>
</ul>
<table>
<tr><th>Latency</th><th>Interpretation</th></tr>
<tr><td><span class="ok">&lt; 50 ms</span></td><td>Excellent — local or nearby server</td></tr>
<tr><td><span class="warn">50–150 ms</span></td><td>Acceptable — distant server or loaded network</td></tr>
<tr><td><span class="danger">&gt; 150 ms</span></td><td>High — may cause slowdowns in real-time apps</td></tr>
</table>

<h3>Action Buttons</h3>
<table>
<tr><th>Button</th><th>What it does</th><th>Requires</th></tr>
<tr><td>Refresh Status</td><td>Re-runs all checks: IP, DNS, latency, tunnel state</td><td>Internet access</td></tr>
<tr><td>Connect</td><td>Brings up the selected profile's WireGuard tunnel via <code>sudo wg-quick up</code></td><td>wg-quick, sudo password, .conf file</td></tr>
<tr><td>Disconnect</td><td>Brings down the tunnel via <code>sudo wg-quick down</code></td><td>wg-quick, sudo password</td></tr>
<tr><td>Restart</td><td>Disconnect then reconnect — useful after config changes</td><td>Same as Connect</td></tr>
<tr><td>Test DNS Leak</td><td>Re-runs the DNS resolver check only</td><td>Internet access</td></tr>
<tr><td>Test Latency</td><td>Re-runs ping to the selected profile endpoint</td><td>Network access to endpoint</td></tr>
<tr><td>Docs</td><td>Opens this guide</td><td>Nothing</td></tr>
</table>

<h3>Activity Log</h3>
<p>Shows a running log of events, status changes, and warnings. Most recent entries appear at the top. The log is not saved to disk in Phase 1 — it resets each session.</p>

<hr>

<h2><a name="setup"></a>3. First-Time Setup on macOS</h2>

<h3>3.1 Install Homebrew (if not already installed)</h3>
<pre>/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"</pre>

<h3>3.2 Install WireGuard Tools</h3>
<pre>brew install wireguard-tools</pre>
<p>This installs <code>wg</code> and <code>wg-quick</code>, the command-line tools the app uses to control tunnels. Without this, Connect / Disconnect buttons will report an error.</p>

<h3>3.3 Verify installation</h3>
<pre>which wg-quick
wg --version</pre>

<h3>3.4 Activate the Python venv</h3>
<pre>source /Users/as/Documents/lab/vpn_agent/venv/bin/activate</pre>
<p>Do this in every new terminal tab before running the app.</p>

<h3>3.5 Run the app</h3>
<pre>cd /Users/as/Documents/lab/vpn_agent
python main.py</pre>

<hr>

<h2><a name="profiles"></a>4. VPN Profiles</h2>
<p>Profiles are stored in <code>config/vpn_profiles.json</code>. Each profile maps a friendly name to a WireGuard interface and endpoint.</p>
<pre>{
  "profiles": [
    {
      "name": "VPS Node 1",
      "endpoint": "203.0.113.10",
      "port": 51820,
      "interface": "wg2",
      "notes": "Hetzner VPS, Germany"
    }
  ],
  "active_profile": "VPS Node 1"
}</pre>

<table>
<tr><th>Field</th><th>Meaning</th></tr>
<tr><td>name</td><td>Display name in the dropdown</td></tr>
<tr><td>endpoint</td><td>IP or hostname of the VPN server — used for latency tests</td></tr>
<tr><td>port</td><td>WireGuard UDP port on the server (default 51820)</td></tr>
<tr><td>interface</td><td>WireGuard interface name on your Mac (must match your .conf filename)</td></tr>
<tr><td>notes</td><td>Optional description for your reference</td></tr>
</table>

<div class="tip"><b>Naming convention:</b> If your WireGuard config file is <code>/etc/wireguard/wg2.conf</code>, your interface name is <code>wg2</code>.</div>

<hr>

<h2><a name="vps"></a>5. VPS Setup Guide</h2>
<p>A VPS (Virtual Private Server) is a rented Linux server on the internet that acts as your WireGuard server. You route your traffic through it so your public IP becomes the VPS's IP.</p>

<h3>5.1 Choose a VPS Provider</h3>
<table>
<tr><th>Provider</th><th>Price</th><th>Notes</th></tr>
<tr><td>Hetzner Cloud</td><td>~€4/mo</td><td>Excellent value, EU/US locations, fast network</td></tr>
<tr><td>Vultr</td><td>~$6/mo</td><td>Many global locations, good for latency testing</td></tr>
<tr><td>DigitalOcean</td><td>~$6/mo</td><td>Reliable, good documentation</td></tr>
<tr><td>Oracle Cloud Free</td><td>Free</td><td>2 free VMs permanently — Ampere ARM or x86</td></tr>
<tr><td>Linode / Akamai</td><td>~$5/mo</td><td>Solid performance, global presence</td></tr>
</table>
<p><b>Recommended OS:</b> Ubuntu 22.04 LTS or Debian 12. Both have WireGuard in their standard repos.</p>
<p><b>Recommended specs:</b> 1 vCPU, 512MB RAM — more than enough for personal WireGuard.</p>

<h3>5.2 Initial Server Setup</h3>
<p>Connect via SSH immediately after provisioning:</p>
<pre>ssh root@YOUR_VPS_IP</pre>
<p>Update the system first:</p>
<pre>apt update && apt upgrade -y</pre>

<h3>5.3 Install WireGuard on the Server</h3>
<pre>apt install wireguard -y</pre>

<h3>5.4 Generate Key Pairs</h3>
<p><b>On the server</b> — generate the server key pair:</p>
<pre>cd /etc/wireguard
wg genkey | tee server_private.key | wg pubkey > server_public.key
chmod 600 server_private.key
echo "Server private key:" && cat server_private.key
echo "Server public key:"  && cat server_public.key</pre>
<p>Copy both keys somewhere safe. You need them in the next steps.</p>
<p><b>On your Mac</b> — generate the client key pair:</p>
<pre>mkdir -p ~/wireguard-keys
cd ~/wireguard-keys
wg genkey | tee client_private.key | wg pubkey > client_public.key
echo "Client private key:" && cat client_private.key
echo "Client public key:"  && cat client_public.key</pre>

<div class="danger-box"><b>Never share private keys.</b> They grant full access to the tunnel. Store them in a secure location. If a key is compromised, generate a new pair and update both server and client configs.</div>

<h3>5.5 Create Server Config</h3>
<p>On the server, find your primary network interface name first:</p>
<pre>ip link show | grep -v lo | head -5</pre>
<p>Common names: <code>eth0</code>, <code>ens3</code>, <code>enp1s0</code>. Use the right one in the PostUp/PostDown rules below.</p>
<pre>nano /etc/wireguard/wg0.conf</pre>
<p>Paste this, replacing the placeholders:</p>
<pre>[Interface]
Address    = 10.8.0.1/24
ListenPort = 51820
PrivateKey = PASTE_SERVER_PRIVATE_KEY_HERE

# Enable NAT — replace eth0 with your actual interface name
PostUp   = iptables -A FORWARD -i %i -j ACCEPT; iptables -A FORWARD -o %i -j ACCEPT; iptables -t nat -A POSTROUTING -o eth0 -j MASQUERADE
PostDown = iptables -D FORWARD -i %i -j ACCEPT; iptables -D FORWARD -o %i -j ACCEPT; iptables -t nat -D POSTROUTING -o eth0 -j MASQUERADE

[Peer]
# Your Mac client
PublicKey  = PASTE_CLIENT_PUBLIC_KEY_HERE
AllowedIPs = 10.8.0.2/32</pre>

<h3>5.6 Enable IP Forwarding</h3>
<pre>echo "net.ipv4.ip_forward=1"          >> /etc/sysctl.conf
echo "net.ipv6.conf.all.forwarding=1" >> /etc/sysctl.conf
sysctl -p</pre>

<h3>5.7 Configure the Firewall (UFW)</h3>
<div class="danger-box"><b>Always allow SSH before enabling UFW</b> — otherwise you will lock yourself out.</div>
<pre>ufw allow 22/tcp      # SSH — keep this open!
ufw allow 51820/udp   # WireGuard
ufw --force enable
ufw status</pre>

<h3>5.8 Start WireGuard on the Server</h3>
<pre>wg-quick up wg0
systemctl enable wg-quick@wg0   # auto-start after reboot
wg show                          # verify it's running</pre>

<h3>5.9 Create Client Config on Your Mac</h3>
<pre>sudo nano /etc/wireguard/wg2.conf</pre>
<p>Paste this, replacing placeholders:</p>
<pre>[Interface]
PrivateKey = PASTE_CLIENT_PRIVATE_KEY_HERE
Address    = 10.8.0.2/32
DNS        = 1.1.1.1

[Peer]
PublicKey           = PASTE_SERVER_PUBLIC_KEY_HERE
Endpoint            = YOUR_VPS_PUBLIC_IP:51820
AllowedIPs          = 0.0.0.0/0, ::/0
PersistentKeepalive = 25</pre>

<table>
<tr><th>Setting</th><th>Why it matters</th></tr>
<tr><td>DNS = 1.1.1.1</td><td>Forces DNS through the tunnel — prevents DNS leaks</td></tr>
<tr><td>AllowedIPs = 0.0.0.0/0</td><td>Routes ALL traffic through VPN (full tunnel). Use a specific subnet for split-tunnel.</td></tr>
<tr><td>PersistentKeepalive = 25</td><td>Sends a keepalive packet every 25s — essential for staying connected through NAT (your home router)</td></tr>
</table>

<h3>5.10 Test the Connection</h3>
<pre># Connect the tunnel
sudo wg-quick up wg2

# Check your public IP — should now show the VPS IP
curl https://api.ipify.org

# Verify handshake with server
wg show wg2

# Disconnect when done testing
sudo wg-quick down wg2</pre>

<h3>5.11 Add to VPN Agent</h3>
<p>Open <code>config/vpn_profiles.json</code> and update the VPS Node 1 entry:</p>
<pre>{
  "name": "VPS Node 1",
  "endpoint": "YOUR_VPS_IP",
  "port": 51820,
  "interface": "wg2",
  "notes": "My Hetzner VPS"
}</pre>
<p>Restart the app — the profile appears in the dropdown and Connect/Disconnect will work.</p>

<hr>

<h2><a name="glinet"></a>6. GL.iNet Router Integration</h2>
<p>Your GL.iNet Flint 2 and XE300 have built-in WireGuard client support. This means you can route all devices on the router's network through VPN without configuring each device individually.</p>

<h3>6.1 Access the Router Admin Panel</h3>
<pre>http://192.168.8.1</pre>

<h3>6.2 Add a WireGuard Profile</h3>
<ol>
<li>Go to <b>VPN → WireGuard Client</b></li>
<li>Click <b>Add</b> or <b>Import Config</b></li>
<li>Paste your client <code>.conf</code> file content or upload it</li>
<li>Save and connect</li>
</ol>
<div class="tip"><b>Tip:</b> The router holds its own key pair, separate from your Mac's. Generate a new client key pair for the router and add it as a separate <code>[Peer]</code> block on your server config.</div>

<h3>6.3 VPN Agent Profile for GL.iNet</h3>
<p>The GL.iNet Flint 2 profile in VPN Agent uses the router's local IP as the endpoint. This lets you ping the router to check it's reachable, but Connect/Disconnect in the app won't control the router — you do that via the router's web UI or GL.iNet mobile app.</p>

<hr>

<h2><a name="dns"></a>7. DNS Leaks Explained</h2>
<p>A DNS leak happens when your DNS queries (domain name lookups) bypass the VPN tunnel and go directly to your ISP's resolver — revealing which websites you visit even when your traffic appears hidden.</p>

<h3>How it happens</h3>
<ul>
<li>WireGuard is connected and routing IP traffic through the tunnel</li>
<li>But macOS still sends DNS queries to the ISP resolver it learned from DHCP</li>
<li>Your ISP can see every domain you visit</li>
</ul>

<h3>How to fix it</h3>
<p>Always include <code>DNS = 1.1.1.1</code> (or your preferred resolver) in your WireGuard client <code>.conf</code> file. This tells wg-quick to push a DNS server to your system when the tunnel comes up.</p>

<h3>What the DNS check shows</h3>
<ul>
<li><span class="ok">DNS OK — known public resolvers</span>: Your resolvers are Cloudflare, Google, Quad9, or OpenDNS. No obvious leak.</li>
<li><span class="warn">Mixed resolvers</span>: Some resolvers are unknown — could be VPN provider's private resolver (normal) or could be ISP (investigate).</li>
<li><span class="danger">Possible DNS leak</span>: All resolvers are unknown and don't match any known public resolver. Check your WireGuard DNS setting.</li>
</ul>
<div class="warning-box"><b>Note:</b> If your VPN server uses its own private DNS resolver (e.g. 10.8.0.1), it will show as "Unknown" in this app. That's fine — the app doesn't know your server's resolver IP. Check manually by comparing the resolver IP to your WireGuard tunnel address range.</div>

<hr>

<h2><a name="health"></a>8. Health Monitor</h2>
<p>The health monitor runs in the background every 30 seconds and checks three things:</p>

<h3>8.1 IP Change Detection</h3>
<p>If your public IP changes unexpectedly, a warning appears. This usually means the VPN tunnel dropped and your traffic is now going through your ISP directly.</p>

<h3>8.2 DNS Change Detection</h3>
<p>If the DNS resolvers your system uses change unexpectedly, a warning appears. This can happen when:</p>
<ul>
<li>VPN connects or disconnects (expected — can be dismissed)</li>
<li>Router updates DHCP settings (investigate)</li>
<li>Something hijacked your DNS (serious — check immediately)</li>
</ul>

<h3>8.3 Tunnel Drop Detection</h3>
<p>The monitor watches whichever interfaces correspond to the selected profile. If a tunnel that was active goes offline, a red warning banner appears at the top of the window.</p>
<div class="danger-box"><b>When a tunnel drops:</b> Your traffic immediately reverts to your ISP connection. No kill switch is active by default. Press Connect to restore the tunnel.</div>

<h3>8.4 Warning Banner</h3>
<p>Red banners appear at the top of the window when the health monitor detects a problem. Click <b>Dismiss</b> to hide the banner after you've read it. The activity log always keeps a full history of all warnings.</p>

<hr>

<h2><a name="killswitch"></a>9. Kill Switch &amp; Safety</h2>
<p>A kill switch blocks all internet traffic if the VPN drops, ensuring no traffic ever leaks to your ISP. WireGuard on macOS does not include a built-in kill switch.</p>

<h3>9.1 What this app does</h3>
<ul>
<li>Detects tunnel drops within 30 seconds and shows a warning</li>
<li>Logs the event with a timestamp</li>
<li>Lets you reconnect with one click</li>
</ul>

<h3>9.2 Manual kill switch via macOS PF (Advanced)</h3>
<p>macOS has a built-in packet filter (PF) that can block traffic outside the tunnel. This is complex and requires root. A basic example:</p>
<pre># Create /etc/pf-vpn-killswitch.conf:
# Block everything by default
block all
# Allow loopback
pass quick on lo0 all
# Allow WireGuard handshake to VPS (replace with your VPS IP and port)
pass out quick proto udp to YOUR_VPS_IP port 51820
# Allow all traffic on the WireGuard interface
pass quick on wg2 all

# Activate:
sudo pfctl -ef /etc/pf-vpn-killswitch.conf

# Deactivate:
sudo pfctl -d</pre>
<div class="warning-box"><b>Be careful:</b> If you activate PF rules while the VPN is down and your VPS IP is wrong, you will lose all internet access. Keep a way to disable PF (another terminal, or physical access) before enabling.</div>

<h3>9.3 Practical safety habits</h3>
<ul>
<li>Check the Tunnel Indicator before any sensitive activity</li>
<li>After connecting, always verify the Public IP changed to the VPS IP</li>
<li>After connecting, run Test DNS Leak to confirm resolvers changed</li>
<li>Keep the app visible while working — the warning banner is your safety net</li>
</ul>

<hr>

<h2><a name="security"></a>10. Security Best Practices</h2>

<h3>Key Management</h3>
<ul>
<li>Never share private keys. Treat them like passwords.</li>
<li>Store keys in files with permission 600: <code>chmod 600 /etc/wireguard/*.conf</code></li>
<li>Rotate keys every few months — generate a new pair, update server and client, delete old</li>
<li>Each device should have its own key pair — never reuse a client key across devices</li>
</ul>

<h3>VPS Hardening</h3>
<ul>
<li>Disable password SSH login: <code>PasswordAuthentication no</code> in <code>/etc/ssh/sshd_config</code></li>
<li>Use SSH key authentication only</li>
<li>Consider changing the SSH port from 22 to something non-standard</li>
<li>Install fail2ban to block brute-force attempts: <code>apt install fail2ban -y</code></li>
<li>Keep the OS updated: <code>apt update && apt upgrade -y</code> weekly</li>
<li>Use UFW to block all ports except what you need (22/tcp and 51820/udp)</li>
</ul>

<h3>WireGuard Config File Permissions</h3>
<pre>sudo chmod 600 /etc/wireguard/*.conf
sudo chown root:root /etc/wireguard/*.conf</pre>

<h3>Verify Your Setup</h3>
<p>After connecting, always confirm these three things:</p>
<ol>
<li>Public IP shows the VPS IP (not your home IP)</li>
<li>ISP field shows your VPS provider (not Virgin Media)</li>
<li>DNS resolvers changed from your ISP's to the ones in your WireGuard config</li>
</ol>

<hr>

<h2><a name="tips"></a>11. Tips &amp; Tricks</h2>

<h3>Checking if the handshake is alive</h3>
<pre>watch -n 2 wg show</pre>
<p>The "latest handshake" timestamp should update every ~25 seconds if PersistentKeepalive is set. If it's stale (more than 3 minutes), the tunnel is broken.</p>

<h3>Diagnosing connection problems on the server</h3>
<pre>journalctl -u wg-quick@wg0 -f</pre>
<p>Follow live logs from WireGuard on the server. Look for handshake events and errors.</p>

<h3>Find your server's primary network interface</h3>
<pre>ip route | grep default</pre>
<p>The interface after "dev" is what you put in PostUp/PostDown rules.</p>

<h3>Test connectivity through the tunnel</h3>
<pre>curl https://api.ipify.org          # public IP
curl https://ipapi.co/json/         # full details
dig +short myip.opendns.com @resolver1.opendns.com  # DNS-based IP check</pre>

<h3>Check if WireGuard port is reachable from your Mac</h3>
<pre>nc -zvu YOUR_VPS_IP 51820</pre>
<p>Should return "Connection to ... succeeded". If it times out, check your UFW rules on the server.</p>

<h3>Split tunneling (route only specific traffic through VPN)</h3>
<p>Change <code>AllowedIPs</code> in your client config to specific subnets instead of <code>0.0.0.0/0</code>:</p>
<pre># Only route traffic to 10.8.0.0/24 through VPN (the VPN subnet)
AllowedIPs = 10.8.0.0/24</pre>
<p>This is useful if you want to keep local traffic on your ISP while accessing private VPN resources.</p>

<h3>Multiple VPS nodes</h3>
<p>Add each node as a separate profile in <code>config/vpn_profiles.json</code> with a different interface name (wg2, wg3, wg4...). Each needs its own <code>.conf</code> file in <code>/etc/wireguard/</code>.</p>

<h3>Port choice</h3>
<p>Port 51820 is the WireGuard default and may be filtered by some networks (hotels, corporate). Consider using port 443 (HTTPS port) or 53 (DNS port) on your server — these are almost never filtered. Change <code>ListenPort</code> on the server and <code>Endpoint</code> port on the client to match.</p>

<h3>GL.iNet as a travel router</h3>
<p>The GL-XE300 is a portable 4G router. Configure it with a WireGuard client profile and all devices connected to it will route through your VPN automatically — useful when travelling.</p>

<h3>Monitor server traffic stats</h3>
<pre># On the server — see bytes transferred per peer
wg show wg0 transfer</pre>

<hr>

<h2><a name="troubleshoot"></a>12. Troubleshooting</h2>

<table>
<tr><th>Problem</th><th>Cause</th><th>Fix</th></tr>
<tr><td>Connect shows "wg-quick not found"</td><td>wireguard-tools not installed</td><td><code>brew install wireguard-tools</code></td></tr>
<tr><td>Connect shows "Permission denied"</td><td>sudo required for wg-quick</td><td>macOS will prompt for your password — allow it</td></tr>
<tr><td>No handshake after connecting</td><td>Server firewall blocking UDP 51820</td><td>Check UFW on server: <code>ufw status</code></td></tr>
<tr><td>IP doesn't change after connecting</td><td>AllowedIPs not routing all traffic</td><td>Set <code>AllowedIPs = 0.0.0.0/0, ::/0</code> in client config</td></tr>
<tr><td>DNS leak detected after connecting</td><td>DNS not set in client config</td><td>Add <code>DNS = 1.1.1.1</code> to client <code>.conf</code></td></tr>
<tr><td>Connection drops after a few minutes</td><td>NAT timeout on home router</td><td>Add <code>PersistentKeepalive = 25</code> to client config</td></tr>
<tr><td>Very high latency (&gt;300ms)</td><td>Server geographically far, or overloaded</td><td>Try a server in a closer region</td></tr>
<tr><td>Public IP check shows "No connection"</td><td>No internet or ipify.org blocked</td><td>Check network, try a different IP check URL</td></tr>
<tr><td>Tunnel shows NONE but wg is running</td><td>/var/run/wireguard/ not populated</td><td>Use WireGuard.app instead of wg-quick, or check file permissions</td></tr>
<tr><td>wg show returns nothing</td><td>No tunnels active, or wg not in PATH</td><td>Activate venv, verify <code>which wg</code> returns a path</td></tr>
</table>

<h3>Useful diagnostic commands</h3>
<pre># Check all active WireGuard interfaces
wg show all

# Follow system log for WireGuard events (macOS)
log stream --predicate 'process == "wireguard-go"' --level debug

# Check routing table (verify VPN route is present)
netstat -rn | grep wg

# Flush DNS cache after config changes
sudo dscacheutil -flushcache && sudo killall -HUP mDNSResponder</pre>

<hr>
<p style="color:#444444; font-size:11px; text-align:center;">VPN Agent — Personal VPN Control Center &nbsp;|&nbsp; Phase 1</p>

</body>
</html>"""

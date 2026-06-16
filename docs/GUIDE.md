# VPN Agent — Complete Guide

A personal VPN control center for managing WireGuard tunnels, monitoring health, and running your own private VPN infrastructure.

---

## Contents

1. [Overview](#1-overview)
2. [Dashboard Reference](#2-dashboard-reference)
3. [First-Time Setup on macOS](#3-first-time-setup-on-macos)
4. [VPN Profiles](#4-vpn-profiles)
5. [VPS Setup Guide](#5-vps-setup-guide)
6. [GL.iNet Router Integration](#6-glinet-router-integration)
7. [DNS Leaks Explained](#7-dns-leaks-explained)
8. [Health Monitor](#8-health-monitor)
9. [Kill Switch & Safety](#9-kill-switch--safety)
10. [Security Best Practices](#10-security-best-practices)
11. [Tips & Tricks](#11-tips--tricks)
12. [Troubleshooting](#12-troubleshooting)

---

## 1. Overview

VPN Agent is a standalone desktop app that gives you a control panel for your own WireGuard-based VPN infrastructure. Unlike commercial VPN apps, you own every server and hold every private key.

**What it does:**
- Shows your real-time public IP, country, and ISP
- Detects which DNS resolvers your system is using (leak detection)
- Measures latency to any VPN endpoint
- Controls WireGuard tunnels (connect / disconnect / restart)
- Monitors your connection health in the background and alerts you when things change
- Supports multiple VPN profiles (home server, VPS nodes, routers)

**What it does NOT do:**
- It is not a commercial VPN service
- It does not manage VPN accounts or subscriptions
- It does not provide servers — you bring your own (VPS, home server, GL.iNet router)

---

## 2. Dashboard Reference

### Tunnel Indicator (top right)

Shows which WireGuard interfaces are currently active on your system.

| Display | Meaning |
|---|---|
| `● TUNNEL: WG0` | Interface wg0 is active — traffic is routing through it |
| `● TUNNEL: NONE` | No tunnels — you are on your raw ISP connection |
| `● TUNNEL: UNKNOWN` | Not yet checked — press Refresh Status |

> **Warning:** If the indicator shows NONE when you expect a tunnel to be active, your traffic is NOT protected.

### Active Profile Dropdown

Selects which VPN profile to use for Connect / Disconnect / Restart / Latency Test. Profiles are defined in `config/vpn_profiles.json`.

### Public IP Panel

- **IP address** — Your outbound IP. Should show your VPN server's IP when connected.
- **Country** — Geographic location of the IP (via ipapi.co).
- **ISP** — The organisation that owns the IP. Should change to your hosting provider when VPN is active.

### DNS Status Panel

- **Status line** — Summary: green = known resolvers, orange = possible leak.
- **Resolvers** — The actual DNS server IPs your system is querying. Should match what your WireGuard config specifies under `DNS =`.

> **Tip:** If you see your ISP's DNS resolver IP here while VPN is connected, you have a DNS leak. Fix it by adding `DNS = 1.1.1.1` to your WireGuard client config.

### Latency Panel

| Latency | Interpretation |
|---|---|
| < 50 ms | Excellent — local or nearby server |
| 50–150 ms | Acceptable — distant server or loaded network |
| > 150 ms | High — may cause slowdowns in real-time apps |

### Action Buttons

| Button | What it does | Requires |
|---|---|---|
| Refresh Status | Re-runs all checks | Internet access |
| Connect | Brings up the WireGuard tunnel (`sudo wg-quick up`) | wg-quick, sudo, .conf file |
| Disconnect | Brings down the tunnel (`sudo wg-quick down`) | wg-quick, sudo |
| Restart | Disconnect then reconnect | Same as Connect |
| Test DNS Leak | Re-runs the DNS resolver check | Internet access |
| Test Latency | Pings the selected profile endpoint | Network access |
| Docs | Opens this guide | Nothing |

---

## 3. First-Time Setup on macOS

### 3.1 Install Homebrew (if not already installed)

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

### 3.2 Install WireGuard Tools

```bash
brew install wireguard-tools
```

This installs `wg` and `wg-quick`. Without this, Connect / Disconnect buttons will report an error.

### 3.3 Verify installation

```bash
which wg-quick
wg --version
```

### 3.4 Activate the Python venv

```bash
source /Users/as/Documents/python_projects/vpn_agent/venv/bin/activate
```

Do this in every new terminal tab before running the app.

### 3.5 Run the app

```bash
cd /Users/as/Documents/python_projects/vpn_agent
python main.py
```

---

## 4. VPN Profiles

Profiles are stored in `config/vpn_profiles.json`:

```json
{
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
}
```

| Field | Meaning |
|---|---|
| name | Display name in the dropdown |
| endpoint | IP or hostname of the VPN server |
| port | WireGuard UDP port on the server (default 51820) |
| interface | WireGuard interface name on your Mac — must match the .conf filename |
| notes | Optional description |

> **Naming convention:** If your config file is `/etc/wireguard/wg2.conf`, your interface name is `wg2`.

---

## 5. VPS Setup Guide

A VPS (Virtual Private Server) is a rented Linux server that acts as your WireGuard server. Your traffic routes through it so your public IP becomes the VPS's IP.

### 5.1 Choose a Provider

| Provider | Price | Notes |
|---|---|---|
| Hetzner Cloud | ~€4/mo | Excellent value, EU/US, fast network |
| Vultr | ~$6/mo | Many global locations |
| DigitalOcean | ~$6/mo | Reliable, good docs |
| Oracle Cloud Free | Free | 2 free VMs permanently |
| Linode / Akamai | ~$5/mo | Solid global presence |

**Recommended OS:** Ubuntu 22.04 LTS or Debian 12
**Recommended specs:** 1 vCPU, 512MB RAM — more than enough for personal WireGuard.

### 5.2 Initial Server Setup

```bash
ssh root@YOUR_VPS_IP
apt update && apt upgrade -y
```

### 5.3 Install WireGuard on the Server

```bash
apt install wireguard -y
```

### 5.4 Generate Key Pairs

**On the server — server keys:**

```bash
cd /etc/wireguard
wg genkey | tee server_private.key | wg pubkey > server_public.key
chmod 600 server_private.key
echo "Server private key:" && cat server_private.key
echo "Server public key:"  && cat server_public.key
```

**On your Mac — client keys:**

```bash
mkdir -p ~/wireguard-keys && cd ~/wireguard-keys
wg genkey | tee client_private.key | wg pubkey > client_public.key
echo "Client private key:" && cat client_private.key
echo "Client public key:"  && cat client_public.key
```

> **NEVER share private keys.** If a key is compromised, generate a new pair and update both configs.

### 5.5 Find Your Server's Network Interface

```bash
ip route | grep default
```

The interface after `dev` (commonly `eth0`, `ens3`, `enp1s0`) goes into PostUp/PostDown rules.

### 5.6 Create Server Config

```bash
nano /etc/wireguard/wg0.conf
```

```ini
[Interface]
Address    = 10.8.0.1/24
ListenPort = 51820
PrivateKey = PASTE_SERVER_PRIVATE_KEY_HERE

# Replace eth0 with your actual interface name
PostUp   = iptables -A FORWARD -i %i -j ACCEPT; iptables -A FORWARD -o %i -j ACCEPT; iptables -t nat -A POSTROUTING -o eth0 -j MASQUERADE
PostDown = iptables -D FORWARD -i %i -j ACCEPT; iptables -D FORWARD -o %i -j ACCEPT; iptables -t nat -D POSTROUTING -o eth0 -j MASQUERADE

[Peer]
# Your Mac client
PublicKey  = PASTE_CLIENT_PUBLIC_KEY_HERE
AllowedIPs = 10.8.0.2/32
```

### 5.7 Enable IP Forwarding

```bash
echo "net.ipv4.ip_forward=1"          >> /etc/sysctl.conf
echo "net.ipv6.conf.all.forwarding=1" >> /etc/sysctl.conf
sysctl -p
```

### 5.8 Configure the Firewall

> **Always allow SSH before enabling UFW — otherwise you will lock yourself out.**

```bash
ufw allow 22/tcp      # SSH — keep this open!
ufw allow 51820/udp   # WireGuard
ufw --force enable
ufw status
```

### 5.9 Start WireGuard on the Server

```bash
wg-quick up wg0
systemctl enable wg-quick@wg0   # auto-start after reboot
wg show                          # verify it's running
```

### 5.10 Create Client Config on Your Mac

```bash
sudo nano /etc/wireguard/wg2.conf
```

```ini
[Interface]
PrivateKey = PASTE_CLIENT_PRIVATE_KEY_HERE
Address    = 10.8.0.2/32
DNS        = 1.1.1.1

[Peer]
PublicKey           = PASTE_SERVER_PUBLIC_KEY_HERE
Endpoint            = YOUR_VPS_PUBLIC_IP:51820
AllowedIPs          = 0.0.0.0/0, ::/0
PersistentKeepalive = 25
```

| Setting | Why it matters |
|---|---|
| `DNS = 1.1.1.1` | Forces DNS through the tunnel — prevents DNS leaks |
| `AllowedIPs = 0.0.0.0/0` | Routes ALL traffic through VPN (full tunnel) |
| `PersistentKeepalive = 25` | Sends keepalive every 25s — essential for NAT traversal |

### 5.11 Test the Connection

```bash
sudo wg-quick up wg2
curl https://api.ipify.org          # should show VPS IP
wg show wg2                         # verify handshake
sudo wg-quick down wg2
```

### 5.12 Add to VPN Agent

Open `config/vpn_profiles.json` and update VPS Node 1:

```json
{
  "name": "VPS Node 1",
  "endpoint": "YOUR_VPS_IP",
  "port": 51820,
  "interface": "wg2",
  "notes": "My Hetzner VPS"
}
```

Restart the app — Connect/Disconnect will now control this tunnel.

---

## 6. GL.iNet Router Integration

Your GL.iNet Flint 2 and XE300 have built-in WireGuard client support. All devices connected to the router will route through VPN without individual configuration.

### Access the Router Admin Panel

```
http://192.168.8.1
```

### Add a WireGuard Profile

1. Go to **VPN → WireGuard Client**
2. Click **Add** or **Import Config**
3. Paste your client `.conf` file content
4. Save and connect

> **Tip:** Generate a separate key pair for the router. Add it as a second `[Peer]` block on the server. Never reuse the same private key across devices.

---

## 7. DNS Leaks Explained

A DNS leak happens when DNS queries bypass the VPN tunnel and go directly to your ISP's resolver — revealing which websites you visit even when your IP appears hidden.

### How to fix it

Always include `DNS = 1.1.1.1` in your WireGuard client `.conf`. This forces `wg-quick` to update your system's resolver when the tunnel comes up.

### What the DNS check shows

| Status | Meaning |
|---|---|
| DNS OK — known public resolvers | Cloudflare, Google, Quad9 detected. No obvious leak. |
| Mixed resolvers | Some unknown — could be VPN provider's private resolver (normal) or ISP (investigate) |
| Possible DNS leak | All resolvers unknown. Check your WireGuard DNS setting. |

> **Note:** If your VPN server uses a private resolver (e.g. `10.8.0.1`), it will show as "Unknown". That's fine — verify it matches your WireGuard tunnel subnet manually.

---

## 8. Health Monitor

Runs in the background every 30 seconds and checks three things:

### IP Change Detection
If your public IP changes unexpectedly, a warning appears. Usually means the VPN dropped.

### DNS Change Detection
If resolvers change unexpectedly, a warning appears. Can be expected (VPN connected/disconnected) or suspicious (investigate).

### Tunnel Drop Detection
Watches whichever interfaces the selected profile uses. If a tunnel that was active goes offline, a red warning banner appears at the top of the window.

> **When a tunnel drops:** Your traffic immediately reverts to your ISP. No kill switch is active by default. Press Connect to restore the tunnel.

---

## 9. Kill Switch & Safety

WireGuard on macOS does not include a built-in kill switch.

### What this app does

- Detects tunnel drops within 30 seconds
- Shows a prominent red warning banner
- Logs the event with details
- Lets you reconnect with one click

### Manual kill switch via macOS PF (Advanced)

```bash
# Create /etc/pf-vpn-killswitch.conf:
# Block everything by default
block all
# Allow loopback
pass quick on lo0 all
# Allow WireGuard handshake to VPS only
pass out quick proto udp to YOUR_VPS_IP port 51820
# Allow all traffic on the WireGuard interface
pass quick on wg2 all

# Activate:
sudo pfctl -ef /etc/pf-vpn-killswitch.conf

# Deactivate:
sudo pfctl -d
```

> **Be careful:** If PF is active and VPN is down with the wrong VPS IP, you lose all internet access. Test with a fallback ready.

### Practical safety habits

1. Check the Tunnel Indicator before sensitive activity
2. After connecting, verify the Public IP changed to the VPS IP
3. After connecting, run Test DNS Leak to confirm resolvers changed
4. Keep the app visible — the warning banner is your safety net

---

## 10. Security Best Practices

### Key Management
- Never share private keys — treat them like passwords
- Permissions on config files: `sudo chmod 600 /etc/wireguard/*.conf`
- Each device gets its own key pair — never reuse
- Rotate keys every few months

### VPS Hardening
- Disable password SSH: `PasswordAuthentication no` in `/etc/ssh/sshd_config`
- Use SSH key authentication only
- Consider changing SSH port from 22 to non-standard
- Install fail2ban: `apt install fail2ban -y`
- Keep OS updated: `apt update && apt upgrade -y` weekly
- UFW: only allow 22/tcp and 51820/udp

### Verify Your Setup After Connecting
1. Public IP shows the VPS IP (not your home IP)
2. ISP field shows your VPS provider (not Virgin Media)
3. DNS resolvers changed from ISP's to the ones in your WireGuard config

---

## 11. Tips & Tricks

### Check if handshake is alive

```bash
watch -n 2 wg show
```

The "latest handshake" should update every ~25s if PersistentKeepalive is set. If stale (>3 minutes), the tunnel is broken.

### Follow server logs live

```bash
journalctl -u wg-quick@wg0 -f
```

### Test connectivity through the tunnel

```bash
curl https://api.ipify.org
curl https://ipapi.co/json/
dig +short myip.opendns.com @resolver1.opendns.com
```

### Check if WireGuard port is reachable

```bash
nc -zvu YOUR_VPS_IP 51820
```

Should say "Connection succeeded". If it times out, check UFW on the server.

### Split tunneling

Change `AllowedIPs` to route only specific traffic through VPN:

```ini
# Only VPN subnet — local traffic stays on ISP
AllowedIPs = 10.8.0.0/24
```

### Port choice for filtered networks (hotels, corporate)

Change `ListenPort` on server and `Endpoint` port on client to:
- `443` — HTTPS port, almost never filtered
- `53` — DNS port, rarely filtered

### Monitor server transfer stats

```bash
wg show wg0 transfer
```

### Flush DNS cache after config changes

```bash
sudo dscacheutil -flushcache && sudo killall -HUP mDNSResponder
```

---

## 12. Troubleshooting

| Problem | Cause | Fix |
|---|---|---|
| Connect: "wg-quick not found" | wireguard-tools not installed | `brew install wireguard-tools` |
| Connect: "Permission denied" | sudo required | macOS will prompt — allow it |
| No handshake after connecting | Server firewall blocking UDP 51820 | Check UFW on server: `ufw status` |
| IP doesn't change after connecting | AllowedIPs not routing all traffic | Set `AllowedIPs = 0.0.0.0/0, ::/0` |
| DNS leak after connecting | DNS not set in client config | Add `DNS = 1.1.1.1` to client `.conf` |
| Connection drops after minutes | NAT timeout on home router | Add `PersistentKeepalive = 25` |
| Very high latency (>300ms) | Server too far or overloaded | Try a closer region |
| "No connection" on IP check | No internet or ipify.org blocked | Check network connection |
| Tunnel shows NONE but wg is running | `/var/run/wireguard/` not populated | Verify wg-quick is managing the interface |

### Useful diagnostic commands

```bash
# All active WireGuard interfaces
wg show all

# Follow WireGuard logs on macOS
log stream --predicate 'process == "wireguard-go"' --level debug

# Check routing table for VPN route
netstat -rn | grep wg

# Flush DNS cache
sudo dscacheutil -flushcache && sudo killall -HUP mDNSResponder
```

---

*VPN Agent — Personal VPN Control Center | Phase 1*

# SocketCAN Traffic Shaper & Analyzer

<!-- > Incremental README — we’ll grow this as the project evolves. -->

<!-- > New to CAN? Read the **[CAN basics](docs/can-basics.md)** primer. -->

Minimal toolkit to **analyze** CAN traffic and **shape** (rate-limit/drop/remap) frames.
Targets Linux **SocketCAN** (e.g., `can0`, `vcan0`). Windows is supported via WSL2 or vendor backends through `python-can`.

- [SocketCAN Traffic Shaper \& Analyzer](#socketcan-traffic-shaper--analyzer)
  - [1) What is SocketCAN?](#1-what-is-socketcan)
  - [2) Project Goals](#2-project-goals)
  - [3) Quick Start](#3-quick-start)
    - [3.1 Prerequisites (Linux/WSL2)](#31-prerequisites-linuxwsl2)
      - [3.1.1 WSL2 setup (Windows)](#311-wsl2-setup-windows)
    - [3.2 Enable SocketCAN in WSL2 (vCAN)](#32-enable-socketcan-in-wsl2-vcan)
    - [3.3 Create a virtual CAN interface](#33-create-a-virtual-can-interface)
    - [3.4 Install tooling](#34-install-tooling)
    - [3.5 Sanity test (send/receive)](#35-sanity-test-sendreceive)
    - [3.6 Using a real USB‑CAN adapter from WSL2 (optional)](#36-using-a-real-usbcan-adapter-from-wsl2-optional)
  - [4) Traffic Shaping: Approaches (Under Development)](#4-traffic-shaping-approaches-under-development)
  - [5) Project Structure (Under Development)](#5-project-structure-under-development)
  - [6) Usage (Under Development)](#6-usage-under-development)
  - [7) Development (Under Development)](#7-development-under-development)
    - [7.1 Local setup](#71-local-setup)
  - [8) Testing \& Benchmarking (Under Development)](#8-testing--benchmarking-under-development)
  - [9) Roadmap (living)](#9-roadmap-living)
  - [10) FAQs](#10-faqs)
  - [11) References](#11-references)

---

## 1) What is SocketCAN?
**SocketCAN** is the set of open‑source CAN (Controller Area Network) drivers and a Linux‑kernel networking stack that exposes CAN devices via the familiar Berkeley sockets API (PF_CAN). In practice, it lets you:
- Use `ip`, `ifconfig`, `tc`, and other standard net tools with CAN interfaces.
- Work with real CAN adapters (e.g., USB‑to‑CAN) *and* virtual interfaces (e.g., `vcan`) for simulation.
- Send/receive classic CAN (11/29‑bit IDs) and, on supported hardware, CAN FD.

> Key ideas: a CAN interface shows up as a Linux net device (e.g., `can0`, `vcan0`), and frames are read/written using sockets instead of vendor SDKs.

---

## 2) Project Goals
A practical toolkit to **shape** (prioritize, pace, rate‑limit) and **analyze** CAN traffic using SocketCAN — with a friendly CLI, repeatable scenarios, and clear metrics.

Core pillars:
- **Traffic shaping**: prioritize IDs, throttle rates, burst/latency control, and queue tuning.
- **Analysis**: live sniffing, stats, histograms (inter‑arrival, latency), ID filters/whitelists/blacklists.
- **Emulation**: reproducible testbeds using `vcan` so contributors don’t need hardware.
- **Extensibility**: clean modules for new shaping policies and analyzers.

---

## 3) Quick Start

### 3.1 Prerequisites (Linux/WSL2)

- Linux (Ubuntu/Debian recommended) or 
- **WSL2** on Windows.

#### 3.1.1 WSL2 setup (Windows)

If you’re on Windows, we recommend **WSL2 + Ubuntu**.

**Official docs:**

- Install WSL: https://learn.microsoft.com/windows/wsl/install

**Quick checks:**
```powershell
wsl -l -v               # list installed distros and versions
wsl --set-version <Distro> 2
wsl --install           # one-shot install on supported Windows versions
```
> Tip: Keep WSL (Store package) and the WSL kernel updated before troubleshooting modules.

### 3.2 Enable SocketCAN in WSL2 (vCAN)
Most recent WSL2 kernels ship `vcan` and `can` as modules. Verify and enable:
```bash
# Inside your WSL2 Ubuntu shell
uname -r                 # Note kernel version
sudo modprobe vcan       # Load virtual CAN module (no output on success)
sudo modprobe can        # Base CAN stack module; usually auto-loaded
lsmod | grep -E "^(vcan|can)" || echo "Modules not loaded"
```
If `modprobe vcan` fails with “module not found”, you have two options:
1) **Use an official custom-kernel route**
   - WSL advanced settings & custom kernel path (`.wslconfig`): https://learn.microsoft.com/windows/wsl/wsl-config
   - Microsoft WSL2 kernel repo (source & configs): https://github.com/microsoft/WSL2-Linux-Kernel
   - Community how-to for Microsoft kernel v6 (semi-official Learn community page): https://learn.microsoft.com/en-us/community/content/wsl-user-msft-kernel-v6
2) **Community guide (example below)**
   - Enabling SocketCAN on WSL2: https://gist.github.com/manavortex/cdaf9540784808e5848cbec744d49a19 


### 3.3 Create a virtual CAN interface
```bash
# Load the virtual CAN kernel module
sudo modprobe vcan
# Create vcan0 and bring it up
sudo ip link add dev vcan0 type vcan
sudo ip link set up vcan0

# Verify
ip -details -statistics link show vcan0
```

### 3.4 Install tooling
```bash
sudo apt update
sudo apt install -y iproute2 can-utils
```

### 3.5 Sanity test (send/receive)
In **terminal A**:
```bash
candump vcan0
```
In **terminal B** (send a sample frame):
```bash
cansend vcan0 123#DEADBEEF
# or generate traffic
cangen vcan0 -g 5  # 5 ms gap between frames
```
You should see frames in terminal A.


### 3.6 Using a real USB‑CAN adapter from WSL2 (optional)
Use **usbipd-win** on Windows to attach a USB device to WSL2, then bring the interface up inside WSL:
```powershell
# On Windows PowerShell (Admin): list and attach by busid
usbipd wsl list
usbipd wsl attach --busid <BUSID>
```
Back in WSL:
```bash
# Example: bring up classic CAN at 500 kbit/s
sudo ip link set can0 up type can bitrate 500000
# optional: tune TX queue length
sudo ip link set can0 txqueuelen 100
# teardown
sudo ip link set can0 down
```
**Resources:**
- Microsoft usbipd guide: https://learn.microsoft.com/windows/wsl/connect-usb
- `usbipd-win` wiki (WSL support): https://github.com/dorssel/usbipd-win/wiki/WSL-support

> If you rely on Docker Desktop in WSL, be cautious with **custom kernels**; some tools don’t support non‑default kernels. We’ll track compatibility notes in `docs/wsl-kernel.md`.

---

## 4) Traffic Shaping: Approaches (Under Development)
Traffic shaping in CAN can be approached at several levels. We will support and compare these strategies:

1. **User‑space pacing (initial focus)**
   - Controlled sender that schedules frames based on per‑ID/token‑bucket/leaky‑bucket policies.
   - Pros: portable, predictable, easy to test on `vcan`.  
   - Cons: app‑level; relies on scheduler timing.

2. **Queue tuning**
   - Adjust driver/netdev queue sizes (`txqueuelen`), apply prioritization in user‑space queues before send.

3. **Kernel qdisc experiments (later)**
   - Where feasible, explore `tc`‑based queuing/priority on CAN netdevs and document what is (and isn’t) supported for CAN.

4. **ID‑based prioritization**
   - Map arbitration IDs (or ranges/masks) to priority classes and schedule accordingly (e.g., safety‑critical vs diagnostic).

> We’ll start with **user‑space token‑bucket** shaping (per‑ID or per‑class), then benchmark alternatives.

---

## 5) Project Structure (Under Development)
```
.
├── README.md                # You are here
├── docs/
│   ├── architecture.md      # Components & data flow diagrams
│   ├── shaping-policies.md  # Token bucket, priority classes, etc.
│   └── faq.md
├── scripts/
│   ├── setup_vcan.sh        # Create/teardown vcan interfaces
│   └── demo_traffic.sh      # cangen/cansend demo scenarios
├── src/
│   ├── shaper/              # User-space shaping (policies, schedulers)
│   ├── capture/             # SocketCAN RX, filters, ring buffers
│   ├── analysis/            # Stats, histograms, exporters
│   └── cli/                 # CLI entry points
├── tests/
│   ├── integration/
│   └── unit/
├── examples/
│   ├── replay_trace/        # Trace replayer examples
│   └── policies/            # Sample policy files
└── CHANGELOG.md
```

---

## 6) Usage (Under Development)
> Placeholder — actual commands will land once `src/cli` is in place.
```bash
# Start analyzer on vcan0 and print basic stats
can-shaper analyze --iface vcan0 --ids 100-1FF --histogram inter-arrival

# Shape: throttle ID 0x123 to 100 frames/sec, allow burst of 10
can-shaper shape --iface vcan0 \
  --policy token-bucket \
  --id 0x123 --rate 100/s --burst 10

# Prioritize ranges (class A > class B)
can-shaper shape --iface vcan0 \
  --class A:100-1FF --class B:200-2FF --strategy priority
```

---

## 7) Development (Under Development)
- Language/tooling: **TBD** (C/C++ for raw perf, or Rust for safety, or Python for fast prototyping).  
  We’ll begin with a Python prototype for shaping logic + `python-can` bindings for speed of iteration, then harden in C/C++.
- Style & CI: `.clang-format`/`ruff`/`pytest` (depending on language choice), GitHub Actions.

### 7.1 Local setup
```bash
# (If Python prototype)
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

---

## 8) Testing & Benchmarking (Under Development)
- Deterministic scenarios using `vcan` + `cangen` against the shaper.
- Metrics: throughput, inter‑arrival variance, max/min latency, drop rate.
- Reports: CSV + plots; reproducible via `make bench` (later).

---

## 9) Roadmap (living)
- [ ] **MVP**: Python user‑space shaper with token‑bucket per‑ID; basic analyzer
- [ ] CLI UX: YAML policy files, human‑readable stats
- [ ] Trace replay: load `.log`/`candump` format and apply shaping
- [ ] Priority classes & fairness policies
- [ ] Bench suite & plots
- [ ] Hardware guide (USB‑CAN in Linux native and WSL2 bridging)
- [ ] Optional: kernel/qdisc experiments & documentation of findings

---

## 10) FAQs
**Q: Do I need hardware?**  
A: No. Start with `vcan`. Hardware integration docs will come later.

**Q: Is Windows supported?**  
A: Use **WSL2** with `vcan` for dev. Native Windows CAN is out‑of‑scope initially.

**Q: CAN FD?**  
A: Planned where hardware/kernel support exists; we’ll gate it behind a flag.

---

## 11) References
- WSL install (official): https://learn.microsoft.com/windows/wsl/install
- WSL manual install (official): https://learn.microsoft.com/windows/wsl/install-manual
- WSL basic commands (official): https://learn.microsoft.com/windows/wsl/basic-commands
- WSL advanced settings & custom kernel path (official): https://learn.microsoft.com/windows/wsl/wsl-config
- WSL kernel release notes (official): https://learn.microsoft.com/windows/wsl/kernel-release-notes
- USB passthrough to WSL (official): https://learn.microsoft.com/windows/wsl/connect-usb
- `usbipd-win` wiki (WSL usage): https://github.com/dorssel/usbipd-win/wiki/WSL-support
- Microsoft WSL2 Kernel repo (source): https://github.com/microsoft/WSL2-Linux-Kernel
- Community kernel build guide (MS Learn community): https://learn.microsoft.com/en-us/community/content/wsl-user-msft-kernel-v6
- Community guide (user-supplied): https://gist.github.com/manavortex/cdaf9540784808e5848cbec744d49a19

- SocketCAN / linux-can docs (to add)
- can-utils repo (to add)
- python-can (to add)
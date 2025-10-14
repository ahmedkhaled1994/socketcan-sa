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
  - [4) Traffic Shaping: Approaches (Implemented)](#4-traffic-shaping-approaches-implemented)
  - [5) Project Structure (Current Implementation)](#5-project-structure-current-implementation)
  - [6) Usage (Implemented Modules)](#6-usage-implemented-modules)
  - [7) Development (Current State)](#7-development-current-state)
    - [7.1 Local setup](#71-local-setup)
  - [8) Testing \& Benchmarking (Implemented)](#8-testing--benchmarking-implemented)
  - [9) Implementation Status \& Future Work](#9-implementation-status--future-work)
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

## 4) Traffic Shaping: Approaches (Implemented)
Traffic shaping in CAN can be approached at several levels. Current implementation focuses on:

1. **User‑space bridge foundation (implemented)**
   - Pass-through CAN bridge with real-time statistics and proper resource cleanup.
   - Foundation for future token bucket rate limiting implementation.
   - Pros: portable, predictable, comprehensive test coverage.  
   - Status: Bridge ready, token bucket components for future integration.

2. **Queue tuning**
   - Adjust driver/netdev queue sizes (`txqueuelen`), apply prioritization in user‑space queues before send.

3. **Kernel qdisc experiments (later)**
   - Where feasible, explore `tc`‑based queuing/priority on CAN netdevs and document what is (and isn’t) supported for CAN.

4. **ID‑based prioritization**
   - Map arbitration IDs (or ranges/masks) to priority classes and schedule accordingly (e.g., safety‑critical vs diagnostic).

> **Current Status**: Pass-through bridge implemented with comprehensive testing. Ready for token bucket integration or further development.

---

## 5) Project Structure (Current Implementation)
```
.
├── README.md                # You are here
├── docs/
│   ├── roadmap.md           # Development roadmap and status
│   └── testing.md           # Testing infrastructure notes
├── tools/                   # Renamed from scripts/
│   ├── setup_vcan.sh        # Create/teardown vcan interfaces
│   ├── shutdown_vcan.sh     # Cleanup vcan interfaces
│   └── wsl-env.sh          # WSL environment setup helper
├── src/
│   └── socketcan_sa/        # Main package
│       ├── analyzer.py      # CAN traffic analysis with CSV export
│       ├── shaper.py        # Pass-through CAN bridge (traffic shaping foundation)
│       └── rules.py         # YAML configuration parser
├── tests/                   # Comprehensive test suites
│   ├── test_analyzer*.py    # 42 analyzer tests (5 categories)
│   ├── test_shaper*.py      # 35 shaper tests (100% coverage)
│   ├── test_rules*.py       # 65 rules tests (98.72% coverage)
│   ├── conftest.py          # Test fixtures and utilities
│   └── sample_frames.py     # Test data generation
├── configs/
│   └── rules.dev.yaml       # Example YAML configuration
└── pyproject.toml          # Python packaging configuration
```

---

## 6) Usage (Implemented Modules)
The core modules can be imported and used directly:

```python
# Analyze CAN traffic with CSV export
from socketcan_sa.analyzer import analyze
analyze("vcan0", interval=2.0, csv_path="traffic.csv")

# Pass-through bridge (foundation for traffic shaping)
from socketcan_sa.shaper import run_bridge
import threading
stop_event = threading.Event()
run_bridge("vcan0", "vcan1", stats_interval=1.0)

# Parse YAML rules configuration
from socketcan_sa.rules import load_rules
rules = load_rules("configs/rules.dev.yaml")
limits = rules["limits"]  # Per-ID rate limits
drops = rules["drop"]     # IDs to drop
remaps = rules["remap"]   # ID remapping
```

> **Integration Status**: Core components ready. CLI integration available for future development.

---

## 7) Development (Current State)
- **Language**: Python 3.12+ with type hints and comprehensive testing
- **Dependencies**: `python-can`, `PyYAML`, `rich` for CLI output, `hypothesis` for property testing
- **Testing**: `pytest` with coverage reporting, 5-category test methodology
- **Quality**: Type hints, docstrings, 95%+ test coverage across all modules

### 7.1 Local setup
```bash
# WSL2 environment (recommended)
python3 -m venv .venv-wsl  
source .venv-wsl/bin/activate
pip install -e .

# Run comprehensive test suite
python -m pytest tests/ -v

# Check coverage
python -m pytest tests/ --cov=socketcan_sa --cov-report=html
```

---

## 8) Testing & Benchmarking (Implemented)
- **5-Category Test Methodology**: Coverage, Integration, Performance, Properties (hypothesis), Stress
- **Test Coverage**: 142 total tests across all modules with 95%+ coverage
- **Performance Benchmarks**: Bridge throughput (1000+ fps), rules parsing scalability, analyzer throughput  
- **Property-Based Testing**: Mathematical invariants validation with Hypothesis framework
- **Integration Tests**: Real vcan interface testing with automotive and industrial scenarios

---

## 9) Implementation Status & Future Work
- [x] **Core Components**: Analyzer, Pass-through bridge, YAML rules parser  
- [x] **Comprehensive Testing**: 142 tests with property-based validation
- [x] **YAML Configuration**: Full CAN ID parsing with automotive/industrial examples
- [x] **Performance Analysis**: Benchmarking and memory efficiency testing
- [ ] **Integration Layer**: Bridge components for complete traffic shaping pipeline
- [ ] **CLI Interface**: Command-line tools for ease of use
- [ ] **Hardware Integration**: Real CAN adapter support beyond vcan testing

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
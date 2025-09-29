# SocketCAN Traffic Shaper & Analyzer

Minimal toolkit to **analyze** CAN traffic and **shape** (rate-limit/drop/remap) frames.
Targets Linux **SocketCAN** (e.g., `can0`, `vcan0`). Windows is supported via WSL2 or vendor backends through `python-can`.

## Status

MVP in progress (Analyzer + Shaper). This README will expand as features land.

## Quick start (Linux/WSL2)

```bash
# once we add the script in tools/
sudo ./tools/setup_vcan.sh  # creates vcan0 (and can add vcan1 later)

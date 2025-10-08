#!/usr/bin/env bash
set -euo pipefail

# Create and bring up virtual CAN interfaces for testing.
# Run with: sudo ./tools/setup_vcan.sh

if [[ ${EUID:-$(id -u)} -ne 0 ]]; then
  echo "Please run as root (use: sudo $0 ...)" >&2
  exit 1
fi

echo "Setting up virtual CAN interfaces for testing..."

modprobe vcan 2>/dev/null || true

if ! ip link show vcan0 &>/dev/null; then
  ip link add dev vcan0 type vcan
fi

ip link set up vcan0
echo "vcan0 is UP"

# Uncomment to also add a second interface for bridging tests later:
if ! ip link show vcan1 &>/dev/null; then
  ip link add dev vcan1 type vcan
fi
ip link set up vcan1
echo "vcan1 is UP"

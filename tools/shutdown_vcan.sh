#!/usr/bin/env bash
set -euo pipefail

# Remove one or more vcan interfaces (default: all existing vcan*).
# Usage:
#   sudo ./tools/shutdown_vcan.sh            # remove all vcan interfaces
#   sudo ./tools/shutdown_vcan.sh vcan0      # remove a specific interface
#   sudo ./tools/shutdown_vcan.sh vcan0 vcan1

if [[ ${EUID:-$(id -u)} -ne 0 ]]; then
  echo "Please run as root (use: sudo $0 ...)" >&2
  exit 1
fi

# Decide targets
declare -a TARGETS=()
if [[ $# -gt 0 ]]; then
  TARGETS=("$@")
else
  # Collect all existing vcan interfaces
  mapfile -t TARGETS < <(ip -o link show type vcan | awk -F': ' '{print $2}')
fi

if [[ ${#TARGETS[@]} -eq 0 ]]; then
  echo "No vcan interfaces found. Nothing to do."
  exit 0
fi

for ifname in "${TARGETS[@]}"; do
  if ip link show "$ifname" &>/dev/null; then
    ip link set "$ifname" down || true
    # Prefer explicit type; fall back to generic delete if needed
    ip link delete "$ifname" type vcan 2>/dev/null || ip link delete "$ifname" || true
    echo "Deleted $ifname"
  else
    echo "Interface $ifname not found (skipped)."
  fi
done

# If no vcan interfaces remain, try unloading the module (optional)
if ! ip -o link show type vcan | grep -q .; then
  if lsmod | grep -q '^vcan'; then
    rmmod vcan || true
    echo "Unloaded vcan module"
  fi
fi

echo "Done."

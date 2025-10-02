# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2025 Ahmed Khaled

#!/usr/bin/env python3
"""
Analyzer for SocketCAN interfaces with bus load and CSV export.
Adds:
  - Bus load estimate (percent) per reporting window
  - CSV export (--csv path)
  - Simple "jitter": average inter-arrival time per ID (ms)

Usage:
  python analyzer.py --if vcan0 --interval 1.0 --bitrate 500000 --csv output.csv

Notes:
  - Bus load is an approximation using payload + fixed overhead per frame.
  - Default bitrate is 500_000 bps; override with --bitrate if needed.
"""

import argparse
import csv
import time
import collections

try:
    import can 
except ImportError as e:
    raise SystemExit("python-can is required. Install with: pip install python-can") from e

# Use rich for better output
try:
    from rich.console import Console
except ImportError:
    print("Tip: Install 'rich' for colored output: pip install rich")
    Console = lambda: type('Console', (), {'print': print})()

# Constants
RECV_TIMEOUT = 0.02     # 20ms timeout for non-blocking receive
MIN_COUNT_FOR_AVG = 1   # Minimum count to avoid division by zero
CAN_MAX_DLC = 8         # CAN 2.0 max payload size

# Rough overhead; ignoring bit stuffing and ext IDs for simplicity
# CAN frame overhead bits (SOF, arbitration, control, CRC, EOF, IFS, ACK)
CAN_FRAME_OVERHEAD_BITS = 47

def _frame_bits(payload_len: int) -> int:
    """
    Estimate the total number of bits in a CAN frame given the payload length.

    Args:
        payload_len (int): The length of the CAN payload in bytes.

    Returns:
        int: The estimated total number of bits in the CAN frame.
    """
    # Rough overhead; ignoring bit stuffing and ext IDs for simplicity
    return CAN_FRAME_OVERHEAD_BITS + payload_len * 8


def analyze(iface: str, interval: float = 1.0, bitrate: int = 500_000, csv_path: str | None = None):
    # Connect to the specified SocketCAN interface
    try:
        bus = can.interface.Bus(channel=iface, interface="socketcan")
    except Exception as e:
        raise SystemExit(f"Failed to connect to interface '{iface}': {e}") from e

    # Dictionary to track statistics per CAN ID during current time window
    # Key: CAN ID (arbitration_id), Value: {"count": frames, "bytes": total_payload_bytes, "last_ts": timestamp, "gaps_ms": list}
    # defaultdict automatically creates {"count": 0, "bytes": 0, "last_ts": None, "gaps_ms": []} for new CAN IDs
    by_id = collections.defaultdict(lambda: {
        "count": 0, 
        "bytes": 0, 
        "last_ts": None, 
        "gaps_ms": []
    })

    # Track when current analysis window started
    window_start = time.time()
    bits_in_window = 0
    csvw = None

    if csv_path:
        f = open(csv_path, "w", newline="")
        csvw = csv.writer(f)
        csvw.writerow(["ts_unix", "iface", "bus_load_pct", "id_hex", "fps",
                       "avg_jitter_ms", "avg_len_bytes", "count"])

    console = Console()

    print(f"Analyzing interface={iface} (interval={interval:.2f}s). Press Ctrl+C to stop.")
    try:
        while True:
            # Receive CAN messages with short timeout to allow periodic reporting
            msg = bus.recv(timeout=RECV_TIMEOUT)
            now = time.time()
            # Process received message, if any
            if msg is not None:
                # Validate DLC (Data Length Code) - CAN 2.0 max payload is 8 bytes
                if len(msg.data) > CAN_MAX_DLC:
                    print(f"Warning: Invalid DLC {len(msg.data)} for ID 0x{msg.arbitration_id:X}")
                    continue

                # Get or create statistics record for this CAN ID
                rec = by_id[msg.arbitration_id]
                rec["count"] += 1                    # Increment frame counter
                payload_len = len(msg.data)
                rec["bytes"] += payload_len        # Add payload size to total

                # simple "jitter": store inter-arrival gaps in ms
                if rec["last_ts"] is not None:
                    rec["gaps_ms"].append((now - rec["last_ts"]) * 1000.0)
                rec["last_ts"] = now

                # accumulate rough frame size for load estimate
                bits_in_window += _frame_bits(payload_len)


            # Check if it's time to report statistics
            if now - window_start >= interval:
                dt = now - window_start
                ts = time.strftime("%H:%M:%S", time.localtime(now))
                bus_load = min(100.0, (bits_in_window / max(dt, 1e-9)) * 100.0 / bitrate)
                console.print(f"[bold blue][{ts}][/bold blue] window={dt:.2f}s  iface={iface}  bus_load≈{bus_load:.1f}%")

                if not by_id:
                    console.print("  (no frames in this window)")
                else:
                    # Report statistics for each CAN ID seen in this window
                    for cid in sorted(by_id.keys()):
                        rec = by_id[cid]
                        fps = rec["count"] / dt                           # Frames per second
                        avg_len = rec["bytes"] / max(MIN_COUNT_FOR_AVG, rec["count"])     # Average payload size
                        avg_jitter = (sum(rec["gaps_ms"]) / len(rec["gaps_ms"])) if rec["gaps_ms"] else 0.0
                        console.print(f"  ID=0x{cid:X}  fps={fps:.2f}  avg_jitter={avg_jitter:.2f}ms  avg_len={avg_len:.1f}B  n={rec['count']}")
                        if csvw:
                            csvw.writerow([
                                int(now),
                                iface,
                                f"{bus_load:.2f}",
                                f"0x{cid:X}",
                                f"{fps:.3f}",
                                f"{avg_jitter:.3f}",
                                f"{avg_len:.2f}",
                                rec["count"],
                            ])
                
                console.print("")  # Blank line after each window
                
                # Clear statistics and start new window
                by_id.clear()
                bits_in_window = 0
                window_start = now

    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        # Add proper resource cleanup
        bus.shutdown()
        if csvw:
            f.close()


def main():
    # Set up command-line argument parser with description
    ap = argparse.ArgumentParser(description="SocketCAN analyzer with bus-load and CSV")
    
    # Required argument: SocketCAN interface name (e.g., vcan0, can0)
    # Note: Using dest="iface" because "--if" is a Python keyword
    ap.add_argument("--if", dest="iface", required=True, help="SocketCAN interface (e.g., vcan0, can0)")
    
    # Optional argument: reporting interval in seconds (defaults to 1.0)
    ap.add_argument("--interval", type=float, default=1.0, help="Report interval in seconds (default: 1.0)")

    # Optional argument: bus bitrate in bps (default to 500000)
    ap.add_argument("--bitrate", type=int, default=500_000, help="Bus bitrate in bps (default: 500000)")
    
    # Optional argument: path to CSV file for output (default: None, meaning no CSV)
    ap.add_argument("--csv", dest="csv_path", default=None, help="Write metrics to CSV at this path")

    # Parse command-line arguments and extract values
    args = ap.parse_args()
    
    # Validate interval parameter
    if args.interval <= 0:
        ap.error("Interval must be positive")
    
    # Start the analyzer with specified parameters
    analyze(args.iface, args.interval, args.bitrate, args.csv_path)


if __name__ == "__main__":
    main()
# EOF

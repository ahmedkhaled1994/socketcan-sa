#!/usr/bin/env python3
"""
Minimal SocketCAN analyzer 
- Prints, every N seconds, per-ID frames-per-second (FPS) and average payload length (bytes).
- Keep it simple: no CSV, no jitter yet (comes in Step 8).

Usage:
    python analyzer.py --if vcan0 --interval 2.0
"""

import argparse
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
    class Console:
        def print(self, *args, **kwargs):
            print(*args, **kwargs)
    Console = Console

RECV_TIMEOUT = 0.05     # 50ms timeout for non-blocking receive
MIN_COUNT_FOR_AVG = 1   # Minimum count to avoid division by zero
CAN_MAX_DLC = 8         # CAN 2.0 max payload size


def analyze(iface: str, interval: float = 1.0):
    # Connect to the specified SocketCAN interface
    try:
        bus = can.interface.Bus(channel=iface, bustype="socketcan")
    except Exception as e:
        raise SystemExit(f"Failed to connect to interface '{iface}': {e}") from e

    # Dictionary to track statistics per CAN ID during current time window
    # Key: CAN ID (arbitration_id), Value: {"count": frames, "bytes": total_payload_bytes}
    # defaultdict automatically creates {"count": 0, "bytes": 0} for new CAN IDs
    by_id = collections.defaultdict(lambda: {"count": 0, "bytes": 0})

    # Track when current analysis window started
    window_start = time.time()

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
                rec["bytes"] += len(msg.data)        # Add payload size to total

            # Check if it's time to report statistics
            if now - window_start >= interval:
                dt = now - window_start
                ts = time.strftime("%H:%M:%S", time.localtime(now))
                console.print(f"[bold blue][{ts}][/bold blue] window={dt:.2f}s")

                if not by_id:
                    console.print("  (no frames in this window)")
                else:
                    # Report statistics for each CAN ID seen in this window
                    for cid in sorted(by_id.keys()):
                        rec = by_id[cid]
                        fps = rec["count"] / dt                           # Frames per second
                        avg_len = rec["bytes"] / rec["count"]     # Average payload size
                        console.print(f"  ID=0x{cid:X}  fps={fps:.2f}  avg_len={avg_len:.1f}B  n={rec['count']}")

                # Clear statistics and start new window
                by_id.clear()
                window_start = now

    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        # Add proper resource cleanup
        bus.shutdown()


def main():
    # Set up command-line argument parser with description
    ap = argparse.ArgumentParser(description="Minimal SocketCAN analyzer (Step 7)")
    
    # Required argument: SocketCAN interface name (e.g., vcan0, can0)
    # Note: Using dest="iface" because "--if" is a Python keyword
    ap.add_argument("--if", dest="iface", required=True, help="SocketCAN interface (e.g., vcan0, can0)")
    
    # Optional argument: reporting interval in seconds (defaults to 1.0)
    ap.add_argument("--interval", type=float, default=1.0, help="Report interval in seconds (default: 1.0)")
    
    # Parse command-line arguments and extract values
    args = ap.parse_args()
    
    # Validate interval parameter
    if args.interval <= 0:
        ap.error("Interval must be positive")
    
    # Start the analyzer with specified interface and interval
    analyze(args.iface, args.interval)


if __name__ == "__main__":
    main()
# EOF

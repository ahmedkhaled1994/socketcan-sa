# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2025 Ahmed Khaled

#!/usr/bin/env python3
"""
Pass-through SocketCAN bridge

Simple bridge that reads CAN frames from an input interface and forwards them 1:1
to an output interface. This is the foundation for traffic shaping functionality.

Features:
- Preserves all frame attributes (ID, payload, RTR, CAN FD flags)
- Real-time statistics reporting (rx/tx/errors)
- Proper resource cleanup on shutdown
- Configurable stats reporting interval

Usage:
    python shaper.py --if-in vcan0 --if-out vcan1 --stats-interval 2.0
    
Test setup:
    # Terminal 1: Start bridge
    python shaper.py --if-in vcan0 --if-out vcan1
    
    # Terminal 2: Generate test traffic
    cangen vcan0 -v
    
    # Terminal 3: Monitor output
    candump vcan1
"""

import argparse
import time
import threading
from typing import Final, Optional

try:
    import can  
except ImportError as e:
    raise SystemExit("python-can is required. Install with: pip install python-can") from e

# Configuration constants
RECV_TIMEOUT: Final[float] = 0.02       # 20ms timeout for non-blocking CAN receive
SEND_TIMEOUT: Final[float] = 0.1        # 100ms timeout for CAN frame transmission
DEFAULT_STATS_INTERVAL: Final[float] = 1.0  # Default statistics reporting interval


def run_bridge(if_in: str, if_out: str, stats_interval: float = DEFAULT_STATS_INTERVAL, quiet: bool = False, stop_event: Optional[threading.Event] = None):
    """
    Run a pass-through CAN bridge between two SocketCAN interfaces.
    
    Reads frames from input interface and forwards them to output interface
    while preserving all frame attributes and flags. Provides periodic
    statistics reporting for monitoring bridge performance.
    
    Args:
        if_in: Input SocketCAN interface name (e.g., 'vcan0', 'can0')
        if_out: Output SocketCAN interface name (e.g., 'vcan1', 'can1')
        stats_interval: Time in seconds between statistics reports
        quiet: If True, suppress periodic statistics output
        
    Raises:
        SystemExit: If interfaces cannot be opened
        KeyboardInterrupt: On Ctrl+C (handled gracefully)
        
    Note:
        This function blocks until interrupted. Use Ctrl+C to stop bridging.
    """
    # Open input and output CAN interfaces
    try:
        in_bus = can.interface.Bus(channel=if_in, interface="socketcan")
        out_bus = can.interface.Bus(channel=if_out, interface="socketcan")
    except Exception as e:
        raise SystemExit(f"Failed to open CAN interfaces: {e}") from e

    # Initialize statistics counters
    rx = tx = send_err = 0      # Frame counters: received, transmitted, send errors
    last = time.time()          # Timestamp for stats interval calculation

    if not quiet:
        print(f"Bridging {if_in} -> {if_out} (stats_interval={stats_interval:.2f}s). Ctrl+C to stop.")
    
    try:
        while True:
            # Check if we should stop (for testing)
            if stop_event and stop_event.is_set():
                break
                
            # Receive frames with short timeout for responsiveness
            # Small timeout keeps the loop responsive to Ctrl+C and stats printing
            msg = in_bus.recv(timeout=RECV_TIMEOUT)
            now = time.time()

            # Process received frame if available
            if msg is not None:
                rx += 1
                
                # Reconstruct message to ensure all flags are preserved explicitly
                # This is important for CAN FD frames and extended IDs
                fwd = can.Message(
                    arbitration_id=msg.arbitration_id,              # CAN ID (11 or 29-bit)
                    data=msg.data,                                  # Payload bytes (0-8 for CAN 2.0)
                    is_extended_id=msg.is_extended_id,              # 29-bit vs 11-bit ID format
                    is_remote_frame=getattr(msg, "is_remote_frame", False),    # RTR flag
                    is_fd=getattr(msg, "is_fd", False),                       # CAN FD frame
                    bitrate_switch=getattr(msg, "bitrate_switch", False),     # CAN FD BRS flag
                    error_state_indicator=getattr(msg, "error_state_indicator", False),  # CAN FD ESI flag
                )
                
                # Forward frame to output interface with timeout
                try:
                    out_bus.send(fwd, timeout=SEND_TIMEOUT)
                    tx += 1
                except can.CanError:
                    # Count send errors but continue processing
                    # This can happen if output interface is busy or down
                    send_err += 1
                    if not quiet:
                        print("send error", flush=True)

            # Print periodic statistics if interval has elapsed
            if now - last >= stats_interval:
                if not quiet:
                    # Format timestamp for readability
                    ts = time.strftime("%H:%M:%S", time.localtime(now))
                    print(f"[{ts}] rx={rx} tx={tx} send_err={send_err}")
                
                # Reset counters for next interval
                rx = tx = send_err = 0
                last = now

    except KeyboardInterrupt:
        if not quiet:
            print("\nStopped.")
    finally:
        # Ensure proper cleanup of CAN bus resources
        # This is critical to release SocketCAN interfaces properly
        in_bus.shutdown()
        out_bus.shutdown()


def main():
    """
    Parse command line arguments and start the CAN bridge.
    
    Provides a CLI interface for the pass-through bridge functionality
    with validation and help text following project conventions.
    """
    # Set up argument parser with descriptive help
    ap = argparse.ArgumentParser(
        description="Pass-through SocketCAN bridge (Step 9)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --if-in vcan0 --if-out vcan1
  %(prog)s --if-in can0 --if-out can1 --stats-interval 5.0 --quiet
  
Testing:
  # Setup virtual CAN interfaces
  sudo modprobe vcan
  sudo ip link add vcan0 type vcan && sudo ip link set vcan0 up
  sudo ip link add vcan1 type vcan && sudo ip link set vcan1 up
  
  # Run bridge and test with cangen/candump
        """
    )
    
    # Define command line arguments
    ap.add_argument(
        "--if-in", 
        required=True, 
        help="Input SocketCAN interface (e.g., vcan0, can0)"
    )
    ap.add_argument(
        "--if-out", 
        required=True, 
        help="Output SocketCAN interface (e.g., vcan1, can1)"
    )
    ap.add_argument(
        "--stats-interval", 
        type=float, 
        default=DEFAULT_STATS_INTERVAL, 
        help=f"Seconds between statistics reports (default: {DEFAULT_STATS_INTERVAL})"
    )
    ap.add_argument(
        "--quiet", 
        action="store_true", 
        help="Suppress periodic statistics output"
    )
    
    # Parse arguments and validate
    args = ap.parse_args()
    
    # Validate stats interval
    if args.stats_interval <= 0:
        ap.error("Stats interval must be positive")
    
    # Start the bridge with parsed arguments
    run_bridge(args.if_in, args.if_out, args.stats_interval, args.quiet)


if __name__ == "__main__":
    main()

import pytest
import asyncio
import subprocess
import time
import platform
import shutil
import threading
import contextlib
import can
import warnings
from socketcan_sa.shaper import run_bridge
from pathlib import Path


@contextlib.contextmanager
def managed_bridge(if_in: str, if_out: str, stats_interval: float = 1.0):
    """Context manager for controlled bridge lifecycle in tests."""
    stop_event = threading.Event()
    bridge_thread = threading.Thread(
        target=run_bridge,
        args=(if_in, if_out, stats_interval, True, stop_event),  # quiet=True, stop_event
        daemon=False  # Not a daemon - we'll shut it down properly
    )
    
    try:
        bridge_thread.start()
        time.sleep(0.1)  # Give bridge time to start
        yield stop_event
    finally:
        # Signal the bridge to stop
        stop_event.set()
        # Wait for clean shutdown
        bridge_thread.join(timeout=2.0)
        if bridge_thread.is_alive():
            # Force kill if it doesn't stop gracefully
            bridge_thread.join(timeout=0.1)


@pytest.fixture(scope="module")
def vcan_interfaces():
    """Setup and teardown virtual CAN interfaces for testing."""
    import platform
    import shutil
    
    # Skip if not on Linux or WSL
    if platform.system() != "Linux":
        pytest.skip("Virtual CAN interfaces only available on Linux/WSL")
    
    # Check if ip command is available
    if not shutil.which("ip"):
        pytest.skip("ip command not available")
    
    interfaces = ["vcan0", "vcan1"]
    created_interfaces = []
    
    # Setup
    try:
        for iface in interfaces:
            # Check if interface already exists and is up
            check_cmd = f"ip link show {iface}"
            result = subprocess.run(check_cmd, shell=True, capture_output=True, text=True)
            
            if result.returncode != 0:  # Interface doesn't exist
                pytest.skip(f"Virtual CAN interface {iface} not found. Please run: sudo ./tools/setup_vcan.sh")
            
            # Check if interface is up
            if "state UP" not in result.stdout and "state UNKNOWN" not in result.stdout:
                pytest.skip(f"Virtual CAN interface {iface} exists but is not up. Please run: sudo ip link set {iface} up")
        
        yield interfaces
        
    finally:
        # No cleanup needed - we don't create interfaces anymore
        # Interfaces should be managed by setup/teardown scripts
        pass


@pytest.mark.integration
class TestShapingIntegration:
    """Integration tests using real virtual CAN interfaces."""
    
    def test_bridge_forwards_real_frames(self, vcan_interfaces):
        """Test bridge with actual CAN traffic on vcan interfaces."""
        with managed_bridge("vcan0", "vcan1", 0.5):
            # Setup CAN buses for test
            sender_bus = can.interface.Bus(channel="vcan0", interface="socketcan")
            receiver_bus = can.interface.Bus(channel="vcan1", interface="socketcan")
            
            try:
                # Send test frame
                test_msg = can.Message(arbitration_id=0xABC, data=b'\xDE\xAD\xBE\xEF')
                sender_bus.send(test_msg)
                
                # Receive forwarded frame
                received = receiver_bus.recv(timeout=1.0)
                
                # Verify frame was forwarded correctly
                assert received is not None
                assert received.arbitration_id == 0xABC
                assert received.data == b'\xDE\xAD\xBE\xEF'
                
            finally:
                sender_bus.shutdown()
                receiver_bus.shutdown()

    def test_bridge_preserves_frame_flags(self, vcan_interfaces):
        """Test that extended ID and other flags are preserved."""
        with managed_bridge("vcan0", "vcan1", 1.0):
            sender_bus = can.interface.Bus(channel="vcan0", interface="socketcan")
            receiver_bus = can.interface.Bus(channel="vcan1", interface="socketcan")
            
            try:
                # Send extended ID frame
                test_msg = can.Message(
                    arbitration_id=0x1FFFFFFF,  # 29-bit extended ID
                    data=b'\x01\x02',
                    is_extended_id=True
                )
                sender_bus.send(test_msg)
                
                received = receiver_bus.recv(timeout=1.0)
                
                assert received is not None
                assert received.arbitration_id == 0x1FFFFFFF
                assert received.is_extended_id is True
                
            finally:
                sender_bus.shutdown()
                receiver_bus.shutdown()
import pytest
import time
from unittest.mock import Mock, patch
from socketcan_sa.shaper import run_bridge


@pytest.mark.performance
@patch('socketcan_sa.shaper.can.interface.Bus')
def test_bridge_throughput_target(mock_bus_class):
    """Test that bridge can handle target throughput of 1000+ fps."""
    mock_in_bus = Mock()
    mock_out_bus = Mock()
    mock_bus_class.side_effect = [mock_in_bus, mock_out_bus]
    
    # Create frame generator for high throughput test
    test_frame = Mock()
    test_frame.arbitration_id = 0x100
    test_frame.data = b'\x01\x02\x03\x04'
    test_frame.is_extended_id = False
    
    frame_count = 0
    def mock_recv(timeout):
        nonlocal frame_count
        if frame_count < 1000:
            frame_count += 1
            return test_frame
        elif frame_count == 1000:
            frame_count += 1
            raise KeyboardInterrupt()  # Stop after 1000 frames
        return None
    
    mock_in_bus.recv.side_effect = mock_recv
    
    start_time = time.time()
    run_bridge("vcan0", "vcan1", quiet=True)
    elapsed = time.time() - start_time
    
    # Should process 1000 frames in reasonable time (< 2 seconds for overhead)
    assert elapsed < 2.0
    assert mock_out_bus.send.call_count == 1000
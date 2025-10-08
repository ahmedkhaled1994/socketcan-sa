import pytest
from hypothesis import given, strategies as st
from unittest.mock import Mock, patch
from socketcan_sa.shaper import run_bridge


@given(
    can_id=st.integers(min_value=0, max_value=0x7FF),  # Standard CAN ID range
    data_len=st.integers(min_value=0, max_value=8),     # Valid DLC range
    stats_interval=st.floats(min_value=0.1, max_value=10.0)
)
@patch('socketcan_sa.shaper.can.interface.Bus')
def test_bridge_handles_valid_frame_ranges(mock_bus_class, can_id, data_len, stats_interval):
    """Test bridge with property-based valid CAN frames."""
    mock_in_bus = Mock()
    mock_out_bus = Mock()
    mock_bus_class.side_effect = [mock_in_bus, mock_out_bus]
    
    # Create frame with generated properties
    test_frame = Mock()
    test_frame.arbitration_id = can_id
    test_frame.data = bytes(range(data_len))  # Generate valid data
    test_frame.is_extended_id = False
    # Provide proper default values for optional CAN attributes
    test_frame.is_remote_frame = False
    test_frame.is_fd = False
    test_frame.bitrate_switch = False
    test_frame.error_state_indicator = False
    
    mock_in_bus.recv.side_effect = [test_frame, KeyboardInterrupt()]
    
    # Should handle any valid frame without error
    run_bridge("vcan0", "vcan1", stats_interval=stats_interval, quiet=True)
    
    # Verify frame was processed
    mock_out_bus.send.assert_called_once()
    sent_frame = mock_out_bus.send.call_args[0][0]
    assert sent_frame.arbitration_id == can_id
    assert len(sent_frame.data) == data_len
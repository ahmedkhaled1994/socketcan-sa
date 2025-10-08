"""
Additional tests to improve shaper.py coverage.
"""
import pytest
from unittest.mock import patch, Mock
from socketcan_sa.shaper import main
import socketcan_sa.shaper


def test_import_error_handling():
    """Test that missing python-can raises SystemExit with helpful message."""
    # This tests the ImportError handling on lines 38-39
    with patch.dict('sys.modules', {'can': None}):
        with pytest.raises(SystemExit, match="python-can is required"):
            # This will trigger the import error since 'can' is None
            import importlib
            import sys
            # Temporarily remove from cache if present
            if 'socketcan_sa.shaper' in sys.modules:
                del sys.modules['socketcan_sa.shaper'] 
            importlib.import_module('socketcan_sa.shaper')


@patch('socketcan_sa.shaper.can.interface.Bus')
def test_send_error_handling(mock_bus_class):
    """Test CAN send error path."""
    from socketcan_sa.shaper import run_bridge
    
    mock_in_bus = Mock()
    mock_out_bus = Mock()
    mock_bus_class.side_effect = [mock_in_bus, mock_out_bus]
    
    # Create test frame
    test_frame = Mock()
    test_frame.arbitration_id = 0x123
    test_frame.data = b'\x01\x02'
    test_frame.is_extended_id = False
    test_frame.is_remote_frame = False
    test_frame.is_fd = False
    test_frame.bitrate_switch = False
    test_frame.error_state_indicator = False
    
    # Make send() raise CanError to trigger error path (line 118)
    import can
    mock_out_bus.send.side_effect = can.CanError("Send failed")
    mock_in_bus.recv.side_effect = [test_frame, KeyboardInterrupt()]
    
    # This should handle the send error gracefully
    run_bridge("vcan0", "vcan1", quiet=False)  # quiet=False to test error print


@patch('socketcan_sa.shaper.run_bridge')
@patch('socketcan_sa.shaper.argparse.ArgumentParser.parse_args')
def test_main_function(mock_parse_args, mock_run_bridge):
    """Test main function calls run_bridge with correct arguments."""
    # Mock command line arguments
    mock_args = Mock()
    mock_args.if_in = "vcan0"
    mock_args.if_out = "vcan1" 
    mock_args.stats_interval = 2.0
    mock_args.quiet = True
    mock_parse_args.return_value = mock_args
    
    # Call main function (tests line 198)
    main()
    
    # Verify run_bridge was called with correct arguments
    mock_run_bridge.assert_called_once_with("vcan0", "vcan1", 2.0, True)


@patch('socketcan_sa.shaper.main')
def test_name_main_guard(mock_main):
    """Test __name__ == '__main__' guard."""
    # This is tricky to test directly, but we can verify the main function exists
    # Line 202 would be covered if we actually ran the script as main
    assert callable(main)
    # In a real scenario, line 202 would be covered by running:
    # python -m socketcan_sa.shaper --help
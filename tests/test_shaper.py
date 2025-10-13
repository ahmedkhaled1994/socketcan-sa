# tests/test_shaper.py
import pytest
from unittest.mock import Mock, patch, call
import time
from socketcan_sa.shaper import run_bridge, RECV_TIMEOUT, SEND_TIMEOUT
import can


class TestRunBridge:
    """Unit tests for CAN bridge functionality using mocks."""
    
    @patch('socketcan_sa.shaper.can.interface.Bus')
    def test_bridge_forwards_frames_successfully(self, mock_bus_class):
        """Test that frames are forwarded from input to output interface."""
        # Setup mock buses
        mock_in_bus = Mock()
        mock_out_bus = Mock()
        mock_bus_class.side_effect = [mock_in_bus, mock_out_bus]
        
        # Create test frame
        test_frame = Mock()
        test_frame.arbitration_id = 0x123
        test_frame.data = b'\x01\x02\x03\x04'
        test_frame.is_extended_id = False
        test_frame.is_remote_frame = False
        test_frame.is_fd = False
        test_frame.bitrate_switch = False
        test_frame.error_state_indicator = False
        
        # Mock recv to return frame once, then None to trigger stats, then KeyboardInterrupt
        mock_in_bus.recv.side_effect = [test_frame, None, KeyboardInterrupt()]
        
        # Run bridge (will exit on KeyboardInterrupt)
        run_bridge("vcan0", "vcan1", stats_interval=0.1, quiet=True)
        
        # Verify buses were created correctly
        expected_calls = [
            call(channel="vcan0", interface="socketcan"),
            call(channel="vcan1", interface="socketcan")
        ]
        mock_bus_class.assert_has_calls(expected_calls)
        
        # Verify frame was received
        mock_in_bus.recv.assert_called_with(timeout=RECV_TIMEOUT)
        
        # Verify frame was forwarded with correct attributes
        mock_out_bus.send.assert_called_once()
        sent_frame = mock_out_bus.send.call_args[0][0]
        assert sent_frame.arbitration_id == 0x123
        assert sent_frame.data == b'\x01\x02\x03\x04'
        
        # Verify cleanup
        mock_in_bus.shutdown.assert_called_once()
        mock_out_bus.shutdown.assert_called_once()

    @patch('socketcan_sa.shaper.can.interface.Bus')
    def test_bridge_handles_send_errors(self, mock_bus_class):
        """Test that send errors are counted but don't stop processing."""
        mock_in_bus = Mock()
        mock_out_bus = Mock()
        mock_bus_class.side_effect = [mock_in_bus, mock_out_bus]
        
        # Create test frame
        test_frame = Mock()
        test_frame.arbitration_id = 0x456
        test_frame.data = b'\x05\x06'
        test_frame.is_extended_id = False
        
        # Mock send to raise CanError
        mock_out_bus.send.side_effect = can.CanError("Bus busy")
        mock_in_bus.recv.side_effect = [test_frame, KeyboardInterrupt()]
        
        # Should not raise exception
        run_bridge("vcan0", "vcan1", quiet=True)
        
        # Verify send was attempted
        mock_out_bus.send.assert_called_once()

    @patch('socketcan_sa.shaper.can.interface.Bus')
    def test_bridge_fails_fast_on_interface_error(self, mock_bus_class):
        """Test that bridge fails fast if interfaces cannot be opened."""
        mock_bus_class.side_effect = Exception("Interface not found")
        
        with pytest.raises(SystemExit) as exc_info:
            run_bridge("invalid0", "invalid1")
        
        assert "Failed to open CAN interfaces" in str(exc_info.value)

    @patch('socketcan_sa.shaper.can.interface.Bus')
    @patch('socketcan_sa.shaper.time.time')
    def test_bridge_prints_statistics(self, mock_time, mock_bus_class, capsys):
        """Test that periodic statistics are printed correctly."""
        mock_in_bus = Mock()
        mock_out_bus = Mock()
        mock_bus_class.side_effect = [mock_in_bus, mock_out_bus]
        
        # Mock time progression
        mock_time.side_effect = [0.0, 0.5, 1.1, 1.1]  # Start, during frame, stats time, final
        
        test_frame = Mock()
        test_frame.arbitration_id = 0x789
        test_frame.data = b'\x07\x08\x09'
        test_frame.is_extended_id = False
        
        mock_in_bus.recv.side_effect = [test_frame, None, KeyboardInterrupt()]
        
        run_bridge("vcan0", "vcan1", stats_interval=1.0, quiet=False)
        
        captured = capsys.readouterr()
        assert "rx=1 tx=1 send_err=0" in captured.out

    def test_main_validates_stats_interval(self, capsys):
        """Test that main function validates stats interval parameter."""
        import sys
        from socketcan_sa.shaper import main
        
        # Mock command line args with invalid interval
        test_args = ["shaper.py", "--if-in", "vcan0", "--if-out", "vcan1", "--stats-interval", "-1.0"]
        
        with patch.object(sys, 'argv', test_args):
            with pytest.raises(SystemExit):
                main()
        
        captured = capsys.readouterr()
        assert "Stats interval must be positive" in captured.err
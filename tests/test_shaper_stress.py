"""
Realistic stress tests for shaper.py that could actually break things.
These tests simulate real-world conditions and edge cases.
"""
import pytest
import time
import threading
import random
from unittest.mock import Mock, patch, call
from socketcan_sa.shaper import run_bridge
import can


class TestShaperStress:
    """Stress tests that simulate real-world chaos."""

    @patch('socketcan_sa.shaper.can.interface.Bus')
    def test_high_frequency_burst_traffic(self, mock_bus_class):
        """Test bridge with burst of 1000+ frames in rapid succession."""
        mock_in_bus = Mock()
        mock_out_bus = Mock()
        mock_bus_class.side_effect = [mock_in_bus, mock_out_bus]
        
        # Generate burst of 1000 frames
        frames = []
        for i in range(1000):
            frame = Mock()
            frame.arbitration_id = random.randint(0, 0x7FF)
            frame.data = bytes([random.randint(0, 255) for _ in range(random.randint(0, 8))])
            frame.is_extended_id = False
            frame.is_remote_frame = False
            frame.is_fd = False
            frame.bitrate_switch = False
            frame.error_state_indicator = False
            frames.append(frame)
        
        # Add frames + interrupt to stop
        mock_in_bus.recv.side_effect = frames + [KeyboardInterrupt()]
        
        start_time = time.time()
        run_bridge("vcan0", "vcan1", stats_interval=0.1, quiet=True)
        duration = time.time() - start_time
        
        # Verify all frames were processed
        assert mock_out_bus.send.call_count == 1000
        print(f"Processed 1000 frames in {duration:.3f}s = {1000/duration:.0f} frames/sec")

    @patch('socketcan_sa.shaper.can.interface.Bus')
    def test_intermittent_send_failures(self, mock_bus_class):
        """Test bridge resilience with random send failures."""
        mock_in_bus = Mock()
        mock_out_bus = Mock()
        mock_bus_class.side_effect = [mock_in_bus, mock_out_bus]
        
        # Create frames
        frames = []
        for i in range(100):
            frame = Mock()
            frame.arbitration_id = i
            frame.data = f"data{i}".encode()
            frame.is_extended_id = False
            frame.is_remote_frame = False
            frame.is_fd = False
            frame.bitrate_switch = False
            frame.error_state_indicator = False
            frames.append(frame)
        
        mock_in_bus.recv.side_effect = frames + [KeyboardInterrupt()]
        
        # Make send fail randomly ~20% of the time
        def random_send_failure(*args, **kwargs):
            if random.random() < 0.2:  # 20% failure rate
                raise can.CanError("Random network congestion")
        
        mock_out_bus.send.side_effect = random_send_failure
        
        # Should handle failures gracefully and continue
        run_bridge("vcan0", "vcan1", stats_interval=0.1, quiet=False)
        
        # Verify it tried to send all frames (even the failing ones)
        assert mock_out_bus.send.call_count == 100

    @patch('socketcan_sa.shaper.can.interface.Bus')
    def test_memory_usage_with_large_frames(self, mock_bus_class):
        """Test memory usage with maximum-size CAN frames."""
        mock_in_bus = Mock()
        mock_out_bus = Mock()
        mock_bus_class.side_effect = [mock_in_bus, mock_out_bus]
        
        # Create frames with maximum data (8 bytes for CAN 2.0)
        large_frames = []
        for i in range(500):
            frame = Mock()
            frame.arbitration_id = i
            frame.data = b'\xFF' * 8  # Maximum size
            frame.is_extended_id = True  # Use extended IDs too
            frame.is_remote_frame = False
            frame.is_fd = False
            frame.bitrate_switch = False
            frame.error_state_indicator = False
            large_frames.append(frame)
        
        mock_in_bus.recv.side_effect = large_frames + [KeyboardInterrupt()]
        
        run_bridge("vcan0", "vcan1", stats_interval=0.1, quiet=True) 
        
        # Verify all large frames were handled
        assert mock_out_bus.send.call_count == 500
        
        # Check that extended ID flag was preserved
        sent_frames = [call[0][0] for call in mock_out_bus.send.call_args_list]
        assert all(frame.is_extended_id for frame in sent_frames)

    @patch('socketcan_sa.shaper.can.interface.Bus')
    @patch('socketcan_sa.shaper.time.time')
    def test_statistics_timing_accuracy(self, mock_time, mock_bus_class):
        """Test that statistics timing is accurate under load."""
        mock_in_bus = Mock()
        mock_out_bus = Mock()
        mock_bus_class.side_effect = [mock_in_bus, mock_out_bus]
        
        # Mock time to advance predictably
        start_time = 1000.0
        mock_time.side_effect = [
            start_time,  # Initial time
            start_time + 0.5,  # First frame
            start_time + 1.0,  # Stats print time (should trigger)
            start_time + 1.5,  # Second frame  
            start_time + 2.0,  # Second stats print (should trigger)
        ]
        
        # Create test frames
        frame1 = Mock()
        frame1.arbitration_id = 0x123
        frame1.data = b'test1'
        frame1.is_extended_id = False
        frame1.is_remote_frame = False
        frame1.is_fd = False
        frame1.bitrate_switch = False
        frame1.error_state_indicator = False
        
        frame2 = Mock()
        frame2.arbitration_id = 0x456
        frame2.data = b'test2'
        frame2.is_extended_id = False
        frame2.is_remote_frame = False
        frame2.is_fd = False
        frame2.bitrate_switch = False
        frame2.error_state_indicator = False
        
        mock_in_bus.recv.side_effect = [frame1, frame2, KeyboardInterrupt()]
        
        # Capture print output to verify stats
        with patch('builtins.print') as mock_print:
            run_bridge("vcan0", "vcan1", stats_interval=1.0, quiet=False)
            
            # Should have printed statistics at least once
            print_calls = [str(call) for call in mock_print.call_args_list]
            stats_calls = [call for call in print_calls if 'rx=' in call]
            assert len(stats_calls) > 0  # At least one stats print

    @patch('socketcan_sa.shaper.can.interface.Bus')
    def test_concurrent_stop_event_race_condition(self, mock_bus_class):
        """Test for race conditions with stop_event in threaded environment."""
        mock_in_bus = Mock()
        mock_out_bus = Mock()
        mock_bus_class.side_effect = [mock_in_bus, mock_out_bus]
        
        # Create a slow frame source
        def slow_recv(*args, **kwargs):
            time.sleep(0.01)  # 10ms delay per frame
            frame = Mock()
            frame.arbitration_id = 0x123
            frame.data = b'test'
            frame.is_extended_id = False
            frame.is_remote_frame = False
            frame.is_fd = False
            frame.bitrate_switch = False
            frame.error_state_indicator = False
            return frame
        
        mock_in_bus.recv.side_effect = slow_recv
        
        # Start bridge in thread
        stop_event = threading.Event()
        bridge_thread = threading.Thread(
            target=run_bridge,
            args=("vcan0", "vcan1", 0.1, True, stop_event),
            daemon=False
        )
        
        bridge_thread.start()
        
        # Let it run briefly then stop quickly
        time.sleep(0.05)  # 50ms
        stop_event.set()
        
        # Should stop within reasonable time
        bridge_thread.join(timeout=1.0)  # 1 second max
        assert not bridge_thread.is_alive(), "Bridge thread should have stopped cleanly"

    @patch('socketcan_sa.shaper.can.interface.Bus')
    def test_malformed_frame_attributes(self, mock_bus_class):
        """Test bridge with frames that have unexpected/missing attributes."""
        mock_in_bus = Mock()
        mock_out_bus = Mock()
        mock_bus_class.side_effect = [mock_in_bus, mock_out_bus]
        
        # Create a frame with missing/weird attributes
        weird_frame = Mock()
        weird_frame.arbitration_id = 0x123
        weird_frame.data = b'test'
        weird_frame.is_extended_id = False
        # Deliberately missing some attributes to test getattr() defaults
        del weird_frame.is_remote_frame  # This will make getattr() return False
        weird_frame.is_fd = "not_a_boolean"  # Wrong type
        weird_frame.bitrate_switch = None    # None instead of boolean
        
        mock_in_bus.recv.side_effect = [weird_frame, KeyboardInterrupt()]
        
        # Should handle malformed attributes gracefully
        run_bridge("vcan0", "vcan1", quiet=True)
        
        # Verify frame was still sent (with corrected attributes)
        assert mock_out_bus.send.call_count == 1
        sent_frame = mock_out_bus.send.call_args[0][0]
        assert sent_frame.arbitration_id == 0x123
        assert sent_frame.data == b'test'

    @patch('socketcan_sa.shaper.can.interface.Bus')
    def test_send_timeout_stress(self, mock_bus_class):
        """Test behavior when send operations consistently timeout."""
        mock_in_bus = Mock()
        mock_out_bus = Mock()
        mock_bus_class.side_effect = [mock_in_bus, mock_out_bus]
        
        # Make every send operation take longer than timeout
        def slow_send(*args, **kwargs):
            time.sleep(0.2)  # 200ms delay (longer than SEND_TIMEOUT = 0.1s)
            # This might actually cause issues if the real implementation
            # doesn't handle timeouts properly
        
        mock_out_bus.send.side_effect = slow_send
        
        # Create test frames
        frames = []
        for i in range(10):
            frame = Mock()
            frame.arbitration_id = i
            frame.data = f"frame{i}".encode()
            frame.is_extended_id = False
            frame.is_remote_frame = False
            frame.is_fd = False
            frame.bitrate_switch = False  
            frame.error_state_indicator = False
            frames.append(frame)
        
        mock_in_bus.recv.side_effect = frames + [KeyboardInterrupt()]
        
        start_time = time.time()
        run_bridge("vcan0", "vcan1", quiet=True)
        duration = time.time() - start_time
        
        # Should have tried to send all frames despite slow sends
        assert mock_out_bus.send.call_count == 10
        # Total time should be significant due to slow sends
        assert duration > 1.0, f"Expected slow execution, got {duration:.3f}s"
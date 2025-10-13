#!/usr/bin/env python3
"""
Coverage tests for analyzer.py

Tests edge cases, error conditions, and boundary scenarios to achieve
high test coverage including:
- Error handling (CAN interface, file I/O)
- Invalid data handling (DLC violations)
- Division by zero protection
- Boundary conditions
- Resource cleanup scenarios
"""

import pytest
import tempfile
import os
from unittest.mock import Mock, patch, MagicMock, mock_open
from socketcan_sa.analyzer import analyze, _frame_bits, CAN_MAX_DLC


class TestErrorHandling:
    """Test error conditions and exception handling."""
    
    @patch('socketcan_sa.analyzer.Console')
    @patch('can.interface.Bus')
    def test_can_interface_connection_failure(self, mock_bus_class, mock_console_class):
        """Test handling of CAN interface connection errors."""
        # Simulate various connection failures
        error_messages = [
            "No such device",
            "Permission denied", 
            "Interface busy",
            "Network is down"
        ]
        
        for error_msg in error_messages:
            mock_bus_class.side_effect = Exception(error_msg)
            
            with pytest.raises(SystemExit):
                analyze("test_iface")
            
    @patch('socketcan_sa.analyzer.Console')
    @patch('can.interface.Bus')
    @patch('builtins.open')
    def test_csv_file_creation_error(self, mock_open_func, mock_bus_class, mock_console_class):
        """Test handling of CSV file creation errors."""
        mock_bus = Mock()
        mock_bus_class.return_value = mock_bus
        mock_console_class.return_value = Mock()
        mock_bus.recv.return_value = None
        
        # Simulate file permission error
        mock_open_func.side_effect = PermissionError("Permission denied")
        
        with pytest.raises(PermissionError):
            analyze("test_iface", csv_path="readonly.csv")
            
    @patch('socketcan_sa.analyzer.Console')
    @patch('can.interface.Bus')
    @patch('time.time')
    def test_csv_write_error_during_analysis(self, mock_time, mock_bus_class, mock_console_class):
        """Test handling of CSV write errors during analysis."""
        mock_bus = Mock()
        mock_bus_class.return_value = mock_bus
        mock_console_class.return_value = Mock()
        
        # Create a frame for processing
        test_frame = Mock()
        test_frame.arbitration_id = 0x123
        test_frame.data = b'\x01\x02\x03\x04'
        
        # Set up time and recv mocks with cycling functions
        time_values = [1000.0, 1000.5, 1001.1, 1001.2]
        time_call_count = 0
        def time_side_effect():
            nonlocal time_call_count
            if time_call_count < len(time_values):
                result = time_values[time_call_count]
                time_call_count += 1
                return result
            return 1002.0
        
        recv_call_count = 0
        def recv_side_effect(timeout=None):
            nonlocal recv_call_count
            recv_call_count += 1
            if recv_call_count == 1:
                return test_frame
            elif recv_call_count <= 3:
                return None  # Timeout
            else:
                raise KeyboardInterrupt()  # Force exit
        
        mock_time.side_effect = time_side_effect
        mock_bus.recv.side_effect = recv_side_effect
        
        # Mock CSV file that fails on write
        mock_csv_file = mock_open()
        mock_csv_writer = Mock()
        mock_csv_writer.writerow.side_effect = IOError("Disk full")
        
        with patch('builtins.open', mock_csv_file), \
             patch('csv.writer', return_value=mock_csv_writer), \
             patch('builtins.print'), \
             pytest.raises(IOError):
            # CSV write error should propagate (analyzer doesn't handle it)
            analyze("test_iface", interval=1.0, csv_path="test.csv")


class TestInvalidDataHandling:
    """Test handling of invalid or edge-case data."""
    
    @patch('socketcan_sa.analyzer.Console')
    @patch('can.interface.Bus')
    @patch('time.time')
    def test_invalid_dlc_handling(self, mock_time, mock_bus_class, mock_console_class):
        """Test handling of frames with invalid DLC (> 8 bytes)."""
        mock_bus = Mock()
        mock_bus_class.return_value = mock_bus
        mock_console = Mock()
        mock_console_class.return_value = mock_console
        
        # Create frame with invalid DLC
        invalid_frame = Mock()
        invalid_frame.arbitration_id = 0x123
        invalid_frame.data = b'\x01\x02\x03\x04\x05\x06\x07\x08\x09'  # 9 bytes (invalid)
        
        # Create valid frame for comparison
        valid_frame = Mock()
        valid_frame.arbitration_id = 0x456
        valid_frame.data = b'\x01\x02\x03\x04'  # 4 bytes (valid)
        
        # Use cycling function to prevent StopIteration
        time_values = [1000.0, 1000.1, 1000.2, 1001.1, 1001.2]
        time_call_count = 0
        def time_side_effect():
            nonlocal time_call_count
            if time_call_count < len(time_values):
                result = time_values[time_call_count]
                time_call_count += 1
                return result
            return 1002.0
        
        recv_call_count = 0
        def recv_side_effect(timeout=None):
            nonlocal recv_call_count
            recv_call_count += 1
            if recv_call_count == 1:
                return invalid_frame
            elif recv_call_count == 2:
                return valid_frame
            elif recv_call_count <= 4:
                return None  # Timeout
            else:
                raise KeyboardInterrupt()  # Force exit
        
        mock_time.side_effect = time_side_effect
        mock_bus.recv.side_effect = recv_side_effect
        
        # Run analyzer
        with patch('builtins.print') as mock_print:
            analyze("test_iface", interval=1.0)
        
        # Verify warning was printed for invalid DLC
        warning_printed = any("Warning: Invalid DLC" in str(call) for call in mock_print.call_args_list)
        assert warning_printed, "Expected warning for invalid DLC"
        
        # Verify valid frame was still processed
        mock_console.print.assert_called()  # Statistics should be reported
        
    @patch('socketcan_sa.analyzer.Console')
    @patch('can.interface.Bus')
    @patch('time.time')
    def test_maximum_valid_dlc(self, mock_time, mock_bus_class, mock_console_class):
        """Test that maximum valid DLC (8 bytes) is handled correctly."""
        mock_bus = Mock()
        mock_bus_class.return_value = mock_bus
        mock_console = Mock()
        mock_console_class.return_value = mock_console
        
        # Create frame with maximum valid DLC
        max_frame = Mock()
        max_frame.arbitration_id = 0x7FF
        max_frame.data = b'\x01\x02\x03\x04\x05\x06\x07\x08'  # 8 bytes (valid)
        
        # Use cycling function to prevent StopIteration
        time_values = [1000.0, 1000.5, 1001.1, 1001.2]
        time_call_count = 0
        def time_side_effect():
            nonlocal time_call_count
            if time_call_count < len(time_values):
                result = time_values[time_call_count]
                time_call_count += 1
                return result
            return 1002.0
        
        recv_call_count = 0
        def recv_side_effect(timeout=None):
            nonlocal recv_call_count
            recv_call_count += 1
            if recv_call_count == 1:
                return max_frame
            elif recv_call_count <= 3:
                return None  # Timeout
            else:
                raise KeyboardInterrupt()  # Force exit
        
        mock_time.side_effect = time_side_effect
        mock_bus.recv.side_effect = recv_side_effect
        
        # Run analyzer - should not raise warnings
        with patch('builtins.print') as mock_print:
            analyze("test_iface", interval=1.0)
        
        # Verify no warning was printed
        warning_printed = any("Warning" in str(call) for call in mock_print.call_args_list)
        assert not warning_printed, "No warning expected for valid DLC"
        
    @patch('socketcan_sa.analyzer.Console')
    @patch('can.interface.Bus')
    @patch('time.time')
    def test_zero_length_payload(self, mock_time, mock_bus_class, mock_console_class):
        """Test handling of frames with zero-length payload."""
        mock_bus = Mock()
        mock_bus_class.return_value = mock_bus
        mock_console = Mock()
        mock_console_class.return_value = mock_console
        
        # Create frame with empty payload
        empty_frame = Mock()
        empty_frame.arbitration_id = 0x100
        empty_frame.data = b''  # 0 bytes (valid)
        
        time_values = [1000.0, 1000.5, 1001.1]
        time_call_count = 0
        def time_side_effect():
            nonlocal time_call_count
            if time_call_count < len(time_values):
                result = time_values[time_call_count]
                time_call_count += 1
                return result
            return 1002.0
        
        recv_call_count = 0
        def recv_side_effect(timeout=None):
            nonlocal recv_call_count
            recv_call_count += 1
            if recv_call_count == 1:
                return empty_frame
            elif recv_call_count <= 3:
                return None
            else:
                raise KeyboardInterrupt()
        
        mock_time.side_effect = time_side_effect
        mock_bus.recv.side_effect = recv_side_effect
        
        with patch('builtins.print'):
            analyze("test_iface", interval=1.0)
        
        # Should handle zero-length payload without issues
        mock_console.print.assert_called()


class TestBoundaryConditions:
    """Test boundary conditions and edge cases."""
    
    @patch('socketcan_sa.analyzer.Console')
    @patch('can.interface.Bus')
    @patch('time.time')
    def test_zero_interval_protection(self, mock_time, mock_bus_class, mock_console_class):
        """Test protection against zero interval division."""
        mock_bus = Mock()
        mock_bus_class.return_value = mock_bus
        mock_console_class.return_value = Mock()
        
        mock_bus.recv.return_value = None
        
        # Simulate zero time interval (edge case)
        time_values = [1000.0, 1000.0, 1000.0]  # Same time
        time_call_count = 0
        def time_side_effect():
            nonlocal time_call_count
            if time_call_count < len(time_values):
                result = time_values[time_call_count]
                time_call_count += 1
                return result
            return 1001.0
        
        mock_time.side_effect = time_side_effect
        
        recv_call_count = 0
        def recv_side_effect(timeout=None):
            nonlocal recv_call_count
            recv_call_count += 1
            if recv_call_count <= 2:
                return None
            else:
                raise KeyboardInterrupt()
        
        mock_bus.recv.side_effect = recv_side_effect
        
        # Should not crash on zero interval
        with patch('builtins.print'):
            analyze("test_iface", interval=1.0)
            
    @patch('socketcan_sa.analyzer.Console')
    @patch('can.interface.Bus')
    @patch('time.time')
    def test_single_frame_statistics(self, mock_time, mock_bus_class, mock_console_class):
        """Test statistics calculation with exactly one frame."""
        mock_bus = Mock()
        mock_bus_class.return_value = mock_bus
        mock_console = Mock()
        mock_console_class.return_value = mock_console
        
        # Single frame
        single_frame = Mock()
        single_frame.arbitration_id = 0x123
        single_frame.data = b'\x01\x02\x03'
        
        time_values = [1000.0, 1000.5, 1001.1]
        time_call_count = 0
        def time_side_effect():
            nonlocal time_call_count
            if time_call_count < len(time_values):
                result = time_values[time_call_count]
                time_call_count += 1
                return result
            return 1002.0
        
        recv_call_count = 0
        def recv_side_effect(timeout=None):
            nonlocal recv_call_count
            recv_call_count += 1
            if recv_call_count == 1:
                return single_frame
            elif recv_call_count <= 3:
                return None
            else:
                raise KeyboardInterrupt()
        
        mock_time.side_effect = time_side_effect
        mock_bus.recv.side_effect = recv_side_effect
        
        with patch('builtins.print'):
            analyze("test_iface", interval=1.0)
        
        # Should handle single frame statistics
        mock_console.print.assert_called()
        
    @patch('socketcan_sa.analyzer.Console')
    @patch('can.interface.Bus')
    @patch('time.time')
    def test_maximum_can_id_values(self, mock_time, mock_bus_class, mock_console_class):
        """Test handling of maximum CAN ID values."""
        mock_bus = Mock()
        mock_bus_class.return_value = mock_bus
        mock_console = Mock()
        mock_console_class.return_value = mock_console
        
        # Standard CAN maximum ID
        max_std_frame = Mock()
        max_std_frame.arbitration_id = 0x7FF  # 11-bit max
        max_std_frame.data = b'\x01\x02'
        
        # Extended CAN maximum ID  
        max_ext_frame = Mock()
        max_ext_frame.arbitration_id = 0x1FFFFFFF  # 29-bit max
        max_ext_frame.data = b'\x03\x04'
        
        time_values = [1000.0, 1000.1, 1000.2, 1001.1]
        time_call_count = 0
        def time_side_effect():
            nonlocal time_call_count
            if time_call_count < len(time_values):
                result = time_values[time_call_count]
                time_call_count += 1
                return result
            return 1002.0
        
        recv_call_count = 0
        def recv_side_effect(timeout=None):
            nonlocal recv_call_count
            recv_call_count += 1
            if recv_call_count == 1:
                return max_std_frame
            elif recv_call_count == 2:
                return max_ext_frame
            elif recv_call_count <= 4:
                return None
            else:
                raise KeyboardInterrupt()
        
        mock_time.side_effect = time_side_effect
        mock_bus.recv.side_effect = recv_side_effect
        
        with patch('builtins.print'):
            analyze("test_iface", interval=1.0)
        
        mock_console.print.assert_called()
        
    @patch('socketcan_sa.analyzer.Console')
    @patch('can.interface.Bus')
    @patch('time.time')
    def test_bus_load_calculation_overflow_protection(self, mock_time, mock_bus_class, mock_console_class):
        """Test bus load calculation doesn't overflow with extreme values."""
        mock_bus = Mock()
        mock_bus_class.return_value = mock_bus
        mock_console = Mock()
        mock_console_class.return_value = mock_console
        
        # Create many frames to test high load
        large_frame = Mock()
        large_frame.arbitration_id = 0x123
        large_frame.data = b'\x01\x02\x03\x04\x05\x06\x07\x08'  # Max payload
        
        # Create timeline: start at 1000, receive frames, then jump past interval
        time_values = [1000.0]  # window_start
        for i in range(15):  # Timestamps for receiving frames
            time_values.append(1000.0 + i * 0.001)  # Very short intervals
        time_values.append(1001.5)  # Jump past the interval=1.0 to trigger reporting
        time_values.append(1001.6)  # Final timestamp
        
        time_call_count = 0
        def time_side_effect():
            nonlocal time_call_count
            if time_call_count < len(time_values):
                result = time_values[time_call_count]
                time_call_count += 1
                return result
            return 1002.0
        
        recv_call_count = 0
        def recv_side_effect(timeout=None):
            nonlocal recv_call_count
            recv_call_count += 1
            if recv_call_count <= 15:  # Return many frames quickly
                return large_frame
            elif recv_call_count <= 17:
                return None
            else:
                raise KeyboardInterrupt()
        
        mock_time.side_effect = time_side_effect
        mock_bus.recv.side_effect = recv_side_effect
        
        with patch('builtins.print'):
            # Use very low bitrate to test overflow protection - should cap at 100%
            analyze("test_iface", interval=1.0, bitrate=1000, quiet=False)
        
        # Verify console.print was called (should happen when reporting window stats)
        mock_console.print.assert_called()


class TestResourceCleanup:
    """Test proper resource cleanup in various scenarios."""
    
    @patch('socketcan_sa.analyzer.Console')
    @patch('can.interface.Bus')
    def test_bus_shutdown_on_normal_exit(self, mock_bus_class, mock_console_class):
        """Test that CAN bus is properly shutdown on normal exit."""
        mock_bus = Mock()
        mock_bus_class.return_value = mock_bus
        mock_console_class.return_value = Mock()
        
        mock_bus.recv.return_value = None
        
        with patch('time.time') as mock_time:
            time_values = [1000.0, 1001.1]
            time_call_count = 0
            def time_side_effect():
                nonlocal time_call_count
                if time_call_count < len(time_values):
                    result = time_values[time_call_count]
                    time_call_count += 1
                    return result
                return 1002.0
            
            mock_time.side_effect = time_side_effect
            
            recv_call_count = 0
            def recv_side_effect(timeout=None):
                nonlocal recv_call_count
                recv_call_count += 1
                if recv_call_count <= 2:
                    return None
                else:
                    raise KeyboardInterrupt()
            
            mock_bus.recv.side_effect = recv_side_effect
            
            with patch('builtins.print'):
                analyze("test_iface", interval=1.0)
        
        # Verify bus was shutdown
        mock_bus.shutdown.assert_called_once()
        
    @patch('socketcan_sa.analyzer.Console')
    @patch('can.interface.Bus')
    def test_bus_shutdown_on_keyboard_interrupt(self, mock_bus_class, mock_console_class):
        """Test that CAN bus is shutdown even on KeyboardInterrupt."""
        mock_bus = Mock()
        mock_bus_class.return_value = mock_bus
        mock_console_class.return_value = Mock()
        
        # Simulate KeyboardInterrupt during recv
        mock_bus.recv.side_effect = KeyboardInterrupt()
        
        with patch('builtins.print'):
            analyze("test_iface")
        
        # Verify bus was shutdown despite interrupt
        mock_bus.shutdown.assert_called_once()
        
    @patch('socketcan_sa.analyzer.Console')
    @patch('can.interface.Bus')
    def test_csv_file_cleanup_on_error(self, mock_bus_class, mock_console_class):
        """Test CSV file is properly closed even on errors."""
        mock_bus = Mock()
        mock_bus_class.return_value = mock_bus
        mock_console_class.return_value = Mock()
        
        # Simulate error during processing
        mock_bus.recv.side_effect = Exception("Simulated error")
        
        mock_file = mock_open()
        with patch('builtins.open', mock_file), \
             patch('csv.writer'), \
             patch('builtins.print'), \
             pytest.raises(Exception, match="Simulated error"):
            analyze("test_iface", csv_path="test.csv")
        
        # File should be properly closed
        mock_file().close.assert_called()


class TestMinCountProtection:
    """Test protection against division by zero in average calculations."""
    
    def test_min_count_for_avg_constant(self):
        """Test that MIN_COUNT_FOR_AVG constant is properly defined."""
        from socketcan_sa.analyzer import MIN_COUNT_FOR_AVG
        assert MIN_COUNT_FOR_AVG >= 1, "MIN_COUNT_FOR_AVG should be at least 1"
        
    @patch('socketcan_sa.analyzer.Console')
    @patch('can.interface.Bus')
    @patch('time.time')
    def test_average_calculation_with_zero_count(self, mock_time, mock_bus_class, mock_console_class):
        """Test average calculations don't fail with zero count."""
        mock_bus = Mock()
        mock_bus_class.return_value = mock_bus
        mock_console = Mock()
        mock_console_class.return_value = mock_console
        
        # No frames - should handle gracefully
        mock_bus.recv.return_value = None
        
        time_values = [1000.0, 1001.1]
        time_call_count = 0
        def time_side_effect():
            nonlocal time_call_count
            if time_call_count < len(time_values):
                result = time_values[time_call_count]
                time_call_count += 1
                return result
            return 1002.0
        
        recv_call_count = 0
        def recv_side_effect(timeout=None):
            nonlocal recv_call_count
            recv_call_count += 1
            if recv_call_count <= 2:
                return None
            else:
                raise KeyboardInterrupt()
        
        mock_time.side_effect = time_side_effect
        mock_bus.recv.side_effect = recv_side_effect
        
        # Should not crash with no frames
        with patch('builtins.print'):
            analyze("test_iface", interval=1.0)

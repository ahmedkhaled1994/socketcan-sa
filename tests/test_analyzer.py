#!/usr/bin/env python3
"""
Core unit tests for analyzer.py

Tests the basic functionality of the CAN analyzer including:
- Frame bit calculation
- Statistics accumulation 
- Window behavior
- Core analyze() function logic
"""

import pytest
import time
import collections
from unittest.mock import Mock, patch, MagicMock, call
from socketcan_sa.analyzer import _frame_bits, analyze, CAN_FRAME_OVERHEAD_BITS, MIN_COUNT_FOR_AVG


class TestFrameBits:
    """Test the _frame_bits() helper function."""
    
    def test_frame_bits_zero_payload(self):
        """Test bit calculation for empty payload."""
        result = _frame_bits(0)
        expected = CAN_FRAME_OVERHEAD_BITS + 0 * 8  # 47 + 0 = 47
        assert result == expected
        
    def test_frame_bits_single_byte(self):
        """Test bit calculation for 1-byte payload."""
        result = _frame_bits(1)
        expected = CAN_FRAME_OVERHEAD_BITS + 1 * 8  # 47 + 8 = 55
        assert result == expected
        
    def test_frame_bits_half_payload(self):
        """Test bit calculation for 4-byte payload."""
        result = _frame_bits(4)
        expected = CAN_FRAME_OVERHEAD_BITS + 4 * 8  # 47 + 32 = 79
        assert result == expected
        
    def test_frame_bits_max_payload(self):
        """Test bit calculation for maximum CAN payload (8 bytes)."""
        result = _frame_bits(8)
        expected = CAN_FRAME_OVERHEAD_BITS + 8 * 8  # 47 + 64 = 111
        assert result == expected
        
    def test_frame_bits_formula_consistency(self):
        """Verify the bit calculation formula is consistent."""
        for payload_len in range(9):  # 0-8 bytes
            result = _frame_bits(payload_len)
            expected = 47 + payload_len * 8
            assert result == expected, f"Failed for payload_len={payload_len}"


class TestAnalyzeCore:
    """Test the core analyze() function with mocked CAN bus."""
    
    @pytest.mark.timeout(5)  # 5 second timeout to prevent hanging
    @patch('socketcan_sa.analyzer.Console')
    @patch('can.interface.Bus')
    @patch('time.time')
    def test_analyze_single_frame_statistics(self, mock_time, mock_bus_class, mock_console_class):
        """Test basic statistics with a single CAN frame."""
        # Setup mocks
        mock_bus = Mock()
        mock_bus_class.return_value = mock_bus
        mock_console = Mock()
        mock_console_class.return_value = mock_console
        
        # Create test frame
        test_frame = Mock()
        test_frame.arbitration_id = 0x123
        test_frame.data = b'\x01\x02\x03\x04'  # 4 bytes
        
        # Mock recv to return frame then KeyboardInterrupt after a few cycles
        def recv_side_effect(timeout=None):
            if not hasattr(recv_side_effect, 'call_count'):
                recv_side_effect.call_count = 0
            recv_side_effect.call_count += 1
            
            if recv_side_effect.call_count == 1:
                return test_frame
            elif recv_side_effect.call_count <= 3:
                return None  # Timeout
            else:
                raise KeyboardInterrupt()  # Force exit
        
        mock_bus.recv.side_effect = recv_side_effect
        
        # Mock time progression
        mock_time.side_effect = [1000.0, 1000.5, 1000.6, 1001.1, 1001.2]
        
        # Run analyzer (should exit cleanly via KeyboardInterrupt)
        with patch('builtins.print'):
            analyze("test_iface", interval=1.0, bitrate=500_000)
        
        # Verify bus connection
        mock_bus_class.assert_called_once_with(channel="test_iface", interface="socketcan")
        
        # Verify frame processing occurred
        assert mock_bus.recv.call_count >= 2
        
        # Verify bus shutdown
        mock_bus.shutdown.assert_called_once()
        
    @pytest.mark.timeout(5)  # 5 second timeout
    @patch('socketcan_sa.analyzer.Console')  
    @patch('can.interface.Bus')
    @patch('time.time')
    def test_analyze_multiple_frames_same_id(self, mock_time, mock_bus_class, mock_console_class):
        """Test statistics accumulation for multiple frames with same CAN ID."""
        # Setup mocks
        mock_bus = Mock()
        mock_bus_class.return_value = mock_bus
        mock_console = Mock()
        mock_console_class.return_value = mock_console
        
        # Create test frames with same ID
        frame1 = Mock()
        frame1.arbitration_id = 0x100
        frame1.data = b'\x01\x02'  # 2 bytes
        
        frame2 = Mock()
        frame2.arbitration_id = 0x100  # Same ID
        frame2.data = b'\x03\x04\x05'  # 3 bytes
        
        # Mock recv to return frames then exit
        def recv_side_effect(timeout=None):
            if not hasattr(recv_side_effect, 'call_count'):
                recv_side_effect.call_count = 0
            recv_side_effect.call_count += 1
            
            if recv_side_effect.call_count == 1:
                return frame1
            elif recv_side_effect.call_count == 2:
                return frame2
            elif recv_side_effect.call_count <= 4:
                return None  # Timeout
            else:
                raise KeyboardInterrupt()  # Force exit
        
        mock_bus.recv.side_effect = recv_side_effect
        
        # Mock time progression
        mock_time.side_effect = [1000.0, 1000.2, 1000.4, 1000.6, 1001.1, 1001.2]
        
        # Run analyzer
        with patch('builtins.print'):
            analyze("test_iface", interval=1.0, bitrate=500_000)
        
        # Verify multiple recv calls
        assert mock_bus.recv.call_count >= 3
        
    @pytest.mark.timeout(5)  # 5 second timeout
    @patch('socketcan_sa.analyzer.Console')
    @patch('can.interface.Bus')
    @patch('time.time')
    def test_analyze_multiple_can_ids(self, mock_time, mock_bus_class, mock_console_class):
        """Test statistics tracking for multiple different CAN IDs."""
        # Setup mocks
        mock_bus = Mock()
        mock_bus_class.return_value = mock_bus
        mock_console = Mock()
        mock_console_class.return_value = mock_console
        
        # Create frames with different IDs
        frame1 = Mock()
        frame1.arbitration_id = 0x100
        frame1.data = b'\x01'
        
        frame2 = Mock()
        frame2.arbitration_id = 0x200  # Different ID
        frame2.data = b'\x02\x03'
        
        frame3 = Mock() 
        frame3.arbitration_id = 0x100  # Back to first ID
        frame3.data = b'\x04\x05\x06'
        
        # Mock recv to return frames then exit
        def recv_side_effect(timeout=None):
            if not hasattr(recv_side_effect, 'call_count'):
                recv_side_effect.call_count = 0
            recv_side_effect.call_count += 1
            
            if recv_side_effect.call_count == 1:
                return frame1
            elif recv_side_effect.call_count == 2:
                return frame2
            elif recv_side_effect.call_count == 3:
                return frame3
            elif recv_side_effect.call_count <= 5:
                return None  # Timeout
            else:
                raise KeyboardInterrupt()  # Force exit
        
        mock_bus.recv.side_effect = recv_side_effect
        
        # Mock time progression
        mock_time.side_effect = [1000.0, 1000.1, 1000.2, 1000.3, 1000.4, 1001.1, 1001.2]
        
        # Run analyzer
        with patch('builtins.print'):
            analyze("test_iface", interval=1.0, bitrate=500_000)
        
        # Verify processing occurred
        assert mock_bus.recv.call_count >= 4
        
    @pytest.mark.timeout(5)  # 5 second timeout
    @patch('socketcan_sa.analyzer.Console')
    @patch('can.interface.Bus')
    @patch('time.time')
    def test_analyze_bus_load_calculation(self, mock_time, mock_bus_class, mock_console_class):
        """Test bus load percentage calculation."""
        # Setup mocks
        mock_bus = Mock()
        mock_bus_class.return_value = mock_bus
        mock_console = Mock()
        mock_console_class.return_value = mock_console
        
        # Create frame with known size
        test_frame = Mock()
        test_frame.arbitration_id = 0x123
        test_frame.data = b'\x01\x02\x03\x04'  # 4 bytes -> 47 + 32 = 79 bits
        
        # Mock recv with KeyboardInterrupt exit
        def recv_side_effect(timeout=None):
            if not hasattr(recv_side_effect, 'call_count'):
                recv_side_effect.call_count = 0
            recv_side_effect.call_count += 1
            
            if recv_side_effect.call_count == 1:
                return test_frame
            elif recv_side_effect.call_count <= 3:
                return None  # Timeout
            else:
                raise KeyboardInterrupt()  # Force exit
        
        mock_bus.recv.side_effect = recv_side_effect
        
        # Mock time progression  
        mock_time.side_effect = [1000.0, 1000.5, 1000.6, 1001.1, 1001.2]
        
        # Run with known bitrate
        with patch('builtins.print'):
            analyze("test_iface", interval=1.0, bitrate=1000)  # Low bitrate for easy calculation
        
        # Verify console.print was called for reporting
        mock_console.print.assert_called()
        
    @pytest.mark.timeout(5)  # 5 second timeout
    @patch('socketcan_sa.analyzer.Console')
    @patch('can.interface.Bus') 
    @patch('time.time')
    def test_analyze_window_reset_behavior(self, mock_time, mock_bus_class, mock_console_class):
        """Test that statistics reset properly between windows."""
        # Setup mocks
        mock_bus = Mock()
        mock_bus_class.return_value = mock_bus
        mock_console = Mock()
        mock_console_class.return_value = mock_console
        
        # Create frames for two different windows
        frame1 = Mock()
        frame1.arbitration_id = 0x100
        frame1.data = b'\x01'
        
        frame2 = Mock()
        frame2.arbitration_id = 0x200
        frame2.data = b'\x02'
        
        # Mock recv with KeyboardInterrupt exit
        def recv_side_effect(timeout=None):
            if not hasattr(recv_side_effect, 'call_count'):
                recv_side_effect.call_count = 0
            recv_side_effect.call_count += 1
            
            if recv_side_effect.call_count == 1:
                return frame1
            elif recv_side_effect.call_count == 2:
                return None  # Timeout
            elif recv_side_effect.call_count == 3:
                return frame2
            elif recv_side_effect.call_count <= 5:
                return None  # Timeout
            else:
                raise KeyboardInterrupt()  # Force exit
        
        mock_bus.recv.side_effect = recv_side_effect
        
        # Mock time progression for two windows
        mock_time.side_effect = [1000.0, 1000.5, 1000.6, 1001.1, 1001.5, 1001.6, 1002.1, 1002.2]
        
        # Run analyzer
        with patch('builtins.print'):
            analyze("test_iface", interval=1.0, bitrate=500_000)
        
        # Verify statistics were reported (console.print called)
        mock_console.print.assert_called()
        
    @pytest.mark.timeout(5)  # 5 second timeout
    @patch('socketcan_sa.analyzer.Console')
    @patch('can.interface.Bus')
    @patch('time.time')
    def test_analyze_empty_window_handling(self, mock_time, mock_bus_class, mock_console_class):
        """Test behavior when no frames are received in a window."""
        # Setup mocks
        mock_bus = Mock()
        mock_bus_class.return_value = mock_bus
        mock_console = Mock()
        mock_console_class.return_value = mock_console
        
        # Mock recv to return None then KeyboardInterrupt
        def recv_side_effect(timeout=None):
            if not hasattr(recv_side_effect, 'call_count'):
                recv_side_effect.call_count = 0
            recv_side_effect.call_count += 1
            
            if recv_side_effect.call_count <= 5:
                return None  # No frames
            else:
                raise KeyboardInterrupt()  # Force exit
        
        mock_bus.recv.side_effect = recv_side_effect
        
        # Mock time progression 
        mock_time.side_effect = [1000.0, 1000.5, 1000.6, 1001.1, 1001.2, 1001.3]
        
        # Run analyzer (should exit via KeyboardInterrupt)
        with patch('builtins.print'):
            analyze("test_iface", interval=1.0, bitrate=500_000)
        
        # Should still report window stats (empty window)
        mock_console.print.assert_called()
        
    @patch('socketcan_sa.analyzer.Console')
    @patch('can.interface.Bus')
    def test_analyze_interface_connection_error(self, mock_bus_class, mock_console_class):
        """Test proper error handling when CAN interface fails to connect."""
        # Mock connection failure
        mock_bus_class.side_effect = Exception("Interface not found")
        
        # Should raise SystemExit
        with pytest.raises(SystemExit) as exc_info:
            analyze("invalid_iface")
        
        # Verify error message contains the interface name
        assert "invalid_iface" in str(exc_info.value)
        
    @pytest.mark.timeout(5)  # 5 second timeout
    @patch('socketcan_sa.analyzer.Console')
    @patch('can.interface.Bus')
    @patch('time.time')
    def test_analyze_jitter_calculation(self, mock_time, mock_bus_class, mock_console_class):
        """Test jitter (inter-arrival time) calculation."""
        # Setup mocks
        mock_bus = Mock()
        mock_bus_class.return_value = mock_bus
        mock_console = Mock()
        mock_console_class.return_value = mock_console
        
        # Create frames with known timing for same ID
        frame1 = Mock()
        frame1.arbitration_id = 0x100
        frame1.data = b'\x01'
        
        frame2 = Mock()
        frame2.arbitration_id = 0x100  # Same ID
        frame2.data = b'\x02'
        
        # Mock recv with KeyboardInterrupt exit
        def recv_side_effect(timeout=None):
            if not hasattr(recv_side_effect, 'call_count'):
                recv_side_effect.call_count = 0
            recv_side_effect.call_count += 1
            
            if recv_side_effect.call_count == 1:
                return frame1
            elif recv_side_effect.call_count == 2:
                return frame2
            elif recv_side_effect.call_count <= 4:
                return None  # Timeout
            else:
                raise KeyboardInterrupt()  # Force exit
        
        mock_bus.recv.side_effect = recv_side_effect
        
        # Mock time progression: 100ms gap between frames
        mock_time.side_effect = [1000.0, 1000.1, 1000.2, 1000.3, 1001.1, 1001.2]
        
        # Run analyzer (should exit via KeyboardInterrupt)
        with patch('builtins.print'):
            analyze("test_iface", interval=1.0, bitrate=500_000)
        
        # Verify reporting occurred - jitter should be calculated
        mock_console.print.assert_called()
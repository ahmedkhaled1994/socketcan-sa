#!/usr/bin/env python3
"""
Property-based tests for analyzer.py using hypothesis

Tests mathematical properties and invariants including:
- Frame bits calculation properties
- Statistical properties (bus load, FPS, averages)
- Invariant properties (non-negative values, consistency)
- Robustness properties (handling invalid inputs)
"""

import pytest
from hypothesis import given, strategies as st, assume, settings
from unittest.mock import Mock, patch
from socketcan_sa.analyzer import _frame_bits, analyze, CAN_MAX_DLC


class TestFrameBitsProperties:
    """Property-based tests for frame bits calculation."""
    
    @given(payload_len=st.integers(min_value=0, max_value=CAN_MAX_DLC))
    def test_frame_bits_formula_property(self, payload_len):
        """Test that frame bits follow the expected formula."""
        result = _frame_bits(payload_len)
        
        # Should always be positive
        assert result > 0
        
        # Should include payload bits + overhead
        expected_min = payload_len * 8 + 40  # Rough minimum
        assert result >= expected_min
        
        # Should be reasonable (not too large)
        expected_max = payload_len * 8 + 100  # Rough maximum
        assert result <= expected_max
    
    @given(payload_lengths=st.lists(st.integers(min_value=0, max_value=CAN_MAX_DLC), min_size=2, max_size=10))
    def test_frame_bits_monotonic_property(self, payload_lengths):
        """Test that frame bits increase monotonically with payload length."""
        sorted_lengths = sorted(payload_lengths)
        
        for i in range(len(sorted_lengths) - 1):
            len1, len2 = sorted_lengths[i], sorted_lengths[i + 1]
            bits1, bits2 = _frame_bits(len1), _frame_bits(len2)
            
            if len1 < len2:
                assert bits1 < bits2, f"Frame bits should increase: {len1}→{bits1}, {len2}→{bits2}"
            elif len1 == len2:
                assert bits1 == bits2, f"Frame bits should be equal for same payload: {len1}→{bits1}, {len2}→{bits2}"
    
    @given(payload_len=st.integers(min_value=0, max_value=CAN_MAX_DLC))
    def test_frame_bits_minimum_property(self, payload_len):
        """Test that frame bits have a reasonable minimum."""
        result = _frame_bits(payload_len)
        
        # Even empty frames should have overhead bits
        min_expected = 47  # CAN frame overhead
        assert result >= min_expected, f"Frame should have at least {min_expected} bits for payload {payload_len}"
    
    @given(payload_len=st.integers(min_value=0, max_value=CAN_MAX_DLC))
    def test_frame_bits_can_range_property(self, payload_len):
        """Test frame bits are within CAN protocol limits."""
        result = _frame_bits(payload_len)
        
        # Should be within reasonable CAN frame size limits
        max_can_bits = 8 * 8 + 64 + 20  # Max payload + overhead + margin
        assert result <= max_can_bits, f"Frame bits {result} too large for CAN protocol"


class TestAnalyzerStatisticalProperties:
    """Property-based tests for analyzer statistical calculations."""
    
    @given(can_ids=st.lists(st.integers(min_value=0, max_value=0x7FF), min_size=1, max_size=20),
           payload_lengths=st.lists(st.integers(min_value=0, max_value=CAN_MAX_DLC), min_size=1, max_size=20),
           bitrate=st.integers(min_value=1000, max_value=1000000))
    @settings(max_examples=20, deadline=5000)  # Limit for performance
    @patch('socketcan_sa.analyzer.Console')
    @patch('can.interface.Bus')
    @patch('time.time')
    def test_bus_load_never_exceeds_100_percent(self, mock_time, mock_bus_class, mock_console_class, 
                                               can_ids, payload_lengths, bitrate):
        """Test that calculated bus load never exceeds 100%."""
        mock_bus = Mock()
        mock_bus_class.return_value = mock_bus
        mock_console = Mock()
        mock_console_class.return_value = mock_console
        
        assume(len(can_ids) > 0 and len(payload_lengths) > 0)
        
        # Create frames
        frames = []
        for i, (can_id, payload_len) in enumerate(zip(can_ids, payload_lengths)):
            frame = Mock()
            frame.arbitration_id = can_id
            frame.data = b'\x00' * payload_len
            frames.append(frame)
        
        # Generate timestamps
        start_time = 1000.0
        time_values = [start_time]
        for i in range(len(frames) + 5):
            time_values.append(start_time + i * 0.01)
        time_values.append(start_time + 1.0)
        time_values.append(start_time + 1.1)
        
        time_call_count = 0
        def time_side_effect():
            nonlocal time_call_count
            if time_call_count < len(time_values):
                result = time_values[time_call_count]
                time_call_count += 1
                return result
            return time_values[-1] + 1.0
        
        recv_call_count = 0
        def recv_side_effect(timeout=None):
            nonlocal recv_call_count
            recv_call_count += 1
            if recv_call_count <= len(frames):
                return frames[recv_call_count - 1]
            elif recv_call_count <= len(frames) + 3:
                return None
            else:
                raise KeyboardInterrupt()
        
        mock_time.side_effect = time_side_effect
        mock_bus.recv.side_effect = recv_side_effect
        
        with patch('builtins.print'):
            analyze("test_iface", interval=1.0, bitrate=bitrate)
        
        # Check that bus load in console output never exceeds 100%
        console_calls = [str(call) for call in mock_console.print.call_args_list]
        for call in console_calls:
            if "bus_load=" in call and "%" in call:
                # Extract bus load percentage
                parts = call.split("bus_load=")
                if len(parts) > 1:
                    bus_load_part = parts[1].split("%")[0]
                    try:
                        bus_load = float(bus_load_part)
                        assert bus_load <= 100.0, f"Bus load should not exceed 100%: {bus_load}%"
                        assert bus_load >= 0.0, f"Bus load should not be negative: {bus_load}%"
                    except ValueError:
                        pass  # Skip if parsing fails
    
    @given(frame_count=st.integers(min_value=1, max_value=100),
           window_duration=st.floats(min_value=0.1, max_value=10.0),
           can_id=st.integers(min_value=0, max_value=0x7FF))
    @settings(max_examples=20, deadline=3000)
    @patch('socketcan_sa.analyzer.Console')
    @patch('can.interface.Bus')
    @patch('time.time')
    def test_fps_calculation_property(self, mock_time, mock_bus_class, mock_console_class,
                                     frame_count, window_duration, can_id):
        """Test that FPS calculation is mathematically consistent."""
        mock_bus = Mock()
        mock_bus_class.return_value = mock_bus
        mock_console = Mock()
        mock_console_class.return_value = mock_console
        
        # Create frames
        frame = Mock()
        frame.arbitration_id = can_id
        frame.data = b'\x01\x02'
        
        # Generate timestamps
        start_time = 1000.0
        time_values = [start_time]
        for i in range(frame_count + 5):
            time_values.append(start_time + i * (window_duration / frame_count))
        time_values.append(start_time + window_duration)
        time_values.append(start_time + window_duration + 0.1)
        
        time_call_count = 0
        def time_side_effect():
            nonlocal time_call_count
            if time_call_count < len(time_values):
                result = time_values[time_call_count]
                time_call_count += 1
                return result
            return time_values[-1] + 1.0
        
        recv_call_count = 0
        def recv_side_effect(timeout=None):
            nonlocal recv_call_count
            recv_call_count += 1
            if recv_call_count <= frame_count:
                return frame
            elif recv_call_count <= frame_count + 3:
                return None
            else:
                raise KeyboardInterrupt()
        
        mock_time.side_effect = time_side_effect
        mock_bus.recv.side_effect = recv_side_effect
        
        with patch('builtins.print'):
            analyze("test_iface", interval=window_duration)
        
        # Verify FPS is reasonable
        console_calls = [str(call) for call in mock_console.print.call_args_list]
        for call in console_calls:
            if f"ID=0x{can_id:X}" in call and "fps=" in call:
                parts = call.split("fps=")
                if len(parts) > 1:
                    fps_part = parts[1].split()[0]
                    try:
                        fps = float(fps_part)
                        expected_fps = frame_count / window_duration
                        # FPS should be close to expected (within reasonable tolerance)
                        tolerance = expected_fps * 0.5  # 50% tolerance for mock timing
                        assert fps >= 0, f"FPS should be non-negative: {fps}"
                        assert fps <= expected_fps + tolerance, f"FPS too high: {fps} > {expected_fps + tolerance}"
                    except ValueError:
                        pass
    
    @given(payload_lengths=st.lists(st.integers(min_value=0, max_value=CAN_MAX_DLC), min_size=1, max_size=50),
           can_id=st.integers(min_value=0, max_value=0x7FF))
    @settings(max_examples=15, deadline=3000)
    @patch('socketcan_sa.analyzer.Console')
    @patch('can.interface.Bus')
    @patch('time.time')
    def test_average_payload_length_property(self, mock_time, mock_bus_class, mock_console_class,
                                           payload_lengths, can_id):
        """Test that average payload length calculation is correct."""
        mock_bus = Mock()
        mock_bus_class.return_value = mock_bus
        mock_console = Mock()
        mock_console_class.return_value = mock_console
        
        # Create frames with specific payload lengths
        frames = []
        for length in payload_lengths:
            frame = Mock()
            frame.arbitration_id = can_id
            frame.data = b'\x00' * length
            frames.append(frame)
        
        # Generate timestamps
        start_time = 1000.0
        time_values = [start_time]
        for i in range(len(frames) + 5):
            time_values.append(start_time + i * 0.01)
        time_values.append(start_time + 1.0)
        time_values.append(start_time + 1.1)
        
        time_call_count = 0
        def time_side_effect():
            nonlocal time_call_count
            if time_call_count < len(time_values):
                result = time_values[time_call_count]
                time_call_count += 1
                return result
            return time_values[-1] + 1.0
        
        recv_call_count = 0
        def recv_side_effect(timeout=None):
            nonlocal recv_call_count
            recv_call_count += 1
            if recv_call_count <= len(frames):
                return frames[recv_call_count - 1]
            elif recv_call_count <= len(frames) + 3:
                return None
            else:
                raise KeyboardInterrupt()
        
        mock_time.side_effect = time_side_effect
        mock_bus.recv.side_effect = recv_side_effect
        
        with patch('builtins.print'):
            analyze("test_iface", interval=1.0)
        
        # Calculate expected average
        expected_avg = sum(payload_lengths) / len(payload_lengths)
        
        # Check reported average in console
        console_calls = [str(call) for call in mock_console.print.call_args_list]
        for call in console_calls:
            if f"ID=0x{can_id:X}" in call and "avg_len=" in call:
                parts = call.split("avg_len=")
                if len(parts) > 1:
                    avg_part = parts[1].split()[0]
                    try:
                        reported_avg = float(avg_part)
                        # Should be close to expected average
                        tolerance = 0.1
                        assert abs(reported_avg - expected_avg) <= tolerance, \
                            f"Average payload length mismatch: {reported_avg} vs {expected_avg}"
                    except ValueError:
                        pass
    
    @given(inter_arrival_times=st.lists(st.floats(min_value=0.001, max_value=1.0), min_size=2, max_size=20),
           can_id=st.integers(min_value=0, max_value=0x7FF))
    @settings(max_examples=15, deadline=3000)
    @patch('socketcan_sa.analyzer.Console')
    @patch('can.interface.Bus')
    @patch('time.time')
    def test_jitter_calculation_property(self, mock_time, mock_bus_class, mock_console_class,
                                        inter_arrival_times, can_id):
        """Test that jitter calculation properties hold."""
        mock_bus = Mock()
        mock_bus_class.return_value = mock_bus
        mock_console = Mock()
        mock_console_class.return_value = mock_console
        
        # Create frame
        frame = Mock()
        frame.arbitration_id = can_id
        frame.data = b'\x01\x02'
        
        # Generate timestamps based on inter-arrival times
        start_time = 1000.0
        time_values = [start_time]
        current_time = start_time
        
        for interval in inter_arrival_times:
            current_time += interval
            time_values.append(current_time)
        
        time_values.append(current_time + 1.0)  # Window end
        time_values.append(current_time + 1.1)  # Extra time
        
        time_call_count = 0
        def time_side_effect():
            nonlocal time_call_count
            if time_call_count < len(time_values):
                result = time_values[time_call_count]
                time_call_count += 1
                return result
            return time_values[-1] + 1.0
        
        recv_call_count = 0
        def recv_side_effect(timeout=None):
            nonlocal recv_call_count
            recv_call_count += 1
            if recv_call_count <= len(inter_arrival_times):
                return frame
            elif recv_call_count <= len(inter_arrival_times) + 3:
                return None
            else:
                raise KeyboardInterrupt()
        
        mock_time.side_effect = time_side_effect
        mock_bus.recv.side_effect = recv_side_effect
        
        with patch('builtins.print'):
            analyze("test_iface", interval=2.0)  # Longer window to capture all frames
        
        # Jitter should be non-negative
        console_calls = [str(call) for call in mock_console.print.call_args_list]
        for call in console_calls:
            if f"ID=0x{can_id:X}" in call and "avg_jitter=" in call:
                parts = call.split("avg_jitter=")
                if len(parts) > 1:
                    jitter_part = parts[1].split("ms")[0]
                    try:
                        jitter = float(jitter_part)
                        assert jitter >= 0, f"Jitter should be non-negative: {jitter}ms"
                        # Jitter should be reasonable compared to inter-arrival times
                        max_interval = max(inter_arrival_times) * 1000  # Convert to ms
                        assert jitter <= max_interval * 2, f"Jitter too large: {jitter}ms vs max interval {max_interval}ms"
                    except ValueError:
                        pass


class TestAnalyzerInvariantProperties:
    """Test invariant properties that should always hold."""
    
    @given(can_ids=st.lists(st.integers(min_value=0, max_value=0x7FF), min_size=1, max_size=10),
           payload_size=st.integers(min_value=0, max_value=CAN_MAX_DLC))
    @settings(max_examples=15, deadline=3000)
    @patch('socketcan_sa.analyzer.Console')
    @patch('can.interface.Bus')
    @patch('time.time')
    def test_frame_count_never_negative(self, mock_time, mock_bus_class, mock_console_class,
                                       can_ids, payload_size):
        """Test that frame counts are never negative."""
        mock_bus = Mock()
        mock_bus_class.return_value = mock_bus
        mock_console = Mock()
        mock_console_class.return_value = mock_console
        
        # Create frames
        frames = []
        for can_id in can_ids:
            frame = Mock()
            frame.arbitration_id = can_id
            frame.data = b'\x00' * payload_size
            frames.append(frame)
        
        # Generate timestamps
        start_time = 1000.0
        time_values = [start_time]
        for i in range(len(frames) + 5):
            time_values.append(start_time + i * 0.01)
        time_values.append(start_time + 1.0)
        
        time_call_count = 0
        def time_side_effect():
            nonlocal time_call_count
            if time_call_count < len(time_values):
                result = time_values[time_call_count]
                time_call_count += 1
                return result
            return time_values[-1] + 1.0
        
        recv_call_count = 0
        def recv_side_effect(timeout=None):
            nonlocal recv_call_count
            recv_call_count += 1
            if recv_call_count <= len(frames):
                return frames[recv_call_count - 1]
            elif recv_call_count <= len(frames) + 3:
                return None
            else:
                raise KeyboardInterrupt()
        
        mock_time.side_effect = time_side_effect
        mock_bus.recv.side_effect = recv_side_effect
        
        with patch('builtins.print'):
            analyze("test_iface", interval=1.0)
        
        # Check all counts are non-negative
        console_calls = [str(call) for call in mock_console.print.call_args_list]
        for call in console_calls:
            if "count=" in call:
                parts = call.split("count=")
                if len(parts) > 1:
                    count_part = parts[1].split()[0]
                    try:
                        count = int(count_part)
                        assert count >= 0, f"Frame count should be non-negative: {count}"
                    except ValueError:
                        pass
    
    @given(window_interval=st.floats(min_value=0.1, max_value=10.0),
           bitrate=st.integers(min_value=1000, max_value=1000000))
    @settings(max_examples=10, deadline=3000)
    @patch('socketcan_sa.analyzer.Console')
    @patch('can.interface.Bus')
    @patch('time.time')
    def test_empty_window_handling_property(self, mock_time, mock_bus_class, mock_console_class,
                                          window_interval, bitrate):
        """Test that empty windows are handled gracefully."""
        mock_bus = Mock()
        mock_bus_class.return_value = mock_bus
        mock_console = Mock()
        mock_console_class.return_value = mock_console
        
        # No frames, just timeouts
        mock_bus.recv.return_value = None
        
        time_values = [1000.0, 1000.0 + window_interval, 1000.0 + window_interval + 0.1]
        time_call_count = 0
        def time_side_effect():
            nonlocal time_call_count
            if time_call_count < len(time_values):
                result = time_values[time_call_count]
                time_call_count += 1
                return result
            return time_values[-1] + 1.0
        
        recv_call_count = 0
        def recv_side_effect(timeout=None):
            nonlocal recv_call_count
            recv_call_count += 1
            if recv_call_count <= 3:
                return None
            else:
                raise KeyboardInterrupt()
        
        mock_time.side_effect = time_side_effect
        mock_bus.recv.side_effect = recv_side_effect
        
        # Should handle empty window without crashing
        with patch('builtins.print'):
            analyze("test_iface", interval=window_interval, bitrate=bitrate)
        
        # Should still report (even if empty)
        mock_console.print.assert_called()
    
    def test_total_bits_calculation_property(self):
        """Test that total bits calculation is consistent."""
        # Test with known values
        test_cases = [
            (0, 47),    # Empty frame
            (1, 55),    # 1 byte
            (8, 111),   # Max payload
        ]
        
        for payload_len, expected_bits in test_cases:
            result = _frame_bits(payload_len)
            assert result == expected_bits, f"Frame bits mismatch for {payload_len} bytes: {result} != {expected_bits}"
    
    @given(can_id=st.integers(min_value=0, max_value=0x7FF),
           payload_len=st.integers(min_value=0, max_value=CAN_MAX_DLC),
           count=st.integers(min_value=1, max_value=100))
    @settings(max_examples=20, deadline=3000)
    @patch('socketcan_sa.analyzer.Console')
    @patch('can.interface.Bus')
    @patch('time.time')
    def test_statistics_consistency_property(self, mock_time, mock_bus_class, mock_console_class,
                                           can_id, payload_len, count):
        """Test that statistics are internally consistent."""
        mock_bus = Mock()
        mock_bus_class.return_value = mock_bus
        mock_console = Mock()
        mock_console_class.return_value = mock_console
        
        # Create identical frames
        frame = Mock()
        frame.arbitration_id = can_id
        frame.data = b'\x00' * payload_len
        
        # Generate regular timestamps
        start_time = 1000.0
        time_values = [start_time]
        for i in range(count + 5):
            time_values.append(start_time + i * 0.01)
        time_values.append(start_time + 1.0)
        
        time_call_count = 0
        def time_side_effect():
            nonlocal time_call_count
            if time_call_count < len(time_values):
                result = time_values[time_call_count]
                time_call_count += 1
                return result
            return time_values[-1] + 1.0
        
        recv_call_count = 0
        def recv_side_effect(timeout=None):
            nonlocal recv_call_count
            recv_call_count += 1
            if recv_call_count <= count:
                return frame
            elif recv_call_count <= count + 3:
                return None
            else:
                raise KeyboardInterrupt()
        
        mock_time.side_effect = time_side_effect
        mock_bus.recv.side_effect = recv_side_effect
        
        with patch('builtins.print'):
            analyze("test_iface", interval=1.0)
        
        # For identical frames, average payload should equal individual payload
        console_calls = [str(call) for call in mock_console.print.call_args_list]
        for call in console_calls:
            if f"ID=0x{can_id:X}" in call and "avg_len=" in call:
                parts = call.split("avg_len=")
                if len(parts) > 1:
                    avg_part = parts[1].split()[0]
                    try:
                        avg_len = float(avg_part)
                        # Should equal the payload length
                        assert abs(avg_len - payload_len) < 0.1, \
                            f"Average length inconsistent: {avg_len} vs {payload_len}"
                    except ValueError:
                        pass


class TestAnalyzerRobustnessProperties:
    """Test robustness properties under various conditions."""
    
    @given(valid_payloads=st.lists(st.integers(min_value=0, max_value=CAN_MAX_DLC), min_size=1, max_size=10),
           invalid_payloads=st.lists(st.integers(min_value=CAN_MAX_DLC + 1, max_value=20), min_size=1, max_size=5))
    @settings(max_examples=10, deadline=3000)
    @patch('socketcan_sa.analyzer.Console')
    @patch('can.interface.Bus')
    @patch('time.time')
    def test_mixed_valid_invalid_dlc_property(self, mock_time, mock_bus_class, mock_console_class,
                                             valid_payloads, invalid_payloads):
        """Test handling of mixed valid and invalid DLC frames."""
        mock_bus = Mock()
        mock_bus_class.return_value = mock_bus
        mock_console = Mock()
        mock_console_class.return_value = mock_console
        
        # Create mixed frames
        frames = []
        can_id = 0x123
        
        # Valid frames
        for payload_len in valid_payloads:
            frame = Mock()
            frame.arbitration_id = can_id
            frame.data = b'\x00' * payload_len
            frames.append(frame)
        
        # Invalid frames (will trigger warnings)
        for payload_len in invalid_payloads:
            frame = Mock()
            frame.arbitration_id = can_id + 1
            frame.data = b'\x00' * payload_len
            frames.append(frame)
        
        # Generate timestamps to ensure window reporting triggers
        start_time = 1000.0
        time_values = [start_time]  # window_start
        for i in range(len(frames) + 2):
            time_values.append(start_time + i * 0.01)  # Frame timestamps
        time_values.append(start_time + 1.1)  # Cross interval threshold
        
        time_call_count = 0
        def time_side_effect():
            nonlocal time_call_count
            if time_call_count < len(time_values):
                result = time_values[time_call_count]
                time_call_count += 1
                return result
            return time_values[-1] + 1.0
        
        recv_call_count = 0
        def recv_side_effect(timeout=None):
            nonlocal recv_call_count
            recv_call_count += 1
            if recv_call_count <= len(frames):
                return frames[recv_call_count - 1]
            elif recv_call_count <= len(frames) + 3:
                return None
            else:
                raise KeyboardInterrupt()
        
        mock_time.side_effect = time_side_effect
        mock_bus.recv.side_effect = recv_side_effect
        
        # Should handle mixed frames without crashing
        with patch('builtins.print') as mock_print:
            analyze("test_iface", interval=1.0)
        
        # Should report some statistics for valid frames
        mock_console.print.assert_called()
        
        # Should warn about invalid DLC
        warning_calls = [str(call) for call in mock_print.call_args_list]
        warning_found = any("Warning" in call for call in warning_calls)
        if invalid_payloads:  # Only expect warnings if there were invalid payloads
            assert warning_found, "Should warn about invalid DLC"
    
    @given(window_size=st.floats(min_value=0.001, max_value=0.1),  # Very small windows
           frame_count=st.integers(min_value=1, max_value=10))
    @settings(max_examples=10, deadline=3000)
    @patch('socketcan_sa.analyzer.Console')
    @patch('can.interface.Bus')
    @patch('time.time')
    def test_tiny_window_robustness_property(self, mock_time, mock_bus_class, mock_console_class,
                                            window_size, frame_count):
        """Test robustness with very small time windows."""
        mock_bus = Mock()
        mock_bus_class.return_value = mock_bus
        mock_console = Mock()
        mock_console_class.return_value = mock_console
        
        # Create frame
        frame = Mock()
        frame.arbitration_id = 0x100
        frame.data = b'\x01\x02'
        
        # Generate timestamps for tiny window - ensure we cross the interval
        start_time = 1000.0
        time_values = [start_time]  # window_start
        for i in range(frame_count + 2):
            time_values.append(start_time + i * (window_size / (frame_count + 5)))
        time_values.append(start_time + window_size + 0.001)  # Definitely cross interval
        
        time_call_count = 0
        def time_side_effect():
            nonlocal time_call_count
            if time_call_count < len(time_values):
                result = time_values[time_call_count]
                time_call_count += 1
                return result
            return time_values[-1] + 1.0
        
        recv_call_count = 0
        def recv_side_effect(timeout=None):
            nonlocal recv_call_count
            recv_call_count += 1
            if recv_call_count <= frame_count:
                return frame
            elif recv_call_count <= frame_count + 3:
                return None
            else:
                raise KeyboardInterrupt()
        
        mock_time.side_effect = time_side_effect
        mock_bus.recv.side_effect = recv_side_effect
        
        # Should handle tiny windows without numerical issues
        with patch('builtins.print'):
            analyze("test_iface", interval=window_size)
        
        # Should still report (even for tiny windows)
        mock_console.print.assert_called()
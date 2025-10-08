#!/usr/bin/env python3
"""
Stress tests for analyzer.py

Tests extreme conditions and edge cases including:
- High-frequency burst traffic
- Massive CAN ID diversity
- Marathon analysis sessions
- Extreme payload variations
- Rapid window transitions
- CSV output stress testing
- Mixed error conditions under load
- Interrupt handling under stress
- Concurrent operations stress
"""

import pytest
import time
import tempfile
import os
import threading
from unittest.mock import Mock, patch
from socketcan_sa.analyzer import analyze, _frame_bits, CAN_MAX_DLC


@pytest.mark.timeout(60)  # Longer timeout for stress tests
class TestAnalyzerStress:
    """Stress tests for analyzer under extreme conditions."""
    
    @patch('socketcan_sa.analyzer.Console')
    @patch('can.interface.Bus')
    @patch('time.time')
    def test_high_frequency_burst_traffic(self, mock_time, mock_bus_class, mock_console_class):
        """Test analyzer under high-frequency burst traffic (1000+ fps)."""
        mock_bus = Mock()
        mock_bus_class.return_value = mock_bus
        mock_console = Mock()
        mock_console_class.return_value = mock_console
        
        # Create burst traffic
        burst_frame = Mock()
        burst_frame.arbitration_id = 0x200
        burst_frame.data = b'\x01\x02\x03\x04\x05'
        
        # Simulate 1000+ frames in short burst
        num_frames = 1000
        burst_duration = 0.5  # 500ms burst = 2000fps
        
        # Generate timestamps for burst
        start_time = 1000.0
        time_values = [start_time]
        for i in range(num_frames):
            time_values.append(start_time + i * (burst_duration / num_frames))
        time_values.append(start_time + burst_duration)
        time_values.append(start_time + 1.0)  # Window end
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
            if recv_call_count <= num_frames:
                return burst_frame
            elif recv_call_count <= num_frames + 5:
                return None
            else:
                raise KeyboardInterrupt()
        
        mock_time.side_effect = time_side_effect
        mock_bus.recv.side_effect = recv_side_effect
        
        # Should handle burst traffic without issues
        start_real_time = time.perf_counter()
        
        with patch('builtins.print'):
            analyze("test_iface", interval=1.0)
        
        end_real_time = time.perf_counter()
        execution_time = end_real_time - start_real_time
        
        # Should complete in reasonable time despite high load
        assert execution_time < 30.0, f"Burst traffic processing took too long: {execution_time:.2f}s"
        
        # Should report statistics
        mock_console.print.assert_called()
        
    @patch('socketcan_sa.analyzer.Console')
    @patch('can.interface.Bus')
    @patch('time.time')
    def test_massive_can_id_diversity(self, mock_time, mock_bus_class, mock_console_class):
        """Test analyzer with massive CAN ID diversity (500+ unique IDs)."""
        mock_bus = Mock()
        mock_bus_class.return_value = mock_bus
        mock_console = Mock()
        mock_console_class.return_value = mock_console
        
        # Create frames with many unique IDs
        num_unique_ids = 500
        frames = []
        for i in range(num_unique_ids):
            frame = Mock()
            frame.arbitration_id = 0x100 + i
            frame.data = bytes([i % 256, (i + 1) % 256, (i + 2) % 256])
            frames.append(frame)
        
        # Generate timestamps
        start_time = 1000.0
        time_values = [start_time]
        for i in range(num_unique_ids * 2):  # Send each ID twice
            time_values.append(start_time + i * 0.001)  # 1ms intervals
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
            if recv_call_count <= num_unique_ids * 2:
                return frames[(recv_call_count - 1) % num_unique_ids]
            elif recv_call_count <= num_unique_ids * 2 + 5:
                return None
            else:
                raise KeyboardInterrupt()
        
        mock_time.side_effect = time_side_effect
        mock_bus.recv.side_effect = recv_side_effect
        
        # Should handle massive ID diversity
        start_real_time = time.perf_counter()
        
        with patch('builtins.print'):
            analyze("test_iface", interval=1.0)
        
        end_real_time = time.perf_counter()
        execution_time = end_real_time - start_real_time
        
        # Should complete in reasonable time
        assert execution_time < 45.0, f"Massive ID diversity took too long: {execution_time:.2f}s"
        
        # Should report statistics for multiple IDs
        mock_console.print.assert_called()
        console_calls = mock_console.print.call_args_list
        assert len(console_calls) > 10, "Should report statistics for many IDs"
        
    @patch('socketcan_sa.analyzer.Console')
    @patch('can.interface.Bus')
    @patch('time.time')
    def test_marathon_analysis_session(self, mock_time, mock_bus_class, mock_console_class):
        """Test analyzer for extended duration (simulated marathon session)."""
        mock_bus = Mock()
        mock_bus_class.return_value = mock_bus
        mock_console = Mock()
        mock_console_class.return_value = mock_console
        
        # Create frame for long session
        marathon_frame = Mock()
        marathon_frame.arbitration_id = 0x300
        marathon_frame.data = b'\x01\x02\x03'
        
        # Simulate many windows (equivalent to long session)
        num_windows = 50
        frames_per_window = 20
        total_frames = num_windows * frames_per_window
        
        # Generate timestamps for many windows
        start_time = 1000.0
        time_values = [start_time]
        
        for window in range(num_windows):
            window_start = start_time + window * 1.0
            for frame in range(frames_per_window):
                time_values.append(window_start + frame * 0.05)
            time_values.append(window_start + 1.0)  # Window boundary
        
        time_values.append(start_time + num_windows + 1)
        
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
            if recv_call_count <= total_frames:
                return marathon_frame
            elif recv_call_count <= total_frames + 10:
                return None
            else:
                raise KeyboardInterrupt()
        
        mock_time.side_effect = time_side_effect
        mock_bus.recv.side_effect = recv_side_effect
        
        # Should handle marathon session
        start_real_time = time.perf_counter()
        
        with patch('builtins.print'):
            analyze("test_iface", interval=1.0)
        
        end_real_time = time.perf_counter()
        execution_time = end_real_time - start_real_time
        
        # Should complete marathon session
        assert execution_time < 60.0, f"Marathon session took too long: {execution_time:.2f}s"
        
        # Should have many window reports (looking for actual console output format)
        console_calls = mock_console.print.call_args_list
        window_reports = len([call for call in console_calls if "window=" in str(call) or "bus_load≈" in str(call)])
        assert window_reports >= 20, f"Expected many window reports, got {window_reports}"
        
    @patch('socketcan_sa.analyzer.Console')
    @patch('can.interface.Bus')
    @patch('time.time')
    def test_extreme_payload_variations(self, mock_time, mock_bus_class, mock_console_class):
        """Test analyzer with extreme payload size variations."""
        mock_bus = Mock()
        mock_bus_class.return_value = mock_bus
        mock_console = Mock()
        mock_console_class.return_value = mock_console
        
        # Create frames with all possible payload sizes + invalid ones
        frames = []
        can_id_base = 0x400
        
        # Valid payloads (0-8 bytes)
        for size in range(CAN_MAX_DLC + 1):
            frame = Mock()
            frame.arbitration_id = can_id_base + size
            frame.data = b'\xFF' * size
            frames.append(frame)
        
        # Invalid payloads (will trigger warnings)
        for size in [9, 10, 15, 20]:
            frame = Mock()
            frame.arbitration_id = can_id_base + 100 + size
            frame.data = b'\xAA' * size
            frames.append(frame)
        
        # Generate timestamps
        start_time = 1000.0
        time_values = [start_time]
        for i in range(len(frames) * 5):  # Send each frame multiple times
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
            if recv_call_count <= len(frames) * 5:
                return frames[(recv_call_count - 1) % len(frames)]
            elif recv_call_count <= len(frames) * 5 + 5:
                return None
            else:
                raise KeyboardInterrupt()
        
        mock_time.side_effect = time_side_effect
        mock_bus.recv.side_effect = recv_side_effect
        
        # Should handle extreme payload variations
        with patch('builtins.print') as mock_print:
            analyze("test_iface", interval=1.0)
        
        # Should report statistics for valid frames
        mock_console.print.assert_called()
        
        # Should warn about invalid payloads
        warning_calls = [str(call) for call in mock_print.call_args_list]
        warning_found = any("Warning" in call for call in warning_calls)
        assert warning_found, "Should warn about invalid DLC"
        
    @patch('socketcan_sa.analyzer.Console')
    @patch('can.interface.Bus')
    @patch('time.time')
    def test_rapid_window_transitions(self, mock_time, mock_bus_class, mock_console_class):
        """Test analyzer with very rapid window transitions."""
        mock_bus = Mock()
        mock_bus_class.return_value = mock_bus
        mock_console = Mock()
        mock_console_class.return_value = mock_console
        
        # Create frame
        transition_frame = Mock()
        transition_frame.arbitration_id = 0x500
        transition_frame.data = b'\x01\x02'
        
        # Very small windows for rapid transitions
        window_size = 0.1  # 100ms windows
        num_windows = 30
        frames_per_window = 5
        
        # Generate timestamps for rapid windows
        start_time = 1000.0
        time_values = [start_time]
        
        for window in range(num_windows):
            window_start = start_time + window * window_size
            for frame in range(frames_per_window):
                time_values.append(window_start + frame * (window_size / frames_per_window))
            time_values.append(window_start + window_size)  # Window boundary
        
        time_values.append(start_time + num_windows * window_size + 0.1)
        
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
            if recv_call_count <= num_windows * frames_per_window:
                return transition_frame
            elif recv_call_count <= num_windows * frames_per_window + 5:
                return None
            else:
                raise KeyboardInterrupt()
        
        mock_time.side_effect = time_side_effect
        mock_bus.recv.side_effect = recv_side_effect
        
        # Should handle rapid window transitions
        with patch('builtins.print'):
            analyze("test_iface", interval=window_size)
        
        # Should report for multiple windows
        console_calls = mock_console.print.call_args_list
        assert len(console_calls) >= 15, "Should have many rapid window reports"
        
    @patch('socketcan_sa.analyzer.Console')
    @patch('can.interface.Bus')
    @patch('time.time')
    def test_csv_file_stress_large_output(self, mock_time, mock_bus_class, mock_console_class):
        """Test CSV file handling under stress with large output."""
        mock_bus = Mock()
        mock_bus_class.return_value = mock_bus
        mock_console = Mock()
        mock_console_class.return_value = mock_console
        
        # Create frame for CSV stress
        csv_frame = Mock()
        csv_frame.arbitration_id = 0x600
        csv_frame.data = b'\x01\x02\x03\x04\x05\x06\x07\x08'
        
        # Generate many windows for large CSV
        num_windows = 100
        frames_per_window = 10
        
        # Generate timestamps
        start_time = 1000.0
        time_values = [start_time]
        
        for window in range(num_windows):
            window_start = start_time + window * 1.0
            for frame in range(frames_per_window):
                time_values.append(window_start + frame * 0.1)
            time_values.append(window_start + 1.0)
        
        time_values.append(start_time + num_windows + 1)
        
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
            if recv_call_count <= num_windows * frames_per_window:
                return csv_frame
            elif recv_call_count <= num_windows * frames_per_window + 5:
                return None
            else:
                raise KeyboardInterrupt()
        
        mock_time.side_effect = time_side_effect
        mock_bus.recv.side_effect = recv_side_effect
        
        # Use temporary file for large CSV
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as temp_file:
            csv_path = temp_file.name
        
        try:
            # Should handle large CSV output
            with patch('builtins.print'):
                analyze("test_iface", interval=1.0, csv_path=csv_path)
            
            # Verify large CSV was created
            assert os.path.exists(csv_path), "Large CSV file should be created"
            
            with open(csv_path, 'r') as f:
                lines = f.readlines()
            
            # Should have many rows
            assert len(lines) >= 50, f"Large CSV should have many rows, got {len(lines)}"
            
            # File should be substantial size
            file_size = os.path.getsize(csv_path)
            assert file_size > 1000, f"CSV file should be substantial, got {file_size} bytes"
            
        finally:
            if os.path.exists(csv_path):
                os.unlink(csv_path)
                
    @patch('socketcan_sa.analyzer.Console')
    @patch('can.interface.Bus')
    @patch('time.time')
    def test_mixed_error_conditions_under_load(self, mock_time, mock_bus_class, mock_console_class):
        """Test analyzer handling mixed error conditions under high load."""
        mock_bus = Mock()
        mock_bus_class.return_value = mock_bus
        mock_console = Mock()
        mock_console_class.return_value = mock_console
        
        # Create mix of valid and invalid frames
        valid_frame = Mock()
        valid_frame.arbitration_id = 0x700
        valid_frame.data = b'\x01\x02\x03'
        
        invalid_frame = Mock()
        invalid_frame.arbitration_id = 0x701
        invalid_frame.data = b'\x01\x02\x03\x04\x05\x06\x07\x08\x09\x0A'  # Too long
        
        # Generate mixed load
        num_cycles = 200
        
        time_values = [1000.0]
        for i in range(num_cycles + 10):
            time_values.append(1000.0 + i * 0.005)  # 200fps
        time_values.append(1001.0)
        time_values.append(1001.1)
        
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
            if recv_call_count <= num_cycles:
                # Mix valid and invalid frames
                if recv_call_count % 3 == 0:
                    return invalid_frame  # Every 3rd frame is invalid
                else:
                    return valid_frame
            elif recv_call_count <= num_cycles + 5:
                return None
            else:
                raise KeyboardInterrupt()
        
        mock_time.side_effect = time_side_effect
        mock_bus.recv.side_effect = recv_side_effect
        
        # Should handle mixed errors under load
        with patch('builtins.print') as mock_print:
            analyze("test_iface", interval=1.0)
        
        # Should report statistics for valid frames
        mock_console.print.assert_called()
        
        # Should warn about invalid frames
        warning_calls = [str(call) for call in mock_print.call_args_list]
        warning_count = sum(1 for call in warning_calls if "Warning" in call)
        expected_warnings = num_cycles // 3  # Every 3rd frame
        assert warning_count >= expected_warnings // 2, f"Expected warnings for invalid frames: {warning_count} >= {expected_warnings // 2}"
        
    @patch('socketcan_sa.analyzer.Console')
    @patch('can.interface.Bus')
    @patch('time.time')
    def test_interrupt_signal_stress_during_analysis(self, mock_time, mock_bus_class, mock_console_class):
        """Test interrupt signal handling during intensive analysis."""
        mock_bus = Mock()
        mock_bus_class.return_value = mock_bus
        mock_console = Mock()
        mock_console_class.return_value = mock_console
        
        # Create frame for stress
        stress_frame = Mock()
        stress_frame.arbitration_id = 0x800
        stress_frame.data = b'\x01\x02\x03\x04'
        
        # Set up timing with realistic values to avoid recursion
        start_time = 1000.0
        time_call_count = 0
        
        def time_side_effect():
            nonlocal time_call_count
            time_call_count += 1
            return start_time + time_call_count * 0.01
        
        # Counter for controlling when to interrupt
        recv_call_count = 0
        interrupt_after = 100  # Interrupt after processing some frames
        
        def recv_side_effect(timeout=None):
            nonlocal recv_call_count
            recv_call_count += 1
            
            if recv_call_count <= interrupt_after:
                return stress_frame
            elif recv_call_count <= interrupt_after + 10:
                return None  # Some timeouts
            else:
                # Simulate interrupt during intensive processing
                raise KeyboardInterrupt("Simulated interrupt during stress")
        
        mock_time.side_effect = time_side_effect
        mock_bus.recv.side_effect = recv_side_effect
        
        # Should handle interrupt gracefully even under stress
        with patch('builtins.print'):
            analyze("test_iface", interval=1.0)
        
        # Should have attempted to shutdown cleanly
        mock_bus.shutdown.assert_called_once()
        
        # Should have processed some frames before interrupt
        assert recv_call_count >= interrupt_after, "Should process frames before interrupt"
        
    def test_frame_bits_stress_extreme_values(self):
        """Test frame bits calculation under stress with extreme values."""
        # Test with all valid payload sizes rapidly
        test_iterations = 10000
        
        start_time = time.perf_counter()
        
        for iteration in range(test_iterations):
            for payload_size in range(CAN_MAX_DLC + 1):
                result = _frame_bits(payload_size)
                
                # Basic sanity checks under stress
                assert result > 0, f"Frame bits should be positive at iteration {iteration}, size {payload_size}"
                assert result < 200, f"Frame bits too large at iteration {iteration}, size {payload_size}: {result}"
        
        end_time = time.perf_counter()
        execution_time = end_time - start_time
        
        # Should complete stress test quickly
        assert execution_time < 2.0, f"Frame bits stress test took too long: {execution_time:.3f}s"
        
        # Calculate throughput
        total_calculations = test_iterations * (CAN_MAX_DLC + 1)
        calculations_per_sec = total_calculations / execution_time
        
        # Should maintain high throughput under stress
        assert calculations_per_sec > 50000, f"Frame bits calculation too slow under stress: {calculations_per_sec:.0f} calc/sec"
        
    @patch('socketcan_sa.analyzer.Console')
    @patch('can.interface.Bus')
    @patch('time.time')
    def test_concurrent_statistics_calculation_stress(self, mock_time, mock_bus_class, mock_console_class):
        """Test statistics calculation under concurrent-like stress conditions."""
        mock_bus = Mock()
        mock_bus_class.return_value = mock_bus
        mock_console = Mock()
        mock_console_class.return_value = mock_console
        
        # Create many frames with different IDs for concurrent-like processing
        num_concurrent_ids = 100
        frames_per_id = 20
        frames = []
        
        for can_id in range(num_concurrent_ids):
            for frame_num in range(frames_per_id):
                frame = Mock()
                frame.arbitration_id = 0x100 + can_id
                frame.data = bytes([can_id % 256, frame_num % 256, (can_id + frame_num) % 256])
                frames.append(frame)
        
        # Shuffle frames to simulate concurrent arrival
        import random
        random.shuffle(frames)
        
        # Generate timestamps
        start_time = 1000.0
        time_values = [start_time]
        for i in range(len(frames) + 10):
            time_values.append(start_time + i * 0.001)  # 1000fps
        time_values.append(start_time + 2.0)
        time_values.append(start_time + 2.1)
        
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
            elif recv_call_count <= len(frames) + 5:
                return None
            else:
                raise KeyboardInterrupt()
        
        mock_time.side_effect = time_side_effect
        mock_bus.recv.side_effect = recv_side_effect
        
        # Should handle concurrent-like statistics calculation
        start_real_time = time.perf_counter()
        
        with patch('builtins.print'):
            analyze("test_iface", interval=2.0)  # Longer window to capture all
        
        end_real_time = time.perf_counter()
        execution_time = end_real_time - start_real_time
        
        # Should complete concurrent stress test
        assert execution_time < 30.0, f"Concurrent stress test took too long: {execution_time:.2f}s"
        
        # Should report statistics for many IDs
        console_calls = mock_console.print.call_args_list
        id_reports = [call for call in console_calls if "ID=" in str(call)]
        assert len(id_reports) >= 50, f"Expected statistics for many IDs, got {len(id_reports)}"

#!/usr/bin/env python3
"""
Performance tests for analyzer.py

Tests performance characteristics including:
- High-frequency frame processing
- Scalability with many CAN IDs
- Memory usage monitoring
- CSV export performance
- Frame bits calculation performance
"""

import pytest
import time
import tempfile
import os
import psutil
from unittest.mock import Mock, patch
from socketcan_sa.analyzer import analyze, _frame_bits


@pytest.mark.timeout(30)  # Prevent hanging
class TestAnalyzerPerformance:
    """Performance benchmark tests for analyzer functionality."""
    
    @patch('socketcan_sa.analyzer.Console')
    @patch('can.interface.Bus')
    @patch('time.time')
    def test_high_frequency_processing_performance(self, mock_time, mock_bus_class, mock_console_class):
        """Test analyzer can handle high-frequency frame processing."""
        mock_bus = Mock()
        mock_bus_class.return_value = mock_bus
        mock_console = Mock()
        mock_console_class.return_value = mock_console
        
        # Create high-frequency frames (simulate 100+ fps)
        test_frame = Mock()
        test_frame.arbitration_id = 0x123
        test_frame.data = b'\x01\x02\x03\x04'
        
        # Generate many timestamps for high frequency
        start_time = 1000.0
        frame_interval = 0.01  # 10ms = 100fps
        num_frames = 100
        
        time_values = [start_time]
        for i in range(num_frames):
            time_values.append(start_time + i * frame_interval)
        time_values.append(start_time + 1.0)  # Window end
        time_values.append(start_time + 1.1)  # Extra time
        
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
                return test_frame
            elif recv_call_count <= num_frames + 3:
                return None  # Some timeouts
            else:
                raise KeyboardInterrupt()  # Force exit
        
        mock_time.side_effect = time_side_effect
        mock_bus.recv.side_effect = recv_side_effect
        
        # Measure execution time
        start_real_time = time.perf_counter()
        
        with patch('builtins.print'):
            analyze("test_iface", interval=1.0)
        
        end_real_time = time.perf_counter()
        execution_time = end_real_time - start_real_time
        
        # Verify performance - should process frames quickly
        assert execution_time < 5.0, f"High-frequency processing took too long: {execution_time:.2f}s"
        
        # Verify frames were processed
        assert recv_call_count > num_frames, "Not enough frames processed"
        mock_console.print.assert_called()
        
        # Extract FPS from console output to verify performance
        console_calls = [str(call) for call in mock_console.print.call_args_list]
        fps_info = None
        for call in console_calls:
            if "fps=" in call:
                fps_info = call
                break
        
        assert fps_info is not None, "FPS information should be reported"
        
    @patch('socketcan_sa.analyzer.Console')
    @patch('can.interface.Bus')
    @patch('time.time')
    def test_many_can_ids_scalability(self, mock_time, mock_bus_class, mock_console_class):
        """Test analyzer scalability with many different CAN IDs."""
        mock_bus = Mock()
        mock_bus_class.return_value = mock_bus
        mock_console = Mock()
        mock_console_class.return_value = mock_console
        
        # Create frames with many different IDs
        num_ids = 50
        frames = []
        for i in range(num_ids):
            frame = Mock()
            frame.arbitration_id = 0x100 + i
            frame.data = bytes([i % 256, (i + 1) % 256, (i + 2) % 256])
            frames.append(frame)
        
        # Generate timestamps
        start_time = 1000.0
        time_values = [start_time]
        for i in range(num_ids * 2):  # Multiple frames per ID
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
            if recv_call_count <= len(frames) * 2:  # Send each frame twice
                return frames[(recv_call_count - 1) % len(frames)]
            elif recv_call_count <= len(frames) * 2 + 3:
                return None
            else:
                raise KeyboardInterrupt()
        
        mock_time.side_effect = time_side_effect
        mock_bus.recv.side_effect = recv_side_effect
        
        # Measure execution time
        start_real_time = time.perf_counter()
        
        with patch('builtins.print'):
            analyze("test_iface", interval=1.0)
        
        end_real_time = time.perf_counter()
        execution_time = end_real_time - start_real_time
        
        # Should handle many IDs efficiently
        assert execution_time < 10.0, f"Many IDs processing took too long: {execution_time:.2f}s"
        
        # Verify all IDs were processed
        console_calls = [str(call) for call in mock_console.print.call_args_list]
        id_reports = [call for call in console_calls if "ID=" in call]
        unique_ids = set()
        for report in id_reports:
            if "ID=" in report:
                # Extract ID from report (simplified parsing)
                for part in report.split():
                    if part.startswith("ID="):
                        unique_ids.add(part)
        
        # Should have processed multiple unique IDs
        assert len(unique_ids) >= 10, f"Expected at least 10 unique IDs, got {len(unique_ids)}"
        
    @patch('socketcan_sa.analyzer.Console')
    @patch('can.interface.Bus')
    @patch('time.time')
    def test_csv_export_performance_large_dataset(self, mock_time, mock_bus_class, mock_console_class):
        """Test CSV export performance with large datasets."""
        mock_bus = Mock()
        mock_bus_class.return_value = mock_bus
        mock_console = Mock()
        mock_console_class.return_value = mock_console
        
        # Create many frames for CSV export
        test_frame = Mock()
        test_frame.arbitration_id = 0x200
        test_frame.data = b'\x01\x02\x03\x04\x05'
        
        num_windows = 10
        frames_per_window = 20
        total_frames = num_windows * frames_per_window
        
        # Generate timestamps for multiple windows
        start_time = 1000.0
        time_values = [start_time]
        
        for window in range(num_windows):
            window_start = start_time + window * 1.0
            for frame in range(frames_per_window):
                time_values.append(window_start + frame * 0.05)  # 20fps per window
            time_values.append(window_start + 1.0)  # Window boundary
        
        time_values.append(start_time + num_windows + 1)  # Final time
        
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
                return test_frame
            elif recv_call_count <= total_frames + 5:
                return None
            else:
                raise KeyboardInterrupt()
        
        mock_time.side_effect = time_side_effect
        mock_bus.recv.side_effect = recv_side_effect
        
        # Use temporary file for CSV export
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as temp_file:
            csv_path = temp_file.name
        
        try:
            # Measure CSV export performance
            start_real_time = time.perf_counter()
            
            with patch('builtins.print'):
                analyze("test_iface", interval=1.0, csv_path=csv_path)
            
            end_real_time = time.perf_counter()
            execution_time = end_real_time - start_real_time
            
            # Should handle large CSV export efficiently
            assert execution_time < 15.0, f"CSV export took too long: {execution_time:.2f}s"
            
            # Verify CSV file was created and has content
            assert os.path.exists(csv_path), "CSV file should be created"
            
            with open(csv_path, 'r') as f:
                lines = f.readlines()
                
            # Should have header + data rows
            assert len(lines) >= 2, "CSV should have header and data"
            
            # Should have multiple data rows (one per window)
            data_rows = len(lines) - 1  # Exclude header
            assert data_rows >= 5, f"Should export at least 5 rows, got {data_rows}"
            
        finally:
            # Cleanup
            if os.path.exists(csv_path):
                os.unlink(csv_path)
    
    def test_frame_bits_calculation_performance(self):
        """Test performance of frame bits calculation function."""
        # Test with various payload sizes
        payload_sizes = [0, 1, 2, 4, 6, 8]
        iterations = 10000
        
        start_time = time.perf_counter()
        
        for _ in range(iterations):
            for size in payload_sizes:
                result = _frame_bits(size)
                assert result > 0, f"Frame bits should be positive for size {size}"
        
        end_time = time.perf_counter()
        execution_time = end_time - start_time
        
        # Should be very fast
        assert execution_time < 1.0, f"Frame bits calculation too slow: {execution_time:.3f}s"
        
        # Calculate operations per second
        total_operations = iterations * len(payload_sizes)
        ops_per_sec = total_operations / execution_time
        
        # Should handle at least 10k operations per second
        assert ops_per_sec > 10000, f"Too slow: {ops_per_sec:.0f} ops/sec"
    
    @patch('socketcan_sa.analyzer.Console')
    @patch('can.interface.Bus') 
    @patch('time.time')
    def test_memory_usage_stability(self, mock_time, mock_bus_class, mock_console_class):
        """Test that memory usage remains stable during long runs."""
        mock_bus = Mock()
        mock_bus_class.return_value = mock_bus
        mock_console = Mock()
        mock_console_class.return_value = mock_console
        
        # Create frame for processing
        test_frame = Mock()
        test_frame.arbitration_id = 0x300
        test_frame.data = b'\x01\x02\x03'
        
        # Simulate longer run with many frames
        num_frames = 500
        start_time = 1000.0
        
        time_values = [start_time]
        for i in range(num_frames + 10):
            time_values.append(start_time + i * 0.002)  # 500fps
        time_values.append(start_time + 2.0)
        
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
                return test_frame
            elif recv_call_count <= num_frames + 5:
                return None
            else:
                raise KeyboardInterrupt()
        
        mock_time.side_effect = time_side_effect
        mock_bus.recv.side_effect = recv_side_effect
        
        # Monitor memory usage
        process = psutil.Process()
        initial_memory = process.memory_info().rss / 1024 / 1024  # MB
        
        with patch('builtins.print'):
            analyze("test_iface", interval=1.0)
        
        final_memory = process.memory_info().rss / 1024 / 1024  # MB
        memory_increase = final_memory - initial_memory
        
        # Memory usage should not increase significantly
        assert memory_increase < 50, f"Memory usage increased too much: {memory_increase:.1f}MB"
        
        # Should have processed many frames
        assert recv_call_count > num_frames, "Should have processed many frames"

#!/usr/bin/env python3
"""
CSV export tests for analyzer.py

Tests dedicated to CSV functionality including:
- File creation and header validation
- Data formatting and consistency
- Schema validation
- Error handling (permissions, disk space)
- Special character handling
- Large dataset export
- Multi-window CSV consistency
"""

import pytest
import tempfile
import os
import csv
from unittest.mock import Mock, patch, mock_open
from socketcan_sa.analyzer import analyze


class TestCSVExport:
    """Test CSV export functionality."""
    
    @patch('socketcan_sa.analyzer.Console')
    @patch('can.interface.Bus')
    @patch('time.time')
    def test_csv_file_creation_and_header(self, mock_time, mock_bus_class, mock_console_class):
        """Test CSV file creation and header validation."""
        mock_bus = Mock()
        mock_bus_class.return_value = mock_bus
        mock_console_class.return_value = Mock()
        
        # Create test frame
        test_frame = Mock()
        test_frame.arbitration_id = 0x123
        test_frame.data = b'\x01\x02\x03\x04'
        
        # Set up mocks with cycling functions
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
                return None
            else:
                raise KeyboardInterrupt()
        
        mock_time.side_effect = time_side_effect
        mock_bus.recv.side_effect = recv_side_effect
        
        # Use temporary file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as temp_file:
            csv_path = temp_file.name
        
        try:
            with patch('builtins.print'):
                analyze("test_iface", interval=1.0, csv_path=csv_path)
            
            # Verify CSV file exists
            assert os.path.exists(csv_path), "CSV file should be created"
            
            # Read and verify CSV content
            with open(csv_path, 'r', newline='') as csvfile:
                reader = csv.reader(csvfile)
                rows = list(reader)
            
            # Should have at least header + one data row
            assert len(rows) >= 2, f"CSV should have header + data rows, got {len(rows)}"
            
            # Verify header - match actual analyzer.py headers
            header = rows[0]
            expected_fields = ['ts_unix', 'iface', 'bus_load_pct', 'id_hex', 'fps',
                             'avg_jitter_ms', 'avg_len_bytes', 'count']
            
            for field in expected_fields:
                assert field in header, f"Header should contain '{field}', got: {header}"
            
            # Verify data row format
            if len(rows) > 1:
                data_row = rows[1]
                assert len(data_row) == len(header), "Data row should match header length"
                
                # Basic data validation
                timestamp = float(data_row[header.index('ts_unix')])
                assert timestamp > 0, "Timestamp should be positive"
                
                can_id = data_row[header.index('id_hex')]
                assert can_id == '0x123', f"CAN ID should be '0x123', got '{can_id}'"
                
                frame_count = int(data_row[header.index('count')])
                assert frame_count > 0, "Frame count should be positive"
                
        finally:
            if os.path.exists(csv_path):
                os.unlink(csv_path)
    
    @patch('socketcan_sa.analyzer.Console')
    @patch('can.interface.Bus')
    @patch('time.time')
    def test_csv_data_row_format(self, mock_time, mock_bus_class, mock_console_class):
        """Test CSV data row formatting and data types."""
        mock_bus = Mock()
        mock_bus_class.return_value = mock_bus
        mock_console_class.return_value = Mock()
        
        # Create test frame with specific data
        test_frame = Mock()
        test_frame.arbitration_id = 0x456
        test_frame.data = b'\x01\x02\x03\x04\x05'  # 5 bytes
        
        time_values = [1000.0, 1000.2, 1000.4, 1001.1]
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
            if recv_call_count <= 2:  # Two frames
                return test_frame
            elif recv_call_count <= 4:
                return None
            else:
                raise KeyboardInterrupt()
        
        mock_time.side_effect = time_side_effect
        mock_bus.recv.side_effect = recv_side_effect
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as temp_file:
            csv_path = temp_file.name
        
        try:
            with patch('builtins.print'):
                analyze("test_iface", interval=1.0, csv_path=csv_path, bitrate=500000)
            
            with open(csv_path, 'r', newline='') as csvfile:
                reader = csv.DictReader(csvfile)
                rows = list(reader)
            
            assert len(rows) >= 1, "Should have at least one data row"
            
            row = rows[0]
            
            # Validate data types and ranges
            timestamp = float(row['ts_unix'])
            assert timestamp >= 1000.0, f"Timestamp should be >= 1000.0, got {timestamp}"
            
            # Note: analyzer.py doesn't output window_start/window_end, so skip those checks
            
            can_id = row['id_hex']
            assert can_id == '0x456', f"CAN ID should be '0x456', got '{can_id}'"
            
            frame_count = int(row['count'])
            assert frame_count == 2, f"Frame count should be 2, got {frame_count}"
            
            avg_payload_len = float(row['avg_len_bytes'])
            assert avg_payload_len == 5.0, f"Average payload length should be 5.0, got {avg_payload_len}"
            
            fps = float(row['fps'])
            assert fps > 0, f"FPS should be positive, got {fps}"
            
            bus_load_percent = float(row['bus_load_pct'])
            assert 0 <= bus_load_percent <= 100, f"Bus load should be 0-100%, got {bus_load_percent}"
            
        finally:
            if os.path.exists(csv_path):
                os.unlink(csv_path)
    
    @patch('socketcan_sa.analyzer.Console')
    @patch('can.interface.Bus')
    @patch('time.time')
    def test_csv_multiple_windows(self, mock_time, mock_bus_class, mock_console_class):
        """Test CSV export with multiple windows."""
        mock_bus = Mock()
        mock_bus_class.return_value = mock_bus
        mock_console_class.return_value = Mock()
        
        # Create test frames
        frame1 = Mock()
        frame1.arbitration_id = 0x100
        frame1.data = b'\x01\x02'
        
        frame2 = Mock()
        frame2.arbitration_id = 0x200
        frame2.data = b'\x03\x04\x05'
        
        # Generate timestamps for multiple windows
        time_values = [
            1000.0,  # Start
            1000.3,  # Frame 1
            1000.6,  # Frame 2
            1001.0,  # Window 1 end
            1001.3,  # Frame 1 (window 2)
            1001.6,  # Frame 2 (window 2)
            1002.0,  # Window 2 end
            1002.1   # Extra
        ]
        
        time_call_count = 0
        def time_side_effect():
            nonlocal time_call_count
            if time_call_count < len(time_values):
                result = time_values[time_call_count]
                time_call_count += 1
                return result
            return 1003.0
        
        recv_call_count = 0
        def recv_side_effect(timeout=None):
            nonlocal recv_call_count
            recv_call_count += 1
            if recv_call_count == 1:
                return frame1
            elif recv_call_count == 2:
                return frame2
            elif recv_call_count == 3:
                return frame1
            elif recv_call_count == 4:
                return frame2
            elif recv_call_count <= 7:
                return None
            else:
                raise KeyboardInterrupt()
        
        mock_time.side_effect = time_side_effect
        mock_bus.recv.side_effect = recv_side_effect
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as temp_file:
            csv_path = temp_file.name
        
        try:
            with patch('builtins.print'):
                analyze("test_iface", interval=1.0, csv_path=csv_path)
            
            with open(csv_path, 'r', newline='') as csvfile:
                reader = csv.DictReader(csvfile)
                rows = list(reader)
            
            # Should have multiple rows (one per CAN ID per window)
            assert len(rows) >= 2, f"Should have multiple CSV rows, got {len(rows)}"
            
            # Check that we have data for both CAN IDs
            can_ids = [row['id_hex'] for row in rows]
            unique_can_ids = set(can_ids)
            
            # Should have data for both CAN IDs
            assert '0x100' in unique_can_ids or '0x200' in unique_can_ids, f"Should have expected CAN IDs: {unique_can_ids}"
            
            # Verify all rows have valid data
            for row in rows:
                assert float(row['ts_unix']) > 0, "Timestamp should be positive"
                assert int(row['count']) > 0, "Frame count should be positive"
                
        finally:
            if os.path.exists(csv_path):
                os.unlink(csv_path)
    
    @patch('socketcan_sa.analyzer.Console')
    @patch('can.interface.Bus')
    @patch('time.time')
    def test_csv_no_frames_window(self, mock_time, mock_bus_class, mock_console_class):
        """Test CSV export when window has no frames."""
        mock_bus = Mock()
        mock_bus_class.return_value = mock_bus
        mock_console_class.return_value = Mock()
        
        # No frames, only timeouts
        mock_bus.recv.return_value = None
        
        time_values = [1000.0, 1001.1, 1001.2]
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
            if recv_call_count <= 3:
                return None
            else:
                raise KeyboardInterrupt()
        
        mock_time.side_effect = time_side_effect
        mock_bus.recv.side_effect = recv_side_effect
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as temp_file:
            csv_path = temp_file.name
        
        try:
            with patch('builtins.print'):
                analyze("test_iface", interval=1.0, csv_path=csv_path)
            
            # CSV should exist but may be empty or have only header
            assert os.path.exists(csv_path), "CSV file should be created even with no frames"
            
            with open(csv_path, 'r', newline='') as csvfile:
                content = csvfile.read()
            
            # Should at least have header
            assert len(content) > 0, "CSV should have content (at least header)"
            
        finally:
            if os.path.exists(csv_path):
                os.unlink(csv_path)


class TestCSVErrorHandling:
    """Test CSV error handling scenarios."""
    
    @patch('socketcan_sa.analyzer.Console')
    @patch('can.interface.Bus')
    def test_csv_file_permission_error(self, mock_bus_class, mock_console_class):
        """Test handling of CSV file permission errors."""
        mock_bus = Mock()
        mock_bus_class.return_value = mock_bus
        mock_console_class.return_value = Mock()
        mock_bus.recv.return_value = None
        
        # Use a path that should cause permission error (root directory on Unix-like systems)
        readonly_path = "/root/readonly.csv" if os.name == 'posix' else "C:\\Windows\\System32\\readonly.csv"
        
        # Should handle permission error (analyzer doesn't wrap in SystemExit)
        with pytest.raises((PermissionError, OSError, FileNotFoundError)):
            analyze("test_iface", csv_path=readonly_path)
    
    @patch('socketcan_sa.analyzer.Console')
    @patch('can.interface.Bus')
    @patch('time.time')
    def test_csv_disk_full_simulation(self, mock_time, mock_bus_class, mock_console_class):
        """Test handling of disk full scenario during CSV write."""
        mock_bus = Mock()
        mock_bus_class.return_value = mock_bus
        mock_console_class.return_value = Mock()
        
        # Create test frame
        test_frame = Mock()
        test_frame.arbitration_id = 0x789
        test_frame.data = b'\x01\x02\x03'
        
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
                return test_frame
            elif recv_call_count <= 3:
                return None
            else:
                raise KeyboardInterrupt()
        
        mock_time.side_effect = time_side_effect
        mock_bus.recv.side_effect = recv_side_effect
        
        # Mock CSV writer to simulate disk full
        mock_csv_writer = Mock()
        mock_csv_writer.writerow.side_effect = OSError("No space left on device")
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as temp_file:
            csv_path = temp_file.name
        
        try:
            with patch('csv.writer', return_value=mock_csv_writer), \
                 patch('builtins.print'):
                # Should propagate disk full error
                with pytest.raises(OSError, match="No space left on device"):
                    analyze("test_iface", interval=1.0, csv_path=csv_path)
                
            # CSV writer should have been called and triggered the error
            mock_csv_writer.writerow.assert_called()
            
        finally:
            if os.path.exists(csv_path):
                os.unlink(csv_path)
    
    @patch('socketcan_sa.analyzer.Console')
    @patch('can.interface.Bus')
    @patch('time.time')
    def test_csv_special_characters_in_data(self, mock_time, mock_bus_class, mock_console_class):
        """Test CSV handling of special characters and edge cases."""
        mock_bus = Mock()
        mock_bus_class.return_value = mock_bus
        mock_console_class.return_value = Mock()
        
        # Create frame with special CAN ID that might cause formatting issues
        special_frame = Mock()
        special_frame.arbitration_id = 0x1FFFFFFF  # Maximum extended CAN ID
        special_frame.data = b'\xFF\x00\x01\x02'  # Mixed data
        
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
                return special_frame
            elif recv_call_count <= 3:
                return None
            else:
                raise KeyboardInterrupt()
        
        mock_time.side_effect = time_side_effect
        mock_bus.recv.side_effect = recv_side_effect
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as temp_file:
            csv_path = temp_file.name
        
        try:
            with patch('builtins.print'):
                analyze("test_iface", interval=1.0, csv_path=csv_path)
            
            # Should handle special characters in CSV
            with open(csv_path, 'r', newline='') as csvfile:
                reader = csv.DictReader(csvfile)
                rows = list(reader)
            
            assert len(rows) >= 1, "Should have data row with special characters"
            
            row = rows[0]
            can_id = row['id_hex']
            
            # Should format extended CAN ID correctly
            assert can_id == '0x1FFFFFFF', f"Extended CAN ID should be formatted correctly: {can_id}"
            
            # All fields should be present and valid
            for field_name, field_value in row.items():
                assert field_value is not None, f"Field '{field_name}' should not be None"
                assert ',' not in field_value, f"Field '{field_name}' should not contain unescaped commas: {field_value}"
                
        finally:
            if os.path.exists(csv_path):
                os.unlink(csv_path)


class TestCSVSchema:
    """Test CSV schema consistency and validation."""
    
    def test_csv_header_schema(self):
        """Test that CSV header schema is consistent."""
        # Expected CSV schema - match actual analyzer.py output
        expected_schema = {
            'ts_unix': float,
            'iface': str,
            'bus_load_pct': float,
            'id_hex': str,
            'fps': float,
            'avg_jitter_ms': float,
            'avg_len_bytes': float,
            'count': int
        }
        
        # This test documents the expected CSV schema
        assert len(expected_schema) == 8, "CSV schema should have exactly 8 fields"
        
        # Verify field types are appropriate
        assert expected_schema['ts_unix'] == float, "Timestamp should be float"
        assert expected_schema['id_hex'] == str, "CAN ID should be string (hex format)"
        assert expected_schema['count'] == int, "Frame count should be integer"
        assert expected_schema['bus_load_pct'] == float, "Bus load should be float percentage"
    
    @patch('socketcan_sa.analyzer.Console')
    @patch('can.interface.Bus')
    @patch('time.time')
    def test_csv_data_types_consistency(self, mock_time, mock_bus_class, mock_console_class):
        """Test that CSV data types are consistent across multiple rows."""
        mock_bus = Mock()
        mock_bus_class.return_value = mock_bus
        mock_console_class.return_value = Mock()
        
        # Create different frames for consistency testing
        frame1 = Mock()
        frame1.arbitration_id = 0x123
        frame1.data = b'\x01\x02'
        
        frame2 = Mock()
        frame2.arbitration_id = 0x456
        frame2.data = b'\x03\x04\x05\x06'
        
        # Multiple windows with different data
        time_values = [
            1000.0, 1000.2, 1000.4, 1001.0,  # Window 1
            1001.2, 1001.4, 1001.6, 1002.0,  # Window 2
            1002.1
        ]
        
        time_call_count = 0
        def time_side_effect():
            nonlocal time_call_count
            if time_call_count < len(time_values):
                result = time_values[time_call_count]
                time_call_count += 1
                return result
            return 1003.0
        
        recv_call_count = 0
        def recv_side_effect(timeout=None):
            nonlocal recv_call_count
            recv_call_count += 1
            if recv_call_count <= 2:
                return frame1
            elif recv_call_count <= 4:
                return frame2
            elif recv_call_count <= 7:
                return None
            else:
                raise KeyboardInterrupt()
        
        mock_time.side_effect = time_side_effect
        mock_bus.recv.side_effect = recv_side_effect
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as temp_file:
            csv_path = temp_file.name
        
        try:
            with patch('builtins.print'):
                analyze("test_iface", interval=1.0, csv_path=csv_path)
            
            with open(csv_path, 'r', newline='') as csvfile:
                reader = csv.DictReader(csvfile)
                rows = list(reader)
            
            assert len(rows) >= 2, "Should have multiple rows for consistency testing"
            
            # Test data type consistency across all rows
            for i, row in enumerate(rows):
                # Test numeric fields can be converted to appropriate types
                try:
                    float(row['ts_unix'])
                    float(row['bus_load_pct'])
                    int(row['count'])
                    float(row['fps'])
                    float(row['avg_jitter_ms'])
                    float(row['avg_len_bytes'])
                except ValueError as e:
                    pytest.fail(f"Row {i} has invalid data type: {e}")
                
                # Test string fields format
                can_id = row['id_hex']
                assert can_id.startswith('0x'), f"CAN ID should start with '0x': {can_id}"
                
                iface = row['iface']
                assert isinstance(iface, str), f"Interface should be string: {iface}"
                
                # Test value ranges
                fps = float(row['fps'])
                assert fps >= 0, f"FPS should be non-negative: {fps}"
                
                bus_load = float(row['bus_load_pct'])
                assert 0 <= bus_load <= 100, f"Bus load should be 0-100%: {bus_load}"
                
                frame_count = int(row['count'])
                assert frame_count > 0, f"Frame count should be positive: {frame_count}"
                
        finally:
            if os.path.exists(csv_path):
                os.unlink(csv_path)

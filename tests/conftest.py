import pytest
import logging
from pathlib import Path


def pytest_configure(config):
    """Configure pytest with custom markers."""
    config.addinivalue_line("markers", "integration: mark test as integration test")
    config.addinivalue_line("markers", "performance: mark test as performance test")


@pytest.fixture(autouse=True)
def setup_logging():
    """Setup logging for tests."""
    logging.basicConfig(level=logging.DEBUG)


@pytest.fixture
def sample_can_frames():
    """Provide sample CAN frames for testing."""
    return [
        {"id": 0x100, "data": b'\x01\x02\x03', "ts": 1234567890.0},
        {"id": 0x200, "data": b'\x04\x05\x06\x07', "ts": 1234567890.1},
        {"id": 0x7FF, "data": b'\x08', "ts": 1234567890.2},
    ]


@pytest.fixture
def mock_can_message():
    """Create a mock CAN message for analyzer testing."""
    from unittest.mock import Mock
    
    def _create_message(arbitration_id, data, timestamp=None):
        msg = Mock()
        msg.arbitration_id = arbitration_id
        msg.data = data
        msg.is_extended_id = arbitration_id > 0x7FF
        msg.timestamp = timestamp or 1234567890.0
        return msg
    
    return _create_message


@pytest.fixture  
def analyzer_test_data():
    """Provide comprehensive test data for analyzer tests."""
    return {
        # Various payload sizes for bit calculation testing
        "payload_sizes": [0, 1, 2, 4, 8],
        
        # Common CAN IDs for testing
        "standard_ids": [0x100, 0x200, 0x300, 0x7FF],
        "extended_ids": [0x800, 0x18FF1234, 0x1FFFFFFF],
        
        # Test data patterns
        "data_patterns": [
            b'',                      # Empty
            b'\x00',                  # Single zero
            b'\xFF',                  # Single 0xFF  
            b'\x01\x02\x03\x04',      # Sequential
            b'\xAA\x55\xAA\x55\xAA\x55\xAA\x55',  # Alternating pattern
        ],
        
        # Timing patterns for jitter testing
        "timing_patterns": {
            "regular_10ms": [1000.0, 1000.01, 1000.02, 1000.03, 1000.04],
            "irregular": [1000.0, 1000.005, 1000.025, 1000.035, 1000.055],
            "burst": [1000.0, 1000.001, 1000.002, 1000.003, 1001.0],
        },
        
        # Expected frame bit calculations
        "expected_frame_bits": {
            0: 47,   # 47 + 0*8 = 47
            1: 55,   # 47 + 1*8 = 55  
            4: 79,   # 47 + 4*8 = 79
            8: 111,  # 47 + 8*8 = 111
        },
        
        # Bus load test scenarios
        "bus_load_scenarios": [
            {
                "bitrate": 500_000,
                "frame_bits": 79,  # 4-byte payload
                "interval_ms": 100,  # 100ms = 10 Hz
                "expected_load_pct": (79 * 10) / 500_000 * 100  # ~0.16%
            },
            {
                "bitrate": 100_000, 
                "frame_bits": 111,  # 8-byte payload
                "interval_ms": 10,   # 10ms = 100 Hz  
                "expected_load_pct": (111 * 100) / 100_000 * 100  # ~11.1%
            }
        ]
    }


@pytest.fixture
def analyzer_mock_strategy():
    """Provide mock strategies for analyzer testing."""
    from unittest.mock import Mock, patch
    
    class AnalyzerMockStrategy:
        def __init__(self):
            self.call_counts = {}
        
        def create_recv_sequence(self, frames, timeouts=3, exit_after=True):
            """
            Create a recv side_effect that returns frames then exits cleanly.
            
            Args:
                frames: List of mock CAN messages to return
                timeouts: Number of None returns (timeouts) after frames
                exit_after: Whether to raise KeyboardInterrupt to exit
            """
            def recv_side_effect(timeout=None):
                if not hasattr(recv_side_effect, 'call_count'):
                    recv_side_effect.call_count = 0
                recv_side_effect.call_count += 1
                
                if recv_side_effect.call_count <= len(frames):
                    return frames[recv_side_effect.call_count - 1]
                elif recv_side_effect.call_count <= len(frames) + timeouts:
                    return None  # Timeout
                elif exit_after:
                    raise KeyboardInterrupt()  # Clean exit
                else:
                    return None
            
            return recv_side_effect
        
        def create_time_sequence(self, times, increment=0.01):
            """
            Create a time side_effect that returns specified times then increments.
            
            Args:
                times: List of specific timestamps to return first
                increment: Amount to increment for subsequent calls
            """
            def time_side_effect():
                if not hasattr(time_side_effect, 'call_count'):
                    time_side_effect.call_count = 0
                time_side_effect.call_count += 1
                
                if time_side_effect.call_count <= len(times):
                    return times[time_side_effect.call_count - 1]
                else:
                    # Continue incrementing after specified times
                    return times[-1] + (time_side_effect.call_count - len(times)) * increment
            
            return time_side_effect
        
        def patch_analyzer_dependencies(self):
            """Return context manager that patches all analyzer dependencies."""
            return patch.multiple(
                'socketcan_sa.analyzer',
                Console=Mock(),
                can=Mock()
            )
    
    return AnalyzerMockStrategy()


@pytest.fixture
def csv_validator():
    """Provide CSV validation utilities for testing."""
    import csv
    import io
    
    class CSVValidator:
        @staticmethod
        def validate_header(csv_content, expected_headers):
            """Validate CSV header matches expected format."""
            reader = csv.DictReader(io.StringIO(csv_content))
            return reader.fieldnames == expected_headers
        
        @staticmethod
        def validate_data_types(csv_content):
            """Validate CSV data types are correct."""
            reader = csv.DictReader(io.StringIO(csv_content))
            rows = list(reader)
            
            for row in rows:
                try:
                    # Validate numeric fields
                    float(row['bus_load_pct'])
                    float(row['fps'])
                    float(row['avg_jitter_ms'])
                    float(row['avg_len_bytes'])
                    int(row['count'])
                    int(row['ts_unix'])
                    
                    # Validate ranges
                    assert 0 <= float(row['bus_load_pct']) <= 100
                    assert float(row['fps']) >= 0
                    assert float(row['avg_jitter_ms']) >= 0
                    assert 0 <= float(row['avg_len_bytes']) <= 8
                    assert int(row['count']) > 0
                    
                    # Validate hex ID format
                    assert row['id_hex'].startswith('0x')
                    int(row['id_hex'], 16)  # Should parse as hex
                
                except (ValueError, AssertionError) as e:
                    return False, f"Invalid data in row {row}: {e}"
            
            return True, "All data valid"
        
        @staticmethod
        def get_statistics(csv_content):
            """Extract statistics from CSV content."""
            reader = csv.DictReader(io.StringIO(csv_content))
            rows = list(reader)
            
            if not rows:
                return {}
            
            can_ids = {row['id_hex'] for row in rows}
            interfaces = {row['iface'] for row in rows}
            
            bus_loads = [float(row['bus_load_pct']) for row in rows]
            fps_values = [float(row['fps']) for row in rows]
            
            return {
                'row_count': len(rows),
                'unique_can_ids': len(can_ids),
                'unique_interfaces': len(interfaces),
                'avg_bus_load': sum(bus_loads) / len(bus_loads),
                'max_fps': max(fps_values),
                'min_fps': min(fps_values),
                'can_ids': sorted(can_ids),
                'interfaces': sorted(interfaces)
            }
    
    return CSVValidator()


@pytest.fixture
def analyzer_can_frames():
    """Provide CAN frames specifically for analyzer testing."""
    return [
        # Standard frames with various payload sizes
        {"arbitration_id": 0x100, "data": b'', "extended": False},           # Empty payload
        {"arbitration_id": 0x101, "data": b'\x01', "extended": False},       # 1 byte
        {"arbitration_id": 0x102, "data": b'\x01\x02\x03\x04', "extended": False},  # 4 bytes
        {"arbitration_id": 0x103, "data": b'\x01\x02\x03\x04\x05\x06\x07\x08', "extended": False},  # 8 bytes (max)
        
        # Extended ID frames
        {"arbitration_id": 0x12345678, "data": b'\xAA\xBB', "extended": True},
        {"arbitration_id": 0x1FFFFFFF, "data": b'\xFF', "extended": True},   # Max extended ID
        
        # Edge cases
        {"arbitration_id": 0x000, "data": b'\x00', "extended": False},       # Min standard ID
        {"arbitration_id": 0x7FF, "data": b'\xFF', "extended": False},       # Max standard ID
    ]


@pytest.fixture 
def mock_can_frame():
    """Factory for creating mock CAN frames."""
    def _create_frame(arbitration_id=0x123, data=b'\x01\x02', extended=False):
        from unittest.mock import Mock
        frame = Mock()
        frame.arbitration_id = arbitration_id
        frame.data = data
        frame.is_extended_id = extended
        return frame
    return _create_frame


@pytest.fixture
def analyzer_test_data():
    """Comprehensive test data for analyzer stress testing."""
    return {
        # High-frequency test data
        "high_frequency": [
            {"arbitration_id": 0x100 + i, "data": bytes([i % 256] * (i % 8 + 1))} 
            for i in range(1000)
        ],
        
        # Multi-ID diversity data  
        "diverse_ids": [
            {"arbitration_id": i, "data": b'\x01\x02\x03\x04'}
            for i in range(500)
        ],
        
        # Payload variation data
        "payload_variations": [
            {"arbitration_id": 0x200, "data": b'' if i % 2 == 0 else b'\x01\x02\x03\x04\x05\x06\x07\x08'}
            for i in range(100)
        ],
        
        # Timing test data (for jitter testing)
        "timing_patterns": {
            "regular": [0.01 * i for i in range(50)],           # 10ms intervals
            "bursty": [0.1 * (i // 10) + 0.001 * (i % 10) for i in range(50)],  # Bursts every 100ms
            "random": [0.001, 0.05, 0.002, 0.1, 0.003, 0.02, 0.001, 0.08],     # Irregular
        }
    }
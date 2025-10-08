"""Sample CAN frames for testing."""

SAMPLE_FRAMES = [
    # Standard frames
    {"id": 0x123, "data": b'\x01\x02\x03\x04', "ts": 1640995200.0, "extended": False},
    {"id": 0x456, "data": b'\x05\x06', "ts": 1640995200.1, "extended": False},
    
    # Extended frames  
    {"id": 0x18FF1234, "data": b'\x07\x08\x09\x0A\x0B', "ts": 1640995200.2, "extended": True},
    
    # Edge cases
    {"id": 0x000, "data": b'', "ts": 1640995200.3, "extended": False},  # Empty data
    {"id": 0x7FF, "data": b'\xFF' * 8, "ts": 1640995200.4, "extended": False},  # Max DLC
]


# Analyzer-specific test data
ANALYZER_TEST_FRAMES = [
    # High-frequency sequence for jitter testing (10ms intervals)
    {"id": 0x100, "data": b'\x01', "ts": 1000.000, "extended": False},
    {"id": 0x100, "data": b'\x02', "ts": 1000.010, "extended": False},
    {"id": 0x100, "data": b'\x03', "ts": 1000.020, "extended": False},
    {"id": 0x100, "data": b'\x04', "ts": 1000.030, "extended": False},
    
    # Multiple CAN IDs for statistics testing
    {"id": 0x200, "data": b'\x11\x22', "ts": 1000.005, "extended": False},
    {"id": 0x300, "data": b'\x33\x44\x55', "ts": 1000.015, "extended": False},
    {"id": 0x200, "data": b'\x66\x77', "ts": 1000.025, "extended": False},
    
    # Variable payload sizes for bit calculation testing
    {"id": 0x400, "data": b'', "ts": 1000.050, "extended": False},          # 0 bytes
    {"id": 0x401, "data": b'\x01', "ts": 1000.051, "extended": False},      # 1 byte
    {"id": 0x402, "data": b'\x01\x02', "ts": 1000.052, "extended": False},  # 2 bytes
    {"id": 0x404, "data": b'\x01\x02\x03\x04', "ts": 1000.054, "extended": False},  # 4 bytes
    {"id": 0x408, "data": b'\x01\x02\x03\x04\x05\x06\x07\x08', "ts": 1000.058, "extended": False},  # 8 bytes
    
    # Extended ID frames
    {"id": 0x18DA10F1, "data": b'\x01\x02\x03', "ts": 1000.100, "extended": True},
    {"id": 0x1FFFFFFF, "data": b'\xFF\x00\xAA\x55', "ts": 1000.101, "extended": True},
]


# Bus load test scenarios
BUS_LOAD_TEST_SCENARIOS = [
    {
        "name": "low_load_scenario",
        "bitrate": 500_000,
        "frames": [
            {"id": 0x123, "data": b'\x01\x02\x03\x04', "interval_ms": 100},  # 10 Hz, 79 bits
        ],
        "expected_load_pct": 0.16,  # (79 * 10) / 500_000 * 100
    },
    {
        "name": "medium_load_scenario", 
        "bitrate": 250_000,
        "frames": [
            {"id": 0x100, "data": b'\x01\x02', "interval_ms": 20},           # 50 Hz, 63 bits
            {"id": 0x200, "data": b'\x03\x04\x05\x06', "interval_ms": 50},   # 20 Hz, 79 bits  
        ],
        "expected_load_pct": 1.89,  # ((63 * 50) + (79 * 20)) / 250_000 * 100
    },
    {
        "name": "high_load_scenario",
        "bitrate": 125_000,
        "frames": [
            {"id": 0x100, "data": b'\x01\x02\x03\x04\x05\x06\x07\x08', "interval_ms": 10},  # 100 Hz, 111 bits
            {"id": 0x200, "data": b'\x11\x22\x33\x44', "interval_ms": 20},                  # 50 Hz, 79 bits
            {"id": 0x300, "data": b'\xAA\xBB', "interval_ms": 25},                          # 40 Hz, 63 bits
        ],
        "expected_load_pct": 21.02,  # ((111*100) + (79*50) + (63*40)) / 125_000 * 100
    }
]


# CSV export test data
CSV_TEST_DATA = {
    "headers": ["ts_unix", "iface", "bus_load_pct", "id_hex", "fps", "avg_jitter_ms", "avg_len_bytes", "count"],
    "sample_rows": [
        ["1640995200", "vcan0", "1.5", "0x123", "10.25", "98.5", "4.0", "15"],
        ["1640995201", "vcan0", "2.1", "0x456", "5.50", "185.2", "2.5", "8"],
        ["1640995202", "vcan0", "0.8", "0x18FF1234", "2.75", "350.0", "6.0", "3"],
    ],
    "expected_statistics": {
        "total_rows": 3,
        "unique_ids": {"0x123", "0x456", "0x18FF1234"},
        "avg_bus_load": 1.47,  # (1.5 + 2.1 + 0.8) / 3
        "total_frames": 26,    # 15 + 8 + 3
    }
}


# Jitter calculation test patterns
JITTER_TEST_PATTERNS = {
    "regular_timing": {
        "frames": [
            {"id": 0x100, "ts": 1000.000},
            {"id": 0x100, "ts": 1000.100},  # 100ms gap
            {"id": 0x100, "ts": 1000.200},  # 100ms gap
            {"id": 0x100, "ts": 1000.300},  # 100ms gap
        ],
        "expected_jitter_ms": 100.0,
        "tolerance_ms": 1.0,
    },
    "irregular_timing": {
        "frames": [
            {"id": 0x200, "ts": 1000.000},
            {"id": 0x200, "ts": 1000.050},  # 50ms gap
            {"id": 0x200, "ts": 1000.150},  # 100ms gap  
            {"id": 0x200, "ts": 1000.200},  # 50ms gap
        ],
        "expected_jitter_ms": 66.67,  # (50 + 100 + 50) / 3
        "tolerance_ms": 5.0,
    },
    "burst_timing": {
        "frames": [
            {"id": 0x300, "ts": 1000.000},
            {"id": 0x300, "ts": 1000.001},  # 1ms gap
            {"id": 0x300, "ts": 1000.002},  # 1ms gap
            {"id": 0x300, "ts": 1001.000},  # 998ms gap
        ],
        "expected_jitter_ms": 333.33,  # (1 + 1 + 998) / 3  
        "tolerance_ms": 10.0,
    }
}


# Performance test data patterns
PERFORMANCE_TEST_PATTERNS = {
    "high_frequency": {
        "frame_count": 1000,
        "duration_sec": 10.0,
        "target_fps": 100.0,
        "can_ids": [0x100, 0x200, 0x300],
        "payload_sizes": [4, 8, 2],
    },
    "many_ids": {
        "frame_count": 500,
        "unique_ids": 50,
        "duration_sec": 5.0,
        "id_range": (0x100, 0x131),  # 50 IDs: 0x100-0x131
    },
    "large_dataset": {
        "frame_count": 5000,
        "duration_sec": 30.0,
        "csv_size_mb_min": 0.1,
        "unique_ids": 10,
    }
}
#!/usr/bin/env python3
"""
Performance tests for rules.py

Tests performance characteristics including:
- Large configuration file parsing
- Memory usage monitoring  
- CAN ID parsing speed
- Complex validation performance
"""

import pytest
import time
import tempfile
import os
import textwrap
try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False
from socketcan_sa.rules import load_rules, _parse_can_id, MAX_CAN_ID


def _write_tmp(yaml_text: str) -> str:
    """Helper to write temporary YAML file."""
    fd, path = tempfile.mkstemp(suffix=".yaml")
    os.close(fd)
    with open(path, "w", encoding="utf-8") as f:
        f.write(textwrap.dedent(yaml_text))
    return path


@pytest.mark.timeout(60)  # Prevent hanging
class TestRulesPerformance:
    """Performance benchmark tests for rules functionality."""

    def test_large_configuration_parsing_performance(self):
        """Test parsing performance with large configuration files."""
        # Generate large configuration (5000 limits + 1000 drops + 500 remaps)
        yaml_lines = ["# Large CAN configuration for performance testing"]
        
        # Limits section (5000 entries)
        yaml_lines.append("limits:")
        for i in range(5000):
            can_id = 0x1000 + i
            rate = 10 + (i % 1000)
            burst = max(1, rate // 5)
            yaml_lines.append(f'  "0x{can_id:X}": {{ rate: {rate}, burst: {burst} }}')
        
        # Actions section
        yaml_lines.append("actions:")
        yaml_lines.append("  drop:")
        
        # Drop list (1000 entries)
        for i in range(1000):
            can_id = 0x10000 + i
            yaml_lines.append(f'    - "0x{can_id:X}"')
        
        # Remap list (500 entries)
        yaml_lines.append("  remap:")
        for i in range(500):
            from_id = 0x20000 + i
            to_id = 0x30000 + i
            yaml_lines.append(f'    - {{ from: "0x{from_id:X}", to: "0x{to_id:X}" }}')
        
        path = _write_tmp("\n".join(yaml_lines))
        
        try:
            # Measure parsing time
            start_time = time.perf_counter()
            if PSUTIL_AVAILABLE:
                process = psutil.Process()
                start_memory = process.memory_info().rss / 1024 / 1024  # MB
            
            rules = load_rules(path)
            
            end_time = time.perf_counter()
            parsing_time = end_time - start_time
            
            if PSUTIL_AVAILABLE:
                end_memory = process.memory_info().rss / 1024 / 1024  # MB
                memory_usage = end_memory - start_memory
            else:
                memory_usage = 0
            
            # Performance assertions
            assert parsing_time < 10.0, f"Large config parsing too slow: {parsing_time:.2f}s"
            if PSUTIL_AVAILABLE:
                assert memory_usage < 100, f"Memory usage too high: {memory_usage:.1f}MB"
            
            # Verify correct parsing
            assert len(rules["limits"]) == 5000
            assert len(rules["drop"]) == 1000
            assert len(rules["remap"]) == 500
            
            print(f"Performance: {parsing_time:.3f}s, {memory_usage:.1f}MB for 6500 entries")
            
        finally:
            os.unlink(path)

    def test_can_id_parsing_performance(self):
        """Test CAN ID parsing performance across different formats."""
        test_cases = [
            # (input, format_type)
            (0x123456, "int"),
            ("0x123456", "hex_string"),
            ("1193046", "dec_string"),
            ("0X123456", "hex_upper"),
        ]
        
        iterations = 10000
        
        for input_val, format_type in test_cases:
            start_time = time.perf_counter()
            
            # Parse many times
            for _ in range(iterations):
                result = _parse_can_id(input_val, field="perf_test")
                assert result == 0x123456  # Verify correctness
            
            end_time = time.perf_counter()
            total_time = end_time - start_time
            per_parse = total_time / iterations * 1000  # ms per parse
            
            # Should parse very quickly
            assert total_time < 5.0, f"{format_type} parsing too slow: {total_time:.3f}s total"
            assert per_parse < 0.1, f"{format_type} per-parse too slow: {per_parse:.4f}ms"
            
            print(f"CAN ID parsing ({format_type}): {per_parse:.4f}ms per parse")

    def test_validation_performance_complex_config(self):
        """Test validation performance with complex interconnected rules."""
        # Create config with overlapping IDs between sections
        yaml_lines = ["# Complex validation test configuration"]
        
        # Limits with many unique IDs (no overlaps for remap validation)
        yaml_lines.append("limits:")
        base_ids = []
        for i in range(1000):  # Reduced to avoid ID space exhaustion
            can_id = 0x100 + i  # Sequential IDs, no overlaps
            base_ids.append(can_id)
            rate = 10 + (i % 100)
            yaml_lines.append(f'  "0x{can_id:X}": {{ rate: {rate} }}')
        
        # Drop list with some overlapping IDs from limits
        yaml_lines.extend([
            "actions:",
            "  drop:"
        ])
        for i in range(0, len(base_ids), 3):  # Every 3rd ID
            yaml_lines.append(f'    - "0x{base_ids[i]:X}"')
        
        # Remap with complex relationships  
        yaml_lines.append("  remap:")
        for i in range(0, min(500, len(base_ids) // 4)):
            from_id = base_ids[i * 4]
            to_id = base_ids[i * 4 + 1] + 0x10000  # Ensure no collision
            yaml_lines.append(f'    - {{ from: "0x{from_id:X}", to: "0x{to_id:X}" }}')
        
        path = _write_tmp("\n".join(yaml_lines))
        
        try:
            start_time = time.perf_counter()
            rules = load_rules(path)
            end_time = time.perf_counter()
            
            validation_time = end_time - start_time
            
            # Should handle complex validation efficiently
            assert validation_time < 15.0, f"Complex validation too slow: {validation_time:.2f}s"
            
            # Verify some overlaps were handled correctly
            assert len(rules["limits"]) <= 1000  # Deduplicated by CAN ID
            assert len(rules["drop"]) > 0
            assert len(rules["remap"]) > 0
            
            print(f"Complex validation: {validation_time:.3f}s")
            
        finally:
            os.unlink(path)

    def test_memory_efficiency_repeated_parsing(self):
        """Test memory efficiency with repeated parsing operations."""
        if not PSUTIL_AVAILABLE:
            pytest.skip("psutil not available for memory monitoring")
        
        # Create moderate-sized config with proper YAML formatting
        yaml_lines = ["limits:"]
        for i in range(1000):
            yaml_lines.append(f'  "0x{0x100 + i:X}": {{ rate: {10 + i}, burst: {max(1, (10 + i) // 5)} }}')
        
        yaml_lines.append("actions:")
        yaml_lines.append("  drop:")
        for i in range(200):
            yaml_lines.append(f'    - "0x{0x2000 + i:X}"')
        
        yaml_lines.append("  remap:")
        for i in range(100):
            yaml_lines.append(f'    - {{ from: "0x{0x3000 + i:X}", to: "0x{0x4000 + i:X}" }}')
        
        yaml_content = "\n".join(yaml_lines)
        
        path = _write_tmp(yaml_content)
        
        try:
            process = psutil.Process()
            initial_memory = process.memory_info().rss / 1024 / 1024  # MB
            
            # Parse same file multiple times
            for i in range(20):
                rules = load_rules(path)
                
                # Verify parsing correctness 
                assert len(rules["limits"]) == 1000
                assert len(rules["drop"]) == 200
                assert len(rules["remap"]) == 100
                
                # Check memory growth every few iterations
                if i % 5 == 0:
                    current_memory = process.memory_info().rss / 1024 / 1024
                    memory_growth = current_memory - initial_memory
                    
                    # Memory growth should be reasonable
                    assert memory_growth < 50, f"Memory leak detected: {memory_growth:.1f}MB growth at iteration {i}"
            
            final_memory = process.memory_info().rss / 1024 / 1024
            total_growth = final_memory - initial_memory
            
            print(f"Memory efficiency: {total_growth:.1f}MB growth over 20 parses")
            
        finally:
            os.unlink(path)

    def test_error_handling_performance(self):
        """Test that error handling doesn't significantly impact performance."""
        # Create configs with various types of errors
        error_configs = [
            # Invalid rate
            'limits: {"0x123": {rate: -1}}',
            # Invalid CAN ID
            'limits: {"invalid_id": {rate: 10}}', 
            # Missing required field
            'limits: {"0x123": {burst: 5}}',
            # Invalid structure
            'limits: []',
            # Invalid remap
            'actions: {remap: [{from: "0x123", to: "0x123"}]}',
        ]
        
        iterations = 100
        
        for i, config in enumerate(error_configs):
            path = _write_tmp(config)
            
            try:
                start_time = time.perf_counter()
                
                # Try parsing multiple times (should fail quickly each time)
                for _ in range(iterations):
                    try:
                        load_rules(path)
                        pytest.fail("Expected RuleError but parsing succeeded")
                    except Exception:
                        pass  # Expected to fail
                
                end_time = time.perf_counter()
                total_time = end_time - start_time
                per_error = total_time / iterations * 1000  # ms per error
                
                # Error handling should be fast
                assert total_time < 2.0, f"Error config {i} handling too slow: {total_time:.3f}s"
                assert per_error < 1.0, f"Error config {i} per-error too slow: {per_error:.3f}ms"
                
            finally:
                os.unlink(path)

    @pytest.mark.parametrize("config_size", [10, 100, 1000, 5000])
    def test_scaling_performance(self, config_size):
        """Test performance scaling with different configuration sizes."""
        # Generate config of specified size
        yaml_lines = ["limits:"]
        for i in range(config_size):
            can_id = 0x1000 + i
            rate = 10 + (i % 100)
            yaml_lines.append(f'  "0x{can_id:X}": {{ rate: {rate} }}')
        
        path = _write_tmp("\n".join(yaml_lines))
        
        try:
            start_time = time.perf_counter()
            rules = load_rules(path)
            end_time = time.perf_counter()
            
            parsing_time = end_time - start_time
            
            # Performance should scale reasonably
            # Allow more time for larger configs but not exponential
            max_time = 0.1 + (config_size / 1000) * 2.0  # Linear scaling expectation
            assert parsing_time < max_time, f"Size {config_size} too slow: {parsing_time:.3f}s > {max_time:.3f}s"
            
            # Verify correctness
            assert len(rules["limits"]) == config_size
            
            entries_per_second = config_size / parsing_time if parsing_time > 0 else float('inf')
            print(f"Config size {config_size}: {parsing_time:.4f}s ({entries_per_second:.0f} entries/sec)")
            
        finally:
            os.unlink(path)
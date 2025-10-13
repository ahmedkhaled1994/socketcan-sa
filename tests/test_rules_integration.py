#!/usr/bin/env python3
"""
Integration tests for rules.py

Tests real YAML files, complex configurations, and integration scenarios
with realistic CAN traffic shaping rules.
"""

import pytest
import tempfile
import os
import textwrap
from socketcan_sa.rules import load_rules, RuleError


def _write_tmp(yaml_text: str) -> str:
    """Helper to write temporary YAML file."""
    fd, path = tempfile.mkstemp(suffix=".yaml")
    os.close(fd)
    with open(path, "w", encoding="utf-8") as f:
        f.write(textwrap.dedent(yaml_text))
    return path


class TestRealWorldConfigurations:
    """Test realistic CAN traffic shaping configurations."""

    def test_automotive_ecu_configuration(self):
        """Test realistic automotive ECU traffic shaping rules."""
        path = _write_tmp("""
        # Automotive ECU Rate Limits
        limits:
          # Engine Management
          "0x7E0": { rate: 100, burst: 20 }    # Engine RPM (high frequency)
          "0x7E1": { rate: 50, burst: 10 }     # Engine temperature
          "0x7E2": { rate: 10, burst: 5 }      # Engine diagnostics
          
          # Transmission
          "0x7E3": { rate: 50, burst: 15 }     # Gear position
          "0x7E4": { rate: 25, burst: 8 }      # Transmission temperature
          
          # Body Control Module  
          "0x500": { rate: 20, burst: 5 }      # Door status
          "0x501": { rate: 15, burst: 3 }      # Window status
          "0x502": { rate: 5, burst: 2 }       # Interior lights
          
          # Safety Systems
          "0x300": { rate: 200, burst: 50 }    # ABS (critical, high rate)
          "0x301": { rate: 100, burst: 25 }    # Airbag system
          "0x302": { rate: 80, burst: 20 }     # ESP/Traction control

        actions:
          # Drop non-essential messages during high load
          drop: 
            - "0x600"  # Infotainment heartbeat
            - "0x601"  # Radio status
            - "0x602"  # Climate control display
            
          # Remap deprecated IDs to new ones
          remap:
            - { from: "0x7E5", to: "0x7E0" }   # Old engine RPM -> new
            - { from: "0x7E6", to: "0x7E1" }   # Old temperature -> new
            - { from: "0x400", to: "0x500" }   # Old door status -> new
        """)
        
        try:
            rules = load_rules(path)
            
            # Verify engine management rates
            assert rules["limits"][0x7E0]["rate"] == 100.0
            assert rules["limits"][0x7E0]["burst"] == 20
            
            # Verify safety system priorities (higher rates)
            assert rules["limits"][0x300]["rate"] == 200.0  # ABS highest
            assert rules["limits"][0x301]["rate"] == 100.0  # Airbag high
            
            # Verify infotainment blocking
            assert 0x600 in rules["drop"]
            assert 0x601 in rules["drop"]
            
            # Verify legacy ID remapping
            assert rules["remap"][0x7E5] == 0x7E0
            assert rules["remap"][0x400] == 0x500
            
        finally:
            os.unlink(path)

    def test_industrial_can_bus_configuration(self):
        """Test industrial CAN bus traffic management rules."""
        path = _write_tmp("""
        # Industrial Automation Network
        limits:
          # High-priority control loops (1-100ms)
          "0x100": { rate: 1000, burst: 100 }  # Servo motor position
          "0x101": { rate: 500, burst: 50 }    # Hydraulic pressure
          "0x102": { rate: 250, burst: 25 }    # Temperature control
          
          # Medium-priority sensors (100-500ms)
          "0x200": { rate: 100, burst: 10 }    # Flow sensors
          "0x201": { rate: 50, burst: 5 }      # Vibration monitoring  
          "0x202": { rate: 25, burst: 3 }      # Environmental sensors
          
          # Low-priority diagnostics (1-10s)
          "0x300": { rate: 10, burst: 2 }      # System health
          "0x301": { rate: 5, burst: 1 }       # Performance metrics
          "0x302": { rate: 1, burst: 1 }       # Log messages

        actions:
          # Drop debug messages during production
          drop:
            - "0x7F0"    # Debug traces
            - "0x7F1"    # Development logs
            - "0x7F2"    # Test patterns
            
          # Consolidate sensor readings
          remap:
            - { from: "0x250", to: "0x200" }   # Backup flow sensor
            - { from: "0x251", to: "0x201" }   # Backup vibration
        """)
        
        try:
            rules = load_rules(path)
            
            # Verify control loop priorities (highest rates)
            assert rules["limits"][0x100]["rate"] == 1000.0
            assert rules["limits"][0x101]["rate"] == 500.0
            
            # Verify sensor rates are lower
            assert rules["limits"][0x200]["rate"] == 100.0
            assert rules["limits"][0x201]["rate"] == 50.0
            
            # Verify diagnostics have lowest rates
            assert rules["limits"][0x300]["rate"] == 10.0
            assert rules["limits"][0x302]["rate"] == 1.0
            
            # Verify debug filtering
            debug_ids = {0x7F0, 0x7F1, 0x7F2}
            assert debug_ids.issubset(rules["drop"])
            
        finally:
            os.unlink(path)

    def test_can_fd_extended_id_configuration(self):
        """Test configuration with CAN FD extended 29-bit IDs."""
        path = _write_tmp("""
        # CAN FD with Extended IDs (29-bit)
        limits:
          # Extended format IDs (automotive standard)
          "0x18DA10F1": { rate: 50, burst: 10 }   # ISO-TP request
          "0x18DAF110": { rate: 30, burst: 6 }    # ISO-TP response  
          "0x18DB33F1": { rate: 25, burst: 5 }    # Diagnostic data
          "0x1CFECA00": { rate: 100, burst: 20 }  # J1939 engine data
          "0x1CFEF600": { rate: 80, burst: 15 }   # J1939 vehicle speed
          "0x1CFF0000": { rate: 200, burst: 40 }  # J1939 high priority

        actions:
          drop:
            - "0x1FFFFF00"    # Test message (near maximum ID)
            - "0x1FFFFFE0"    # Another test message
            
          remap:
            - { from: "0x18DA00F1", to: "0x18DA10F1" }  # Legacy diagnostic
        """)
        
        try:
            rules = load_rules(path)
            
            # Verify extended ID parsing
            assert 0x18DA10F1 in rules["limits"]
            assert 0x1CFECA00 in rules["limits"]
            assert 0x1CFF0000 in rules["limits"]
            
            # Verify rates are properly assigned
            assert rules["limits"][0x1CFF0000]["rate"] == 200.0  # Highest priority
            assert rules["limits"][0x18DA10F1]["rate"] == 50.0   # Diagnostic
            
            # Verify extended ID actions
            assert 0x1FFFFF00 in rules["drop"]
            assert rules["remap"][0x18DA00F1] == 0x18DA10F1
            
        finally:
            os.unlink(path)


class TestComplexValidationScenarios:
    """Test complex validation and cross-section interactions."""

    def test_limits_and_actions_interaction(self):
        """Test interaction between limits and actions for same IDs."""
        path = _write_tmp("""
        limits:
          "0x123": { rate: 50, burst: 10 }
          "0x456": { rate: 25, burst: 5 }
          
        actions:
          drop: ["0x123"]    # Also in limits - should be valid
          remap:
            - { from: "0x456", to: "0x789" }  # From ID also in limits
        """)
        
        try:
            rules = load_rules(path)
            
            # Should allow ID to be in both limits and actions
            assert 0x123 in rules["limits"]
            assert 0x123 in rules["drop"]
            
            assert 0x456 in rules["limits"]  
            assert rules["remap"][0x456] == 0x789
            
        finally:
            os.unlink(path)

    def test_large_configuration_parsing(self):
        """Test parsing of large, complex configuration."""
        # Generate large config with many entries
        yaml_lines = ["# Large CAN configuration", "limits:"]
        
        # Add 500 limit entries
        for i in range(500):
            can_id = 0x100 + i
            rate = 10 + (i % 100)
            burst = max(1, rate // 5)
            yaml_lines.append(f'  "0x{can_id:X}": {{ rate: {rate}, burst: {burst} }}')
        
        yaml_lines.extend([
            "",
            "actions:",
            "  drop:"
        ])
        
        # Add 100 drop entries  
        for i in range(100):
            can_id = 0x700 + i
            yaml_lines.append(f'    - "0x{can_id:X}"')
        
        yaml_lines.extend([
            "  remap:"
        ])
        
        # Add 50 remap entries
        for i in range(50):
            from_id = 0x800 + i
            to_id = 0x900 + i  
            yaml_lines.append(f'    - {{ from: "0x{from_id:X}", to: "0x{to_id:X}" }}')
        
        path = _write_tmp("\n".join(yaml_lines))
        
        try:
            rules = load_rules(path)
            
            # Verify correct parsing of large config
            assert len(rules["limits"]) == 500
            assert len(rules["drop"]) == 100
            assert len(rules["remap"]) == 50
            
            # Spot check some entries
            assert rules["limits"][0x150]["rate"] == 90.0  # 10 + (0x50 % 100)
            assert 0x750 in rules["drop"]
            assert rules["remap"][0x820] == 0x920
            
        finally:
            os.unlink(path)


class TestFileFormatCompatibility:
    """Test compatibility with various YAML file formats and styles."""

    def test_yaml_flow_style_syntax(self):
        """Test YAML flow style (inline) syntax."""
        path = _write_tmp("""
        limits: {"0x123": {rate: 10, burst: 5}, "0x456": {rate: 20}}
        actions: {drop: ["0x789", "0xABC"], remap: [{from: "0x100", to: "0x200"}]}
        """)
        
        try:
            rules = load_rules(path)
            
            assert rules["limits"][0x123]["rate"] == 10.0
            assert rules["limits"][0x456]["burst"] == 20  # Default ceil(20)
            assert 0x789 in rules["drop"]
            assert rules["remap"][0x100] == 0x200
            
        finally:
            os.unlink(path)

    def test_yaml_block_style_variations(self):
        """Test various YAML block style formats."""
        path = _write_tmp("""
        limits:
          0x123:          # Unquoted hex (valid YAML)
            rate: 10
            burst: 5
          "0x456":        # Quoted hex
            rate: 20
          291:            # Decimal int key
            rate: 30
            burst: 15
            
        actions:
          drop:
            - 0x789       # Unquoted in list
            - "0xABC"     # Quoted in list
            - 1000        # Decimal in list
          remap:
            - from: 0x100      # Unquoted from
              to: "0x200"      # Quoted to
        """)
        
        try:
            rules = load_rules(path)
            
            # Should parse correctly (0x123 and 291 are different IDs)
            assert len(rules["limits"]) >= 2  # At least 2 different IDs
            assert len(rules["drop"]) == 3
            assert len(rules["remap"]) == 1
            
        finally:
            os.unlink(path)

    def test_yaml_comments_and_whitespace(self):
        """Test YAML with extensive comments and varied whitespace."""
        path = _write_tmp("""
        # Main configuration file for CAN traffic shaping
        # Generated on 2025-10-13
        
        limits:    # Rate limiting section
          # Engine control messages
          "0x7E0": { rate: 100, burst: 20 }    # RPM signal - critical
          "0x7E1": { rate: 50 }                # Temperature - medium priority
          
          # Body control
          "0x500":      # Door sensors
            rate: 10    # Low frequency sufficient 
            burst: 2    # Small burst allowance
            
        actions:
          # Remove unnecessary traffic
          drop:
            - "0x600"   # Radio status
            - "0x601"   # CD player info  
            # More entries could go here
            
          # Legacy compatibility  
          remap:
            - { from: "0x7E5", to: "0x7E0" }  # Old RPM ID -> new
            # Could add more mappings
        
        # End of configuration
        """)
        
        try:
            rules = load_rules(path)
            
            # Should parse correctly despite extensive comments
            assert len(rules["limits"]) == 3
            assert len(rules["drop"]) == 2  
            assert len(rules["remap"]) == 1
            
            # Verify specific values
            assert rules["limits"][0x7E0]["rate"] == 100.0
            assert rules["limits"][0x7E1]["burst"] == 50  # ceil(50)
            assert rules["limits"][0x500]["burst"] == 2
            
        finally:
            os.unlink(path)


class TestErrorRecoveryAndReporting:
    """Test error recovery and detailed error reporting."""

    def test_detailed_error_messages_with_context(self):
        """Test that error messages provide helpful context."""
        # Test with specific field references in error messages
        test_cases = [
            (
                'limits: {"invalid_hex": {rate: 10}}',
                "limits[invalid_hex]",  # Should reference the problematic key
            ),
            (
                'actions: {drop: ["invalid_id"]}', 
                "actions.drop",  # Should reference the drop section
            ),
            (
                'actions: {remap: [{from: "invalid", to: "0x123"}]}',
                "actions.remap.from",  # Should reference the from field
            ),
        ]
        
        for yaml_content, expected_context in test_cases:
            path = _write_tmp(yaml_content)
            try:
                with pytest.raises(RuleError) as exc_info:
                    load_rules(path)
                
                # Error message should contain contextual information
                error_message = str(exc_info.value)
                assert expected_context in error_message
                
            finally:
                os.unlink(path)

    def test_multiple_errors_in_same_file(self):
        """Test behavior when multiple errors exist in same file."""
        # This will fail on the first error encountered
        path = _write_tmp("""
        limits:
          "invalid_id_1": { rate: -1 }      # First error - negative rate
          "invalid_id_2": { rate: 0 }       # Second error - zero rate  
          "0x123": { rate: "not_number" }   # Third error - invalid type
        """)
        
        try:
            with pytest.raises(RuleError):
                load_rules(path)
            # Should fail fast on first error, not collect all errors
            
        finally:
            os.unlink(path)
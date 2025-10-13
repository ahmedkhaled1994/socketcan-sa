#!/usr/bin/env python3
"""
Coverage tests for rules.py

Tests error handling, boundary conditions, invalid data, and edge cases
for the YAML rules parser and CAN ID validation.
"""

import pytest
import tempfile
import os
import textwrap
from unittest.mock import Mock, patch, mock_open
from socketcan_sa.rules import load_rules, RuleError, _parse_can_id, MAX_CAN_ID


def _write_tmp(yaml_text: str) -> str:
    """Helper to write temporary YAML file."""
    fd, path = tempfile.mkstemp(suffix=".yaml")
    os.close(fd)
    with open(path, "w", encoding="utf-8") as f:
        f.write(textwrap.dedent(yaml_text))
    return path


class TestErrorHandling:
    """Test error handling scenarios for file operations."""

    def test_file_not_found(self):
        """Test handling of non-existent rules file."""
        with pytest.raises(RuleError, match="Failed to load rules"):
            load_rules("/nonexistent/path/rules.yaml")

    def test_file_permission_denied(self):
        """Test handling of file permission errors."""
        with patch('builtins.open', side_effect=PermissionError("Permission denied")):
            with pytest.raises(RuleError, match="Failed to load rules"):
                load_rules("protected.yaml")

    def test_malformed_yaml_syntax(self):
        """Test handling of malformed YAML syntax."""
        path = _write_tmp("""
        limits:
          "0x123": { rate: 10
        # Missing closing brace - invalid YAML
        """)
        try:
            with pytest.raises(RuleError, match="Failed to load rules"):
                load_rules(path)
        finally:
            os.unlink(path)

    def test_yaml_with_tabs_and_mixed_indentation(self):
        """Test handling of YAML with problematic whitespace."""
        # YAML doesn't allow tabs for indentation - should raise error
        content = "limits:\n\t'0x123': { rate: 10 }"
        path = _write_tmp(content)
        try:
            with pytest.raises(RuleError, match="Failed to load rules"):
                load_rules(path)
        finally:
            os.unlink(path)

    def test_empty_file_handling(self):
        """Test handling of completely empty YAML file."""
        path = _write_tmp("")
        try:
            rules = load_rules(path)
            assert rules == {"limits": {}, "drop": set(), "remap": {}}
        finally:
            os.unlink(path)

    def test_yaml_with_null_values(self):
        """Test handling of null/None values in YAML."""
        path = _write_tmp("""
        limits: null
        actions: null
        """)
        try:
            # null limits should raise validation error
            with pytest.raises(RuleError, match="limits: must be a mapping"):
                load_rules(path)
        finally:
            os.unlink(path)


class TestCanIdParsing:
    """Test CAN ID parsing edge cases and boundary conditions."""

    def test_can_id_boundary_values(self):
        """Test CAN ID parsing at boundary values."""
        # Minimum valid ID
        assert _parse_can_id(0, field="test") == 0
        assert _parse_can_id("0", field="test") == 0
        assert _parse_can_id("0x0", field="test") == 0
        
        # Maximum 11-bit ID (standard CAN)
        assert _parse_can_id(0x7FF, field="test") == 0x7FF
        assert _parse_can_id("2047", field="test") == 0x7FF
        assert _parse_can_id("0x7FF", field="test") == 0x7FF
        
        # Maximum 29-bit ID (extended CAN)
        assert _parse_can_id(MAX_CAN_ID, field="test") == MAX_CAN_ID
        assert _parse_can_id("0x1FFFFFFF", field="test") == MAX_CAN_ID

    def test_can_id_format_variations(self):
        """Test various CAN ID format inputs."""
        test_cases = [
            ("0x123", 0x123),
            ("0X123", 0x123),  # Uppercase X
            ("0x0123", 0x123),  # Leading zeros
            ("123", 123),
            ("  123  ", 123),  # Whitespace
            ("12_3", 123),     # Underscores (should be removed)
        ]
        
        for input_val, expected in test_cases:
            assert _parse_can_id(input_val, field="test") == expected

    def test_can_id_invalid_formats(self):
        """Test invalid CAN ID format handling."""
        invalid_cases = [
            (None, "must be int or hex/dec string"),
            ([], "must be int or hex/dec string"),
            ({}, "must be int or hex/dec string"),
            (3.14, "must be int or hex/dec string"),
            ("", "invalid CAN ID format"),
            ("0x", "invalid CAN ID format"),
            ("xyz", "invalid CAN ID format"),
            ("0xGHI", "invalid CAN ID format"),
            ("12.34", "invalid CAN ID format"),
            ("0b1010", "invalid CAN ID format"),  # Binary not supported
        ]
        
        for invalid_input, expected_error in invalid_cases:
            with pytest.raises(RuleError, match=expected_error):
                _parse_can_id(invalid_input, field="test_field")

    def test_can_id_out_of_range(self):
        """Test CAN ID range validation."""
        out_of_range_cases = [
            -1,
            -100,
            "0x20000000",  # Just above MAX_CAN_ID
            "0x30000000",
            MAX_CAN_ID + 1,
            "999999999",   # Large decimal
        ]
        
        for invalid_id in out_of_range_cases:
            with pytest.raises(RuleError, match="out of range"):
                _parse_can_id(invalid_id, field="test")


class TestLimitsSection:
    """Test limits section parsing and validation."""

    def test_limits_non_dict_types(self):
        """Test invalid limits section types."""
        invalid_limits = [
            ("limits: []", "must be a mapping"),
            ("limits: 'string'", "must be a mapping"), 
            ("limits: 123", "must be a mapping"),
            ("limits: null", "must be a mapping"),
        ]
        
        for yaml_content, expected_error in invalid_limits:
            path = _write_tmp(yaml_content)
            try:
                with pytest.raises(RuleError, match=expected_error):
                    load_rules(path)
            finally:
                os.unlink(path)

    def test_limits_invalid_config_types(self):
        """Test invalid limit configuration types."""
        invalid_configs = [
            ('limits: {"0x123": "not a dict"}', "value must be a mapping"),
            ('limits: {"0x123": []}', "value must be a mapping"),
            ('limits: {"0x123": 123}', "value must be a mapping"),
            ('limits: {"0x123": null}', "value must be a mapping"),
        ]
        
        for yaml_content, expected_error in invalid_configs:
            path = _write_tmp(yaml_content)
            try:
                with pytest.raises(RuleError, match=expected_error):
                    load_rules(path)
            finally:
                os.unlink(path)

    def test_limits_missing_required_fields(self):
        """Test missing required fields in limit config."""
        path = _write_tmp("""
        limits:
          "0x123": { burst: 10 }  # Missing rate
        """)
        try:
            with pytest.raises(RuleError, match="missing 'rate'"):
                load_rules(path)
        finally:
            os.unlink(path)

    def test_limits_invalid_rate_values(self):
        """Test invalid rate value types and ranges."""
        invalid_rates = [
            (0, "must be > 0"),
            (-1, "must be > 0"),
            (-0.5, "must be > 0"),
            ("not_a_number", "must be > 0"),
            (None, "must be > 0"),
            ([], "must be > 0"),
        ]
        
        for rate_val, expected_error in invalid_rates:
            yaml_content = f"""
            limits:
              "0x123": {{ rate: {repr(rate_val)} }}
            """
            path = _write_tmp(yaml_content)
            try:
                with pytest.raises(RuleError, match=expected_error):
                    load_rules(path)
            finally:
                os.unlink(path)

    def test_limits_invalid_burst_values(self):
        """Test invalid burst value types and ranges."""
        invalid_bursts = [
            (0, "must be >= 1"),
            (-1, "must be >= 1"),
            (0.5, "must be >= 1"),  # Float burst not allowed
            ("5", "must be >= 1"),  # String not allowed
            (None, "must be >= 1"),
        ]
        
        for burst_val, expected_error in invalid_bursts:
            yaml_content = f"""
            limits:
              "0x123": {{ rate: 10, burst: {repr(burst_val)} }}
            """
            path = _write_tmp(yaml_content)
            try:
                with pytest.raises(RuleError, match=expected_error):
                    load_rules(path)
            finally:
                os.unlink(path)

    def test_limits_default_burst_calculation(self):
        """Test default burst calculation when not specified."""
        path = _write_tmp("""
        limits:
          "0x123": { rate: 10.7 }    # Should ceil to 11
          "0x456": { rate: 5.0 }     # Should be 5
          "0x789": { rate: 1.1 }     # Should ceil to 2
        """)
        try:
            rules = load_rules(path)
            assert rules["limits"][0x123]["burst"] == 11  # ceil(10.7)
            assert rules["limits"][0x456]["burst"] == 5   # ceil(5.0) 
            assert rules["limits"][0x789]["burst"] == 2   # ceil(1.1)
        finally:
            os.unlink(path)


class TestActionsSection:
    """Test actions section parsing and validation."""

    def test_actions_non_dict_types(self):
        """Test invalid actions section types."""
        invalid_actions = [
            ("actions: []", "must be a mapping"),
            ("actions: 'string'", "must be a mapping"),
            ("actions: 123", "must be a mapping"),
        ]
        
        for yaml_content, expected_error in invalid_actions:
            path = _write_tmp(yaml_content)
            try:
                with pytest.raises(RuleError, match=expected_error):
                    load_rules(path)
            finally:
                os.unlink(path)

    def test_drop_list_invalid_types(self):
        """Test invalid drop list types."""
        invalid_drops = [
            ("actions: { drop: 'not a list' }", "must be a list"),
            ("actions: { drop: 123 }", "must be a list"),
            ("actions: { drop: {} }", "must be a list"),
        ]
        
        for yaml_content, expected_error in invalid_drops:
            path = _write_tmp(yaml_content)
            try:
                with pytest.raises(RuleError, match=expected_error):
                    load_rules(path)
            finally:
                os.unlink(path)

    def test_remap_list_invalid_types(self):
        """Test invalid remap list types."""
        invalid_remaps = [
            ("actions: { remap: 'not a list' }", "must be a list"),
            ("actions: { remap: 123 }", "must be a list"),
            ("actions: { remap: {} }", "must be a list"),
        ]
        
        for yaml_content, expected_error in invalid_remaps:
            path = _write_tmp(yaml_content)
            try:
                with pytest.raises(RuleError, match=expected_error):
                    load_rules(path)
            finally:
                os.unlink(path)

    def test_remap_invalid_item_structure(self):
        """Test invalid remap item structures."""
        invalid_items = [
            ('actions: { remap: ["not a dict"] }', "each item must be"),
            ('actions: { remap: [123] }', "each item must be"),
            ('actions: { remap: [{}] }', "each item must be"),  # Missing from/to
            ('actions: { remap: [{ from: "0x123" }] }', "each item must be"),  # Missing to
            ('actions: { remap: [{ to: "0x123" }] }', "each item must be"),    # Missing from
        ]
        
        for yaml_content, expected_error in invalid_items:
            path = _write_tmp(yaml_content)
            try:
                with pytest.raises(RuleError, match=expected_error):
                    load_rules(path)
            finally:
                os.unlink(path)

    def test_remap_identical_from_to(self):
        """Test remap with identical from and to IDs."""
        path = _write_tmp("""
        actions:
          remap:
            - { from: "0x123", to: "0x123" }  # Identical
        """)
        try:
            with pytest.raises(RuleError, match="from and to are identical"):
                load_rules(path)
        finally:
            os.unlink(path)

    def test_remap_duplicate_from_ids(self):
        """Test remap with duplicate from IDs."""
        path = _write_tmp("""
        actions:
          remap:
            - { from: "0x123", to: "0x456" }
            - { from: "0x123", to: "0x789" }  # Duplicate from
        """)
        try:
            with pytest.raises(RuleError, match="duplicate 'from' ID"):
                load_rules(path)
        finally:
            os.unlink(path)


class TestBoundaryConditions:
    """Test boundary conditions and edge cases."""

    def test_maximum_limits_entries(self):
        """Test parsing large numbers of limit entries."""
        # Generate many limit entries
        limits_yaml = "limits:\n"
        for i in range(1000):  # Test with 1000 entries
            limits_yaml += f'  "0x{i:X}": {{ rate: {i + 1} }}\n'
        
        path = _write_tmp(limits_yaml)
        try:
            rules = load_rules(path)
            assert len(rules["limits"]) == 1000
            assert rules["limits"][0x123]["rate"] == 292.0  # 0x123 + 1
        finally:
            os.unlink(path)

    def test_mixed_id_formats_in_same_file(self):
        """Test mixing different ID formats in same file."""
        path = _write_tmp("""
        limits:
          "0x100": { rate: 10 }      # Hex string
          256: { rate: 20 }          # Decimal int
          "0X101": { rate: 30 }      # Uppercase hex
          "258": { rate: 40 }        # Decimal string
        actions:
          drop: ["0x200", 513, "0X202", "515"]
          remap:
            - { from: "0x300", to: 769 }     # Hex to decimal
            - { from: 770, to: "0x303" }     # Decimal to hex
        """)
        try:
            rules = load_rules(path)
            
            # Check limits normalized correctly
            assert 0x100 in rules["limits"]
            assert 256 in rules["limits"]
            assert 0x101 in rules["limits"]
            assert 258 in rules["limits"]
            
            # Check drop set normalized
            assert {0x200, 513, 0x202, 515}.issubset(rules["drop"])
            
            # Check remap dict normalized
            assert rules["remap"][0x300] == 769
            assert rules["remap"][770] == 0x303
        finally:
            os.unlink(path)

    def test_unicode_and_special_characters_in_yaml(self):
        """Test handling of Unicode and special characters."""
        path = _write_tmp("""
        # Comments with üñíçødé characters
        limits:
          "0x123": { rate: 10 }  # Comment with émojis 🚗💨
        actions:
          drop: ["0x456"]        # More ünîcødé
        """)
        try:
            rules = load_rules(path)
            assert 0x123 in rules["limits"]
            assert 0x456 in rules["drop"]
        finally:
            os.unlink(path)


class TestResourceCleanup:
    """Test proper resource cleanup in various scenarios."""

    def test_file_handle_cleanup_on_success(self):
        """Test file handles are properly closed on successful parsing."""
        path = _write_tmp("""
        limits:
          "0x123": { rate: 10 }
        """)
        try:
            # Parse rules successfully
            rules = load_rules(path)
            
            # File should be closed and we can delete it
            os.unlink(path)
            
            # Rules should still be accessible
            assert rules["limits"][0x123]["rate"] == 10.0
        except OSError:
            # If we can't delete, file handle wasn't closed properly
            pytest.fail("File handle not properly closed after successful parsing")

    def test_file_handle_cleanup_on_error(self):
        """Test file handles are properly closed even when parsing fails."""
        path = _write_tmp("""
        limits:
          "0x123": { rate: -1 }  # Invalid rate
        """)
        try:
            # Parsing should fail
            with pytest.raises(RuleError):
                load_rules(path)
            
            # File should still be closed and deletable
            os.unlink(path)
        except OSError:
            pytest.fail("File handle not properly closed after parsing error")
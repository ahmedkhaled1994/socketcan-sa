#!/usr/bin/env python3
"""
Property-based tests for rules.py

Uses Hypothesis to generate test cases and validate mathematical properties
and invariants of the rules parsing and validation system.
"""

import pytest
import tempfile
import os
import textwrap
import math
from hypothesis import given, strategies as st, settings, assume
from socketcan_sa.rules import load_rules, RuleError, _parse_can_id, MAX_CAN_ID


def _write_tmp(yaml_text: str) -> str:
    """Helper to write temporary YAML file."""
    fd, path = tempfile.mkstemp(suffix=".yaml")
    os.close(fd)
    with open(path, "w", encoding="utf-8") as f:
        f.write(textwrap.dedent(yaml_text))
    return path


class TestCanIdParsingProperties:
    """Property-based tests for CAN ID parsing."""

    @given(can_id=st.integers(min_value=0, max_value=MAX_CAN_ID))
    @settings(max_examples=100, deadline=1000)
    def test_can_id_int_roundtrip_property(self, can_id):
        """Test that valid integer CAN IDs parse correctly."""
        result = _parse_can_id(can_id, field="test")
        assert result == can_id
        assert isinstance(result, int)

    @given(can_id=st.integers(min_value=0, max_value=MAX_CAN_ID))  
    @settings(max_examples=100, deadline=1000)
    def test_can_id_hex_string_roundtrip_property(self, can_id):
        """Test that hex string CAN IDs parse to correct integer values."""
        hex_string = f"0x{can_id:X}"
        result = _parse_can_id(hex_string, field="test")
        assert result == can_id

    @given(can_id=st.integers(min_value=0, max_value=MAX_CAN_ID))
    @settings(max_examples=100, deadline=1000) 
    def test_can_id_decimal_string_roundtrip_property(self, can_id):
        """Test that decimal string CAN IDs parse correctly."""
        decimal_string = str(can_id)
        result = _parse_can_id(decimal_string, field="test")
        assert result == can_id

    @given(can_id=st.integers(min_value=MAX_CAN_ID + 1, max_value=0xFFFFFFFF))
    @settings(max_examples=50, deadline=1000)
    def test_can_id_out_of_range_property(self, can_id):
        """Test that out-of-range CAN IDs are consistently rejected."""
        with pytest.raises(RuleError, match="out of range"):
            _parse_can_id(can_id, field="test")

    @given(can_id=st.integers(max_value=-1))
    @settings(max_examples=50, deadline=1000)
    def test_can_id_negative_property(self, can_id):
        """Test that negative CAN IDs are consistently rejected."""
        with pytest.raises(RuleError, match="out of range"):
            _parse_can_id(can_id, field="test")

    @given(
        can_id=st.integers(min_value=0, max_value=MAX_CAN_ID),
        prefix=st.sampled_from(["0x", "0X"]),
        padding=st.integers(min_value=0, max_value=8)
    )
    @settings(max_examples=100, deadline=1000)
    def test_hex_format_variations_property(self, can_id, prefix, padding):
        """Test various hex format variations parse consistently."""
        # Create hex string with optional zero padding
        hex_digits = f"{can_id:X}"
        padded_hex = hex_digits.zfill(len(hex_digits) + padding)
        hex_string = f"{prefix}{padded_hex}"
        
        result = _parse_can_id(hex_string, field="test")
        assert result == can_id


class TestRateLimitProperties:
    """Property-based tests for rate limit validation."""

    @given(rate=st.floats(min_value=0.1, max_value=10000.0, allow_nan=False, allow_infinity=False))
    @settings(max_examples=100, deadline=1000)
    def test_valid_rate_acceptance_property(self, rate):
        """Test that valid positive rates are accepted."""
        yaml_content = f"""
        limits:
          "0x123": {{ rate: {rate} }}
        """
        path = _write_tmp(yaml_content)
        try:
            rules = load_rules(path)
            assert rules["limits"][0x123]["rate"] == float(rate)
        finally:
            os.unlink(path)

    @given(rate=st.floats(min_value=0.1, max_value=1000.0, allow_nan=False, allow_infinity=False))
    @settings(max_examples=100, deadline=1000)
    def test_burst_default_calculation_property(self, rate):
        """Test that default burst calculation follows ceil(rate) property."""
        yaml_content = f"""
        limits:
          "0x123": {{ rate: {rate} }}
        """
        path = _write_tmp(yaml_content)
        try:
            rules = load_rules(path)
            expected_burst = math.ceil(rate)
            assert rules["limits"][0x123]["burst"] == expected_burst
            assert rules["limits"][0x123]["burst"] >= rate  # Burst should always be >= rate
        finally:
            os.unlink(path)

    @given(
        rate=st.floats(min_value=0.1, max_value=1000.0, allow_nan=False, allow_infinity=False),
        burst=st.integers(min_value=1, max_value=2000)
    )
    @settings(max_examples=100, deadline=1000)
    def test_explicit_burst_property(self, rate, burst):
        """Test that explicit burst values are preserved when valid."""
        yaml_content = f"""
        limits:
          "0x123": {{ rate: {rate}, burst: {burst} }}
        """
        path = _write_tmp(yaml_content)
        try:
            rules = load_rules(path)
            assert rules["limits"][0x123]["rate"] == float(rate)
            assert rules["limits"][0x123]["burst"] == burst
        finally:
            os.unlink(path)

    @given(rate=st.one_of(
        st.floats(max_value=0.0, allow_nan=False, allow_infinity=False),
        st.floats(min_value=-1000.0, max_value=-0.1, allow_nan=False, allow_infinity=False)
    ))
    @settings(max_examples=50, deadline=1000)
    def test_invalid_rate_rejection_property(self, rate):
        """Test that non-positive rates are consistently rejected."""
        yaml_content = f"""
        limits:
          "0x123": {{ rate: {rate} }}
        """
        path = _write_tmp(yaml_content)
        try:
            with pytest.raises(RuleError, match="must be > 0"):
                load_rules(path)
        finally:
            os.unlink(path)

    @given(burst=st.integers(max_value=0))
    @settings(max_examples=50, deadline=1000)
    def test_invalid_burst_rejection_property(self, burst):
        """Test that non-positive burst values are consistently rejected."""
        yaml_content = f"""
        limits:
          "0x123": {{ rate: 10.0, burst: {burst} }}
        """
        path = _write_tmp(yaml_content)
        try:
            with pytest.raises(RuleError, match="must be >= 1"):
                load_rules(path)
        finally:
            os.unlink(path)


class TestDropListProperties:
    """Property-based tests for drop list validation."""

    @given(drop_ids=st.lists(
        st.integers(min_value=0, max_value=MAX_CAN_ID), 
        min_size=1, 
        max_size=50,
        unique=True
    ))
    @settings(max_examples=50, deadline=2000)
    def test_drop_list_normalization_property(self, drop_ids):
        """Test that drop lists are properly normalized to sets."""
        # Convert to YAML list format
        yaml_drop_list = ", ".join(f'"0x{cid:X}"' for cid in drop_ids)
        yaml_content = f"""
        actions:
          drop: [{yaml_drop_list}]
        """
        path = _write_tmp(yaml_content)
        try:
            rules = load_rules(path)
            
            # Should normalize to set with same IDs
            assert isinstance(rules["drop"], set)
            assert len(rules["drop"]) == len(drop_ids)
            assert rules["drop"] == set(drop_ids)
        finally:
            os.unlink(path)

    @given(drop_ids=st.lists(
        st.integers(min_value=0, max_value=MAX_CAN_ID),
        min_size=1,
        max_size=20
    ))  # Note: not unique=True to test duplicate handling
    @settings(max_examples=50, deadline=2000)
    def test_drop_list_deduplication_property(self, drop_ids):
        """Test that duplicate IDs in drop lists are deduplicated."""
        yaml_drop_list = ", ".join(f'"0x{cid:X}"' for cid in drop_ids)
        yaml_content = f"""
        actions:
          drop: [{yaml_drop_list}]
        """
        path = _write_tmp(yaml_content)
        try:
            rules = load_rules(path)
            
            # Set should contain only unique IDs
            unique_ids = set(drop_ids)
            assert rules["drop"] == unique_ids
            assert len(rules["drop"]) == len(unique_ids)
        finally:
            os.unlink(path)


class TestRemapProperties:  
    """Property-based tests for ID remapping validation."""

    @given(remap_pairs=st.lists(
        st.tuples(
            st.integers(min_value=0, max_value=MAX_CAN_ID // 2),  # from_id
            st.integers(min_value=MAX_CAN_ID // 2 + 1, max_value=MAX_CAN_ID)  # to_id (different range)
        ),
        min_size=1,
        max_size=20,
        unique_by=lambda x: x[0]  # Unique by from_id to avoid duplicates
    ))
    @settings(max_examples=50, deadline=2000)
    def test_remap_normalization_property(self, remap_pairs):
        """Test that remap lists are properly normalized to dictionaries."""
        # Build YAML remap list
        remap_items = []
        for from_id, to_id in remap_pairs:
            remap_items.append(f'{{ from: "0x{from_id:X}", to: "0x{to_id:X}" }}')
        
        yaml_content = f"""
        actions:
          remap: [{", ".join(remap_items)}]
        """
        path = _write_tmp(yaml_content)
        try:
            rules = load_rules(path)
            
            # Should normalize to dict
            assert isinstance(rules["remap"], dict)
            assert len(rules["remap"]) == len(remap_pairs)
            
            # Verify all mappings
            for from_id, to_id in remap_pairs:
                assert rules["remap"][from_id] == to_id
        finally:
            os.unlink(path)

    @given(can_id=st.integers(min_value=0, max_value=MAX_CAN_ID))
    @settings(max_examples=50, deadline=1000)
    def test_remap_identical_ids_property(self, can_id):
        """Test that identical from/to IDs are rejected."""
        from_id = to_id = can_id  # Always identical
        
        yaml_content = f"""
        actions:
          remap:
            - {{ from: "0x{from_id:X}", to: "0x{to_id:X}" }}
        """
        path = _write_tmp(yaml_content)
        try:
            with pytest.raises(RuleError, match="from and to are identical"):
                load_rules(path)
        finally:
            os.unlink(path)


class TestStructuralProperties:
    """Property-based tests for overall structure validation."""

    @given(
        num_limits=st.integers(min_value=0, max_value=50),
        num_drops=st.integers(min_value=0, max_value=30),
        num_remaps=st.integers(min_value=0, max_value=20)
    )
    @settings(max_examples=50, deadline=3000)
    def test_configuration_size_scaling_property(self, num_limits, num_drops, num_remaps):
        """Test that configurations scale properly with increasing size."""
        # Generate unique CAN IDs for each section
        limits_yaml = []
        drops_yaml = []
        remaps_yaml = []
        
        # Generate limits
        for i in range(num_limits):
            can_id = 0x100 + i
            rate = 10 + (i % 50)
            limits_yaml.append(f'  "0x{can_id:X}": {{ rate: {rate} }}')
        
        # Generate drops (different ID range)
        for i in range(num_drops):
            can_id = 0x200 + i
            drops_yaml.append(f'"0x{can_id:X}"')
        
        # Generate remaps (different ID ranges)
        for i in range(num_remaps):
            from_id = 0x300 + i
            to_id = 0x400 + i
            remaps_yaml.append(f'{{ from: "0x{from_id:X}", to: "0x{to_id:X}" }}')
        
        # Build complete YAML with proper formatting
        yaml_parts = []
        if limits_yaml:
            yaml_parts.extend(["limits:"] + limits_yaml)
        if drops_yaml or remaps_yaml:
            yaml_parts.append("actions:")
            if drops_yaml:
                yaml_parts.append("  drop:")
                for drop_id in drops_yaml:
                    yaml_parts.append(f"    - {drop_id}")
            if remaps_yaml:
                yaml_parts.append("  remap:")
                for remap_item in remaps_yaml:
                    yaml_parts.append(f"    - {remap_item}")
        
        if not yaml_parts:
            yaml_content = "{}"  # Empty config
        else:
            yaml_content = "\n".join(yaml_parts)
        
        path = _write_tmp(yaml_content)
        try:
            rules = load_rules(path)
            
            # Verify correct parsing
            assert len(rules["limits"]) == num_limits
            assert len(rules["drop"]) == num_drops  
            assert len(rules["remap"]) == num_remaps
            
            # Verify structure invariants
            assert isinstance(rules["limits"], dict)
            assert isinstance(rules["drop"], set)
            assert isinstance(rules["remap"], dict)
            
        finally:
            os.unlink(path)

    @given(data=st.data())
    @settings(max_examples=30, deadline=2000)
    def test_mixed_id_format_consistency_property(self, data):
        """Test that mixed ID formats produce consistent results."""
        # Generate a CAN ID and represent it in different formats
        can_id = data.draw(st.integers(min_value=0, max_value=MAX_CAN_ID))
        
        formats = [
            str(can_id),           # Decimal string
            f"0x{can_id:X}",       # Hex string lowercase
            f"0X{can_id:X}",       # Hex string uppercase  
            can_id,                # Integer
        ]
        
        # Use different formats in same config
        chosen_formats = data.draw(st.lists(st.sampled_from(formats), min_size=2, max_size=4, unique=True))
        
        if len(chosen_formats) >= 2:
            yaml_content = f"""
            limits:
              {repr(chosen_formats[0])}: {{ rate: 10 }}
            actions:
              drop: [{repr(chosen_formats[1])}]
            """
            
            path = _write_tmp(yaml_content)
            try:
                rules = load_rules(path)
                
                # Both should resolve to the same CAN ID
                assert can_id in rules["limits"]
                assert can_id in rules["drop"]
                
            finally:
                os.unlink(path)
#!/usr/bin/env python3
"""
Rules parser (Step 10)

YAML schema (strings or ints for IDs; hex with/without 0x ok):

limits:
  "0x18FF50E5": { rate: 50, burst: 25 }   # fps, tokens
  "0x7DF":      { rate: 10 }               # burst defaults to ceil(rate)

actions:
  drop:  [ "0x123", 0x321, 200 ]          # IDs to drop
  remap: [ { from: "0x456", to: "0x457" } ]

Returns a normalized dict:
{
  "limits": {int_id: {"rate": float, "burst": int}, ...},
  "drop":   set[int],
  "remap":  dict[int, int],  # from_id -> to_id
}
"""

from __future__ import annotations
from typing import Any, Dict, Set
import math
import yaml

MAX_CAN_ID = 0x1FFFFFFF  # 29-bit (covers 11-bit too)


class RuleError(ValueError):
    """Raised when rule parsing or validation fails."""
    pass


def _parse_can_id(val: Any, *, field: str) -> int:
    """Parse CAN ID from various input formats.
    
    Args:
        val: Input value (int, hex string, decimal string)
        field: Field name for error messages
        
    Returns:
        Parsed CAN ID as integer
        
    Raises:
        RuleError: If parsing fails or ID is out of range
    """
    if isinstance(val, int):
        cid = val
    elif isinstance(val, str):
        s = val.strip().lower().replace("_", "")
        try:
            if s.startswith("0x"):
                cid = int(s, 16)
            else:
                cid = int(s, 10)
        except ValueError:
            raise RuleError(f"{field}: invalid CAN ID format '{val}'")
    else:
        raise RuleError(f"{field}: CAN ID must be int or hex/dec string, got {type(val).__name__}")
    
    # Validate range
    if not (0 <= cid <= MAX_CAN_ID):
        raise RuleError(f"{field}: CAN ID 0x{cid:X} out of range [0, 0x{MAX_CAN_ID:X}]")
    
    return cid


def load_rules(path: str) -> Dict[str, Any]:
    """Load and validate shaping rules from YAML file.
    
    Args:
        path: Path to YAML rules file
        
    Returns:
        Normalized rules dictionary with:
        - limits: {can_id: {"rate": float, "burst": int}}
        - drop: set of CAN IDs to drop
        - remap: {from_id: to_id} mapping
        
    Raises:
        RuleError: If file cannot be parsed or contains invalid rules
    """
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f) or {}
    except (OSError, yaml.YAMLError) as e:
        raise RuleError(f"Failed to load rules from {path}: {e}")
    
    if not isinstance(data, dict):
        raise RuleError("Top-level YAML must be a mapping")
    
    result = {
        "limits": {},
        "drop": set(),
        "remap": {},
    }
    
    # Parse limits section
    if "limits" in data:
        limits_data = data["limits"]
        if not isinstance(limits_data, dict):
            raise RuleError("limits: must be a mapping")
        
        for id_key, limit_config in limits_data.items():
            if not isinstance(limit_config, dict):
                raise RuleError(f"limits[{id_key}]: value must be a mapping")
            
            can_id = _parse_can_id(id_key, field=f"limits[{id_key}]")
            
            if "rate" not in limit_config:
                raise RuleError(f"limits[{id_key}]: missing 'rate' field")
            
            rate = limit_config["rate"]
            if not isinstance(rate, (int, float)) or rate <= 0:
                raise RuleError(f"limits[{id_key}]: rate must be > 0, got {rate}")
            
            burst = limit_config.get("burst")
            if burst is None:
                burst = math.ceil(rate)
            elif not isinstance(burst, int) or burst < 1:
                raise RuleError(f"limits[{id_key}]: burst must be >= 1, got {burst}")
            
            result["limits"][can_id] = {
                "rate": float(rate),
                "burst": int(burst)
            }
    
    # Parse actions section
    if "actions" in data:
        actions_data = data["actions"]
        if not isinstance(actions_data, dict):
            raise RuleError("actions: must be a mapping")
        
        # Parse drop list
        if "drop" in actions_data:
            drop_list = actions_data["drop"]
            if not isinstance(drop_list, list):
                raise RuleError("actions.drop: must be a list")
            
            for item in drop_list:
                can_id = _parse_can_id(item, field="actions.drop")
                result["drop"].add(can_id)
        
        # Parse remap list
        if "remap" in actions_data:
            remap_list = actions_data["remap"]
            if not isinstance(remap_list, list):
                raise RuleError("actions.remap: must be a list")
            
            seen_from_ids = set()
            for item in remap_list:
                if not isinstance(item, dict) or "from" not in item or "to" not in item:
                    raise RuleError("actions.remap: each item must be {from: id, to: id}")
                
                from_id = _parse_can_id(item["from"], field="actions.remap.from")
                to_id = _parse_can_id(item["to"], field="actions.remap.to")
                
                if from_id == to_id:
                    raise RuleError(f"actions.remap: from and to are identical (0x{from_id:X})")
                
                if from_id in seen_from_ids:
                    raise RuleError(f"actions.remap: duplicate 'from' ID 0x{from_id:X}")
                
                seen_from_ids.add(from_id)
                result["remap"][from_id] = to_id
    
    return result

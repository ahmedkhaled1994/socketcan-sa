"""
SocketCAN Traffic Shaper & Analyzer

A Python package for shaping, analyzing, and replaying SocketCAN traffic.
"""

__version__ = "0.1.0"

# Import main modules for easier access
from . import analyzer
from . import rules  
from . import shaper

# Export key public functions per Copilot guidelines
from .analyzer import analyze
from .rules import load_rules, RuleError
from .shaper import run_bridge

__all__ = [
    # Modules
    "analyzer", "rules", "shaper",
    # Key functions and classes
    "analyze", "load_rules", "RuleError", "run_bridge"
]
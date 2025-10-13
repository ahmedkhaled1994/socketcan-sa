"""
SocketCAN Traffic Shaper & Analyzer

A Python package for shaping, analyzing, and replaying SocketCAN traffic.
"""

__version__ = "0.1.0"

# Import main modules for easier access
from . import shaper
from . import analyzer

__all__ = ["shaper", "analyzer"]
"""
NES Open Tournament Golf - Editor Algorithms

Contains algorithmic tools for the editor (e.g., fringe generation, rough fill).
"""

from .fringe_generator import FringeGenerator
from .rough_fill import RoughFill

__all__ = ["FringeGenerator", "RoughFill"]

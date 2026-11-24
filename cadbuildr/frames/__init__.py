"""Structural and woodworking frames (weldments) on CADbuildr foundation.

A ``Frame`` sweeps a profile along a skeleton of line / arc segments, trims
the corners (miter, butt, coped), adds gussets and end caps, and reports a
cut list. Each member is its own Part inside the frame Assembly.
"""

from .cut_list import CutListItem
from .frame import EndCap, EndCapPlate, Frame, FrameMember, Gusset, GussetPlate
from .geometry import Arc3D, Line3D, box_edges, polyline, rectangle
from .layout import DEFAULT_UP, FALLBACK_UP, solve_layout
from .profiles import (
    LUMBER_SIZES_IN,
    Angle,
    Channel,
    IBeam,
    Lumber,
    Profile,
    RectBar,
    RectTube,
    RoundBar,
    RoundTube,
    SquareTube,
)

__all__ = [
    "Angle",
    "Arc3D",
    "Channel",
    "CutListItem",
    "DEFAULT_UP",
    "EndCap",
    "EndCapPlate",
    "FALLBACK_UP",
    "Frame",
    "FrameMember",
    "Gusset",
    "GussetPlate",
    "IBeam",
    "LUMBER_SIZES_IN",
    "Line3D",
    "Lumber",
    "Profile",
    "RectBar",
    "RectTube",
    "RoundBar",
    "RoundTube",
    "SquareTube",
    "box_edges",
    "polyline",
    "rectangle",
    "solve_layout",
]

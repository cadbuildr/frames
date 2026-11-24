"""Structural and woodworking frames (weldments) on CADbuildr foundation.

A ``Frame`` sweeps a profile along a skeleton of line / arc segments, trims
the corners (miter, butt, coped), adds gussets and end caps, and reports a
cut list. Each member is its own Part inside the frame Assembly.
"""

from .connectors import Connection, ConnectorRule, Placed
from .cut_list import CutListItem
from .frame import (
    EndCap,
    EndCapPlate,
    Frame,
    FrameMember,
    Gusset,
    GussetPlate,
    basis_transform,
)
from .geometry import Arc3D, Line3D, box_edges, polyline, rectangle
from .layout import (
    DEFAULT_UP,
    FALLBACK_UP,
    FrameLayout,
    Junction,
    JunctionEnd,
    MemberLayout,
    solve_layout,
)
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
    "Connection",
    "ConnectorRule",
    "CutListItem",
    "DEFAULT_UP",
    "EndCap",
    "EndCapPlate",
    "FALLBACK_UP",
    "Frame",
    "FrameLayout",
    "FrameMember",
    "Gusset",
    "GussetPlate",
    "IBeam",
    "Junction",
    "JunctionEnd",
    "LUMBER_SIZES_IN",
    "Line3D",
    "Lumber",
    "MemberLayout",
    "Placed",
    "Profile",
    "RectBar",
    "RectTube",
    "RoundBar",
    "RoundTube",
    "SquareTube",
    "basis_transform",
    "box_edges",
    "polyline",
    "rectangle",
    "solve_layout",
]

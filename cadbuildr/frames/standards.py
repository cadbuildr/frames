"""Standard section sizes: the tables behind ``standard_profile`` and the
library's configurable members (``SquareTubeMember(size="40x40x3")``…).

Every table maps a size key (what a viewer shows in its drop-down) to the
dimensions in **millimetres**. Rows are the common stock sizes of each
standard, not the whole standard; add a row when a project needs one.

| Table | Standard | Family | Profile |
|---|---|---|---|
| ``EN10219_SHS`` | EN 10219-2 | square hollow section | ``SquareTube`` |
| ``EN10219_RHS`` | EN 10219-2 | rectangular hollow section | ``RectTube`` |
| ``EN10219_CHS`` | EN 10219-2 | circular hollow section | ``RoundTube`` |
| ``ASTM_A500_SQUARE`` | ASTM A500 / AISC | square HSS (inch) | ``SquareTube`` |
| ``EN10056_ANGLE`` | EN 10056-1 | equal angle | ``Angle`` |
| ``UPN`` | DIN 1026-1 | taper-flange channel (as parallel) | ``Channel`` |
| ``IPE`` | EN 10365 | I beam | ``IBeam`` |
| ``HEA`` | EN 10365 | wide-flange H beam | ``IBeam`` |
| ``AISC_W`` | ASTM A6 / AISC | W shape (inch) | ``IBeam`` |
| ``EN10058_FLAT`` | EN 10058 | flat bar | ``RectBar`` |
| ``EN10060_ROUND`` | EN 10060 | round bar | ``RoundBar`` |

Simplifications (the same as the profiles): sharp tube corners, no root
fillets, UPN flanges drawn parallel at their nominal thickness. Weights
computed from these sections are therefore within a few percent of the
catalogue values, a little high for tubes and a little low for beams.
"""

from __future__ import annotations

from typing import Callable

from .profiles import (
    INCH,
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

# --------------------------------------------------------------------------- #
# Hollow sections
# --------------------------------------------------------------------------- #

# EN 10219-2 cold-formed square hollow sections: size (mm), wall (mm).
EN10219_SHS: dict[str, dict[str, float]] = {
    f"{s:g}x{s:g}x{t:g}": {"size": s, "wall": t}
    for s, t in (
        (20, 2),
        (25, 2),
        (25, 2.5),
        (30, 2),
        (30, 3),
        (40, 2),
        (40, 3),
        (40, 4),
        (50, 3),
        (50, 4),
        (60, 3),
        (60, 4),
        (70, 4),
        (80, 4),
        (80, 5),
        (100, 4),
        (100, 5),
        (100, 6),
        (120, 5),
        (120, 6),
        (150, 6),
        (150, 8),
        (200, 8),
        (200, 10),
    )
}

# EN 10219-2 rectangular hollow sections: width (u) x height (v) x wall.
EN10219_RHS: dict[str, dict[str, float]] = {
    f"{h:g}x{w:g}x{t:g}": {"width": w, "height": h, "wall": t}
    for h, w, t in (
        (40, 20, 2),
        (50, 25, 2),
        (50, 30, 3),
        (60, 30, 3),
        (60, 40, 3),
        (80, 40, 3),
        (80, 40, 4),
        (100, 50, 3),
        (100, 50, 4),
        (100, 50, 5),
        (120, 60, 4),
        (120, 80, 5),
        (150, 100, 5),
        (160, 80, 5),
        (200, 100, 6),
    )
}

# EN 10219-2 circular hollow sections: outside diameter x wall.
EN10219_CHS: dict[str, dict[str, float]] = {
    f"{d:g}x{t:g}": {"diameter": d, "wall": t}
    for d, t in (
        (21.3, 2.0),
        (26.9, 2.0),
        (26.9, 2.6),
        (33.7, 2.6),
        (33.7, 3.2),
        (42.4, 2.6),
        (42.4, 3.2),
        (48.3, 3.2),
        (48.3, 4.0),
        (60.3, 3.2),
        (60.3, 4.0),
        (76.1, 3.2),
        (88.9, 4.0),
        (114.3, 4.0),
        (139.7, 5.0),
        (168.3, 5.0),
    )
}

# AISC design wall thickness of ASTM A500 (ERW) HSS = 0.93 x nominal.
A500_DESIGN_WALL_FACTOR = 0.93

# ASTM A500 square HSS: (size, nominal wall) in inches; dims stored in mm with
# the AISC design wall.
_A500 = (
    ("1", 1.0, "1/8", 0.125),
    ("1-1/2", 1.5, "1/8", 0.125),
    ("1-1/2", 1.5, "3/16", 0.1875),
    ("2", 2.0, "1/8", 0.125),
    ("2", 2.0, "3/16", 0.1875),
    ("2", 2.0, "1/4", 0.25),
    ("2-1/2", 2.5, "3/16", 0.1875),
    ("3", 3.0, "3/16", 0.1875),
    ("3", 3.0, "1/4", 0.25),
    ("4", 4.0, "1/4", 0.25),
    ("4", 4.0, "3/8", 0.375),
    ("6", 6.0, "1/4", 0.25),
    ("6", 6.0, "3/8", 0.375),
)
ASTM_A500_SQUARE: dict[str, dict[str, float]] = {
    f"HSS{n}x{n}x{tn}": {
        "size": round(s * INCH, 2),
        "wall": round(t * A500_DESIGN_WALL_FACTOR * INCH, 2),
    }
    for n, s, tn, t in _A500
}

# --------------------------------------------------------------------------- #
# Open sections
# --------------------------------------------------------------------------- #

# EN 10056-1 equal angles: leg x thickness.
EN10056_ANGLE: dict[str, dict[str, float]] = {
    f"L{a:g}x{a:g}x{t:g}": {"width": a, "height": a, "thickness": t}
    for a, t in (
        (20, 3),
        (25, 3),
        (30, 3),
        (40, 4),
        (50, 5),
        (60, 6),
        (70, 7),
        (80, 8),
        (100, 10),
    )
}

# DIN 1026-1 UPN channels: height h, flange width b, web tw, flange tf.
UPN: dict[str, dict[str, float]] = {
    f"UPN{h:g}": {"height": h, "width": b, "web": tw, "flange": tf}
    for h, b, tw, tf in (
        (50, 38, 5.0, 7.0),
        (65, 42, 5.5, 7.5),
        (80, 45, 6.0, 8.0),
        (100, 50, 6.0, 8.5),
        (120, 55, 7.0, 9.0),
        (140, 60, 7.0, 10.0),
        (160, 65, 7.5, 10.5),
        (180, 70, 8.0, 11.0),
        (200, 75, 8.5, 11.5),
    )
}

# EN 10365 IPE beams: height h, flange width b, web tw, flange tf.
IPE: dict[str, dict[str, float]] = {
    f"IPE{h:g}": {"height": h, "width": b, "web": tw, "flange": tf}
    for h, b, tw, tf in (
        (80, 46, 3.8, 5.2),
        (100, 55, 4.1, 5.7),
        (120, 64, 4.4, 6.3),
        (140, 73, 4.7, 6.9),
        (160, 82, 5.0, 7.4),
        (180, 91, 5.3, 8.0),
        (200, 100, 5.6, 8.5),
        (220, 110, 5.9, 9.2),
        (240, 120, 6.2, 9.8),
        (270, 135, 6.6, 10.2),
        (300, 150, 7.1, 10.7),
    )
}

# EN 10365 HEA (wide-flange) beams: designation by nominal size.
HEA: dict[str, dict[str, float]] = {
    f"HEA{n}": {"height": h, "width": b, "web": tw, "flange": tf}
    for n, h, b, tw, tf in (
        (100, 96, 100, 5.0, 8.0),
        (120, 114, 120, 5.0, 8.0),
        (140, 133, 140, 5.5, 8.5),
        (160, 152, 160, 6.0, 9.0),
        (180, 171, 180, 6.0, 9.5),
        (200, 190, 200, 6.5, 10.0),
        (220, 210, 220, 7.0, 11.0),
        (240, 230, 240, 7.5, 12.0),
    )
}

# AISC W shapes (ASTM A992): d, bf, tw, tf in inches, stored in mm.
AISC_W: dict[str, dict[str, float]] = {
    name: {
        "height": round(d * INCH, 1),
        "width": round(bf * INCH, 1),
        "web": round(tw * INCH, 2),
        "flange": round(tf * INCH, 2),
    }
    for name, d, bf, tw, tf in (
        ("W4x13", 4.16, 4.06, 0.280, 0.345),
        ("W6x9", 5.90, 3.94, 0.170, 0.215),
        ("W6x15", 5.99, 5.99, 0.230, 0.260),
        ("W8x10", 7.89, 3.94, 0.170, 0.205),
        ("W8x18", 8.14, 5.25, 0.230, 0.330),
        ("W8x31", 8.00, 8.00, 0.285, 0.435),
        ("W10x12", 9.87, 3.96, 0.190, 0.210),
        ("W10x22", 10.2, 5.75, 0.240, 0.360),
        ("W12x26", 12.2, 6.49, 0.230, 0.380),
    )
}

# EN 10058 hot-rolled flat bar: width (u) x thickness (v).
EN10058_FLAT: dict[str, dict[str, float]] = {
    f"{w:g}x{t:g}": {"width": w, "height": t}
    for w, t in (
        (20, 3),
        (20, 5),
        (25, 5),
        (30, 5),
        (40, 5),
        (40, 8),
        (50, 5),
        (50, 10),
        (60, 8),
        (80, 10),
        (100, 10),
    )
}

# EN 10060 hot-rolled round bar: diameter.
EN10060_ROUND: dict[str, dict[str, float]] = {
    f"{d:g}": {"diameter": d} for d in (6, 8, 10, 12, 16, 20, 25, 30, 40)
}

# Dimensional lumber (nominal -> actual dressed size), as a table.
LUMBER: dict[str, dict[str, str]] = {k: {"nominal": k} for k in LUMBER_SIZES_IN}

# --------------------------------------------------------------------------- #
# Lookup
# --------------------------------------------------------------------------- #

# family -> (table, standard, profile factory)
FAMILIES: dict[str, tuple[dict, str, Callable[..., Profile]]] = {
    "SHS": (EN10219_SHS, "EN 10219-2", lambda size, wall: SquareTube(size, wall)),
    "RHS": (EN10219_RHS, "EN 10219-2", RectTube),
    "CHS": (EN10219_CHS, "EN 10219-2", RoundTube),
    "HSS": (
        ASTM_A500_SQUARE,
        "ASTM A500",
        lambda size, wall: SquareTube(size, wall),
    ),
    "L": (EN10056_ANGLE, "EN 10056-1", Angle),
    "UPN": (UPN, "DIN 1026-1", Channel),
    "IPE": (IPE, "EN 10365", IBeam),
    "HEA": (HEA, "EN 10365", IBeam),
    "W": (AISC_W, "ASTM A6", IBeam),
    "FL": (EN10058_FLAT, "EN 10058", RectBar),
    "RD": (EN10060_ROUND, "EN 10060", RoundBar),
    "LUMBER": (LUMBER, "dimensional lumber", Lumber),
}


class UnknownSectionError(ValueError):
    """A family or size that is not in the standard tables."""


def standard_profile(family: str, size: str) -> Profile:
    """A profile from the standard tables: ``standard_profile("SHS",
    "40x40x3")``, ``standard_profile("IPE", "IPE200")``,
    ``standard_profile("W", "W8x18")``, ``standard_profile("LUMBER",
    "2x4")``. Raises ``UnknownSectionError`` listing the known sizes."""
    key = family.upper()
    if key not in FAMILIES:
        raise UnknownSectionError(
            f"unknown section family {family!r}; known: {', '.join(FAMILIES)}"
        )
    table, _, make = FAMILIES[key]
    if size not in table:
        raise UnknownSectionError(
            f"{family} {size!r} is not in the {key} table; known: "
            f"{', '.join(table)}"
        )
    profile = make(**table[size])
    return _designated(profile, key, size)


def _designated(profile: Profile, family: str, size: str) -> Profile:
    """Keep the standard designation (``IPE200``, ``W8x18``) on the profile so
    cut lists name the stock the way it is ordered."""
    names = {
        "IPE": size,
        "HEA": size,
        "W": size,
        "UPN": size,
        "HSS": size,
        "L": size,
    }
    if family in names:
        object.__setattr__(profile, "_designation", names[family])
    return profile


def profile_from_designation(designation: str) -> Profile:
    """Parse a designation the way stock is ordered: ``"SHS 40x40x3"``,
    ``"RHS 80x40x3"``, ``"CHS 48.3x3.2"``, ``"IPE200"``, ``"HEA160"``,
    ``"UPN100"``, ``"W8x18"``, ``"HSS2x2x1/8"``, ``"L50x50x5"``,
    ``"FL 50x10"``, ``"RD 20"``, ``"Lumber 2x4"``."""
    text = designation.strip()
    for family, (table, _, _) in FAMILIES.items():
        if text in table and family in ("IPE", "HEA", "UPN", "W", "HSS", "L"):
            return standard_profile(family, text)
    head, _, rest = text.partition(" ")
    if rest and head.upper() in FAMILIES:
        return standard_profile(head.upper(), rest.strip())
    raise UnknownSectionError(
        f"cannot read section designation {designation!r}; write it as "
        "'SHS 40x40x3', 'RHS 80x40x3', 'CHS 48.3x3.2', 'IPE200', 'HEA160', "
        "'UPN100', 'W8x18', 'HSS2x2x1/8', 'L50x50x5', 'FL 50x10', 'RD 20' or "
        "'Lumber 2x4'"
    )

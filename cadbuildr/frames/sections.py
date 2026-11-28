"""Rolled-section outlines with their real radii, and section properties.

Hot-rolled angles and channels are not sharp polygons: EN 10056-1 angles
have a root radius ``r1`` (inside the heel) and a toe radius ``r2`` (the
inner edge of each leg tip); channels have a root radius between web and
flanges (BS EN 10365 parallel-flange channels) plus a toe radius and an 8 %
flange taper (DIN 1026-1 UPN); EN 10219-2 cold-formed hollow sections have
an outer corner radius ``r_o`` and an inner radius ``r_i``. This module
draws those outlines as ONE ``CompactPolygon`` per loop (straight edges +
true circular arcs, foundation's compact geometry) and computes the
section properties the cut list, weights and the load check use.

- :func:`rounded_polygon` — fillet the corners of a polygon: returns
  ``(x, y, bulge)`` vertices (bulge = tan(sweep / 4), + = counter-clockwise).
- :func:`outline_points` — the same outline densified into points (for
  weld lengths, supports, properties).
- :class:`SectionProperties` / :func:`section_properties` — area, centroid,
  second moments ``I_u`` / ``I_v`` about the centroidal axes parallel to the
  profile's u / v, elastic moduli, by Green's theorem over the densified
  outline (exact for the polygon; arcs are sampled at 64 segments per
  quarter turn, so the error is < 0.01 %).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Sequence

from cadbuildr.foundation import CompactPolygon, Sketch

Point2 = tuple[float, float]
BulgePoint = tuple[float, float, float]

# Arc densification: segments per 90 degrees of sweep.
ARC_SEGMENTS_PER_QUARTER = 64


class SectionGeometryError(ValueError):
    """A radius that does not fit the section (fillets overlap an edge)."""


def _unit2(x: float, y: float) -> Point2:
    n = math.hypot(x, y)
    return (x / n, y / n)


def rounded_polygon(
    points: Sequence[Point2], radii: Sequence[float]
) -> list[BulgePoint]:
    """Fillet the corners of the counter-clockwise polygon ``points`` with
    ``radii`` (one per vertex, 0 = sharp). Returns ``(x, y, bulge)``
    vertices for ``CompactPolygon.from_points``: each filleted corner turns
    into its two tangent points, the edge between them an arc.

    Convex corners get a counter-clockwise arc (bulge > 0), concave ones
    (root fillets) a clockwise arc. Raises :class:`SectionGeometryError`
    when two fillets need more than the edge between them."""
    n = len(points)
    if len(radii) != n:
        raise SectionGeometryError(
            f"rounded_polygon: {len(radii)} radii for {n} vertices"
        )
    corners = []
    for i in range(n):
        px, py = points[i]
        ax, ay = points[i - 1]
        bx, by = points[(i + 1) % n]
        r = float(radii[i])
        if r <= 0:
            corners.append(None)
            continue
        d1 = _unit2(ax - px, ay - py)
        d2 = _unit2(bx - px, by - py)
        gamma = math.acos(max(-1.0, min(1.0, d1[0] * d2[0] + d1[1] * d2[1])))
        t = r / math.tan(gamma / 2.0)
        turn = (px - ax) * (by - py) - (py - ay) * (bx - px)
        sweep = math.pi - gamma
        bulge = math.tan(sweep / 4.0) * (1.0 if turn > 0 else -1.0)
        corners.append((t, d1, d2, bulge))
    for i in range(n):
        j = (i + 1) % n
        edge = math.dist(points[i], points[j])
        need = (corners[i][0] if corners[i] else 0.0) + (
            corners[j][0] if corners[j] else 0.0
        )
        if need > edge + 1e-9:
            raise SectionGeometryError(
                f"radii at vertices {i} and {j} need {need:.3f} mm of a "
                f"{edge:.3f} mm edge"
            )
    out: list[BulgePoint] = []
    for i, c in enumerate(corners):
        px, py = points[i]
        if c is None:
            out.append((px, py, 0.0))
            continue
        t, d1, d2, bulge = c
        out.append((px + d1[0] * t, py + d1[1] * t, bulge))
        out.append((px + d2[0] * t, py + d2[1] * t, 0.0))
    return out


def densify(loop: Sequence[BulgePoint]) -> list[Point2]:
    """Points along a bulge loop: vertices plus arc samples."""
    pts: list[Point2] = []
    n = len(loop)
    for i in range(n):
        ax, ay, b = loop[i]
        bx, by, _ = loop[(i + 1) % n]
        pts.append((ax, ay))
        if abs(b) < 1e-12:
            continue
        sweep = 4.0 * math.atan(b)  # signed, + = CCW
        chord = math.hypot(bx - ax, by - ay)
        radius = chord / (2.0 * math.sin(abs(sweep) / 2.0))
        # centre: on the left of a->b for a CCW arc
        mx, my = (ax + bx) / 2.0, (ay + by) / 2.0
        ux, uy = (bx - ax) / chord, (by - ay) / chord
        h = radius * math.cos(abs(sweep) / 2.0)
        side = 1.0 if sweep > 0 else -1.0
        cx, cy = mx - side * uy * h, my + side * ux * h
        a0 = math.atan2(ay - cy, ax - cx)
        steps = max(2, int(math.ceil(abs(sweep) / (math.pi / 2) * ARC_SEGMENTS_PER_QUARTER)))
        for k in range(1, steps):
            a = a0 + sweep * k / steps
            pts.append((cx + radius * math.cos(a), cy + radius * math.sin(a)))
    return pts


def circle_points(radius: float, n: int = 4 * ARC_SEGMENTS_PER_QUARTER) -> list[Point2]:
    return [
        (radius * math.cos(2 * math.pi * k / n), radius * math.sin(2 * math.pi * k / n))
        for k in range(n)
    ]


def draw_loop(sketch: Sketch, loop: Sequence[BulgePoint]) -> Any:
    """One ``CompactPolygon`` node for a bulge loop (sharp loops too)."""
    return CompactPolygon.from_points(sketch, [tuple(p) for p in loop])


# --------------------------------------------------------------------------- #
# Section properties
# --------------------------------------------------------------------------- #


def _green(pts: Sequence[Point2]) -> tuple[float, float, float, float, float]:
    """Signed area, first moments (Sx = int y, Sy = int x) and second
    moments about the origin (Iuu = int v^2 dA, Ivv = int u^2 dA) of a
    polygon (positive for counter-clockwise)."""
    a = sx = sy = iuu = ivv = 0.0
    n = len(pts)
    for i in range(n):
        x0, y0 = pts[i]
        x1, y1 = pts[(i + 1) % n]
        c = x0 * y1 - x1 * y0
        a += c
        sy += (x0 + x1) * c
        sx += (y0 + y1) * c
        iuu += (y0 * y0 + y0 * y1 + y1 * y1) * c
        ivv += (x0 * x0 + x0 * x1 + x1 * x1) * c
    return a / 2.0, sx / 6.0, sy / 6.0, iuu / 12.0, ivv / 12.0


@dataclass(frozen=True)
class SectionProperties:
    """Cross-section properties in mm units (area mm^2, I mm^4, W mm^3).

    ``i_u`` is the second moment about the centroidal axis parallel to the
    profile's u axis (bending that deflects along v — the strong axis of an
    I beam drawn with its web along v); ``w_u`` = ``i_u`` / the extreme
    fibre distance along v (elastic modulus). Likewise ``i_v`` / ``w_v``."""

    area: float
    centroid: Point2
    i_u: float
    i_v: float
    w_u: float
    w_v: float

    @property
    def area_cm2(self) -> float:
        return self.area / 100.0

    @property
    def i_u_cm4(self) -> float:
        return self.i_u / 1e4

    @property
    def w_u_cm3(self) -> float:
        return self.w_u / 1e3


def polygon_properties(
    outer: Sequence[Point2], inner: Sequence[Point2] | None = None
) -> SectionProperties:
    """Properties of the region inside ``outer`` and outside ``inner``
    (each loop in either orientation)."""
    loops = [(outer, 1.0)] + ([(inner, -1.0)] if inner else [])
    a = sx = sy = iuu = ivv = 0.0
    for pts, sign in loops:
        la, lsx, lsy, liuu, livv = _green(pts)
        k = sign * (1.0 if la > 0 else -1.0)
        a += k * la
        sx += k * lsx
        sy += k * lsy
        iuu += k * liuu
        ivv += k * livv
    cu, cv = sy / a, sx / a
    i_u = iuu - a * cv * cv
    i_v = ivv - a * cu * cu
    vs = [p[1] for p in outer]
    us = [p[0] for p in outer]
    c_v = max(max(vs) - cv, cv - min(vs))
    c_u = max(max(us) - cu, cu - min(us))
    return SectionProperties(a, (cu, cv), i_u, i_v, i_u / c_v, i_v / c_u)


def section_properties(profile: Any) -> SectionProperties:
    """Section properties of any frames profile (round sections exactly,
    polygons and rounded outlines by Green's theorem)."""
    from .profiles import RoundBar, RoundTube

    if isinstance(profile, (RoundTube, RoundBar)):
        d = profile.diameter
        di = d - 2 * profile.wall if isinstance(profile, RoundTube) else 0.0
        area = math.pi / 4 * (d * d - di * di)
        i = math.pi / 64 * (d**4 - di**4)
        return SectionProperties(area, (0.0, 0.0), i, i, i / (d / 2), i / (d / 2))
    outer, inner = profile.outline()
    return polygon_properties(outer, inner)

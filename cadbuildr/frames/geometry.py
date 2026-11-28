"""Skeleton geometry: 3D line / arc segments and the small vector maths the
frame layout needs.

Everything is in millimetres, in the frame assembly's coordinates.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable, Sequence, Union

Vec = tuple[float, float, float]

# Two skeleton points closer than this (mm) are the same node.
NODE_TOLERANCE = 1e-6


def vec(p: Sequence[float]) -> Vec:
    if len(p) != 3:
        raise ValueError(f"expected a 3D point (x, y, z), got {p!r}")
    return (float(p[0]), float(p[1]), float(p[2]))


def add(a: Vec, b: Vec) -> Vec:
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def sub(a: Vec, b: Vec) -> Vec:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def scale(a: Vec, k: float) -> Vec:
    return (a[0] * k, a[1] * k, a[2] * k)


def dot(a: Vec, b: Vec) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def cross(a: Vec, b: Vec) -> Vec:
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def norm(a: Vec) -> float:
    return math.sqrt(dot(a, a))


def unit(a: Vec) -> Vec:
    n = norm(a)
    if n < 1e-12:
        raise ValueError("cannot normalise a zero-length vector")
    return scale(a, 1.0 / n)


def rotate(v: Vec, axis: Vec, angle: float) -> Vec:
    """Rodrigues rotation of ``v`` about unit ``axis`` by ``angle`` radians."""
    c, s = math.cos(angle), math.sin(angle)
    return add(
        add(scale(v, c), scale(cross(axis, v), s)),
        scale(axis, dot(axis, v) * (1.0 - c)),
    )


# A member's orientation: the world directions of its local x (along the
# member), y and z (the profile's u and v axes).
Basis = tuple[Vec, Vec, Vec]


def basis_from_up(x: Vec, up: Vec, fallback_up: Vec) -> Basis:
    """Right-handed basis with ``x`` along the member and ``z`` as close to
    ``up`` as possible (``fallback_up`` when the member is parallel to up)."""
    x = unit(x)
    z = sub(up, scale(x, dot(up, x)))
    if norm(z) < 1e-9:
        z = sub(fallback_up, scale(x, dot(fallback_up, x)))
    z = unit(z)
    y = cross(z, x)
    return (x, y, z)


def to_local(basis: Basis, v: Vec) -> Vec:
    return (dot(v, basis[0]), dot(v, basis[1]), dot(v, basis[2]))


@dataclass(frozen=True)
class Line3D:
    """A straight skeleton segment from ``start`` to ``end``."""

    start: Vec
    end: Vec

    def __init__(self, start: Sequence[float], end: Sequence[float]):
        object.__setattr__(self, "start", vec(start))
        object.__setattr__(self, "end", vec(end))
        if self.length < NODE_TOLERANCE:
            raise ValueError(f"Line3D has zero length: {start} -> {end}")

    @property
    def length(self) -> float:
        return norm(sub(self.end, self.start))

    @property
    def start_tangent(self) -> Vec:
        return unit(sub(self.end, self.start))

    @property
    def end_tangent(self) -> Vec:
        return self.start_tangent

    def points(self) -> list[Vec]:
        return [self.start, self.end]

    def end_basis(self, start_basis: Basis) -> Basis:
        return start_basis

    def contains_interior(self, p: Vec, tol: float) -> float | None:
        """Distance along the line from ``start`` when ``p`` lies strictly
        inside the segment (not at an end), else ``None``."""
        d = self.start_tangent
        s = dot(sub(p, self.start), d)
        if s <= tol or s >= self.length - tol:
            return None
        off = sub(sub(p, self.start), scale(d, s))
        return s if norm(off) <= tol else None


@dataclass(frozen=True)
class Arc3D:
    """A circular skeleton segment from ``start`` through ``through`` to ``end``
    (the three points must not be collinear)."""

    start: Vec
    through: Vec
    end: Vec

    def __init__(
        self,
        start: Sequence[float],
        through: Sequence[float],
        end: Sequence[float],
    ):
        object.__setattr__(self, "start", vec(start))
        object.__setattr__(self, "through", vec(through))
        object.__setattr__(self, "end", vec(end))
        u, v = sub(self.through, self.start), sub(self.end, self.start)
        if norm(cross(u, v)) < 1e-9 * max(1.0, dot(u, u), dot(v, v)):
            raise ValueError("Arc3D points are collinear; use Line3D")

    @property
    def normal(self) -> Vec:
        """Arc axis; the arc runs counter-clockwise about it."""
        return unit(cross(sub(self.through, self.start), sub(self.end, self.start)))

    @property
    def center(self) -> Vec:
        a, b = sub(self.through, self.start), sub(self.end, self.start)
        w = cross(a, b)
        num = cross(sub(scale(b, dot(a, a)), scale(a, dot(b, b))), w)
        return add(self.start, scale(num, 1.0 / (2.0 * dot(w, w))))

    @property
    def radius(self) -> float:
        return norm(sub(self.start, self.center))

    @property
    def sweep(self) -> float:
        """Swept angle in radians, in (0, 2*pi)."""
        c, k = self.center, self.normal
        ra, rc = sub(self.start, c), sub(self.end, c)
        ang = math.atan2(dot(k, cross(ra, rc)), dot(ra, rc))
        return ang if ang > 0 else ang + 2.0 * math.pi

    @property
    def length(self) -> float:
        return self.radius * self.sweep

    @property
    def start_tangent(self) -> Vec:
        return unit(cross(self.normal, sub(self.start, self.center)))

    @property
    def end_tangent(self) -> Vec:
        return unit(cross(self.normal, sub(self.end, self.center)))

    def points(self) -> list[Vec]:
        return [self.start, self.through, self.end]

    def end_basis(self, start_basis: Basis) -> Basis:
        """The profile frame carried along the bend to the arc's end."""
        k, a = self.normal, self.sweep
        return tuple(rotate(axis, k, a) for axis in start_basis)  # type: ignore[return-value]

    def contains_interior(self, p: Vec, tol: float) -> float | None:
        return None  # T-junctions onto a curved member are not supported


Segment = Union[Line3D, Arc3D]


def polyline(points: Iterable[Sequence[float]], closed: bool = False) -> list[Line3D]:
    """Straight segments through ``points`` (and back to the first one when
    ``closed``)."""
    pts = [vec(p) for p in points]
    if len(pts) < 2:
        raise ValueError("polyline needs at least two points")
    if closed:
        pts.append(pts[0])
    return [Line3D(a, b) for a, b in zip(pts, pts[1:])]


def rectangle(
    width: float,
    depth: float,
    center: Sequence[float] = (0.0, 0.0, 0.0),
) -> list[Line3D]:
    """Closed rectangular skeleton in the XY plane: ``width`` along X,
    ``depth`` along Y, centred on ``center`` (counter-clockwise from the
    -X/-Y corner)."""
    cx, cy, cz = vec(center)
    w, d = width / 2.0, depth / 2.0
    return polyline(
        [
            (cx - w, cy - d, cz),
            (cx + w, cy - d, cz),
            (cx + w, cy + d, cz),
            (cx - w, cy + d, cz),
        ],
        closed=True,
    )


def box_edges(
    width: float,
    depth: float,
    height: float,
    center: Sequence[float] = (0.0, 0.0, 0.0),
) -> list[Line3D]:
    """The 12 edges of a box (e.g. a cube or table frame): 4 bottom rails,
    4 top rails, then the 4 vertical posts. ``center`` is the centre of the
    bottom face."""
    cx, cy, cz = vec(center)
    bottom = rectangle(width, depth, (cx, cy, cz))
    top = rectangle(width, depth, (cx, cy, cz + height))
    posts = [Line3D(seg.start, add(seg.start, (0.0, 0.0, height))) for seg in bottom]
    return bottom + top + posts


def offset_skeleton(segments: Iterable[Segment], by: Sequence[float]) -> list[Segment]:
    """The skeleton moved by ``by`` = ``(dx, dy, dz)`` mm: lay a frame out
    where it belongs instead of transforming the built assembly."""
    d = vec(by)
    out: list[Segment] = []
    for s in segments:
        if isinstance(s, Arc3D):
            out.append(Arc3D(add(s.start, d), add(s.through, d), add(s.end, d)))
        else:
            out.append(Line3D(add(s.start, d), add(s.end, d)))
    return out


def skeleton_normal(segments: Sequence[Segment]) -> Vec | None:
    """Normal of the skeleton's plane (pointing to +Z where possible), or
    ``None`` when the skeleton is not planar."""
    pts = [p for s in segments for p in s.points()]
    origin = pts[0]
    n: Vec | None = None
    for p in pts[1:]:
        for q in pts[1:]:
            c = cross(sub(p, origin), sub(q, origin))
            if norm(c) > 1e-6:
                n = unit(c)
                break
        if n is not None:
            break
    if n is None:
        return None  # all collinear: no unique plane
    span = max(norm(sub(p, origin)) for p in pts)
    if any(abs(dot(sub(p, origin), n)) > 1e-6 * max(1.0, span) for p in pts):
        return None
    for axis in range(3):
        comp = n[2 - axis]  # prefer +Z, then +Y, then +X
        if abs(comp) > 1e-9:
            return n if comp > 0 else scale(n, -1.0)
    return n

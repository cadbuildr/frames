"""Standard cross-sections a frame member is swept with.

A profile is drawn in its member's cross-section plane: ``u`` runs along the
member's local y, ``v`` along its local z (the frame's ``up`` side). Every
profile is centred on the skeleton line at the centre of its bounding box.
Dimensions are millimetres.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from cadbuildr.foundation import Circle, Point, Sketch

INCH = 25.4


class Profile:
    """Base class: an outer outline and an optional inner (hollow) outline."""

    designation: str

    def outer(self, sketch: Sketch) -> Any:
        raise NotImplementedError

    def inner(self, sketch: Sketch) -> Any | None:
        return None

    def support(self, du: float, dv: float) -> float:
        """Largest ``u*du + v*dv`` over the outline: how far the profile
        reaches in the cross-section direction ``(du, dv)``."""
        raise NotImplementedError

    @property
    def size(self) -> tuple[float, float]:
        """Bounding box ``(u extent, v extent)``."""
        return (
            self.support(1.0, 0.0) + self.support(-1.0, 0.0),
            self.support(0.0, 1.0) + self.support(0.0, -1.0),
        )

    def __str__(self) -> str:
        return self.designation


def _polygon(sketch: Sketch, pts: list[tuple[float, float]]) -> Any:
    pencil = sketch.pencil
    pencil.move_to(*pts[0])
    for p in pts[1:]:
        pencil.line_to(*p)
    return pencil.close()


class PolygonProfile(Profile):
    """A profile whose outline is a polygon (and optional polygon hole)."""

    def outer_points(self) -> list[tuple[float, float]]:
        raise NotImplementedError

    def inner_points(self) -> list[tuple[float, float]] | None:
        return None

    def outer(self, sketch: Sketch) -> Any:
        return _polygon(sketch, self.outer_points())

    def inner(self, sketch: Sketch) -> Any | None:
        pts = self.inner_points()
        return _polygon(sketch, pts) if pts else None

    def support(self, du: float, dv: float) -> float:
        return max(u * du + v * dv for u, v in self.outer_points())


def _rect(w: float, h: float) -> list[tuple[float, float]]:
    return [(-w / 2, -h / 2), (w / 2, -h / 2), (w / 2, h / 2), (-w / 2, h / 2)]


def _positive(**dims: float) -> None:
    for name, value in dims.items():
        if not value > 0:
            raise ValueError(f"{name} must be > 0, got {value}")


@dataclass(frozen=True, repr=False)
class RectTube(PolygonProfile):
    """Rectangular hollow section ``width`` (u) x ``height`` (v), wall ``wall``.
    Corners are sharp (no outer radius) — a simplification of rolled tube."""

    width: float
    height: float
    wall: float

    def __post_init__(self) -> None:
        _positive(width=self.width, height=self.height, wall=self.wall)
        if 2 * self.wall >= min(self.width, self.height):
            raise ValueError("RectTube wall is too thick for its size")

    @property
    def designation(self) -> str:  # type: ignore[override]
        return f"RHS {self.width:g}x{self.height:g}x{self.wall:g}"

    def outer_points(self):
        return _rect(self.width, self.height)

    def inner_points(self):
        return _rect(self.width - 2 * self.wall, self.height - 2 * self.wall)


class SquareTube(RectTube):
    """Square hollow section ``size`` x ``size``, wall ``wall``."""

    def __init__(self, size: float, wall: float):
        super().__init__(size, size, wall)

    @property
    def designation(self) -> str:  # type: ignore[override]
        return f"SHS {self.width:g}x{self.width:g}x{self.wall:g}"


@dataclass(frozen=True, repr=False)
class RoundTube(Profile):
    """Circular hollow section of outside ``diameter`` and ``wall``."""

    diameter: float
    wall: float

    def __post_init__(self) -> None:
        _positive(diameter=self.diameter, wall=self.wall)
        if 2 * self.wall >= self.diameter:
            raise ValueError("RoundTube wall is too thick for its diameter")

    @property
    def designation(self) -> str:  # type: ignore[override]
        return f"CHS {self.diameter:g}x{self.wall:g}"

    def outer(self, sketch: Sketch) -> Any:
        return Circle(Point(sketch, 0.0, 0.0), self.diameter / 2)

    def inner(self, sketch: Sketch) -> Any:
        return Circle(Point(sketch, 0.0, 0.0), self.diameter / 2 - self.wall)

    def support(self, du: float, dv: float) -> float:
        return self.diameter / 2 * math.hypot(du, dv)


@dataclass(frozen=True, repr=False)
class RoundBar(Profile):
    """Solid round bar of ``diameter``."""

    diameter: float

    def __post_init__(self) -> None:
        _positive(diameter=self.diameter)

    @property
    def designation(self) -> str:  # type: ignore[override]
        return f"Round bar {self.diameter:g}"

    def outer(self, sketch: Sketch) -> Any:
        return Circle(Point(sketch, 0.0, 0.0), self.diameter / 2)

    def support(self, du: float, dv: float) -> float:
        return self.diameter / 2 * math.hypot(du, dv)


@dataclass(frozen=True, repr=False)
class RectBar(PolygonProfile):
    """Solid rectangular bar / flat bar ``width`` (u) x ``height`` (v)."""

    width: float
    height: float

    def __post_init__(self) -> None:
        _positive(width=self.width, height=self.height)

    @property
    def designation(self) -> str:  # type: ignore[override]
        return f"Flat bar {self.width:g}x{self.height:g}"

    def outer_points(self):
        return _rect(self.width, self.height)


@dataclass(frozen=True, repr=False)
class Angle(PolygonProfile):
    """Equal or unequal angle (L section): legs ``width`` (u) and ``height``
    (v), ``thickness``. The heel is at the -u/-v corner of the bounding box."""

    width: float
    height: float
    thickness: float

    def __post_init__(self) -> None:
        _positive(width=self.width, height=self.height, thickness=self.thickness)
        if self.thickness >= min(self.width, self.height):
            raise ValueError("Angle thickness must be smaller than its legs")

    @property
    def designation(self) -> str:  # type: ignore[override]
        return f"L {self.width:g}x{self.height:g}x{self.thickness:g}"

    def outer_points(self):
        w, h, t = self.width / 2, self.height / 2, self.thickness
        return [(-w, -h), (w, -h), (w, -h + t), (-w + t, -h + t), (-w + t, h), (-w, h)]


@dataclass(frozen=True, repr=False)
class Channel(PolygonProfile):
    """C / U channel: ``height`` (v, web depth) x ``width`` (u, flange
    width), web thickness ``web``, flange thickness ``flange``. The web is at
    -u, the flanges open towards +u."""

    height: float
    width: float
    web: float
    flange: float

    def __post_init__(self) -> None:
        _positive(
            height=self.height, width=self.width, web=self.web, flange=self.flange
        )
        if self.web >= self.width or 2 * self.flange >= self.height:
            raise ValueError("Channel web/flange too thick for its size")

    @property
    def designation(self) -> str:  # type: ignore[override]
        return f"C {self.height:g}x{self.width:g}x{self.web:g}/{self.flange:g}"

    def outer_points(self):
        w, h, tw, tf = self.width / 2, self.height / 2, self.web, self.flange
        return [
            (-w, -h),
            (w, -h),
            (w, -h + tf),
            (-w + tw, -h + tf),
            (-w + tw, h - tf),
            (w, h - tf),
            (w, h),
            (-w, h),
        ]


@dataclass(frozen=True, repr=False)
class IBeam(PolygonProfile):
    """I / H beam: ``height`` (v) x flange ``width`` (u), ``web`` and
    ``flange`` thicknesses (no root fillets)."""

    height: float
    width: float
    web: float
    flange: float

    def __post_init__(self) -> None:
        _positive(
            height=self.height, width=self.width, web=self.web, flange=self.flange
        )
        if self.web >= self.width or 2 * self.flange >= self.height:
            raise ValueError("IBeam web/flange too thick for its size")

    @property
    def designation(self) -> str:  # type: ignore[override]
        return f"I {self.height:g}x{self.width:g}x{self.web:g}/{self.flange:g}"

    def outer_points(self):
        w, h, tw, tf = self.width / 2, self.height / 2, self.web / 2, self.flange
        return [
            (-w, -h),
            (w, -h),
            (w, -h + tf),
            (tw, -h + tf),
            (tw, h - tf),
            (w, h - tf),
            (w, h),
            (-w, h),
            (-w, h - tf),
            (-tw, h - tf),
            (-tw, -h + tf),
            (-w, -h + tf),
        ]


# Actual (dressed) sizes of North American dimensional lumber, in inches
# (thickness, depth) — same table as cadbuildr.wood.standards.
LUMBER_SIZES_IN: dict[str, tuple[float, float]] = {
    "1x2": (0.75, 1.5),
    "1x4": (0.75, 3.5),
    "1x6": (0.75, 5.5),
    "2x2": (1.5, 1.5),
    "2x3": (1.5, 2.5),
    "2x4": (1.5, 3.5),
    "2x6": (1.5, 5.5),
    "2x8": (1.5, 7.25),
    "2x10": (1.5, 9.25),
    "2x12": (1.5, 11.25),
    "4x4": (3.5, 3.5),
    "6x6": (5.5, 5.5),
}


class Lumber(RectBar):
    """Dimensional lumber by nominal size (``"2x4"``…): the actual dressed
    thickness runs along u, the depth along v (on edge, towards ``up``)."""

    def __init__(self, nominal: str):
        key = nominal.lower().replace(" ", "")
        if key not in LUMBER_SIZES_IN:
            raise ValueError(
                f"unknown lumber size {nominal!r}; known: {', '.join(LUMBER_SIZES_IN)}"
            )
        t, d = LUMBER_SIZES_IN[key]
        super().__init__(t * INCH, d * INCH)
        object.__setattr__(self, "nominal", key)

    @property
    def designation(self) -> str:  # type: ignore[override]
        return f"Lumber {self.nominal}"  # type: ignore[attr-defined]

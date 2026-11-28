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
    """Base class: an outer outline and an optional inner (hollow) outline.

    ``designation`` names the stock the way it is ordered (``SHS 40x40x3``,
    ``IPE200``); ``area`` is the cross-section area in mm^2 and
    ``mass_per_m(density)`` the weight in kg/m.
    """

    @property
    def designation(self) -> str:
        """The stock designation (a standard name when the profile came
        from :func:`~cadbuildr.frames.standards.standard_profile`)."""
        named = self.__dict__.get("_designation")
        return named if named else self._default_designation()

    def _default_designation(self) -> str:
        return type(self).__name__

    @property
    def area(self) -> float:
        """Cross-section area in mm^2."""
        raise NotImplementedError(
            f"{type(self).__name__} does not define its cross-section area"
        )

    @property
    def outer_area(self) -> float:
        """Area inside the outer outline in mm^2 (an end cap's size)."""
        raise NotImplementedError(
            f"{type(self).__name__} does not define its outer outline area"
        )

    def mass_per_m(self, density: float = 7850.0) -> float:
        """Weight in kg per metre of length for a material ``density`` in
        kg/m^3 (steel 7850, aluminium 2700, softwood ~500). A profile with a
        catalog weight (``weight_per_m``) returns that instead."""
        catalog = getattr(self, "weight_per_m", None)
        if catalog is not None:
            return float(catalog)
        return self.area * 1e-6 * density

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

    @property
    def outer_area(self) -> float:
        return _shoelace(self.outer_points())

    @property
    def area(self) -> float:
        inner = self.inner_points()
        return _shoelace(self.outer_points()) - (_shoelace(inner) if inner else 0.0)


def _shoelace(pts: list[tuple[float, float]]) -> float:
    n = len(pts)
    return abs(
        sum(
            pts[i][0] * pts[(i + 1) % n][1] - pts[(i + 1) % n][0] * pts[i][1]
            for i in range(n)
        )
        / 2.0
    )


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

    def _default_designation(self) -> str:
        return f"RHS {self.width:g}x{self.height:g}x{self.wall:g}"

    def outer_points(self):
        return _rect(self.width, self.height)

    def inner_points(self):
        return _rect(self.width - 2 * self.wall, self.height - 2 * self.wall)


class SquareTube(RectTube):
    """Square hollow section ``size`` x ``size``, wall ``wall``."""

    def __init__(self, size: float, wall: float):
        super().__init__(size, size, wall)

    def _default_designation(self) -> str:
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

    def _default_designation(self) -> str:
        return f"CHS {self.diameter:g}x{self.wall:g}"

    def outer(self, sketch: Sketch) -> Any:
        return Circle(Point(sketch, 0.0, 0.0), self.diameter / 2)

    def inner(self, sketch: Sketch) -> Any:
        return Circle(Point(sketch, 0.0, 0.0), self.diameter / 2 - self.wall)

    @property
    def outer_area(self) -> float:
        return math.pi / 4 * self.diameter**2

    @property
    def area(self) -> float:
        d_in = self.diameter - 2 * self.wall
        return math.pi / 4 * (self.diameter**2 - d_in**2)

    def support(self, du: float, dv: float) -> float:
        return self.diameter / 2 * math.hypot(du, dv)


@dataclass(frozen=True, repr=False)
class RoundBar(Profile):
    """Solid round bar of ``diameter``."""

    diameter: float

    def __post_init__(self) -> None:
        _positive(diameter=self.diameter)

    def _default_designation(self) -> str:
        return f"Round bar {self.diameter:g}"

    def outer(self, sketch: Sketch) -> Any:
        return Circle(Point(sketch, 0.0, 0.0), self.diameter / 2)

    @property
    def area(self) -> float:
        return math.pi / 4 * self.diameter**2

    @property
    def outer_area(self) -> float:
        return self.area

    def support(self, du: float, dv: float) -> float:
        return self.diameter / 2 * math.hypot(du, dv)


@dataclass(frozen=True, repr=False)
class RectBar(PolygonProfile):
    """Solid rectangular bar / flat bar ``width`` (u) x ``height`` (v)."""

    width: float
    height: float

    def __post_init__(self) -> None:
        _positive(width=self.width, height=self.height)

    def _default_designation(self) -> str:
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

    def _default_designation(self) -> str:
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

    def _default_designation(self) -> str:
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

    def _default_designation(self) -> str:
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

    def _default_designation(self) -> str:
        return f"Lumber {self.nominal}"  # type: ignore[attr-defined]

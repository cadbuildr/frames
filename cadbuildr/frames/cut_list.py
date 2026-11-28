"""Cut list: frame members grouped into identical cut pieces."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import math

from .geometry import Arc3D, to_local
from .layout import MemberLayout
from .profiles import RoundBar, RoundTube

# Lengths / angles are grouped after rounding to these.
LENGTH_DECIMALS = 1
ANGLE_DECIMALS = 1


@dataclass(frozen=True)
class SawAngle:
    """Saw setting for one end: ``miter`` = blade turned from square about
    the profile's v axis (seen from the frame's up side), ``bevel`` = blade
    tilted from square about the profile's u axis, both in degrees. A plain
    90-degree corner miter is ``SawAngle(45, 0)``; a square cut ``(0, 0)``."""

    miter: float
    bevel: float = 0.0

    def __str__(self) -> str:
        if abs(self.bevel) < 0.05:
            return f"{self.miter:.1f}"
        return f"{self.miter:.1f}/{self.bevel:.1f}b"


def _round(p) -> bool:
    return isinstance(p, (RoundTube, RoundBar))


def end_saw_angle(
    m: MemberLayout, which: str, members: Sequence[MemberLayout] = ()
) -> SawAngle | None:
    """The saw setting of member end ``which``, or ``None`` when the end is
    not a saw cut (a saddle cope onto a round host: notcher / template)."""
    cut = m.cut(which)
    if cut.cope is not None:
        if _round(cut.cope.host):
            return None
        return SawAngle(round(90.0 - cut.cope.angle, 6), 0.0)
    if cut.cope_member is not None and members:
        if _round(members[cut.cope_member].profile):
            return None
    if not cut.needs_trim or cut.trim_normal is None:
        return SawAngle(0.0, 0.0)
    nx, ny, nz = to_local(m.frame_at(which), cut.trim_normal)
    n = math.sqrt(nx * nx + ny * ny + nz * nz)
    nx, ny, nz = abs(nx) / n, abs(ny) / n, abs(nz) / n
    miter = math.degrees(math.atan2(ny, nx))
    bevel = math.degrees(math.asin(min(1.0, nz)))
    return SawAngle(round(miter, 6), round(bevel, 6))


def end_prep_label(
    m: MemberLayout, which: str, members: Sequence[MemberLayout] = ()
) -> str:
    """What happens to an end beyond the saw cut: ``"cope onto CHS 48.3x3.2
    @ 90 deg"``, ``"bevel 30 deg / root face 1.5"`` or ``""``."""
    cut = m.cut(which)
    parts = []
    if cut.cope is not None:
        parts.append(cut.cope.label)
    elif cut.cope_member is not None and members:
        host = members[cut.cope_member]
        parts.append(f"cope onto {host.profile.designation}")
    if cut.bevel is not None:
        parts.append(cut.bevel.label)
    return ", ".join(parts)


@dataclass(frozen=True)
class CutListItem:
    """One cut-list row: ``count`` identical pieces of ``profile``.

    ``length`` is the overall (long-point to long-point) stock length in mm;
    ``end_angles`` the cut angle of each end from square, in degrees (0 =
    square, 45 = a 90-degree corner miter); ``end_cuts`` how each end is
    cut (``free``, ``miter``, ``butt``, ``through``, ``coped``,
    ``continuous``); ``bend_radius`` is set for bent (arc) members.
    """

    item: int
    profile: str
    length: float
    end_angles: tuple[float, float]
    end_cuts: tuple[str, str]
    count: int
    members: tuple[str, ...]
    bend_radius: float | None = None
    # saw setting per end (None = coped onto a round host, not a saw cut)
    saw_angles: tuple[SawAngle | None, SawAngle | None] = (None, None)
    # end preparation per end beyond the cut (cope / weld-prep bevel)
    end_preps: tuple[str, str] = ("", "")


def _saw_key(saw: SawAngle | None):
    if saw is None:
        return None
    return (round(saw.miter, ANGLE_DECIMALS), round(saw.bevel, ANGLE_DECIMALS))


def _row_key(m: MemberLayout, members: Sequence[MemberLayout]):
    ends = sorted(
        [
            (
                round(m.start.angle_deg, ANGLE_DECIMALS),
                m.start.kind,
                _saw_key(end_saw_angle(m, "start", members)) or (-1.0, -1.0),
                end_prep_label(m, "start", members),
            ),
            (
                round(m.end.angle_deg, ANGLE_DECIMALS),
                m.end.kind,
                _saw_key(end_saw_angle(m, "end", members)) or (-1.0, -1.0),
                end_prep_label(m, "end", members),
            ),
        ]
    )
    radius = (
        round(m.segment.radius, LENGTH_DECIMALS)
        if isinstance(m.segment, Arc3D)
        else None
    )
    return (
        m.profile.designation,
        round(m.cut_length, LENGTH_DECIMALS),
        tuple(ends),
        radius,
    )


def cut_list(members: Sequence[MemberLayout]) -> list[CutListItem]:
    groups: dict[tuple, list[MemberLayout]] = {}
    for m in members:
        groups.setdefault(_row_key(m, members), []).append(m)
    rows = []
    for i, (key, ms) in enumerate(groups.items()):
        designation, length, ends, radius = key

        def saw(e):
            return None if e[2] == (-1.0, -1.0) else SawAngle(*e[2])

        rows.append(
            CutListItem(
                item=i + 1,
                profile=designation,
                length=length,
                end_angles=(ends[0][0], ends[1][0]),
                end_cuts=(ends[0][1], ends[1][1]),
                count=len(ms),
                members=tuple(m.name for m in ms),
                bend_radius=radius,
                saw_angles=(saw(ends[0]), saw(ends[1])),
                end_preps=(ends[0][3], ends[1][3]),
            )
        )
    return rows


def format_cut_list(rows: Sequence[CutListItem]) -> str:
    header = (
        "Item",
        "Qty",
        "Profile",
        "Length",
        "Angle 1",
        "Angle 2",
        "Saw 1",
        "Saw 2",
        "Ends",
    )

    def saw(s: SawAngle | None) -> str:
        return "cope" if s is None else str(s)

    def ends(r: CutListItem) -> str:
        text = "/".join(r.end_cuts)
        preps = "; ".join(p for p in r.end_preps if p)
        return f"{text} ({preps})" if preps else text

    lines = [header] + [
        (
            str(r.item),
            str(r.count),
            r.profile + (f" (bent R{r.bend_radius:g})" if r.bend_radius else ""),
            f"{r.length:.1f}",
            f"{r.end_angles[0]:.1f}",
            f"{r.end_angles[1]:.1f}",
            saw(r.saw_angles[0]),
            saw(r.saw_angles[1]),
            ends(r),
        )
        for r in rows
    ]
    widths = [max(len(row[c]) for row in lines) for c in range(len(header))]
    out = [
        "  ".join(cell.ljust(w) for cell, w in zip(row, widths)).rstrip()
        for row in lines
    ]
    out.insert(1, "  ".join("-" * w for w in widths))
    return "\n".join(out)

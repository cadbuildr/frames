"""Cut list: frame members grouped into identical cut pieces."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from .geometry import Arc3D
from .layout import MemberLayout

# Lengths / angles are grouped after rounding to these.
LENGTH_DECIMALS = 1
ANGLE_DECIMALS = 1


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


def _row_key(m: MemberLayout):
    ends = sorted(
        [
            (round(m.start.angle_deg, ANGLE_DECIMALS), m.start.kind),
            (round(m.end.angle_deg, ANGLE_DECIMALS), m.end.kind),
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
        groups.setdefault(_row_key(m), []).append(m)
    rows = []
    for i, (key, ms) in enumerate(groups.items()):
        designation, length, ends, radius = key
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
            )
        )
    return rows


def format_cut_list(rows: Sequence[CutListItem]) -> str:
    header = ("Item", "Qty", "Profile", "Length", "Angle 1", "Angle 2", "Ends")
    lines = [header] + [
        (
            str(r.item),
            str(r.count),
            r.profile + (f" (bent R{r.bend_radius:g})" if r.bend_radius else ""),
            f"{r.length:.1f}",
            f"{r.end_angles[0]:.1f}",
            f"{r.end_angles[1]:.1f}",
            "/".join(r.end_cuts),
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

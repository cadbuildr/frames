# cadbuildr.frames

## Summary

Structural and woodworking frames (weldments) built on CADbuildr foundation —
the Onshape *Frame / Frame trim / Gusset / End cap / Cut list* features as a
library. A `Frame` sweeps a profile (square/rect/round tube, angle, channel,
I-beam, flat/round bar, dimensional lumber) along a skeleton of line and arc
segments, trims the corners (miter, butt "trim to", coped), adds gusset plates
and end caps, and reports a cut list. Every member is its own `Part` inside the
frame `Assembly`, so BOMs and exports see real cut pieces.

It composes plain foundation operations only — `Extrusion` along each segment,
`Lathe` for bent (arc) members, cut `Extrusion`s on trim planes for miters and
butts, and the through member's outline for copes — so it renders anywhere
foundation does (Prototype app, Hub, Playground, kernel-api). No schema nodes.

## Tags

cad, python, frames, weldments, structural, steel, tube, lumber, cut-list, assembly

## Status

yellow

## Guidelines

- Pure layout maths (`layout.py`) is separate from geometry (`frame.py`): the
  cut list is computed from the skeleton + profiles without a kernel, and the
  Parts are built from that same layout — one source of truth.
- Named defaults, no silent magic: `DEFAULT_UP` / `FALLBACK_UP` decide profile
  orientation, "longer member runs through" decides butt corners, and every
  rule is documented on `Frame` and below.
- Unsupported input fails loudly (`ValueError` naming the members): overlapping
  members, a coped member wider than its host, an arc that would need cutting
  back, a gusset on something that is not a two-member corner.
- Publish-first: depends on `cadbuildr-foundation` from PyPI only.

## Dependencies

### Upstream

- [cadbuildr-foundation](https://pypi.org/project/cadbuildr-foundation/) (PyPI)

### Downstream

- None yet (to be added to the curated-libraries registry once on PyPI).

## Usage

```python
from cadbuildr.foundation import show
from cadbuildr.frames import EndCap, Frame, Gusset, SquareTube, rectangle

# 600 x 400 mm rectangle (skeleton = tube centrelines), 40x40x3 square tube,
# mitered corners, a gusset in each corner.
frame = Frame(
    skeleton=rectangle(600, 400),
    profile=SquareTube(40, 3),
    corner="miter",
    gussets=[Gusset(at=(x, y, 0), size=60, thickness=4)
             for x in (-300, 300) for y in (-200, 200)],
)
print(frame.cut_list_table())
show(frame)
```

```text
Item  Qty  Profile         Length  Angle 1  Angle 2  Ends
----  ---  --------------  ------  -------  -------  -----------
1     2    SHS 40x40x3     640.0   45.0     45.0     miter/miter
2     2    SHS 40x40x3     440.0   45.0     45.0     miter/miter
```

The same rectangle with `corner="butt"`: the 600 rails run through (640 long,
square ends), the 400 sides are trimmed to their faces (360 long).

`frame.cut_list()` returns `CutListItem` rows: `profile`, `length` (overall,
long point to long point, mm), `end_angles` (degrees from square: 0 = square,
45 = corner miter), `end_cuts` (`free`, `miter`, `butt`, `through`, `coped`,
`continuous`), `count`, `members` (Part names) and `bend_radius` for arcs.

### Skeleton

- `Line3D(start, end)`, `Arc3D(start, through, end)` — segments in mm.
- Helpers: `rectangle(width, depth, center)` (closed, XY plane),
  `polyline(points, closed=False)`, `box_edges(width, depth, height)` (the 12
  edges of a box / table frame).
- Segments sharing an end point are joined. An end lying inside another
  straight member is a T-junction.

### Profiles

| Profile | Arguments |
|---|---|
| `SquareTube(size, wall)` | square hollow section |
| `RectTube(width, height, wall)` | rectangular hollow section |
| `RoundTube(diameter, wall)` | round tube |
| `RoundBar(diameter)`, `RectBar(width, height)` | solid bar / flat bar |
| `Angle(width, height, thickness)` | L section, heel at the -u/-v corner |
| `Channel(height, width, web, flange)` | C channel, web at -u |
| `IBeam(height, width, web, flange)` | I / H beam |
| `Lumber("2x4")` | dimensional lumber, actual dressed size (1.5" x 3.5") |

Profiles are centred on the skeleton at their bounding-box centre. `u` (the
first dimension) lies across the member in the frame's plane, `v` (the
second) points to the `up` side: for a planar skeleton `up` is its plane
normal (towards +Z), otherwise world +Z; members parallel to `up` (table
posts) use world +X. Pass `up=` to change it. Tube corners are sharp and
beams have no root fillets (a simplification).

### Corners and junctions

| Node | Treatment |
|---|---|
| free end | square cut (end caps go here) |
| two members, `corner="miter"` | both cut on the bisector plane |
| two members, `corner="butt"` | the longer member runs through (square end, extended over the other), the other is trimmed to its face; ties: the first segment runs through; an arc always runs through a line |
| two members, `corner="coped"` | as butt, but the trimmed member is cut to the through member's outer shape (round tube to round tube) |
| collinear / tangent ends | continuous, no cut |
| three or more members | the longest runs through, the others are butted (coped with `corner="coped"`) |
| T-junction | the end is butted (coped) onto the member it lands on |

### Gussets and end caps

- `Gusset(at=corner_point, size=60, thickness=5, position="center")` — a
  triangular plate in the corner with both legs `size` long from the members'
  inner corner. `position`: `"center"` (frame mid-plane), `"top"` / `"bottom"`
  (flush with that face). Only on two-member corners.
- `EndCap(thickness=3)` — a plate of the outer outline on every free end,
  added beyond the end (cut lengths are unchanged).

Members are `FrameMember` Parts named `member_1…` (skeleton order), plates
`gusset_N` / `end_cap_N`; `frame.members`, `frame.gussets`, `frame.end_caps`
list them.

### Connector hook (joint hardware)

`Frame(..., connector=...)` is the one extension point for joint hardware —
brackets, fasteners, end caps — that a library (e.g. `cadbuildr-tslot`)
places on the frame. It is called once per junction, after the layout is
solved and before any member is added, so it can also machine the members.

```python
from cadbuildr.frames import Connection, ConnectorRule, Placed, basis_transform

class PostsThrough(ConnectorRule):
    def choose_through(self, node, ends):          # optional
        return next((i for i, e in enumerate(ends) if abs(e.into[2]) > 0.99), None)

    def prepare_member(self, part):                # optional, once per member
        ...                                        # e.g. add slot anchors

    def connect(self, junction, layout):           # per junction
        if junction.kind == "free":
            return None
        end = junction.butting[0]
        return Connection(
            components=[Placed(MyBracket(), basis_transform(junction.node, end.basis))],
            machining=[(end, lambda part: part.add_operation(...))],
        )

Frame(box_edges(600, 400, 300), profile, corner="butt", connector=PostsThrough())
```

- A plain callable `connector(junction) -> Connection | None` works too.
- `Junction`: `kind` (`free`, `continuous`, `corner`, `tee`, `multi`),
  `node`, `through` (the member running through, `None` for free /
  continuous / mitered nodes), `butting` (the trimmed members), `ends`,
  `corner`, `up`. Each `JunctionEnd` has `member` (`MemberLayout`), `which`
  (`"start"` / `"end"`, `None` for a T host), `into` (unit direction from the
  node into the member), `basis` (member x / profile u / v at the node),
  `profile` and `cut` (the `EndCut`, with `extension`).
- `choose_through` overrides "longest runs through" at butt / coped / multi
  nodes (return an index into `ends`, or `None`).
- Machining functions get the `FrameMember` (local coordinates: start at
  the origin, +X along the member); `part.plane(origin, x, z)`,
  `part.local_point(p)`, `part.local_dir(v)` and `part.length_range` help.
- `frame.junctions`, `frame.connections` and `frame.connectors` list what
  was found and added. Without a connector the frame is unchanged.

## Not supported (yet)

- T-junctions onto arc members; mitering two arcs that are not tangent.
- Per-corner overrides (choose which member runs through), profile offsets
  (e.g. an angle's heel on the skeleton) and profile rotation other than
  `up=`.
- Weld beads, tube corner radii, hole patterns.

## Example

`examples/frames_showcase.py` builds four small frames — a mitered rectangle
with gussets, a table base (butted three-member corners, capped feet), a bent
round-tube rail with a coped post, and a channel bracket with a butt corner —
and prints their cut lists. Rendered in the Playground:
[docs/funnel-evidence/frames-weldments-library/showcase.png](../../../../docs/funnel-evidence/frames-weldments-library/showcase.png).

User docs: `tsjs/apps/documentation/pages/Foundation/Libraries/frames.mdx`.

## Tests

```bash
cd py && uv run --frozen --package cadbuildr-frames python -m pytest packages/cadbuildr/frames/tests -q
```

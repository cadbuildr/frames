# cadbuildr.frames

## Summary

Structural and woodworking frames (weldments) built on CADbuildr foundation —
the Onshape *Frame / Frame trim / Gusset / End cap / Cut list* features as a
library. A `Frame` sweeps a profile (square/rect/round tube, angle, channel,
I-beam, flat/round bar, dimensional lumber) along a skeleton of line and arc
segments, trims the corners (miter, butt "trim to", coped), adds gusset plates
and end caps, drills hole rows, and reports a cut list, weight and stock plan.
Every member is its own `Part` inside the frame `Assembly`, placed by a joint
and carrying anchors + interfaces (`end_a` / `end_b` / `axis` / `face_*`) other
parts mate to, so BOMs and exports see real cut pieces.

It is also a library of configurables (`@part` / `@assembly`, entry point
`cadbuildr.libraries: frames`): standard-size members (EN 10219 SHS / RHS /
CHS, ASTM A500 HSS, angle, UPN, IPE, HEA, AISC W, flat / round bar, lumber),
base plates and gussets, and parametric frames (rectangular, table /
workbench, shelving, ladder / chassis, gate) that a viewer inserts and edits
with widgets.

It composes plain foundation operations only — `Extrusion` along each segment,
`Lathe` for bent (arc) members, cut `Extrusion`s on trim planes for miters and
butts, and the through member's outline for copes — so it renders anywhere
foundation does (Prototype app, Hub, Playground, kernel-api). No schema nodes.

## Tags

cad, python, frames, weldments, structural, steel, tube, lumber, cut-list, assembly, library-configurables, interfaces

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
  back, a gusset on something that is not a two-member corner, a hole that
  runs off its member or face; `UnknownSectionError` lists the known sizes.
- Placement by anchors and joints, never transforms: members are jointed to
  their skeleton node, plates `connect` by interfaces (`assembly.check()`
  reports no coordinate placements). Lay a frame out where it belongs
  (`rectangle(center=...)`, `offset_skeleton`) instead of moving it.
- Every configurable builds from its defaults and from each configuration
  (`tests/test_catalog.py` walks the manifest).
- Publish-first: depends on `cadbuildr-foundation` from PyPI only.

## Dependencies

### Upstream

- [cadbuildr-foundation](https://pypi.org/project/cadbuildr-foundation/) (PyPI)

### Downstream

- [cadbuildr-tslot](https://github.com/cadbuildr/tslot) (T-slot framing on the connector hook and the member `face_*` anchors)
- The CADbuildr agent's curated-libraries registry (prompt routing adds it as a project dependency; its harness skill is `SKILL.md` here).

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

### Anchors and interfaces (mate parts onto a frame)

Every `FrameMember` carries, in its local coordinates (start node at the
origin, +X along the member):

| Anchor | Where | Interface |
|---|---|---|
| `node_a`, `node_b` | the skeleton nodes (the frame places the member by `node_a`) | — |
| `end_a`, `end_b` | the material ends, +Z out of the member | `PlaneFace` |
| `axis` | at `end_a`, +Z along the member | `Shaft(d)` on round tube / bar |
| `face_top`, `face_bottom`, `face_left`, `face_right` | outside of the profile at `end_a`, +Z out of the face, +X along the member (straight members) | `PlaneFace` |

```python
scene.connect(plate.interface("seat"), frame.member(0).interface("face_top"))
frame.member("member_2").anchor("face_left").offset([250, 0, 0])  # 250 mm along
```

End caps connect face to face onto `end_a` / `end_b`; gussets are jointed
to a `gusset_N` anchor on their first member.

### Holes

`member.drill(face="top", size="M8", count=4, margin=50)` (or `at=[...]`,
`count=` + `pitch=`, `diameter=`, `offset=`, `through=True`) cuts a row of
ISO 273 clearance holes and returns their anchors `hole_0…`, each with a
`ScrewHole(size)` interface a screw / bolt mates onto.
`Frame(..., holes=[HolePattern(member=0, face="top", size="M8", count=4,
margin=50)])` does the same while the frame is built.

### Standard sections, weight, stock

```python
from cadbuildr.frames import standard_profile, profile_from_designation, STEEL_DENSITY

standard_profile("SHS", "40x40x3"); standard_profile("IPE", "IPE200")
profile_from_designation("W8x18"); profile_from_designation("CHS 48.3x3.2")
frame.weight(STEEL_DENSITY)          # kg: stock length x kg/m + plates
frame.total_length()                 # {"SHS 40x40x3": 2160.0}
print(frame.stock_plan(stock_length=6000, kerf=3).table())
```

Tables (`cadbuildr.frames.standards`): `EN10219_SHS`, `EN10219_RHS`,
`EN10219_CHS`, `ASTM_A500_SQUARE`, `EN10056_ANGLE`, `UPN`, `IPE`, `HEA`,
`AISC_W`, `EN10058_FLAT`, `EN10060_ROUND`, `LUMBER`. Sections stay
simplified (sharp corners, no root fillets): masses are within a few percent
of the catalogue.

### Library configurables

`python -m cadbuildr.foundation.library manifest cadbuildr.frames`:

| Toolbar section | Items |
|---|---|
| Frames | `RectangularFrame`, `TableFrame` (shelf, end-cap or `BasePlate` feet), `ShelvingFrame`, `LadderFrame` (ladder / trailer / cart base), `GateFrame` (pickets or brace) |
| Tubes | `SquareTubeMember`, `RectTubeMember`, `RoundTubeMember`, `HSSMember` |
| Beams and sections | `IPEMember`, `HEAMember`, `WideFlangeMember`, `ChannelMember`, `AngleMember` |
| Bars and lumber | `FlatBarMember`, `RoundBarMember`, `LumberMember` |
| Plates | `BasePlate` (4 bolt holes, `top` mates onto a member end), `TriangularGusset` |

Members take `size` (one configuration per table row), `length` and an
optional hole row (`hole_count`, `hole_size`, `hole_face`, `hole_margin`).
The parametric frames are `Frame`s, so `cut_list()`, `weight()` and
`stock_plan()` work on them.

## Not supported (yet)

- T-junctions onto arc members; mitering two arcs that are not tangent.
- Per-corner overrides from the `Frame` call (a `ConnectorRule.choose_through`
  does it), profile offsets (e.g. an angle's heel on the skeleton) and
  profile rotation other than `up=`.
- Weld beads, tube corner radii, holes on bent members, hole grids
  (rows only).
- `Frame` itself is not a manifest item (a skeleton has no widget yet); the
  parametric frames are.

## Example

- `examples/frames_showcase.py` builds four small frames — a mitered
  rectangle with gussets, a table base (butted three-member corners, capped
  feet), a bent round-tube rail with a coped post, and a channel bracket
  with a butt corner — laid out in place (no transforms) and prints their
  cut lists.
- `examples/workbench.py`: a `TableFrame` workbench with a shelf, bolt-down
  base plates and a drilled top rail; prints the cut list, weight and stock
  plan.

User docs: https://documentation.cadbuildr.com (Foundation > Libraries > Frames).

## Tests

```bash
uv sync && uv run pytest tests -q
```

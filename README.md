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

For welded and fabricated work it also prepares tube ends (true saddle
copes onto round or square tube, mitres, ISO 9692-1 / ASME B16.25 weld-prep
bevels), annotates every joint with its weld (ISO 2553 symbol as data,
fillet size and length, total weld length in the BOM), gives a saw angle per
end in the cut list, adds anchor-bolt base plates, corner gussets and end
caps, and checks a member as a simple span under a UDL (L/250 deflection and
yield) in its `__checks__` hook.

It composes plain foundation operations only — `Extrusion` along each segment,
`Lathe` for bent (arc) members, cut `Extrusion`s on trim planes for miters and
butts, and the through member's outline for copes — so it renders anywhere
foundation does (Prototype app, Hub, Playground, kernel-api). No schema nodes.

## Tags

cad, python, frames, weldments, structural, steel, tube, lumber, cut-list, assembly, library-configurables, interfaces, welding, coping, base-plate, load-check

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
- Checks go in `__checks__` hooks (member load check, base-plate edge /
  spacing / washer checks); `check()` is never overridden.
- Every dimension is cited in the docstring of its table or class
  (standard number or datasheet URL); estimated values are listed under
  `Estimated:`.
- Publish-first: depends on `cadbuildr-foundation` from PyPI only
  (`cadbuildr-bom` is optional: weld lines are added when it is installed).

## Dependencies

### Upstream

- [cadbuildr-foundation](https://pypi.org/project/cadbuildr-foundation/) `>=0.3.0,<0.4.0` (PyPI)
- optional: [cadbuildr-bom](https://github.com/cadbuildr/bom) (weld BOM lines)

### Downstream

- [cadbuildr-tslot](https://github.com/cadbuildr/tslot) (T-slot framing on the connector hook and the member `face_*` anchors)
- The CADbuildr agent's curated-libraries registry (prompt routing adds it as a project dependency; its harness skill is `SKILL.md` here).

## Quickstart (welded)

```python
from cadbuildr.foundation import show
from cadbuildr.frames import Frame, PreparedTube, profile_from_designation, rectangle

frame = Frame(rectangle(1500, 700), profile_from_designation("SHS 50x50x3"), corner="butt")
frame.apply_udl("member_1", 3.0)          # kN/m, simple span -> __checks__
print(frame.cut_list_table())             # with a saw angle per end
print(frame.weld_table())                 # ISO 2553 symbols, lengths
print(frame.bom_table())                  # members, plates, welds, total weld length
print(frame.check())                      # L/250 deflection and yield

post = PreparedTube(section="CHS 42.4x3.2", length=900, end_a="cope", cope_host="CHS 48.3x3.2")
print(post.cut_length, post.cope_template()[:3])
show(frame)
```

## Catalogue

| Item | Kind | Standard / source |
|---|---|---|
| `SquareTubeMember`, `RectTubeMember`, `RoundTubeMember` | part | EN 10219-2 (corner radii 2t / 2.5t / 3t) |
| `HSSMember` | part | ASTM A500 / AISC design wall |
| `AngleMember` | part | EN 10056-1 (root r1, toe r2) |
| `ChannelMember` (UPN) | part | DIN 1026-1, tolerances EN 10279 (8 % taper, r1, r2) |
| `PFCMember` | part | BS EN 10365, tolerances EN 10279 (root radius) |
| `IPEMember`, `HEAMember` | part | EN 10365 (root radius) |
| `WideFlangeMember` | part | ASTM A6 / AISC |
| `FlatBarMember`, `RoundBarMember` | part | EN 10058, EN 10060 |
| `LumberMember` | part | dimensional lumber (dressed sizes) |
| `PreparedTube` | part | cope / mitre / bevel (ISO 9692-1, ASME B16.25) |
| `SimplySupportedBeam` | part | EN 1993-1-1 6.2.5, L/250 (`__checks__`) |
| `BasePlate`, `AnchorBasePlate` | part | EN 1090-2 Table 11 holes, EN 1993-1-8 Table 3.3 |
| `TriangularGusset`, `CornerGusset`, `TubeEndCap` | part | — |
| `RectangularFrame`, `TableFrame`, `ShelvingFrame`, `LadderFrame`, `GateFrame` | assembly | — |

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
posts) use world +X. Pass `up=` to change it. Constructed directly, tube
corners are sharp unless `corner_radius=` is given and angles / channels /
beams take optional `root_radius`, `toe_radius` (and `taper` for channels);
`standard_profile()` sets the standard's radii. Rounded outlines are drawn
as one `CompactPolygon` per loop (lines + true arcs).
`profile.section_properties()` returns area, centroid, `i_u` / `i_v` and
`w_u` / `w_v` (checked against the catalogues to 0.5 %).

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
`EN10219_CHS`, `ASTM_A500_SQUARE`, `EN10056_ANGLE`, `UPN`, `PFC`, `IPE`,
`HEA`, `AISC_W`, `EN10058_FLAT`, `EN10060_ROUND`, `LUMBER`. Areas and masses
match the catalogues to within 0.5 % (W shapes and HSS are still sharp: a
few percent off).

### Tube end prep

`PreparedTube(section, length, end_a, end_b, ...)` with each end `square`,
`miter` (`miter_a` / `miter_b`, about the profile's `v` or `u` axis),
`cope` (`cope_host`, `cope_angle`, `cope_offset`) or `bevel`
(`bevel_angle`, `root_face`). On any straight member:
`member.cope(which, Cope(host, angle, offset))`,
`member.bevel(which, BEVEL_ISO_9692_1_V)`.

**How the cope is cut.** The host's outer profile is extruded along the
host axis and subtracted from the branch. The kernel intersects the
branch's outer and inner cylinders with the host cylinder exactly, so both
walls end on the true saddle curve; onto a square / rectangular host the
same subtraction leaves a plane. The cut list, templates and weld lengths
use the closed form of that intersection,
`x(phi) = (r cos(phi) cos(a) + sqrt(R^2 - (e + r sin(phi))^2)) / sin(a)`
(branch radius r, host radius R, angle a, offset e). Tests check it
against closed forms: the half-bicylinder volume 8R³/3 and the
ellipse-shaped saddle of two equal tubes. `cope_template()` /
`cope_template_svg()` unroll it into a 1:1 wrap-around template.

Bevels: `BEVEL_ISO_9692_1_V` (30 deg, root face 1.5 mm: ISO 9692-1 ref. 1.3
single-V, t = 3..10 mm) and `BEVEL_ASME_B16_25` (37.5 deg, land 1.6 mm). Round
tubes get a conical (revolved) cut, rectangular tubes one plane wedge per
wall.

### Cut list saw angles

`cut_list()` rows carry `saw_angles` per end (`SawAngle(miter, bevel)` in
degrees from square; `None` = a saddle cope, cut with a notcher or a
template) and `end_preps` (`"cope onto CHS 48.3x3.2 @ 90 deg"`,
`"bevel 30 deg / root face 1.5"`); the table prints `Saw 1` / `Saw 2`.

### Welds (metadata)

`frame.welds()` returns one `Weld` per joint: mitred corners get an
all-round butt weld, butted / coped / T nodes an all-round fillet on the
trimmed member's end outline (the 3D saddle for round-on-round copes),
gussets a fillet per leg on both faces, end caps and feet (`frame.feet`
with `plate.welded_to`) an all-round fillet. Each has an ISO 2553
`WeldSymbol` as data (`elementary`, `size` with `a` / `z` / `s`, `length`,
`side`, `all_around`, `field`, ISO 4063 `process`, ISO 5817 `quality`).
The default throat is `a = 0.7 t_min`, at least 3 mm (EN 1993-1-8 4.5.2(2));
thinner walls get `a = t` with a note. This default is an estimate.
`frame.bom()` / `bom_table()` list
members, plates and one row per weld size, ending in the total weld length.
With `cadbuildr-bom` installed the weld totals are BOM lines (unit mm).

### Load check

`frame.apply_udl(member, udl_kN_per_m, span=None, grade="S235",
limit_ratio=250)` (or `SimplySupportedBeam`) makes the member's
`__checks__` report `delta = 5 w L^4 / (384 E I)` against `L / 250` and
`sigma = w L^2 / (8 W_el)` against `f_y` (Roark Table 8.1; EN 1993-1-1
6.2.5, gamma_M0 = 1.0, E = 210 000 N/mm²). `load_table(profile, spans)`
gives the allowable UDL per span. Not checked: lateral-torsional buckling,
shear, local buckling, web bearing.

### Plates

- `AnchorBasePlate(column, width, depth, thickness, anchor, hole, pattern,
  edge)`: 2 / 4 / 6 / 8 anchors, `d0` from EN 1090-2 Table 11 (normal or
  oversize), `__checks__` warns below `e = 1.2 d0` / `p = 2.2 d0`
  (EN 1993-1-8 Table 3.3) and when a washer (ISO 7089) fouls the column
  weld; `BasePlateError` when holes or the column do not fit.
- `CornerGusset(leg, width, thickness, inner_radius, corner_radius)`: an
  L-shaped knee plate with a true inner radius.
- `TubeEndCap(section, style="plate" | "inset", thickness, clearance)`: a
  welded cap; `seat` mates onto a member end.

### Library configurables

`python -m cadbuildr.foundation.library manifest cadbuildr.frames`:

| Toolbar section | Items |
|---|---|
| Frames | `RectangularFrame`, `TableFrame` (shelf, end-cap or `BasePlate` feet), `ShelvingFrame`, `LadderFrame` (ladder / trailer / cart base), `GateFrame` (pickets or brace) |
| Tubes | `SquareTubeMember`, `RectTubeMember`, `RoundTubeMember`, `HSSMember` |
| Beams and sections | `IPEMember`, `HEAMember`, `WideFlangeMember`, `ChannelMember`, `PFCMember`, `AngleMember` |
| Bars and lumber | `FlatBarMember`, `RoundBarMember`, `LumberMember` |
| Plates | `BasePlate` (4 bolt holes, `top` mates onto a member end), `AnchorBasePlate`, `TriangularGusset`, `CornerGusset`, `TubeEndCap` |
| Fabrication | `PreparedTube` (cope / mitre / bevel), `SimplySupportedBeam` (UDL check) |

Members take `size` (one configuration per table row), `length` and an
optional hole row (`hole_count`, `hole_size`, `hole_face`, `hole_margin`).
The parametric frames are `Frame`s, so `cut_list()`, `weight()` and
`stock_plan()` work on them.

## Not supported (yet)

- T-junctions onto arc members; mitering two arcs that are not tangent.
- Per-corner overrides from the `Frame` call (a `ConnectorRule.choose_through`
  does it), profile offsets (e.g. an angle's heel on the skeleton) and
  profile rotation other than `up=`.
- Weld beads as solids (welds are metadata), holes on bent members, hole
  grids (rows only), end prep on bent members, bevels on open sections.
- Cut lengths and the BOM use the saw-cut stock length; the material a
  cope or bevel removes is not subtracted from the mass.
- Unequal angles, UPE, AISC C / L tables; root fillets on W shapes.
- `Frame` itself is not a manifest item (a skeleton has no widget yet); the
  parametric frames are.

## Example

- `examples/frames_showcase.py` builds four small frames — a mitered
  rectangle with gussets, a table base (butted three-member corners, capped
  feet), a bent round-tube rail with a coped post, and a channel bracket
  with a butt corner — laid out in place (no transforms) and prints their
  cut lists.
- `examples/welded_workbench.py`: a welded SHS 50 workbench with a
  mitred L50 lip, a CHS footrest, anchor-bolt base plates, a load check
  on the front rail; prints cut list (saw angles), weld list, BOM and a
  load table.
- `examples/trailer_ladder_frame.py`: a 2400 x 1200 trailer ladder frame
  (RHS 100x50x4 rails, UPN 100 cross members, A-frame drawbar with
  compound saw angles, nose gusset), payload check, weld list, stock plan.
- `examples/workbench.py`: a `TableFrame` workbench with a shelf, bolt-down
  base plates and a drilled top rail; prints the cut list, weight and stock
  plan.

User docs: https://documentation.cadbuildr.com (Foundation > Libraries > Frames).

## Tests

```bash
uv sync && uv run pytest tests -q
```

---
name: cadbuildr-frames
description: How to build welded / structural frames (weldments) with cadbuildr.frames — standard sections (EN 10219 SHS/RHS/CHS, ASTM A500 HSS, angle, UPN, IPE, HEA, AISC W, bar, lumber) swept along a skeleton of centre lines, miter / butt / coped corners, gussets, end caps, bolt-hole rows, cut list, weight and stock plan, member anchors/interfaces to mate parts onto a frame, ready-made parametric frames (table/workbench, shelving, ladder/chassis, gate), and the connector hook for joint hardware.
---

# cadbuildr-frames

Structural frames as a library on `cadbuildr.foundation` (the Onshape
Frame / Frame trim / Gusset / End cap / Cut list features). You give a
SKELETON of line / arc segments (the profiles' CENTRE LINES) and a profile;
the library sweeps every member, trims the corners and reports the cut
list. **Never extrude, position, trim or `translate()` tubes by hand** —
lay the skeleton out where the frame belongs. Each member is its own `Part`
inside the frame `Assembly`, placed by a joint, so BOMs and exports see
real cut pieces. For aluminium T-slot (80/20) framing use `cadbuildr-tslot`,
which is built on this library.

## Fastest path: a parametric frame

```python
from cadbuildr.foundation import show
from cadbuildr.frames import TableFrame

bench = TableFrame(width=1500, depth=700, height=900, section="SHS 40x40x3",
                   shelf_height=150, feet="base_plate")   # or "end_cap" / "none"
bench.member("member_1").drill("top", size="M8", count=6, margin=80)
print(bench.cut_list_table()); print(f"{bench.weight():.1f} kg")
print(bench.stock_plan(stock_length=6000, kerf=3).table())
show(bench)
```

| Class | What | Key inputs |
|---|---|---|
| `RectangularFrame` | flat frame in XY, centred | `width, depth, section, corner="miter"/"butt", gussets` |
| `TableFrame` | table / workbench base, floor at z=0, top face at `height` | `width, depth, height, section, shelf_height, feet` |
| `ShelvingFrame` | 4 posts + a rail rectangle per level | `width, depth, height, levels, bottom, section` |
| `LadderFrame` | 2 rails along X + rungs (ladder, trailer chassis, cart) | `length, width, rungs, section, rung_section` |
| `GateFrame` | gate leaf in XZ, bottom-left at origin | `width, height, section, infill="pickets"/"brace"/"none", pickets` |

`section` is a designation string: `"SHS 40x40x3"`, `"RHS 80x40x3"`,
`"CHS 48.3x3.2"`, `"L50x50x5"`, `"UPN100"`, `"IPE100"`, `"HSS2x2x1/8"`,
`"Lumber 2x4"`… (`cadbuildr.frames.catalog.SECTIONS` lists the widget
options). All of them are `Frame`s.

## Custom frames: `Frame(skeleton, profile, ...)`

```python
from cadbuildr.frames import Frame, Line3D, polyline, EndCap, standard_profile

corners = [(-300, -200), (300, -200), (300, 200), (-300, 200)]
top = polyline([(x, y, 700) for x, y in corners], closed=True)
legs = [Line3D((x, y, 700), (x, y, 0)) for x, y in corners]
frame = Frame(top + legs, standard_profile("SHS", "40x40x3"), corner="butt",
              end_caps=EndCap(thickness=3))
```

- Skeleton (mm): `Line3D(start, end)`, `Arc3D(start, through, end)` (bent
  member); helpers `rectangle(width, depth, center=...)`,
  `polyline(points, closed=False)`, `box_edges(width, depth, height)`,
  `offset_skeleton(segments, (dx, dy, dz))` — concatenate lists with `+`.
  Segments sharing an end point are joined; an end lying inside another
  straight member is a T-junction (rails at mid-height of posts work).
- `profile=` one profile or a list with one per segment.
- `corner=`: `"miter"` (default, bisector cut), `"butt"` (the longer member
  runs through, the other is trimmed to its face; ties: first segment; an
  arc always runs through), `"coped"` (as butt, cut to the through member's
  outer shape — round tube onto round tube). 3+ members at a node: the
  longest runs through. Collinear ends: continuous. Free ends: square.
- `up=(x, y, z)`: which side the profile's v axis faces (default: the plane
  normal of a planar skeleton, else +Z; posts parallel to up use +X).

## Profiles

Standard sizes (prefer these — real stock, real designations in the cut
list): `standard_profile(family, size)` with family `SHS`, `RHS`, `CHS`,
`HSS`, `L`, `UPN`, `IPE`, `HEA`, `W`, `FL` (flat), `RD` (round bar),
`LUMBER`; or `profile_from_designation("IPE200")`. Tables in
`cadbuildr.frames.standards` (`EN10219_SHS`, `IPE`, `AISC_W`…). Unknown
size -> `UnknownSectionError` listing the known ones.

Free dimensions: `SquareTube(size, wall)`, `RectTube(width, height, wall)`,
`RoundTube(diameter, wall)`, `RoundBar(d)`, `RectBar(w, h)`,
`Angle(w, h, t)`, `Channel(height, width, web, flange)`,
`IBeam(height, width, web, flange)`, `Lumber("2x4")`. `u` (first dim) lies
across the member in the frame's plane, `v` towards `up`. Every profile has
`area` (mm^2) and `mass_per_m(density)` (kg/m).

## Single members (to mate into your own assembly)

`SquareTubeMember(size="40x40x3", length=1000, hole_count=0, hole_size="M8",
hole_face="top", hole_margin=50)` — same for `RectTubeMember`,
`RoundTubeMember`, `HSSMember`, `AngleMember`, `ChannelMember`, `IPEMember`,
`HEAMember`, `WideFlangeMember`, `FlatBarMember`, `RoundBarMember`,
`LumberMember`, or `standard_member("IPE", "IPE200", 3000)`. Along +X from
`end_a` (x=0) to `end_b`.

## Anchors and interfaces — mate parts onto members

Every member (in a `Frame` or standalone) has, in local coordinates (start
node at origin, +X along the member):

- `end_a`, `end_b`: material ends, +Z outward — `PlaneFace`.
- `face_top`, `face_bottom`, `face_left`, `face_right` (straight members):
  outside of the profile at `end_a`, +Z out of the face, +X along the
  member — `PlaneFace`. `anchor("face_top").offset([d, 0, 0], name="x")`
  is a point `d` mm along the face.
- `axis`: at `end_a`, +Z along the member — `Shaft(d)` on round tube / bar.
- `node_a`, `node_b`: the skeleton nodes.

```python
scene = Assembly(); scene.ground(frame)
scene.connect(bracket.interface("seat"), frame.member(0).interface("face_top"))
```

`frame.member(i_or_name)`, `frame.members`, `frame.gussets`, `frame.end_caps`.
Use `connect` / joints, not `add_component(tf=...)`; `frame.check()` should
report no `coordinates` issues.

## Holes, plates

- `member.drill(face="top", size="M8", count=4, margin=50)` — also
  `at=[...]` (mm from `end_a`), `count=` + `pitch=` (centred), `diameter=`,
  `offset=` (across the face), `through=True` (both walls). Returns anchors
  `hole_0…`, each a `ScrewHole(size)` interface (stdlib screws mate here).
  Or `Frame(..., holes=[HolePattern(member=0, face="top", size="M8",
  count=4, margin=50)])`.
- `BasePlate(width, depth, thickness, hole_size, hole_inset)`: foot plate;
  `connect(plate.interface("top"), leg.interface("end_b"))`; holes
  `hole_0..3` are `ScrewHole`s (anchor bolts).
- `TriangularGusset(size, thickness, chamfer)` free-standing; inside a frame
  use `gussets=[Gusset(at=(x, y, z), size=60, thickness=5,
  position="center"/"top"/"bottom")]` (TWO-member corners only).
- `end_caps=EndCap(thickness=3)` on every free end (cut lengths unchanged).

## Cut list, weight, stock

- `frame.cut_list()` -> `CutListItem` rows (`profile`, `length` long point
  to long point, `end_angles` from square, `end_cuts`, `count`, `members`,
  `bend_radius`); `frame.cut_list_table()` prints them.
- `frame.weight(density=STEEL_DENSITY)` kg (also `ALUMINIUM_DENSITY`,
  `STAINLESS_DENSITY`, `SOFTWOOD_DENSITY`); `frame.total_length()` per
  profile.
- `frame.stock_plan(stock_length=6000, kerf=3)` -> `StockPlan` (`.count()`,
  `.utilisation`, `.table()`); `STOCK_LENGTH_20FT` / `_24FT` for US stock.

## Connector hook (joint hardware)

`Frame(..., connector=rule)` is called once per junction before members
are added: return `Connection(components=[Placed(part, transform)],
machining=[(end, fn)])` or `None`. Subclass `ConnectorRule` (`connect`,
optional `choose_through` — e.g. make posts run through — and
`prepare_member`) or pass a callable `connector(junction)`.
`Junction.kind` is `free` / `continuous` / `corner` / `tee` / `multi`;
`junction.through`, `junction.butting`, `junction.ends` (each `JunctionEnd`
has `member`, `which`, `into`, `basis`, `cut`).
`basis_transform(junction.node, end.basis)` places hardware at a joint.

## Errors (it fails loudly, never silently)

`ValueError` naming the members for: overlapping members, a coped member
wider than its host, an arc that would need cutting back, a gusset on
something that is not a two-member corner, a profile list of the wrong
length, a hole running off its member / face, a shelf outside the legs.
Not supported yet: T-junctions onto arcs, mitering two non-tangent arcs,
weld beads, tube corner radii, holes on bent members.

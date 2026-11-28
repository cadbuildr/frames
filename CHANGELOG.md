# Changelog

## 0.3.0 (unreleased)

### Welded and fabricated frames

- Tube end prep (`end_prep`): true saddle copes onto round tube / bar and
  flat copes onto SHS / RHS (host envelope subtraction + closed-form
  saddle), mitres about u or v, ISO 9692-1 / ASME B16.25 weld-prep
  bevels; cope templates (points and 1:1 SVG). `PreparedTube` configurable,
  `FrameMember.cope` / `.bevel`.
- Rolled radii: EN 10056-1 angle root / toe radii, DIN 1026-1 UPN radii
  and 8 % taper, new BS EN 10365 `PFC` table and `PFCMember`, IPE / HEA
  root radii, EN 10219-2 tube corner radii; more EN 10056-1 and EN 10058
  rows. `section_properties()` (area, I, W_el) matches the catalogues
  to 0.5 %.
- Welds as metadata (`welds`): per-joint fillet / butt welds with ISO 2553
  symbols as data, default throat per EN 1993-1-8 4.5.2(2), `Frame.welds()`,
  `weld_table()`, `bom()` / `bom_table()` with the total weld length, and
  `cadbuildr-bom` lines when it is installed. `Frame(welded=False)`.
- Cut list: `saw_angles` (mitre / bevel) and `end_preps` per end.
- Load check (`loads`): simple-span UDL against L/250 and yield in
  `FrameMember.__checks__` (`apply_udl`), `load_table`,
  `SimplySupportedBeam` configurable.
- Plates: `AnchorBasePlate` (2/4/6/8 anchors, EN 1090-2 holes,
  EN 1993-1-8 edge / spacing checks), `CornerGusset`, `TubeEndCap`.
- Examples: `welded_workbench.py`, `trailer_ladder_frame.py`.
- Standard SHS / RHS / L / UPN / IPE / HEA profiles are now rounded, so
  their masses and miter long points change slightly (closer to the
  catalogue). `RHS` designations read height x width (`RHS 100x50x4`).

### Sync from the monorepo (Nov-27 refactor)

- Library configurables: 12 standard `*Member` parts (one configuration per
  table row), `BasePlate`, `TriangularGusset` and the parametric
  `RectangularFrame`, `TableFrame`, `ShelvingFrame`, `LadderFrame`,
  `GateFrame` assemblies; `cadbuildr.libraries` entry point `frames`.
- Standard section tables (`cadbuildr.frames.standards`): EN 10219 SHS / RHS
  / CHS, ASTM A500 HSS, EN 10056 angle, DIN 1026 UPN, EN 10365 IPE / HEA,
  AISC W, EN 10058 flat, EN 10060 round, lumber; `standard_profile`,
  `profile_from_designation`, `UnknownSectionError`.
- Member anchors and interfaces (`node_a/b`, `end_a/b`, `axis`, `face_*` with
  `PlaneFace` / `Shaft`), placement by joints instead of transforms,
  `FrameMember.drill` / `HolePattern` with `ScrewHole` interfaces,
  `offset_skeleton`.
- `Frame.weight`, `Frame.total_length`, `Frame.stock_plan` (first-fit
  decreasing, kerf).
- Requires `cadbuildr-foundation>=0.3.0,<0.4.0`.
- `uv.lock` removed until foundation 0.3.0 is on PyPI (the old lock pinned
  0.2.21 and no longer resolves); CI installs foundation from git meanwhile.

## 0.2.0

- Connector hook (`ConnectorRule`, `Connection`, `Placed`), used by
  `cadbuildr-tslot`.

## 0.1.0

- First release: `Frame`, skeleton helpers, profiles, miter / butt / coped
  corners, gussets, end caps, cut list.

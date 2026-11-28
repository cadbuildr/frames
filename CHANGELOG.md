# Changelog

## 0.3.0 (unreleased)

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

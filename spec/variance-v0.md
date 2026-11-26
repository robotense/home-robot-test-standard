# Home variance classification and variance card, v0

Status: **draft v0.** Part of the Robotense test standard, with `spec/v0.md`. Robotense publishes and maintains it. The text is published under CC BY 4.0. The rules adopted on the design questions of v0 are in §10.

**Draft additions for variance-v0.1.** Interaction attributes for doors and drawers (§4.3 and §4.3.1), a drawer-clearance card (§9, card 4), robot profiles (§5.1), a reference-path format (§5), and changes proposed from our home generator's implementation (§13). Rows added in v0.1 carry "v0.1" in the tier column.

**What this is.**
- **Classification.** A standard way to describe the conditions a home robot operates in, organised as domain > category > attribute. It is the vocabulary of the test standard and the input language of a variance engine.
- **Variance card.** The record format for one specific variance. The engine compiles a card into scene edits and spec v0 factors.

Each attribute row cites its evidence by short reference (§12).

**Lineage.**
- ISO 34503:2023: the split into fixed scenery, ambient conditions and moving agents; a separate domain for conditions internal to the system (its Annex A); include, exclude and conditional statements (its §12.4, "Inclusion, exclusion, and conditional"; table of contents fetched 2026-11-24, https://www.din.de/de/mitwirken/normenausschuesse/naautomobil/veroeffentlichungen/wdc-beuth:din21:371879457/toc-3487472/download).
- ISO 34504:2024: extensible tag trees.
- Scenic 3: a scenario is a distribution over scenes, with hard `require`, soft `require[p]` and `mutate`.
- STAR-Gen: each variance is tagged by what it changes for the policy, relative to a base task.
- Manipulation benchmarks: the factor lists of The Colosseum, Factor World, LIBERO-Plus, LIBERO-PRO, REALM, VLA-Arena and GemBench.

No construct here is new by itself.

**Relation to spec v0.** A card is a higher-level generator of spec v0 factor blocks (`spec/v0.md` §2). Compiling a card against a base scenario produces two things. The first is a factor list in v0 form (name, low, high, nominal, kind, unit, failure type). The second is a deterministic scene-edit program. The purity rule holds: the initial scene is a pure function of the base scenario hash, the card's compile hash, the factor vector and the variance seed (§7).

## 1. Terms

| Term | Meaning |
|---|---|
| **Classification** | The registry of attributes in §4. It describes the home operational domain: the ways any home can be. It is not tied to one robot |
| **Domain, category, attribute** | Three levels. An attribute ID is `domain.category.attribute`, for example `surface.rug.edge` |
| **Attribute** | One typed variable that describes a home condition, with the fields in §2 |
| **Anchor** | A reference to the task or the robot that placement can be relative to: the reference path, target object, camera or window (§5) |
| **Variance** | A specific condition or family of conditions: a set of attribute values or distributions, placed relative to anchors. A variance with ranges is a distribution over scenes |
| **Variance card** | The record of one variance (§6). Its `compile` block is hashed. Everything else is metadata that may change without changing generated scenes |
| **Instance** | One sampled scene from a card: base scenario, card, factor vector and seed |
| **Declared domain** | A robot maker's statement of the conditions its robot is designed for, written over attributes (§8). It corresponds to an automotive ODD |
| **Channel** | What a variance changes for the policy, relative to the base task: `observation`, `instruction` or `behavior` (STAR-Gen V, S, B). A variance can have several |
| **Part** | A door, drawer or flap of a fixture or piece of furniture, on its own joint. Its ID is `<item>.door<k>` or `<item>.drawer<k>` (the generator's stable part IDs). Attributes with scope `part` are recorded per part |
| **Robot profile** | The dimensions of one robot that access and clearance are measured against (§5.1). The classification describes homes for any robot; quantities relative to a robot are derived per profile and never stored as home attributes |
| **Feasibility status** | Per instance and robot profile: `feasible`, `infeasible` or `ambiguous`, from a rule declared in the card or scenario. It decides how a reported refusal is scored (§9, card 4, `expected_handling`) |

## 2. Attribute fields

Each attribute in the registry carries these fields. §4 shows them in compact form.

```yaml
id: surface.rug.edge
type: struct                # enum | float | int | bool | set | struct | string
fields:                     # for struct; each field has its own type and range
  present: {type: bool}
  edge_height: {type: float, low: 0.003, high: 0.03, unit: m}
  fringe: {type: bool}
  anchored: {type: bool}
nominal: {present: false}
scope: room                 # home | room | surface | fixture | part | object | agent | light | camera | task
measure: "ruler at the edge; present and fringe taggable from one robot camera frame"
image_taggable: true        # can be tagged from one robot camera frame (coverage check vocabulary)
generate:
  op: add_entity            # §6 edit operator used
  backends: {mujoco: approx, isaac: supported, blender: supported}
  note: "flat rug is a thin box with friction; curled edges and fringe need deformables"
failure_types: [contact, safety_constraint]   # spec/v0.md §2 list
default_channels: [behavior]
evidence: {grade: C, refs: [Sung10]}
tier: core                  # core | extended
since: variance-v0
```

- **Failure types** are those of `spec/v0.md` §2: `instruction`, `visual`, `layout`, `object_identity`, `object_state`, `contact`, `long_horizon`, `safety_constraint`. An attribute is a condition (a cause). A failure type is an effect. The mapping is many to many and records suspicion, not fact.
- **Units** are SI, except lux for illuminance, kelvin for colour temperature and degrees for angles.
- **Ranges** are working bounds for generation. Where a range comes from a source, the row cites it. Otherwise it is our bound and can change without a version bump.

## 3. Codes used in §4

**Evidence grade.**
- **A**: an outcome effect measured in two or more studies, at least one on a real robot.
- **B**: measured in simulation or in one real study.
- **C**: reported qualitatively in real homes.
- **S**: tested by a published test standard. This shows the industry thinks the condition matters, not that it changes outcomes.
- **H**: hypothesis. We found no outcome evidence.
- **mixed**: studies disagree.

Short references are listed in §12.

**Generation.**
- **M**: native in MuJoCo now.
- **M~**: approximated in MuJoCo; the approximation is stated.
- **I**: needs Isaac Sim for realism.
- **B**: needs a ray-traced renderer (Blender Cycles via Infinigen, or Isaac RTX).
- **G**: set at layout generation (MolmoSpaces, ProcTHOR, Infinigen or RoboCasa).
- **—**: we found no open asset or method.

**Measure.** How to measure the attribute in a real home. **img** means it can be tagged from one robot camera frame, which makes it part of the coverage-check vocabulary.

**Tier.**
- **core**: the set the engine's MuJoCo path targets. Core attributes are chosen for evidence grade A, B or C, generation M or M~, or because a worked card needs them.
- **ext**: defined, and outside that target set.

## 4. Classification v0

13 domains, 89 attributes, 53 core (v0: 76 and 44; the v0.1 draft adds 13 attributes, 9 of them core). Each domain notes its automotive counterpart (ISO 34503 clause) where one exists.

### 4.1 `structure`: home structure and layout (ISO 34503 §9 scenery)

| ID | Type; range or values; nominal | Measure | Generation | Relevance: grade, evidence, failure types | Tier |
|---|---|---|---|---|---|
| `structure.room.type` | enum {kitchen, living, dining, bedroom, bathroom, hallway, entry, laundry, office}; kitchen | img | G (room specs; RoboCasa is kitchens only) | H; room types are descriptive scope (AI2-THOR, BEHAVIOR) · layout | core |
| `structure.room.floor_area` | float m² [4, 50]; the clear floor area inside the walls | laser measure | G (floor-plan constraint) | H · layout | ext |
| `structure.home.orientation` | float deg [0, 360), compass bearing of plan north; 0 | compass | M (metadata; no geometry changes) | H; needed to resolve `structure.window.geometry.azimuth` and so `light.daylight.sun` · visual | core, v0.1 |
| `structure.wall.height` | float m [2.2, 3.5]; 2.5 | laser measure | M | H · layout | ext, v0.1 |
| `structure.wall.thickness` | struct {interior: m [0.05, 0.3]; exterior: m [0.1, 0.5]}; {0.10, 0.20} | tape at a doorway | M | H · layout | ext, v0.1 |
| `structure.passage.clear_width` | float m [0.55, 1.2]; 0.815 | tape at the narrowest point of the route, whatever narrows it (doorway, furniture, wall) | M (wall, door or furniture placement) | S (IEC 62885-7 minimum passable gap) · layout, contact | ext |
| `structure.doorway.clear_width` | float m [0.6, 1.0]; 0.815, per doorway: the opening between jambs (frames and casings excluded until generated) | tape between jambs | M | S (ADA 404.2.3: 32 in minimum clear width) · layout, contact | ext, v0.1 |
| `structure.doorway.height` | float m [1.9, 2.4]; 2.03 | tape | M | H · layout | ext, v0.1 |
| `structure.doorway.threshold` | struct {height: m [0, 0.03]; profile: {flat, beveled, rounded, square}}; {0.013, beveled} | ruler | M (primitive at the doorway) | C+S (Sung10: households tested thresholds; IEC 62885-7 maximum threshold height, cylindrical and rectangular profiles; ADA ½ in maximum) · contact | ext |
| `structure.level.change` | struct {type: {none, step_up, step_down, stairs_up, stairs_down}; riser: m [0.10, 0.20]}; none | tape | G, M | C (Sung10: staircase tested); S (ISO 13482 §5.16 heading). IRC maximum riser 7¾ in **[unverified]** · layout, safety_constraint | ext |
| `structure.door.state` | struct {type: {hinged, sliding, pocket}; angle: deg [0, 90]}; {hinged, 90} | img | M (joint state) | C (RUM24: unusual doors misjudged) · layout, object_state | ext |
| `structure.window.geometry` | struct {azimuth: deg [0, 360); sill: m [0.3, 1.2]; area: m² [0.3, 4]} | compass and tape | G, M | H; the anchor for `light.daylight.sun` · visual | core |

**Definitions for generators (v0.1 draft).** These make two generators build the same thing from the same values. They come from our home generator's implementation, adopted as the v0 definitions.

- **Door angle.** `structure.door.state.angle` is 0 when closed and positive when opening into the room the door swings into. A door's leaf is recorded with the scene (hinge position, width, thickness). Default leaf: the clear width less 5 mm at each jamb, 40 mm thick.
- **Threshold profiles** for `structure.doorway.threshold.profile`, at the declared height:

  | Profile | Geometry |
  |---|---|
  | square | 60 mm deep block |
  | flat | Plate 10 mm wider than the wall on each side |
  | beveled | 50 mm top with 1:2 slopes |
  | rounded | Circular segment with an 80 mm chord |

- **Keep-clear zones** are derived from the blueprint and are anchors (§5): a door's swing (the area its leaf sweeps), a 0.9 m approach on each side of each doorway, and 0.9 m at the foot of a stair flight.

### 4.2 `surface`: surfaces and materials (ISO 34503 §9.3.7 drivable-area surface)

| ID | Type; range or values; nominal | Measure | Generation | Relevance | Tier |
|---|---|---|---|---|---|
| `surface.floor.material` | enum {hardwood, laminate, tile, vinyl, stone, concrete, carpet_low, carpet_high}; hardwood | img | M (texture and friction) | C (Sung10 floor types; OK-Robot carpet-to-floor transitions); S (IEC 62885-7 hard floor and carpet) · contact, visual | core |
| `surface.floor.friction` | float coefficient [0.2, 1.0], per room; from the floor material | inclined-plane or pull test with the robot's wheel or foot material | M (geom friction) | H; sets how much pulling force a mobile robot can apply before its base slides (the opening forces in §4.3.1) · contact | core, v0.1 |
| `surface.floor.transition_height` | float m [0, 0.02]; 0 | ruler | M | S (IEC 62885-7 maximum transition height); C (OK-Robot) · contact | ext |
| `surface.rug.edge` | struct {present: bool; edge_height: m [0.003, 0.03]; fringe: bool; anchored: bool}; {false} | img (present, fringe); ruler | M for a flat rug (thin box with friction); M~ for fringe and curled edges (MuJoCo flex **[unverified]**); I | C (Sung10: rugs removed, a tassel cut "to prevent it from getting stuck on the fringe") · contact, safety_constraint | core |
| `surface.support.appearance` | struct {texture: library ID; albedo: [0.05, 0.9]; pattern: {plain, low, high}} for the surface under the task; library default | img | M (material swap) | A (Xie23 real table texture 52.8% vs 91.7%; Colosseum table colour and texture; VLA-Arena V2). Background and walls matter less (LIBERO-Plus 67.5) · visual | core |
| `surface.finish.optical` | per named surface, including a part's front (`<part>.front`: glass cabinet doors, mirror wardrobe doors, high-gloss fronts): enum {matte, gloss, mirror, transparent, dark}; matte | img | M~ (rasterised specular and alpha); B or I for reflections and refraction; I for depth-sensor artefacts | C (Dobb-E: shiny handle 0/10; mirror shows the demonstrator, then the robot); B (ClearGrasp: depth fails on transparent surfaces) · visual | core |
| `surface.support.friction` | float coefficient [0.2, 1.0]; 0.6 | inclined-plane test | M | under-measured (Colosseum inconclusive; STAR-Gen hidden-scene axis) · contact | ext |

### 4.3 `furniture`: furniture and fixtures (ISO 34503 §9.5–9.6 structures)

| ID | Type; range or values; nominal | Measure | Generation | Relevance | Tier |
|---|---|---|---|---|---|
| `furniture.support.height` | float m [0.4, 1.0]; 0.9 | tape | M | B (Gao24 real: table height composes worst with object position; Xie23 sim: table position as hard as table texture). ADA work surfaces 0.71–0.86 m · layout, contact | core |
| `furniture.layout.density` | float [0.1, 0.6]: furniture footprint over clear floor area, for the whole home; per-room values are recorded | floor plan | G (Infinigen counts and spacing) | H · layout | ext |
| `furniture.layout.under_clearance` | float m [0.05, 0.4] | tape | M | S (IEC 62885-7 minimum passable height) · contact | ext |
| `furniture.fixture.handle_type` | per part: enum {bar, knob, recessed, edge_pull, push_to_open, none}; bar. Values defined in §4.3.1 | img | M (geometry on the part's front) | B (GemBench new articulated objects 41.5% vs 94.3% for placements; DoorGym, room doors in simulation: round knobs much harder than pull handles, §4.3.1); C (RUM24 left out round-knob doors and knob drawers because its two-finger gripper could not open them; Dobb-E knob-turning task 13/20) · object_identity, contact | core |
| `furniture.fixture.handle_geometry` | per part: struct {length: m [0, 0.6]; projection: m [0, 0.045]; grip_diameter: m [0.008, 0.05]; orientation: {vertical, horizontal}; along: [0, 1]; height: [0, 1]}; nominal by part kind (§4.3.1) | calipers and tape; orientation and position img | M | H; C for spacing (RUM24: with handles close together the robot grasped both) · contact, object_identity | core, v0.1 |
| `furniture.fixture.handle_finish` | per part: enum {matte, satin, polished, transparent}; matte | img (reflection test, §4.3.1) | M~ (matte, satin); B or I for polished and transparent; MuJoCo depth sees a transparent geom as opaque, and no backend reproduces real depth-sensor errors without a sensor model | C (Dobb-E: a shiny air-fryer handle gave bad depth and 0/10); B (ClearGrasp: depth fails on transparent surfaces) · visual | core, v0.1 |
| `furniture.fixture.hinge` | per hinged part: struct {side: {left, right, top, bottom}, as seen facing the front; max_angle: deg [75, 180]; counterbalance: [0, 1.2]}; {left, 110, 0} | inspection; protractor | M (joint axis, position and range) | H (DoorGym randomises hinge side and push or pull; no per-side result reported) · contact, layout | core, v0.1 |
| `furniture.fixture.resistance` | per part: struct {open_force: N [2, 60]; self_closing: bool; soft_close: {on: bool; pull_force: N [0, 8]}}; {10, false, {false, 0}}. Running force is derived and recorded. Hinge stiffness is this attribute on a hinged part (§4.3.1) | force gauge at the handle | M (joint friction, damping and spring; zone forces as clamped actuator bias) | C (Dobb-E: pulling heavy doors high up tipped the robot; RUM24: drawers sag); S (ADA 309.4 and 404.2.9: 22.2 N maximum for operable parts and interior doors; appliance doors exempt, 804.6.2) · contact | core |
| `furniture.fixture.travel` | per drawer: struct {travel: m [0.10, 0.75]; fraction: share of the box depth [0.3, 1.0]}; {0.35, 0.75} | tape from closed to fully open | M (slide range) | C (RUM24: the policy pulled cloth drawers right out and could not see sagging) · contact | core, v0.1 |
| `furniture.fixture.latch` | per part: struct {type: {none, magnetic, roller, gasket_seal, push_latch, button_release, child_lock}; hold_force: N [0, 40]; zone: deg [0, 10] or m [0, 0.01]; release_force: N [0, 40]}; {none, 0, 0, 0} | inspection; force gauge | M (holding force near closed as clamped actuator bias) | B (DoorGym: latched lever and round knobs harder than the unlatched pull knob; simulation, room doors) · contact | core, v0.1 |
| `furniture.fixture.part_mass` | per part: float kg [0.3, 15]; 2.0 | scale, or door weight from product data | M (body mass) | C (Dobb-E heavy doors) · contact | core, v0.1 |
| `furniture.fixture.operating_clearance` | per part: struct {free_depth: m [0, 3]; side_access: {open, one_side, blocked}}; {1.2, open}. Per robot profile, derived: ratio and class (§4.3.1) | tape straight out from the front; inspection | M (placement of an opposing element; the generator measures free depth per part) | S for the human norm (ADA 804.2.1: 40 in between opposing kitchen faces; 804.6.3: the open dishwasher door must not block its clear floor space); H for robot outcomes · layout, contact, safety_constraint | core, v0.1 |
| `furniture.fixture.mirror_in_view` | enum {none, partial, large}, relative to a named camera; none | img | B, I (MuJoCo reflects only on a plane or a box's +Z face, and only the first reflective geom in a model) | C (Dobb-E) · visual | ext |

#### 4.3.1 Openable parts: interaction detail (v0.1 draft)

These attributes describe how a door or drawer looks and responds when a robot opens it. A home generator builds them per part, and skill fixtures test them. Every value is stored per part under its stable part ID. Ranges without a source are our working bounds.

**Handle types.**

| Value | Geometry | Opening action |
|---|---|---|
| `bar` | A straight pull on two posts, standing off the front | Grasp and pull |
| `knob` | A single-post knob, round or square | Grasp (pinch or wrap) and pull |
| `recessed` | A cup or slot cut into the front, flush with it | Hook fingers in and pull |
| `edge_pull` | A lip or channel along the front's top or side edge (finger pull, J-profile, handleless channel) | Hook fingers behind the edge and pull |
| `push_to_open` | No handle. A push latch opens the part a few millimetres when the front is pressed | Press the front, then grip the gap or edge and pull |
| `none` | No handle and no push latch | Grip the edge or the gap between fronts and pull |

- `push_to_open` requires `furniture.fixture.latch.type = push_latch`. A compiler that sets one sets the other and records both.

**Handle geometry.** `length` is the grip length (0 for knobs, recessed pulls and push-to-open). `projection` is the distance from the front face to the grip's outer face (0 when flush). `grip_diameter` is the bar's or the knob's diameter. `along` is the handle centre's position across the front, from the hinge edge (0) to the free edge (1); for drawers, from the left edge as seen facing the front. `height` is the position up the front, from its bottom (0) to its top (1). Nominal values: door {0.16, 0.035, 0.012, vertical, 0.9, 0.8 for a base cabinet and 0.2 for a wall cabinet}; drawer {0.16, 0.035, 0.012, horizontal, 0.5, 0.5}.

**Finish classes.** Classed by eye with one test: look at a ceiling light in the handle's surface. No reflection: `matte`. A blurred highlight: `satin` (brushed metal). A sharp image of the light: `polished` (chrome). The handle can be seen through: `transparent` (glass, clear acrylic). A front's own finish uses `surface.finish.optical` with the surface `<part>.front`. Every backend renders a class from the same material parameters, which the generator writes into the scene so they can be read back from the loaded model. Values are our working values, not measurements.

| Class | Physically based parameters (Isaac, Blender) | MuJoCo native renderer |
|---|---|---|
| `matte` | metallic 0, roughness 0.8 | specular 0.1, shininess 0.1 |
| `satin` | metallic 1, roughness 0.35 | specular 0.5, shininess 0.3 |
| `polished` | metallic 1, roughness 0.05 | specular 1.0, shininess 1.0; no environment reflection |
| `transparent` | transmission 1, index of refraction 1.5, roughness 0.02 | rgba alpha 0.3, specular 0.8, shininess 0.9; no refraction |

MuJoCo stores `metallic` and `roughness` on a material but its native renderer ignores them; they exist for physically based renderers. Its `reflectance` applies only to a plane or a box's +Z face, and only to the first reflective geom in a model ([MuJoCo XML reference](https://mujoco.readthedocs.io/en/stable/XMLreference.html), material attributes, fetched 2026-11-22). A generator writes both columns: `metallic` and `roughness` for physically based backends, `specular`, `shininess` and alpha for the native renderer.

**Hinges.** `side` names the edge the hinges are on, as seen by a person standing in front of the closed part: `left` or `right` for vertical hinges, `top` for lift-up flaps and wall-cabinet flaps, `bottom` for drop-down doors (ovens, dishwashers). `max_angle` is the angle at the hinge stop. Cabinet hinges are sold with stops at 107°, 110°, 125° and 155° ([Blum CLIP top BLUMOTION](https://www.blum.com/il/en/products/hingesystems/clip-top-blumotion/overview/), fetched 2026-11-22); 95° and 170° hinges appear in search summaries only **[unverified]**. `counterbalance` applies to `top` and `bottom` hinges: the share of the door's gravity torque at 45° that springs offset (1 = the door stays where it is left; 0 = it falls).

**Resistance, hinge stiffness and opening force.** Each quantity is defined by how it is measured with a force gauge at the handle, pulling slowly (about 0.05 m/s) along the opening direction.
- `open_force`: the peak force to start the part moving from closed, after any push or button release. It includes friction, the latch's hold and the soft-close pull.
- `running_force` (derived, recorded): the force to keep the part moving through the middle of its range, beyond every zone near closed. In the generator's model it is `open_force − latch.hold_force − soft_close.pull_force`, plus damping at the measuring speed. On a hinged part, this force times the handle's distance from the hinge axis is the hinge's running torque.
- `self_closing`: a spring pulls the part toward closed over its whole range. The generator records the spring's force at the handle at full open.
- `soft_close`: near closed, the part is pulled in with `pull_force` and slowed by extra damping, instead of striking the carcass.

Generators realise these as follows. Joint friction loss carries `running_force` (N for a slide; N·m for a hinge, at the handle's lever arm), with a stiff friction impedance so the simulated breakaway matches the record. Damping is recorded per part. The latch hold and the soft-close pull are zone forces near closed, built in MJCF as a zero-gain actuator whose affine bias is clamped by its force range: full force near closed, falling to zero across the second half of the zone. A self-closing spring is the joint's linear spring. All of these are in the model, so they are measured on the loaded model without runner code. The generator keeps `latch.hold_force + soft_close.pull_force` within 0.8 of `open_force`.

ADA sets 5 lbf (22.2 N) as the maximum force for operable parts (309.4) and for opening interior doors, excluding latch release (404.2.9). It exempts appliance doors and their latches from the operable-parts limit (804.6.2) ([2010 ADA Standards](https://www.access-board.gov/ada/), fetched 2026-11-22). These are design rules for accessible public buildings, not measurements of homes. We found no measured survey of opening forces in homes. The range above 22.2 N is for appliance doors and is our bound.

**Latches.** `magnetic`, `roller` and `gasket_seal` (refrigerator and freezer seals) hold the part closed with `hold_force` within `zone` of closed (degrees for a hinge, metres for a slide). Their hold is part of `open_force`; measured, it is the force gauge's peak less the running force. `push_latch` (with `push_to_open`), `button_release` (microwave doors) and `child_lock` need a separate action, and `release_force` is that action's force: the push at the front's centre, the button force, or the lock's release force.

**Drawer travel.** `travel` is the distance the front moves from closed to its stop; `fraction` is travel over the drawer box depth. Runner systems are sold as single extension (about three quarters of the box depth, our working value) and full extension (the whole depth), with nominal lengths from 250 to 650 mm ([Blum TANDEM](https://www.blum.com/gb/en/products/runnersystems/tandem/programme/), fetched 2026-11-22). Full extension needs `fraction` up to 1.0.

**Operating clearance.** `free_depth` is the distance straight out from the part's front, across its width, to the nearest solid taller than a person's step (0.20 m), or to the room's clear edge. This is how the generator measures it. `side_access` is `open` when the floor beside the part's operating zone is free for at least 0.6 m on at least one side, up to the front's plane; `blocked` when solids stand within 0.05 m of both sides of the zone, from the front's plane out to `free_depth`; `one_side` otherwise. The 0.6 m figure is our bound. For each robot profile (§5.1), the scene records:
- `reach`: the depth the part needs in front of it. For a drawer this is its travel. For a door it is its width plus its thickness, or width × sin(`max_angle`) + thickness when `max_angle` < 90°.
- `ratio` = (`free_depth` − `standing_depth`) / `reach`. Standing straight in front with its back to the obstacle, the robot can open the part to at most this fraction of its range. The hand needs room too, so the real limit is lower.
- `class`: `no_stand` when ratio < 0, `stand_not_open` when 0 ≤ ratio < 1, `fits` when ratio ≥ 1.

`ratio` and `class` are computed from the generator's per-part `free_depth` and its per-profile record of whether the robot, and the robot with the open part, fit the operating zone.

**Generation by backend.**

| Attribute | MuJoCo | Isaac Sim | Blender Cycles |
|---|---|---|---|
| `handle_type`, `handle_geometry` | Supported: primitives or convex meshes on the part's body | Supported | Geometry only |
| `handle_finish` matte, satin; front `matte`, `gloss`, `dark` | Approximate (Phong highlight) | Supported (RTX) | Supported |
| `handle_finish` polished; front `mirror` | Approximate: a highlight but no reflected scene (one planar reflector per model at most) | Supported (RTX reflections) | Supported |
| `handle_finish` transparent; front `transparent` | Approximate: alpha blending, no refraction | Supported (path-traced refraction) | Supported |
| Depth images of polished or transparent surfaces | Clean depth of the surface: a transparent geom reads as opaque (measured in our home generator); real sensors give holes or errors there (ClearGrasp; Dobb-E) | Needs a depth-sensor noise model **[unverified which Isaac sensor models cover this]** | No depth-sensor model |
| `hinge`, `travel`, `part_mass` | Supported (joint axis, range, body mass) | Supported | Not applicable |
| `resistance` running force, self-closing spring | Supported (joint friction loss, damping, stiffness) | Supported (joint friction and drive) **[unverified detail]** | Not applicable |
| `resistance.soft_close`, `latch` holding force | Supported: zero-gain actuator with clamped affine bias | Needs an equivalent drive or scripted force **[unverified]** | Not applicable |
| `latch` push and button release | Recorded; not simulated by our generator | Not checked | Not applicable |
| `operating_clearance` | Supported (placement, measured on the model) | Supported | Supported |

Variants that need a ray-traced renderer still run in MuJoCo, but their instances carry `fidelity.rendering: ray_traced` and a stated limitation. Results from the two renderers are reported apart and are not pooled for trust (§6, `fidelity`).

**Evidence used above.**
- DoorGym ([1908.01887](https://ar5iv.labs.arxiv.org/html/1908.01887), Tables 8 and 9, fetched 2026-11-22). Simulated room doors with three knob types. Success with ground-truth knob position, PPO, pull doors, over six robot and gripper set-ups: pull knob 0.68–0.95, lever 0–0.88, round 0–0.51. Its door joints randomise spring, damping and friction (Table 5), with no per-value results. These are room doors with latches, so they suggest, but do not measure, the cabinet case.
- RUM24 ([2409.05865](https://arxiv.org/html/2409.05865), §2.2, §5 and Appendix A.7, fetched 2026-11-22). 47/50 door and 47/50 drawer openings over 5 new environments each (Table 1, which sits under a heading about retries while §3.1 cites it as zero-shot), after doors with round knobs and drawers with knobs were left out of the data because the gripper could not open them. Named failure causes: unusual doors, two handles grasped together, sagging drawers, cloth drawers pulled right out.
- Dobb-E ([2311.16098](https://arxiv.org/html/2311.16098), §3.3.2, §3.3.3 and Table 2, fetched 2026-11-22). A shiny air-fryer handle gave bad depth and 0/10 in one home; the other door, drawer and appliance opening tasks scored 6/10 to 10/10 across 10 homes. Pulling a heavy door from high on the robot tipped it. Knob turning scored 13/20 over two homes.

### 4.4 `object`: objects and their states (ISO 34503 §11 dynamic elements, extended to object state)

| ID | Type; range or values; nominal | Measure | Generation | Relevance | Tier |
|---|---|---|---|---|---|
| `object.identity.category` | string: asset-library category, with an optional lexicon ID | img | M (asset query with licence filter) | B (Lin24: object diversity drives generalisation) · object_identity | core |
| `object.identity.novelty` | enum {training_instance, new_instance, new_category, unknown}, **per policy**; training_instance | from the policy's training-data card | M (asset swap) | A (2606.10366 real: unseen objects are the most damaging axis, 1.000; REALM: new object > known-object swap; GemBench L2 64.5%) · object_identity | core |
| `object.placement.pose` | struct {dx, dy: m; dyaw: deg} from nominal in the task frame; ranges per task; {0, 0, 0} | tape, img | M | A (LIBERO-PRO: collapse beyond ~0.2 units; LIBERO-Plus target pose; 2606.10366 real layout 0.679; REALM: pose second; Gao24) · layout | core |
| `object.appearance.colour_texture` | struct {hue_shift: deg [0, 180]; texture: library ID}; {0, default} | img | M | A (Colosseum real: object colour −82.6%; Xie23 sim: object texture as hard as camera; STAR-Gen visual-task-object axis) · visual | core |
| `object.geometry.scale` | float factor [0.7, 1.5]; 1.0 | calipers | M (scale with colliders) | mixed (Colosseum: size least; STAR-Gen: morphed objects large) · contact, layout | core |
| `object.physical.mass` | float kg [0.01, 2.0]; asset value | scale | M | under-measured (Colosseum inconclusive; REALM small; OK-Robot payload limits) · contact | core |
| `object.appearance.optical` | enum {matte, glossy, metallic, transparent, translucent}; matte | img | M~; B or I for physically correct appearance and depth | B (ClearGrasp); C (OK-Robot excluded "too translucent" objects; Dobb-E shiny handle) · visual | core |
| `object.state.articulation` | float fraction of joint range [0, 1] (lid, door, drawer, flap); 0 | img | M (initial joint state) | H (AI2-THOR "openable"; KitchenShift object done-state shift) · object_state | core |
| `object.state.fill` | struct {level: [0, 1]; content: {none, liquid, granular, solid}}; {0, none} | img (partly) | M~ (mass and centre-of-mass shift; spill as a checker event); I for liquid particles **[unverified for MuJoCo]** | B (VLA-Arena StatePreservation suite: empty, half, full; per-level results not read) · object_state, safety_constraint | core |
| `object.physical.deformability` | enum {rigid, articulated, cloth, soft, cable, granular}; rigid | img | M~ (MuJoCo flex **[unverified]**); I | B (2511.04665: physics fidelity changed sim–real agreement on rope); C (RUM24: bag pick-up 32% of failures) · contact | core |
| `object.physical.fragility` | struct {class: {robust, breakable, crushable}; break_force: N}; robust | product data | M (a checker force threshold; no fracture simulation) | B (STAR-Gen hidden-object axis names fragility; VLA-Arena fragile obstacles) · safety_constraint, contact | core |
| `object.state.other` | set ⊆ {dirty, on, hot, cold, wet}; {} | img (partly) | M (appearance plus checker metadata; no heat simulation) | H (AI2-THOR states) · object_state | ext |

### 4.5 `clutter`: density, arrangement and occlusion

| ID | Type; range or values; nominal | Measure | Generation | Relevance | Tier |
|---|---|---|---|---|---|
| `clutter.surface.density` | float fraction of support area covered within the workspace [0, 0.8]; 0.1 | top-down photo | M (batch placement with collision check) | A (OK-Robot real: manipulation error 25% → 13% after decluttering, success 58.5% → 82.4%; Colosseum: distractor count among the top three). Against: Xie23 real 80.6%; LIBERO-Plus "ignore distractors well" · visual, layout | core |
| `clutter.distractor.similarity` | enum {dissimilar, same_colour, same_category, same_instance}; dissimilar | img | M (asset query) | C (OK-Robot: navigation error 15% → 4% as ambiguous objects were removed; Dobb-E: identical-looking locations 0/10). Hypothesis: similarity, not presence, drives the distractor effect · object_identity | core |
| `clutter.visibility.target_occlusion` | float fraction of target pixels hidden from a named camera [0, 0.9]; 0 | render or photo | M (placement under a ray-cast visibility constraint) | B (STAR-Gen viewpoint axis includes partial occlusion); LIVIN names occlusion · visual | core |
| `clutter.surface.approach_clearance` | float m [0.01, 0.2], minimum free space around the target in approach directions; 0.1 | ruler | M | C (OK-Robot: difficult grasp poses); `spec/v0.md` Example 3 · contact, safety_constraint | core |
| `clutter.floor.count` | int [0, 20] small objects on the floor in the path or workspace; 0 | count | M | B (Scenic3: up to 44% of vacuum runs falsified at 16 toys, sim); C (Sung10: toys "eaten") · layout, safety_constraint | ext |
| `clutter.surface.arrangement` | enum {organised, scattered, piled, stacked, nested, in_container}; organised | img | M (physics settle) | H · layout, contact | ext |

### 4.6 `light`: lighting (ISO 34503 §10.4 illumination)

| ID | Type; range or values; nominal | Measure | Generation | Relevance | Tier |
|---|---|---|---|---|---|
| `light.ambient.illuminance` | float lux at the workspace [1, 2000]; 200 | lux meter; img mean luma as a proxy | M (light intensity). MuJoCo lights are not photometric, so sim controls image statistics and real records lux (§10) | mixed (Colosseum: lighting among the top three; Xie23 real 83.3%; LIBERO-Plus 61.0). Homes: living room evening 3–410 lx, median 23; kitchen 6–485 lx, median 104 (IES18). IEC 62885-7 tests at 200 ± 50 lx · visual | core |
| `light.ambient.cct` | float K [1800, 6500]; 4000 | colour meter | M | B (Colosseum light colour; LIBERO-Plus diffuse colour; VLA-Arena V1). Home sources 1,800–4,600 K (IES18) · visual | core |
| `light.key.direction` | struct {azimuth, elevation: deg} of the dominant source relative to the workspace | compass or estimate | M | B (LIBERO-Plus light-direction sub-factor) · visual | ext |
| `light.daylight.sun` | struct {latitude: deg; date; local_time; window: anchor} → sun vector and irradiance through the window | computed | M~ (directional light from the computed vector); B or I for realistic daylight | H · visual | core |
| `light.artefact.glare` | float fraction of saturated pixels in a named camera [0, 0.3], from a specular highlight or a source in view; 0 | img | B, I; M~ (crude specular) | B (RoboLab: π0 0% under overexposure; LIBERO-Plus specular sub-factor) · visual | core |
| `light.artefact.shadow` | struct {coverage of target or workspace: [0, 1]; caster: {robot_self, person, furniture, window_frame}}; {0} | img | M (shadow maps); B or I for soft shadows | B (RoboLab: π0 0% under shadows); C (Dobb-E: the arm's own shadow caused failures until a light was added) · visual | core |

### 4.7 `people` (ISO 34503 §11.1 traffic agents; PAS 1883:2025 vulnerable road users)

| ID | Type; range or values; nominal | Measure | Generation | Relevance | Tier |
|---|---|---|---|---|---|
| `people.presence.count` | int [0, 4] in the room; 0 | count | I (animated people); M~ (static or keyframed mannequins) | H · visual, safety_constraint | ext |
| `people.proximity.min_distance` | float m [0, 3] from the robot's reach envelope; 3 | tape or tracking | I; M~ | H; ISO 13482 §5.14 "lack of awareness of robots by humans" (heading) · safety_constraint | ext |
| `people.activity.motion` | enum {static, walking_past, crossing_path, reaching_into_workspace, handing_object}; static | video | I; M~ (kinematic proxy) | B as a proxy (VLA-Arena dynamic obstacles: safety cost rises with level) · safety_constraint, visual | ext |
| `people.presence.age_class` | enum {adult, older_adult, child_6_12, child_under_6}; adult | record | I (child assets **[unverified]**) | C (Sung10: children chased the robot and tried to jump over it); UL 3300 "user classes" · safety_constraint | ext |

### 4.8 `pets`

| ID | Type; range or values; nominal | Measure | Generation | Relevance | Tier |
|---|---|---|---|---|---|
| `pets.presence.type` | enum {none, cat, dog_small, dog_large, other}; none | record | — (no animated pet library); M for a static mesh proxy | C (Sung10: pets followed the robot) · safety_constraint, visual | ext |
| `pets.activity.motion` | enum {resting, wandering, following_robot, contacting_robot}; resting | video | —; M~ (scripted rigid proxy) | H · safety_constraint | ext |
| `pets.items.set` | set ⊆ {food_bowl, water_bowl, toy, waste, hair}; {} | img | M (objects); M~ (waste and hair as decals or small objects) | C (Sung10: pet hair) · layout, safety_constraint | ext |

### 4.9 `dynamics`: changes during a task

Each dynamic attribute carries a trigger: a spec v0 stage (`acquire`, `transport`, `finish`, or any declared stage), a time in seconds, or an event (§6 `timing`).

| ID | Type; range or values; nominal | Measure | Generation | Relevance | Tier |
|---|---|---|---|---|---|
| `dynamics.object.target_displaced` | struct {distance: m [0.02, 0.3]; trigger}; none | video | M (kinematic edit at the trigger) | H; C (RUM24: tissue box moves with the gripper) · layout | core |
| `dynamics.agent.obstacle_enters` | struct {entity; speed: m/s [0.1, 1.5]; trigger} into the path or workspace; none | video | M (scripted object); I (agents) | B (VLA-Arena dynamic obstacles and distractors) · safety_constraint, layout | core |
| `dynamics.ambient.light_change` | struct {delta_lux; trigger} (switch, curtain); none | lux log | M | H · visual | ext |
| `dynamics.agent.human_intervention` | enum {takes_object, hands_object, closes_door_or_drawer, new_instruction, cancel} with trigger; none | video | M (scripted edit or instruction change) | H · instruction, object_state | ext |
| `dynamics.object.support_moves` | struct {support mass: kg; friction} for a support or container that moves on contact; none | push test | M | C (RUM24) · contact | ext |

### 4.10 `hazard`

A hazard attribute also proposes a `never` constraint template (`spec/v0.md` §4). Failure search scores violations of it as constraint failures.

| ID | Type; range or values; nominal | Measure | Generation | Relevance | Tier |
|---|---|---|---|---|---|
| `hazard.liquid.spill` | struct {area: m² [0, 0.5]; location: {floor_path, worktop, near_target}; friction_scale: [0.1, 1]}; none | img | M (decal plus friction patch); I for fluids | H · contact, safety_constraint | ext |
| `hazard.thermal.heat_source` | struct {type: {stove_on, oven_open, kettle, candle, iron}; clearance: m}; none | img | M (object plus keep-out constraint; no heat simulation) | B (VLA-Arena HazardAvoidance with a lit candle) · safety_constraint | core |
| `hazard.sharp.edge` | struct {object: {knife, scissors, broken_glass}; edge orientation; location}; none | img | M (keep-out on the edge geometry) | B (VLA-Arena CautiousGrasp: grasp by the handle) · safety_constraint | core |
| `hazard.entangle.cord` | struct {crosses: {path, workspace, target}; slack: m; attached_appliance: bool}; none | img | M~ (cable composite or flex **[unverified]**); I | C (Sung10: wires picked up before runs; the paper's design implication is to prevent robots "getting stuck in wires") · contact, safety_constraint | core |
| `hazard.ingest.small_object` | int count of loose objects below the robot's intake or pinch size; 0 | count | M | C (Sung10: "eating toys") · safety_constraint | ext |
| `hazard.tip.unstable_object` | struct {height_to_base: [1, 6]; distance to trajectory: m}; none | tape | M | C (Sung10: "breaking a full-sized mirror"; a book placed under a lamp); B (VLA-Arena fragile static obstacles); `spec/v0.md` Example 3 · safety_constraint | core |
| `hazard.fall.drop_edge` | float m from the path or placement to a stair or worktop edge; none | tape | M | H; ISO 13482 §5.16 (heading) · safety_constraint | ext |

### 4.11 `sensing`: conditions in the home that affect sensing (ISO 34503 §10.3 particulates)

| ID | Type; range or values; nominal | Measure | Generation | Relevance | Tier |
|---|---|---|---|---|---|
| `sensing.camera.occlusion` | struct {camera; fraction: [0, 0.6]; occluder: {hand, cloth, hair, film}}; none | img | M (near-field geometry) | B (STAR-Gen viewpoint and occlusion; LIBERO-Plus third-person blackout, labelled out-of-distribution; MolmoSpaces evaluation perturbation) · visual | core |
| `sensing.camera.lens_contamination` | struct {type: {smudge, droplets, dust}; severity: [0, 1]}; clean | img | M (image-space post-process, out-of-distribution caution) | B as a proxy (LIBERO-Plus glass blur and fog) · visual | ext |
| `sensing.air.particulates` | struct {source: {steam, smoke, dust}; optical_depth: [0, 2]}; none | img | B, I (volumetric); M~ (image-space fog) | H · visual | ext |
| `sensing.camera.image_degradation` | struct {type: {motion_blur, defocus, noise, low_light_noise}; severity: [0, 1]}; none | img | M (post-process) | B (LIBERO-Plus noise 50.8%; VLA-Arena V4: −50.5% average) · visual | core |
| `sensing.camera.exposure_colour` | struct {auto_exposure: bool; wb_offset: K; colour_transform}; locked | camera settings | M | B (2511.04665: removing colour alignment cut push-T agreement r from 0.915 to 0.529); `spec/v0.md` §6 locks exposure · visual | core |
| `sensing.audio.noise` | float dB(A) [30, 80] at the robot microphone, for spoken instructions; 35 | sound meter | record only (no audio simulation in v0) | H · instruction | ext |

### 4.12 `robot`: conditions internal to the robot (ISO 34503 Annex A operational design conditions)

These are robot-side conditions that occur in homes (a bumped camera mount, a different start pose, the base parked elsewhere). They are listed because they are among the highest-impact variations measured.

| ID | Type; range or values; nominal | Measure | Generation | Relevance | Tier |
|---|---|---|---|---|---|
| `robot.camera.pose_offset` | per camera struct {translation: mm [0, 60]; rotation: deg [0, 10]}; {0, 0} | calibration | M | A (LIBERO-Plus: worst of seven, 28.5%; Xie23 real: worst, 45.8%; WARP-VLA: 2 cm/3° costs 4.7 points, 4 cm/6° costs 74; VLA-Arena V3). 3D policies less affected (Colosseum) · visual | core |
| `robot.arm.initial_state` | float joint offset deg [0, 20] from nominal; 0 | joint readout | M | B (LIBERO-Plus 30.5%) · layout | core |
| `robot.base.pose` | struct {dx, dy: m; dyaw: deg} of the base or mount relative to the workspace; {0, 0, 0} | tape | M | B (Xie23: table position as hard as table texture; Gao24: table height) · layout | core |

### 4.13 `task`: task context

| ID | Type; range or values; nominal | Measure | Generation | Relevance | Tier |
|---|---|---|---|---|---|
| `task.instruction.form` | enum {canonical, paraphrase, synonym_1, synonym_2, synonym_3, synonym_4, added_context, indirect_need, world_knowledge}; canonical | record | M (text) | A (STAR-Gen real: semantic generalisation weakest; REALM: world knowledge and affordances strongest; VLA-Arena W1–W4). Plain paraphrase small (LIBERO-Plus 65.3%; 2606.10366 real 0.241) · instruction | core |
| `task.instruction.referent` | enum {canonical, other_present_object, by_property, by_spatial_relation}; canonical | record | M | A (LIBERO-Plus: swapping the target object gives near-zero success; STAR-Gen noun grounding and multi-object referencing; REALM) · instruction, object_identity | core |
| `task.structure.horizon` | int subgoals [1, 10]; 1 | record | M | A (GemBench L4 17.4%; VLA-Arena long-horizon collapse beyond L0, sim and real) · long_horizon | core |
| `task.habit.location_prior` | enum {habitual, atypical, inside_container, out_of_reach}; habitual | user interview | M (placement) | C (OK-Robot: middle of a bed, high shelves); H for habits · layout, object_identity | ext |
| `task.habit.user_convention` | string list of household preferences (where items are kept, how they are placed, what "tidy" means), written as goal predicates | user interview | M (`spec/v0.md` §3 goal predicates) | H · instruction, long_horizon | ext |

## 5. Anchors and placement predicates

**Anchors.** Scenic 3 can already place objects relative to the robot, other objects and a camera's view. What this spec adds is a convention: anchoring placement to the goal and to a stored reference path, so every policy sees the same scene.

| Anchor | Resolves to |
|---|---|
| `robot.base` | Base or mount frame |
| `robot.reach` | Reach envelope (convex approximation) |
| `robot.reference_path` | For mobile robots, the planned base path. For arms, the end-effector path. Both come from a **reference trajectory stored with the base scenario** |
| `task.target`, `task.receptacle` | Objects named in the base scenario's goal predicates (`spec/v0.md` §3) |
| `task.workspace` | Support-surface region under the target and receptacle, plus a declared margin |
| `camera.<name>` | A named camera's pose and frustum |
| `window.<id>`, `door.<id>`, `light.<id>` | Scene elements by ID |
| `task.part` (v0.1) | The door or drawer named in the base scenario's goal; `task.part.handle` and `task.part.front` are its handle and front geoms |
| `zone.<part>` (v0.1) | The floor a part's swing or travel needs in front of it (the generator's `operating_zone`) |
| `keep.<door>.swing`, `keep.<door>.<room>`, `keep.<stairs>.foot` (v0.1) | Keep-clear zones (§4.1 definitions) |
| `robot.standing_depth`, `robot.width`, `robot.hand_depth` (v0.1) | Values from the scenario's robot profile (§5.1) |

**Anchors never come from the policy under test.** If a path anchor came from each policy's own rollout, the scene would differ by policy, and two policies would not see the same variance. The base scenario therefore carries a `reference_path` with its hash: a scripted or planner-generated reference, or the nominal-reference episode named by `nominal_ref`. Every policy then gets the same scene for the same factor vector.

**Reference path format (v0.1 draft).** A planner makes each path for one robot profile, so a base scenario names its profile and its path together.

```yaml
reference_path:
  kind: base_polyline        # base_polyline (mobile robots: floor points) | ee_polyline (arms: end-effector points)
  frame: scene               # the scene frame: x plan east, y plan north, z up, metres
  points: [[x, y], ...]      # millimetre precision; [x, y, z] for ee_polyline
  start: <room ID or pose ID>
  goal: <room ID or pose ID>
  profile: <robot profile ID>
  clearance: {radius: 0.25, margin: 0.02}   # what the path was planned to keep from obstacles
  planner: visibility        # visibility | grid | scripted | episode:<nominal_ref episode ID>
  hash: <SHA-256 of the canonical JSON of points>
```

Fractions in `crosses(..., at=[f0, f1])` are fractions of the polyline's length. When the profile has no path (the generator records the blocking elements instead), `reference_path` is null and cards that require it are reported as `base requirement unmet`, never as policy failures.

**Expressions** in `require`, `prefer` and `parameters` may read anchor values with dot access, for example `task.part.travel` or `robot.standing_depth` (v0.1).

**Placement predicates.** These add to the `spec/v0.md` §3 grammar and reuse `on` and `inside` from it. Distances are in metres and angles in degrees.

| Predicate | Meaning | Scenic 3 | Infinigen Indoors |
|---|---|---|---|
| `on(a, b)`, `inside(a, b)` | As in spec v0 | `on` specifier; containment | `StableAgainst`, `SupportedBy` |
| `near(a, b, d)` | Centre distance ≤ d | `distance to` in `require` | distance term |
| `clear_of(a, b, d)` | Surface distance ≥ d | `require (distance from a to b) >= d` | `min_distance` |
| `close_to(a, b, d)` (v0.1) | Surface distance ≤ d | `require (distance from a to b) <= d` | distance term |
| `front_gap(p, b, d, tol=0.002)` (v0.1) | The free depth straight out from part p's front, across its width, to b's nearest face, equals d within tol | polyline region plus distance in `require` | none |
| `crosses(a, path, at=[f0, f1], angle=[lo, hi])` | Entity a intersects the path between path fractions f0 and f1, at the given angle | polyline region plus `intersects` in `require` | none; resolve to fixed geometry first |
| `in_view(a, cam, min_frac)` | At least min_frac of a's pixels are visible from cam | `visible from`; ray-traced visibility | none |
| `occludes(a, target, cam, frac=[lo, hi])` | a hides between lo and hi of target's pixels from cam | `can see` with occlusion, in `require` | none |
| `left_of`, `right_of`, `in_front_of`, `behind(a, b, frame)` | Relative position in an anchor's frame | specifiers of the same names | relation terms |
| `facing(a, b, tol)` | a's forward axis within tol of the direction to b | `facing toward` | none |
| `within_reach(a)` | a inside `robot.reach` | containment in a region | none |
| `count(class, region) op n` | Number of entities of a class in a region | counting in `require` | count constraints |

### 5.1 Robot profiles (v0.1 draft)

A home is valid when a person can live in it; whether a robot can get around it is measured per robot profile and never required. A scenario names one profile as its embodiment profile, and every quantity relative to a robot (access, reference path, clearance ratio, feasibility) is derived for that profile.

```yaml
robot_profile:
  id: base_r0.25
  footprint: {shape: disc, radius: 0.25}   # disc only in v0.1
  max_step: 0.02                           # m; taller geometry blocks the robot
  height: 1.5                              # m; geometry lower than this blocks the robot
  standing_depth: 0.50                     # m; footprint depth along the approach axis in its operating posture (a disc: the diameter)
  width: 0.50                              # m; footprint width across the approach axis (a disc: the diameter)
  hand_depth: 0.15                         # m; least space between the body's front and a part's front at which the robot can still hold the handle
  geom_sets:                               # names the skill-fixture checker uses
    body: <robot geoms other than hand and ground contact>
    hand: <end-effector geoms, fingers included>
    fingers: <finger pad geoms>
    ground_contact: <wheel or foot geoms>
```

- `id`, `radius`, `max_step` and `height` are the fields of a basic robot profile. The other fields are optional. For a disc, `standing_depth` and `width` default to the diameter.
- `hand_depth` is declared by the robot maker or measured on the robot model. The default of 0.15 m is our bound, not a measurement.
- Every scene records, per profile: reachable floor, missing paths with their blocking elements, doors narrower than the robot, thresholds above its step, and the operating clearance of every part (§4.3.1). This is the generator's per-profile record.

## 6. Variance card format

A card is one YAML document. Fields outside `compile` are metadata. Changing them does not change generated scenes or the card hash.

```yaml
card_version: v0
id: <string, unique in the card library>
title: <plain one-line name>
status: draft                      # draft | compiled | validated | retired
summary: <one or two plain sentences: what the condition is>
applies_to:
  embodiment_class: [fixed_arm, mobile_manipulator, mobile_base, humanoid]
  task_family: [<e.g. pick_place, open_articulated, wipe>]
  room_type: [<structure.room.type values>]
origin:                            # provenance
  kind: literature                 # field_report | video | literature | idea | search_finding | coverage_gap
  source: <URL, file path or issue>
  observed_in_real_home: true      # was this condition seen in a real home?
  media_licence: <licence of any image or video used, or null>
  recorded: 2026-11-22
  recorded_by: <role or organisation>
classification:
  channels: [behavior]             # observation | instruction | behavior, relative to the base task
  attributes: [<attribute IDs set by this card>]
compile:                           # hashed: SHA-256 of canonical JSON of this block
  base_requirements:               # what the base scenario must provide
    anchors: [robot.reference_path]
    embodiment_profile: optional   # required | optional (v0.1): whether the card needs a robot profile (§5.1)
    part_kind: null                # door | drawer | null (v0.1): the kind task.part must be
  sets:                            # attribute values or distributions (the variance itself)
    - {attr: <id>[.<field>], dist: {uniform: [lo, hi]}}   # uniform | normal | choice | value
  holds:                           # attributes pinned for this card; unlisted ones keep the base scene's values
    - {attr: <id>, value: <v>}
  entities:                        # new things the card adds
    - {name: <local name>, asset: {class: <category>, licence_filter: commercial_safe}}
  placement:
    require: [<predicate>, ...]    # hard; every instance satisfies all
    prefer:                        # soft; each holds with probability p (Scenic require[p])
      - {p: 0.8, expr: <predicate>}
    noise: {entities: [<names>], scale: 1.0}   # Scenic mutate: Gaussian on position and heading
  edits:                           # ordered; applied after placement
    - {op: add, entity: <name>}
    # ops: add | remove | move | set_material | set_joint | set_physics | set_light |
    #      set_camera | attach_motion | post_process | set_instruction
  timing:                          # only for dynamic variances
    trigger: {stage: transport}    # stage | t (seconds) | event
    duration: null
  parameters:                      # emitted as spec v0 factors; search moves these
    - {name: <factor>, from: <attr>[.<field>], low: , high: , nominal: , kind: float, unit: , failure_type: }
  constraints:                     # spec v0 never constraints added by the card
    - {id: <id>, never: <predicate expression>, after: start, failure_type: safety_constraint}
  feasibility: null                # v0.1: {rule: <rule ID>, ...params}; computes each instance's feasibility status
                                   #   per robot profile
expected_handling:                 # v0.1, not hashed: plain description of good and bad behaviour per feasibility status
  feasible: <sentence>
  infeasible: <sentence>
  ambiguous: <sentence>
suspected_failures:                # updated as evidence arrives; not hashed
  - failure_type: contact
    stage_class: T                 # G | T | P per spec v0 §5, if known
    description: <plain sentence>
    evidence: {grade: C, refs: [<ref>]}
    status: suspected              # suspected | reproduced_sim | reproduced_real | refuted
fidelity:
  physics: <minimum tier>
  rendering: rasterised            # rasterised | ray_traced
  backends: {mujoco: supported, isaac: supported, blender: n/a}   # supported | approx | unsupported
  limitation: <plain sentence, or null>
validity_gates: [stability, intersection, placement_satisfied]
real_check:                        # how to set this up or measure it in a real home (spec v0 §6)
  setup: <plain instruction>
  measure: [<instrument or method>]
trust: []                          # filled by calibration only (spec v0 §7), never by the author
links: {parent: null, variants: [], supersedes: null}
```

**Rules.**
- `sets` is the variance. `holds` pins other attributes. Every attribute the card does not name keeps the base scene's value. All three are recorded, so effects can be attributed.
- `parameters` lists every free quantity in `sets` and `placement` that search may move. If the author omits it, the compiler derives it from `sets` (one factor per distribution, named `<card id>.<attr>`). Factor `failure_type` comes from the attribute's first failure type, unless set.
- A card adds a factor `variance_seed` (kind int). The seed drives asset choice and placement sampling. This keeps a scene a pure function of factor values (`spec/v0.md` §2).
- `trust` follows `spec/v0.md` §7: real paired data only, and never synthetic data.
- Attributes outside the registry use an `x.` prefix (§11).

## 7. Compilation

**Inputs:**
- the base scenario (spec v0 document and its hash)
- the card's `compile` block and its hash
- the factor vector u ∈ [0,1]^d (spec v0 unit-cube mapping)
- the asset-library version

**Steps:**
1. **Check base requirements.** Resolve anchors from the base scenario and its stored reference trajectory. Stop if a required anchor is missing.
2. **Map factors.** Map u to values through the `parameters` bounds, and read `variance_seed`.
3. **Instantiate entities** by seeded asset query under the licence filter.
4. **Place.** Draw one coin per `prefer` predicate from the variance seed, before placement; a predicate is enforced when its coin falls below its p. Sample until every `require` and every enforced `prefer` holds. Retries keep the coins (v0.1 draft). Re-drawing the coins on each attempt favours attempts with fewer preferences enforced, which pushes the realised share below p. The attempt limit is set by the engine. If no sample succeeds, the instance is recorded as `infeasible`. That is a property of the card and the base scene, and it is never counted as a policy failure. Infeasible instances drop out, so the realised share among compiled instances can still differ from p; the compile report states it.
5. **Apply `edits`** in order. Attach `timing` hooks to the runner. Some attributes are realised through another, and the compiler records the edit it actually made. On an existing home, `structure.window.geometry.azimuth` is set by turning `structure.home.orientation`, which changes no geometry (v0.1).
6. **Run the validity gates:**
   - stability and intersection (MolmoSpaces' tests)
   - `placement_satisfied` (re-check every `require` on the settled scene)

   A failed gate makes the instance invalid, not a policy failure.
7. **Emit** the backend scene (MJCF or USD), the v0 factor list and values, and the scene hash.

**Episode record.** The spec v0 §8 record gains one block:

```json
"variance": {"card_id": "rug_edge_on_path_001", "card_hash": "…", "base_scenario_hash": "…",
             "values": {"rug_edge_height": 0.018, "crossing_fraction": 0.42, "variance_seed": 7},
             "reference_path_hash": "…", "asset_library": "…", "validity": {"stability": true,
             "intersection": true, "placement_satisfied": true}, "infeasible": false,
             "profile": "base_r0.25", "feasibility": null}
```

`profile` and `feasibility` are v0.1 fields. `feasibility` is null unless the card or scenario declares a rule; then it is `{"status": "feasible" | "infeasible" | "ambiguous", "rule": "…", "inputs": {…}}`, with the measured inputs the rule used.

**Compile targets.**

| Card element | Scenic 3 | Infinigen Indoors | Direct MJCF |
|---|---|---|---|
| `sets` distributions | Scenic distributions (`Range`, `Normal`, `Options`) | sampled by us before the solve, passed as constants | our sampler |
| anchors | objects and regions built from the base scene and reference path | fixed geometry added to the solver state; Infinigen has no task anchors | coordinates |
| `require` | `require` | hard constraint | rejection sampling |
| `prefer {p}` | `require[p]` (p must be a literal) | soft-constraint weight. The semantics differ: a probability against a cost weight. The compiler records the mapping used | probabilistic rejection |
| `noise` | `mutate … by scale` | none | Gaussian noise |
| `timing` | behaviours and monitors; `terminate when` | none (static scenes) | runner hooks |
| `constraints` | `require always` monitors | none | spec v0 checker |

A Scenic or Infinigen target is optional. The direct path compiles to MJCF, because we found no Scenic MuJoCo interface and Infinigen exports whole scenes only as USD.

## 8. Declared operating domain (optional block)

A robot maker or tester can declare the home conditions a robot is designed for. The form follows ISO 34503 §12.4 (inclusion, exclusion, conditional) and Shakeri's `attribute ⋈ value` statements.

```yaml
declared_domain:
  robot: <id and version>
  mode: restrictive                 # restrictive: unlisted attributes are outside the domain (recommended, see §10)
  include:
    - "structure.room.type in {kitchen, living}"
    - "light.ambient.illuminance >= 50"
    - "surface.rug.edge.edge_height <= 0.015"
  exclude:
    - "people.presence.age_class == child_under_6"
  conditional:
    - {if: "people.proximity.min_distance < 0.5", then: "dynamics.agent.obstacle_enters == none"}
```

The evidence report can then say which declared conditions were tested, at what coverage and with what trust. Conditions outside the domain are reported separately as out-of-domain findings.

### 8.1 Operating conditions: a maker's input to a test plan

Status: draft. A maker sends little more than the conditions its robot should operate in, and we compile them into a test plan of generated homes. The input is one JSON (or YAML) document. It wraps the declared domain above and adds what a narrow robot needs to say: what it does and where it enters the home.

```json
{"record": "operating_conditions", "spec_version": "v0", "id": "<1-64 letters, digits, _ . ->",
 "robot": {"id": "…", "version": "…", "embodiment_class": "fixed_arm | mobile_manipulator | mobile_base | humanoid",
           "profile": {"id": "…", "radius": 0.10, "max_step": 0.0, "height": 0.45}},
 "entry": "worktop | room | home",
 "tasks": [{"id": "pick_mug_from_counter", "family": "pick_place", "objects": ["mug"], "surfaces": ["counter"]}],
 "declared_domain": {"mode": "restrictive", "include": ["…"], "exclude": ["…"], "conditional": [{"if": "…", "then": "…"}]},
 "notes": "…"}
```

- **`tasks`** is the closed list of what the robot does ("X, Y and Z"). Each task's `family` selects a base scenario in the generator (the compiler supports `pick_place` and `navigate`, both on a kitchen-counter base scenario). Cards apply only when their `applies_to.task_family` matches (or is `any`).
- **`entry`** is where the robot enters the generator's layer tree: `worktop` for a tabletop arm, `room` or `home` for robots that move. Variation is meant to start at that layer. The runner regenerates the whole home for every test, and the plan says so.
- **`robot.profile`** is the robot profile of §5.1; its `embodiment_class` selects cards by `applies_to`.
- **Statements.** `<attr> in {a, b}`, `<attr> not in {…}`, `<attr> in [lo, hi]`, `<attr> <= x` (and `>=`, `<`, `>`), `<attr> == v`, `<attr> != v`. Includes intersect. Excludes name values (`==` or `in {…}`); numeric attributes are bounded with includes. A conditional applies its `then` wherever its `if` holds.
- **Mode.** In `restrictive` mode the domain is what is listed. Attributes the maker does not list still vary as the generator's baseline (homes people could live in); the plan records them as baseline, not declared.

### 8.2 Test plan

Status: draft. Our test-plan compiler turns operating conditions, the card library and a seed into a test plan: a list of entries, each a generator spec (constraints file, blueprint seed, furnishing seed, robot profile, the task's base scenario, and optionally one card with its factor vector and variance seed). It works in two steps. The **design** draws every entry's conditions and first seeds; it is reproducible from (conditions, card library, seed, counts, compiler version) and hashed as `design_sha256`. The **feasibility step** then asks the generator, entry by entry, whether the condition can occur in the drawn home, and draws again where it cannot (below). The plan's `plan_sha256` covers both. Four parts, always reported separately:

| Part | What it is for | How entries are drawn |
|---|---|---|
| `broad` | A representative success rate across the declared conditions | Latin hypercube over the declared numeric attributes, each cut into 5 strata, the generator sampling inside the stratum; categorical attributes cycle through their allowed values; entries alternate between the base scenario and each applicable card, with factors drawn inside the declared ranges |
| `search_seeds` | The starting design of failure search | Halton points over the same coordinates and the card factors. The search's own episodes are added when it runs; they are not in the plan |
| `library` | Targeted known hazards | Each applicable card at its nominal factors and at every corner of its factor box as narrowed by the declared domain |
| `stress` | Behaviour when a home breaks the declared conditions | One declared numeric attribute per entry in a band just outside its declared range (25% of the declared width beyond the bound, inside the generator's range); every other attribute in its declared range. Labelled out of domain and never pooled with the other parts |

- **Coverage.** The plan lists declared attributes the generator sets (by constraints or by cards), declared attributes it does not set (`not_generated`), and conditionals it enforced or could not enforce. An evidence report states the `not_generated` list as untested.
- **Feasibility: each condition only where it can occur.** A plan never contains a scene in which its condition cannot happen. For each entry, the generator is asked first whether the factors alone allow the condition (for the sun card, the sun's elevation from its latitude, date and time; below the horizon, new factors are drawn inside the declared ranges and conditionals), then whether the drawn home does: it must sample and furnish, its base scenario must carry the anchors the card needs (a kitchen window), and the card's placement and requires must hold (sunlight through the window reaching the target). A home that fails is replaced by the next seeds, keeping the factors, up to 40 draws. Every infeasible draw is counted per condition (the card, or `base` for the home alone) with its reason, and the counts are a plan statistic (`feasibility.per_condition`). An entry that the generator declares impossible (an invalid result of kind `infeasible`: a request no home can meet), or that has no feasible draw in 40 (the generator's `not_found` in every home drawn, as for a furniture density above what the drawn homes reach), stays in the plan labelled `expected_infeasible` with its reason, is never run, and is counted per part; nothing is dropped silently. A library design point that is infeasible by its factors alone is dropped before entries are assigned and listed. Each feasible draw records the values its home actually has (furniture density, every doorway's width and threshold, door angles, windows, and the card's attribute values); `coverage.generated_ranges` gives, per declared numeric attribute, the lowest and highest value generated in the in-domain parts and lists the rest of the declared range as untested (a gap is listed only when it is wider than 2% of the declared width or one generator grid step, whichever is larger; a declared attribute the measurement does not read says "not measured"; a generated value outside its declared range is flagged and kept out of the generated range). The reach comes from the plan's own draws, not from a generator constant. A condition that is rarely feasible inside the declared conditions is a finding of the plan, reported with its share of feasible draws.
- **Generation and validation**: every entry is regenerated from its recorded seeds; it is valid when the card compiles, the home checks pass, and a second generation gives identical hashes. Anything else is a defect to report, never retried.

## 9. Worked cards

Cards 1 to 3 are v0 cards chosen for an end-to-end compile; card 4 is a v0.1 draft.

**Card 1: rug edge across the robot's path** (mobile robots; from a field study).

```yaml
card_version: v0
id: rug_edge_on_path_001
title: Rug edge across the robot's path
status: draft
summary: A loose rug lies across the route the robot must drive, with a raised or fringed edge.
applies_to: {embodiment_class: [mobile_manipulator, mobile_base], task_family: [any], room_type: [living, bedroom, hallway]}
origin: {kind: literature, source: "https://faculty.cc.gatech.edu/~beki/j16.pdf", observed_in_real_home: true,
         media_licence: null, recorded: 2026-11-22, recorded_by: Robotense}
classification: {channels: [behavior, observation], attributes: [surface.rug.edge]}
compile:
  base_requirements: {anchors: [robot.reference_path]}
  sets:
    - {attr: surface.rug.edge.present, dist: {value: true}}
    - {attr: surface.rug.edge.edge_height, dist: {uniform: [0.003, 0.03]}}
    - {attr: surface.rug.edge.fringe, dist: {choice: [true, false]}}
    - {attr: surface.rug.edge.anchored, dist: {value: false}}
  entities:
    - {name: rug, asset: {class: rug, licence_filter: commercial_safe}}
  placement:
    require:
      - "on(rug, floor)"
      - "crosses(rug.edge, robot.reference_path, at=[0.3, 0.7], angle=[30, 90])"
    prefer:
      - {p: 0.7, expr: "clear_of(rug, furniture, 0.1)"}
  edits:
    - {op: add, entity: rug}
    - {op: set_physics, entity: rug, friction: {material: carpet_low}, edge_height: {from: surface.rug.edge.edge_height}}
  parameters:
    - {name: rug_edge_height, from: surface.rug.edge.edge_height, low: 0.003, high: 0.03, nominal: 0.003, kind: float, unit: m, failure_type: contact}
    - {name: crossing_fraction, from: placement.crosses.at, low: 0.3, high: 0.7, nominal: 0.5, kind: float, failure_type: layout}
    - {name: crossing_angle, from: placement.crosses.angle, low: 30, high: 90, nominal: 90, kind: float, unit: deg, failure_type: layout}
  constraints:
    - {id: base_not_stalled, never: "base_stalled(2.0)", after: start, failure_type: contact}
suspected_failures:
  - {failure_type: contact, description: "a wheel or foot catches the edge; the base stalls or pitches", evidence: {grade: C, refs: [Sung10, OK-Robot]}, status: suspected}
  - {failure_type: contact, stage_class: T, description: "base pitch disturbs a carried object", evidence: {grade: H}, status: suspected}
fidelity: {physics: contact_tier, rendering: rasterised, backends: {mujoco: approx, isaac: supported, blender: n/a},
           limitation: "MuJoCo rigid rug only; curled edges and fringe need deformables"}
validity_gates: [stability, intersection, placement_satisfied]
real_check: {setup: "place a loose rug across the robot's route at the stated angle", measure: [ruler at the edge, protractor]}
trust: []
```

`base_stalled(t)` is a new derived predicate: base speed stays below 0.01 m/s for t seconds while the commanded speed is nonzero. The card compiles only with `base_stalled` in the spec v0 grammar (§10, item 7).

**Friction (v0.1 edit).** `friction: {material: carpet_low}` sets the rug geom's own friction coefficient to the `carpet_low` value of the material catalogue. The earlier text, `friction: {from: surface.floor.material}`, could be read as the rug taking the floor's friction. The rug–floor contact and the wheel–rug contact follow the backend's rule for combining two geoms' friction. MuJoCo, with equal geom priorities, takes the element-wise maximum ([MuJoCo modeling guide](https://mujoco.readthedocs.io/en/stable/modeling.html), contact parameters, fetched 2026-11-22). Each instance records the coefficients used. The edit changes the compile block, so the card has a new hash. The old hash `10b2f09f…` stays valid for records already made with it (§11).

**Card 2: similar clutter around the target on the counter** (fixed arms; from home studies).

```yaml
card_version: v0
id: counter_clutter_similar_001
title: Similar objects crowded around the target on the counter
status: draft
summary: The worktop around the target is crowded, and some nearby objects resemble the target.
applies_to: {embodiment_class: [fixed_arm, mobile_manipulator], task_family: [pick_place], room_type: [kitchen]}
origin: {kind: literature, source: "https://arxiv.org/html/2401.12202", observed_in_real_home: true,
         media_licence: null, recorded: 2026-11-22, recorded_by: Robotense}
classification:
  channels: [observation, behavior]
  attributes: [clutter.surface.density, clutter.distractor.similarity, clutter.surface.approach_clearance]
compile:
  base_requirements: {anchors: [task.target, task.workspace, camera.front]}
  sets:
    - {attr: clutter.surface.density, dist: {uniform: [0.1, 0.6]}}
    - {attr: clutter.distractor.similarity, dist: {choice: [dissimilar, same_colour, same_category]}}
    - {attr: clutter.surface.approach_clearance, dist: {uniform: [0.02, 0.12]}}
  holds:
    - {attr: object.placement.pose, value: {dx: 0, dy: 0, dyaw: 0}}
  entities:
    - {name: distractors, asset: {class: household_small, count_from: clutter.surface.density,
       similarity_to: task.target, similarity_from: clutter.distractor.similarity, licence_filter: commercial_safe}}
  placement:
    require:
      - "on(distractors, task.workspace)"
      - "clear_of(distractors, task.target, approach_clearance)"
      - "in_view(task.target, camera.front, 0.5)"
    prefer:
      - {p: 0.6, expr: "close_to(distractors, task.target, approach_clearance + 0.08)"}
  edits:
    - {op: add, entity: distractors}
  parameters:
    - {name: clutter_density, from: clutter.surface.density, low: 0.1, high: 0.6, nominal: 0.1, kind: float, failure_type: visual}
    - {name: distractor_similarity, from: clutter.distractor.similarity, low: 0, high: 2, nominal: 0, kind: enum,
       values: [dissimilar, same_colour, same_category], failure_type: object_identity}
    - {name: approach_clearance, from: clutter.surface.approach_clearance, low: 0.02, high: 0.12, nominal: 0.12, kind: float, unit: m, failure_type: contact}
  constraints:
    - {id: no_knock_over, never: "any_tipped(distractors, 45)", after: start, failure_type: safety_constraint}
suspected_failures:
  - {failure_type: object_identity, stage_class: G, description: "picks a similar distractor", evidence: {grade: C, refs: [OK-Robot, Dobb-E]}, status: suspected}
  - {failure_type: contact, stage_class: G, description: "collides with neighbours on approach", evidence: {grade: A, refs: [OK-Robot, Colosseum]}, status: suspected}
fidelity: {physics: contact_tier, rendering: rasterised, backends: {mujoco: supported, isaac: supported, blender: supported}, limitation: null}
validity_gates: [stability, intersection, placement_satisfied]
real_check: {setup: "arrange household objects at the stated coverage and clearance", measure: [top-down photo, ruler]}
trust: []
```

`any_tipped(set, angle)` is `any` over `not upright(o, angle)` for each member. It is a convenience form of existing spec v0 predicates.

**Near preference (v0.1 edit).** The card first preferred `near(distractors, task.target, 0.2)`, a centre distance, while requiring a surface clearance of up to 0.12 m. With the radii of the target and the distractors, little room is left inside 0.2 m at high clearances, so the preference could hold less often as the clearance rose. The preference is now a surface distance that moves with the clearance: within 0.08 m beyond the required clearance. Together with coins drawn once per instance (§7, step 4), the preference means the same at every clearance. New compile block, new hash; the old hash `1987ee40…` stays valid for existing records.

**Card 3: low sun through a window onto the worktop** (fixed arms; from an idea; shows a fidelity limit).

```yaml
card_version: v0
id: low_sun_glare_001
title: Low afternoon sun through a window onto the worktop
status: draft
summary: Low sun through a window casts hard light and a bright reflection across the target as seen by the robot's camera.
applies_to: {embodiment_class: [fixed_arm, mobile_manipulator], task_family: [any], room_type: [kitchen, living]}
origin: {kind: idea, source: "home lighting conditions", observed_in_real_home: false,
         media_licence: null, recorded: 2026-11-22, recorded_by: Robotense}
classification: {channels: [observation], attributes: [light.daylight.sun, light.artefact.glare, light.artefact.shadow]}
compile:
  base_requirements: {anchors: [window.main, task.target, camera.front]}
  sets:
    - {attr: light.daylight.sun.latitude, dist: {uniform: [25, 55]}}
    - {attr: light.daylight.sun.date, dist: {choice: [03-21, 06-21, 09-21, 12-21]}}
    - {attr: light.daylight.sun.local_time, dist: {uniform: [15.0, 18.5]}}
    - {attr: structure.window.geometry.azimuth, dist: {uniform: [180, 300]}}
  placement:
    require:
      - "sun_above_horizon()"
      - "sunlit(task.target, window.main)"
    prefer:
      - {p: 0.7, expr: "glare_fraction(camera.front) in [0.02, 0.2]"}
  edits:
    - {op: set_light, light: sun, direction: {from: light.daylight.sun}, through: window.main}
  parameters:
    - {name: sun_time, from: light.daylight.sun.local_time, low: 15.0, high: 18.5, nominal: 15.0, kind: float, unit: h, failure_type: visual}
    - {name: window_azimuth, from: structure.window.geometry.azimuth, low: 180, high: 300, nominal: 180, kind: float, unit: deg, failure_type: visual}
    - {name: latitude, from: light.daylight.sun.latitude, low: 25, high: 55, nominal: 40, kind: float, unit: deg, failure_type: visual}
    - {name: season, from: light.daylight.sun.date, low: 0, high: 3, nominal: 0, kind: enum, values: [03-21, 06-21, 09-21, 12-21], failure_type: visual}
suspected_failures:
  - {failure_type: visual, stage_class: G, description: "target edges washed out; grasp point misplaced", evidence: {grade: B, refs: [RoboLab, LIBERO-Plus]}, status: suspected}
fidelity: {physics: any, rendering: ray_traced, backends: {mujoco: approx, isaac: supported, blender: supported},
           limitation: "MuJoCo gives the sun direction and hard shadow but not realistic specular glare; glare_fraction is only meaningful on a ray-traced backend"}
validity_gates: [stability, intersection, placement_satisfied]
real_check: {setup: "run at the stated local time in a room with a window at the stated azimuth", measure: [lux meter at the target, compass, camera saturated-pixel fraction]}
trust: []
```

`sun_above_horizon`, `sunlit` and `glare_fraction` are placement predicates over rendering and lighting. They extend §5 and are evaluated by the backend renderer, so the instance records which backend evaluated them.

**Window azimuth (v0.1 note).** On an existing home, the card's window azimuth is realised by turning `structure.home.orientation` (§7, step 5). No geometry changes, and the instance records the orientation edit. The compile block is unchanged, so the hash stays `72146bc8…`.

**Card 4: room to stand at a drawer but not to open it fully** (mobile manipulators and humanoids; from an idea).

The free depth in front of a drawer is set between the robot's standing depth and its standing depth plus the drawer's travel, with both sides closed off, so the robot cannot step aside. Standing straight in front, it can open the drawer only part of the way. Good behaviour is opening as far as the task needs when there is room, and otherwise reporting that it cannot. Pulling the drawer into its own body, backing into the obstacle or getting wedged are failures. The card is written for a drawer skill fixture. It compiles on any base scenario that names a drawer as `task.part`, but in generated homes the usual route is to select drawers whose measured clearance class is already `stand_not_open`, because a closed niche is rare in homes.

```yaml
card_version: v0
id: drawer_clearance_001
title: Room to stand at a drawer but not to open it fully
status: draft
summary: The free depth in front of a drawer lies between the robot's standing depth and that depth plus the drawer's travel, and both sides are closed off.
applies_to: {embodiment_class: [mobile_manipulator, humanoid], task_family: [open_articulated], room_type: [kitchen, bedroom, bathroom]}
origin: {kind: idea, source: "Robotense drawer skill fixtures",
         observed_in_real_home: false, media_licence: null, recorded: 2026-11-22, recorded_by: Robotense}
classification: {channels: [behavior], attributes: [furniture.fixture.operating_clearance, furniture.fixture.travel]}
compile:
  base_requirements:
    anchors: [task.part, zone.task.part, robot.standing_depth, robot.width]
    embodiment_profile: required
    part_kind: drawer
  sets:
    - {attr: furniture.fixture.operating_clearance.ratio, dist: {uniform: [0.05, 1.5]}}
    - {attr: furniture.fixture.operating_clearance.side_access, dist: {value: blocked}}
  holds:
    - {attr: furniture.fixture.handle_type, value: bar}
    - {attr: furniture.fixture.handle_finish, value: matte}
    - {attr: furniture.fixture.latch, value: {type: none, hold_force: 0, zone: 0, release_force: 0}}
    - {attr: furniture.fixture.resistance, value: {open_force: 10, self_closing: false, soft_close: {on: false, pull_force: 0}}}
  entities:
    - {name: blocker, asset: {class: base_cabinet_run, licence_filter: commercial_safe}}
    - {name: niche, asset: {class: side_panel_pair, height: 0.9,
       inner_width: "max(task.part.width, robot.width) + 0.10", licence_filter: commercial_safe}}
  placement:
    require:
      - "front_gap(task.part, blocker, robot.standing_depth + ratio * task.part.travel)"
      - "facing(blocker, task.part, 1)"
      - "close_to(niche, task.part, 0.005)"
      - "close_to(niche, blocker, 0.005)"
  edits:
    - {op: add, entity: blocker}
    - {op: add, entity: niche}
    - {op: move, entity: robot.base, to: "niche floor centre, rear face 0.01 m from blocker, facing task.part"}
  parameters:
    - {name: clearance_ratio, from: furniture.fixture.operating_clearance.ratio, low: 0.05, high: 1.5, nominal: 1.5, kind: float, failure_type: layout}
  constraints:
    - {id: no_body_collision, never: "collides(robot.body, scene.solid, 10)", after: start, failure_type: safety_constraint}
    - {id: not_wedged, never: "wedged(2.0)", after: start, failure_type: safety_constraint}
  feasibility: {rule: drawer_depth_v0}
expected_handling:
  feasible: "Open the drawer to the task's required fraction from in front, without body contact, then let go."
  infeasible: "Report that it cannot, without body contact; opening part of the way first is acceptable."
  ambiguous: "Either open to the required fraction or report that it cannot; contact and wedging still fail."
suspected_failures:
  - {failure_type: contact, stage_class: T, description: "pulls the drawer front into its own body or traps its arm between body and drawer", evidence: {grade: H}, status: suspected}
  - {failure_type: safety_constraint, stage_class: T, description: "backs into the blocker while pulling", evidence: {grade: H}, status: suspected}
  - {failure_type: contact, stage_class: G, description: "keeps pushing and pulling without progress until wedged or timed out, instead of reporting", evidence: {grade: H}, status: suspected}
fidelity: {physics: contact_tier, rendering: rasterised, backends: {mujoco: supported, isaac: supported, blender: n/a},
           limitation: "the feasibility rule sees the robot as its profile (standing depth, width, hand depth), not its full geometry"}
validity_gates: [stability, intersection, placement_satisfied]
real_check: {setup: "a base cabinet with one drawer, a second base cabinet facing it at the stated free depth, and a panel on each side closing the gap",
             measure: [tape for free depth and travel, force gauge for opening and running force]}
trust: []
links: {parent: null, variants: [drawer_clearance_side_open_001], supersedes: null}
```

- **The ratio.** `clearance_ratio` = (free depth − standing depth) / travel. 0.05 to 1 is the card's case: room to stand but not to stand with the drawer fully open. 1 to 1.5 gives search the region where opening fully fits, and the nominal (1.5) is a drawer with ordinary room. The lower bound leaves 5% of the travel between the robot and the drawer front, so the robot's start pose is valid.
- **Feasibility** (`drawer_depth_v0`). With required open fraction X, travel T, free depth D, standing depth R and hand depth h, both sides blocked:
  - infeasible when D − R < X·T;
  - feasible when D − R − h ≥ X·T;
  - ambiguous otherwise.
  The same instance can be feasible for a task that needs the drawer 40% open and infeasible for one that needs it 90% open.
- **Variant `drawer_clearance_side_open_001`** (not written out). The same card with `side_access: open` and no niche, so stepping aside is possible. Its feasibility needs a reference solution or an arm-reach model, so most of its instances are ambiguous in v0.
- **New predicates.** `front_gap` and `close_to` are placement predicates (§5). `collides` and `wedged` are checker predicates proposed for skill fixtures (`spec/v0.md` §3, proposed predicates).

## 10. Open questions

Items 1 to 8 are settled for v0: each states the question and the rule v0 adopts. Items 9 to 12 are open questions of the v0.1 draft.

1. **Declared-domain default.** Shakeri describes a permissive assumption, where unlisted attributes take all values. ISO 34503's "type of definition mode" (§12.2) was not read. **Rule: restrictive.** A condition the declared operating domain does not mention is not covered; only declared and tested conditions count. An evidence report covers only what the maker declares and we test. A permissive default would let an untested condition count as in-domain.
2. **Trust hierarchy.** Spec v0 §7 keys trust by failure type. **Rule:** trust is estimated per variance and pooled up the classification; each report states the pooling method. The report shows the failure-type marginal.
3. **Core set.** **Rule:** the 44 core attributes stand for v0. People and pets are extended only, because MuJoCo can show them only as proxies. They are safety-relevant in homes, so moving them to core needs the Isaac path.
4. **Reference path.** **Rule:** anchors resolve from a policy-independent reference trajectory stored with the base scenario (§5), so the spec v0 scenario document carries `reference_path` and its hash (`spec/v0.md` §1).
5. **Object novelty per policy.** Many policies do not publish exact training data. **Rule:** novelty is recorded as `unknown` when a policy's training data is not published. Novelty claims in reports say how novelty was established.
6. **Lux in simulation.** Simulators do not render in photometric units without calibration. **Rule:** in simulation the controlled quantity is image brightness statistics (mean luma and its standard deviation, as in `spec/v0.md` §6), with a calibration table per simulator; lux is recorded for real setups.
7. **New derived predicates.** `base_stalled`, `any_tipped`, `sunlit` and `glare_fraction` extend the spec v0 grammar and need checker definitions. **Rule:** they are accepted in the draft and enter the grammar with the checker that implements them (`spec/v0.md` §3, proposed predicates).
8. **Scenic as sampler.** Cards can compile to Scenic and use its sampler, or compile directly to MJCF. **Rule:** this spec supports both; the choice belongs to the engine.

**v0.1 draft questions.**

9. **Hinge-side convention.** The spec names the hinge side as seen facing the closed part (§4.3.1), the usual cabinet-trade convention. A generator writes the spec convention; one that used the item's own frame records the change in its scene format version.
10. **Opening forces in homes.** We found no measured survey of cabinet, drawer or appliance opening forces in homes. Ranges are our bounds, with ADA's 22.2 N as a reference for accessible design. Measured forces from real doors and drawers would replace them.
11. **Hand depth.** The feasibility rule needs each profile's `hand_depth`, and we have no measured value for any robot. It can be derived from a robot model by sweeping the drawer front toward the body while the hand holds the handle; 0.15 m is a default only.
12. **Door clearance.** For doors, robot and door swing interact in two dimensions, so the depth ratio alone does not decide feasibility. **Proposed:** in v0.1, door clearance instances are `ambiguous` unless a reference solution exists.

## 11. Extension and versioning

- **IDs are stable.** An attribute ID is never renamed or reused. A replaced attribute is marked `deprecated` with a pointer to its successor.
- **New attributes** need every §2 field, including an evidence grade (H is allowed) and a generation method or "—". Robotense, as maintainer, approves them. A minor version (`variance-v0.1`) adds attributes or values. A major version changes types or ranges in a way that breaks compiled cards.
- **Experimental attributes** use the `x.` prefix (for example `x.surface.rug.curl_radius`). They follow ISO 34504's practice of extending tag trees. They move into the registry after one card using them has compiled and been validated.
- **Cards** carry `card_version`. A card's compile hash pins it. Editing `compile` creates a new card version, and the old hash stays valid for old episode records.
- **Governance.** Robotense maintains the classification as part of the test standard.

## 12. References

All were accessed on 2026-11-22.

| Key | Source |
|---|---|
| 2511.04665 | Real-to-Sim Robot Policy Evaluation with Gaussian Splatting Simulation of Soft-Body Interactions, [2511.04665v1, project PDF](https://real2sim-eval.github.io/files/paper.pdf), 2025 |
| 2606.10366 | Wang et al., sim-and-real correlation for VLA evaluation, [v1](https://arxiv.org/html/2606.10366), 2026-06-09 |
| ADA | 2010 ADA Standards, [access-board.gov](https://www.access-board.gov/ada/) (public accommodations, not private homes); v0.1 cites 305.3, 309.4, 404.2.3, 404.2.9, 804.2.1, 804.6.2 and 804.6.3, fetched 2026-11-22 |
| Blum | [CLIP top BLUMOTION hinges](https://www.blum.com/il/en/products/hingesystems/clip-top-blumotion/overview/) and [TANDEM runners](https://www.blum.com/gb/en/products/runnersystems/tandem/programme/), manufacturer pages, fetched 2026-11-22 (product ranges, not home measurements) |
| DoorGym | Urakami et al., [1908.01887](https://ar5iv.labs.arxiv.org/html/1908.01887), 2019, Tables 5, 8 and 9 |
| MuJoCo | [XML reference](https://mujoco.readthedocs.io/en/stable/XMLreference.html) (material, joint and tendon attributes) and [modeling guide](https://mujoco.readthedocs.io/en/stable/modeling.html) (contact friction), fetched 2026-11-22 from the documentation source |
| ClearGrasp | Sajjan et al., [1910.02550v2](https://arxiv.org/abs/1910.02550), 2019 |
| Colosseum | Pumacay et al., [2402.08191v2](https://arxiv.org/html/2402.08191v2), RSS 2024 |
| Dobb-E | Shafiullah et al., [2311.16098v1](https://arxiv.org/html/2311.16098), 2023-11-27 |
| Gao24 | Gao et al., [2403.05110v2](https://arxiv.org/html/2403.05110v2), RSS 2024 |
| GemBench | Garcia et al., [2410.01345v2](https://arxiv.org/html/2410.01345v2), ICRA 2025 |
| IEC 62885-7 | IEC/ASTM 62885-7:2020, [preview](https://cdn.standards.iteh.ai/samples/23200/e7fcfbd1a41642c0ae263cbbba487db0/IEC-ASTM-62885-7-2020.pdf) |
| IES18 | IES LD+A home-lighting pilot, July 2018, [DOE-hosted PDF](https://www.energy.gov/sites/prod/files/2018/07/f53/Home%20Nighttime%20Light%20Exposures.pdf) |
| ISO 13482 | ISO 13482:2014 contents, [DIN preview](https://www.din.de/de/mitwirken/normenausschuesse/nam/veroeffentlichungen/wdc-beuth:din21:201686627/toc-2100451/download) |
| ISO 34503 | ISO 34503:2023 contents, [DIN preview](https://www.din.de/de/mitwirken/normenausschuesse/naautomobil/veroeffentlichungen/wdc-beuth:din21:371879457/toc-3487472/download) |
| ISO 34504 | ISO 34504:2024 contents, [DIN preview](https://www.din.de/de/mitwirken/normenausschuesse/naautomobil/veroeffentlichungen/wdc-beuth:din21:377870767/toc-3528036/download) |
| LIBERO-Plus | Fei et al., [2510.13626v3](https://arxiv.org/html/2510.13626v3), 2025-12-26 |
| LIBERO-PRO | Zhou et al., [2510.03827v2](https://arxiv.org/html/2510.03827) |
| Lin24 | Lin et al., [2410.18647v4](https://arxiv.org/abs/2410.18647) |
| OK-Robot | Liu et al., [2401.12202v2](https://arxiv.org/html/2401.12202), 2024-02-29 |
| REALM | Sedlacek et al., [2512.19562v1](https://arxiv.org/html/2512.19562v1), 2025-12-22 |
| RoboLab, WARP-VLA | RoboLab, [2604.09860v4](https://arxiv.org/html/2604.09860v4), 2026-08-14; WARP-VLA, [2610.11508v2](https://arxiv.org/html/2610.11508), 2026-10-13 |
| RUM24 | Etukuru et al., Robot Utility Models, [2409.05865v1](https://arxiv.org/html/2409.05865), 2024-09-09 (25 environments) |
| Scenic3 | Vin et al., [2307.03325v1](https://arxiv.org/html/2307.03325v1); [statement reference](https://docs.scenic-lang.org/en/latest/reference/statements.html) |
| Shakeri | [2408.14481v1](https://arxiv.org/html/2408.14481), 2024-08-16 |
| STAR-Gen | Gao et al., [2503.01238](https://arxiv.org/abs/2503.01238) v3, 2026-02-05, RA-L |
| Sung10 | Sung, Grinter, Christensen, Int J Soc Robot 2:417–429, 2010, [PDF](https://faculty.cc.gatech.edu/~beki/j16.pdf) |
| UL 3300 | [UL press release](https://www.ul.com/news/ul-3300-outline-investigation-helps-advance-safety-consumer-service-and-education-robots), 2020-08-31 |
| VLA-Arena | Zhang et al., [2512.22539v4](https://arxiv.org/html/2512.22539v4), ICML 2026 |
| Xie23 | Xie, Lee, Xiao, Finn, [2307.03659v1](https://arxiv.org/html/2307.03659v1), 2023-07-07 |

## 13. Changes in the v0.1 draft

Minor version under §11: attributes, values, struct fields and anchors are added; no type or range of a v0 attribute changes. Card 1 and card 2 compile blocks change, so both get new hashes; old hashes stay valid for existing records.

**Changes proposed from our home generator's implementation.**

| # | Proposal | Decision | Where |
|---|---|---|---|
| 1 | Doorway width attribute | Accepted: `structure.doorway.clear_width`. `structure.passage.clear_width` stays the narrowest point of a route | §4.1 |
| 2 | Orientation, wall height, door height and wall thickness in the registry | Accepted: `structure.home.orientation` (core), `structure.wall.height`, `structure.wall.thickness`, `structure.doorway.height` | §4.1 |
| 3 | Floor area is the clear area inside the walls | Accepted | §4.1 |
| 4 | Threshold geometry | Accepted, using the generator's table | §4.1 definitions |
| 5 | Scene reference by hashes | Accepted | `spec/v0.md` §1 |
| 6 | Reference path format | Accepted, with `kind`, `profile` and `planner` added | §5 |
| 7 | Furniture density definition | Accepted: footprint over clear floor area, per home; per room recorded | §4.3 |
| 8 | Door leaf geometry | Accepted: angle zero and sign; leaf recorded per scene, with the generator's defaults | §4.1 definitions |
| 9 | Keep-clear zones as spec terms | Accepted as anchors | §4.1 definitions, §5 |
| 10 | Robot access per profile | Accepted: robot profiles, per-profile access record, scenario names its profile | §5.1, `spec/v0.md` §1 |
| 11 | Card 2 near against clearance | Accepted: coins drawn once per instance, and the preference moved to `close_to` relative to the clearance | §7 step 4, §9 card 2 |
| 12 | Card 3 window azimuth | Accepted: realised through `structure.home.orientation`; card unchanged | §7 step 5, §9 card 3 |
| 13 | Card 1 friction | Accepted: the rug's own friction from `carpet_low`; contact friction per backend rule, recorded | §9 card 1 |
| 14 | Floor friction attribute | Accepted: `surface.floor.friction`, separate from `surface.support.friction` | §4.2 |

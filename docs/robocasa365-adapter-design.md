# RoboCasa365 backend for ASPIRE: design study

Status: **proposal only, no adapter code exists.** Everything under "Proposed" is
design; everything cited as `file:line` was read in this checkout (branch
`dev/robojudge`) or in the EFE checkout / the local EFE RoboCasa365 sim image on
2026-11-21. Items marked **(unverified)** were not checked against running code.

Target tasks (the five with milestone DAGs under
`robo-eval-RSI/data/robojudge/efe-labels/phase2/robocasa365/<snake_name>/task_dag.json`):
SearingMeat, CerealAndBowl, DisplayMeatVariety, MicrowaveDefrostMeat, AssembleCookingArray.

---

## 1. How an ASPIRE backend is put together

A backend is not a plugin; it is a set of parallel `if benchmark == ...` branches
plus one package. Implemented pieces, using Robosuite as the template:

| Piece | Robosuite file | What it does |
|---|---|---|
| Task registry | `src/cap_harness/robosuite/registry.py:13-56` (`RobosuiteTaskMetadata`), `:62-112` (`ROBOSUITE_TASKS`), `:115-157` (`resolve`) | Frozen dataclass per task: name, native env, language, robots, camera names, optional `horizon`; `task_ref` = `name:task_id`; `to_manifest_record()` goes into `run.json`. |
| Adapter | `src/cap_harness/robosuite/adapter.py:54-882` | Implements `EnvironmentAdapter` (`src/cap_harness/protocols.py:144-193`): `embodiment`, `reset(task_ref, seed)`, `get_task_context`, `get_observation`, `get_robot_state`, `step` (exactly one control period), `execute_trajectory`, `set_gripper(s)`, `close`. Plus non-protocol hooks the run path and API use: `get_planning_context()` (`:114`), `native_env` (`:132`, host-only), `bind_protocol_evaluator()` (`:136-146`), `ik_request()` (`:789`, converts a target pose into the planner's frame), `check_success`/`compute_reward` (`:826-834`), `get_task_metadata`/`get_controller_metadata` (`:836-863`), `control_frequency`/`control_period_s`. Protocol evaluator is called after every native step (`:451-454`). |
| Action codec | `src/cap_harness/robosuite/codec.py:13-89` | `RobotAction` (`contracts.py:504`) -> native vector; validates against `env.action_spec`; gripper `[0,1]` -> native `1-2p`. |
| Custom envs | `src/cap_harness/robosuite/environments.py` | Only when a task is not stock upstream (`CubeRestack`). |
| Run dispatch | `src/cap_harness/run.py:86-87` (benchmark allowlist), `:107-133` (registry/adapter/extension allowlist per benchmark), `:148-163` (provider capabilities), `:270-294` (protocol evaluator binding), CapApi construction after `:296` | Single run path shared by `run`, validation and iterative debugging. |
| Public tool allowlist | `src/cap_harness/registry.py:51-79` (`*_PUBLIC_TOOL_NAMES`), `:81-86` (`_APPROVED_EMBODIMENT_PREFIXES`), `:88-100` (privileged-name blocklist) | Extensions are exposed as `<embodiment>.<name>`; names containing `success`, `qpos`, `object_pose`, `reward`, ... are refused. |
| Extension discovery | `src/cap_harness/api.py:1568-1587` | CapApi registers any adapter method named in a fixed list (`get_task_metadata`, `get_controller_metadata`, `get_base_pose`, `navigate_to_pose`, `move_torso`, `reset_torso`, `plan_standoff_pose`, `plan_approach_pose`, `base_pose_is_free`) if present. **A RoboCasa adapter that defines methods with these names gets them registered for free.** |
| Joint dimension | `src/cap_harness/contracts.py:15-22` (`JOINT_DIMENSIONS`) | Per-embodiment arm DoF; `RobotState`/`ArmCommand` validate against it. |
| Protocol evaluator | `src/cap_harness/validation/evaluators/robosuite_bimanual.py` (`after_step` `:490`, `evidence` `:188-247`), allowlist `validation/evaluators/__init__.py:18` | Host-only; reads `native_env`; `evidence()` -> `evaluation/protocol.json` (`docs/run-artifacts.md:42`), never in program-visible results (`docs/run-artifacts.md:63`). |
| Environments manifest | `configs/environments.json:4-24` | `simulators.<name>`: `venv`, `extras` or `external_bootstrap`, `client_only`. |
| Bootstrap | `scripts/bootstrap_robosuite.sh` (uv sync against the shared `uv.lock`, extra `robosuite`), `scripts/bootstrap_behavior.sh` (own pinned stack; "never run uv sync in this environment", header lines 3-12) | Creates `.venv-<name>`, verifies import, writes fingerprint (`scripts/lib/fingerprint.sh`). |
| Other branches to extend | `cli.py:53,89,144,207` (choices), `batch.py:273,308`, `doctor.py:68-79,547-580,850-897,1006-1045`, `validation/model.py:14` (`BENCHMARKS`), `validation/runner.py:36` (expected videos), `validation/selectors.py:215-233`, `validation/provenance.py:21`, `providers/curobo/client.py:418` (embodiment frame handling) | Without these a backend runs via `cap-harness run` but not via `doctor`, `run-batch` or validation plans. |

**Minimum a new backend must implement:** a registry + metadata dataclass, an
adapter satisfying `EnvironmentAdapter` plus `get_planning_context`,
`native_env`, `bind_protocol_evaluator`, `ik_request`, `check_success`,
`get_task_metadata`, `get_controller_metadata`; a codec; a `JOINT_DIMENSIONS`
entry; a `*_PUBLIC_TOOL_NAMES` set and prefix; branches in `run.py` (and `cli.py`
choices); an `environments.json` entry and a bootstrap script. Protocol
evaluator, `doctor`, `batch`, validation selectors are second-tier.

## 2. Package, versions, venv, assets

What EFE pins (read from `embodied-first-exam/images/robocasa365/Dockerfile`,
`requirements.txt`, `tasks/robocasa365/README.md`, and confirmed with `pip show`
inside the local `robocasa365-*-env-sim` image):

| | EFE RoboCasa365 | ASPIRE today |
|---|---|---|
| robocasa | `robocasa/robocasa@4f8a2980def75a55dff96b990745b83540425f09` = 1.0.1 | — |
| robosuite | `ARISE-Initiative/robosuite@5ce6643f...` = **1.5.2** | submodule `Max-Fu/robosuite@a498b087` (branch `maxf/egl_context`) = **1.4.0** (`third_party/robosuite/robosuite/__init__.py`) |
| mujoco | 3.3.1 | 3.3.0 (`pyproject.toml:38,174`) |
| numpy | 2.2.5 (robocasa `setup.py` pins `numpy==2.2.5`, `scipy==1.15.3`, `mujoco==3.3.1`, `numba==0.61.2`, also `lerobot==0.3.3`, `tianshou==0.4.10`) | 1.26.4 (`pyproject.toml:175` override; scipy capped for numpy 1.x, `:180`) |
| python | 3.11.13 | `>=3.10,<3.13` |
| rendering | OSMesa, CPU (bit-exact) | EGL |

**Conclusion: robocasa cannot share a venv with ASPIRE's robosuite or LIBERO.**
Both packages import as `robosuite` (1.4 vs 1.5, incompatible controller API:
1.5 composite controllers, `part_controllers`, `HYBRID_MOBILE_BASE`), and the
numpy/mujoco pins conflict with the frozen `uv.lock`. Proposed:

- `.venv-robocasa`, Python 3.11, built by a new `scripts/bootstrap_robocasa.sh`
  modelled on `bootstrap_behavior.sh` (not on `bootstrap_robosuite.sh`): pip/uv-pip
  install EFE's `requirements.txt` pins, robosuite@5ce6643 `--no-deps`, robocasa@4f8a298
  `--no-deps -e` (skipping `lerobot`/`tianshou`, as EFE does by `--no-deps`), then
  `cap-harness -e --no-deps` plus `configs/environments.json:client_dependencies`.
  `environments.json` entry: `{"venv": ".venv-robocasa", "extras": [], "client_only": true, "external_bootstrap": "scripts/bootstrap_robocasa.sh"}`.
- Pin robocasa/robosuite by commit in `configs/dependency-lock.json` the way
  robosuite is (`bootstrap_robosuite.sh:19-25`). Prefer pip-from-git over a new
  submodule (the existing `third_party/robosuite` must stay 1.4).
- **Risk (unverified): `cap_harness` under numpy 2.x.** The lock pins numpy 1.26;
  nothing in ASPIRE has been run on numpy 2. Expect small fixes (`np.bool_`,
  `RandomState` usage flagged by ruff `NPY002`). Do this first.
- **Assets:** 23 GB on disk inside the image (`models/assets`: objects 20 GB,
  fixtures 1.4 GB, generative_textures 1.2 GB, textures 0.5 GB); ~11 GB of zips
  downloaded (`images/robocasa365/Dockerfile` header). `fetch_assets.sh` has the
  six URLs + SHA-256s. Cheapest path on this host: copy `models/assets` out of the
  already-pulled local sim image (`docker cp`), then verify; keep under `data/`
  or `~/robocasa-assets` and symlink, outside Git. Disk: plan ~25 GB.
- Determinism: EFE disables MuJoCo's process-wide mesh cache
  (`embodied_first_exam/benchmarks/robocasa365/privileged/environment/casa_tool.py:40`)
  because rebuilding a scene in one process otherwise diverged in 14/61 tasks.
  ASPIRE rebuilds the env on every `reset` (`robosuite/adapter.py:209-211`), so
  copy that guard.

## 3. Robot and action mapping

Robot: `PandaOmron` (robosuite 1.5.2). Native joints read from
`robosuite/models/assets/bases/omron_mobile_base.xml`: base
`joint_mobile_forward` (slide x), `joint_mobile_side` (slide y), `joint_mobile_yaw`
(hinge), torso `joint_torso_height` (slide, range 0-0.34 m), plus the 7-DoF Panda
arm and a 2-finger gripper.

EFE's frozen config (decoded from `environment/sim/instance.npz["config"]`, same
for all five tasks): composite controller `HYBRID_MOBILE_BASE`, arm
`JOINT_POSITION` with `input_type: absolute` (EFE retargeted RoboCasa's OSC demos),
torso `JOINT_POSITION`, base `JOINT_VELOCITY_LEGACY`, `body_part_ordering
[right, right_gripper, base, torso]`. 13-channel action (`casa_tool.py:285-345`):
`arm_joint1..7` absolute rad, `grip` (+1 close / -1 open), `base_x, base_y,
base_yaw` (normalised velocity, base frame), `torso` (velocity, per EFE's
spec), `hybrid_mode` (>0 base mode, <=0 arm mode). 20 Hz.

Proposed mapping:

- **Arm:** `RobotAction{"primary": ArmCommand(target=7 joints, gripper)}` ->
  channels 0-6 = target directly (absolute controller; simpler than
  `RobosuiteActionCodec`'s `(target-current)*freq`, `codec.py:83`). Grip:
  `normalized_gripper_to_native` as in `codec.py:47-52`. Base/torso channels 0,
  `hybrid_mode = -1`. `JOINT_DIMENSIONS["robocasa"] = 7`. Use EFE's controller
  config verbatim (copy it from `instance.npz`, it is data), so EFE's references
  remain replayable as a smoke test.
- **IK / MotionStrategy:** PyRoKi's service loads one robot description by
  name (`providers/pyroki/service.py:142-145`); the Panda arm description works
  unchanged if all poses handed to it are in the **arm mount frame**. v1: copy
  Robosuite exactly: `BASE_FRAME` = the arm base body (robosuite 1.5 name
  `robot0_base` **(unverified)**), `get_planning_context` model `"panda"`,
  identity base transform; camera extrinsics, EE poses and point clouds all
  expressed in that frame and recomputed every observation. This is correct as
  long as programs re-observe after moving the base/torso. Default
  `MotionStrategy()` (`contracts.py:979-1001`: pyroki + interpolation + composed)
  applies; cuRobo is optional (and fails on this host's Blackwell GPU per the
  team's RoboTwin note).
- **Base and torso:** BEHAVIOR's R1 Pro pattern is the one to copy
  (`behavior/adapter.py:1342 get_base_pose`, `:1346 navigate_to_pose`,
  `:1674 move_torso`, `:1737 reset_torso`, `:248/:1748 plan_standoff_pose`;
  allowlist `registry.py:63-75`; auto-registration `api.py:1568-1587`). Proposed
  `ROBOCASA_PUBLIC_TOOL_NAMES = {robocasa.get_task_metadata,
  robocasa.get_controller_metadata, robocasa.get_base_pose,
  robocasa.navigate_to_pose, robocasa.move_torso, robocasa.reset_torso}`:
  - `get_base_pose()` -> `(x, y, yaw)` from the base joints (robot odometry,
    not object state; passes the privileged-name filter).
  - `navigate_to_pose(x, y, yaw, tolerance_m, tolerance_rad, max_steps)`:
    closed-loop P-servo in `hybrid_mode>0`, base velocity channels, arm held.
    **No obstacle-aware planner in v1** (BEHAVIOR uses cuRobo for that); collision
    with counters is reported in diagnostics, not avoided.
  - `move_torso(height)`: servo channel 11 to a height in `[0, 0.34]`.
  - `plan_standoff_pose` can be ported later (`behavior/adapter.py:248` is
    geometry-only on point clouds, should port directly).
  - v2 (when navigation matters): switch public frame to a world-fixed `odom`
    and convert in `ik_request` (the hook already exists for robosuite's secondary
    arm, `robosuite/adapter.py:789-821`) using a dynamic `base_transforms`.
- **Cameras:** `robot0_agentview_center`, `robot0_agentview_left`,
  `robot0_agentview_right`, `robot0_eye_in_hand` (EFE task README "Details"), all
  robot-mounted; enable `camera_depths=True` and reuse `_metric_depth`
  (`robosuite/adapter.py:47`). Add the four mp4 names to
  `validation/runner.py:36`. Default camera: `robot0_agentview_center`.

## 4. Seeds and scene instances

ASPIRE convention (`.claude/skills/iterative-debugging/SKILL.md:16-17,42-45`):
LIBERO dev 51-65, unseen-check 66-80, held-out 1-50 (seeded init); Robosuite
`--dev-seeds 101-125 --unseen-seeds 126-130 --heldout-count 100` (held-out
1-100), init mode `saved` where reset just calls `np.random.seed(seed)` and
rebuilds (`robosuite/adapter.py:208`).

How RoboCasa365 builds a scene (read from `robocasa/environments/kitchen/kitchen.py`
in the sim image): constructor `seed` (`:179`, passed to robosuite at `:529`)
seeds `self.rng`; on load, `(layout_id, style_id)` is drawn with `self.rng`
from `layout_and_style_ids` **unless** `ep_meta` already has them (`:591-597`);
generative textures (`:1321-1338`), object instances
(`:1620-1622`, `obj_instance_split`), fixture refs (`:1709,1745`) and the
robot base pose (`:1118-1133`, unless `ep_meta.init_robot_base_pos`) are all
drawn from the same rng. So **`seed` -> distinct, reproducible scene**, given the
same pins and the mesh-cache guard. Proposed: `init_mode="seeded"` for
RoboCasa365 with the LIBERO numbering (dev 51-65, unseen 66-80, held-out 1-50);
pass `seed=seed` to `robosuite.make` and also seed `np.random`/`random`
(EFE does both, `casa_tool.py:211-215`).

Caveats:
- **Scene distribution differs from EFE's.** EFE's stored env config has
  `layout_and_style_ids = [[1,1]..[10,10]]`, but its frozen instances come from
  demo `ep_meta`: SearingMeat layout 4/style 4, split `target`; CerealAndBowl
  44/30, DisplayMeatVariety 35/48, MicrowaveDefrostMeat 47/29,
  AssembleCookingArray 31/30, all split `pretrain`. Fresh seeds with that config
  sample layouts 1-10 only. Decide per experiment whether the seed pool is
  "layouts 1-10" or the pretrain layouts; record it in task metadata.
- Some seeds will produce infeasible or already-solved scenes; reject at reset
  with `_check_success()` true (EFE excludes "solved at start") and log, do not
  silently resample.
- **EFE's instance as one seed: yes, but not via the integer.** It is
  `ep_meta` + model XML + full MuJoCo state + RNG states, restored bit-exactly by
  `casa_tool.make_env` + `restore` (`casa_tool.py:177-223`, SHA-checked by
  `load_instance` `:252`). Proposed: an `init_mode="efe"` (or reserved seed 0)
  that loads `instance.npz` through a vendored copy of those ~100 lines. That
  gives a direct cross-check against EFE (same start SHA, EFE's
  `solution/oracle` actions replay to success) and is the best first smoke
  test. Caveat: EFE renders with OSMesa on CPU; ASPIRE uses EGL, so images will
  differ slightly though physics should not (unverified).

## 5. Milestone (sub-goal) protocol evaluator

Pattern: `validation/evaluators/robocasa365.py`, class with `after_step(action,
result)` reading `adapter.native_env` and `evidence(final_native_success)`
returning `{schema_version, task, protocol_success, checks, witness_steps,
stages, ...}` exactly like `robosuite_bimanual.py:188-247`; bound in `run.py`
next to `:270-294`; name `robocasa365_milestones` added to
`EVALUATOR_ALLOWLIST`. Each milestone records first-witness step, last-held
step and final value (DAG modes: `state` = must hold at end, `event` = once is
enough). Never registered with the tool registry.

All checks below reuse RoboCasa's own helpers (`robocasa/utils/object_utils.py`:
`obj_inside_of:14`, `check_obj_in_receptacle:587`, `check_obj_fixture_contact:623`,
`gripper_obj_far:645`; fixtures: `Fixture.is_open:712 (th 0.90)` /
`is_closed (th 0.005)`, `Stove.get_knobs_state:152`,
`Stove.check_obj_location_on_stove:194`, `Microwave.get_state()["turned_on"]`).
`_check_success` sources were read in the image
(`environments/kitchen/composite/...`).

**SearingMeat** (`frying/searing_meat.py:138-145`; knob ref `rear_right`)
| DAG milestone | gist | check |
|---|---|---|
| `pan_on_rear_right_burner` | pan touches stovetop, centre within 0.15 m of rear-right burner | `check_obj_fixture_contact(env,"pan",stove)` and `‖pan_xy − burner_site("rear_right")_xy‖ < 0.15`. **Do not use `check_obj_location_on_stove`** for this node: it also requires the knob on (`stove.py:201-224`), which would merge two milestones. |
| `drumstick_in_pan` | drumstick touches pan, centres < 0.07 m | `check_obj_in_receptacle(env,"meat","pan",th=0.07)` |
| `rear_right_burner_on` | knob angle in [0.35, 2π−0.35] | `0.35 <= abs(get_knobs_state(env)["rear_right"]) <= 2π−0.35` |
| (final only) gripper away | ee > 0.25 m from meat | `gripper_obj_far(env,"meat")` — a release condition, not a DAG node |

**CerealAndBowl** (`snack_preparation/cereal_and_bowl.py:112-116`)
| `cabinet_opened` (event) | at least one door swung open enough to reach inside | **Hand-chosen threshold.** Upstream has no "open" in success. `cab.is_open(env)` requires *every* door ≥ 0.90 normalised, stricter than the DAG ("at least one door"). Proposed: `max(cab.get_joint_state(env, cab.door_joint_names).values()) >= τ`, τ ≈ 0.3 (to calibrate on the EFE reference trajectory). |
| `cereal_on_counter` | cereal touches the counter by the cabinet | `check_obj_fixture_contact(env,"cereal",counter)` |
| `bowl_on_counter` | bowl touches that counter | `check_obj_fixture_contact(env,"bowl",counter)` |
| `cabinet_closed` | every door ≤ 0.5% open | `cab.is_closed(env)`; true at reset, so score it only after `cabinet_opened` (DAG `after`). |

**DisplayMeatVariety** (`filling_serving_dishes/display_meat_variety.py:121-142`)
| `chicken_on_tray`, `shrimp_on_tray`, `beef_on_tray` | object touches tray, centre within 0.7 × tray radius | `check_obj_in_receptacle(env, X, "serving_tray")` (default th) |
| `tray_on_dining_counter` | tray stays in contact with dining counter (true at start) | `check_obj_fixture_contact(env,"serving_tray",dining_table)` |
| (final) gripper away from all three | `gripper_obj_far` ×3 |
Optional extra diagnostic (not a DAG node): "retrieved from fridge" = `not obj_inside_of(env, X, fridge)` — useful for partial credit, threshold-free.

**MicrowaveDefrostMeat** (`microwaving_food/microwave_defrost_meat.py:78-94`)
| `drumstick_in_tupperware` | drumstick in tupperware (true at start) | `check_obj_in_receptacle(env,"meat","tupperware")` |
| `tupperware_in_microwave` | all 8 bbox corners inside cavity (5 cm tol) | `obj_inside_of(env,"tupperware",microwave)` |
| `microwave_door_closed` | door ≤ 0.5% open | `microwave.is_closed(env)`; score after `tupperware_in_microwave`. |
| `microwave_on` | start pressed with door closed | `microwave.get_state()["turned_on"]`. Stateful: updated by the fixture's per-step `update_state` (`microwave.py:85-90`), so the evaluator must read it *after* the env step, never call `update_state` itself. |
| (final) | `gripper_obj_far(env,"tupperware")` |

**AssembleCookingArray** (`frying/assemble_cooking_array.py:107-125`)
| `shrimp_in_pan` | `check_obj_in_receptacle(env,"meat","pan",th=0.07)` |
| `syrup_on_counter` | `check_obj_fixture_contact(env,"condiment",counter)` |
| `broccoli_on_counter` | `check_obj_fixture_contact(env,"vegetable",counter)` |
| (final) | `gripper_obj_far` for meat, condiment, vegetable |

Object/fixture names (`meat`, `pan`, `condiment`, ...) are from each instance's
`ep_meta.object_cfgs` / `fixture_refs`; they are stable per task class, so the
evaluator can key on the class name.

**Thresholds needing a hand choice:** only `cabinet_opened` (no upstream
predicate matches the DAG wording). Everything else is an upstream helper with
upstream constants. Two more judgment calls: (a) contact predicates are
true while the object is still held (DAG notes say "gripper still holding but
touching counter counts"), so a milestone witness may fire during transport;
report `final` vs `first_witness` separately; (b) "event" vs "state" timing is
from the DAG `mode` field, not from the simulator.

## 6. Effort, risks, order

Estimates assume one engineer familiar with ASPIRE; ranges reflect unknowns.

| # | Part | Effort | Notes |
|---|---|---|---|
| 1 | `.venv-robocasa` bootstrap + assets + numpy-2 smoke of `cap_harness` | 0.5-1.5 d | Assets copied from local image. numpy-2 fixes are the unknown. |
| 2 | Registry (5 tasks) + adapter reset/observe/step, arm-only codec, 4 cameras + depth, recorder hooks, `run.py`/`cli.py`/`contracts.py`/`registry.py` branches | 2-3 d | Copy `RobosuiteAdapter`; main delta is 1.5 composite controller and the 13-ch action. |
| 3 | EFE-instance init mode (vendored restore) + replay of EFE oracle actions as acceptance | 0.5-1 d | Gives a ground-truth "adapter is right" check. |
| 4 | Seeded init, seed-pool policy, solved-at-start rejection | 0.5 d | |
| 5 | Base/torso extensions (`get_base_pose`, `navigate_to_pose` servo, `move_torso`) | 1-2 d | No obstacle avoidance in v1. |
| 6 | Milestone protocol evaluator, 5 tasks + tests on oracle replay | 1-1.5 d | Calibrate `cabinet_opened` on the reference. |
| 7 | doctor / batch / validation selectors / skill seed flags / docs | 1 d | |
| 8 | World-frame (`odom`) public frame via `ik_request` | 1-2 d | Only if programs need to navigate between observations. |

Risks:
1. **Task difficulty vs ASPIRE's tool set.** All five are long-horizon mobile
   manipulation (EFE references: 787-1623 control steps). Several need doors,
   knobs and buttons (articulated fixtures) which ASPIRE's
   segment -> grasp -> move_to_pose stack has never been shown on. Expect low
   success; the milestone evaluator is what makes runs informative.
2. Navigation without an obstacle-aware planner (base collides with counters).
   In EFE's instances the robot already starts near the relevant fixtures, but
   tasks like DisplayMeatVariety (fridge -> dining counter) need base motion.
3. numpy 2 / Python 3.11 compatibility of `cap_harness` (untested).
4. Frame bookkeeping once the base moves (arm-base frame invalidates stored
   poses); mitigated by re-observing or by v2 `odom` frame.
5. Gripper semantics in robosuite 1.5 `GRIP` (whether intermediate positions
   hold; `gripper_holds_intermediate`, `robosuite/adapter.py:61`) **(unverified)**.
6. Scene build time and memory: kitchen scenes are large; EFE budgets 10 GiB
   for the sim container and ~0.035 s/control step CPU. Rebuilding per reset is
   seconds to tens of seconds (unverified on this host).
7. Seed-pool mismatch with EFE (layouts 1-10 vs the demos' pretrain layouts).

**Recommended order (smallest runnable slice first):**
1. Bootstrap `.venv-robocasa`; in it, build EFE's SearingMeat instance with
   vendored `make_env`/`restore`, check start SHA equals EFE's
   `RCB_START_SHA`, replay `solution/` actions to `_check_success()==True`.
   (No ASPIRE code yet; proves the stack.)
2. `RobocasaAdapter` for SearingMeat only: reset (EFE mode), 4 cameras + depth,
   `get_robot_state`, `step` with arm-only codec, recorder; run a trivial
   program (`go_home`, move EE 10 cm, open/close gripper) through
   `cap-harness run --benchmark robocasa365` and inspect videos/`run.json`.
3. Milestone evaluator for SearingMeat; verify on oracle replay that all three
   milestones witness and `protocol.json` is written.
4. Seeded init + the other four tasks in the registry + their evaluators.
5. Base/torso extensions; then iterative-debugging seed flags in the skill.
6. doctor/batch/validation plumbing; world frame only if needed.

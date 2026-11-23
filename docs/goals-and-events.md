# Goals down, events up: the list (DRAFT)

**Status: a draft from the AFT side (2026-11-22), for the wayfarer side to correct and
complete.** Words are used as defined in `docs/terminology.md`.

## What this page is for

The goal (`docs/terminology.md`): the robot boots, loads everything, and can then
carry out any mission, given as a mission script or as a request in plain English to
the brain. That needs lower layers that do not care who gives the orders, which only
works if there is one agreed list of:

- **Goals:** what mission logic (a mission script, the mission's behavior tree, or
  later a brain) may ask the lower layers to do, including which skill to run. Never
  wheel speeds.
- **Events:** what the lower layers report upward.

Whatever sits on top uses this list and nothing else. When both projects implement the
same list, a mission's behavior tree or a brain built in wayfarer can be installed on
AFT's robot without changing the layers underneath.

## Milestones

The "Needed by" column in the tables uses these.

| | Milestone | Where |
|---|---|---|
| **M1** | RF-DETR is the detector on the robot (shadow mode, then switched), under the mission script | AFT |
| **M2** | The describer is used inside a real run: loaded before "go", kept loaded, with a "ready" check | AFT |
| **M3** | A box with an untrusted name is treated as unknown; its crop goes to the describer; the answer is logged | AFT |
| **M4** | The skills run on the real robot: wayfarer's mission's behavior tree carries out a mission on AFT's robot, with no brain | Both |
| **M5** | The first brain (brain-assisted) is asked on named events, in simulation first, then on the robot | Wayfarer, then both |
| **M6** | A mission given in plain English (brain-led): the brain turns the request into a plan of skills and makes the final judgment | Wayfarer, then both |

## Goals (down)

| Goal | What it asks for | How it is carried today | AFT (real robot) | Wayfarer (simulator) | Needed by |
|---|---|---|---|---|---|
| Go to a pose | Drive to x, y and heading on the map | Nav2 action `NavigateToPose` | Yes | Yes | Now |
| Cancel the current goal | Stop driving toward it | Cancel on the same action | Yes | Yes | Now |
| Take a picture | Save the current camera frame with a tag | Inside the mission process | Yes | Yes | Now |
| Clear the costmaps | Forget remembered obstacles | Nav2 service `ClearEntireCostmap` | Yes | Yes | Now |
| Turn on the spot by an angle | Rotate without driving | Nav2 action `Spin` | **No: fails on the real robot** | Yes | **M4** |
| Drive straight a distance | Short forward move without a plan | Nav2 action `DriveOnHeading` | **Not proven** (same Nav2 component as `Spin`) | Yes | **M4** |
| Back up a distance | Short reverse move | Nav2 action `BackUp` | **No: fails on the real robot** | Yes | **M4** |
| Mark an obstacle the lidar cannot see | Tell navigation "something is at this spot" | A topic published by the mission process | No | Yes | M4 |
| Ask the describer about a crop | "Describe this image." with a time limit | Not built | No | No | M3 |
| Ask the brain for a decision | A named event, a snapshot, a short list of allowed choices | Not built (wayfarer's decision log already records the same fields) | No | No | M5 |
| Load and report ready | Load and warm everything, then say "ready" or say what is missing | Partly (`robot_boot.sh` checks IMU, battery, drivers) | Partly | No | M2 |
| Run a named skill | "Search for an object", "approach it", "go around it", "go home" | Inside the mission's behavior tree; not callable by name from outside | No | Yes, as parts of its mission's behavior tree | M4 (on the robot), M5 (by name) |
| Carry out a mission given in plain English | The request, turned into a plan of skills | Not built | No | No | M6 |
| Ask another robot to do something | A goal sent to a second robot, its events returned | Not built | No | No | After M6 |

## Events (up)

| Event | What it tells mission logic | How it is carried today | AFT (real robot) | Wayfarer (simulator) | Needed by |
|---|---|---|---|---|---|
| Pose | Where the robot believes it is | TF and AMCL | Yes | Yes | Now |
| Goal result | Reached, rejected, or timed out | Action result; reasons `goal_rejected`, `nav_timeout` | Yes | Yes | Now |
| Detections | Boxes with a name, a score and a distance | `/robot_001/detections` (`vision_msgs/Detection2DArray`) | Yes: names `yellow_ball`, `red_ball` only | Yes; its mission's behavior tree reads a `color` field | Now; changes at M1 |
| Detection with a real name and confidence | Any class the detector knows, with its score | Same topic | No | No | M1 |
| Unknown object | Something is there and no trustworthy name covers it | Not built. A detector never reports this by itself | No | No | M3 |
| Describer answer | A sentence, or "no answer" (timeout, empty, useless) | Not built | No | No | M3 |
| Free space around the robot | Clearance in a direction, whether a corridor is clear | Read from the lidar scan | The scan exists; the helper functions do not | Yes | M4 |
| Obstacle hold started / ended | The reflex is holding the wheels for something in the path | `/robot_001/obstacle_hold` (true/false) | Yes, but **nothing above the reflex listens** | No | **M4** |
| Operator hold started / ended | The reflex is holding the wheels because the operator's link went quiet | `/robot_001/operator_hold` (true/false) | Yes, but nothing above the reflex listens | No | M4 |
| Stuck | A hold has not ended, or no progress, for too long | Not built (only Nav2's timeout, 60-74 s) | No | No | M4 |
| Wheel slip | The wheels turn and the robot does not move | `/robot_001/slip/status` | Yes, observe-only | No | M4 or later |
| Battery | Pack voltage; too low to start or continue | `/robot_001/battery_voltage` | Yes | No | M4 |
| Sensor unhealthy | A sensor is streaming but dead (frozen IMU), or no camera frame | The driver refuses motion; no event is sent upward. `no_camera_frame` ends the mission | Partly | No | M4 |
| Link to the mother ship lost / restored | Whether a remote computer can be reached | Not built (the operator watch is the nearest thing) | No | No | M5 |
| Ready / not ready | The result of the load phase, with what is missing | Not built as an event | No | No | M2 |
| Skill result | A named skill finished, failed, or gave up, with a reason | Inside the mission's behavior tree and its decision log | No | Yes | M4 |
| Findings | What was found and where (an object, its name or description, its place on the map, a photo) | Photos are saved; nothing is placed on the map | No | No | M6 |

## What the draft already shows

These three are the real obstacles to M4, found by laying the two projects side by
side:

1. **Wayfarer's skills need three moves the real robot cannot do.**
   It turns, drives short distances and backs up through Nav2's `Spin`,
   `DriveOnHeading` and `BackUp` actions. On AFT's robot those belong to the Nav2
   component that fails every time ("Pose Goes Off Grid"), which is why Nav2's behavior
   tree here has no recoveries. This is the first existing-solution case from
   `CLAUDE.md`: the standard part was switched off, not root-caused. It now blocks the
   install as well as the dresser stall.
2. **The reflexes report nothing upward that anyone hears.** The holds are published
   as topics, but the mission script does not listen, and wayfarer's mission's behavior
   tree does not know they exist. A hold that never ends has no "stuck" event.
3. **The detection message is about to change** (real names and confidence at M1, an
   unknown kind at M3), and wayfarer's mission's behavior tree reads a `color` field.
   Agreeing the new fields now saves changing them twice.

Also: wayfarer's code uses simulator ground truth in places (a ground-truth odometry
topic). Anything the mission's behavior tree needs from it has no equivalent on the
real robot and should be listed here as an event the robot can actually supply, or
dropped.

## Open questions for the wayfarer side

- Is the list of goals complete for the mission's behavior tree as it is today, and
  which of its parts are the skills a brain would choose among?
- Which events would the first brain need in its snapshot that are not in the table?
- For each event marked "nothing listens": should mission logic receive it as a
  message, or ask for it when it wants it?
- One message for a detection in both projects: which fields, and what are the kinds
  (known, unknown, hazard)?

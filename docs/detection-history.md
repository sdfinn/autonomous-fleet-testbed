# Ball detection: what we built, what broke, what fixed it, and why a trained detector is next

This is the story of one small perception component, told in order, with the evidence
for each step. It exists because the hand-built detector is about to be replaced, and
the reasons for replacing it are only convincing next to what it took to get this far.

Every claim below is from this repo's session notes or measurements. Where something
was not measured, it says so.

## In five sentences

We started with color thresholding, which is the right first tool in a simulator where
the ball is the only thing of its color. On the real robot it failed three different
ways in three sessions: the floor was the ball's color, the light changed the ball's
color, and the camera's view and frame rate changed what "seen for three frames" meant.
Each failure was fixed by adding a fact that did not depend on color: first shape, then
where a ball resting on the floor can appear in the picture. That got the first real
reaction on the robot, and it also showed the ceiling: every fix was specific to round
balls on a flat floor under light we had measured. The next target is "find the dog
toys in a whole house", which is many shapes in unknown light, and that is the job
trained detectors exist for.

## Timeline

| When | What we had | What broke | What fixed it |
|---|---|---|---|
| 2026-07, simulator | Threshold in HSV, take the bounding box of every matching pixel, read distance from the box's width (`range_m = range_k / width_px`) | Nothing: in Gazebo the ball is the only yellow or red thing | — |
| 2026-07-17, simulator | Same | A ball cut by the frame edge looked narrow, so it read 2.9-6.7 m away for a true 1.1 m | Mark edge-clipped boxes and give them no distance |
| 2026-07-17, simulator | Reaction rule: a color within its distance for 3 frames in a row | Too few frames inside 1.0 m before the robot stopped | Red's distance widened from 1.0 to 1.3 m |
| 2026-08-13, real robot | The simulator's color profile as a stand-in | The red desk was a "red ball"; reproduced twice | Reactions switched off on the real robot (`MISSION2_IGNORE_REACTIONS`) so navigation could be tested |
| 2026-11-19, real robot | A profile measured on the real front camera, lamp light | The wood floor is inside the yellow band: with no ball in the room the detector reported a yellow ball 4 cm away, as wide as the picture | **Shape:** split the matching pixels into blobs and keep only the largest ball-shaped one (fill and aspect limits); a distance scale per color |
| 2026-11-20, real robot, daylight | The lamp-light profile with the shape rule | Red missed at every distance (its hue moved from 352-358 to about 330 and its saturation halved); with the curtain closed, yellow merged with the wall | **Geometry:** a ball resting on the floor has its bottom edge on a row fixed by its width (`bottom_row = 325 + 1.32 * width_px`); only blobs on that line count, and the largest one *on the line* is taken |
| 2026-11-20, real robot | Detection fixed | Yellow tracked for 22 frames and still did not react: two frames inside 0.8 m, three needed, and the robot arrived | Not fixed yet. The rule has a frame rate hidden in it |

## The three failures, and what each one taught

### 1. The background is the target's color (2026-11-19)

A color band answers "which pixels are yellow?". In a real room the answer includes the
floor. Taking the bounding box of all of them gave a "ball" the width of the picture.
No choice of band fixed it: the calibration tool's own suggested band still matched the
floor.

**The fix was to ask a second, different question:** is this group of pixels shaped like
a ball? Connected blobs, a fill ratio (a disc fills 0.785 of its bounding box), an
aspect limit. On 33 ball-free photos from that day the widest remaining false blob read
2.1 m away, against reaction distances of 0.8 m and 1.3 m.

**Lesson.** When thresholds will not separate two things, ask what else differs between
them.

### 2. The light changes the target's color (2026-11-20)

The profile was measured under a ceiling lamp. The next afternoon, with a window behind
the balls:

| | Lamp | Daylight | Curtain closed |
|---|---|---|---|
| Red ball hue | 352-358 | about 330 | 351 |
| Red ball saturation | 0.57-1.0 | 0.36-0.51 | 0.69 |
| Result with the lamp profile | found | **red missed at 0.5, 0.8, 1.05, 1.55 m** | red found, **yellow merged with the wall** |

Three repairs were tried with the balls still on the floor, and each was measured:

| Tried | Result |
|---|---|
| Lock the camera's white balance | Worse: red's hue swing between the two lights grew from 19 to 51 degrees. The light itself changes color, and automatic white balance had been partly compensating |
| Widen the red band | Found red at 0.5 and 0.8 m only, and let in a false red reading 1.36 m (the reaction line is 1.3 m) |
| Stronger clean-up of thin bridges | Rescued yellow behind the curtain, and turned a patch of floor into a ball 0.37 m away |

**The fix was a fact from physics, not from the picture.** The camera is at a fixed
height and the ball sits on the floor, so a nearer ball is both wider and lower in the
frame. Eighteen real sightings in three kinds of light sat within 26 pixels of one
straight line. Of 51 false blobs, one was within 30 pixels, and every one that read
close enough to matter was 75-359 pixels off. With that rule in place the color band
could be widened safely, and a second small rule let through a ball whose top was lost
to glare (full width, lower half only).

| Scored on every saved frame | Before | After |
|---|---|---|
| Yellow found (9 frames) | 8 | 9 |
| Red found (9 frames) | 5, and 0 of 4 in daylight | 8, and 4 of 4 in daylight |
| Nearest false yellow in 52 ball-free photos | reads 1.00 m | reads 3.06 m |

On the floor the same afternoon: both balls tracked continuously across the whole
approach, and the first real reaction on this robot. It stopped 58 cm from the red ball
by tape measure, against a last detector reading of 0.62 m.

**Lessons.** Look at the mask before tuning the threshold: the masks showed the right
pixels were being selected and the loss was in shape, which pointed at geometry. And
"the biggest blob" is a tie-break, not a test.

### 3. The rule around the detector has assumptions in it (2026-11-20)

With detection working, yellow still did not react. Its readings on the approach were
0.86, 0.84, 0.84, 0.60, 0.53 m against a 0.8 m rule. The detector delivers a frame every
0.28 s, so "three frames in a row" is about 25 cm of travel at 0.3 m/s, and the robot
reached its stop first. Earlier the same day the ball had slid out of the front camera's
narrow view (about 69 degrees) 5 cm before the reaction distance.

**Lesson.** A threshold stated in frames is a distance once you know the frame rate, and
a detector's field of view is part of the behavior that depends on it. Neither shows up
in a simulator whose camera is wider and faster than the real one.

## What the hand-built detector cannot do

Stated plainly, because these are the reasons to move on:

- **Anything that is not a round ball on a flat floor.** Both fixes are shape rules for
  that one case. A rope toy, a plush animal or a ball under a chair breaks them.
- **Light we have not measured.** Three conditions are fitted. A fourth is a guess.
- **A moving camera.** The floor line was fitted with the robot standing still; braking
  pitches the camera. Not measured.
- **Speed.** About 3.6 frames a second on the Jetson's CPU.
- **Known leftovers:** red reads near under lamp light and is missed at 1.05 m there;
  one false red at 1.46 m; nothing found in the saved reaction photo although the live
  frames a second earlier found the ball (not investigated).

## Why a trained detector is next

| Need | Hand-built | Trained detector (expected; not yet tested here) |
|---|---|---|
| Changing light | A rule per condition | Learned from many conditions |
| Many kinds of object (dog toys) | One shape rule per kind | Classes, or fine-tuning on our own photos |
| Distance | From picture width, 10-30% off when the rim washes out | From the front camera's stereo depth, on the same chip |
| Frame rate | 3.6 a second on the Jetson's CPU | The Jetson's GPU first (not yet timed); the camera's own vision chip later, if a current model converts to it |
| Why it decided something | Fully inspectable: a mask, a blob, a line | Much less so. This is the real cost |

Two facts already in hand: the front camera is running a small built-in network today
(its log reports "NN Family: mobilenet", 300x300 input) and publishing detections that
nothing reads; and the describer on the Jetson (`moondream`) judged "ball or not" correctly
on 11 of 11 crops while naming the red ball's color correctly on only 1 of 3.

## What carries over

The hand-built work is not thrown away:

- **The scoring set.** Frames at four distances in three kinds of light, plus 52
  ball-free photos, with a script that scores any detector against all of them
  (`reports/camera_cal_20261120_day/score.py`, outside git). The trained detector gets
  judged on the same frames the hand-built one was.
- **The floor rule as a sanity check.** Whatever finds an object, "an object this size
  resting on the floor must be on this row" is still true, and it gives a distance for
  anything lying on the floor.
- **The cascade** (sketched, not built): a cheap score on every frame; when unsure and
  close, pause and ask the describer on the robot about the crop; when still unsure, a
  larger model if a link exists; with no link, treat the unknown as the more dangerous
  case.
- **The method.** Rule ideas out while the scene is still set up; score every candidate
  against everything on disk; write down the limits next to the numbers.

## The first experiment (Release 2)

*Run on 2026-11-22 for questions 1 and 2; results are in the next section. Questions 3
and 4 are still open.*

Run a pretrained detector on the workstation's GPU against the saved frames plus photos
of the real dog toys. No robot needed. The questions, in order:

1. Does it find the croquet balls in all three lights, at 0.5 to 1.55 m?
2. What does it report on the 52 ball-free photos?
3. Does it find the dog toys at all, and as what class?
4. If yes to enough of those: can a model that size run on the front camera's chip, and
   at what frame rate?

The answer to 3 decides whether pretrained classes are enough or whether we collect and
label our own photos.

## First experiment results (2026-11-22, workstation only)

Pretrained detectors, no training, on the same frames that scored the hand-built
detector: 9 front-camera frames with a yellow, a dark and a red croquet ball at 0.5 to
1.55 m in three kinds of light, and 52 ball-free photos. A ball's true place in each
frame is taken from the hand-built detector (one red frame has no reference). A box
counts at confidence 0.25 or more. Scripts and saved detections are in
`reports/detect_exp_20261122/` (outside git): `exp.py`, `analyze.py`,
`second_opinion.py`.

| Detector | License | Yellow: boxed / named a ball (of 9) | Red: boxed / named (of 8) | Dark ball, no hand-built rule: boxed / named (of 8) |
|---|---|---|---|---|
| Hand-built | ours | 9 | 8 of 9 | has no rule for it |
| YOLO26 nano | AGPL-3.0 | 9 / 0 | 8 / 2 | 7 / 1 |
| YOLO26 small | AGPL-3.0 | 9 / 2 | 8 / 5 | 7 / 4 |
| YOLO26 medium | AGPL-3.0 | 9 / 5 | 8 / 8 | 7 / 7 |
| RF-DETR nano | Apache-2.0 | 9 / 8 | 8 / 7 | 8 / 8 |
| RF-DETR small | Apache-2.0 | 9 / 8 | 8 / 8 | 7 / 7 |
| YOLOE 26 small, prompted with words | AGPL-3.0 | 7 / 7 | 8 / 8 | 7 / 7 |
| YOLOE 11 small, prompted with words | AGPL-3.0 | 9 / 9 | 8 / 8 | 7 / 7 |

No detector reported a ball in any of the 52 ball-free photos. (The hand-built one has
false blobs there that read far away: nearest yellow 3.06 m, one red at 1.46 m.)

What we learned, in order of importance:

1. **Finding and naming are two different results.** Every model put a tight box on
   almost every ball. The models differ only in what they called it. The yellow ball
   was "orange" 26 times across the runs, the red one "apple" 11 times, with
   confidence up to 0.92. A pretrained detector must choose among its fixed classes; a
   croquet ball is not one of them.
2. **Confidence is not "how sure it is right".** It is "this class rather than my
   other classes". A white furniture foot seen close up was a "toilet" at 0.87. So a
   high score cannot be the signal for "known object", and a detector never says
   "unknown object": that has to come from geometry (something solid is there and no
   trustworthy name covers it).
3. **A new object needed no new rule.** The dark ball, which the hand-built detector
   cannot see at all, was boxed in 7 of 8 frames by every model.
4. **Distance from the box is better than from the color blob.** With the same
   `range_k / width` formula: mean error 6-8% and worst 12-15%, against 12% and 29% for
   the hand-built detector, because the box is tighter than a blob whose rim washes
   out.
5. **The floor-line rule carries over.** Every ball box sat within 27 pixels of
   `bottom_row = 325 + 1.32 * width`; of the other boxes (44 to 130 a model) only 3 to
   9 did. It stays useful as a check on any detector.
6. **A larger picture is not better.** At 640 pixels wide (what a Jetson would likely
   run) the YOLO26 models named the balls correctly more often than at 1280: nano 0
   to 3 yellow and 2 to 5 red; small 2 to 6 and 5 to 8; medium 5 to 8 and 8 to 8. The
   models were trained at 640, so objects then appear at the size they learned.
7. **It sees the room.** In the ball-free photos the models boxed the bed, chairs, and
   a real person sitting at a desk seen through the doorway (0.68-0.88). Also things
   that are not there: "toilet", "cake".
8. **The describer can repair a wrong name.** Crops of 25 balls and 17
   non-balls given to `moondream:1.8b` with "Describe this image.": 22 of 25 balls
   described as a ball, 17 of 17 others not, 0.2 s a crop on the workstation. With
   "Is this a ball? Answer yes or no." it returned an EMPTY answer for all 42: the
   prompt quirk recorded in `tools/vlm_canary.py` is real. So the second-opinion idea
   works, and its answer has to be read out of a description, not a yes or no.

Limits. Nine frames in one room. Round balls only: **no dog toy has been tested**,
because there are no photos of one. Times (5-12 ms a frame on an RTX 5080) say nothing
about the Jetson; nothing was run there. No model was trained or fine-tuned. The true
ball positions come from the hand-built detector, so a frame it gets wrong would
mislead the count.

What it means for the choice:

- A trained detector does replace the hand-built one for finding objects, and the two
  fixes that cost the most (shape, light) are not needed. The floor rule is kept.
- For naming, pretrained classes are not enough even for a ball. The route is a small
  model fine-tuned on our own photos (balls, dog toys), with a prompted model such as
  YOLOE used on the workstation to label those photos.
- RF-DETR did as well as anything and is Apache-2.0, the same as this repo. The YOLO
  models are AGPL-3.0. Decided the same day: see "Decisions" below.
- Still owed: dog-toy photos from the robot's front camera; one model timed on the
  Jetson; a check of the maintained ROS detector packages before writing a node.

## Decisions (Mike, 2026-11-22)

1. **RF-DETR is the detector for production; YOLO is for comparison.** "Production"
   means anything that ships in this repo, in the robot's image, or in a wayfarer brain
   release. The YOLO models (YOLO26, YOLOE) stay on the workstation for comparison and,
   later, for labeling photos.
2. **No model training for now.** Pretrained weights only, until the dog-toy photos
   show whether that is enough.

**Why RF-DETR, in short.** It named the balls as well as anything tested, and its
license matches this repo's.

| | Apache-2.0 (this repo, RF-DETR nano to large) | AGPL-3.0 (Ultralytics YOLO26, YOLOE) |
|---|---|---|
| Use it privately, experiment, label photos | Free | Free |
| Build it into your own software and share that | Allowed under any license, with attribution | Only if the whole combined work is released under AGPL too |
| A company reusing the project | No obstacle | Must open its own code under AGPL or buy a commercial license |

This is the practical reading, not legal advice. Ultralytics states that its terms also
cover the pretrained weights and models trained with its code.

**The two designs, for the record.** YOLO26 (Ultralytics, January 2026) is a
convolutional network, the long-standing YOLO family, built small and fast for edge
hardware, with the largest set of tools and guides. RF-DETR (Roboflow) is a
transformer-based detector that starts from a large general-purpose vision network pretrained on a very
large set of pictures; that broad pretraining is the likely reason it named a croquet
ball better without training (not verified). It is also the larger model: its smallest
size has roughly ten times the parameters of YOLO26 nano (from memory, not checked), so
its speed and memory on the Jetson are the first thing to measure. YOLOE is an
"open-vocabulary" YOLO: the list of things to look for is given as words at run time
("ball", "dog toy") instead of being fixed at training. It could never answer "orange"
because that word was not on its list, so part of its score comes from being told what
to look for.

**Status at the end of 2026-11-22:** workstation items 1, 2 and 3 and simulator item 1
are done (results in the sections below). What the results point to, for Mike to
confirm: RF-DETR small, in a small node of our own (option A), loading an engine built
on the Jetson from a portable ONNX file. Next are item 4 (shadow mode) and item 5.

**Next steps (order confirmed by Mike, 2026-11-22: workstation items 1-5 as numbered, with simulator item 1 done right after workstation item 1):**

*Workstation and real robot*
1. A 15-minute check of the maintained ROS detector packages before writing a node
   (the "existing-solution check" rule in `CLAUDE.md`).
2. Dog-toy photos from the robot's front camera (Jetson on its charger and Ethernet, no
   driving), scored with the same scripts.
3. One RF-DETR and one YOLO26 model timed on the Jetson with the navigation container
   running; memory recorded. Any install on the Jetson is Mike's to run.
4. A detector node in shadow mode on a floor run: it publishes and is logged while the
   hand-built detector still drives the reactions. Compare, then switch.
5. The reaction rule in seconds, not frames.

*Simulator*
1. The same models on the saved simulator photos: does a detector recognize a rendered
   ball at all?
2. The CI describer check stepped up, log-only at first: detector box, crop,
   "Describe this image.", compared with what the simulator knows is there.
3. The detection message agreed with wayfarer, including an "unknown object" kind
   (`~/wayfarer/docs/transfer/2026-11-22-detector-and-brain-from-aft.md`).

*Not yet:* training a model; running on the camera's own chip.

## Follow-up checks (2026-11-22, after the decisions)

**1. Is there a maintained ROS 2 package that already does this?** (15-minute search,
nothing installed or run.)

| Option | What it is | Fit here |
|---|---|---|
| A dedicated RF-DETR ROS 2 package | None found | — |
| NVIDIA Isaac ROS, `isaac_ros_rtdetr` | Maintained node for ROS 2 Jazzy: TensorRT on the Jetson's GPU, publishes the same `vision_msgs/Detection2DArray` we use. Isaac ROS 4.6 lists Jetson Orin with JetPack 7.2 | Built for RT-DETR, a different (also Apache-licensed) transformer detector, not RF-DETR. Whether RF-DETR's exported model fits it is unverified. A large stack to adopt for one node; NVIDIA warns about memory on small Orin Nano boards |
| The camera vendor's driver (`depthai-ros`) | Already runs a network on the camera's chip and publishes detections with distance; custom networks through a plugin | Whether RF-DETR converts to that older chip is unverified and unlikely to be simple |
| Roboflow's own Jetson route | RF-DETR exports to ONNX and TensorRT; a DeepStream guide exists. No ROS | Gives the engine, not the node |

Published speeds, none measured here: RF-DETR nano on a Jetson Orin NX with TensorRT,
78 to 166 pictures a second depending on what is counted; RF-DETR base (larger than
nano) on an Orin Nano Super, about 15 ms a picture. Our Orin Nano should be far above
the hand-built detector's 3.6 a second; the Jetson timing step will say.

Reading: there is no ready-made RF-DETR node, so there are three ways to run the
detector. Compared for Mike on 2026-11-22:

| | A. Our own small node around RF-DETR | B. NVIDIA's node with the RT-DETR model | C. On the camera's own chip |
|---|---|---|---|
| What we build | About 150 lines: picture in, model, detections out | Nothing; install and configure | A plugin for the camera driver, plus converting a model |
| Model | RF-DETR, the one we measured | RT-DETR, not measured here | Unknown whether either converts to this older chip |
| Dependencies | The Jetson's built-in GPU libraries | NVIDIA's large Isaac ROS stack | Already installed |
| Maintained by | Us | NVIDIA | The camera vendor |
| Load on the Jetson | GPU and some memory, to be measured | Similar or more | Almost none |
| Distance | Box width and the floor rule now; camera depth later | Same as A | Built in, from stereo |
| Works in the simulator, CI and HIL | Yes: reads any picture topic | Yes, with an NVIDIA GPU | No: it only sees the real camera |
| Main risk | We own the bugs | A big dependency for one node | May not be possible at all |

- **Installing wayfarer's mission's behavior tree, and later a brain:** all three
  publish the same message, so whatever sits on top does not care. With A or B the
  detector it met in the simulator is the same program that runs on the robot; with C
  it can never be tested against the real detector before it is on the robot.
- **In wayfarer:** A is the same node and model file on the workstation against the
  rendered camera, one shared copy. B means installing and maintaining Isaac ROS in
  both projects and both CI pipelines. C is not possible in a simulator.
- **Recommendation, not yet a decision:** start with A; keep B as the fallback if the
  Jetson timing shows a plain node is too slow or too heavy; keep C as a later
  optimization. Score RT-DETR alongside the others on the dog-toy photos so B stays an
  informed fallback. The choice is made after the Jetson timing.
- **Design constraint on A (from the other-devices discussion below):** load the model
  through a portable format (ONNX) with the Jetson's fast path as one backend, so the
  node is not tied to NVIDIA hardware.

**2. Do the detectors recognize the simulator's rendered balls?** Yes. Latest 30
red-reaction and 30 yellow-reaction photos from the Gazebo camera (640x480; the ball
is 39-72 pixels wide), and 30 home photos with no ball, at 640 input:

| Detector | Red named a ball (of 30) | Yellow named a ball (of 30) | "Ball" in 30 ball-free photos |
|---|---|---|---|
| RF-DETR nano | 29 | 27 | 0 |
| RF-DETR small | 29 | 27 | 0 |
| YOLO26 nano | 23 | 21 | 0 |
| YOLO26 small | 30 | 29 | 0 |
| YOLOE 11 small, prompted | 7 | 6 | 0 |

Read across both tables, RF-DETR is the only model that is good in both places:
YOLO26 small is slightly better in the simulator and clearly worse on the robot's
camera; YOLOE is the reverse.

So the CI step-up is worth designing: RF-DETR finds and names the rendered ball almost
every time. Two things to carry into that design: the model that was best on real
frames when prompted with words (YOLOE) was the worst on rendered ones, so a result in
the simulator does not predict the result on the robot; and the rendered ball is named
"sports ball" far more reliably than the real croquet ball, so the simulator is the
easy case.

## Dog toys and clutter from the robot's camera (2026-11-22)

Five arrangements on the bedroom rug, photographed by the robot's front camera with
only the camera driver running (frames in `reports/toys_20261122/`, outside git; script
`reports/detect_exp_20261122/toy_preview.py`). One frame each, confidence 0.25 or more.
What is in each frame was listed from the picture and confirmed by Mike.

| Arrangement | RF-DETR nano | RF-DETR small | YOLO26 small | YOLOE prompted (ball, dog toy, stuffed animal, shoe, bag) |
|---|---|---|---|---|
| Row at 1.3-1.6 m, daylight: 4 plush toys / 3 balls / 2 shoes | 4 / 2 / 0 | 4 / 2 / 0 | 2 / 2 / 0 | 3 / 2 / 1 (as "bag") |
| Close group, daylight: 3 plush toys (one half hidden) / 3 balls / duffel bag | 2 / 3 / no | 3 / 3 / yes | 2 / 3 / no | 3 / 2 / yes |
| Same group, curtain closed | 2 / 1 / yes | 2 / 3 / yes | 2 / 2 / no | 2 / 1 / yes |
| Clutter, curtain closed: 12 objects | 8 boxed | 9 boxed | 3 boxed | 4 boxed |
| Empty rug, curtain closed | nothing small | nothing small | nothing small | nothing |

The clutter frame, object by object (RF-DETR small's name in quotes): pink pig "apple",
green ball "apple", mug "cup", red ball "sports ball", handheld radio "cell phone",
yellow ball "sports ball", phone "cell phone", dark brown wallet "remote", watch with a
red strap "remote". Missed by RF-DETR: a blue plush toy in the shadow at the foot of
the bed (missed by every model), a sock lying flat, dark shoes by the door.

What we learned:

1. **Plush dog toys are found without training, as "teddy bear".** All four in the row
   (0.33-0.61) and the close ones at 0.85-0.92. A rope or rubber toy was not tested.
2. **Close toys do not depend on the light.** Duck and dragon scored 0.87 / 0.92 in
   daylight and 0.90 / 0.89 with the curtain closed.
3. **For general clutter RF-DETR is in a different class from the YOLO models:** 8-9 of
   12 objects boxed against 3-4. A prompted model only looks for its words.
4. **Finding is far better than naming, again.** Of RF-DETR small's nine boxes in the
   clutter frame two or three had the right name.
5. **What is missed is flat, dark, or in shadow** (sock, dark shoes, the toy under the
   bed's edge). All of these are also under the lidar's scan plane, so today nothing on
   the robot knows they are there.
6. **Small is better than nano where it is hard:** the half-hidden toy, balls in dim
   light, the watch.
7. **One repeatable false detection:** RF-DETR small boxes most of the rug as "bed"
   (0.28-0.42) in four of the five frames. A size limit or the floor rule removes it.
8. **A prompted model finds what it is told to find:** YOLOE called the watch a
   "dog toy" at 0.39.
9. **A large remote model saw everything.** The object list for the clutter frame came
   from the assistant model looking at the (brightened) picture: 12 of 12, with one
   color wrong. That is seconds a picture, over a link, and not something that runs on
   the robot: it is the "mother ship" end of the cascade.

Limits: one frame per arrangement, one room, one afternoon; no rope or rubber toys;
the robot standing still.

## Timing on the Jetson (2026-11-22)

No install was needed: JetPack 7.2 already has TensorRT 10.16 and its `trtexec` tool.
Models were exported to ONNX on the workstation, copied over, built into engines on
the Jetson (16-bit floating point) and timed there, in the 25 W power mode, with the
camera driver running and no navigation stack. Files:
`~/fleet-ci-data/tuning/trt_20261122/` on the Jetson.

| Model | Input | Pictures a second | Median time | One-time engine build | Engine file |
|---|---|---|---|---|---|
| Hand-built detector (as on 2026-11-20) | 1280x720 | 3.6 | about 280 ms | none | — |
| RF-DETR nano | 384x384 | 163 | 6.3 ms | 2 min 41 s | 59 MB |
| RF-DETR small | 512x512 | 96 | 10.5 ms | 2 min 54 s | 62 MB |
| YOLO26 nano (comparison only) | 640x640 | 249 | 4.5 ms | 7 min 0 s | 8 MB |

Memory available on the Jetson (7.5 GB total), RF-DETR small:

| State | Available |
|---|---|
| Baseline (camera driver only) | 5.7 GB |
| RF-DETR small loaded and running | 5.5 GB (about 0.2 GB for the detector) |
| Plus the describer (`moondream:1.8b` on Ollama) loaded | 3.5 GB (about 1.8 GB for the describer) |
| Lowest during an engine build | 2.8 GB |

With the describer loaded and answering one "Describe this image." on a full frame
(5.9 s), RF-DETR small still ran at 89 pictures a second; its slowest single picture
was 26 ms.

What we learned:

1. **The model is no longer the limit; the camera is.** The front camera delivered 10
   pictures a second (measured with `ros2 topic hz`; `docs/cameras.md` notes it links
   at USB 2 speed). RF-DETR small could process nine or ten times that.
2. **Small fits, so small is the choice.** Its extra cost over nano is 4 ms a picture
   and almost no memory. Nano is kept as the fallback for a weaker board.
3. **The detector and the describer fit together** with 3.5 GB to spare, and the
   describer answering barely slows the detector.
4. **The engine is built on the robot, once, per model and per software version.**
   About three minutes. It cannot be built on the workstation and copied over; the
   portable file is the ONNX one.

Not measured: the whole node (decoding the picture, resizing it, publishing the
message add time to the 10.5 ms); with the navigation container running; on a moving
robot. `trtexec` times the model alone.

## The detector node, built and bench-tested (2026-11-22, evening)

Option A from the comparison above, confirmed by Mike: our own small node.

| Piece | File | What it is |
|---|---|---|
| The arithmetic | `src/nav_fleet/nav_fleet/rfdetr_detect.py` | Picture to network input, raw output to named boxes, distance for ball-like names. Plain numpy, no ROS, no GPU code |
| Where the network runs | `src/nav_fleet/nav_fleet/rfdetr_backends.py` | One interface, two backends: a TensorRT engine on the Jetson's GPU, ONNX Runtime anywhere else. Not tied to NVIDIA hardware |
| The ROS node | `src/nav_fleet/nav_fleet/object_detector.py` | Reads camera pictures, publishes `Detection2DArray`. Shadow mode by default: `/robot_001/detections_shadow`, which nothing acts on |
| Settings | `src/nav_fleet/config/detector_rfdetr.yaml` | Score line, size filter, the names a ball arrives under |
| The switch | `scripts/robot_boot.sh`, `ROBOT_BOOT_SHADOW_DETECTOR=1` | Starts the node beside the mission on the Jetson; fatal before anything moves if it is not ready in 60 s |
| Model files | `~/fleet-ci-data/models/rfdetr-small.{onnx,engine}` on the Jetson | Not in git |

Checked so far:

- **Same answers as the reference implementation.** On the five dog-toy frames our code
  matched 43 of 44 boxes from the `rfdetr` package itself, on the workstation (ONNX
  Runtime) and on the Jetson's GPU (TensorRT): scores within 0.08, box edges within
  about 2 pixels. The one difference is a box sitting on the 0.25 score line.
- **Live on the Jetson with the real camera, no driving:** 10 pictures a second (all the
  camera delivers), about 40 ms of work a picture, a third of one processor core,
  ready 0.5 s after start plus 0.5 s for the first picture.

What the bench test taught:

1. **Time each stage before trusting a total.** The first run took 76 ms a picture when
   the network takes 13. A plain-numpy resize of the camera picture was 62 ms of it;
   OpenCV does the same resize in 8 ms with the same result.
2. **Check a filter against measured sizes, not a guess.** The rug-as-"bed" box covers
   41% of the picture, and the size filter had been set at 50%, so it let the box
   through at a score of 0.49. The line is now 35%; the real bed covers 17-20%.
3. **The picture is about a third of a second old when its detections go out** (340-440
   ms), almost all of it inside the camera's own pipeline. At 0.3 m/s the robot has
   moved about 10 cm since the picture was taken. Any reaction rule has to allow for
   that, whichever detector is used.
4. **Copying a picture is not free.** A 1280 x 720 picture is 2.7 MB; removing two
   copies of it per picture took the node from 64% of a processor core to 36%.

Not yet done: a floor run with the mission script unchanged and both detectors
recorded (needs the code pushed so the Jetson's checkout has it, and Mike with the
robot); the same with the navigation container running.

## Other devices later (discussion, 2026-11-22; nothing measured)

Mike asked how today's choices affect three possible future devices: a follower robot
on an Arduino Uno Q, a drone, and a follower robot on a Raspberry Pi. His framing: both
projects are about the brain more than the hardware. A cheap robot with a camera and
WiFi feeds pictures and sensor data to a more capable computer (the "mother ship")
that runs the brain; the brain does not run on the cheap board. A much-reduced brain on
a well-equipped Raspberry Pi 5 might give a proof of concept for a simple task.

What carries over to any device: the detection message (class, confidence, distance,
known or unknown); the detector as a separate node; a profile per device stating what
it can run and what it cannot see (`robot_profiles/`); rules written in seconds, not
frames; the Apache license choice; and the existing-solution check, since each board
has its own vendor route.

What does not carry over: RF-DETR itself. From general knowledge, not measured:

| Device | RF-DETR on board? | Likely route |
|---|---|---|
| Arduino Uno Q (a small Linux computer paired with a microcontroller, no NVIDIA GPU) | Probably not usefully | Send pictures to the mother ship; or a much smaller model; or a camera with its own chip. Arduino ships packaged detection blocks for this board: check those first |
| Raspberry Pi | Slowly at best on the processor alone | The same choices; an add-on accelerator board exists, RF-DETR on it is unknown |
| Drone | Yes if its onboard computer is a Jetson | The same node; but the floor-line rule does not apply, frame rates must be higher, and obstacle avoidance must come from depth, not a detector. The drone is cut from the roadmap; this is background |

Consequences: option C (a camera that does its own detection) is the weak option for
the Jetson and may be the right one for a weak computer; and a robot that depends on
the mother ship for detection still needs its own reflexes on board (stop when the
link goes quiet, stop for an obstacle), because a lost link must not be fatal.

Words on this page follow `docs/terminology.md`. In sections written before that
page existed, "vision model" meant the describer.

## Where the detail is

- `docs/sessions/2026-11-19.md`, section 6: the shape rule, with before and after code.
- `docs/sessions/2026-11-20.md`, sections 4 and 5: the daylight failure, the three ideas
  that did not work, the floor rule, and the floor results.
- `src/nav_fleet/nav_fleet/hsv_detect.py` and `src/nav_fleet/config/hsv_realcam.yaml`:
  the detector and its measured profile; the comments carry the numbers.
- `docs/cameras.md`: both cameras, and the plans that use them together.

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
nothing reads; and the small vision model on the Jetson judged "ball or not" correctly
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
  close, pause and ask the on-robot vision model about the crop; when still unsure, a
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
8. **The small vision model can repair a wrong name.** Crops of 25 balls and 17
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
transformer-based detector that starts from a large vision model pretrained on a very
large set of pictures; that broad pretraining is the likely reason it named a croquet
ball better without training (not verified). It is also the larger model: its smallest
size has roughly ten times the parameters of YOLO26 nano (from memory, not checked), so
its speed and memory on the Jetson are the first thing to measure. YOLOE is an
"open-vocabulary" YOLO: the list of things to look for is given as words at run time
("ball", "dog toy") instead of being fixed at training. It could never answer "orange"
because that word was not on its list, so part of its score comes from being told what
to look for.

**Next steps agreed in outline (order to be confirmed):**

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
2. The CI vision-model check stepped up, log-only at first: detector box, crop,
   "Describe this image.", compared with what the simulator knows is there.
3. The detection message agreed with wayfarer, including an "unknown object" kind
   (`~/wayfarer/docs/transfer/2026-11-22-detector-and-brain-from-aft.md`).

*Not yet:* training a model; running on the camera's own chip.

## Where the detail is

- `docs/sessions/2026-11-19.md`, section 6: the shape rule, with before and after code.
- `docs/sessions/2026-11-20.md`, sections 4 and 5: the daylight failure, the three ideas
  that did not work, the floor rule, and the floor results.
- `src/nav_fleet/nav_fleet/hsv_detect.py` and `src/nav_fleet/config/hsv_realcam.yaml`:
  the detector and its measured profile; the comments carry the numbers.
- `docs/cameras.md`: both cameras, and the plans that use them together.

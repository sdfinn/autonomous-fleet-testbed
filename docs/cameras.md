# The robot's two cameras — facts, measurements, and where to combine them

Written 2026-11-17 from a bench session (robot stationary, bedroom, evening room light).
Photos, scripts and the exposure series are in `reports/camera_compare_20261117/`
(workstation only, untracked). Everything below was measured that day unless marked
*believed* or *not tested*.

## 1. What is on the robot

| | OAK-D-Lite ("the camera we have been using") | USB camera ("the second camera") |
|---|---|---|
| Identity | Luxonis OAK-D-Lite, MXID `19443010F1EADC7D00`, USB `03e7:2485` (Intel Movidius MyriadX) | "Xitech USB Camera", USB `0abd:8050`, serial `20250606105` |
| How it is reached | ROS driver `depthai_ros_driver` (`camera.launch.py`), topics under `/oak/...`; `camera_relay` republishes to `/robot_001/camera/image_raw` | Plain webcam: `/dev/video0` (`/dev/video1` is its metadata node). Stable name: `/dev/v4l/by-id/usb-Xitech_USB_Camera_20250606105-video-index0`. No ROS driver in this repo yet; OpenCV (`cv2.VideoCapture`, MJPG) works |
| Mounting | Fixed to the chassis front (CLAUDE.md, calibration facts) | On the pan-tilt mast — confirmed: its view follows every gimbal command (section 7) |
| Colour image used | 1280 x 720 (sensor mode 1080P, scaled) | 2592 x 1944 max; also 2048x1536, 1920x1080, 1280x720, 640x480 |
| Frame rate seen | About 5.5-6 raw frames/s over ROS, although 30 is requested | Reports 30 fps (not measured under load) |
| USB link | Log says `USB SPEED: HIGH` (USB 2) although the driver asks for `SUPER` (USB 3) | USB 2 |
| Field of view | Narrow. *From the datasheet, not measured:* about 69 deg horizontal | Very wide, roughly twice the OAK's width (an object 135 px wide in the OAK frame is about 70 px in the USB frame at the same image width). Strong fisheye distortion |
| Extra abilities | Two side cameras for distance (stereo depth); on-board chip running a detection network: `/oak/nn/spatial_detections` is already published (MobileNet, 300x300 input) and nothing uses it; `/oak/imu/data` exists but carried no messages in the 2026-11-16 bag | None: picture only |
| Exposure / colour | Automatic by default; manual via `rgb.r_set_man_exposure`, `rgb.r_exposure` (microseconds), `rgb.r_iso`, and `rgb.r_set_man_whitebalance` / `rgb.r_whitebalance` on node `/oak` (settable while running) | Automatic. White balance drifted between two photos 10 minutes apart (first strongly yellow, second neutral, same light). Locking it: *not tested* |

## 2. Three balls, same scene, both cameras

Left to right: dark green, yellow, dark red, on the rug about 1 m ahead. Median colour
at the centre of each ball (hue on OpenCV's 0-179 scale, saturation and brightness 0-255).

| Ball | USB camera H / S / V | OAK (automatic) H / S / V |
|---|---|---|
| Green | 58 / 111 / 37 | 75 / 64 / 12 |
| Yellow | 21 / 244 / 206 | 17 / 194 / 107 |
| Red | 3 / 207 / 105 | 5 / 193 / 36 |

- The OAK frame is dark overall (mean 80 of 255 against the USB camera's 129-141). Its
  green ball is nearly black; hue at that brightness is unreliable (it read 75 in one
  photo and 53 in the next).
- Red and yellow are only about 15 hue units apart, and the wood floor and dresser are
  in the same orange range. That is consistent with the red-desk false positives
  (CLAUDE.md, A4).
- Red sits at the wrap-around point of the hue scale: it read 3-5 in one photo and
  175-177 in others. A red threshold must cover both ends.

## 3. OAK exposure test

Same scene, one photo per setting (`oak_exposure_series/`, with `contact_sheet.jpg`).

| Setting | Frame mean | Green V | Yellow V | Red V |
|---|---|---|---|---|
| Automatic | 82 | 12 | 108 | 37 |
| 20 ms, ISO 800 | 40 | 0 | 57 | 2 |
| 33 ms, ISO 800 | 62 | 2 | 86 | 24 |
| 33 ms, ISO 1600 (the maximum at 30 fps) | 106 | 30 | 128 | 49 |
| 10 ms, ISO 1600 | 41 | 0 | 58 | 12 |
| 5 ms, ISO 1600 | 17 | 0 | 28 | 3 |

**Result: tuning does not rescue the OAK in this light.** Automatic exposure is already
close to the ceiling. The maximum manual setting is about 30% brighter overall, and the
green ball is still very dark (30 of 255, against 37 on the USB camera, which is also
low). Nothing clipped at any setting. Going further means a longer exposure (lower
frame rate, more motion blur while driving — the 2026-11-16 arrival photo was already
blurred) or more light in the room.

## 4. Which camera for what

- **Colour (ball detection, A4 calibration): the USB camera**, with white balance and
  exposure locked first. It is brighter, sharper, and separates the three balls better.
- **Distance to an object: the OAK.** Only it can measure range.
- **Wide view / looking around: the USB camera** (it is the one on the pan-tilt).
- **Anything that measures position from the USB image** needs the fisheye corrected
  first (a one-time lens calibration).

## 5. Where and when combining them makes the robot better

In suggested order. Items 1-2 need no robot motion to build.

| # | Idea | What it fixes | Needs first |
|---|---|---|---|
| 1 | **A4 colour calibration on the USB camera** | The `hsv_gazebo.yaml` stand-in and its false positives | A ROS node publishing the USB image; white balance/exposure locked |
| 2 | **Two-camera confirmation, straight ahead**: a ball counts only when both cameras agree on colour and rough direction | False positives from furniture (each camera errs differently) | Item 1; pan-tilt pinned forward (`tools/pin_gimbal.py`); a rough mapping between the two images |
| 3 | **OAK depth for range**: colour from the USB camera, distance from the OAK | "How far is the ball" — colour thresholding cannot say | Item 2's image mapping; a check that depth works at ball size and distance |
| 4 | **Pan to search instead of spinning the chassis** | On-the-spot spins are this robot's weak point (tyre scrub, turn gain 2.8, the front-right tyre coming off its rim) | The pan angle known at every moment and published as a transform; fisheye correction |
| 5 | **See what the lidar cannot**: the lidar sees one flat slice; a camera sees rug edges, cables, low feet of furniture, overhangs | Collisions with things outside the lidar's slice | Collision avoidance working at all (the current real priority) |
| 6 | **Position check from a landmark** (a printed marker or a doorway) | Position-estimate jumps like the 0.55 m one on 2026-11-16 | The robot's own SLAM map (A3); fisheye correction |
| 7 | **Scene description** with the vision model already on the Jetson (moondream) on the wide view | "Door is closed", "something is in the hall" before a leg starts | R2 scope |
| 8 | **Try the OAK's built-in detections** (`/oak/nn/spatial_detections`) | Possibly free object detection with distance | Finding out what the default network actually recognises — *not looked at* |

**When:** none of this comes before the SLAM map and collision avoidance. Items 1-2 are
the natural content of A4; items 3-4 follow once A4 is done; 5-8 are R2/R3 material.

### Mast camera enhancements (added 2026-11-20)

On 2026-11-20 the mast camera was recorded during three floor runs with a throwaway
script (640x480, 10 frames a second, wall-clock time stamped on each frame). It was
used only as a witness, and it explained three things the bag could not:

- the robot stalled nose-to the dresser foot and was then turned by hand (the gyro
  showed a turn with the wheels at zero; the video showed why);
- the balls were placed correctly, so the missing reaction was the detector's fault;
- the yellow ball slid out of the front camera's narrow view about 5 cm before the
  reaction distance, while staying in the mast camera's wide view throughout.

| # | Enhancement | What it buys | Needs first |
|---|---|---|---|
| 9 | **Record the mast camera on every run**, started and stopped by `robot_boot.sh`, saved beside the bag and pulled back with the logs | An outside-style view of every run with no phone on a tripod; a time stamp in the picture to line it up with the bag | The recorder in the repo (today it is `~/robot_boot_debug/mast_record.py` on the Jetson only); a clean stop on Ctrl+C |
| 10 | **Publish the mast image as a ROS topic** (small, compressed, a few frames a second) | The video is inside the bag, on the bag's clock, and available to every idea below | A small camera node; a CPU and USB budget check with the OAK running |
| 11 | **Wide-view hand-off for ball tracking**: when a ball being tracked leaves the front camera's frame, the mast camera keeps its bearing | Reactions no longer depend on the ball staying inside a ~69 deg view while the robot passes it | Item 10; fisheye correction; a rough mapping between the two images (item 2) |
| 12 | **Pan to follow** a tracked ball or a goal, instead of pointing fixed ahead | The ball stays centred in the wide view; later, look where the robot is about to turn | A gimbal command path inside `esp32_driver` (the serial port is exclusive); the pan angle published as a transform (item 4) |
| 13 | **Pre-start scene check**: compare the mast view (and the first lidar scan) with a stored reference of the home spot before the first goal | Catches "robot not on the home spot", "door in a different state from the map" and a wrong starting pose before the robot moves | A stored reference per home spot; ties in with items 6 and 7 |
| 14 | **Crops for the confidence cascade**: the wide view supplies the picture that the on-robot vision model (and, when unsure, a larger one) is asked about | A second opinion from a different lens and different lighting response than the front camera | The cascade itself (`docs/sessions/2026-11-20.md`); item 10 |
| 15 | **Operator view during attended runs**: a low-rate picture over the same link the operator watch already uses | The operator sees what the robot faces without walking beside it | Item 10; a bandwidth check on the roaming WiFi link |

**When:** item 9 is cheap and pays on every floor run; it comes first. Item 10 is the
gate for everything else. Items 11-14 belong with the next version of ball detection
(A4); item 15 is a convenience.

## 6. Open questions

- Why does the OAK link at USB 2 speed (cable, port or hub)? At USB 3 the frame rate
  should rise from about 6 fps.
- Can the USB camera's white balance and exposure be locked through OpenCV/V4L2?
- How well does either camera do in daylight? Everything here is evening room light.
  *Partly answered 2026-11-20 for the OAK:* with a bright window behind the balls the
  red ball's hue moves from 352-358 to about 330 and its saturation halves, so the
  lamp-light colour band misses it at every distance; yellow is still found but reads
  10-30% too far. With the curtain closed it is the other way round (red found, yellow
  merged with the wall). Locking the OAK's white balance made the swing larger, not
  smaller. The mast camera has not been measured in daylight.
- Does a second camera stream fit in the Jetson's CPU and USB budget during a mission?
  *Partly answered 2026-11-20:* recording the mast camera at 640x480, 10 frames a
  second, at low priority ran through three full three-trip missions with every leg
  completing and no operator-watch pause. CPU load was not measured.

## 7. Pan-tilt test

`tools/pin_gimbal.py` (serial command T:133, driver layer stopped) moved the mast and the
USB camera took a photo at each pose: `reports/camera_compare_20261117/gimbal/`
(`contact_sheet.jpg` shows all five). Script: `gimbal_look.sh` in the same folder.

| Command | What the photo shows |
|---|---|
| pan 0, tilt 0 | Balls centred, bed left, dresser right |
| pan +35 | View swings right: dresser centred, hallway visible past it |
| pan -35 | View swings left: bed centred, desk chair at the left edge |
| tilt +25 | View rises: ceiling light, balls at the bottom edge |
| tilt -20 | View drops: mostly rug, the robot's own front edge at the bottom |

- Signs confirmed by picture: pan positive = right, negative = left; tilt positive = up
  (until now only inferred), negative = down.
- A 35 deg pan either way keeps the area straight ahead in frame, because the lens is so
  wide: three poses (-35, 0, +35) cover well over half a circle without moving the chassis.
- At tilt -20 the robot's own body enters the picture; a detector would need that
  region masked.
- The mast was returned to pan 0 / tilt 0 afterwards. The serial port can only be held by
  one program, so the gimbal cannot be commanded this way while `esp32_driver` is running;
  panning during a mission needs a gimbal command path inside the driver.

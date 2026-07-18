# Copyright 2026 Mike
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""sensor_msgs/Image -> PNG, without importing ROS.

Duck-typed on purpose: takes anything with .height/.width/.step/.encoding/.data so the
conversion is unit-testable on CI runners without ROS2 (the actual sensor_msgs.msg.Image
instances arrive only inside mission_runner, which never runs there).
"""
import numpy as np
from PIL import Image as PILImage


def image_msg_to_rgb(msg):
    """Decode one sensor_msgs/Image (rgb8/bgr8, row padding OK) to an RGB uint8 array."""
    if msg.encoding not in ('rgb8', 'bgr8'):
        raise ValueError(f'unsupported image encoding: {msg.encoding}')
    # `step` is the stride in bytes per row (may exceed width*3 due to padding).
    arr = np.frombuffer(bytes(msg.data), dtype=np.uint8).reshape(msg.height, msg.step)
    arr = arr[:, : msg.width * 3].reshape(msg.height, msg.width, 3)
    if msg.encoding == 'bgr8':
        arr = arr[:, :, ::-1]
    return arr


def image_msg_to_png(msg, path):
    """Write one camera frame to `path` as PNG. Supports rgb8 and bgr8 encodings."""
    PILImage.fromarray(image_msg_to_rgb(msg), 'RGB').save(path)


PAIR_DOWNSAMPLE = 32  # grayscale grid the pair-check compares on (Task 13 return fidelity)


def photo_similarity(path_a, path_b, size=PAIR_DOWNSAMPLE):
    """Return-fidelity metric (Task 13 §3): mean absolute grayscale pixel difference between
    two saved photos, downsampled to `size`x`size`, normalised to [0.0, 1.0] where 0.0 is
    identical and 1.0 is maximally different.

    Why this metric: dependency-light (pillow + numpy, already required by this module),
    deterministic, and the downsample makes it tolerant of the small, expected differences
    between the home reference photo and the home arrival photo (Nav2 goal tolerance is a
    few cm and RegulatedPurePursuit's rotate-to-heading can leave up to ~17 deg of final
    yaw error, so the arrival frame is a slightly parallaxed/rotated view of the same
    scene, not a pixel-perfect copy). The judge's threshold (HOME_PAIR_MAX_DIFF in
    tools/mission2_harness.py) is calibrated from real runs to absorb exactly that.
    Raises OSError/ValueError (from PIL) on an unreadable path — callers decide how to
    treat a missing/corrupt photo."""
    a = np.asarray(PILImage.open(path_a).convert('L').resize((size, size)), dtype=np.int16)
    b = np.asarray(PILImage.open(path_b).convert('L').resize((size, size)), dtype=np.int16)
    return float(np.mean(np.abs(a - b))) / 255.0

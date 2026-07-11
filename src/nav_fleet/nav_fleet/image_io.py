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


def image_msg_to_png(msg, path):
    """Write one camera frame to `path` as PNG. Supports rgb8 and bgr8 encodings."""
    if msg.encoding not in ('rgb8', 'bgr8'):
        raise ValueError(f'unsupported image encoding: {msg.encoding}')
    # `step` is the stride in bytes per row (may exceed width*3 due to padding).
    arr = np.frombuffer(bytes(msg.data), dtype=np.uint8).reshape(msg.height, msg.step)
    arr = arr[:, : msg.width * 3].reshape(msg.height, msg.width, 3)
    if msg.encoding == 'bgr8':
        arr = arr[:, :, ::-1]
    PILImage.fromarray(arr, 'RGB').save(path)

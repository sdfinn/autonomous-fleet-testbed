# Copyright 2026 Mike
# SPDX-License-Identifier: Apache-2.0
"""nav_fleet.object_detector: the ROS wrapper around the RF-DETR detector.

Imports rclpy at module level, so this file is --ignore'd in stage 1 (bare Ubuntu) and
runs where ROS is installed. No network is loaded: the backend is a fake."""
import math

import numpy as np
import pytest
import rclpy
from sensor_msgs.msg import Image
from vision_msgs.msg import Detection2DArray

from nav_fleet import object_detector
from nav_fleet.rfdetr_detect import Detection


class _FakeBackend:
    input_hw = (64, 64)
    closed = False

    def infer(self, batch):
        boxes = np.full((1, 4, 4), 0.01, dtype=np.float32)
        logits = np.full((1, 4, 91), -12.0, dtype=np.float32)
        boxes[0, 1] = (0.5, 0.5, 0.1, 0.2)
        logits[0, 1, 37] = 2.0                      # sports ball, score 0.88
        return boxes, logits

    def close(self):
        self.closed = True


@pytest.fixture
def node(tmp_path, monkeypatch):
    model = tmp_path / 'fake.onnx'
    model.write_bytes(b'x')
    backend = _FakeBackend()
    monkeypatch.setattr(object_detector, 'make_backend', lambda kind, path: backend)
    rclpy.init(args=['--ros-args', '-p', 'model_path:=%s' % model])
    made = object_detector.ObjectDetector()
    yield made
    made.close()
    made.destroy_node()
    rclpy.shutdown()
    assert backend.closed


def _image(node, encoding='rgb8'):
    msg = Image()
    msg.height, msg.width, msg.step, msg.encoding = 72, 128, 128 * 3, encoding
    msg.data = bytes(72 * 128 * 3)
    msg.header.frame_id = 'camera_link'
    msg.header.stamp = node.get_clock().now().to_msg()
    return msg


def test_shadow_topic_is_the_default_and_a_picture_gives_one_array(node):
    assert node.pub.topic_name == object_detector.SHADOW_TOPIC
    sent = []
    node.pub.publish = sent.append
    node._image_cb(_image(node))
    (array,) = sent
    assert isinstance(array, Detection2DArray) and array.header.frame_id == 'camera_link'
    (det,) = array.detections
    assert det.results[0].hypothesis.class_id == 'sports ball'
    assert det.results[0].hypothesis.score == pytest.approx(0.88, abs=0.01)
    assert det.bbox.center.position.x == pytest.approx(64.0, abs=0.01)
    assert det.bbox.size_x == pytest.approx(12.8, abs=0.01)
    assert node.stats.count == 1 and node.stats.boxes == 1


def test_picture_is_read_without_a_copy_and_padding_is_dropped():
    msg = Image()
    msg.height, msg.width, msg.step, msg.encoding = 2, 3, 12, 'bgr8'    # 3 bytes of padding a row
    msg.data = bytes(range(24))
    picture, bgr = object_detector.image_msg_to_array(msg)
    assert bgr and picture.shape == (2, 3, 3)
    assert picture[0].ravel().tolist() == list(range(9))
    assert picture[1].ravel().tolist() == list(range(12, 21))
    assert not picture.flags['OWNDATA']


def test_an_unsupported_picture_is_skipped_not_fatal(node):
    sent = []
    node.pub.publish = sent.append
    node._image_cb(_image(node, encoding='mono8'))
    assert sent == [] and node._bad_frames == 1 and node.stats.count == 0


def test_message_carries_distance_or_nan():
    header = Image().header
    array = object_detector.to_detection_array(
        [Detection('sports ball', 0.8, 10, 20, 96, 100, 1.0),
         Detection('teddy bear', 0.6, 0, 0, 50, 50, float('nan')),
         Detection('orange', 0.7, 200, 20, 286, 100, 1.0, 'yellow')], header)
    first, second, third = array.detections
    # A ball whose color was read goes out under the name the mission reacts to.
    assert [d.results[0].hypothesis.class_id for d in array.detections] == [
        'sports ball', 'teddy bear', 'yellow_ball']
    assert first.results[0].pose.pose.position.x == 1.0
    assert math.isnan(second.results[0].pose.pose.position.x)
    assert (first.bbox.center.position.y, first.bbox.size_y) == (60.0, 80.0)


def test_stats_line_reads_sensibly():
    stats = object_detector.FrameStats()
    assert 'no pictures' in stats.line(10.0)
    stats.add(20.0, 100.0, 2)
    stats.add(30.0, 140.0, 0)
    line = stats.line(10.0)
    assert '0.2 pictures/s' in line and 'mean 25.0 ms, worst 30.0 ms' in line
    assert 'age at publish 120 ms' in line and '1.0 boxes' in line


def test_a_missing_model_file_stops_the_node(tmp_path):
    rclpy.init(args=['--ros-args', '-p', 'model_path:=%s' % (tmp_path / 'none.engine')])
    try:
        with pytest.raises(RuntimeError, match='model file not found'):
            object_detector.ObjectDetector()
    finally:
        rclpy.shutdown()

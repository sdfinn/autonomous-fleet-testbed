# Copyright 2026 Mike
# SPDX-License-Identifier: Apache-2.0
"""Compare the two detectors on one recorded run (shadow mode, 2026-11-22).

A run started with ROBOT_BOOT_SHADOW_DETECTOR=1 records two topics in its bag:
  /robot_001/detections          the hand-written detector; the mission reacts to this one
  /robot_001/detections_shadow   RF-DETR; nothing acts on it
Both saw the same pictures. This tool lines them up by each picture's own time stamp and
answers, for every object the hand-written detector tracked: did RF-DETR box the same
thing, under what name, how early did each first see it, and how far apart were the two
distance readings. It also lists what RF-DETR saw that the hand-written detector has no
rule for.

    python -m tools.shadow_compare <bag folder>

The comparison itself (`compare`) is plain Python on lists, tested without ROS. Only
`read_bag` needs a ROS environment (rosbag2_py), and imports it when called.
"""
import collections
import math
import statistics
import sys

MAIN_TOPIC = '/robot_001/detections'
SHADOW_TOPIC = '/robot_001/detections_shadow'
# The two nodes stamp a detection with its picture's stamp, so the same picture has the
# same stamp on both topics. The tolerance only absorbs rounding.
SAME_PICTURE_S = 0.005

Box = collections.namedtuple('Box', 'name score range_m cx cy width height')
Frame = collections.namedtuple('Frame', 'stamp boxes')


def boxes_from_msg(msg):
    """vision_msgs/Detection2DArray -> Frame (duck-typed, so tests need no ROS)."""
    boxes = []
    for det in msg.detections:
        if not det.results:
            continue
        hyp = det.results[0]
        boxes.append(Box(hyp.hypothesis.class_id, float(hyp.hypothesis.score),
                         float(hyp.pose.pose.position.x),
                         float(det.bbox.center.position.x), float(det.bbox.center.position.y),
                         float(det.bbox.size_x), float(det.bbox.size_y)))
    stamp = msg.header.stamp.sec + msg.header.stamp.nanosec * 1e-9
    return Frame(stamp, boxes)


def same_object(a, b):
    """True when box b sits on box a: b's center is inside a (grown by half its size)
    and the two are within a factor of two in width."""
    if not (a.width > 0 and b.width > 0):
        return False
    inside = (abs(b.cx - a.cx) <= a.width and abs(b.cy - a.cy) <= a.height)
    return inside and 0.5 <= b.width / a.width <= 2.0


def pair_frames(main, shadow, tolerance_s=SAME_PICTURE_S):
    """[(main frame, shadow frame or None)] for every main frame, by picture stamp."""
    by_stamp = sorted(shadow, key=lambda f: f.stamp)
    stamps = [f.stamp for f in by_stamp]
    pairs = []
    index = 0
    for frame in sorted(main, key=lambda f: f.stamp):
        while index + 1 < len(stamps) and abs(stamps[index + 1] - frame.stamp) <= abs(
                stamps[index] - frame.stamp):
            index += 1
        match = by_stamp[index] if stamps and abs(
            stamps[index] - frame.stamp) <= tolerance_s else None
        pairs.append((frame, match))
    return pairs


def compare(main, shadow):
    """Summary dict for one run. `main` and `shadow` are lists of Frame."""
    pairs = pair_frames(main, shadow)
    paired = [(m, s) for m, s in pairs if s is not None]
    t0 = min([f.stamp for f in main + shadow], default=0.0)
    objects = {}
    for m, s in paired:
        for box in m.boxes:
            entry = objects.setdefault(box.name, {
                'frames': 0, 'also_boxed': 0, 'names': collections.Counter(),
                'range_diff': [], 'first_main_s': None, 'first_main_range': None})
            entry['frames'] += 1
            if entry['first_main_s'] is None:
                entry['first_main_s'] = m.stamp - t0
                entry['first_main_range'] = box.range_m
            hits = [b for b in s.boxes if same_object(box, b)]
            if hits:
                best = max(hits, key=lambda b: b.score)
                entry['also_boxed'] += 1
                entry['names'][best.name] += 1
                if math.isfinite(box.range_m) and math.isfinite(best.range_m):
                    entry['range_diff'].append(best.range_m - box.range_m)
    shadow_only = collections.Counter()
    for m, s in pairs:
        if s is None:
            continue
        for b in s.boxes:
            if not any(same_object(a, b) for a in m.boxes):
                shadow_only[b.name] += 1
    unpaired_shadow = collections.Counter()
    main_stamps = {round(f.stamp, 2) for f in main}
    for f in shadow:
        if round(f.stamp, 2) not in main_stamps:
            unpaired_shadow.update(b.name for b in f.boxes)
    return {
        'main_frames': len(main), 'shadow_frames': len(shadow), 'paired_frames': len(paired),
        'main_rate_hz': _rate(main), 'shadow_rate_hz': _rate(shadow),
        'objects': objects, 'shadow_only': shadow_only, 'unpaired_shadow': unpaired_shadow,
    }


def _rate(frames):
    if len(frames) < 2:
        return 0.0
    stamps = sorted(f.stamp for f in frames)
    span = stamps[-1] - stamps[0]
    return (len(stamps) - 1) / span if span > 0 else 0.0


def report(summary):
    lines = ['pictures: hand-written detector %d (%.1f a second), RF-DETR %d (%.1f a second), '
             'same picture on both %d' % (
                 summary['main_frames'], summary['main_rate_hz'], summary['shadow_frames'],
                 summary['shadow_rate_hz'], summary['paired_frames'])]
    if not summary['objects']:
        lines.append('the hand-written detector reported no object in any shared picture')
    for name, e in sorted(summary['objects'].items()):
        lines.append('%s: in %d shared pictures; RF-DETR boxed the same object in %d (%.0f%%)' % (
            name, e['frames'], e['also_boxed'], 100.0 * e['also_boxed'] / e['frames']))
        if e['names']:
            lines.append('    RF-DETR called it: ' + ', '.join(
                '%s x%d' % kv for kv in e['names'].most_common()))
        if e['range_diff']:
            lines.append('    distance, RF-DETR minus hand-written: median %+.2f m, worst %+.2f m '
                         '(%d pictures with both)' % (
                             statistics.median(e['range_diff']),
                             max(e['range_diff'], key=abs), len(e['range_diff'])))
        lines.append('    first seen by the hand-written detector %.1f s into the run, reading %s'
                     % (e['first_main_s'], _meters(e['first_main_range'])))
    if summary['shadow_only']:
        lines.append('RF-DETR boxes with no hand-written counterpart (shared pictures): '
                     + ', '.join('%s x%d' % kv for kv in summary['shadow_only'].most_common(12)))
    if summary['unpaired_shadow']:
        lines.append('RF-DETR boxes in pictures the hand-written detector never processed: '
                     + ', '.join('%s x%d' % kv
                                 for kv in summary['unpaired_shadow'].most_common(12)))
    return '\n'.join(lines)


def _meters(value):
    return '%.2f m' % value if math.isfinite(value) else 'no distance'


def read_bag(bag_dir, topics=(MAIN_TOPIC, SHADOW_TOPIC)):
    """{topic: [Frame]} from a rosbag2 folder. Needs a sourced ROS environment."""
    import rosbag2_py
    from rclpy.serialization import deserialize_message
    from vision_msgs.msg import Detection2DArray
    reader = rosbag2_py.SequentialReader()
    reader.open(rosbag2_py.StorageOptions(uri=bag_dir, storage_id=''),
                rosbag2_py.ConverterOptions('', ''))
    reader.set_filter(rosbag2_py.StorageFilter(topics=list(topics)))
    frames = {topic: [] for topic in topics}
    while reader.has_next():
        topic, data, _ = reader.read_next()
        frames[topic].append(boxes_from_msg(deserialize_message(data, Detection2DArray)))
    return frames


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1:
        print(__doc__.split('\n\n')[0])
        print('usage: python -m tools.shadow_compare <bag folder>')
        return 2
    frames = read_bag(argv[0])
    if not frames[SHADOW_TOPIC]:
        print('no messages on %s: was the run started with ROBOT_BOOT_SHADOW_DETECTOR=1?'
              % SHADOW_TOPIC)
        return 1
    print(report(compare(frames[MAIN_TOPIC], frames[SHADOW_TOPIC])))
    return 0


if __name__ == '__main__':
    sys.exit(main())

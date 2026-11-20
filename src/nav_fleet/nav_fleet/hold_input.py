# Copyright 2026 Mike
# SPDX-License-Identifier: Apache-2.0
"""One "do not turn the wheels" input. Pure logic, no ROS.

Lives in its own file because two things apply holds with the same rule: the real
motor driver (esp32_driver) and the simulator's stand-in for it (sim_wheel_hold).
"""

# Hold topics arrive at 10 Hz; a value older than this says nothing any more.
HOLD_STALE_S = 0.5


class HoldInput:
    """One "do not turn the wheels" input: a Bool topic published by a watcher.

    A fresh True holds. If the watcher is `required` for this run, silence holds too --
    a watcher that has died cannot say the way is safe. If it is not required, silence
    means nothing (and an old True does not trap the robot for ever).
    """

    def __init__(self, topic, when_true, when_silent):
        self.topic = topic
        self.when_true = when_true          # log text, e.g. 'operator unreachable'
        self.when_silent = when_silent      # log text, e.g. 'no operator watch running'
        self.value = False
        self.time = None                    # time.time() of the last message
        self.held = False                   # last state reported, for one log line per change

    def update(self, value, now):
        self.value = bool(value)
        self.time = now

    def state(self, now, required):
        """(holding, reason) right now."""
        if self.time is not None and now - self.time < HOLD_STALE_S:
            return self.value, self.when_true
        return bool(required), self.when_silent

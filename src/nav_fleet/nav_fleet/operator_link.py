# Copyright 2026 Mike
# SPDX-License-Identifier: Apache-2.0
"""Is the operator still there? The decision logic and the beeps, with no ROS in it.

An ATTENDED real-robot run is started by someone over SSH who expects Ctrl+C to work.
When the WiFi link drops, Ctrl+C goes nowhere and the mission carries on (a dropped
link sends no hang-up; found 2026-11-17/18). `operator_watch` (the node) pings the
operator's machine five times a second and feeds the answers to LinkWatch here, which
decides:

    OK  --no answer for pause_after_s-->  PAUSED     wheels held, two short beeps
    PAUSED  --an answer-->  RESUMING                 one long beep, wheels still held
    RESUMING  --resume_delay_s later, link still answering-->  OK    wheels released
    PAUSED  --give_up_after_s without an answer-->  GAVE_UP          three low beeps;
                                                     the node exits and robot_boot.sh
                                                     shuts the mission down

Why pause instead of stopping the run (Mike, 2026-11-19): this robot's WiFi adapter
changes radio band on its own while driving, and each change is about 2.4 s of
silence. Aborting on that threw away good runs; a pause costs a few seconds. The beep
before moving again is there because a robot that has stood still for several seconds
and then drives off by itself is a surprise to anyone who has walked up to it.
"""
import math
import struct

OK = 'ok'
PAUSED = 'paused'
RESUMING = 'resuming'
GAVE_UP = 'gave_up'

# Events returned by LinkWatch.step(), in the order they happened.
LOST = 'lost'            # -> PAUSED
REGAINED = 'regained'    # -> RESUMING
RESUMED = 'resumed'      # -> OK
GIVE_UP = 'give_up'      # -> GAVE_UP

# In RESUMING, the link counts as "still answering" if the last answer is this recent.
# Pings go out every 0.2 s, so this allows two lost in a row.
FRESH_REPLY_S = 0.6


class LinkWatch:
    """Times are seconds on any monotonic clock; the caller supplies `now` everywhere."""

    def __init__(self, now, pause_after_s=2.0, give_up_after_s=10.0, resume_delay_s=1.0):
        if not (pause_after_s > 0 and give_up_after_s > 0 and resume_delay_s >= 0):
            raise ValueError('pause_after_s and give_up_after_s must be > 0, '
                             'resume_delay_s >= 0')
        self.pause_after_s = float(pause_after_s)
        self.give_up_after_s = float(give_up_after_s)
        self.resume_delay_s = float(resume_delay_s)
        self.state = OK
        self.pauses = 0
        self.longest_silence_s = 0.0
        self._last_reply = float(now)
        self._paused_at = None
        self._resume_at = None

    @property
    def hold(self):
        """True whenever the wheels must not turn."""
        return self.state != OK

    def reply(self, now):
        """The operator's machine answered a ping."""
        self.longest_silence_s = max(self.longest_silence_s, now - self._last_reply)
        self._last_reply = float(now)

    def step(self, now):
        """Advance to `now`; returns the events that happened (usually none)."""
        silence = now - self._last_reply
        self.longest_silence_s = max(self.longest_silence_s, silence)
        events = []
        if self.state == OK:
            if silence >= self.pause_after_s:
                self._pause(now, events)
        elif self.state == PAUSED:
            if self._last_reply > self._paused_at:
                self.state = RESUMING
                self._resume_at = now + self.resume_delay_s
                events.append(REGAINED)
            elif now - self._paused_at >= self.give_up_after_s:
                self.state = GAVE_UP
                events.append(GIVE_UP)
        elif self.state == RESUMING:
            if silence >= self.pause_after_s:
                self._pause(now, events)           # lost it again: a new pause
            elif now >= self._resume_at and silence <= FRESH_REPLY_S:
                self.state = OK
                events.append(RESUMED)
        return events

    def _pause(self, now, events):
        self.state = PAUSED
        self.pauses += 1
        self._paused_at = float(now)
        events.append(LOST)


def is_reply_line(line):
    """True for a line `ping` prints when a probe WAS answered.

    Answered:    64 bytes from 192.168.1.119: icmp_seq=7 ttl=64 time=3.21 ms
    Unanswered:  no answer yet for icmp_seq=8          (ping -O)
    """
    return 'bytes from' in line


# (frequency in Hz or 0 for silence, seconds). Chosen to be told apart by ear with the
# motors running: lost = two short high, regained = one long, give up = three low.
BEEPS = {
    LOST: [(1320, 0.12), (0, 0.10), (1320, 0.12)],
    REGAINED: [(880, 0.60)],
    GIVE_UP: [(440, 0.35), (0, 0.15), (440, 0.35), (0, 0.15), (440, 0.35)],
}
BEEP_RATE_HZ = 44100


def beep_samples(pattern, rate=BEEP_RATE_HZ, volume=0.6):
    """16-bit mono samples for a [(freq, seconds)] pattern, with 5 ms fades so the
    speaker does not click, and 50 ms of silence first (USB audio devices swallow the
    first few milliseconds after they wake up)."""
    out = [0] * int(rate * 0.05)
    fade = max(1, int(rate * 0.005))
    for freq, seconds in pattern:
        n = int(rate * seconds)
        for i in range(n):
            if not freq:
                out.append(0)
                continue
            envelope = min(1.0, i / fade, (n - 1 - i) / fade)
            out.append(int(32767 * volume * envelope * math.sin(2 * math.pi * freq * i / rate)))
    return out


def write_beep_wav(path, pattern, rate=BEEP_RATE_HZ):
    """Write `pattern` as a WAV file `aplay` can play."""
    import wave
    samples = beep_samples(pattern, rate)
    with wave.open(str(path), 'wb') as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        wav.writeframes(struct.pack(f'<{len(samples)}h', *samples))
    return path

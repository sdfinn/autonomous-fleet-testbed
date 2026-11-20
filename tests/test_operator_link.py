# Copyright 2026 Mike
# SPDX-License-Identifier: Apache-2.0
"""LinkWatch: when a lost operator link pauses the robot, resumes it, or ends the run.
No ROS (stage-1 safe)."""
import wave

import pytest

from nav_fleet.operator_link import (
    BEEPS, GAVE_UP, GIVE_UP, LOST, OK, PAUSED, REGAINED, RESUMED, RESUMING,
    LinkWatch, beep_samples, is_reply_line, write_beep_wav)


def _run(watch, start, stop, reply_until=None, dt=0.1):
    """Step the watch from start to stop; the link answers every 0.2 s until
    reply_until (None = never answers). Returns [(time, event)]."""
    events = []
    steps = int(round((stop - start) / dt))
    for i in range(1, steps + 1):
        t = start + i * dt
        if reply_until is not None and t <= reply_until and i % 2 == 0:
            watch.reply(t)
        events += [(round(t, 2), e) for e in watch.step(t)]
    return events


def test_a_healthy_link_never_holds_the_robot():
    watch = LinkWatch(now=0.0)
    assert _run(watch, 0.0, 60.0, reply_until=60.0) == []
    assert watch.state == OK and not watch.hold and watch.pauses == 0


def test_silence_shorter_than_the_limit_is_not_a_pause():
    """A healthy WiFi link loses the odd ping; 2026-11-19's first watch stopped a good
    run on two lost in a row."""
    watch = LinkWatch(now=0.0, pause_after_s=2.0)
    watch.reply(1.0)
    assert _run(watch, 1.0, 2.9) == []                 # 1.9 s of silence
    watch.reply(2.95)
    assert _run(watch, 2.95, 4.0, reply_until=4.0) == []
    assert not watch.hold
    assert watch.longest_silence_s == pytest.approx(1.95, abs=0.01)


def test_two_seconds_of_silence_pauses():
    watch = LinkWatch(now=0.0, pause_after_s=2.0)
    events = _run(watch, 0.0, 3.0)
    assert events == [(2.0, LOST)]
    assert watch.state == PAUSED and watch.hold and watch.pauses == 1


def test_a_band_change_pauses_then_resumes_after_the_warning_delay():
    """The real case: about 2.4 s of silence, then the link is back."""
    watch = LinkWatch(now=0.0, pause_after_s=2.0, resume_delay_s=1.0)
    events = _run(watch, 0.0, 2.4)                     # silent
    events += _run(watch, 2.4, 6.0, reply_until=6.0)   # answering again from 2.6
    assert [e for _, e in events] == [LOST, REGAINED, RESUMED]
    lost_t, regained_t, resumed_t = (t for t, _ in events)
    assert lost_t == 2.0
    assert regained_t == pytest.approx(2.6, abs=0.11)
    # Held for the whole warning delay after the "regained" beep, then released.
    assert resumed_t - regained_t == pytest.approx(1.0, abs=0.11)
    assert watch.state == OK and not watch.hold


def test_the_robot_stays_held_between_regained_and_resumed():
    watch = LinkWatch(now=0.0, pause_after_s=2.0, resume_delay_s=1.0)
    _run(watch, 0.0, 2.5)
    watch.reply(2.6)
    assert watch.step(2.6) == [REGAINED]
    assert watch.state == RESUMING and watch.hold


def test_gives_up_after_ten_more_seconds_without_an_answer():
    watch = LinkWatch(now=0.0, pause_after_s=2.0, give_up_after_s=10.0)
    events = _run(watch, 0.0, 15.0)
    assert events == [(2.0, LOST), (12.0, GIVE_UP)]
    assert watch.state == GAVE_UP and watch.hold


def test_giving_up_is_final_even_if_the_link_comes_back():
    watch = LinkWatch(now=0.0, pause_after_s=2.0, give_up_after_s=10.0)
    _run(watch, 0.0, 13.0)
    assert _run(watch, 13.0, 20.0, reply_until=20.0) == []
    assert watch.state == GAVE_UP and watch.hold


def test_a_single_answer_followed_by_silence_does_not_release_the_robot():
    """One stray reply in the middle of an outage must not start the robot moving."""
    watch = LinkWatch(now=0.0, pause_after_s=2.0, give_up_after_s=10.0, resume_delay_s=1.0)
    _run(watch, 0.0, 3.0)
    watch.reply(3.05)
    events = _run(watch, 3.05, 20.0)                   # then nothing, ever
    assert RESUMED not in [e for _, e in events]
    assert [e for _, e in events] == [REGAINED, LOST, GIVE_UP]
    assert watch.pauses == 2


def test_longest_silence_is_recorded_for_the_log():
    watch = LinkWatch(now=0.0)
    watch.reply(0.2)
    watch.reply(1.9)
    watch.step(2.0)
    assert watch.longest_silence_s == pytest.approx(1.7)


@pytest.mark.parametrize('kwargs', [
    {'pause_after_s': 0}, {'give_up_after_s': -1}, {'resume_delay_s': -0.1}])
def test_nonsense_timings_are_refused(kwargs):
    with pytest.raises(ValueError):
        LinkWatch(now=0.0, **kwargs)


def test_ping_lines_are_told_apart():
    assert is_reply_line('64 bytes from 192.168.1.119: icmp_seq=7 ttl=64 time=3.21 ms')
    assert not is_reply_line('no answer yet for icmp_seq=8')
    assert not is_reply_line('ping: sendmsg: Network is unreachable')
    assert not is_reply_line('PING 192.168.1.119 (192.168.1.119) 56(84) bytes of data.')


def test_every_event_that_needs_a_beep_has_a_distinct_one():
    assert set(BEEPS) == {LOST, REGAINED, GIVE_UP}
    assert len({tuple(p) for p in BEEPS.values()}) == 3
    tones = {name: sum(1 for freq, _ in pattern if freq) for name, pattern in BEEPS.items()}
    assert tones == {LOST: 2, REGAINED: 1, GIVE_UP: 3}


def test_beep_samples_fit_16_bits_and_start_and_end_silent():
    samples = beep_samples(BEEPS[LOST])
    assert max(abs(s) for s in samples) <= 32767
    assert max(abs(s) for s in samples) > 10000        # audible, not near-silent
    assert samples[0] == 0 and abs(samples[-1]) < 500


def test_beep_wav_is_a_playable_file(tmp_path):
    path = write_beep_wav(tmp_path / 'lost.wav', BEEPS[LOST])
    with wave.open(str(path)) as wav:
        assert wav.getnchannels() == 1 and wav.getsampwidth() == 2
        assert wav.getframerate() == 44100
        assert wav.getnframes() / wav.getframerate() == pytest.approx(0.05 + 0.34, abs=0.01)

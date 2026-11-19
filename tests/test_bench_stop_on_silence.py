# Copyright 2026 Mike
# SPDX-License-Identifier: Apache-2.0
"""The pass/fail arithmetic of tools/bench_stop_on_silence.py (pyserial is imported
inside main(), so this runs in stage-1-quality)."""
import pytest

from tools.bench_stop_on_silence import STOP_MARGIN_S, time_to_stop, verdict


def _samples(stop_at, until=6.0, speed=0.1, hz=20):
    """Wheels turning until `stop_at` seconds (None = never stop)."""
    out = []
    for i in range(int(until * hz)):
        t = i / hz
        moving = stop_at is None or t < stop_at
        out.append((t, speed if moving else 0, speed if moving else 0))
    return out


def test_time_to_stop_measures_from_the_start_of_silence():
    assert time_to_stop(_samples(stop_at=2.4), silence_start=2.0) == pytest.approx(0.4)


def test_time_to_stop_is_none_when_the_wheels_never_stop():
    # 2026-11-18 on the floor: last command "spin", then nothing, wheels turning for minutes.
    assert time_to_stop(_samples(stop_at=None), silence_start=2.0) is None


def test_time_to_stop_ignores_a_zero_reading_that_did_not_hold():
    samples = _samples(stop_at=None)
    samples[50] = (samples[50][0], 0, 0)          # one zero sample at t=2.5, then moving again
    assert time_to_stop(samples, silence_start=2.0) is None


def test_time_to_stop_is_none_without_any_sample_after_silence_began():
    assert time_to_stop(_samples(stop_at=1.0, until=1.5), silence_start=2.0) is None


def test_verdict_passes_a_stop_within_timeout_plus_margin():
    passed, why = verdict(0.55, timeout_ms=500)
    assert passed and '0.55 s' in why


def test_verdict_fails_a_stop_that_only_the_3_s_default_could_explain():
    passed, why = verdict(3.1, timeout_ms=500)
    assert not passed and 'later than' in why
    assert verdict(0.5 + STOP_MARGIN_S + 0.01, timeout_ms=500)[0] is False


def test_verdict_fails_when_the_wheels_never_stopped():
    passed, why = verdict(None, timeout_ms=500)
    assert not passed and 'STILL TURNING' in why

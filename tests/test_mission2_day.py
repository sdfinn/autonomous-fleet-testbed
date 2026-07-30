# Copyright 2026 Mike
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for tools/mission2_day.py's pure logic (S17 review CR-22): the day
orchestrator is THE stage-4 gate, and its output parsing + retreat detection were
previously untested.

Rewritten for S17 Piece 9 (2026-07-24/25): the old per-scenario `run(ball_xy, color)`
executor interface (and its ExecResult/`_parse_checklist` log-scraping) is gone,
replaced by `run_day() -> list[dict]` — one call returns all 3 legs'
t_start/t_end/ok/checklist/photos/reaction_events at once (the shape
MissionRunner.run_mission2_day() produces). JetsonExecutor's persistent-container
machinery (Piece 8) is also gone: with one `run_day()` call there is only ONE docker
invocation/day either way now, so container-mode HIL goes back to a plain
`docker run --rm` for the single call, not `docker exec` into a long-lived container."""
import json
import subprocess
import threading

import pytest

import re

import tools.mission2_day as mission2_day_module
from tools.mission2_day import (GroundTruthLog, InProcessExecutor, JetsonExecutor,
                                 MissionExecutor, OutboundDetector, RetreatDetector,
                                 hil_variant_names, run_day, sweep_orphans)


def _leg(t_start=0.0, t_end=1.0, ok=True, checklist=None, photos=None, reaction_events=None):
    """One MissionRunner.run_mission2_day()-shaped leg dict — matches the real field
    names/types exactly (checklist rows are JSON lists, not tuples, since they cross a
    json.dumps/json.loads boundary on the Jetson path)."""
    return {
        't_start': t_start, 't_end': t_end, 'ok': ok,
        'checklist': checklist if checklist is not None else [['step', 'PASS']],
        'photos': photos if photos is not None else [],
        'reaction_events': reaction_events if reaction_events is not None else [],
    }


def test_retreat_detector_fires_only_after_drop_from_peak():
    det = RetreatDetector(drop_m=0.4)
    assert det.update(None) is False              # no sample yet
    assert det.update((0.0, 1.0)) is False        # outbound, rising y
    assert det.update((0.0, 3.0)) is False        # still rising (peak 3.0)
    assert det.update((0.0, 2.8)) is False        # dipped 0.2 — below threshold
    assert det.update((0.0, 3.5)) is False        # new peak
    assert det.update((0.0, 3.2)) is False        # 0.3 below new peak — not yet
    assert det.update((0.0, 3.05)) is True        # 0.45 below peak — retreating


def test_outbound_detector_fires_only_after_climb_from_trough():
    """Mirror of test_retreat_detector_fires_only_after_drop_from_peak (same style,
    inverted): does NOT fire while still falling/flat, DOES fire once risen enough
    above the trough seen so far."""
    det = OutboundDetector(climb_m=0.4)
    assert det.update(None) is False              # no sample yet
    assert det.update((0.0, 4.0)) is False        # first sample, trough=4.0
    assert det.update((0.0, 2.0)) is False        # falling, new trough=2.0
    assert det.update((0.0, 2.2)) is False        # risen 0.2 — below threshold
    assert det.update((0.0, 1.5)) is False        # new trough
    assert det.update((0.0, 1.8)) is False        # 0.3 above new trough — not yet
    assert det.update((0.0, 1.95)) is True        # 0.45 above trough — heading out


def test_run_ball_choreography_second_wait_requires_a_real_outbound_climb_first(monkeypatch):
    """Reproduces the live 2026-07-24 bug: run_ball_choreography()'s two back-to-back
    RetreatDetector waits share no memory of each other. A synthetic ground-truth
    sequence covers leg 1's own outbound+return (should trigger the FIRST retreat,
    placing yellow), a pause at home, then leg 2's own SEPARATE outbound+return
    (should trigger the SECOND retreat, swapping to red) — but pre-fix, the second
    wait's fresh detector gets fooled by the tail of leg 1's own still-in-progress
    return (still falling right after the first retreat fires) and swaps to red
    while 'leg1_return' is still the active label, well before leg 2 even starts."""
    sequence = []

    def add(label, ys):
        for y in ys:
            sequence.append((label, (0.0, y)))

    add('leg1_outbound', [0.0, 1.0, 2.0, 3.0, 4.0])
    add('leg1_return', [3.5, 3.0, 2.5, 2.0])
    add('home_pause', [2.0, 2.0])
    add('leg2_outbound', [2.2, 2.6, 3.0, 3.5, 4.0])
    add('leg2_return', [3.5, 3.0, 2.5, 2.0])

    state = {'i': 0, 'last_label': None}
    stop_evt = threading.Event()

    def fake_get_xy():
        i = state['i']
        if i >= len(sequence):
            stop_evt.set()
            return None
        label, xy = sequence[i]
        state['i'] += 1
        state['last_label'] = label
        return xy

    class FakeBallOps:
        concurrent = True

        def __init__(self):
            self.place_labels = []
            self.remove_labels = []

        def place(self, color, x, y):
            self.place_labels.append((color, state['last_label']))
            return f'{color}_ball'

        def remove(self, name):
            self.remove_labels.append(state['last_label'])

        def settle(self):
            pass

    monkeypatch.setattr(mission2_day_module, 'get_ground_truth_xy', fake_get_xy)
    monkeypatch.setattr(mission2_day_module.time, 'sleep', lambda s: None)

    ball_ops = FakeBallOps()
    truth_log = mission2_day_module.run_ball_choreography(
        ball_ops, (1.2, 3.9), stop_evt, poll_s=0.0)

    assert ball_ops.place_labels[0] == ('yellow', 'leg1_return')     # first retreat: unaffected
    assert ball_ops.remove_labels[0] == 'leg2_return'                # THE bug: pre-fix this is
                                                                      # 'leg1_return' — the swap
                                                                      # fires during leg 1's own
                                                                      # still-in-progress return.
    assert ball_ops.place_labels[1] == ('red', 'leg2_return')
    # continuous logging through every phase, including the new outbound-wait gap
    assert len(truth_log._samples) == len(sequence)


def test_ground_truth_log_nearest_returns_closest_sample():
    log = mission2_day_module.GroundTruthLog()
    log.record(10.0, (1.0, 2.0))
    log.record(10.5, (1.5, 2.5))
    log.record(11.0, (2.0, 3.0))
    assert log.nearest(10.4) == (1.5, 2.5)
    assert log.nearest(10.0) == (1.0, 2.0)
    assert log.nearest(100.0) == (2.0, 3.0)   # clamps to the last sample, doesn't crash


def test_ground_truth_log_nearest_empty_returns_none():
    log = mission2_day_module.GroundTruthLog()
    assert log.nearest(10.0) is None


def test_ground_truth_log_closest_approach_between_finds_local_minimum():
    """For reaction-point recovery: the closest approach to a KNOWN target xy,
    restricted to a time window (one leg's own approach, not a different leg's)."""
    log = mission2_day_module.GroundTruthLog()
    log.record(0.0, (0.0, 0.0))
    log.record(1.0, (0.0, 3.0))    # closest to (0, 4) in this window
    log.record(2.0, (0.0, 1.0))
    log.record(10.0, (0.0, 3.9))   # a LATER, closer sample outside the window — must
                                    # not be picked for a query scoped to t in [0, 2]
    assert log.closest_approach_to((0.0, 4.0), t_start=0.0, t_end=2.0) == (0.0, 3.0)


# ── MissionExecutor / InProcessExecutor ─────────────────────────────────────────────────────
def test_mission_executor_close_is_a_noop_by_default():
    MissionExecutor().close()   # must not raise


def test_in_process_executor_run_day_delegates_to_runner():
    calls = []

    class FakeRunner:
        def run_mission2_day(self):
            calls.append('called')
            return [_leg(), _leg(), _leg()]

    ex = InProcessExecutor(FakeRunner())
    legs = ex.run_day()
    assert calls == ['called']
    assert len(legs) == 3


# ── JetsonExecutor construction (image preflight — unaffected by the Piece 9 rewrite) ───────
def test_jetson_executor_bare_metal_skips_image_preflight(monkeypatch):
    """HIL_CONTAINER unset (bare-metal, the default) must never touch docker/SSH."""
    monkeypatch.delenv('HIL_CONTAINER', raising=False)

    def _boom(*a, **k):
        raise AssertionError('subprocess.run must not be called in bare-metal mode')
    monkeypatch.setattr(subprocess, 'run', _boom)

    ex = JetsonExecutor('10.42.0.217', '/tmp/hil_stage')
    assert ex.image is None


def test_jetson_executor_container_mode_passes_when_image_present(monkeypatch):
    monkeypatch.setenv('HIL_CONTAINER', '1')
    monkeypatch.setenv('HIL_IMAGE', 'ghcr.io/sdfinn/autonomous-fleet-testbed:deadbeef')
    monkeypatch.setattr(
        subprocess, 'run',
        lambda *a, **k: subprocess.CompletedProcess(a, returncode=0, stdout='', stderr=''))

    ex = JetsonExecutor('10.42.0.217', '/tmp/hil_stage')
    assert ex.image == 'ghcr.io/sdfinn/autonomous-fleet-testbed:deadbeef'


def test_jetson_executor_container_mode_fails_loud_when_image_missing(monkeypatch):
    monkeypatch.setenv('HIL_CONTAINER', '1')
    monkeypatch.setenv('HIL_IMAGE', 'ghcr.io/sdfinn/autonomous-fleet-testbed:wrongtag')
    monkeypatch.setattr(
        subprocess, 'run',
        lambda *a, **k: subprocess.CompletedProcess(
            a, returncode=1, stdout='', stderr='no such image'))

    with pytest.raises(RuntimeError, match='wrongtag'):
        JetsonExecutor('10.42.0.217', '/tmp/hil_stage')


def test_jetson_executor_construction_never_starts_a_container(monkeypatch):
    """Decision 1 (S17 Piece 9 rewrite): the persistent-container machinery (Piece 8's
    `_start_container`/`HIL_CONTAINER_NAME`) is gone — construction in container mode
    must do ONLY the image preflight check, never a `docker run`."""
    monkeypatch.setenv('HIL_CONTAINER', '1')
    monkeypatch.setenv('HIL_IMAGE', 'ghcr.io/sdfinn/autonomous-fleet-testbed:deadbeef')
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, returncode=0, stdout='', stderr='')

    monkeypatch.setattr(subprocess, 'run', fake_run)
    mission2_day_module.JetsonExecutor('10.42.0.217', '/tmp/hil_stage')

    assert not any('docker run' in c[-1] for c in calls if c and c[0] == 'ssh')
    assert not hasattr(mission2_day_module, 'HIL_CONTAINER_NAME')


def test_close_is_a_noop_in_both_modes(monkeypatch):
    """close() is the base MissionExecutor no-op in every mode now — JetsonExecutor no
    longer overrides it (there is no long-lived container left to tear down)."""
    monkeypatch.setenv('HIL_CONTAINER', '1')
    monkeypatch.setenv('HIL_IMAGE', 'ghcr.io/sdfinn/autonomous-fleet-testbed:deadbeef')
    monkeypatch.setattr(
        subprocess, 'run',
        lambda *a, **k: subprocess.CompletedProcess(a, returncode=0, stdout='', stderr=''))
    ex = JetsonExecutor('10.42.0.217', '/tmp/hil_stage')

    def _boom(*a, **k):
        raise AssertionError('close() must not touch docker/SSH — it is a pure no-op now')
    monkeypatch.setattr(subprocess, 'run', _boom)
    ex.close()   # must not raise
    assert 'close' not in JetsonExecutor.__dict__   # confirms no override was reintroduced


# ── JetsonExecutor.run_day() ─────────────────────────────────────────────────────────────────
def _day_result_stdout(legs):
    return 'MISSION2_DAY_RESULT:' + json.dumps(legs) + '\n'


def test_run_day_bare_metal_dispatches_ssh_with_day_flag(monkeypatch, tmp_path):
    monkeypatch.delenv('HIL_CONTAINER', raising=False)
    legs = [_leg(), _leg(), _leg()]
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        if cmd[0] == 'timeout':
            return subprocess.CompletedProcess(cmd, returncode=0,
                                                stdout=_day_result_stdout(legs), stderr='')
        return subprocess.CompletedProcess(cmd, returncode=0, stdout='', stderr='')

    monkeypatch.setattr(subprocess, 'run', fake_run)
    monkeypatch.setattr(mission2_day_module.JetsonExecutor, '_pull_photos_from_paths',
                        lambda self, paths: list(paths))
    ex = JetsonExecutor('10.42.0.217', str(tmp_path))

    result = ex.run_day()

    ssh_cmd = next(c for c in calls if 'ssh' in c)
    assert 'python3 -m nav_fleet.mission_runner --day' in ssh_cmd[-1]
    assert 'docker' not in ssh_cmd[-1]
    assert result == legs


def test_run_day_container_mode_uses_plain_docker_run_rm(monkeypatch, tmp_path):
    """Decision 1: with ONE `run_day()` call for the whole day, container mode goes
    back to a plain one-shot `docker run --rm` — no persistent container/`docker exec`
    left to amortize a per-scenario cost against."""
    monkeypatch.setenv('HIL_CONTAINER', '1')
    monkeypatch.setenv('HIL_IMAGE', 'ghcr.io/sdfinn/autonomous-fleet-testbed:deadbeef')
    legs = [_leg(), _leg(), _leg()]
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        if cmd[0] == 'timeout':
            return subprocess.CompletedProcess(cmd, returncode=0,
                                                stdout=_day_result_stdout(legs), stderr='')
        return subprocess.CompletedProcess(cmd, returncode=0, stdout='', stderr='')

    monkeypatch.setattr(subprocess, 'run', fake_run)
    monkeypatch.setattr(mission2_day_module.JetsonExecutor, '_pull_photos_from_paths',
                        lambda self, paths: list(paths))
    ex = JetsonExecutor('10.42.0.217', str(tmp_path))

    ex.run_day()

    ssh_cmd = next(c for c in calls if 'ssh' in c and 'timeout' in c)
    assert 'docker run --rm' in ssh_cmd[-1]
    assert '--name hil_mission2' in ssh_cmd[-1]
    assert 'docker exec' not in ssh_cmd[-1]
    assert 'python3 -m nav_fleet.mission_runner --day' in ssh_cmd[-1]
    assert 'ghcr.io/sdfinn/autonomous-fleet-testbed:deadbeef' in ssh_cmd[-1]


def test_run_day_pulls_photos_per_leg_and_failure_bags(monkeypatch, tmp_path):
    monkeypatch.delenv('HIL_CONTAINER', raising=False)
    legs = [_leg(photos=['/home/mike/fleet-ci-data/photos/a.png']),
            _leg(photos=['/home/mike/fleet-ci-data/photos/b.png']),
            _leg(photos=[])]
    pulled = []

    def fake_run(cmd, **kwargs):
        if cmd[0] == 'timeout':
            return subprocess.CompletedProcess(cmd, returncode=0,
                                                stdout=_day_result_stdout(legs), stderr='')
        return subprocess.CompletedProcess(cmd, returncode=0, stdout='', stderr='')

    def fake_pull(self, paths):
        pulled.append(list(paths))
        return [f'local/{p.rsplit("/", 1)[-1]}' for p in paths]

    monkeypatch.setattr(subprocess, 'run', fake_run)
    monkeypatch.setattr(mission2_day_module.JetsonExecutor, '_pull_photos_from_paths', fake_pull)
    ex = JetsonExecutor('10.42.0.217', str(tmp_path))

    result = ex.run_day()

    assert pulled == [['/home/mike/fleet-ci-data/photos/a.png'],
                       ['/home/mike/fleet-ci-data/photos/b.png'], []]
    assert result[0]['photos'] == ['local/a.png']
    assert result[1]['photos'] == ['local/b.png']
    assert result[2]['photos'] == []


def test_run_day_raises_when_no_result_line_found(monkeypatch, tmp_path):
    monkeypatch.delenv('HIL_CONTAINER', raising=False)

    def fake_run(cmd, **kwargs):
        return subprocess.CompletedProcess(
            cmd, returncode=1,
            stdout='', stderr='Traceback ...\nModuleNotFoundError\n')

    monkeypatch.setattr(subprocess, 'run', fake_run)
    ex = JetsonExecutor('10.42.0.217', str(tmp_path))

    with pytest.raises(RuntimeError, match='no MISSION2_DAY_RESULT'):
        ex.run_day()


def test_parse_day_result_recovers_the_json_line():
    legs = [_leg(), _leg(), _leg()]
    ex = JetsonExecutor.__new__(JetsonExecutor)   # bypass __init__ — pure parsing test
    log_text = 'some noise\n' + _day_result_stdout(legs) + 'trailer\n'
    assert ex._parse_day_result(log_text) == legs


def test_parse_day_result_raises_when_missing():
    ex = JetsonExecutor.__new__(JetsonExecutor)
    with pytest.raises(RuntimeError, match='no MISSION2_DAY_RESULT'):
        ex._parse_day_result('no result line here\n')


# ── Photo path translation (2026-07-22 regression + container fix, now list-driven) ─────────
def test_pull_photos_bare_metal_uses_absolute_path_verbatim(monkeypatch, tmp_path):
    """Bare-metal mission_runner runs directly as JETSON_USER, so the logged absolute
    path already IS the real host path — no translation needed."""
    monkeypatch.delenv('HIL_CONTAINER', raising=False)
    monkeypatch.setattr(mission2_day_module, 'PHOTO_DIR', tmp_path)
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, returncode=0, stdout='', stderr='')

    monkeypatch.setattr(subprocess, 'run', fake_run)
    ex = JetsonExecutor('10.42.0.217', '/tmp/hil_stage')
    ex._pull_photos_from_paths(['/home/mike/fleet-ci-data/photos/mission2_home_ref_1.png'])
    scp_cmd = next(c for c in calls if c[0] == 'scp')
    assert scp_cmd[-2] == (
        'mike@10.42.0.217:/home/mike/fleet-ci-data/photos/mission2_home_ref_1.png')


def test_pull_photos_container_mode_translates_root_prefix_to_tilde(monkeypatch, tmp_path):
    """Container mode: mission_runner's absolute path is INSIDE the container (root's
    HOME, per the image's missing USER directive), mapped to JETSON_USER's real home via
    the container-run bind mount — the scp path must be JETSON_USER's home, not root's."""
    monkeypatch.setenv('HIL_CONTAINER', '1')
    monkeypatch.setenv('HIL_IMAGE', 'ghcr.io/sdfinn/autonomous-fleet-testbed:deadbeef')
    monkeypatch.setattr(mission2_day_module, 'PHOTO_DIR', tmp_path)
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, returncode=0, stdout='', stderr='')

    monkeypatch.setattr(subprocess, 'run', fake_run)
    ex = JetsonExecutor('10.42.0.217', '/tmp/hil_stage')
    ex._pull_photos_from_paths(['/root/fleet-ci-data/photos/mission2_home_ref_1.png'])
    scp_cmd = next(c for c in calls if c[0] == 'scp')
    assert scp_cmd[-2] == (
        'mike@10.42.0.217:~/fleet-ci-data/photos/mission2_home_ref_1.png')


def test_pull_photos_from_paths_empty_list_makes_no_scp_call(monkeypatch, tmp_path):
    monkeypatch.delenv('HIL_CONTAINER', raising=False)
    monkeypatch.setattr(mission2_day_module, 'PHOTO_DIR', tmp_path)

    def _boom(*a, **k):
        raise AssertionError('scp must not be called with no photo paths')
    monkeypatch.setattr(subprocess, 'run', _boom)

    ex = JetsonExecutor('10.42.0.217', '/tmp/hil_stage')
    assert ex._pull_photos_from_paths([]) == []


# ── Failure-bag scp (unaffected by the Piece 9 rewrite — still a log-text regex scrape) ─────
def test_pull_failure_bags_scps_the_directory_recursively(monkeypatch, tmp_path):
    """S17 Piece 3: a 'failure bag kept: <path>' log line must scp -r the whole bag
    directory back — a single-file scp (the photo pattern) would silently miss the
    .mcap files inside it."""
    monkeypatch.delenv('HIL_CONTAINER', raising=False)
    monkeypatch.setattr(mission2_day_module, 'FAILURE_BAG_DIR', tmp_path)
    captured = {}

    def fake_run(cmd, **kwargs):
        captured['cmd'] = cmd
        return subprocess.CompletedProcess(cmd, returncode=0, stdout='', stderr='')

    monkeypatch.setattr(subprocess, 'run', fake_run)
    ex = JetsonExecutor('10.42.0.217', '/tmp/hil_stage')
    log_text = 'failure bag kept: reports/failure_bags/mission2_20260721_010203\n'
    ex._pull_failure_bags(log_text)
    assert captured['cmd'][:2] == ['scp', '-r']
    assert captured['cmd'][-2] == (
        'mike@10.42.0.217:autonomous-fleet-testbed/'
        'reports/failure_bags/mission2_20260721_010203')
    assert captured['cmd'][-1] == str(tmp_path / 'mission2_20260721_010203')


def test_pull_failure_bags_no_bag_line_makes_no_scp_call(monkeypatch, tmp_path):
    monkeypatch.delenv('HIL_CONTAINER', raising=False)
    monkeypatch.setattr(mission2_day_module, 'FAILURE_BAG_DIR', tmp_path)

    def _boom(*a, **k):
        raise AssertionError('scp must not be called when no bag was kept')
    monkeypatch.setattr(subprocess, 'run', _boom)

    ex = JetsonExecutor('10.42.0.217', '/tmp/hil_stage')
    ex._pull_failure_bags('mission2: PASS, no failure bag here\n')


# ── Startup-crash synthesis (unaffected — same method, same signature) ──────────────────────
def test_no_startup_crash_row_on_clean_exit(monkeypatch):
    """mrc == 0 (script completed normally, whatever the mission result) — never
    synthesize a row; mission_runner.py's own _log_mission already handled it."""
    monkeypatch.delenv('HIL_CONTAINER', raising=False)
    captured = []
    monkeypatch.setattr(mission2_day_module, 'log_run', lambda **kw: captured.append(kw))
    ex = JetsonExecutor('10.42.0.217', '/tmp/hil_stage')
    ex._log_startup_crash_if_needed('Mission mission2: FAIL\n', mrc=0)
    assert captured == []


def test_no_startup_crash_row_when_completion_line_present(monkeypatch):
    """mrc != 0 CAN happen on a normal, handled FAIL (main() does `raise
    SystemExit(0 if ok else 1)`) — the completion print line is the real signal that
    _log_mission already ran, not the exit code alone."""
    monkeypatch.delenv('HIL_CONTAINER', raising=False)
    captured = []
    monkeypatch.setattr(mission2_day_module, 'log_run', lambda **kw: captured.append(kw))
    ex = JetsonExecutor('10.42.0.217', '/tmp/hil_stage')
    ex._log_startup_crash_if_needed('...\nMission mission2: FAIL\n', mrc=1)
    assert captured == []


def test_startup_crash_row_logged_when_process_died_before_completion_line(monkeypatch):
    """mrc != 0 AND no completion line — the process died before _log_mission ever
    ran (e.g. an import-time crash). Synthesize the FAIL row ourselves so the
    workstation DB has SOME record instead of the attempt being invisible."""
    monkeypatch.delenv('HIL_CONTAINER', raising=False)
    captured = []
    monkeypatch.setattr(mission2_day_module, 'log_run', lambda **kw: captured.append(kw))
    ex = JetsonExecutor('10.42.0.217', '/tmp/hil_stage')
    ex._log_startup_crash_if_needed(
        'Traceback (most recent call last):\nModuleNotFoundError: ...\n', mrc=1)
    assert len(captured) == 1
    row = captured[0]
    assert row['scenario'] == 'mission2'
    assert row['result'] == 'FAIL'
    assert row['failure_reason'] == 'startup_crash'
    assert row['runner_type'] == 'hil_jetson'
    assert row['sim_engine'] == 'real'


def test_hil_variant_names_matches_the_declared_pipeline_matrix():
    """Piece 6: run_day's summary loop must iterate the SAME variant names declared in
    config/pipeline_matrix.yaml's hil.scenarios (minus the 'mission2_' prefix), not a
    separately hardcoded tuple that could silently drift out of sync with it."""
    assert hil_variant_names() == ['no_ball', 'yellow', 'red']


def test_sweep_orphans_never_matches_the_gui_viewer_only_process(monkeypatch):
    """Piece 7 (found during a live timed GUI run, 2026-07-22): sweep_orphans() used to
    pkill a bare 'gz sim' pattern, which matches BOTH the headless server ('gz sim -s -r
    world.sdf') AND the separate GUI viewer ('gz sim -g') — killing an observer's viewer
    within seconds of every mission2_day run starting, since launch_stack() sweeps before
    it launches. None of the patterns swept may match a viewer-only cmdline; at least one
    must still match the real server cmdline."""
    patterns = []
    monkeypatch.setattr(
        mission2_day_module.subprocess, 'run',
        lambda cmd, **kw: patterns.append(cmd[cmd.index('-f') + 1]))

    sweep_orphans()

    viewer_cmdline = 'gz sim -g'
    server_cmdline = 'gz sim -s -r /home/mike/autonomous-fleet-testbed/worlds/bedroom_simple.sdf'
    assert not any(re.search(p, viewer_cmdline) for p in patterns)
    assert any(re.search(p, server_cmdline) for p in patterns)


# ── _judge_and_log_leg (S17 Piece 9: the new per-leg judge, replacing run_no_ball/
#    run_yellow/run_red's inline judging) ────────────────────────────────────────────────────
def test_judge_and_log_leg_fills_truth_xy_only_when_missing(monkeypatch):
    gt_log = GroundTruthLog()
    gt_log.record(0.0, (0.0, 0.0))
    gt_log.record(5.0, (1.2, 3.9))   # closest approach to the ball inside [0, 10]
    gt_log.record(10.0, (0.0, 0.5))

    leg = _leg(t_start=0.0, t_end=10.0,
               reaction_events=[{'color': 'yellow', 'reaction': 'photo_then_home',
                                 't': 10.0, 'truth_xy': None},
                                {'color': 'red', 'reaction': 'photo_then_stop',
                                 't': 10.0, 'truth_xy': (9.0, 9.0)}])   # already filled

    captured = {}
    monkeypatch.setattr(
        mission2_day_module, 'judge_yellow',
        lambda ball_xy, events, photos, truth_start, final, sim=None: captured.update(
            events=events) or [])
    monkeypatch.setattr(mission2_day_module, 'log_variant_row', lambda *a, **k: None)

    mission2_day_module._judge_and_log_leg('yellow', leg, (1.2, 3.9), gt_log)

    yellow_event = captured['events'][0]
    red_event = captured['events'][1]
    assert yellow_event['truth_xy'] == (1.2, 3.9)   # filled from the gt_log
    assert red_event['truth_xy'] == (9.0, 9.0)      # left untouched — was already set


@pytest.mark.parametrize('name,judge_name', [
    ('no_ball', 'judge_no_ball'), ('yellow', 'judge_yellow'), ('red', 'judge_red')])
def test_judge_and_log_leg_routes_to_the_right_judge(monkeypatch, name, judge_name):
    gt_log = GroundTruthLog()
    gt_log.record(0.0, (0.0, 0.0))
    gt_log.record(1.0, (0.0, 1.0))
    leg = _leg(t_start=0.0, t_end=1.0)

    called = []
    for fn_name in ('judge_no_ball', 'judge_yellow', 'judge_red'):
        def _make(fn_name):
            def _fn(*a, **k):
                called.append(fn_name)
                return []
            return _fn
        monkeypatch.setattr(mission2_day_module, fn_name, _make(fn_name))
    logged = []
    monkeypatch.setattr(mission2_day_module, 'log_variant_row',
                        lambda variant, seed, ok, runner=None, home_photo_similarity=None:
                        logged.append((variant, ok)))

    ok = mission2_day_module._judge_and_log_leg(name, leg, (1.2, 3.9), gt_log)

    assert called == [judge_name]
    assert ok is True
    assert logged == [(name, True)]


def test_judge_and_log_leg_ok_false_when_judge_reports_fails(monkeypatch):
    gt_log = GroundTruthLog()
    leg = _leg()
    monkeypatch.setattr(mission2_day_module, 'judge_no_ball',
                        lambda *a, **k: ['some failure'])
    logged = []
    monkeypatch.setattr(mission2_day_module, 'log_variant_row',
                        lambda variant, seed, ok, runner=None, home_photo_similarity=None:
                        logged.append(ok))

    ok = mission2_day_module._judge_and_log_leg('no_ball', leg, (1.2, 3.9), gt_log)

    assert ok is False
    assert logged == [False]


# ── run_day() (top-level orchestration) ──────────────────────────────────────────────────────
class _FakeBallOps:
    def __init__(self, concurrent):
        self.concurrent = concurrent


def _fake_log_only(stop_evt, poll_s=0.3):
    """Fast stand-in for run_ground_truth_log_only, used by every run_day() test below
    that isn't specifically exercising Fix 1's operator-mode wiring — avoids each of
    these tests picking up a real ~2.5s wait (Fix 5) plus real subprocess/gz polling."""
    stop_evt.wait(timeout=5)
    return GroundTruthLog()


def test_run_day_operator_mode_never_starts_the_choreography_thread(monkeypatch):
    """Decision 2: OperatorBallOps.concurrent is False, so run_day() must never call
    run_ball_choreography (and therefore never call any ball_ops.place()/.remove()) —
    only the BALL ACTIONS are gated on concurrent. Ground-truth LOGGING is a separate,
    always-on concern (Fix 1, see test_run_day_operator_mode_populates_ground_truth_log
    below) — this test stubs run_ground_truth_log_only to keep it fast/deterministic."""
    def _boom(*a, **k):
        raise AssertionError('run_ball_choreography must not run in operator mode')
    monkeypatch.setattr(mission2_day_module, 'run_ball_choreography', _boom)
    monkeypatch.setattr(mission2_day_module, 'run_ground_truth_log_only', _fake_log_only)
    monkeypatch.setattr(mission2_day_module, '_judge_and_log_leg', lambda *a, **k: True)
    monkeypatch.setattr(mission2_day_module.time, 'sleep', lambda s: None)

    class FakeExecutor:
        def run_day(self):
            return [_leg(), _leg(), _leg()]

    ok = run_day(FakeExecutor(), _FakeBallOps(concurrent=False), (1.2, 3.9), hold_s=0)
    assert ok is True


def test_run_day_operator_mode_populates_ground_truth_log(monkeypatch):
    """Fix 1 (S17 review, 2026-07-25): operator mode (ball_ops.concurrent == False,
    the real-robot day) must still end up with a NON-EMPTY GroundTruthLog fed to
    judging — pre-fix, run_day() started NO background thread at all in this mode
    (the only thing that ever populated a GroundTruthLog was the ball-choreography
    thread, which is concurrent-only), so every judge_* call saw "no ground truth"
    and FAILed unconditionally, even on a mission that ran fine."""
    gt_log = GroundTruthLog()
    gt_log.record(1.0, (2.0, 3.0))

    def fake_log_only(stop_evt, poll_s=0.3):
        stop_evt.wait(timeout=5)
        return gt_log

    def _boom(*a, **k):
        raise AssertionError('run_ball_choreography (and its ball_ops actions) must '
                              'not run in operator mode')

    monkeypatch.setattr(mission2_day_module, 'run_ground_truth_log_only', fake_log_only)
    monkeypatch.setattr(mission2_day_module, 'run_ball_choreography', _boom)
    monkeypatch.setattr(mission2_day_module.time, 'sleep', lambda s: None)

    captured = {}

    def fake_judge(name, leg, ball_xy, gtl):
        captured[name] = gtl
        return True
    monkeypatch.setattr(mission2_day_module, '_judge_and_log_leg', fake_judge)

    class FakeExecutor:
        def run_day(self):
            return [_leg(), _leg(), _leg()]

    ok = run_day(FakeExecutor(), _FakeBallOps(concurrent=False), (1.2, 3.9), hold_s=0)

    assert ok is True
    assert captured['no_ball'] is gt_log
    assert len(gt_log._samples) == 1   # non-empty — the actual regression this fixes


def test_run_ground_truth_log_only_records_until_stop_evt_set(monkeypatch):
    """Unit test for the new function itself, called directly (no thread) — records
    every non-None sample and stops as soon as stop_evt is set."""
    stop_evt = threading.Event()
    calls = {'i': 0}

    def fake_get_xy():
        calls['i'] += 1
        if calls['i'] >= 3:
            stop_evt.set()
        return (float(calls['i']), float(calls['i']))

    monkeypatch.setattr(mission2_day_module, 'get_ground_truth_xy', fake_get_xy)
    monkeypatch.setattr(mission2_day_module.time, 'sleep', lambda s: None)

    log = mission2_day_module.run_ground_truth_log_only(stop_evt, poll_s=0.0)

    assert len(log._samples) == 3


def test_run_day_gz_mode_starts_and_joins_the_choreography_thread(monkeypatch):
    started = []

    def fake_choreography(ball_ops, ball_xy, stop_evt, poll_s=0.3):
        started.append(True)
        stop_evt.wait(timeout=5)
        return GroundTruthLog()

    monkeypatch.setattr(mission2_day_module, 'run_ball_choreography', fake_choreography)
    monkeypatch.setattr(mission2_day_module, '_judge_and_log_leg', lambda *a, **k: True)
    monkeypatch.setattr(mission2_day_module.time, 'sleep', lambda s: None)

    class FakeExecutor:
        def run_day(self):
            return [_leg(), _leg(), _leg()]

    ok = run_day(FakeExecutor(), _FakeBallOps(concurrent=True), (1.2, 3.9), hold_s=0)
    assert started == [True]
    assert ok is True


def test_run_day_judges_all_three_legs_in_declared_order(monkeypatch):
    judged_names = []
    monkeypatch.setattr(mission2_day_module, '_judge_and_log_leg',
                        lambda name, leg, ball_xy, gt_log: judged_names.append(name) or True)
    monkeypatch.setattr(mission2_day_module, 'run_ground_truth_log_only', _fake_log_only)
    monkeypatch.setattr(mission2_day_module.time, 'sleep', lambda s: None)

    class FakeExecutor:
        def run_day(self):
            return [_leg(), _leg(), _leg()]

    run_day(FakeExecutor(), _FakeBallOps(concurrent=False), (1.2, 3.9), hold_s=0)
    assert judged_names == ['no_ball', 'yellow', 'red']


def test_run_day_returns_false_if_any_leg_fails(monkeypatch):
    results = iter([True, False, True])
    monkeypatch.setattr(mission2_day_module, '_judge_and_log_leg',
                        lambda *a, **k: next(results))
    monkeypatch.setattr(mission2_day_module, 'run_ground_truth_log_only', _fake_log_only)
    monkeypatch.setattr(mission2_day_module.time, 'sleep', lambda s: None)

    class FakeExecutor:
        def run_day(self):
            return [_leg(), _leg(), _leg()]

    ok = run_day(FakeExecutor(), _FakeBallOps(concurrent=False), (1.2, 3.9), hold_s=0)
    assert ok is False


def test_run_day_waits_before_stopping_the_gt_thread(monkeypatch):
    """Fix 5 (S17 review, 2026-07-25): the finally block must give the ground-truth
    thread ~2.5 real seconds to keep sampling past the day's nominal end BEFORE
    signalling stop — otherwise (as found live on the x86 in-process executor) the
    stationary check's t_end and t_end+2.0 samples clamp to the identical last sample
    and can never fail, a vacuous check rather than a real one. Verified here by
    checked via source inspection rather than by racing two real threads around a
    monkeypatched threading.Event — Python's own Thread machinery uses an Event
    internally too (`Thread._started`), so subclassing/patching threading.Event
    globally spuriously records ITS .set() call as well, which is exactly what a
    first attempt at this test hit (Thread._bootstrap_inner()'s `self._started.set()`
    firing before run_day()'s own real time.sleep(2.5)/stop_evt.set() pair ever
    runs — a false failure, not a real one). Source inspection sidesteps that
    entirely: it directly verifies the actual code shape, not a racy proxy for it."""
    import inspect
    src = inspect.getsource(mission2_day_module.run_day)
    finally_src = src[src.index('finally:'):]
    assert finally_src.count('time.sleep(2.5)') == 1        # once per run_day() call
    sleep_idx = finally_src.index('time.sleep(2.5)')
    stop_idx = finally_src.index('stop_evt.set()')
    assert sleep_idx < stop_idx                              # sleep happens BEFORE stop_evt.set()


def test_maybe_spawn_vlm_canary_spawns_detached_process_on_red_reaction(monkeypatch):
    captured = {}

    def fake_popen(cmd, **kwargs):
        captured['cmd'] = cmd
        captured['kwargs'] = kwargs
        return None
    monkeypatch.setattr(mission2_day_module.subprocess, 'Popen', fake_popen)

    leg = _leg(photos=['/tmp/red_reaction_red_20260730_120000.png'],
               reaction_events=[{'color': 'red', 'reaction': 'photo_then_stop',
                                 'truth_xy': None}])
    mission2_day_module._maybe_spawn_vlm_canary('red', leg)

    assert captured['cmd'][:3] == [mission2_day_module.sys.executable, '-m', 'tools.vlm_canary']
    assert captured['cmd'][3] == '/tmp/red_reaction_red_20260730_120000.png'
    assert captured['cmd'][4] == 'red'
    assert captured['kwargs']['start_new_session'] is True


def test_maybe_spawn_vlm_canary_does_nothing_without_a_red_reaction(monkeypatch):
    def _boom(cmd, **kwargs):
        raise AssertionError('must not spawn when there was no red reaction')
    monkeypatch.setattr(mission2_day_module.subprocess, 'Popen', _boom)

    leg = _leg(photos=['/tmp/mission2_marker_20260730_120000.png'], reaction_events=[])
    mission2_day_module._maybe_spawn_vlm_canary('no_ball', leg)  # must not raise


def test_maybe_spawn_vlm_canary_ignores_yellow_reactions(monkeypatch):
    def _boom(cmd, **kwargs):
        raise AssertionError('must not spawn for a yellow-only reaction')
    monkeypatch.setattr(mission2_day_module.subprocess, 'Popen', _boom)

    leg = _leg(photos=['/tmp/yellow_reaction_yellow_20260730_120000.png'],
               reaction_events=[{'color': 'yellow', 'reaction': 'photo_then_home',
                                 'truth_xy': None}])
    mission2_day_module._maybe_spawn_vlm_canary('yellow', leg)  # must not raise


def test_maybe_spawn_vlm_canary_logs_warning_on_spawn_failure_without_raising(monkeypatch):
    def _boom(cmd, **kwargs):
        raise OSError('no such file or directory')
    monkeypatch.setattr(mission2_day_module.subprocess, 'Popen', _boom)

    leg = _leg(photos=['/tmp/red_reaction_red_20260730_120000.png'],
               reaction_events=[{'color': 'red', 'reaction': 'photo_then_stop',
                                 'truth_xy': None}])
    mission2_day_module._maybe_spawn_vlm_canary('red', leg)  # must not raise


def test_run_day_calls_maybe_spawn_vlm_canary_once_per_leg(monkeypatch):
    """Integration check: run_day() itself wires the hook in, for every leg —
    doesn't assert on judging/telemetry, which the existing run_day tests already
    cover; monkeypatches _judge_and_log_leg exactly like
    test_run_day_operator_mode_never_starts_the_choreography_thread does."""
    calls = []
    monkeypatch.setattr(mission2_day_module, '_judge_and_log_leg', lambda *a, **k: True)
    monkeypatch.setattr(mission2_day_module, '_maybe_spawn_vlm_canary',
                        lambda name, leg: calls.append(name))
    monkeypatch.setattr(mission2_day_module.time, 'sleep', lambda s: None)

    class FakeExecutor:
        def run_day(self):
            return [_leg(), _leg(), _leg()]

    ok = run_day(FakeExecutor(), _FakeBallOps(concurrent=False), (1.2, 3.9), hold_s=0)
    assert ok is True
    assert calls == ['no_ball', 'yellow', 'red']

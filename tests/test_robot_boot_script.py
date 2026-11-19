# Copyright 2026 Mike
# SPDX-License-Identifier: Apache-2.0
"""Behavioural tests for scripts/robot_boot.sh — the real robot's mission entry point.

Runs the REAL script against fake `git`, `docker` and `ros2` commands, so the things
that matter on the robot are proven without one:

* a bag recording starts on every run and is finalized (SIGINT) on every exit path;
* Ctrl+C / SIGTERM actually stops the mission. The fake `docker run` IGNORES SIGINT
  and SIGTERM on purpose: that is what the real container does (its PID 1 is a plain
  bash script with no signal handler — found live 2026-11-16, session notes item 2),
  so a test with a well-behaved fake would pass vacuously.

No ROS 2 needed (stage-1 safe): the script's ROS setup file is overridden through
ROBOT_BOOT_ROS_SETUP, and the fake workspace overlay puts the stubs on PATH.
"""
import os
import shutil
import signal
import stat
import subprocess
import time
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / 'scripts' / 'robot_boot.sh'

FAKE_GIT = """#!/bin/bash
echo deadbeefdeadbeefdeadbeefdeadbeefdeadbeef
"""

# `docker run` ignores SIGINT/SIGTERM like the real container; only `docker rm -f`
# (SIGKILL) ends it — unless FAKE_MISSION_SECONDS is set, when it ends by itself.
FAKE_DOCKER = """#!/bin/bash
case "$1" in
  image) exit 0 ;;
  rm)
    echo "docker_rm" >> "$EVENTS"
    if [ -f "$STATE/docker_run.pid" ]; then
      kill -KILL "$(cat "$STATE/docker_run.pid")" 2>/dev/null
      rm -f "$STATE/docker_run.pid"
    fi
    exit 0 ;;
  run)
    trap '' INT TERM
    echo $$ > "$STATE/docker_run.pid"
    echo "docker_run $*" >> "$EVENTS"
    echo "fake mission output"
    if [ -n "${FAKE_MISSION_SECONDS:-}" ]; then
      sleep "$FAKE_MISSION_SECONDS"
      rm -f "$STATE/docker_run.pid"
      echo "docker_run_finished" >> "$EVENTS"
      exit "${FAKE_MISSION_RC:-0}"
    fi
    while true; do sleep 0.2; done ;;
esac
"""

# `colcon build`: records the call and creates a launcher for every node named in
# FAKE_COLCON_BUILDS (space separated), like a real build of a newer setup.py would.
FAKE_COLCON = """#!/bin/bash
echo "colcon $*" >> "$EVENTS"
for n in ${FAKE_COLCON_BUILDS:-}; do
  printf '#!/bin/bash\n' > "$HOME/autonomous-fleet-testbed/install/nav_fleet/lib/nav_fleet/$n"
  chmod +x "$HOME/autonomous-fleet-testbed/install/nav_fleet/lib/nav_fleet/$n"
done
exit "${FAKE_COLCON_RC:-0}"
"""

FAKE_ROS2 = """#!/bin/bash
case "$1" in
  launch)
    trap 'echo drivers_sigint >> "$EVENTS"; exit 0' INT
    echo "drivers_start" >> "$EVENTS"
    echo "esp32_driver up"
    echo "ldlidar communication is normal"
    echo "Camera with MXID 123 opened"
    echo "camera_relay up"
    # FAKE_BATTERY_LINE: what esp32_driver logs about the pack ("none" = nothing).
    if [ "${FAKE_BATTERY_LINE:-}" != "none" ]; then
      line="${FAKE_BATTERY_LINE:-esp32_driver: battery 11.82 V (ok)}"
      echo "[esp32_driver-2] [INFO] [1.0] [esp32_driver]: $line"
    fi
    while true; do sleep 0.2; done ;;
  bag)
    echo "bag_start $*" >> "$EVENTS"
    [ -n "${FAKE_BAG_DIES:-}" ] && exit 1
    out=""
    while [ $# -gt 0 ]; do
      [ "$1" = "-o" ] && out="$2"
      shift
    done
    trap 'echo bag_sigint >> "$EVENTS"; touch "$out/metadata.yaml"; exit 0' INT
    mkdir -p "$out"
    while true; do sleep 0.2; done ;;
esac
"""


def _write_exec(path, text):
    path.write_text(text)
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


@pytest.fixture
def boot_env(tmp_path):
    """A fake $HOME holding a fake checkout, plus stub commands on PATH."""
    home = tmp_path / 'home'
    repo = home / 'autonomous-fleet-testbed'
    stubs = tmp_path / 'stubs'
    state = tmp_path / 'state'
    for d in (repo / 'install', repo / 'scripts', stubs, state):
        d.mkdir(parents=True)
    (repo / 'install' / 'setup.bash').write_text('')
    (repo / 'scripts' / 'regen_cyclonedds_config.sh').write_text('exit 0\n')
    # The real launcher check, against a fake package with one node already built.
    shutil.copy(SCRIPT.parent / 'ensure_nav_fleet_built.sh', repo / 'scripts')
    (repo / 'src' / 'nav_fleet').mkdir(parents=True)
    (repo / 'src' / 'nav_fleet' / 'setup.py').write_text(
        "entry_points={'console_scripts': ['esp32_driver = nav_fleet.esp32_driver:main']}\n")
    (repo / 'install' / 'nav_fleet' / 'lib' / 'nav_fleet').mkdir(parents=True)
    _write_exec(repo / 'install' / 'nav_fleet' / 'lib' / 'nav_fleet' / 'esp32_driver', '')
    _write_exec(stubs / 'colcon', FAKE_COLCON)
    ros_setup = tmp_path / 'ros_setup.bash'
    ros_setup.write_text('')
    _write_exec(stubs / 'git', FAKE_GIT)
    _write_exec(stubs / 'docker', FAKE_DOCKER)
    _write_exec(stubs / 'ros2', FAKE_ROS2)
    events = state / 'events.log'
    events.write_text('')
    env = {
        'HOME': str(home),
        'PATH': f"{stubs}:{os.environ['PATH']}",
        'EVENTS': str(events),
        'STATE': str(state),
        'ROBOT_BOOT_ROS_SETUP': str(ros_setup),
    }
    return env, events, home


def _events(events):
    return [line.split()[0] for line in events.read_text().splitlines() if line.strip()]


def _wait_for_event(events, name, timeout=20.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if name in _events(events):
            return
        time.sleep(0.1)
    raise AssertionError(f"'{name}' never happened; events: {_events(events)}")


def _start(env):
    # Own session = own process group, so the test can signal the group exactly the
    # way a terminal's Ctrl+C does (to every process in the foreground group).
    return subprocess.Popen(
        ['bash', str(SCRIPT)], env=env, stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        start_new_session=True)


def _finish(proc, timeout=40.0):
    try:
        out, _ = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        os.killpg(proc.pid, signal.SIGKILL)
        out, _ = proc.communicate()
        raise AssertionError(f'robot_boot.sh did not exit within {timeout}s:\n{out}')
    return out


@pytest.mark.parametrize('sig, expected_rc', [
    (signal.SIGINT, 130),    # Ctrl+C in the terminal
    (signal.SIGTERM, 143),   # systemctl stop robot-mission.service
    (signal.SIGHUP, 129),    # the SSH session / terminal went away
])
def test_signal_stops_the_mission_and_finalizes_the_bag(boot_env, sig, expected_rc):
    env, events, _home = boot_env
    proc = _start(env)
    _wait_for_event(events, 'docker_run')

    os.killpg(proc.pid, sig)
    out = _finish(proc, timeout=20.0)

    ev = _events(events)
    assert proc.returncode == expected_rc, out
    # The mission container is force-removed AFTER it started (the script's own
    # stale-container `docker rm -f` before `docker run` does not count).
    assert 'docker_rm' in ev[ev.index('docker_run'):], out
    assert 'docker_run_finished' not in ev
    # Order: stop the brain first, then finalize the evidence, then the drivers
    # (so the bag still sees the wheels stop).
    stop_order = [e for e in ev[ev.index('docker_run'):]
                  if e in ('docker_rm', 'bag_sigint', 'drivers_sigint')]
    assert stop_order == ['docker_rm', 'bag_sigint', 'drivers_sigint'], out


def test_bag_starts_before_the_drivers_and_is_finalized_on_a_normal_run(boot_env):
    env, events, home = boot_env
    env['FAKE_MISSION_SECONDS'] = '1'
    proc = _start(env)
    out = _finish(proc)

    ev = _events(events)
    assert proc.returncode == 0, out
    assert ev.index('bag_start') < ev.index('drivers_start') < ev.index('docker_run')
    assert ev.index('docker_run_finished') < ev.index('bag_sigint') < ev.index('drivers_sigint')
    bags = [p for p in (home / 'fleet-ci-data' / 'robot_boot_logs').glob('bag_*')
            if p.is_dir()]
    assert len(bags) == 1 and (bags[0] / 'metadata.yaml').exists(), out
    # The mission's own output still reaches the terminal and the log file.
    assert 'fake mission output' in out
    logs = list((home / 'fleet-ci-data' / 'robot_boot_logs').glob('robot_boot_*.log'))
    assert len(logs) == 1 and 'fake mission output' in logs[0].read_text()


def test_bag_recorder_arguments(boot_env):
    env, events, _home = boot_env
    env['FAKE_MISSION_SECONDS'] = '1'
    _finish(_start(env))

    bag_line = next(line for line in events.read_text().splitlines()
                    if line.startswith('bag_start'))
    assert ' record ' in bag_line and '--all-topics' in bag_line
    # Raw camera frames are megabytes each; the theora streams are kept instead.
    assert '--exclude-regex .*/image_(raw|rect)' in bag_line
    # A second node called rosbag2_recorder would also answer the failure-bag
    # snapshot service that nav_fleet.failure_bag calls inside the container.
    assert '--node-name robot_boot_recorder' in bag_line


def test_mission_failure_exit_code_is_passed_through(boot_env):
    env, events, _home = boot_env
    env['FAKE_MISSION_SECONDS'] = '1'
    env['FAKE_MISSION_RC'] = '3'
    proc = _start(env)
    out = _finish(proc)

    assert proc.returncode == 3, out
    assert 'bag_sigint' in _events(events)


def test_no_mission_without_a_running_bag_recorder(boot_env):
    env, events, _home = boot_env
    env['FAKE_BAG_DIES'] = '1'
    proc = _start(env)
    out = _finish(proc)

    ev = _events(events)
    assert proc.returncode != 0
    assert 'bag recorder' in out
    assert 'docker_run' not in ev and 'drivers_start' not in ev


def test_no_bag_opt_out_still_runs_the_mission(boot_env):
    env, events, _home = boot_env
    env['FAKE_MISSION_SECONDS'] = '1'
    env['ROBOT_BOOT_NO_BAG'] = '1'
    proc = _start(env)
    out = _finish(proc)

    ev = _events(events)
    assert proc.returncode == 0, out
    assert 'bag_start' not in ev and 'docker_run_finished' in ev


def _docker_run_line(events):
    return next(line for line in events.read_text().splitlines()
                if line.startswith('docker_run '))


def test_real_map_is_mounted_and_selected_when_present(boot_env):
    """The robot's own map is kept out of git (a floor plan of a real home) in
    ~/fleet-ci-data/maps; when it is there the container must use it."""
    env, events, home = boot_env
    maps = home / 'fleet-ci-data' / 'maps'
    maps.mkdir(parents=True)
    (maps / 'bedroom_real.yaml').write_text('image: bedroom_real.pgm\n')
    (maps / 'bedroom_real.pgm').write_bytes(b'P5 1 1 255 \x00')
    env['FAKE_MISSION_SECONDS'] = '1'
    out = _finish(_start(env))

    line = _docker_run_line(events)
    assert '-e NAV2_MAP_FILE=bedroom_real.yaml' in line
    assert 'NAV2_MAP_FILE=living_room.yaml' not in line
    for ext in ('yaml', 'pgm'):
        assert (f'-v {maps}/bedroom_real.{ext}:'
                f'/ros2_ws/src/nav_fleet/maps/bedroom_real.{ext}:ro') in line
    assert "the robot's own map" in out
    assert 'WARNING' not in out


@pytest.mark.parametrize('present', [(), ('bedroom_real.yaml',), ('bedroom_real.pgm',)])
def test_borrowed_map_fallback_is_loud_when_the_real_map_is_missing_or_incomplete(
        boot_env, present):
    env, events, home = boot_env
    maps = home / 'fleet-ci-data' / 'maps'
    maps.mkdir(parents=True)
    for name in present:
        (maps / name).write_text('x')
    env['FAKE_MISSION_SECONDS'] = '1'
    out = _finish(_start(env))

    line = _docker_run_line(events)
    assert '-e NAV2_MAP_FILE=living_room.yaml' in line
    assert 'bedroom_real' not in line            # half a map must never be mounted
    assert 'WARNING: no real map' in out


def _add_new_node_to_setup_py(home):
    setup_py = home / 'autonomous-fleet-testbed' / 'src' / 'nav_fleet' / 'setup.py'
    setup_py.write_text(
        "entry_points={'console_scripts': ['esp32_driver = nav_fleet.esp32_driver:main',\n"
        "    'slip_monitor = nav_fleet.slip_monitor:main']}\n")


def test_no_rebuild_when_every_node_already_has_a_launcher(boot_env):
    env, events, _home = boot_env
    env['FAKE_MISSION_SECONDS'] = '1'
    _finish(_start(env))
    assert 'colcon' not in _events(events)


def test_a_node_added_since_the_last_build_triggers_a_rebuild_before_the_drivers(boot_env):
    """2026-11-18: the Jetson's install/ dated from August and sync no longer builds;
    a new node in drivers_only_launch.py would have killed the driver layer."""
    env, events, home = boot_env
    _add_new_node_to_setup_py(home)
    env['FAKE_COLCON_BUILDS'] = 'slip_monitor'
    env['FAKE_MISSION_SECONDS'] = '1'
    out = _finish(_start(env))

    lines = events.read_text().splitlines()
    build = next(i for i, line in enumerate(lines) if line.startswith('colcon '))
    assert 'build --symlink-install --packages-select nav_fleet' in lines[build]
    assert build < _events(events).index('drivers_start')
    assert 'no launcher for: slip_monitor' in out
    assert 'docker_run' in _events(events)           # and the mission still runs


@pytest.mark.parametrize('colcon_env', [
    {'FAKE_COLCON_RC': '1'},                         # the build itself fails
    {},                                              # build "succeeds", launcher still absent
])
def test_no_mission_when_the_rebuild_does_not_produce_the_launcher(boot_env, colcon_env):
    env, events, home = boot_env
    _add_new_node_to_setup_py(home)
    env.update(colcon_env)
    env['FAKE_MISSION_SECONDS'] = '1'
    proc = _start(env)
    out = _finish(proc)
    assert proc.returncode == 1
    assert 'FATAL' in out
    assert 'drivers_start' not in _events(events)
    assert 'docker_run' not in _events(events)


def test_healthy_battery_is_reported_and_the_mission_runs(boot_env):
    env, events, _home = boot_env
    env['FAKE_MISSION_SECONDS'] = '1'
    out = _finish(_start(env))
    assert 'battery 11.82 V (ok)' in out
    assert 'docker_run' in _events(events)


@pytest.mark.parametrize('line', [
    'esp32_driver: battery 10.31 V (low) -- charge before the next mission',
    'esp32_driver: battery 9.17 V (critical) -- motion REFUSED until the pack is charged',
    'none',                                   # no reading at all: fail closed
])
def test_no_mission_on_a_low_critical_or_unknown_battery(boot_env, line):
    """2026-11-17 and 2026-11-18 both ended on a flat pack; the second time the
    Jetson lost power mid-spin and the robot could not be stopped."""
    env, events, _home = boot_env
    env['FAKE_BATTERY_LINE'] = line
    env['FAKE_MISSION_SECONDS'] = '1'
    proc = _start(env)
    out = _finish(proc, timeout=60.0)
    assert proc.returncode == 1
    assert 'FATAL: battery is not OK' in out
    assert 'docker_run' not in _events(events)
    assert 'drivers_sigint' in _events(events)       # and the drivers were shut down


def test_battery_check_can_be_overridden_for_bench_work(boot_env):
    env, events, _home = boot_env
    env['FAKE_BATTERY_LINE'] = 'esp32_driver: battery 10.31 V (low)'
    env['ROBOT_BOOT_IGNORE_BATTERY'] = '1'
    env['FAKE_MISSION_SECONDS'] = '1'
    out = _finish(_start(env))
    assert 'ROBOT_BOOT_IGNORE_BATTERY set' in out
    assert 'docker_run' in _events(events)

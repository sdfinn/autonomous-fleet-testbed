# Copyright 2026 Mike
# SPDX-License-Identifier: Apache-2.0
"""Pull a robot's most recent ROS2 log directory back to the workstation (S17 Piece 3).

The gap this closes: NavRunner/MissionRunner already log rich per-step detail via ROS's
own `self.get_logger()` (goal timeouts/retries/rejections, step narrative, reactions —
see CLAUDE.md), and it already persists to `~/.ros/log/<session>/` on whichever host ran
the mission. But nothing ever retrieves it, and there is NO automatic retention: this
workstation alone has 2,800+ session directories (2.2 GB, oldest from 2026-06-28) sitting
untouched. `rcl` already maintains a `latest` symlink to the most recent session, so this
tool needs no dir-scanning logic of its own — just resolve the symlink and copy it over.

Usage (repo root):
    python -m tools.pull_ros_logs                        # from JETSON_USER@JETSON_IP
    python -m tools.pull_ros_logs --host mike@jetson.local
    python -m tools.pull_ros_logs --host ''               # local ~/.ros/log/latest, no ssh
"""
import argparse
import os
import pathlib
import subprocess

DEST_DIR = 'reports/ros_logs'


def _default_host():
    """JETSON_USER@JETSON_IP (same env vars as scripts/hil_stage.sh), or None (local) if
    JETSON_IP isn't set — mirrors that script's convention rather than inventing a new one."""
    ip = os.environ.get('JETSON_IP')
    if not ip:
        return None
    user = os.environ.get('JETSON_USER', 'mike')
    return f'{user}@{ip}'


def resolve_latest_session(host):
    """Return the concrete (symlink-resolved) ~/.ros/log session directory path on `host`
    (None = localhost, no ssh)."""
    target = 'readlink -f ~/.ros/log/latest'
    cmd = (['ssh', '-o', 'BatchMode=yes', host, target] if host is not None
           else ['readlink', '-f', os.path.expanduser('~/.ros/log/latest')])
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
    if result.returncode != 0:
        raise RuntimeError(f'could not resolve latest ROS log session on '
                           f'{host or "localhost"}: {result.stderr.strip()}')
    return result.stdout.strip()


def pull_latest(host, dest_dir=DEST_DIR):
    """Copy (scp, or cp for local) the resolved session directory into dest_dir. Returns
    the resulting local path."""
    session_path = resolve_latest_session(host)
    dest_dir = pathlib.Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    local_path = dest_dir / pathlib.PurePosixPath(session_path).name
    if host is None:
        cmd = ['cp', '-r', session_path, str(local_path)]
    else:
        cmd = ['scp', '-r', '-o', 'BatchMode=yes', f'{host}:{session_path}', str(local_path)]
    subprocess.run(cmd, check=True)
    return local_path


def main():
    parser = argparse.ArgumentParser(
        description="Pull a robot's most recent ROS2 log directory to the workstation.")
    parser.add_argument('--host', default=None,
                        help="user@host to ssh to (default: JETSON_USER@JETSON_IP env "
                             "vars; pass an empty string to pull from localhost instead)")
    parser.add_argument('--dest', default=DEST_DIR)
    args = parser.parse_args()
    host = _default_host() if args.host is None else (args.host or None)
    local_path = pull_latest(host, dest_dir=args.dest)
    print(f'pulled to {local_path}')


if __name__ == '__main__':
    main()

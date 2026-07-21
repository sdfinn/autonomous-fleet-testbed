# Copyright 2026 Mike
# SPDX-License-Identifier: Apache-2.0
"""Shared logging setup for tools/ and nav_fleet/ modules (S17 Piece 3).

FLEET_LOG_LEVEL (env, default INFO) sets console verbosity on the workstation AND the
robot — the same env-var-driven pattern as POWER_MODE_ID/HIL_CONTAINER/FLEET_DB. The
optional file handler always captures DEBUG+ regardless of the console level, so a
file log is generous for post-mortem forensics even on a quiet console.

Usage: call configure() once near process start (mission_runner.main(), mission2_day's
main(), etc.); every module then calls get_logger(__name__) and logs normally — child
loggers propagate up to the 'fleet' root, which owns the handlers.
"""
import logging
import os
import subprocess

ROOT_NAME = 'fleet'
_FORMAT = '%(asctime)s [%(levelname)s] [%(name)s] %(message)s'
_DATEFMT = '%Y-%m-%d %H:%M:%S'
_LEVELS = {
    'DEBUG': logging.DEBUG,
    'INFO': logging.INFO,
    'WARNING': logging.WARNING,
    'ERROR': logging.ERROR,
    'CRITICAL': logging.CRITICAL,
}


def resolve_level(env=None):
    """FLEET_LOG_LEVEL -> a logging level int. Unset or unrecognized -> INFO."""
    env = os.environ if env is None else env
    name = env.get('FLEET_LOG_LEVEL', 'INFO').upper()
    return _LEVELS.get(name, logging.INFO)


def get_logger(name):
    """Namespaced per-module logger — propagates to the 'fleet' root's handlers.

    propagate is forced True defensively: ROS2's `launch` package calls
    `logging.setLoggerClass(LaunchLogger)` as an import side effect (fires even when
    pytest.ini disables the launch-testing plugin's HOOKS — the module still gets
    imported during plugin discovery), and LaunchLogger defaults propagate=False.
    Without this, every new logger created in this process after `launch` has been
    imported silently never reaches its parent's handlers — found via a test that
    passed standalone but failed under pytest."""
    logger = logging.getLogger(f'{ROOT_NAME}.{name}')
    logger.propagate = True
    return logger


def configure(log_file=None, env=None):
    """One-time setup of the 'fleet' root logger. Idempotent: repeat calls replace
    handlers rather than accumulating them (the classic duplicate-log-lines bug)."""
    logger = logging.getLogger(ROOT_NAME)
    logger.setLevel(logging.DEBUG)   # permissive at the logger; handlers do the filtering
    logger.propagate = False
    logger.handlers.clear()

    formatter = logging.Formatter(_FORMAT, datefmt=_DATEFMT)

    stream = logging.StreamHandler()
    stream.setLevel(resolve_level(env))
    stream.setFormatter(formatter)
    logger.addHandler(stream)

    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(logging.DEBUG)   # file always gets everything
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger


def build_env_manifest(**fields):
    """Format arbitrary environment/config fields as one manifest line, so a run's
    context (git sha, power mode, runner type, ...) is captured alongside its events —
    the caller decides what fields matter and how to obtain them. None values are
    skipped (e.g. an optional field like hil_image that's only set in container mode)."""
    parts = [f'{k}={v}' for k, v in fields.items() if v is not None]
    return 'env: ' + ' '.join(parts) if parts else 'env: (no fields provided)'


def git_sha(env=None, default='unknown'):
    """Best-effort short git sha for the environment manifest — never raises. Prefers
    GITHUB_SHA (authoritative in CI, avoids a subprocess call); falls back to `git
    rev-parse` for local/manual runs; returns `default` if neither is available (e.g.
    inside a container image with no .git)."""
    env = os.environ if env is None else env
    sha = env.get('GITHUB_SHA')
    if sha:
        return sha[:12]
    try:
        result = subprocess.run(
            ['git', 'rev-parse', '--short', 'HEAD'],
            capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            return result.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        pass
    return default

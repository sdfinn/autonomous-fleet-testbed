# Copyright 2026 Mike
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for tools/log_setup.py (S17 Piece 3): shared logging setup consumed by
tools/ and nav_fleet/ modules — the FLEET_LOG_LEVEL debug switch, the bracketed-tag
formatter, and the always-DEBUG file handler for post-mortem forensics."""
import logging
import re
import subprocess

import pytest

from tools.log_setup import build_env_manifest, configure, get_logger, git_sha, resolve_level


@pytest.fixture(autouse=True)
def _clean_fleet_logger():
    logger = logging.getLogger('fleet')
    logger.handlers.clear()
    yield
    logger.handlers.clear()


def test_resolve_level_defaults_to_info_when_unset():
    assert resolve_level(env={}) == logging.INFO


def test_resolve_level_reads_debug_from_env():
    assert resolve_level(env={'FLEET_LOG_LEVEL': 'DEBUG'}) == logging.DEBUG


def test_resolve_level_is_case_insensitive():
    assert resolve_level(env={'FLEET_LOG_LEVEL': 'debug'}) == logging.DEBUG


def test_resolve_level_falls_back_to_info_on_garbage():
    assert resolve_level(env={'FLEET_LOG_LEVEL': 'NOTALEVEL'}) == logging.INFO


def test_get_logger_returns_namespaced_logger():
    logger = get_logger('mission2_day')
    assert logger.name == 'fleet.mission2_day'


def test_get_logger_forces_propagation_true():
    """Regression: ROS2's `launch` package sets a global logger class whose default
    is propagate=False (see tools/log_setup.py docstring) — without forcing this,
    child loggers silently never reach the 'fleet' root's handlers under pytest."""
    assert get_logger('y').propagate is True


def test_configure_sets_console_level_from_env_default():
    configure(env={})
    stream_handlers = [
        h for h in logging.getLogger('fleet').handlers
        if isinstance(h, logging.StreamHandler) and not isinstance(h, logging.FileHandler)]
    assert len(stream_handlers) == 1
    assert stream_handlers[0].level == logging.INFO


def test_configure_respects_env_debug():
    configure(env={'FLEET_LOG_LEVEL': 'DEBUG'})
    stream_handlers = [
        h for h in logging.getLogger('fleet').handlers
        if isinstance(h, logging.StreamHandler) and not isinstance(h, logging.FileHandler)]
    assert stream_handlers[0].level == logging.DEBUG


def test_configure_stream_uses_bracketed_format(capsys):
    configure(env={})
    get_logger('x').info('hello world')
    captured = capsys.readouterr()
    assert re.search(r'\[INFO\] \[fleet\.x\] hello world', captured.err) \
        or re.search(r'\[INFO\] \[fleet\.x\] hello world', captured.out)


def test_configure_with_log_file_writes_to_file(tmp_path):
    log_file = tmp_path / 'test.log'
    configure(log_file=str(log_file), env={})
    get_logger('x').info('hello file')
    content = log_file.read_text()
    assert '[INFO] [fleet.x] hello file' in content


def test_file_handler_captures_debug_even_when_console_is_info(tmp_path):
    log_file = tmp_path / 'test.log'
    configure(log_file=str(log_file), env={})  # default INFO console
    file_handlers = [
        h for h in logging.getLogger('fleet').handlers if isinstance(h, logging.FileHandler)]
    assert len(file_handlers) == 1
    assert file_handlers[0].level == logging.DEBUG


def test_configure_is_idempotent():
    configure(env={})
    configure(env={})
    assert len(logging.getLogger('fleet').handlers) == 1


def test_build_env_manifest_formats_key_value_pairs():
    assert (build_env_manifest(runner_type='local', power_mode='25W')
            == 'env: runner_type=local power_mode=25W')


def test_build_env_manifest_skips_none_values():
    assert build_env_manifest(runner_type='local', hil_image=None) == 'env: runner_type=local'


def test_build_env_manifest_empty_when_no_fields():
    assert build_env_manifest() == 'env: (no fields provided)'


def test_git_sha_prefers_github_sha_env_truncated():
    assert git_sha(env={'GITHUB_SHA': 'a' * 40}) == 'a' * 12


def test_git_sha_falls_back_to_subprocess(monkeypatch):
    def fake_run(*a, **k):
        return subprocess.CompletedProcess(a, returncode=0, stdout='deadbee\n', stderr='')
    monkeypatch.setattr(subprocess, 'run', fake_run)
    assert git_sha(env={}) == 'deadbee'


def test_git_sha_returns_default_when_git_unavailable(monkeypatch):
    def fake_run(*a, **k):
        raise FileNotFoundError('git not found')
    monkeypatch.setattr(subprocess, 'run', fake_run)
    assert git_sha(env={}, default='unknown') == 'unknown'

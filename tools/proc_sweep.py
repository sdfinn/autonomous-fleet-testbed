# Copyright 2026 Mike
# SPDX-License-Identifier: Apache-2.0
"""Kill leftover simulator / Nav2 processes by name, but only this project's own.

Why this exists (2026-11-22): this workstation also runs the sister project (wayfarer),
whose Nav2 and EKF processes carry the same names as ours (`component_container_isolated`,
`ekf_node`, `robot_state_publisher`, ...). A plain `pkill -9 -f <name>` in our CI sweep
killed theirs too. The two projects run on different ROS domains (this repo: 0, wayfarer:
42), and every process keeps the environment it was started with in
`/proc/<pid>/environ`, so the domain tells the two apart:

    a process is OURS when its start-up environment has ROS_DOMAIN_ID equal to our
    domain, or has no ROS_DOMAIN_ID at all while our domain is 0 (unset means 0 to ROS).

Anything else that matches a pattern is left alone and reported. A process whose
environment cannot be read (another user's) is also left alone.

This process and its parents (the shell or CI step whose own command line contains the
pattern) are never matched, which removes the `pkill -f` self-match trap.

Use from the repo root, standard library only (CI calls it before any venv exists):

    python3 -m tools.proc_sweep "parameter_bridge|ekf_node" "gz sim"     # SIGKILL
    python3 -m tools.proc_sweep --signal TERM "gz sim"
    python3 -m tools.proc_sweep --list "component_container"             # report only

Exit status is always 0 when the arguments are valid: a sweep is best-effort clean-up.
"""
import argparse
import os
import re
import signal
import sys
from collections import namedtuple

DOMAIN_VAR = 'ROS_DOMAIN_ID'
DEFAULT_DOMAIN = '0'          # what ROS uses when the variable is not set
UNREADABLE = object()         # marker: the process's environment could not be read

Proc = namedtuple('Proc', 'pid cmdline domain')   # domain: str, None (unset) or UNREADABLE
Found = namedtuple('Found', 'ours others')        # two lists of Proc


def own_domain(env=None):
    """The ROS domain this process runs on, as a string ('0' when unset or empty)."""
    value = (os.environ if env is None else env).get(DOMAIN_VAR, '').strip()
    return value or DEFAULT_DOMAIN


def _read_bytes(path):
    """File contents; None if the process is gone; UNREADABLE if we may not read it."""
    try:
        with open(path, 'rb') as handle:
            return handle.read()
    except PermissionError:
        return UNREADABLE
    except OSError:               # the process exited between listing and reading
        return None


def _domain_of(environ_bytes):
    """ROS_DOMAIN_ID from a /proc/<pid>/environ blob: its value, or None when not set."""
    if environ_bytes is UNREADABLE:
        return UNREADABLE
    prefix = (DOMAIN_VAR + '=').encode()
    for entry in (environ_bytes or b'').split(b'\0'):
        if entry.startswith(prefix):
            return entry[len(prefix):].decode(errors='replace').strip() or None
    return None


def _parent_of(pid, proc_root):
    status = _read_bytes(os.path.join(proc_root, str(pid), 'status'))
    if status is None or status is UNREADABLE:
        return None
    for line in status.decode(errors='replace').splitlines():
        if line.startswith('PPid:'):
            return int(line.split()[1])
    return None


def self_and_ancestors(pid=None, proc_root='/proc'):
    """This process and every parent above it: never candidates for a sweep."""
    seen = set()
    pid = os.getpid() if pid is None else pid
    while pid and pid not in seen:
        seen.add(pid)
        pid = _parent_of(pid, proc_root)
    return seen


def running_processes(proc_root='/proc'):
    """Every process with a command line, as Proc(pid, cmdline, domain)."""
    for name in sorted(os.listdir(proc_root), key=lambda n: (len(n), n)):
        if not name.isdigit():
            continue
        raw = _read_bytes(os.path.join(proc_root, name, 'cmdline'))
        if not raw or raw is UNREADABLE:      # gone, unreadable, or a kernel thread
            continue
        cmdline = raw.replace(b'\0', b' ').decode(errors='replace').strip()
        environ = _read_bytes(os.path.join(proc_root, name, 'environ'))
        if environ is None:                   # exited while we were looking
            continue
        yield Proc(int(name), cmdline, _domain_of(environ))


def is_ours(proc, domain):
    """True when `proc` was started on `domain` (see the module text for the rule)."""
    if proc.domain is UNREADABLE:
        return False
    if proc.domain is None:
        return domain == DEFAULT_DOMAIN
    return proc.domain == domain


def find(patterns, domain=None, proc_root='/proc', skip=None):
    """Processes whose command line matches any pattern (regular expressions, searched
    anywhere in the line, like `pgrep -f`), split into ours and others."""
    domain = own_domain() if domain is None else str(domain)
    skip = self_and_ancestors(proc_root=proc_root) if skip is None else set(skip)
    regexes = [re.compile(p) for p in patterns]
    found = Found([], [])
    for proc in running_processes(proc_root):
        if proc.pid in skip or not any(r.search(proc.cmdline) for r in regexes):
            continue
        (found.ours if is_ours(proc, domain) else found.others).append(proc)
    return found


def sweep(patterns, sig=signal.SIGKILL, domain=None, proc_root='/proc', skip=None,
          kill=os.kill):
    """Send `sig` to every matching process of our own domain. Returns Found: `ours` are
    the processes signalled, `others` the matches that were left alone."""
    found = find(patterns, domain=domain, proc_root=proc_root, skip=skip)
    for proc in found.ours:
        try:
            kill(proc.pid, sig)
        except (ProcessLookupError, PermissionError):
            pass                              # already gone, or not ours to signal
    return found


def describe(proc):
    if proc.domain is UNREADABLE:
        where = 'environment not readable'
    elif proc.domain is None:
        where = 'no %s' % DOMAIN_VAR
    else:
        where = '%s=%s' % (DOMAIN_VAR, proc.domain)
    return 'pid %d (%s): %s' % (proc.pid, where, proc.cmdline[:120])


def main(argv=None, proc_root='/proc', skip=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('patterns', nargs='+', help='regular expressions, as for pgrep -f')
    parser.add_argument('--signal', default='KILL', help='KILL (default), TERM or INT')
    parser.add_argument('--list', action='store_true', help='report matches, signal nothing')
    parser.add_argument('--domain', default=None,
                        help='domain to treat as ours (default: %s, else 0)' % DOMAIN_VAR)
    args = parser.parse_args(argv)
    try:
        sig = getattr(signal, 'SIG' + args.signal.upper().removeprefix('SIG'))
    except AttributeError:
        parser.error('unknown signal %r' % args.signal)
    domain = own_domain() if args.domain is None else args.domain
    if args.list:
        found = find(args.patterns, domain=domain, proc_root=proc_root, skip=skip)
        verb = 'found'
    else:
        found = sweep(args.patterns, sig=sig, domain=domain, proc_root=proc_root, skip=skip)
        verb = 'sent SIG%s to' % sig.name[3:]
    for proc in found.ours:
        print('[sweep] %s %s' % (verb, describe(proc)))
    for proc in found.others:
        print('[sweep] left alone, not on domain %s: %s' % (domain, describe(proc)))
    if not found.ours and not found.others:
        print('[sweep] nothing matches %s' % ' | '.join(args.patterns))
    return 0


if __name__ == '__main__':
    sys.exit(main())

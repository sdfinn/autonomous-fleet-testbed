# Copyright 2026 Mike
# SPDX-License-Identifier: Apache-2.0
"""On-device VLM canary (2026-07-30 design spec): a fully decoupled, log-only
classification of Mission 2's existing red-ball reaction photo by a small local
vision-language model. No pass/fail, no mission/navigation impact — see
docs/superpowers/specs/2026-07-30-cuda-canary-vlm-red-ball-design.md.

Run standalone: python -m tools.vlm_canary <photo_path> <run_context>

Spawned as a fully detached, fire-and-forget subprocess by tools/mission2_day.py right
after a red-reaction photo is already saved — this process is never awaited by its
caller, so any failure here (Ollama not running, model not pulled) can only ever land
in this module's own log row, never propagate to the mission.
"""
import sqlite3
import sys
import time

import ollama

from tools.telemetry_logger import DB_PATH

DEFAULT_MODEL = 'moondream:1.8b'


def init_db(db_path: str = DB_PATH):
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS vlm_canary_log (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at   TEXT,
            run_context  TEXT,
            photo_path   TEXT,
            model_name   TEXT,
            answer       TEXT,
            error        TEXT
        )
    """)
    conn.commit()
    conn.close()


def classify_photo(photo_path: str, model_name: str = DEFAULT_MODEL) -> str:
    """Asks the model a plain, open-ended question about the photo. Raises
    RuntimeError on any Ollama-side failure (unreachable daemon, model not pulled) —
    callers (main() below) are expected to catch this and log it as an error row,
    never let it propagate. Mirrors tools/agentic_loop.py's _call_ollama_chat error
    convention exactly.

    Prompt wording matters here: 'What is the main object in this photo? Answer in
    one short sentence.' produced a broken 2-token near-empty response ('urn') from
    this exact model, live-tested 2026-07-30 against a real Mission 2 reaction
    photo — moondream's chat template (`ollama show moondream:1.8b`) is a terse Q/A
    format, and the meta-instruction seems to trigger an early stop. The simple,
    direct 'Describe this image.' correctly identified the red ball in every live
    test; don't revert to a more elaborate prompt without re-testing against a real
    photo first."""
    try:
        result = ollama.chat(
            model=model_name,
            messages=[{
                'role': 'user',
                'content': 'Describe this image.',
                'images': [photo_path],
            }],
        )
    except Exception as exc:
        if 'not found' in str(exc).lower():
            raise RuntimeError(
                f"Model {model_name!r} isn't pulled locally — run "
                f"`ollama pull {model_name}`."
            ) from exc
        raise RuntimeError(
            "Couldn't reach Ollama — is it running? Start it with `ollama serve` "
            "(or check `systemctl status ollama`), then retry."
        ) from exc
    return result.message.content


def log_vlm_canary_result(run_context, photo_path, model_name, answer=None,
                           error=None, db_path: str = DB_PATH) -> int:
    init_db(db_path)
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO vlm_canary_log "
        "(created_at, run_context, photo_path, model_name, answer, error) "
        "VALUES (?,?,?,?,?,?)",
        (time.strftime("%Y-%m-%dT%H:%M:%S"), run_context, photo_path, model_name,
         answer, error),
    )
    conn.commit()
    row_id = cur.lastrowid
    conn.close()
    return row_id


def find_vlm_canary_results(photo_paths, db_path: str = DB_PATH) -> list:
    """Look up already-logged results for these exact photo paths — reuses whatever
    already resolved the path (e.g. generate_test_report.find_run_photos' own
    time-window matching) as the join key, rather than a second, separate time-window
    match. Returns [] if the table doesn't exist yet (canary never run on this
    machine) or nothing matches — never raises."""
    if not photo_paths:
        return []
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        placeholders = ','.join('?' for _ in photo_paths)
        rows = conn.execute(
            f"SELECT photo_path, model_name, answer, error FROM vlm_canary_log "
            f"WHERE photo_path IN ({placeholders})",
            list(photo_paths),
        ).fetchall()
    except sqlite3.OperationalError:
        rows = []
    conn.close()
    return [dict(r) for r in rows]


def main():
    if len(sys.argv) != 3:
        print("usage: python -m tools.vlm_canary <photo_path> <run_context>",
              file=sys.stderr)
        sys.exit(1)
    photo_path, run_context = sys.argv[1], sys.argv[2]
    # db_path=DB_PATH is passed EXPLICITLY here (not left to log_vlm_canary_result's
    # own default) — a function's own default parameter is bound once at module-load
    # time, so a test that monkeypatches this module's DB_PATH after import would
    # otherwise silently write into the real production DB instead of its tmp_path
    # DB. Referencing the bare global DB_PATH here, inside main()'s own body, re-reads
    # it fresh on every call and correctly picks up a monkeypatched value (same
    # pattern tools/sim_vs_real_comparison.py's main() already uses for its argparse
    # --db default).
    try:
        answer = classify_photo(photo_path)
        log_vlm_canary_result(run_context, photo_path, DEFAULT_MODEL, answer=answer,
                              db_path=DB_PATH)
    except Exception as exc:
        log_vlm_canary_result(run_context, photo_path, DEFAULT_MODEL, error=str(exc),
                              db_path=DB_PATH)


if __name__ == '__main__':
    main()

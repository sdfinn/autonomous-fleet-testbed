#!/bin/bash
# SessionStart hook: prints the dashboard-start command + fleet status to the
# HUMAN user's terminal, not just Claude's context.
#
# Plain stdout from a SessionStart hook is only added to Claude's context, never
# shown to the user (confirmed against Claude Code's hooks docs, 2026-07-29 — a
# genuine gap in the original 2026-07-28 implementation, which used plain `echo`
# and so never reached the user despite the design spec's intent). The fix is to
# emit JSON with `systemMessage` (user-visible) — `additionalContext` is included
# too so Claude keeps seeing the same fleet status it already relied on.
set -euo pipefail

DASH_MSG="Dashboard: streamlit run dashboard/app.py (from repo root; fleet-env venv auto-activates via .bashrc)"

COV_MSG="Coverage: local stage-1 subset — see CLAUDE.md Key Commands for the exact
  pytest --cov invocation | combined stage-1+stage-2 trend: dashboard's Coverage tab
  (pure-local, no third-party site — logged by CI's coverage-report job)"

FLEET_MSG=$(cd ~/autonomous-fleet-testbed && ~/fleet-env/bin/python -m tools.fleet_status 2>/dev/null || echo "Fleet status unavailable (DB not initialized yet?) — run manually: python -m tools.fleet_status")

# --- Last session's recap (2026-11-19, Mike: "I always ask what did we do last time,
# what were the issues and what is next") ---
# Taken straight from the newest docs/sessions/YYYY-MM-DD.md, which every session ends
# by writing (CLAUDE.md, "Session notes"): its Outcome paragraph, its "Open at close"
# list and its "Next (in order)" list. Shown to the user here, and handed to Claude with
# an instruction to read it back in its first reply. No notes file = no recap, silently.
section() {    # section <file> <heading text>: the lines under "## <heading>" up to the next "## " or "---"
  awk -v want="## $2" '
    $0 == want {on = 1; next}
    on && (/^## / || /^---[[:space:]]*$/) {exit}
    on {print}' "$1" | sed -e '/./,$!d'
}
NOTES=$(ls "${CLAUDE_PROJECT_DIR:-$HOME/autonomous-fleet-testbed}"/docs/sessions/20??-??-??.md 2>/dev/null | sort | tail -n 1 || true)
RECAP=""
if [ -n "$NOTES" ] && [ -r "$NOTES" ]; then
  outcome=$(awk '/^\*\*Outcome:\*\*/ {on = 1} on && /^[[:space:]]*$/ {exit} on {print}' "$NOTES")
  RECAP="Last session: $(basename "$NOTES" .md) (full notes: docs/sessions/$(basename "$NOTES"))

${outcome}

Open at close:
$(section "$NOTES" "Open at close")

Next (in order):
$(section "$NOTES" "Next (in order)")"
fi

FULL_MSG="${DASH_MSG}
${COV_MSG}

${FLEET_MSG}"
USER_MSG="$FULL_MSG"
CLAUDE_MSG="$FULL_MSG"
if [ -n "$RECAP" ]; then
  USER_MSG="${RECAP}

${FULL_MSG}"
  CLAUDE_MSG="${FULL_MSG}

SESSION RECAP -- standing request from Mike (2026-11-19): begin your FIRST reply of this
session by reading this back to him without being asked -- what we did last time, what
the issues were, and what is next -- then answer whatever he asked. Read the full notes
file first if he asks for detail.

${RECAP}"
fi

jq -n --arg user "$USER_MSG" --arg claude "$CLAUDE_MSG" '{
  systemMessage: $user,
  hookSpecificOutput: {
    hookEventName: "SessionStart",
    additionalContext: $claude
  }
}'

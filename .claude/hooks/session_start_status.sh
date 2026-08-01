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

FULL_MSG="${DASH_MSG}
${COV_MSG}

${FLEET_MSG}"

jq -n --arg msg "$FULL_MSG" '{
  systemMessage: $msg,
  hookSpecificOutput: {
    hookEventName: "SessionStart",
    additionalContext: $msg
  }
}'

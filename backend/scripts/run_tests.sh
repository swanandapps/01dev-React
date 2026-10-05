#!/usr/bin/env bash
# The one documented way to run the WHOLE backend test suite.
#
# Why this exists instead of a plain `pytest tests`: backend/.venv (built
# from requirements.txt) and backend/.mcp-venv (requirements.txt +
# requirements-mcp.txt) are two separate environments, because fastapi's
# starlette pin and fastmcp's starlette requirement cannot both be satisfied
# in one environment — see requirements-mcp.txt for the proof. This script
# runs each test file in whichever venv it actually needs and reports one
# combined pass/fail, so nobody has to remember the split by hand.
#
# Usage: backend/scripts/run_tests.sh
# Exit code: 0 only if BOTH venvs' runs pass.

set -uo pipefail
cd "$(dirname "$0")/.."

# Tests that import app.mcp.the01dev_tools (needs fastmcp -> .mcp-venv).
# Everything else imports app.main or a plain service module (needs the
# normal backend deps without fastmcp's conflicting starlette -> .venv).
MCP_ONLY_TESTS=(
  tests/test_mcp_get_concept_confidence.py
  tests/test_mcp_record_skill_observation.py
  tests/test_mcp_search_course_content_citations.py
  tests/test_mcp_get_learning_strengths.py
  tests/test_mcp_get_enrolled_courses.py
  tests/test_mcp_get_learning_metrics.py
  tests/test_mcp_explain_concept.py
)

if [ ! -x .venv/bin/pytest ]; then
  echo "backend/.venv not found — run: python3 -m venv .venv && .venv/bin/pip install -r requirements.txt" >&2
  exit 2
fi
if [ ! -x .mcp-venv/bin/pytest ]; then
  echo "backend/.mcp-venv not found — run: python3 -m venv .mcp-venv && .mcp-venv/bin/pip install -r requirements.txt && .mcp-venv/bin/pip install -r requirements-mcp.txt" >&2
  exit 2
fi

IGNORE_ARGS=()
for f in "${MCP_ONLY_TESTS[@]}"; do
  IGNORE_ARGS+=(--ignore="$f")
done

echo "== backend/.venv :: tests/ minus the mcp-server tests =="
.venv/bin/pytest tests "${IGNORE_ARGS[@]}" -q
VENV_STATUS=$?

echo
echo "== backend/.mcp-venv :: the mcp-server tests (need fastmcp) =="
.mcp-venv/bin/pytest "${MCP_ONLY_TESTS[@]}" -q
MCP_STATUS=$?

echo
if [ "$VENV_STATUS" -ne 0 ] || [ "$MCP_STATUS" -ne 0 ]; then
  echo "FAILED — .venv exit=$VENV_STATUS, .mcp-venv exit=$MCP_STATUS"
  exit 1
fi
echo "ALL PASSED — full backend suite is green across both venvs."

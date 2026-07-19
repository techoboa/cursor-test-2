#!/bin/bash
# Watches the entire project for file save operations (manual edits in the
# editor AND agent-driven writes) and forwards each detected save to
# auto-commit-on-save.sh, which commits + pushes every 5th save.
#
# Requires fswatch (brew install fswatch). Run in the background:
#   nohup .cursor/hooks/watch-all-saves.sh >> .cursor/hooks/watcher.log 2>&1 &

set -u

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
STATE_DIR="$REPO_ROOT/.cursor/hooks"
HANDLER="$STATE_DIR/auto-commit-on-save.sh"
PID_FILE="$STATE_DIR/.watcher.pid"

echo $$ > "$PID_FILE"
trap 'rm -f "$PID_FILE"' EXIT

if ! command -v fswatch >/dev/null 2>&1; then
  echo "fswatch not found on PATH; cannot watch for file saves." >&2
  exit 1
fi

cd "$REPO_ROOT" || exit 1

echo "$(date '+%Y-%m-%d %H:%M:%S') Watcher started (pid $$) on $REPO_ROOT"

fswatch -o -r -l 1 \
  --exclude '/\.git/' \
  --exclude '/\.cursor/hooks/\.save_count$' \
  --exclude '/\.cursor/hooks/auto-commit\.log$' \
  --exclude '/\.cursor/hooks/watcher\.log$' \
  --exclude '/\.cursor/hooks/\.watcher\.pid$' \
  --exclude '/\.venv/' \
  --exclude '__pycache__' \
  --exclude '/\.DS_Store$' \
  "$REPO_ROOT" |
while read -r _batch; do
  "$HANDLER"
done

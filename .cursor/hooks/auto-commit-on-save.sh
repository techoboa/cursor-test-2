#!/bin/bash
# Cursor afterFileEdit hook: counts file save operations and, every 5th save,
# commits and pushes all changes to the configured GitHub remote.
#
# Fails open: any error here only logs a message and never blocks the edit.

set -u

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
STATE_DIR="$REPO_ROOT/.cursor/hooks"
COUNT_FILE="$STATE_DIR/.save_count"
LOG_FILE="$STATE_DIR/auto-commit.log"
SAVE_THRESHOLD=5
BRANCH="main"

log() {
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" >> "$LOG_FILE"
}

# Consume stdin (hook input JSON) so Cursor doesn't see a broken pipe.
cat > /dev/null

cd "$REPO_ROOT" || exit 0

if [ ! -d .git ]; then
  log "No .git directory found at $REPO_ROOT; skipping."
  exit 0
fi

count=0
if [ -f "$COUNT_FILE" ]; then
  count=$(cat "$COUNT_FILE" 2>/dev/null || echo 0)
fi
case "$count" in
  ''|*[!0-9]*) count=0 ;;
esac

count=$((count + 1))

if [ "$count" -lt "$SAVE_THRESHOLD" ]; then
  echo "$count" > "$COUNT_FILE"
  exit 0
fi

# Threshold reached: reset counter and attempt commit + push.
echo 0 > "$COUNT_FILE"
log "Save threshold ($SAVE_THRESHOLD) reached; attempting commit and push."

if [ -z "$(git status --porcelain)" ]; then
  log "No changes to commit."
  exit 0
fi

git add -A >> "$LOG_FILE" 2>&1

if git diff --cached --quiet; then
  log "No staged changes after add; skipping commit."
  exit 0
fi

commit_msg="Auto-commit: ${SAVE_THRESHOLD} file save operations ($(date '+%Y-%m-%d %H:%M:%S'))"
if git commit -m "$commit_msg" >> "$LOG_FILE" 2>&1; then
  log "Committed: $commit_msg"
else
  log "Commit failed."
  exit 0
fi

if git push origin "$BRANCH" >> "$LOG_FILE" 2>&1; then
  log "Pushed to origin/$BRANCH successfully."
else
  log "Push to origin/$BRANCH failed (see log above). Changes remain committed locally."
fi

exit 0

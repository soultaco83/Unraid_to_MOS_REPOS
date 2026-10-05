#!/usr/bin/env bash
#
# publish_repo.sh - bash version of publish_repo.fish.
#
# Turn the Unraid_to_MOS_REPOS working tree into a single clean git repository
# that is ready to push to GitHub. The repository keeps one self-contained MOS
# Hub repository folder per upstream author (each with its own maintainer.json,
# docker/ and images/), plus the conversion tools, and commits the whole tree as
# ONE repository.
#
# Usage:
#   tools/publish_repo.sh [ROOT_DIR] [REMOTE_URL]
#
#   ROOT_DIR    defaults to the parent directory of this script
#   REMOTE_URL  optional, e.g. https://github.com/<user>/Unraid_to_MOS_REPOS
#               when given it is configured as the "origin" remote
#               (nothing is pushed automatically)
#
# Idempotent: the repository is only re-committed when its content changed, so
# it can be re-run after every conversion refresh.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="${1:-$(cd "$SCRIPT_DIR/.." && pwd)}"
REMOTE_URL="${2:-}"
cd "$ROOT"

[ -d .git ] || git init -q -b main
git add -A

if [ -z "$(git log --oneline -1 2>/dev/null || true)" ]; then
  msg="Initial import: unRAID template sets converted for MOS Hub"
else
  msg="Refresh MOS templates ($(date +%Y-%m-%d))"
fi

if ! git diff --cached --quiet; then
  git commit -q -m "$msg"
fi

if [ -n "$REMOTE_URL" ]; then
  url="${REMOTE_URL%/}"
  if git remote get-url origin >/dev/null 2>&1; then
    git remote set-url origin "$url"
  else
    git remote add origin "$url"
  fi
fi

printf '%-24s %5d files  %s\n' \
  "$(basename "$(pwd)")" "$(git ls-files | wc -l)" "$(git log --oneline -1)"

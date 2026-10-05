#!/usr/bin/env fish
#
# publish_repo.fish - turn the Unraid_to_MOS_REPOS working tree into a single
# clean git repository that is ready to push to GitHub.
#
# The repository is ONE flat MOS Hub repository: maintainer.json and
# docker/<App>.json sit at the repository root (the only layout the Hub
# indexes), with the upstream licence texts under licenses/ and the conversion
# and publish tools under tools/.
#
# Usage:
#   tools/publish_repo.fish [ROOT_DIR] [REMOTE_URL]
#
#   ROOT_DIR    defaults to the parent directory of this script
#   REMOTE_URL  optional, e.g. https://github.com/<user>/Unraid_to_MOS_REPOS
#               when given it is configured as the "origin" remote
#               (nothing is pushed automatically)
#
# Idempotent: the repository is only re-committed when its content changed, so
# it can be re-run after every conversion refresh.

set -l script_dir (dirname (status --current-filename))
set -l root $argv[1]
test -z "$root"; and set root (realpath "$script_dir/..")
set -l remote_url $argv[2]

cd "$root"; or exit 1

if not test -d .git
    git init -q -b main; or exit 1
end

git add -A; or exit 1

set -l lastlog (git log --oneline -1 2>/dev/null)
set -l msg "Refresh MOS templates "(date +%Y-%m-%d)
test -z "$lastlog"; and set msg "Initial import: unRAID template sets converted for MOS Hub"

if not git diff --cached --quiet
    git commit -q -m "$msg"; or exit 1
end

if test -n "$remote_url"
    set -l url (string replace -r '/+$' '' -- $remote_url)
    if git remote get-url origin >/dev/null 2>&1
        git remote set-url origin "$url"
    else
        git remote add origin "$url"
    end
end

printf '%-24s %5d files  %s\n' \
    (basename (pwd)) (count (git ls-files)) (git log --oneline -1)

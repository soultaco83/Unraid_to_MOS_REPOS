#!/usr/bin/env fish
#
# create_and_push.fish - create (or update) the single Unraid_to_MOS_REPOS
# repository on GitHub and push the local templates to it.
#
# The repository bundles one self-contained MOS Hub repository folder per
# upstream author, so the whole collection is added to MOS Hub as ONE URL.
#
# Usage:
#   tools/create_and_push.fish [ROOT_DIR] [--name NAME] [--owner OWNER]
#                              [--description TEXT] [--private]
#
#   ROOT_DIR       defaults to the parent directory of this script
#   --name         repository name             (default: Unraid_to_MOS_REPOS)
#   --owner        user or organisation that owns it
#                  (default: the gh-authenticated user)
#   --description  repository description
#   --private      create a private repository instead of public
#                  (MOS Hub clones repos without credentials, so public is what
#                  you normally want)
#
# Repositories that already exist are not recreated - the origin remote is
# simply re-pointed at them and the local commits are pushed, so the script is
# safe to run again after every conversion refresh.

set -l script_dir (dirname (status --current-filename))
set -l root ""
set -l name "Unraid_to_MOS_REPOS"
set -l owner ""
set -l description "unRAID Community Applications docker templates converted for the MOS Hub"
set -l visibility "--public"

for arg in $argv
    switch $arg
        case '--private'
            set visibility "--private"
        case '--name=*'
            set name (string replace -- '--name=' '' $arg)
        case '--owner=*'
            set owner (string replace -- '--owner=' '' $arg)
        case '--description=*'
            set description (string replace -- '--description=' '' $arg)
        case '-h' '--help'
            echo "usage: "(status --current-filename)" [ROOT_DIR] [--name NAME] [--owner OWNER] [--description TEXT] [--private]"
            exit 0
        case '-*'
            echo "error: unknown option '$arg'" >&2
            exit 2
        case '*'
            set root $arg
    end
end

test -z "$root"; and set root (realpath "$script_dir/..")
cd "$root"; or exit 1

command -q gh; or begin
    echo "error: gh is not installed. Install it first, e.g.:" >&2
    echo "  curl -fsSL -o gh.tar.gz https://github.com/cli/cli/releases/latest/download/gh_linux_amd64.tar.gz" >&2
    exit 1
end

if not gh auth status >/dev/null 2>&1
    echo "error: not logged in to GitHub. Run 'gh auth login' first, then re-run this script." >&2
    exit 1
end

if not test -d .git
    echo "error: $root is not a git repository yet. Run tools/publish_repo.fish first." >&2
    exit 1
end

set -l user "$owner"
test -z "$user"; and set user (gh api user --jq .login)
set -l full "$user/$name"
set -l url "https://github.com/$full.git"

echo "owner: $user   repo: $name   visibility: $visibility"
echo

# NOTE: capture into a variable first. "test -n (cmd)" with empty output expands
# to zero arguments, and fish's "test -n" with no operand is TRUE, which would
# wrongly take the set-url branch for a missing remote.
set -l current_remote (git remote get-url origin 2>/dev/null)
if test -n "$current_remote"
    git remote set-url origin "$url"
else
    git remote add origin "$url"
end

if gh repo view "$full" >/dev/null 2>&1
    printf '%-24s exists, pushing    ' "$name"
    if git push -u origin main >/dev/null 2>&1
        echo "ok  -> $url"
    else
        echo "FAILED"
        exit 1
    end
else
    printf '%-24s creating, pushing  ' "$name"
    if gh repo create "$full" $visibility --source=. --push --description "$description" >/dev/null 2>&1
        echo "ok  -> $url"
    else
        echo "FAILED"
        exit 1
    end
end

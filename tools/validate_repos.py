#!/usr/bin/env python3
"""
validate_repos.py - validate each per-source MOS Hub repository folder in the
Unraid_to_MOS_REPOS working tree against the rules the MOS Hub itself enforces
when it clones and indexes a repository.

Checks performed per repository folder:
  * maintainer.json exists, parses and defines "maintainer"
  * docker/ exists and contains at least one template
  * every docker/*.json parses and defines name / repo / category
  * every category is part of the MOS Hub vocabulary, otherwise the template is
    invisible to the Hub's category filter (mos-api: hub.service.js)
  * template names are unique inside the repository
  * icons are absolute http(s) URLs, because the Hub renders them remotely
  * upstream stub/example templates are not published
  * files carry no executable bits, which would dirty the git tree on reconversion

Usage:
    python3 validate_repos.py [REPOS_ROOT]

Defaults:
    REPOS_ROOT = the parent directory of this script (i.e. Unraid_to_MOS_REPOS/)
"""
from __future__ import annotations

import glob
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from unraid_to_mos import MOS_CATEGORIES, PLACEHOLDER_MARKERS  # noqa: E402

SKIP_DIRS = {"tools", "images"}


def check_modes(repo_dir):
    """Warn about executable bits inside a repository folder.

    A published repository is pure data (JSON, markdown, icons and a licence), so
    every file should be mode 0644. A stray 0755/0777 is harmless to the Hub but
    makes the git tree dirty the moment anything rewrites the file, which shows up
    as commit churn on every reconversion. convert_sources.py normalises modes, so
    anything reported here came from outside the pipeline.
    """
    odd = []
    for root, dirs, files in os.walk(repo_dir):
        dirs[:] = [d for d in dirs if d != ".git"]
        for fname in files:
            path = os.path.join(root, fname)
            if os.stat(path).st_mode & 0o111:
                odd.append(os.path.relpath(path, repo_dir))
    if not odd:
        return []
    shown = ", ".join(sorted(odd)[:5])
    if len(odd) > 5:
        shown += ", ..."
    return ["%d file(s) are executable (expected mode 0644): %s" % (len(odd), shown)]


def check_repo(repo_dir):
    """Return (template_count, problems, warnings) for one repository folder."""
    problems, warnings = [], []
    name = os.path.basename(repo_dir)
    warnings.extend(check_modes(repo_dir))

    maint_path = os.path.join(repo_dir, "maintainer.json")
    if not os.path.isfile(maint_path):
        problems.append("missing maintainer.json")
    else:
        try:
            maint = json.load(open(maint_path, encoding="utf-8"))
            if not maint.get("maintainer"):
                problems.append("maintainer.json has no 'maintainer' field")
        except Exception as exc:  # noqa: BLE001
            problems.append("maintainer.json is not valid JSON: %s" % exc)

    docker_dir = os.path.join(repo_dir, "docker")
    files = sorted(glob.glob(os.path.join(docker_dir, "*.json")))
    if not os.path.isdir(docker_dir) or not files:
        problems.append("no templates in docker/")
        return 0, problems, warnings

    seen_names = {}
    for path in files:
        rel = os.path.relpath(path, repo_dir)
        try:
            tpl = json.load(open(path, encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            problems.append("%s: invalid JSON (%s)" % (rel, exc))
            continue

        if not tpl.get("name"):
            problems.append("%s: missing 'name'" % rel)
        if not tpl.get("repo"):
            problems.append("%s: missing 'repo'" % rel)

        cats = tpl.get("category")
        if not isinstance(cats, list) or not cats:
            problems.append("%s: 'category' must be a non-empty list" % rel)
        else:
            for cat in cats:
                if cat not in MOS_CATEGORIES:
                    problems.append("%s: unknown category %r (not in MOS vocabulary)" % (rel, cat))

        haystack = " ".join(str(tpl.get(f, "")) for f in ("name", "repo")) + " " + " ".join(cats or [])
        for marker in PLACEHOLDER_MARKERS:
            if marker in haystack:
                problems.append("%s: looks like an upstream stub template (%s)" % (rel, marker))
                break

        icon = tpl.get("icon")
        if icon and not str(icon).lower().startswith(("http://", "https://")):
            warnings.append("%s: icon is not an absolute URL (%r)" % (rel, icon))

        key = tpl.get("name")
        if key:
            if key in seen_names:
                problems.append("%s: duplicate template name %r (also in %s)" % (rel, key, seen_names[key]))
            else:
                seen_names[key] = rel

    return len(files), problems, warnings



def main(argv):
    root = argv[1] if len(argv) > 1 else os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    repos = sorted(
        d for d in glob.glob(os.path.join(root, "*"))
        if os.path.isdir(d) and os.path.basename(d) not in SKIP_DIRS
    )
    if not repos:
        print("No repositories found under %s" % root)
        return 1

    total_templates = total_problems = total_warnings = 0
    print("%-16s %9s %8s %8s  %s" % ("repository", "templates", "problems", "warnings", "maintainer"))
    print("-" * 72)
    for repo in repos:
        count, problems, warnings = check_repo(repo)
        total_templates += count
        total_problems += len(problems)
        total_warnings += len(warnings)
        maintainer = ""
        try:
            maintainer = json.load(
                open(os.path.join(repo, "maintainer.json"), encoding="utf-8")
            ).get("maintainer", "")
        except Exception:  # noqa: BLE001
            pass
        print("%-16s %9d %8d %8d  %s"
              % (os.path.basename(repo), count, len(problems), len(warnings), maintainer))
        for problem in problems:
            print("   ! %s" % problem)
        for warning in warnings:
            print("   ~ %s" % warning)

    print("-" * 72)
    print("%-16s %9d %8d %8d" % ("TOTAL", total_templates, total_problems, total_warnings))
    return 1 if total_problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

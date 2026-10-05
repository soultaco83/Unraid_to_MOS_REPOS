#!/usr/bin/env python3
"""
validate_repos.py - validate the flat MOS Hub repository in this working tree
against the rules the MOS Hub itself enforces when it clones and indexes a
repository.

The Hub only indexes the *root* of a repository (maintainer.json + docker/), so
this script validates that root layout. Checks performed:

  * maintainer.json exists at the repository root, parses and defines "maintainer"
  * docker/ exists at the repository root and contains at least one template
  * every docker/*.json parses and defines name / repo / category
  * every category is part of the MOS Hub vocabulary, otherwise the template is
    invisible to the Hub's category filter (mos-api: hub.service.js)
  * template names and file stems are unique across the merged repository
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

# Directories that are not part of the Hub payload (tools/ holds the scripts,
# .git is the repository itself).
SKIP_DIRS = ("tools", ".git")


def check_modes(root):
    """Warn about executable bits inside a published repository.

    A published repository is pure data (JSON, markdown, licence texts), so every
    file should be mode 0644. A stray 0755/0777 is harmless to the Hub but makes
    the git tree dirty the moment anything rewrites the file, which shows up as
    commit churn on every reconversion. convert_sources.py normalises modes, so
    anything reported here came from outside the pipeline.
    """
    odd = []
    for dirpath, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for fname in files:
            path = os.path.join(dirpath, fname)
            if os.stat(path).st_mode & 0o111:
                odd.append(os.path.relpath(path, root))
    if not odd:
        return []
    shown = ", ".join(sorted(odd)[:5])
    if len(odd) > 5:
        shown += ", ..."
    return ["%d file(s) are executable (expected mode 0644): %s" % (len(odd), shown)]


def check_root(root):
    """Return (template_count, problems, warnings) for the repository root."""
    problems, warnings = [], []
    warnings.extend(check_modes(root))

    maint_path = os.path.join(root, "maintainer.json")
    if not os.path.isfile(maint_path):
        problems.append("missing maintainer.json at the repository root - "
                        "the Hub indexes the root only, so nothing would be listed")
    else:
        try:
            maint = json.load(open(maint_path, encoding="utf-8"))
            if not maint.get("maintainer"):
                problems.append("maintainer.json has no 'maintainer' field")
        except Exception as exc:  # noqa: BLE001
            problems.append("maintainer.json is not valid JSON: %s" % exc)

    docker_dir = os.path.join(root, "docker")
    files = sorted(glob.glob(os.path.join(docker_dir, "*.json")))
    if not os.path.isdir(docker_dir) or not files:
        problems.append("no templates in docker/ at the repository root")
        return 0, problems, warnings

    seen_names, seen_stems = {}, {}
    for path in files:
        rel = os.path.relpath(path, root)
        stem = os.path.splitext(os.path.basename(path))[0]
        if stem.lower() in seen_stems:
            problems.append("%s: duplicate file stem (also %s)" % (rel, seen_stems[stem.lower()]))
        seen_stems[stem.lower()] = rel

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
    if not os.path.isdir(os.path.join(root, "docker")):
        print("No MOS Hub repository found under %s" % root)
        return 1

    count, problems, warnings = check_root(root)
    maintainer = ""
    try:
        maintainer = json.load(
            open(os.path.join(root, "maintainer.json"), encoding="utf-8")
        ).get("maintainer", "")
    except Exception:  # noqa: BLE001
        pass

    print("repository : %s" % root)
    print("maintainer : %s" % maintainer)
    print("templates  : %d" % count)
    print("problems   : %d" % len(problems))
    print("warnings   : %d" % len(warnings))
    for problem in problems:
        print("   ! %s" % problem)
    for warning in warnings:
        print("   ~ %s" % warning)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))


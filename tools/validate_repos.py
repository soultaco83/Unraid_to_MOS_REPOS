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
  * no unRAID leftovers remain: host paths live under /mnt/user, PUID/PGID are
    99/100 or unRAID only mounts/flags are still mounted (regenerate with
    `convert_sources.py --mos-paths --mos-defaults`)

Usage:
    python3 validate_repos.py [REPOS_ROOT]

Defaults:
    REPOS_ROOT = the parent directory of this script (i.e. Unraid_to_MOS_REPOS/)
"""
from __future__ import annotations

import glob
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from unraid_to_mos import MOS_CATEGORIES, PLACEHOLDER_MARKERS  # noqa: E402
from convert_sources import (  # noqa: E402
    APP_DATA_RE, UNRAID_ARRAY_PREFIX, UNRAID_ONLY_HOSTS, UNRAID_PATH_RE,
    UNRAID_PREFIX, MOS_APPDATA_ROOT, MOS_ARRAY_ROOT, MOS_GID, MOS_UID,
    free_form_texts, identity_value,
)

# `--user 99:100`, `--user=099:100` - unRAID's user/group pair in flag form
UNRAID_USER_RE = re.compile(r"--user(=|\s+)0*99:0*100(?!\d)")

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

    problems.extend(check_mos_hygiene(root))
    return len(files), problems, warnings


def summarize(label, findings, hint):
    """Collapse per-template findings into one problem line with examples.

    A repository converted without the MOS switches reports the same mistake in
    hundreds of templates, so the result is aggregated instead of printed once
    per file. `findings` maps a template file name to one example finding.
    """
    if not findings:
        return []
    shown = ", ".join(list(findings.values())[:3])
    if len(findings) > 3:
        shown += ", ..."
    return ["%d template(s) still %s: %s (%s)" % (len(findings), label, shown, hint)]


def check_mos_hygiene(root):
    """Return problems about unRAID leftovers in a MOS Hub repository.

    convert_sources.py --mos-paths --mos-defaults rewrites the converted
    templates onto the MOS conventions. Anything found here means the repository
    was converted without those switches, or a template was edited by hand.
    """
    stale_paths, stale_identity, stale_flags = {}, {}, {}
    for path in sorted(glob.glob(os.path.join(root, "docker", "*.json"))):
        rel = os.path.basename(path)
        with open(path, encoding="utf-8") as fh:
            tpl = json.load(fh)
        for row in tpl.get("paths") or []:
            host = (row.get("host") or "").strip()
            if host.startswith((UNRAID_PREFIX, UNRAID_ARRAY_PREFIX)):
                stale_paths.setdefault(rel, "%s: %s" % (rel, host))
            elif host.startswith(UNRAID_ONLY_HOSTS):
                stale_paths.setdefault(rel, "%s: %s (unRAID only mount)" % (rel, host))
            elif APP_DATA_RE.match(host) and not host.startswith(MOS_APPDATA_ROOT):
                stale_paths.setdefault(
                    rel, "%s: %s (appdata outside %s)" % (rel, host, MOS_APPDATA_ROOT))
        for label, text in free_form_texts(tpl):
            match = UNRAID_PATH_RE.search(str(text or ""))
            if match:
                stale_paths.setdefault(rel, "%s: %s... in %s" % (rel, match.group(0), label))
        for row in tpl.get("variables") or []:
            key = (row.get("key") or "").upper()
            expected = identity_value(key)
            if expected and str(row.get("value") or "") != expected:
                stale_identity.setdefault(rel, "%s: %s=%s" % (rel, key, row.get("value")))
        extra = tpl.get("extra_parameters") or ""
        if UNRAID_USER_RE.search(extra):
            stale_flags.setdefault(rel, "%s: %s" % (rel, extra))
    hint = "regenerate with `convert_sources.py --mos-paths --mos-defaults`"
    return (summarize("reference unRAID paths (expected %s/... and %s/...)"
                      % (MOS_APPDATA_ROOT, MOS_ARRAY_ROOT), stale_paths, hint)
            + summarize("use unRAID uid/gid defaults (expected %s/%s)" % (MOS_UID, MOS_GID),
                        stale_identity, hint)
            + summarize("pass unRAID's `--user 99:100`", stale_flags, hint))


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


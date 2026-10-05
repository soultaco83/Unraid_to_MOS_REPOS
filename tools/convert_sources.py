#!/usr/bin/env python3
"""
convert_sources.py - clone well-known unRAID Community Applications template
repositories and convert every Docker (<Container>) template into ONE flat MOS
Hub repository (Unraid_to_MOS_REPOS).

The MOS Hub only indexes the *root* of a repository; its documented layout is

    maintainer.json     repository metadata (maintainer, donation)
    docker/<App>.json   one JSON template per container
    images/  plugins/   optional
    README.md

It does not descend into sub-directories, so every converted template is written
into a single top-level docker/ directory. The upstream author of a template
stays identifiable through the README source table and through the per-template
project / support / registry / donate fields. Only the templates whose file name
(or display name) would clash with another author's are prefixed/suffixed with
the source key.

Usage:
    python3 convert_sources.py [WORK_DIR] [OUTPUT_DIR]
                               [--mos-paths] [--mos-defaults]
                               [--appdata-root PATH] [--array-root PATH]
                               [--maintainer NAME] [--donation URL]

Defaults:
    WORK_DIR   = /tmp/unraid-sources                    (shallow clones cached here)
    OUTPUT_DIR = /mnt/github/github/Unraid_to_MOS_REPOS

The published repository targets MOS, not unRAID, so two switches rewrite the
converted templates onto the MOS conventions:

    --mos-paths      /mnt/user/appdata/... -> /mnt/cache/appdata/...
                     every other /mnt/user/... share -> /mnt/Array/...
                     unRAID only folders (dynamix webUI, unRAID VM manager) dropped
    --mos-defaults   PUID/PGID (any uid/gid spelling) -> 500, `--user 99:100`
                     -> `--user 500:500`, dynamix label prefixes removed

Both paths are configurable (--appdata-root / --array-root) because pool names
are local to an installation. The publish call is

    python3 tools/convert_sources.py --mos-paths --mos-defaults

Only <Container version="2"> Docker templates are converted. unRAID plugins and
multi-container (<Containers>) templates are skipped automatically because their
XML root tag is not <Container>.
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import unraid_to_mos as conv  # noqa: E402

# ich777 is deliberately absent: ich777 is a MOS founder and maintains an own
# MOS Hub repository (https://github.com/ich777/mos-templates), so their
# templates would show up twice in the Hub.
SOURCES = [
    {"key": "unraid",          "maintainer": "Lime Technology", "repo": "unraid/docker-templates"},
    {"key": "binhex",          "maintainer": "binhex",          "repo": "binhex/docker-templates"},
    {"key": "nwithan8",        "maintainer": "nwithan8",        "repo": "nwithan8/unraid_templates"},
    {"key": "xushier",         "maintainer": "xushier",         "repo": "xushier/Unraid-Docker-Templates"},
    {"key": "ibracorp",        "maintainer": "IBRACORP",        "repo": "ibracorp/unraid-templates"},
    {"key": "devzwf",          "maintainer": "devzwf",          "repo": "devzwf/unraid-docker-templates"},
    {"key": "hotio",           "maintainer": "hotio",           "repo": "hotio/unraid-templates"},
    {"key": "digiblur",        "maintainer": "digiblur",        "repo": "digiblur/unraid-docker-templates"},
    {"key": "spaceinvaderone", "maintainer": "SpaceinvaderOne", "repo": "SpaceinvaderOne/Docker-Templates-Unraid"},
    {"key": "eurotimmy",       "maintainer": "Eurotimmy",       "repo": "Eurotimmy/unraid-templates"},
    {"key": "nasutils",        "maintainer": "NasUtils",        "repo": "NasUtils/unraid-docker-templates"},
    {"key": "randomninjaatk",  "maintainer": "RandomNinjaAtk",  "repo": "RandomNinjaAtk/unraid-templates"},
    {"key": "p3terx",          "maintainer": "P3TERX",          "repo": "P3TERX/unraid-docker-templates"},
]

# Repository level metadata written to maintainer.json. The MOS Hub labels EVERY
# docker template of a repository with `maintainer` from this file: see
# mos-api/src/services/hub.service.js `_processDockerTemplate()`, which uses
# `maintainerInfo.maintainer` and has no per-template `author` fallback (only
# plugin templates do, in `_processPluginTemplate()`). One flat repository can
# therefore never show the upstream author as the maintainer - that would need
# one repository per author, because the Hub does not descend into
# sub-directories. The hosting account is used instead; the upstream author
# stays visible per template through the `author`, `project`, `support` and
# `donate` fields and through the README source table.
ROOT_MAINTAINER = "Soultaco83"
ROOT_DONATION = ""

LICENSE_FILES = ("LICENSE", "LICENSE.md", "LICENSE.txt", "License", "license", "COPYING")

# --------------------------------------------------------------------------- #
# MOS rewrite (--mos-paths / --mos-defaults)                                  #
# --------------------------------------------------------------------------- #
# unRAID aggregates every share below /mnt/user/ (/mnt/user0/ is the array-only
# view); MOS keeps data directly inside a pool, container data conventionally in
# /mnt/cache/appdata and everything else on the main array. Both roots are
# configurable (--appdata-root / --array-root) because pool names are local to an
# installation.
UNRAID_PREFIX = "/mnt/user/"
UNRAID_ARRAY_PREFIX = "/mnt/user0/"
MOS_APPDATA_ROOT = "/mnt/cache/appdata"
MOS_ARRAY_ROOT = "/mnt/Array"

# Host folders that exist on unRAID only: the dynamix webUI, its plugin
# configuration and the unRAID VM manager. MOS ships an own UI and VM manager, so
# these mounts have no counterpart and are dropped instead of rewritten.
UNRAID_ONLY_HOSTS = (
    "/usr/local/emhttp",
    "/boot/config/plugins/dynamix",
    "/boot/config/domain.cfg",
)

# MOS runs containers as its local user 500; unRAID templates ship 99/100. The
# same concept is spelled PUID/PGID, UID/GID, USER_ID/GROUP_ID or <APP>_UID /
# <APP>_GID upstream, so the keys are matched by pattern instead of by name.
MOS_UID = "500"
MOS_GID = "500"
IDENTITY_KEY_RE = re.compile(r"^(?:P?[UG]ID|(?:USER|GROUP)_?ID|.*_[UG]ID)$", re.IGNORECASE)
GROUP_KEY_RE = re.compile(r"^(?:P?GID|GROUP_?ID|.*_GID)$", re.IGNORECASE)

# Every /mnt/user/... (and /mnt/user0/...) occurrence inside a free-form field
# such as extra parameters or a description.
UNRAID_PATH_RE = re.compile(r"/mnt/user0?(?:/[^\s:'\",]*)?")

# unRAID's dynamix UI prefixes every configuration label with its type.
ROW_NAME_PREFIXES = ("Variable: ", "Path: ", "Port: ", "Device: ", "Label: ", "Config: ")

# /mnt/<pool>/appdata/... - the appdata share whatever the pool is called
APP_DATA_RE = re.compile(r"^/mnt/[^/]+/appdata(?P<rest>/.*)?$")
# `--user 99:100` / `--user=099:100` - unRAID's user/group pair in flag form
USER_FLAG_RE = re.compile(r"--user(=|\s+)0*(\d+):0*(\d+)")

def clone(repo, dest):
    """Shallow-clone an upstream template repository (cached between runs)."""
    if os.path.isdir(os.path.join(dest, ".git")):
        return
    shutil.rmtree(dest, ignore_errors=True)
    subprocess.check_call(
        ["git", "clone", "--depth", "1", "https://github.com/%s.git" % repo, dest],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )


def find_license(src):
    """Return the upstream licence file for a cloned repository, or None."""
    for base in (src, os.path.dirname(os.path.normpath(src))):
        for cand in LICENSE_FILES:
            candidate = os.path.join(base, cand)
            if os.path.isfile(candidate):
                return candidate
    return None


def mos_host_path(host, appdata_root=MOS_APPDATA_ROOT, array_root=MOS_ARRAY_ROOT):
    """Translate one unRAID host path onto the MOS layout.

    Returns None for folders that exist on unRAID only (dynamix webUI, unRAID VM
    manager) - those have to be dropped, not rewritten. Paths that are already
    MOS/device paths (e.g. /var/run/docker.sock, /dev/dri) are returned as is.
    """
    if host.startswith(UNRAID_ONLY_HOSTS):
        return None
    appdata = APP_DATA_RE.match(host)
    if appdata:                                    # /mnt/<pool>/appdata[/...]
        return appdata_root + (appdata.group("rest") or "")
    for prefix in (UNRAID_PREFIX, UNRAID_ARRAY_PREFIX):
        if host == prefix.rstrip("/"):
            return array_root
        if host.startswith(prefix):                # share -> main array
            return "%s/%s" % (array_root, host[len(prefix):])
    return host


def rewrite_paths(obj, appdata_root=MOS_APPDATA_ROOT, array_root=MOS_ARRAY_ROOT):
    """Map unRAID host paths onto the MOS pool layout (--mos-paths).

    Covered are the mount rows of the template plus every `/mnt/user/...`
    occurrence in a free-form field (extra parameters, post parameters,
    description) - `--env-file=/mnt/user/...` is a host path as well. Mount
    *targets* inside the container are left alone: they are part of what the
    application expects, not a host path.
    """
    rows = []
    for row in obj.get("paths") or []:
        host = (row.get("host") or "").strip()
        mapped = mos_host_path(host, appdata_root, array_root)
        if mapped is None:
            continue                               # unRAID-only mount
        if mapped:
            row["host"] = mapped
        rows.append(row)
    obj["paths"] = rows
    for field in ("extra_parameters", "post_parameters", "description"):
        text = obj.get(field)
        if text and UNRAID_PATH_RE.search(text):
            obj[field] = UNRAID_PATH_RE.sub(
                lambda m: mos_host_path(m.group(0), appdata_root, array_root) or "", text)
    return obj


def identity_value(key):
    """Return the MOS value for a uid/gid style variable key, or None."""
    if not IDENTITY_KEY_RE.match(key or ""):
        return None
    return MOS_GID if GROUP_KEY_RE.match(key) else MOS_UID


def mos_user_flag(value):
    """Translate unRAID's `--user 99:100` (also `099:100`, `--user=99:100`)."""
    def repl(match):
        separator, uid, gid = match.group(1), match.group(2).lstrip("0"), match.group(3).lstrip("0")
        if (uid, gid) != ("99", "100"):
            return match.group(0)                  # keep other explicit users
        return "--user%s%s:%s" % (separator, MOS_UID, MOS_GID)
    return USER_FLAG_RE.sub(repl, value)


def apply_mos_defaults(obj):
    """Replace unRAID specific defaults with the MOS conventions (--mos-defaults).

    * PUID/PGID (and the UID/GID spelling) default to MOS's user 500, unRAID
      ships 99/100 which has no meaning on MOS.
    * `--user 99:100` is the same pair in Docker flag form.
    * dynamix label prefixes ("Variable: ", "Path: ", ...) only make sense in
      the unRAID UI.
    """
    for row in obj.get("variables") or []:
        value = identity_value((row.get("key") or "").upper())
        if value:
            row["value"] = value
    extra = obj.get("extra_parameters")
    if extra:
        obj["extra_parameters"] = mos_user_flag(extra)
    for section in ("variables", "paths", "ports", "devices", "labels"):
        for row in obj.get(section) or []:
            name = row.get("name") or ""
            for prefix in ROW_NAME_PREFIXES:
                if name.startswith(prefix) and len(name) > len(prefix):
                    row["name"] = name[len(prefix):]
                    break
    return obj


def unique_file(used, key, stem):
    """Pick a file name that is unique across the merged docker/ directory.

    Comparison is case-insensitive so that the published repository also stays
    intact when it is checked out on a case-insensitive file system
    (macOS/Windows).
    """
    name = stem + ".json"
    if name.lower() not in used:
        return name
    name = "%s-%s.json" % (key, stem)
    suffix = 2
    while name.lower() in used:
        name = "%s-%s-%d.json" % (key, stem, suffix)
        suffix += 1
    return name


def unique_name(used, key, base):
    """Pick a display name that is unique across the merged repository.

    The Hub lists templates by their "name", so two authors shipping the same
    application (e.g. Ghost, FileBrowser) have to stay distinguishable.
    """
    name = base
    if name not in used:
        return name
    name = "%s (%s)" % (base, key)
    suffix = 2
    while name in used:
        name = "%s (%s-%d)" % (base, key, suffix)
        suffix += 1
    return name


def merge(builds, out_root, mos_paths=False, mos_defaults=False,
          appdata_root=MOS_APPDATA_ROOT, array_root=MOS_ARRAY_ROOT):
    """Merge every per-source docker/ directory into OUT_ROOT/docker/.

    Returns the report rows (key, maintainer, template count, upstream repo,
    licence file) used for the README table.
    """
    docker_dir = os.path.join(out_root, "docker")
    shutil.rmtree(docker_dir, ignore_errors=True)
    os.makedirs(docker_dir, exist_ok=True)

    used_files, used_names = {}, {}
    report = []
    for entry in builds:
        placed = 0
        pattern = os.path.join(entry["build"], "docker", "*.json")
        for path in sorted(glob.glob(pattern)):
            with open(path, encoding="utf-8") as fh:
                obj = json.load(fh)
            stem = os.path.splitext(os.path.basename(path))[0]
            if mos_paths:
                rewrite_paths(obj, appdata_root, array_root)
            if mos_defaults:
                apply_mos_defaults(obj)
            # Credit the upstream template author per template. The Hub shows the
            # repository level maintainer for docker templates, but `author` is a
            # valid template field there and keeps the provenance in the data.
            obj.setdefault("author", entry["maintainer"])
            obj["name"] = unique_name(used_names, entry["key"], obj.get("name") or stem)
            fname = unique_file(used_files, entry["key"], stem)
            used_files[fname.lower()] = entry["key"]
            used_names[obj["name"]] = entry["key"]
            with open(os.path.join(docker_dir, fname), "w", encoding="utf-8") as fh:
                json.dump(obj, fh, indent=2, ensure_ascii=False)
                fh.write("\n")
            placed += 1
        entry["count"] = placed
        report.append(entry)
    return report


def write_maintainer(out_root, maintainer, donation):
    """Write the repository-level maintainer.json the Hub reads first."""
    path = os.path.join(out_root, "maintainer.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({"maintainer": maintainer, "donation": donation}, fh, indent=2)
        fh.write("\n")
    os.chmod(path, 0o644)


def write_licenses(out_root, builds):
    """Keep the upstream licence text of every author that published one."""
    lic_dir = os.path.join(out_root, "licenses")
    shutil.rmtree(lic_dir, ignore_errors=True)
    os.makedirs(lic_dir, exist_ok=True)
    kept = 0
    for entry in builds:
        src = entry.get("license")
        if not src:
            continue
        dest = os.path.join(lic_dir, "%s.txt" % entry["key"])
        shutil.copyfile(src, dest)
        os.chmod(dest, 0o644)
        kept += 1
    return kept


def write_readme(out_root, report, maintainer, mos_paths=False, mos_defaults=False,
                 appdata_root=MOS_APPDATA_ROOT, array_root=MOS_ARRAY_ROOT):
    """Write the repository README (layout, MOS Hub instructions, sources)."""
    total = sum(row["count"] for row in report)
    hub_docs = ("https://github.com/mos-nas/mos-docs/blob/main/"
                "docs/MOS-Hub/Creating-Your-Own-MOS-Hub-Repository.md")
    lines = [
        "# Unraid to MOS - template repository",
        "",
        "A single flat [MOS Hub](%s) repository" % hub_docs,
        "holding docker templates converted from **%d** unRAID Community Applications" % len(report),
        "template repositories: **%d templates** from %d upstream authors." % (total, len(report)),
        "",
        "`maintainer.json` and `docker/<App>.json` sit at the repository root, which is",
        "the only layout the MOS Hub indexes. Author provenance is preserved in every",
        "template (`author`, `project`, `support`, `registry`, `donate`) and in the",
        "table below; templates whose file/display name would clash with another",
        "author's carry a source prefix.",
        "",
        "## Add it to MOS Hub",
        "",
        "1. Open **Settings -> System Configuration -> MOS Hub Settings**.",
        "2. Add this repository URL:",
        "",
        "   ```",
        "   https://github.com/soultaco83/Unraid_to_MOS_REPOS",
        "   ```",
        "",
        "3. Click **Refresh**, then open the **Docker** tab.",
        "",
        "### Add the repository root, not a folder link",
        "",
        "The Hub runs `git clone` on every URL of its repository list and then reads",
        "`maintainer.json`, `docker/`, `compose/` and `plugins/` **at the root of the",
        "cloned repository**; it never descends into sub-directories. Folder links such",
        "as `.../Unraid_to_MOS_REPOS/tree/main/binhex` are not git repositories, so the",
        "Hub logs `Hub: Skipping .../tree/main/binhex - not a valid git repository` and",
        "indexes nothing for that entry. Remove folder links, keep only the repository",
        "URL above, then Refresh.",
        "",
        "The log line `Hub: Could not fetch known repositories: ... 404` comes from",
        "`https://mos-official.net/known-repos.json`, which currently returns 404; the",
        "Hub retries hourly and it only affects the suggested-repository list of the",
        "Hub dialog, not the templates of a configured repository.",
        "",
        "### The maintainer label is repository level",
        "",
        "Every docker template of a repository is labelled with the `maintainer` value",
        "from that repository's `maintainer.json` (Hub source `src/services/",
        "hub.service.js`, `_processDockerTemplate()`; unlike plugin templates, docker",
        "templates have no per-template `author` fallback). Because the Hub only reads",
        "the repository root, one flat repository cannot show per-author labels: all",
        "%d templates below carry the hosting account as maintainer." % total,
        "Showing the original author as the label would need one repository per author,",
        "added to the Hub as several repository URLs.",
        "",
        "The upstream author is still identifiable per template: in the install dialog",
        "through `project`, `support` and `donate`, in the template JSON through",
        "`author`, and in the source table below.",
        "",
        "## Layout",
        "",
        "```",
        "maintainer.json      repository metadata (maintainer: %s)" % maintainer,
        "docker/<App>.json    one template per container (%d total)" % total,
        "licenses/            upstream licence text, where the author published one",
        "tools/               conversion + publish scripts (not part of the Hub payload)",
        "```",
        "",
        "Only Docker (`<Container>`) templates are converted; unRAID plugins and",
        "multi-container stacks are excluded. Icons are referenced from the upstream",
        "repositories, so they always match what the author currently ships.",
        "",
    ]
    if mos_paths or mos_defaults:
        lines += [
            "## MOS compatibility",
            "",
            "unRAID specifics were replaced by the MOS equivalents:",
            "",
        ]
        if mos_paths:
            lines += [
                "* host paths: `/mnt/user/appdata/...` -> `%s/...`, every other" % appdata_root,
                "  `/mnt/user/...` share -> `%s/...` (MOS keeps data directly in a" % array_root,
                "  pool instead of aggregating shares below `/mnt/user`), same for",
                "  `/mnt/user/...` in extra parameters and descriptions; folders that",
                "  exist on unRAID only (dynamix webUI, unRAID VM manager) dropped.",
                "  Container side mount targets stay untouched - they are what the",
                "  application expects inside the container, not a host path",
            ]
        if mos_defaults:
            lines += [
                "* identity: `PUID`/`PGID` and every `UID`/`GID` spelling",
                "  (`UID`, `GID`, `USER_ID`, `GROUP_ID`, `<APP>_UID`, ...) default to",
                "  `%s`/`%s` instead of unRAID's 99/100, `--user 99:100` became" % (MOS_UID, MOS_GID),
                "  `--user %s:%s`, dynamix label prefixes (`Variable: `, `Path: `, ...)" % (MOS_UID, MOS_GID),
                "  removed",
            ]
        lines += [
            "",
            "Icons, ports, variables and `br0` network modes were kept as they are: MOS",
            "supports them (`br0` is the bridge used by VMs and containers). The paths",
            "follow the pool names of the host that generated this repository",
            "(`%s`, `%s`) - re-run the conversion with" % (appdata_root, array_root),
            "`--appdata-root` / `--array-root` for differently named pools.",
            "",
        ]
    lines += [
        "## Sources",
        "",
        "| Source | Maintainer | Templates | Upstream | Licence |",
        "|---|---|---:|---|---|",
    ]
    for row in sorted(report, key=lambda r: r["key"]):
        lic = "[kept](./licenses/%s.txt)" % row["key"] if row.get("license") else "not published"
        lines.append("| `%s` | %s | %d | [%s](https://github.com/%s) | %s |"
                     % (row["key"], row["maintainer"], row["count"], row["repo"], row["repo"], lic))
    lines += [
        "",
        "`ich777` is not part of this collection: ich777 is a MOS founder and",
        "publishes an own MOS Hub repository",
        "([ich777/mos-templates](https://github.com/ich777/mos-templates)), so listing",
        "those templates here as well would duplicate every app in the Hub.",
    ]
    switches = " ".join(name for name, enabled in
                        (("--mos-paths", mos_paths), ("--mos-defaults", mos_defaults))
                        if enabled)
    lines += [
        "",
        "Generated with `tools/convert_sources.py%s`, validated with" % (
            " " + switches if switches else ""),
        "`tools/validate_repos.py`, committed with `tools/publish_repo.fish` and pushed",
        "with `tools/create_and_push.fish`.",
        "",
    ]
    path = os.path.join(out_root, "README.md")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))
    os.chmod(path, 0o644)


def prune_old_layout(out_root, keys):
    """Remove the previous per-author repository folders and stray artifacts."""
    removed = []
    for key in keys:
        path = os.path.join(out_root, key)
        if os.path.isdir(path):
            shutil.rmtree(path, ignore_errors=True)
            removed.append(key)
    for stray in ("images",):
        path = os.path.join(out_root, stray)
        if os.path.isdir(path):
            shutil.rmtree(path, ignore_errors=True)
            removed.append(stray)
    return removed


def normalize_modes(root, skip=("tools", ".git")):
    """Normalise modes: directories 0755, data files 0644."""
    os.chmod(root, 0o755)
    for dirpath, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in skip]
        for name in dirs:
            os.chmod(os.path.join(dirpath, name), 0o755)
        for name in files:
            os.chmod(os.path.join(dirpath, name), 0o644)


def main(argv):
    parser = argparse.ArgumentParser(
        description="Convert unRAID template repositories into one flat MOS Hub repository."
    )
    parser.add_argument("work", nargs="?", default="/tmp/unraid-sources",
                        help="directory used to cache the upstream clones")
    parser.add_argument("out", nargs="?", default="/mnt/github/github/Unraid_to_MOS_REPOS",
                        help="published MOS Hub repository root")
    parser.add_argument("--mos-paths", action="store_true",
                        help="rewrite unRAID host paths onto the MOS pools "
                             "(appdata + main array)")
    parser.add_argument("--mos-defaults", action="store_true",
                        help="replace unRAID identity/UI defaults with the MOS "
                             "conventions (PUID/PGID 500, --user 99:100, label prefixes)")
    parser.add_argument("--appdata-root", default=MOS_APPDATA_ROOT,
                        help="MOS path for container data (default: %(default)s)")
    parser.add_argument("--array-root", default=MOS_ARRAY_ROOT,
                        help="MOS path for main array data (default: %(default)s)")
    parser.add_argument("--maintainer", default=ROOT_MAINTAINER,
                        help="value written to maintainer.json (default: %(default)s)")
    parser.add_argument("--donation", default=ROOT_DONATION,
                        help="donation URL written to maintainer.json")
    args = parser.parse_args(argv[1:])

    work, out_root = args.work, args.out
    os.makedirs(work, exist_ok=True)
    os.makedirs(out_root, exist_ok=True)

    builds = []
    for src in SOURCES:
        clone_dir = os.path.join(work, src["key"])
        build_dir = os.path.join(work, "build", src["key"])
        clone(src["repo"], clone_dir)
        shutil.rmtree(build_dir, ignore_errors=True)
        os.makedirs(build_dir, exist_ok=True)
        conv.MAINTAINER = src["maintainer"]
        conv.DONATION = ""
        print("== %s (%s)" % (src["key"], src["repo"]))
        conv.main(["unraid_to_mos", clone_dir, build_dir])
        builds.append({
            "key": src["key"],
            "maintainer": src["maintainer"],
            "repo": src["repo"],
            "build": build_dir,
            "license": find_license(clone_dir),
        })

    report = merge(builds, out_root, mos_paths=args.mos_paths,
                   mos_defaults=args.mos_defaults,
                   appdata_root=args.appdata_root, array_root=args.array_root)
    write_maintainer(out_root, args.maintainer, args.donation)
    kept = write_licenses(out_root, builds)
    write_readme(out_root, report, args.maintainer, mos_paths=args.mos_paths,
                 mos_defaults=args.mos_defaults,
                 appdata_root=args.appdata_root, array_root=args.array_root)
    removed = prune_old_layout(out_root, [s["key"] for s in SOURCES])
    normalize_modes(out_root)

    print()
    for row in report:
        print("%-16s %5d templates  %s" % (row["key"], row["count"], row["repo"]))
    print("-" * 64)
    print("%-16s %5d templates  (%d sources, %d licences kept)"
          % ("TOTAL", sum(r["count"] for r in report), len(report), kept))
    if removed:
        print("removed old layout : %s" % ", ".join(sorted(removed)))
    print("output             : %s" % os.path.join(out_root, "docker"))
    if args.mos_paths:
        print("MOS paths          : appdata %s, array %s"
              % (args.appdata_root, args.array_root))
    print("MOS defaults       : %s" % ("applied" if args.mos_defaults else "not applied"))


if __name__ == "__main__":
    main(sys.argv)




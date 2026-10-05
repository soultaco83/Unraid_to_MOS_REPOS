#!/usr/bin/env python3
"""
convert_sources.py - clone well-known unRAID Community Applications template
repositories and convert every Docker (<Container>) template into a per-source
MOS Hub repository folder under OUTPUT_DIR/<source>/.

The whole OUTPUT_DIR is published as one git repository (Unraid_to_MOS_REPOS).
It holds a self-contained MOS Hub repository per upstream source - each with its
own maintainer.json, docker/ and images/ - so the original author of every
template set stays clearly separated, while the whole collection is added to
MOS Hub as a single repository URL.

Usage:
    python3 convert_sources.py [WORK_DIR] [OUTPUT_DIR]

Defaults:
    WORK_DIR   = /tmp/unraid-sources                     (shallow clones cached here)
    OUTPUT_DIR = /mnt/github/github/Unraid_to_MOS_REPOS

Only <Container version="2"> Docker templates are converted. unRAID plugins
and multi-container (<Containers>) templates are skipped automatically because
their XML root tag is not <Container>.
"""
from __future__ import annotations

import glob
import json
import os
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import unraid_to_mos as conv  # noqa: E402

SOURCES = [
    {"key": "unraid",          "maintainer": "Lime Technology", "repo": "unraid/docker-templates"},
    {"key": "binhex",          "maintainer": "binhex",          "repo": "binhex/docker-templates"},
    {"key": "ich777",          "maintainer": "ich777",          "repo": "ich777/docker-templates"},
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

IMAGE_EXTS = ("*.png", "*.svg", "*.webp", "*.jpg", "*.jpeg", "*.gif", "*.ico")


def clone(repo, dest):
    if os.path.isdir(os.path.join(dest, ".git")):
        return
    shutil.rmtree(dest, ignore_errors=True)
    subprocess.check_call(
        ["git", "clone", "--depth", "1", "https://github.com/%s.git" % repo, dest],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )


def detect_donation(src):
    for f in glob.glob(os.path.join(src, "**", "*.xml"), recursive=True):
        if os.sep + ".git" + os.sep in f:
            continue
        try:
            root = ET.parse(f).getroot()
        except Exception:  # noqa: BLE001
            continue
        el = root.find("DonateLink")
        if el is not None and (el.text or "").strip():
            return el.text.strip()
    return ""


def mirror_icons(src, out_dir):
    index = {}
    for ext in IMAGE_EXTS:
        for path in glob.glob(os.path.join(src, "**", ext), recursive=True):
            if os.sep + ".git" + os.sep in path:
                continue
            index.setdefault(os.path.basename(path).lower(), path)
    out_img = os.path.join(out_dir, "images")
    copied = 0
    for f in sorted(glob.glob(os.path.join(out_dir, "docker", "*.json"))):
        data = json.load(open(f, encoding="utf-8"))
        base = os.path.basename((data.get("icon") or "").split("?")[0]).lower()
        if base and base in index:
            os.makedirs(out_img, exist_ok=True)
            dest = os.path.join(out_img, os.path.basename(index[base]))
            if not os.path.exists(dest):
                shutil.copy2(index[base], dest)
                copied += 1
    return copied


def normalize_modes(out_dir):
    """Force 0644 on every file and 0755 on every directory of a repository.

    Nothing here is executable, but two operations leak modes into the output:
    open(..., "w") keeps the mode of a file that already exists, and
    shutil.copy2 copies the mode of the source icon. Either one lets a stray
    0755/0777 (from an editor, an old run or an upstream repo) survive into the
    generated repository, where it turns every reconversion into a dirty git
    tree and makes the output depend on something other than the input. Fixing
    the mode keeps conversions reproducible.
    """
    if not os.path.isdir(out_dir):
        return
    os.chmod(out_dir, 0o755)
    for root, dirs, files in os.walk(out_dir):
        dirs[:] = [d for d in dirs if d != ".git"]
        for name in dirs:
            os.chmod(os.path.join(root, name), 0o755)
        for name in files:
            os.chmod(os.path.join(root, name), 0o644)


def write_readme(out_dir, maintainer, repo, count):
    with open(os.path.join(out_dir, "README.md"), "w", encoding="utf-8") as fh:
        fh.write(
            "# %s - MOS Templates\n\n"
            "Docker container templates from [%s](https://github.com/%s), converted to the\n"
            "[MOS Hub](https://github.com/ich777/mos-templates) JSON template format.\n\n"
            "* Maintainer: **%s**\n"
            "* Source: https://github.com/%s\n"
            "* Templates: **%d**\n\n"
            "## Layout\n\n```\nmaintainer.json\ndocker/<App>.json\nimages/            (icons that were hosted in the source repo)\n```\n\n"
            "Generated with `tools/convert_sources.py` (Docker templates only, plugins excluded).\n"
            % (maintainer, repo, repo, maintainer, repo, count)
        )


INDEX_HEADER = (
    "# Unraid to MOS - template repository\n\n"
    "A single GitHub repository that bundles **one self-contained MOS Hub repository\n"
    "per upstream author**. Each folder below has its own `maintainer.json`, `docker/`\n"
    "and `images/`, so the original author of every template set stays clearly\n"
    "separated while the whole collection is added to MOS Hub as **one repository URL**.\n\n"
    "Converted from well-known unRAID Community Applications template repositories.\n"
    "Only Docker (`<Container>`) templates are converted; unRAID plugins and\n"
    "multi-container stacks are excluded.\n\n"
    "| Folder | Maintainer | Templates | Upstream |\n"
    "|---|---|---:|---|\n"
)


def main(argv):
    work = argv[1] if len(argv) > 1 else "/tmp/unraid-sources"
    out_root = argv[2] if len(argv) > 2 else "/mnt/github/github/Unraid_to_MOS_REPOS"
    os.makedirs(work, exist_ok=True)
    os.makedirs(out_root, exist_ok=True)

    report = []
    for src in SOURCES:
        clone_dir = os.path.join(work, src["key"])
        out_dir = os.path.join(out_root, src["key"])
        clone(src["repo"], clone_dir)
        shutil.rmtree(os.path.join(out_dir, "docker"), ignore_errors=True)
        shutil.rmtree(os.path.join(out_dir, "images"), ignore_errors=True)
        donation = detect_donation(clone_dir)
        conv.MAINTAINER = src["maintainer"]
        conv.DONATION = donation
        conv.main(["unraid_to_mos", clone_dir, out_dir])
        icons = mirror_icons(clone_dir, out_dir)
        count = len(glob.glob(os.path.join(out_dir, "docker", "*.json")))
        write_readme(out_dir, src["maintainer"], src["repo"], count)
        normalize_modes(out_dir)
        report.append((src["key"], src["maintainer"], count, src["repo"]))
        print("-> %-16s %3d templates, %3d icons, donation=%r\n"
              % (src["key"], count, icons, donation))

    with open(os.path.join(out_root, "README.md"), "w", encoding="utf-8") as fh:
        fh.write(INDEX_HEADER)
        for key, maintainer, count, repo in report:
            fh.write("| [%s](./%s) | %s | %d | [%s](https://github.com/%s) |\n"
                     % (key, key, maintainer, count, repo, repo))
        fh.write(
            "\nGenerated with `tools/convert_sources.py`, committed with"
            " `tools/publish_repo.fish` and pushed with `tools/create_and_push.fish`.\n"
        )
    os.chmod(os.path.join(out_root, "README.md"), 0o644)
    print("DONE - total templates:", sum(r[2] for r in report))


if __name__ == "__main__":
    main(sys.argv)

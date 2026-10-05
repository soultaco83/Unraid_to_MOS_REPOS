#!/usr/bin/env python3
"""
unraid_to_mos.py - convert unRAID <Container version="2"> XML templates into
MOS Hub Docker template JSON files.

MOS Hub template repo layout (see https://github.com/ich777/mos-templates):
    maintainer.json
    docker/<App>.json        <- one JSON file per container template
    (optional) images/, plugins/, README.md, LICENSE

Usage:
    python3 unraid_to_mos.py [SOURCE_TEMPLATES_DIR] [OUTPUT_MOS_DIR]

Defaults:
    SOURCE_TEMPLATES_DIR = /mnt/github/github/unRAID-CA-templates/templates
    OUTPUT_MOS_DIR       = /mnt/github/github/MOS
"""
from __future__ import annotations

import glob
import json
import os
import re
import sys
import xml.etree.ElementTree as ET

# --------------------------------------------------------------------------- #
# Repository metadata (edit these two values for your own repo if you like).  #
# --------------------------------------------------------------------------- #
MAINTAINER = "selfhosters"
DONATION = ""

# The only category labels the MOS Hub accepts. The Hub validates and filters
# against this exact vocabulary (mos-api: services/hub.service.js -> allowedCategories),
# so every label we emit MUST come from this tuple or the template becomes
# invisible to the Hub's category filter.
MOS_CATEGORIES = (
    "AI", "Backup", "Hosting", "Crypto", "Downloader", "Driver", "Game Server",
    "Home Automation", "Media", "Network", "Productivity", "Monitoring",
    "Security", "System", "Utilities", "Misc",
)

# unRAID category token -> MOS Hub category label
CATEGORY_MAP = {
    # game servers
    "gameservers": "Game Server", "gameserver": "Game Server",
    "game server": "Game Server",
    # tools / system
    "tools": "Utilities", "utilities": "Utilities", "utility": "Utilities",
    "other tools": "Utilities", "management": "Utilities",
    "system": "System", "database": "System", "databases": "System",
    "drivers": "Driver", "driver": "Driver",
    # media
    "mediaapp": "Media", "mediaserver": "Media", "media": "Media",
    "video": "Media", "audio": "Media", "music": "Media", "photos": "Media",
    "books": "Media", "entertainment": "Media", "streaming": "Media",
    # downloaders
    "downloaders": "Downloader", "downloader": "Downloader",
    "download": "Downloader", "torrent": "Downloader", "usenet": "Downloader",
    # network
    "network": "Network", "web": "Network", "dns": "Network", "vpn": "Network",
    "proxy": "Network", "messenger": "Network", "voip": "Network",
    "mail": "Network", "remote": "Network",
    # security / privacy
    "security": "Security", "privacy": "Security", "password": "Security",
    "antivirus": "Security", "firewall": "Security",
    # hosting
    "cloud": "Hosting", "hosting": "Hosting",
    # remaining buckets
    "backup": "Backup", "productivity": "Productivity", "finance": "Productivity",
    "monitoring": "Monitoring", "crypto": "Crypto", "ai": "AI",
    "homeautomation": "Home Automation", "home automation": "Home Automation",
    "automation": "Home Automation",
    "other": "Misc", "misc": "Misc",
}

# Substring fallbacks, used only for tokens that are not in CATEGORY_MAP.
# Order matters: the first match wins.
CATEGORY_HINTS = (
    ("game", "Game Server"),
    ("media", "Media"), ("video", "Media"), ("audio", "Media"), ("music", "Media"),
    ("photo", "Media"), ("book", "Media"), ("movie", "Media"), ("stream", "Media"),
    ("podcast", "Media"), ("imag", "Media"), ("dvr", "Media"),
    ("download", "Downloader"), ("torrent", "Downloader"), ("usenet", "Downloader"),
    ("nzb", "Downloader"), ("deluge", "Downloader"),
    ("backup", "Backup"), ("snapshot", "Backup"), ("sync", "Backup"),
    ("crypt", "Crypto"), ("bitcoin", "Crypto"), ("coin", "Crypto"),
    ("wallet", "Crypto"),
    ("monitor", "Monitoring"), ("stat", "Monitoring"), ("uptime", "Monitoring"),
    ("secur", "Security"), ("privacy", "Security"), ("auth", "Security"),
    ("password", "Security"), ("vpn", "Network"), ("proxy", "Network"),
    ("home", "Home Automation"), ("automat", "Home Automation"),
    ("zigbee", "Home Automation"), ("mqtt", "Home Automation"),
    ("driver", "Driver"), ("gpu", "Driver"), ("kernel", "Driver"),
    ("host", "Hosting"), ("cloud", "Hosting"),
    ("network", "Network"), ("dns", "Network"), ("dhcp", "Network"),
    ("web", "Network"), ("messenger", "Network"), ("voip", "Network"),
    ("mail", "Network"),
    ("productiv", "Productivity"), ("office", "Productivity"), ("note", "Productivity"),
    ("file", "Productivity"), ("finance", "Productivity"), ("calendar", "Productivity"),
    ("llm", "AI"),
    ("tool", "Utilities"), ("util", "Utilities"), ("management", "Utilities"),
    ("system", "System"), ("database", "System"), ("docker", "System"),
)

# tokens that carry no useful category information
SKIP_CATEGORY_TOKENS = {
    "", "status", "stable", "beta", "experimental", "deprecated", "development",
    "none", "for",
}

# Upstream stub/example templates that must never be published as an app.
PLACEHOLDER_STEMS = {"template", "example", "sample", "blank", "stub", "appname"}
PLACEHOLDER_MARKERS = (
    "APPNAME", "PROJECTURL", "OVERVIEWTEXT", "CACATEGORY", "YOURAPPNAME",
    "NOTESTEXT", "THREADID",
)
# unRAID Display values that need normalising to the MOS vocabulary
DISPLAY_MAP = {"normal": "always"}


# --------------------------------------------------------------------------- #
# Helpers                                                                     #
# --------------------------------------------------------------------------- #
def clean(value):
    """Return a stripped string, or None when empty/absent."""
    if value is None:
        return None
    value = value.strip()
    return value or None


def elem_text(el):
    """All text inside an element (decoded), stripped. None when empty."""
    if el is None:
        return None
    return clean("".join(el.itertext()))


def attr(el, name):
    return clean(el.get(name))


def bool_attr(el, name):
    return (el.get(name) or "").strip().lower() == "true"


def display_of(el):
    """Map a unRAID Display attribute to the MOS display vocabulary."""
    value = (el.get("Display") or "always").strip()
    return DISPLAY_MAP.get(value, value)


def normalize_category(token):
    """Map an arbitrary unRAID category token onto the MOS Hub vocabulary."""
    key = token.strip().lower()
    if key in CATEGORY_MAP:
        return CATEGORY_MAP[key]
    for needle, label in CATEGORY_HINTS:
        if needle in key:
            return label
    return "Misc"


def parse_categories(raw):
    """Turn a unRAID <Category> string into a list of MOS Hub category labels.

    Every label returned is guaranteed to be a member of MOS_CATEGORIES, so the
    resulting templates stay visible inside the Hub's category filter.
    """
    if not raw:
        return []
    out = []
    for token in raw.replace(",", " ").split():
        for part in token.split(":"):
            part = part.strip()
            if not part:
                continue
            key = part.lower()
            if key in SKIP_CATEGORY_TOKENS:
                continue
            label = normalize_category(part)
            if label not in out:
                out.append(label)
    return out


def is_placeholder(stem, root):
    """Detect upstream stub/example templates (e.g. binhex/_template.xml).

    Only the identifying fields are inspected (Name / Repository / Category):
    real templates legitimately mention ``APPNAME`` inside their default paths,
    so scanning the whole document produces false positives.
    """
    name = stem.strip().lower().strip("_- ")
    if name in PLACEHOLDER_STEMS:
        return True
    haystack = " ".join(filter(None, (
        elem_text(child(root, "Name")),
        elem_text(child(root, "Repository")),
        elem_text(child(root, "Category")),
    )))
    return any(marker in haystack for marker in PLACEHOLDER_MARKERS)


def fix_malformed(xml_text):
    """Repair the common hand-editing mistake <Config .../>VALUE</Config>."""
    return re.sub(r"(<Config\b[^>]*?)/>\s*([^<]*?)</Config>", r"\1>\2</Config>", xml_text)


def config_value(cfg):
    """The element body (saved value) falling back to the Default attribute."""
    return elem_text(cfg) or attr(cfg, "Default")


# --------------------------------------------------------------------------- #
# Config rows                                                                 #
# --------------------------------------------------------------------------- #
def build_rows(root):
    """Split <Config> entries into paths / ports / variables / devices / labels."""
    paths, ports, variables, devices, labels = [], [], [], [], []
    for cfg in root.findall("Config"):
        ctype = (cfg.get("Type") or "").strip()
        name = attr(cfg, "Name")
        target = attr(cfg, "Target")
        mode = attr(cfg, "Mode")
        desc = attr(cfg, "Description") or ""
        required = bool_attr(cfg, "Required")
        mask = bool_attr(cfg, "Mask")
        display = display_of(cfg)
        value = config_value(cfg)

        if ctype == "Path":
            paths.append({
                "name": name or target or value,
                "host": value,
                "container": target or value,
                "mode": mode or "rw",
                "description": desc,
                "required": required,
                "display": display,
                "default": None,
            })
        elif ctype == "Port":
            ports.append({
                "name": name or target or value,
                "host": value or target,
                "container": target or value,
                "protocol": (mode or "tcp").lower(),
                "description": desc,
                "required": required,
                "mask": mask,
                "display": display,
                "default": None,
            })
        elif ctype == "Variable":
            key = target or name
            if not key:
                continue
            variables.append({
                "name": name or key,
                "key": key,
                "value": value,
                "description": desc,
                "required": required,
                "mask": mask,
                "display": display,
                "default": None,
            })
        elif ctype == "Device":
            host = value
            devices.append({
                "name": name or host,
                "host": host,
                "container": target or host,
                "description": desc,
                "required": required,
                "display": display,
            })
        elif ctype == "Label":
            labels.append({
                "name": name or target,
                "key": target,
                "value": value,
                "description": desc,
                "required": required,
                "mask": mask,
            })
    return paths, ports, variables, devices, labels


# --------------------------------------------------------------------------- #
# Template conversion                                                         #
# --------------------------------------------------------------------------- #
def child(root, tag):
    el = root.find(tag)
    return el


def build_container_object(root):
    paths, ports, variables, devices, labels = build_rows(root)

    name = elem_text(child(root, "Name"))
    repo = elem_text(child(root, "Repository"))
    icon = elem_text(child(root, "Icon"))
    if icon and not icon.lower().startswith(("http://", "https://")):
        icon = None
    extra = elem_text(child(root, "ExtraParams"))

    # NVIDIA pass-through: either --runtime=nvidia or an NVIDIA_VISIBLE_DEVICES var
    gpus = []
    wants_nvidia = (extra and "runtime=nvidia" in extra) or any(
        v["key"] == "NVIDIA_VISIBLE_DEVICES" for v in variables
    )
    if wants_nvidia:
        gpus.append({
            "driver": "nvidia",
            "count": "all",
            "capabilities": ["gpu"],
            "description": "NVIDIA GPU pass-through. Requires the NVIDIA driver / container toolkit on the host (Unraid: install the Nvidia-Driver plugin).",
        })

    # Guarantee the emitted categories are part of the MOS Hub vocabulary;
    # uncategorised templates fall back to "Misc" so they stay filterable.
    categories = [
        c for c in parse_categories(elem_text(child(root, "Category")))
        if c in MOS_CATEGORIES
    ] or ["Misc"]

    obj = {
        "name": name,
        "repo": repo,
        "category": categories,
        "registry": elem_text(child(root, "Registry")),
        "network": elem_text(child(root, "Network")),
        "custom_ip": None,
        "default_shell": elem_text(child(root, "Shell")),
        "privileged": (elem_text(child(root, "Privileged")) or "").lower() == "true",
        "extra_parameters": extra,
        "post_parameters": elem_text(child(root, "PostArgs")),
        "cpu_set": None,
        "web_ui_url": elem_text(child(root, "WebUI")),
    }

    readme = elem_text(child(root, "Readme")) or elem_text(child(root, "ReadMe"))
    if readme:
        obj["readme_url"] = readme

    obj.update({
        "icon": icon,
        "project": elem_text(child(root, "Project")),
        "support": elem_text(child(root, "Support")),
        "description": elem_text(child(root, "Overview")) or elem_text(child(root, "Description")) or "",
    })

    donate = elem_text(child(root, "DonateLink"))
    if donate:
        obj["donate"] = donate
    requires = elem_text(child(root, "Requires"))
    if requires:
        obj["requires"] = requires

    obj.update({
        "paths": paths,
        "ports": ports,
        "variables": variables,
        "devices": devices,
        "labels": labels,
        "gpus": gpus,
    })
    return obj


# --------------------------------------------------------------------------- #
# Entry point                                                                 #
# --------------------------------------------------------------------------- #
def write_maintainer(out_dir):
    with open(os.path.join(out_dir, "maintainer.json"), "w", encoding="utf-8") as fh:
        json.dump({"maintainer": MAINTAINER, "donation": DONATION}, fh, indent=2)
        fh.write("\n")


def main(argv):
    src = argv[1] if len(argv) > 1 else "/mnt/github/github/unRAID-CA-templates/templates"
    out = argv[2] if len(argv) > 2 else "/mnt/github/github/MOS"
    docker_dir = os.path.join(out, "docker")
    os.makedirs(docker_dir, exist_ok=True)

    converted, skipped, failed = [], [], []
    seen_stems = set()
    seen_signatures = {}  # content signature -> first output file that had it
    seen_names = {}       # template name -> file that already uses it
    xml_files = [
        p for p in glob.glob(os.path.join(src, "**", "*.xml"), recursive=True)
        if os.sep + ".git" + os.sep not in p
    ]
    for path in sorted(xml_files):
        try:
            raw = fix_malformed(open(path, encoding="utf-8").read())
            root = ET.fromstring(raw)
        except Exception as exc:  # noqa: BLE001
            failed.append((path, str(exc)))
            continue
        if root.tag != "Container":
            skipped.append((path, root.tag))
            continue
        stem = os.path.splitext(os.path.basename(path))[0]
        if is_placeholder(stem, root):
            skipped.append((path, "placeholder template"))
            continue
        obj = build_container_object(root)
        if stem in seen_stems:
            failed.append((path, "duplicate output name %s.json" % stem))
            continue

        # Some upstream repos ship the very same container several times
        # (e.g. nwithan8/aura.json + aura_2.json). Publishing exact copies would
        # only add noise to the Hub, so keep the first one.
        signature = json.dumps(obj, sort_keys=True)
        previous = seen_signatures.get(signature)
        if previous:
            skipped.append((path, "duplicate of %s" % os.path.basename(previous)))
            continue

        # The Hub lists templates by "name", so keep those unique per repository.
        base_name = obj.get("name") or stem
        name = base_name
        if name in seen_names:
            name = "%s (%s)" % (base_name, stem)
            suffix = 2
            while name in seen_names:
                name = "%s (%s-%d)" % (base_name, stem, suffix)
                suffix += 1
        obj["name"] = name

        seen_stems.add(stem)
        seen_signatures[signature] = path
        seen_names[name] = path
        dest = os.path.join(docker_dir, stem + ".json")
        with open(dest, "w", encoding="utf-8") as fh:
            json.dump(obj, fh, indent=2, ensure_ascii=False)
            fh.write("\n")
        converted.append((path, dest))

    write_maintainer(out)

    for base in (src, os.path.dirname(os.path.normpath(src))):
        found = None
        for cand in ("LICENSE", "LICENSE.md", "LICENSE.txt", "License", "license", "COPYING"):
            candidate = os.path.join(base, cand)
            if os.path.isfile(candidate):
                found = candidate
                break
        if found:
            with open(found, encoding="utf-8") as s, open(os.path.join(out, "LICENSE"), "w", encoding="utf-8") as d:
                d.write(s.read())
            break

    print("converted : %d" % len(converted))
    print("skipped   : %d %s" % (len(skipped), [os.path.basename(p) for p, _ in skipped]))
    print("failed    : %d" % len(failed))
    for p, e in failed:
        print("   ! %s -> %s" % (p, e))
    print("output    : %s" % docker_dir)


if __name__ == "__main__":
    main(sys.argv)

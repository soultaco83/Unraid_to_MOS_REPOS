#!/usr/bin/env python3
"""
unraid_feed_to_mos.py - convert the aggregated unRAID Community Applications
feed (Squidly271/AppFeed) into MOS Hub Docker templates.

convert_sources.py converts the templates that live in a handful of *git
repositories*. The Community Applications plugin knows about far more than
those: its maintainer publishes the whole catalogue as two JSON dumps

    applicationFeed-raw.json   one object per template, carrying the flattened
                               <Container> XML (the Config rows included)
    applicationFeed.json       the framework around it (blacklisted/deprecated
                               images, categories, ...)

The feed is a superset of the git collections - the same template is often
mirrored into several CA repositories - so this module only publishes what the
git sources do not already cover. On top of that it can publish just a *hand
picked* part of the catalogue: a selection is a list of
`<app name>[@<maintainer repository>]` specs (the name CA displays plus the CA
repository it is listed under, both matched loosely - case and punctuation are
ignored). convert_sources.py keeps the curated list of apps this repository
should carry, `--app` narrows a standalone run down to a few apps, and without
any selection the whole catalogue is converted.

Inside the selection an entry is skipped when CA flags it (blacklisted /
deprecated / hidden), when it is a plugin or language pack rather than a
container (it has no image then), or when the container image is already
published by an earlier source. A container whose template carries no <Config>
rows is still published: those apps are configured through their parameters
alone, and the XML sources of tools/unraid_to_mos.py keep such templates as
well.

The converted objects have exactly the shape tools/unraid_to_mos.py emits, so
both converters share the MOS rewrite (--mos-paths / --mos-defaults) and the
merge step.

Usage:
    python3 unraid_feed_to_mos.py [FEED.json] [OUTPUT_DIR]
                                  [--meta applicationFeed.json] [--download DIR]
                                  [--refresh] [--skip-image IMAGE]...
                                  [--app APP]...

Selection:
    Without `--app` the whole catalogue is converted. `--app slskd@manrw`
    (repeatable) publishes only the entries whose name is `slskd` *and* whose CA
    repository title contains `manrw`, which is how one CA listing is picked
    when several repositories share an app name.

Defaults:
    FEED.json  = applicationFeed-raw.json downloaded into --download (./appfeed)
    OUTPUT_DIR = the current directory
"""
from __future__ import annotations

import argparse
import collections
import html
import json
import os
import re
import shutil
import sys
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import unraid_to_mos as conv  # noqa: E402

FEED_REPO = "Squidly271/AppFeed"
FEED_URL = "https://raw.githubusercontent.com/%s/master/applicationFeed-raw.json" % FEED_REPO
META_URL = "https://raw.githubusercontent.com/%s/master/applicationFeed.json" % FEED_REPO
USER_AGENT = "Unraid_to_MOS_REPOS (+https://github.com/soultaco83/Unraid_to_MOS_REPOS)"

# Cached feeds younger than this are reused instead of downloaded again. The CA
# maintainer refreshes the feed hourly, the repository itself daily.
FEED_MAX_AGE = 12 * 3600

# CA marks plugins and language packs with these fields; they have no container
# image and cannot become a MOS Hub docker template.
NON_DOCKER_FIELDS = ("Plugin", "PluginURL")

# CA appends its own plugin categories to the category list of a container
# (e.g. `Tools-Utilities` *and* `Plugins`). They carry no docker information.
SKIP_FEED_TOKENS = {"plugin", "plugins"}

# HTML that CA renders into free-form fields before publishing the feed.
BREAK_RE = re.compile(r"<\s*br\s*/?\s*>", re.IGNORECASE)
TAG_RE = re.compile(r"<[^>]*>")
SPACES_RE = re.compile(r"[ \t]+")


# --------------------------------------------------------------------------- #
# Feed helpers                                                                #
# --------------------------------------------------------------------------- #
def text(value):
    """Trim a feed value to a string or None, mirroring conv's attribute readers."""
    if value is None:
        return None
    if isinstance(value, str):
        value = value.strip()
    elif isinstance(value, (list, tuple)):
        value = " ".join(str(v).strip() for v in value).strip()
    else:
        value = str(value).strip()
    return value or None


def flag(value):
    """unRAID booleans are the strings "true"/"false" (see conv.bool_attr)."""
    return (text(value) or "").lower() == "true"


def image_key(ref):
    """Normalise a container reference for deduplication (tag/digest dropped)."""
    ref = text(ref) or ""
    ref = ref.lower().split("@", 1)[0]
    repo, _, tag = ref.rpartition("/")
    if ":" in tag:
        tag = tag.split(":", 1)[0]
    return ("%s/%s" % (repo, tag) if repo else tag).strip("/")


def repo_label(title):
    """Owner tag of a CA repository title ("KluthR's Repository" -> "KluthR")."""
    label = re.sub(r"\s+", " ", text(title) or "")
    label = re.sub(r"\s*\bRepositor(y|ies)\b\s*$", "", label, flags=re.IGNORECASE)
    label = re.sub(r"\s*\bRepo\b\s*$", "", label, flags=re.IGNORECASE)
    label = re.sub(r"['\u2019]s\s*$", "", label)
    return label.strip(" -\u2019'")


def owner(entry):
    """Short tag identifying the CA repository an entry came from."""
    label = repo_label(entry.get("Repo"))
    if label:
        return label
    parts = image_key(entry.get("Repository")).split("/")
    return parts[-2] if len(parts) > 2 else (parts[-1] or "Community Applications")


def normalize_token(value):
    """Fold a name or repository title to letters+digits for spec matching."""
    return "".join(ch for ch in (text(value) or "").lower() if ch.isalnum())


def app_spec(spec):
    """Split one `<app>[@<repository>]` spec into its two folded tokens."""
    name, _, repo = (text(spec) or "").partition("@")
    return normalize_token(name), normalize_token(repo)


def app_selector(specs):
    """Predicate that matches feed entries against `<app>[@<repository>]` specs.

    The app name has to match the name CA displays (case and punctuation are
    ignored, so `gitea-runner` finds `Gitea-Runner`). The optional repository
    part only has to *occur* in the CA repository title of the entry, which
    tells apart the CA listings that share an app name: `slskd@manrw` selects
    `manrw's Repository` and not `hotio's Repository`.

    Returns None when SPECS is empty (no selection - convert everything), so
    callers can test the result instead of keeping a second flag around.
    """
    wanted = [app_spec(spec) for spec in specs if text(spec)]
    if not wanted:
        return None

    def selected(entry):
        name = normalize_token(entry.get("Name"))
        title = normalize_token(entry.get("Repo"))
        return any(name == want_name and (not want_repo or want_repo in title)
                   for want_name, want_repo in wanted)

    return selected


def plain_text(value):
    """Undo the HTML CA renders into free-form fields (Requires, ...)."""
    if not value:
        return ""
    value = BREAK_RE.sub("\n", value if isinstance(value, str) else str(value))
    value = html.unescape(TAG_RE.sub("", value))
    lines = [SPACES_RE.sub(" ", line).strip() for line in value.splitlines()]
    return "\n".join(line for line in lines if line).strip()


# --------------------------------------------------------------------------- #
# Config rows                                                                 #
# --------------------------------------------------------------------------- #
def rows_of(entry):
    """Split the flattened <Config> rows into the MOS sections.

    The feed stores every row as {"@attributes": {...}, "value": "<body>"}; the
    schema is the one build_rows() reads from the original XML, so the field
    mapping below mirrors tools/unraid_to_mos.py row for row.
    """
    paths, ports, variables, devices, labels = [], [], [], [], []
    for row in entry.get("Config") or []:
        cfg = row.get("@attributes") or {}
        ctype = (text(cfg.get("Type")) or "")
        name = text(cfg.get("Name"))
        target = text(cfg.get("Target"))
        mode = text(cfg.get("Mode"))
        desc = cfg.get("Description") or ""
        required = flag(cfg.get("Required"))
        mask = flag(cfg.get("Mask"))
        display = text(cfg.get("Display")) or "always"
        display = conv.DISPLAY_MAP.get(display, display)
        # config_value(): the element body, falling back to the Default attribute
        value = text(row.get("value")) or text(cfg.get("Default"))

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


def categories_of(entry):
    """MOS categories of one feed entry.

    CA publishes nested categories hyphenated (`Tools-Utilities`), the XML spells
    them with a colon (`Tools:Utilities`); the colon form is what
    conv.parse_categories() expects. The token set is otherwise identical, so the
    feed and the XML sources of the same template agree on its categories.
    """
    tokens = [t for t in (entry.get("CategoryList") or [])
              if text(t) and text(t).lower() not in SKIP_FEED_TOKENS]
    raw = " ".join(t.replace("-", ":") for t in tokens)
    return [c for c in conv.parse_categories(raw) if c in conv.MOS_CATEGORIES] or ["Misc"]




# --------------------------------------------------------------------------- #
# Template conversion                                                         #
# --------------------------------------------------------------------------- #
def skip_reason(entry, meta, taken):
    """Why an entry is not published, or None when it is.

    `taken` holds the normalised images of everything that is already published
    (the git sources and the entries accepted before this one), so the feed only
    adds templates the repository does not carry yet.
    """
    image = image_key(entry.get("Repository"))
    if not image:
        return "no container image"
    if any(entry.get(field) for field in NON_DOCKER_FIELDS):
        return "plugin or language pack, not a container"
    if image in (meta.get("blacklisted") or {}):
        return "blacklisted by Community Applications"
    if image in (meta.get("deprecated") or {}):
        return "deprecated by Community Applications"
    if entry.get("Blacklist"):
        return "blacklisted by Community Applications"
    if entry.get("Deprecated") or entry.get("DeprecatedMaxVer"):
        return "deprecated by Community Applications"
    if entry.get("HideFromCA") or entry.get("hideFromCA"):
        return "hidden from Community Applications"
    if image in taken:
        return "image already published"
    stem = (text(entry.get("Name")) or "").lower().strip("_- ")
    if stem in conv.PLACEHOLDER_STEMS:
        return "placeholder template"
    haystack = " ".join(str(entry.get(field) or "") for field in
                        ("Name", "Repository", "CategoryList"))
    if any(marker in haystack for marker in conv.PLACEHOLDER_MARKERS):
        return "placeholder template"
    return None


def build_object(entry):
    """Convert one feed entry into a MOS Hub docker template object."""
    paths, ports, variables, devices, labels = rows_of(entry)

    icon = text(entry.get("Icon"))
    if icon and not icon.lower().startswith(("http://", "https://")):
        icon = None
    extra = text(entry.get("ExtraParams"))

    # NVIDIA pass-through: either --runtime=nvidia or an NVIDIA_VISIBLE_DEVICES
    # variable, exactly like the XML converter (unraid_to_mos.build_container_object).
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

    obj = {
        "name": text(entry.get("Name")),
        "repo": text(entry.get("Repository")),
        "category": categories_of(entry),
        "registry": text(entry.get("Registry")),
        "network": text(entry.get("Network")),
        "custom_ip": None,
        "default_shell": text(entry.get("Shell")),
        "privileged": flag(entry.get("Privileged")),
        "extra_parameters": extra,
        "post_parameters": text(entry.get("PostArgs")),
        "cpu_set": None,
        "web_ui_url": text(entry.get("WebUI")),
    }

    readme = text(entry.get("ReadMe")) or text(entry.get("Readme"))
    if readme:
        obj["readme_url"] = readme

    obj.update({
        "icon": icon,
        "project": text(entry.get("Project")),
        "support": text(entry.get("Support")),
        "description": text(entry.get("Overview")) or text(entry.get("Description")) or "",
    })

    # CA knows DonateURL/DonorLink where the XML template uses DonateLink.
    donate = text(entry.get("DonateURL")) or text(entry.get("DonorLink"))
    if donate:
        obj["donate"] = donate
    # CA renders this field as HTML (<br>, &nbsp;...) - the XML source is plain.
    requires = plain_text(entry.get("Requires"))
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


def display_name(entry):
    """`<name> (<owner>)` - the owner keeps same-named apps distinguishable."""
    name = text(entry.get("Name")) or image_key(entry.get("Repository"))
    label = owner(entry)
    return "%s (%s)" % (name, label) if label else name


def file_stem(entry):
    """File stem for one entry: the image repository name (ghcr.io/org/obico)."""
    stem = image_key(entry.get("Repository")).rpartition("/")[2]
    stem = re.sub(r"[^a-z0-9._-]+", "-", stem).strip("-.")
    return stem or re.sub(r"[^a-z0-9._-]+", "-", display_name(entry).lower()).strip("-.") or "template"


# --------------------------------------------------------------------------- #
# Feed I/O and conversion driver                                              #
# --------------------------------------------------------------------------- #
def load(path):
    """Read one feed JSON document."""
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def download(dest_dir, refresh=False, timeout=180):
    """Download feed + framework JSON into DEST_DIR and return both paths.

    A cached pair younger than FEED_MAX_AGE is reused, so repeated local runs do
    not re-download ~36 MB; the daily publish job always starts from a fresh
    checkout of the working directory and fetches anew.
    """
    os.makedirs(dest_dir, exist_ok=True)
    paths = []
    for url in (FEED_URL, META_URL):
        path = os.path.join(dest_dir, url.rsplit("/", 1)[-1])
        fresh = os.path.isfile(path) and time.time() - os.path.getmtime(path) < FEED_MAX_AGE
        if refresh or not fresh:
            request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(request, timeout=timeout) as response:
                payload = response.read()
            with open(path, "wb") as fh:
                fh.write(payload)
        paths.append(path)
    return paths[0], paths[1]


def convert(feed_path, meta_path, out_dir, skip_images=(), apps=None):
    """Convert FEED_PATH into OUT_DIR/docker/*.json (the MOS build layout).

    SKIP_IMAGES holds the normalised images that earlier sources already
    published; entries using one of them are counted as skipped. APPS is an
    optional `<app>[@<repository>]` selection (see app_selector); without it the
    whole catalogue is converted.
    """
    entries = load(feed_path)
    meta = load(meta_path)
    selected = app_selector(apps or ())

    docker_dir = os.path.join(out_dir, "docker")
    shutil.rmtree(docker_dir, ignore_errors=True)
    os.makedirs(docker_dir, exist_ok=True)

    taken = set(skip_images)
    used_files, used_names = {}, {}
    skipped = collections.Counter()
    written = matched = 0
    for entry in sorted(entries, key=lambda e: (text(e.get("Name")) or "").lower()):
        if selected is not None and not selected(entry):
            skipped["not part of the app selection"] += 1
            continue
        matched += 1
        reason = skip_reason(entry, meta, taken)
        if reason:
            skipped[reason] += 1
            continue
        obj = build_object(entry)

        # The Hub lists templates by "name", so keep those unique.
        base = display_name(entry)
        name = base
        suffix = 2
        while name.lower() in used_names:
            name = "%s-%d" % (base, suffix)
            suffix += 1
        obj["name"] = name

        # Credit the template author: CA records it per entry, the repository
        # owner is the fallback. The Hub shows the repository level maintainer
        # for docker templates, `author` keeps the provenance in the data.
        obj["author"] = text(entry.get("Author")) or owner(entry)

        stem = file_stem(entry)
        fname = stem + ".json"
        suffix = 2
        while fname.lower() in used_files:
            fname = "%s-%d.json" % (stem, suffix)
            suffix += 1

        used_names[name.lower()] = entry
        used_files[fname.lower()] = entry
        taken.add(image_key(entry.get("Repository")))
        with open(os.path.join(docker_dir, fname), "w", encoding="utf-8") as fh:
            json.dump(obj, fh, indent=2, ensure_ascii=False)
            fh.write("\n")
        written += 1

    return {"written": written, "skipped": skipped, "entries": len(entries),
            "matched": matched}


def report(stats, limit=6):
    """One summary line per skip reason (the feed is large, so keep it short)."""
    total = stats.get("matched", stats["entries"])
    print("converted : %d of %d entries" % (stats["written"], total))
    if stats.get("matched", stats["entries"]) != stats["entries"]:
        print("selected  : %d of %d entries match the app selection"
              % (stats["matched"], stats["entries"]))
    print("skipped   : %d" % sum(stats["skipped"].values()))
    for reason, count in stats["skipped"].most_common(limit):
        print("   - %5d  %s" % (count, reason))
    if len(stats["skipped"]) > limit:
        print("   - %5d  (other reasons)"
              % sum(c for _, c in stats["skipped"].most_common()[limit:]))


# --------------------------------------------------------------------------- #
# Standalone entry point (convert_sources.py drives convert())                #
# --------------------------------------------------------------------------- #
def main(argv):
    parser = argparse.ArgumentParser(
        description="Convert the Community Applications feed into MOS Hub docker templates."
    )
    parser.add_argument("feed", nargs="?",
                        help="applicationFeed-raw.json (default: download into --download)")
    parser.add_argument("out", nargs="?", default=".",
                        help="output directory (default: %(default)s)")
    parser.add_argument("--meta", help="applicationFeed.json (default: next to FEED)")
    parser.add_argument("--download", default="./appfeed",
                        help="cache directory for the downloaded feed (default: %(default)s)")
    parser.add_argument("--refresh", action="store_true",
                        help="ignore the cached feed and download it again")
    parser.add_argument("--skip-image", action="append", default=[], metavar="IMAGE",
                        help="never convert this container image (repeatable)")
    parser.add_argument("--app", action="append", default=[], metavar="APP",
                        help="only convert this Community Applications app, "
                             "spelled '<name>' or '<name>@<repository>' "
                             "(repeatable; default: the whole catalogue)")
    args = parser.parse_args(argv[1:])

    if args.feed:
        feed_path = args.feed
        meta_path = args.meta or os.path.join(
            os.path.dirname(os.path.abspath(feed_path)), "applicationFeed.json")
    else:
        feed_path, meta_path = download(args.download, refresh=args.refresh)

    os.makedirs(args.out, exist_ok=True)
    stats = convert(feed_path, meta_path, args.out,
                    skip_images={image_key(i) for i in args.skip_image},
                    apps=args.app)
    report(stats)
    print("output    : %s" % os.path.join(args.out, "docker"))


if __name__ == "__main__":
    main(sys.argv)

#!/usr/bin/env python3
"""
trending_apps.py - accumulate ca.unraid.net's top-trending Docker apps.

The Community Applications web site sorts the whole catalogue by a "trending"
score (https://ca.unraid.net/apps?category=all&sortBy=trending). That page is a
Nuxt SPA that renders results from a plain JSON search API:

    GET https://ca.unraid.net/api/search?view=summary&type=docker&sortBy=trending

which returns an Algolia-style object whose `hits` array is already in the exact
order the page displays. Every hit carries the CA display `Name` and the CA
repository title `Repo`, which together form the `<name>@<repository>` spec that
unraid_feed_to_mos.py understands.

The selection is accumulated (append-only): each run takes the top N apps and
unions them into a persistent JSON state file, so an app that was trending last
week but is not today is KEPT - it only leaves the repository when Community
Applications itself removes it, never because it dropped out of the top N.
"""

from __future__ import annotations

import json
import os
import urllib.request

TRENDING_URL = ("https://ca.unraid.net/api/search"
                "?view=summary&type=docker&sortBy=trending")
USER_AGENT = "Unraid_to_MOS_REPOS (+https://github.com/soultaco83/Unraid_to_MOS_REPOS)"

# Every app the accumulator has ever picked up, in the order it was added. The
# file lives next to convert_sources.py (tools/) and is committed with the
# repository, which is what makes the accumulation survive between runs.
DEFAULT_STATE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             "trending_apps.json")


def fetch_trending(limit=10, timeout=60):
    """Return up to `limit` ``Name@Repo`` specs from the trending API, in order.

    Deprecated and non-docker hits are skipped, and duplicates (the API can list
    the same app more than once - a live record and a deprecated one share a
    name/repo) are collapsed to their first occurrence, so an otherwise
    deprecated app cannot smuggle a second, non-deprecated record through.
    """
    request = urllib.request.Request(TRENDING_URL, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        data = json.load(response)

    # Deduplicate first, keeping the first record per app (dicts are ordered).
    first_seen = {}
    for hit in data.get("hits") or []:
        if (hit.get("appType") or "").strip().lower() != "docker":
            continue
        name = (hit.get("Name") or "").strip()
        repo = (hit.get("Repo") or "").strip()
        if not name or not repo:
            continue
        first_seen.setdefault(("%s@%s" % (name, repo)).strip().lower(), hit)

    specs = []
    for hit in first_seen.values():
        if hit.get("deprecated") or hit.get("Deprecated"):
            continue
        specs.append("%s@%s" % ((hit.get("Name") or "").strip(),
                                (hit.get("Repo") or "").strip()))
        if len(specs) >= limit:
            break
    return specs


def load_state(path=DEFAULT_STATE):
    """Return the accumulated app list (empty when there is no state yet)."""
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        return list(data.get("apps") or [])
    except (OSError, ValueError):
        return []


def accumulate(path, specs):
    """Union `specs` into the persistent state and return the full list.

    The state file is only rewritten when a new app is added, so a run that
    finds nothing new leaves the repository byte-identical (no commit churn).
    """
    existing = load_state(path)
    seen = {s.strip().lower() for s in existing}
    added = [s for s in specs if s.strip().lower() not in seen]
    if not added:
        return existing

    combined = existing + added
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({"apps": combined}, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    return combined


def union(*lists):
    """Concatenate lists of specs, dropping case-insensitive duplicates."""
    out, seen = [], set()
    for lst in lists:
        for spec in lst or []:
            key = str(spec).strip().lower()
            if key and key not in seen:
                seen.add(key)
                out.append(spec)
    return out

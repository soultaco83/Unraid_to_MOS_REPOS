# Unraid to MOS - template repository

A single flat [MOS Hub](https://github.com/mos-nas/mos-docs/blob/main/docs/MOS-Hub/Creating-Your-Own-MOS-Hub-Repository.md) repository
holding docker templates converted from **5** unRAID Community Applications
template repositories: **300 templates** from 5 upstream authors.

`maintainer.json` and `docker/<App>.json` sit at the repository root, which is
the only layout the MOS Hub indexes. Author provenance is preserved in every
template (`author`, `project`, `support`, `registry`, `donate`) and in the
table below; templates whose file/display name would clash with another
author's carry a source prefix.

## Add it to MOS Hub

1. Open **Settings -> System Configuration -> MOS Hub Settings**.
2. Add this repository URL:

   ```
   https://github.com/soultaco83/Unraid_to_MOS_REPOS
   ```

3. Click **Refresh**, then open the **Docker** tab.

### Add the repository root, not a folder link

The Hub runs `git clone` on every URL of its repository list and then reads
`maintainer.json`, `docker/`, `compose/` and `plugins/` **at the root of the
cloned repository**; it never descends into sub-directories. Folder links such
as `.../Unraid_to_MOS_REPOS/tree/main/binhex` are not git repositories, so the
Hub logs `Hub: Skipping .../tree/main/binhex - not a valid git repository` and
indexes nothing for that entry. Remove folder links, keep only the repository
URL above, then Refresh.

The log line `Hub: Could not fetch known repositories: ... 404` comes from
`https://mos-official.net/known-repos.json`, which currently returns 404; the
Hub retries hourly and it only affects the suggested-repository list of the
Hub dialog, not the templates of a configured repository.

### The maintainer label is repository level

Every docker template of a repository is labelled with the `maintainer` value
from that repository's `maintainer.json` (Hub source `src/services/
hub.service.js`, `_processDockerTemplate()`; unlike plugin templates, docker
templates have no per-template `author` fallback). Because the Hub only reads
the repository root, one flat repository cannot show per-author labels: all
300 templates below carry the hosting account as maintainer.
Showing the original author as the label would need one repository per author,
added to the Hub as several repository URLs.

The upstream author is still identifiable per template: in the install dialog
through `project`, `support` and `donate`, in the template JSON through
`author`, and in the source table below.

## Layout

```
maintainer.json      repository metadata (maintainer: Soultaco83)
docker/<App>.json    one template per container (300 total)
licenses/            upstream licence text, where the author published one
tools/               conversion + publish scripts (not part of the Hub payload)
```

Only Docker (`<Container>`) templates are converted; unRAID plugins and
multi-container stacks are excluded. Icons are referenced from the upstream
repositories, so they always match what the author currently ships.

## MOS compatibility

unRAID specifics were replaced by the MOS equivalents:

* host paths: `/mnt/user/appdata/...` -> `/mnt/cache/appdata/...`, every other
  `/mnt/user/...` share -> `/mnt/Array/...` (MOS keeps data directly in a
  pool instead of aggregating shares below `/mnt/user`); the same
  applies to `/mnt/user/...` inside template text (descriptions,
  `requires`, extra parameters) and to variable defaults. Folders and
  files that exist on unRAID only (dynamix webUI, unRAID VM manager,
  `/etc/unraid-version`) are dropped. Container side mount targets stay
  untouched - they are what the application expects inside the
  container, not a host path
* identity: `PUID`/`PGID` and every `UID`/`GID` spelling
  (`UID`, `GID`, `USER_ID`, `GROUP_ID`, `<APP>_UID`, ...) default to
  `500`/`500` instead of unRAID's 99/100, `--user 99:100` became
  `--user 500:500`, dynamix label prefixes (`Variable: `, `Path: `, ...)
  removed

Icons, ports, variables and `br0` network modes were kept as they are: MOS
supports them (`br0` is the bridge used by VMs and containers). The paths
follow the pool names of the host that generated this repository
(`/mnt/cache/appdata`, `/mnt/Array`) - re-run the conversion with
`--appdata-root` / `--array-root` for differently named pools.

## Sources

| Source | Maintainer | Templates | Upstream | Licence |
|---|---|---:|---|---|
| `binhex` | binhex | 65 | [binhex/docker-templates](https://github.com/binhex/docker-templates) | [kept](./licenses/binhex.txt) |
| `hotio` | hotio | 27 | [hotio/unraid-templates](https://github.com/hotio/unraid-templates) | [kept](./licenses/hotio.txt) |
| `ibracorp` | IBRACORP | 55 | [ibracorp/unraid-templates](https://github.com/ibracorp/unraid-templates) | [kept](./licenses/ibracorp.txt) |
| `selfhosters` | selfhosters | 128 | [selfhosters/unRAID-CA-templates](https://github.com/selfhosters/unRAID-CA-templates) | [kept](./licenses/selfhosters.txt) |
| `spaceinvaderone` | SpaceinvaderOne | 25 | [SpaceinvaderOne/Docker-Templates-Unraid](https://github.com/SpaceinvaderOne/Docker-Templates-Unraid) | not published |

Generated with `tools/convert_sources.py --mos-paths --mos-defaults`, validated with
`tools/validate_repos.py`, committed with `tools/publish_repo.fish` and pushed
with `tools/create_and_push.fish`.

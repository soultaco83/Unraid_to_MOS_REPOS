# Unraid to MOS - template repository

A single flat [MOS Hub](https://github.com/mos-nas/mos-docs/blob/main/docs/MOS-Hub/Creating-Your-Own-MOS-Hub-Repository.md) repository
holding **393 templates**: **379** from 4 dedicated author repositories
plus **14** apps taken from the
[Community Applications feed](https://github.com/Squidly271/AppFeed).
That feed is the catalogue of the whole unRAID community, so the
repository only carries the apps listed in `FEED_APPS`
(`tools/convert_sources.py`). Every feed template keeps the owner tag
of its CA repository (`obico (imagegenius)`) and is only published when
the git repositories do not cover its image already.

`maintainer.json` and `docker/<App>.json` sit at the repository root, which is
the only layout the MOS Hub indexes. Author provenance is preserved in every
template (`author`, `project`, `support`, `registry`, `donate`) and in the
table below; every display name carries its owner:
`jellyfin (hotio)`, `jellyfin (linuxserver)`, `... (SIO)` for
SpaceinvaderOne, `obico (imagegenius)` for the feed.

## Add it to MOS Hub

1. Click **MOS Hub** in the left sidebar.
2. Click the three dots in the bottom right, then **+ repositories**.
3. Add the repository URL:

   ```
   https://github.com/soultaco83/Unraid_to_MOS_REPOS
   ```

4. Click the three dots in the bottom right again and choose **Refresh**.

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
| `appfeed` | Community Applications | 14 | [Squidly271/AppFeed](https://github.com/Squidly271/AppFeed) | not published |
| `hotio` | hotio | 27 | [hotio/unraid-templates](https://github.com/hotio/unraid-templates) | [kept](./licenses/hotio.txt) |
| `linuxserver` | linuxserver | 199 | [linuxserver/templates](https://github.com/linuxserver/templates) | [kept](./licenses/linuxserver.txt) |
| `selfhosters` | selfhosters | 128 | [selfhosters/unRAID-CA-templates](https://github.com/selfhosters/unRAID-CA-templates) | [kept](./licenses/selfhosters.txt) |
| `spaceinvaderone` | SpaceinvaderOne | 25 | [SpaceinvaderOne/Docker-Templates-Unraid](https://github.com/SpaceinvaderOne/Docker-Templates-Unraid) | not published |

The `appfeed` source is curated: `FEED_APPS` in `tools/convert_sources.py`
holds the apps (`<name>@<repository>`) converted from the feed,
`--feed-app NAME[@REPO]` replaces that list for one run and `--feed-all`
converts the whole catalogue.

Generated with `tools/convert_sources.py --mos-paths --mos-defaults`, validated with
`tools/validate_repos.py`, committed with `tools/publish_repo.fish` and pushed
with `tools/create_and_push.fish`.

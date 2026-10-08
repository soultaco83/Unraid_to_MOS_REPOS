# Unraid to MOS - template repository

A single flat [MOS Hub](https://github.com/mos-nas/mos-docs/blob/main/docs/MOS-Hub/Creating-Your-Own-MOS-Hub-Repository.md) repository
holding docker templates converted from **4** unRAID Community Applications
template repositories: **378 templates** from 4 upstream authors.

`maintainer.json` and `docker/<App>.json` sit at the repository root, which is
the only layout the MOS Hub indexes. Author provenance is preserved in every
template (`author`, `project`, `support`, `registry`, `donate`) and in the
table below; templates whose file/display name would clash with another
author's carry a source prefix.

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
| `hotio` | hotio | 27 | [hotio/unraid-templates](https://github.com/hotio/unraid-templates) | [kept](./licenses/hotio.txt) |
| `linuxserver` | linuxserver | 198 | [linuxserver/templates](https://github.com/linuxserver/templates) | [kept](./licenses/linuxserver.txt) |
| `selfhosters` | selfhosters | 128 | [selfhosters/unRAID-CA-templates](https://github.com/selfhosters/unRAID-CA-templates) | [kept](./licenses/selfhosters.txt) |
| `spaceinvaderone` | SpaceinvaderOne | 25 | [SpaceinvaderOne/Docker-Templates-Unraid](https://github.com/SpaceinvaderOne/Docker-Templates-Unraid) | not published |

Generated with `tools/convert_sources.py --mos-paths --mos-defaults`, validated with
`tools/validate_repos.py`, committed with `tools/publish_repo.fish` and pushed
with `tools/create_and_push.fish`.

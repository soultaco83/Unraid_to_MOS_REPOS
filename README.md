# Unraid to MOS - template repository

A single flat [MOS Hub](https://github.com/ich777/mos-templates) repository
holding docker templates converted from **14** unRAID Community Applications
template repositories: **1026 templates** from 14 upstream authors.

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
1026 templates below carry the hosting account as maintainer.
Showing the original author as the label would need one repository per author,
added to the Hub as several repository URLs.

The upstream author is still identifiable per template: in the install dialog
through `project`, `support` and `donate`, in the template JSON through
`author`, and in the source table below.

## Layout

```
maintainer.json      repository metadata (maintainer: Soultaco83)
docker/<App>.json    one template per container (1026 total)
licenses/            upstream licence text, where the author published one
tools/               conversion + publish scripts (not part of the Hub payload)
```

Only Docker (`<Container>`) templates are converted; unRAID plugins and
multi-container stacks are excluded. Icons are referenced from the upstream
repositories, so they always match what the author currently ships.

## Sources

| Source | Maintainer | Templates | Upstream | Licence |
|---|---|---:|---|---|
| `binhex` | binhex | 65 | [binhex/docker-templates](https://github.com/binhex/docker-templates) | [kept](./licenses/binhex.txt) |
| `devzwf` | devzwf | 47 | [devzwf/unraid-docker-templates](https://github.com/devzwf/unraid-docker-templates) | [kept](./licenses/devzwf.txt) |
| `digiblur` | digiblur | 25 | [digiblur/unraid-docker-templates](https://github.com/digiblur/unraid-docker-templates) | not published |
| `eurotimmy` | Eurotimmy | 8 | [Eurotimmy/unraid-templates](https://github.com/Eurotimmy/unraid-templates) | not published |
| `hotio` | hotio | 27 | [hotio/unraid-templates](https://github.com/hotio/unraid-templates) | [kept](./licenses/hotio.txt) |
| `ibracorp` | IBRACORP | 55 | [ibracorp/unraid-templates](https://github.com/ibracorp/unraid-templates) | [kept](./licenses/ibracorp.txt) |
| `ich777` | ich777 | 146 | [ich777/docker-templates](https://github.com/ich777/docker-templates) | not published |
| `nasutils` | NasUtils | 8 | [NasUtils/unraid-docker-templates](https://github.com/NasUtils/unraid-docker-templates) | [kept](./licenses/nasutils.txt) |
| `nwithan8` | nwithan8 | 544 | [nwithan8/unraid_templates](https://github.com/nwithan8/unraid_templates) | not published |
| `p3terx` | P3TERX | 2 | [P3TERX/unraid-docker-templates](https://github.com/P3TERX/unraid-docker-templates) | [kept](./licenses/p3terx.txt) |
| `randomninjaatk` | RandomNinjaAtk | 3 | [RandomNinjaAtk/unraid-templates](https://github.com/RandomNinjaAtk/unraid-templates) | [kept](./licenses/randomninjaatk.txt) |
| `spaceinvaderone` | SpaceinvaderOne | 25 | [SpaceinvaderOne/Docker-Templates-Unraid](https://github.com/SpaceinvaderOne/Docker-Templates-Unraid) | not published |
| `unraid` | Lime Technology | 1 | [unraid/docker-templates](https://github.com/unraid/docker-templates) | [kept](./licenses/unraid.txt) |
| `xushier` | xushier | 70 | [xushier/Unraid-Docker-Templates](https://github.com/xushier/Unraid-Docker-Templates) | not published |

Generated with `tools/convert_sources.py`, validated with
`tools/validate_repos.py`, committed with `tools/publish_repo.fish` and pushed
with `tools/create_and_push.fish`.

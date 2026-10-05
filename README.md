# Unraid to MOS - template repository

A single GitHub repository that bundles **one self-contained MOS Hub repository
per upstream author**. Each folder below has its own `maintainer.json`, `docker/`
and `images/`, so the original author of every template set stays clearly
separated while the whole collection is added to MOS Hub as **one repository URL**.

Converted from well-known unRAID Community Applications template repositories.
Only Docker (`<Container>`) templates are converted; unRAID plugins and
multi-container stacks are excluded.

| Folder | Maintainer | Templates | Upstream |
|---|---|---:|---|
| [unraid](./unraid) | Lime Technology | 1 | [unraid/docker-templates](https://github.com/unraid/docker-templates) |
| [binhex](./binhex) | binhex | 65 | [binhex/docker-templates](https://github.com/binhex/docker-templates) |
| [ich777](./ich777) | ich777 | 146 | [ich777/docker-templates](https://github.com/ich777/docker-templates) |
| [nwithan8](./nwithan8) | nwithan8 | 544 | [nwithan8/unraid_templates](https://github.com/nwithan8/unraid_templates) |
| [xushier](./xushier) | xushier | 70 | [xushier/Unraid-Docker-Templates](https://github.com/xushier/Unraid-Docker-Templates) |
| [ibracorp](./ibracorp) | IBRACORP | 55 | [ibracorp/unraid-templates](https://github.com/ibracorp/unraid-templates) |
| [devzwf](./devzwf) | devzwf | 47 | [devzwf/unraid-docker-templates](https://github.com/devzwf/unraid-docker-templates) |
| [hotio](./hotio) | hotio | 27 | [hotio/unraid-templates](https://github.com/hotio/unraid-templates) |
| [digiblur](./digiblur) | digiblur | 25 | [digiblur/unraid-docker-templates](https://github.com/digiblur/unraid-docker-templates) |
| [spaceinvaderone](./spaceinvaderone) | SpaceinvaderOne | 25 | [SpaceinvaderOne/Docker-Templates-Unraid](https://github.com/SpaceinvaderOne/Docker-Templates-Unraid) |
| [eurotimmy](./eurotimmy) | Eurotimmy | 8 | [Eurotimmy/unraid-templates](https://github.com/Eurotimmy/unraid-templates) |
| [nasutils](./nasutils) | NasUtils | 8 | [NasUtils/unraid-docker-templates](https://github.com/NasUtils/unraid-docker-templates) |
| [randomninjaatk](./randomninjaatk) | RandomNinjaAtk | 3 | [RandomNinjaAtk/unraid-templates](https://github.com/RandomNinjaAtk/unraid-templates) |
| [p3terx](./p3terx) | P3TERX | 2 | [P3TERX/unraid-docker-templates](https://github.com/P3TERX/unraid-docker-templates) |

Generated with `tools/convert_sources.py`, committed with `tools/publish_repo.fish` and pushed with `tools/create_and_push.fish`.

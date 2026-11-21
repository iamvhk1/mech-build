# mech-royale-bot

Autonomous bot for the Mech Royale `mechfight/1` battle royale.

- Rules and protocol: [docs/protocol.md](docs/protocol.md)
- Plan and roadmap: [docs/implementation_plan.md](docs/implementation_plan.md)
- Original kit README: [docs/kit_README.md](docs/kit_README.md)

## Layout

| Path | Purpose |
| --- | --- |
| `Dockerfile` | Submission image (must stay at the top level). |
| `mechfight.py` | Kit protocol wrapper. |
| `example_bot.py` | Kit example bot; current entrypoint until `bot.py` lands. |
| `core/` | C++ core (`libmech_core.so`), Phase 1. |
| `arena/` | Map files for local runs (`/arena` is mounted in matches). |
| `check/` | Kit conformance check. |
| `mechfight.schema.json` | Message schema (used by `check/check.py`). |

## Check locally

```sh
python3 check/check.py -- python3 -u example_bot.py
docker build -t my-bot .
python3 check/check.py --map-dir /arena -- docker run --rm -i --network none --cpus 1 --memory 512m --read-only --tmpfs /tmp:rw,size=64m --user 65534:65534 -v "$PWD/arena:/arena:ro" my-bot
```

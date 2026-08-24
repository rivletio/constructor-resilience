# constructor-resilience

Turn a long session into a handful of **durable claims** (*atoms*) and a small **packet** you can resume from or hand to another agent.

You don’t share the transcript. You share what you chose to keep.

| Word | Meaning |
|------|---------|
| **Atom** | One stand-alone claim worth injecting later |
| **Packet** | A small, non-redundant set of atoms for this topic |
| **Topic** | A named collection of atoms |
| **Share** | An intentional file (`share.json`) — never ambient |
| **Mention / ref** | A name or citation attached to a claim, not a second graph |

## Install (skill)

```bash
npx skills add rivletio/constructor-resilience-skill
```

Then tell the agent: *pack this session*.

Or clone [`constructor-resilience-skill`](https://github.com/rivletio/constructor-resilience-skill) and run `./install.sh` (links the skill and puts `coherence` on PATH). If `coherence` is missing, `bin/coherence` next to `SKILL.md` installs it.

## Install (Python)

```bash
pip install -e ".[dev]"
# optional graph PNG:  pip install -e ".[viz]"
```

Store: `$COHERENCE_ROOT` or `$PWD/.coherence`.

## Quick start

```bash
coherence pack --title "My AI interests" --constraint fact \
  --atom "JEPA predicts in latent space rather than tokens." \
  --mention "JEPA:concept" \
  --atom "Packets are the share unit, not transcripts." \
  --mention "packet:concept"
coherence share --to alice --audience circle
```

JSON file still works (`--json claims.json`) when you need mentions/refs on each claim.

Wire format: [SPEC.md](./SPEC.md). Human walkthrough: [docs/USER_MANUAL.md](./docs/USER_MANUAL.md).

### Optional: local MLX (Apple Silicon)

```bash
coherence ensure-model
coherence mint --file ./notes.md --theme "world models" --ensure-model --auto-score
coherence critique --source-file ./notes.md --apply
coherence review --serve --browser   # http://127.0.0.1:8765; omit --browser to avoid opening Chrome
coherence reject 3 --reason "claimed impossibility does not hold"
coherence eval --query "What is JEPA?" --ensure-model
```

### Overlap with someone else’s surface

```bash
coherence import ./their-atoms.json --title "Lex public" --use
coherence intersect my-ai-interests lex-public --query consciousness --max-size 8
coherence union my-ai-interests lex-public --out /tmp/union.json
coherence check --packet /tmp/union.json
```

### Library

```python
from coherence_cache.search import greedy_resilient
from coherence_cache.intersection import intersection_packet

selected, energy = greedy_resilient(atoms, consistency, max_size=6)
packet = intersection_packet(my_store, their_store, max_size=8, seed_query="AI")
```

## Layout

```
$COHERENCE_ROOT/          # default: ./.coherence
  meta.json
  active.json
  topics/<id>/
    atoms.json
    packet.json
    share.json            # after `coherence share`
```

Packet search: greedy for `pack`; Monte Carlo via `coherence search --method sa-sweep|sa-geo|metropolis`.  
Energy model: [docs/qubo-formulation.md](./docs/qubo-formulation.md). Host contract: [docs/HOSTS.md](./docs/HOSTS.md).

## Hosts

The **CLI** is the reference. The **agent skill** is the usual install:
[`constructor-resilience-skill`](https://github.com/rivletio/constructor-resilience-skill).
Circle policy belongs to the host; this repo is the method.

## License

[AGPL-3.0-or-later](./LICENSE) — GNU Affero General Public License v3 or later.

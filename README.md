# Astrolabe

**Your agent doesn't need your whole archive. It needs a map.**

[![tests](https://github.com/xiaozhanglbz/astrolabe-index/actions/workflows/tests.yml/badge.svg)](https://github.com/xiaozhanglbz/astrolabe-index/actions/workflows/tests.yml)
![python](https://img.shields.io/badge/python-3.10%2B-blue)
![dependencies](https://img.shields.io/badge/dependencies-0-brightgreen)
![license](https://img.shields.io/badge/license-MIT-green)

Astrolabe builds a tiny, hierarchical, **read-only** index over a folder of
notes, drafts, exports or half-forgotten projects, so an AI agent can navigate
to the one file it needs instead of loading all of them into context.

Three levels: **volume → chapter → page**. A few kilobytes of JSON. No server,
no database, no embeddings, no API key — Python 3.10+ and the standard library.

---

## The problem

You point an agent at a directory with 800 files in it. It has two bad options.

**Load everything.** The context window fills with file listings, the actual
question gets buried in the middle, and you pay for every token of it.

**Search blindly.** `ls`, `grep`, `find` — the agent guesses at filenames,
misses the folder named `2024-备份-最终版`, and eventually asks you where the
file is. Which is the thing you were trying to avoid.

What the agent actually needs is not the archive. It is **a map of the archive**.

## The idea

Astrolabe walks the folder once and writes a small catalogue that describes
*where things live*, not *what they say*:

- **Volume** — a family of related material (a project, a client, a year),
  with page count, size, keywords and a "heat" hint (hot / warm / cold).
- **Chapter** — a sub-area inside a volume, with one entry path.
- **Page** — an actual file, reachable by path.

The agent reads the catalogue (a few KB), picks a volume, reads that volume's
file (a few KB more), then opens exactly the pages it needs. Three small reads
instead of one enormous one.

Nothing in your folder is touched. The index lives in `_index/`, is generated
data, and can be deleted at any moment — rebuilding it is a full rescan that
takes well under a second for a normal archive.

## What makes it different

**vs. grep / glob / find** — those only work when you already know the name.
Astrolabe gives the agent a description of the terrain first, so it can decide
*where* to look before it starts matching strings.

**vs. RAG / vector databases** — those need chunking, an embedding model, a
vector store and a retriever, and they answer "which passage is similar to this
question". Astrolabe answers "which file should I open". It is a navigation
layer, not a retrieval layer — and it runs in 0.2 seconds with no model at all.

**vs. wiki generators** — those rewrite your material into a new knowledge
base. Astrolabe never rewrites anything. Your archive stays exactly as it is,
byte for byte.

**vs. memory tools** — those manage what an agent *remembers*. Astrolabe
manages what an agent can *find*. Different problem, different file.

## Quick start

Thirty seconds, no install:

```bash
git clone https://github.com/xiaozhanglbz/astrolabe-index
cd astrolabe-index

# 1. make a synthetic archive to play with
python3 examples/make_demo.py /tmp/demo-archive

# 2. build the index
python3 -m astrolabe build /tmp/demo-archive --split-threshold 30

# 3. verify it against the filesystem
python3 -m astrolabe check /tmp/demo-archive

# 4. look at the size
python3 -m astrolabe stats /tmp/demo-archive
```

Then point it at something real:

```bash
python3 -m astrolabe build ~/Documents/old-projects
```

## Install

Requires Python 3.10 or newer. No dependencies.

```bash
# Option A — clone and run, nothing installed
git clone https://github.com/xiaozhanglbz/astrolabe-index
cd astrolabe-index
python3 -m astrolabe --version

# Option B — install the `astrolabe` command
pip install -e .

# Option C — isolated CLI install
pipx install .
```

## Use

```bash
# build or rebuild the index (writes <dir>/_index/, touches nothing else)
astrolabe build ~/archive

# tune it for a folder with very large subdirectories
astrolabe build ~/archive --split-threshold 50

# verify the index still matches the filesystem (read-only; exit 1 on drift)
astrolabe check ~/archive

# report index size and bytes-per-page
astrolabe stats ~/archive

# print the catalogue as JSON instead of a summary
astrolabe build ~/archive --json
```

All three subcommands accept the same options, so `build`, `check` and `stats`
always talk about the same index.

## Load it into your agent

The catalogue is plain JSON, so any agent that can read a file can use it. Four
ways to wire it up, from lightest to most integrated.

### 1. Claude Code — as an Agent Skill

```bash
mkdir -p ~/.claude/skills/archive-index
cp SKILL.md ~/.claude/skills/archive-index/SKILL.md
```

Or per project: `.claude/skills/archive-index/SKILL.md`. Claude Code will pick it
up automatically and use it when it sees a folder full of old files.

### 2. Codex CLI / anything that reads `AGENTS.md`

Append this to your `AGENTS.md`:

```markdown
## Locating files in large folders
This repo contains archives indexed by Astrolabe.
Before searching, read `_index/00_catalog.json`, then the volume file it points
to, then open the page paths. Never load a whole archive into context.
If the index looks stale, run `astrolabe check <dir>`; rebuild with
`astrolabe build <dir>`.
```

### 3. Cursor — as a project rule

Save the same block as `.cursor/rules/astrolabe.mdc` (or add it to
`.cursorrules`). Same instructions, same effect.

### 4. Any agent — paste this into the system prompt

```text
When a directory has more than ~50 files and you need to find something in it,
look for an `_index/00_catalog.json` first.

If it exists: read it (it is a few KB). Pick a volume from `volume_list`, read
that volume's `file`, then open the `entry` paths of the chapters you need.
Check `_index/gaps.json` before claiming a file is missing.

If it does not exist and the folder matters: run
`python3 -m astrolabe build <dir>` once, then follow the same steps.
```

That block is the whole protocol. Everything else is convenience.

### 5. Python

```python
from pathlib import Path
from astrolabe.core import Config, build

result = build(Config(root=Path("~/archive").expanduser()))
print(result["master"]["volumes"], result["master"]["total_pages"])
```

## What you get

```
archive/
├── project-a_20250615/          ← your files, untouched
├── project-b_2024/
└── _index/                      ← generated, safe to delete
    ├── 00_catalog.json          ← read this first (a few KB)
    ├── 01_project-a.json        ← one file per volume
    ├── 02_project-b.json
    └── gaps.json                ← files that were skipped, and why
```

`00_catalog.json`, abridged:

```json
{
  "about": "Hierarchical, read-only index. Search order: ...",
  "volumes": 2,
  "total_pages": 338,
  "how_to_search": ["Volume level: ...", "Chapter level: ...", "Page level: ..."],
  "volume_list": [
    {
      "volume": "project-a",
      "file": "_index/01_project-a.json",
      "pages": 338,
      "chapters": 8,
      "size": "4.2M",
      "keywords": ["mockup", "wireframes", "checkout", "20250615"],
      "updated": "2026-08-20",
      "heat": "hot",
      "entry": ["project-a_20250615/", "project-a_20250820/"]
    }
  ]
}
```

Each volume file lists its chapters with `entry` paths, plus either
`page_list` (small chapter) or `sample_pages` + `page_distribution` (large
chapter — list the directory to see everything).

## How an agent should read it

1. Read `_index/00_catalog.json`; pick a volume from `volume_list`.
2. Read that volume's `file`; each `chapter_list` item has an `entry` path.
3. Open pages under the entry path. When `page_distribution` is present, list
   the directory to see the full contents.
4. Check `_index/gaps.json` before reporting that a file is missing.

That is it. Four steps, three small reads, one answer.

## Options

| flag | default | meaning |
|---|---|---|
| `-o, --out` | `_index` | index directory name |
| `--split-threshold` | `200` | a chapter with more pages than this is split one level deeper |
| `--list-threshold` | `20` | chapters up to this size list every page name; larger ones get a sample |

Grouping is controlled by `Config.group_patterns` (dated copies such as
`proj_20250615` and `proj_2024` collapse into one volume) and by `skip_ext` /
`skip_dirs` in `astrolabe/core.py`.

## Performance

Measured on a synthetic archive, single run, no caching:

| pages | build time | index size | peak memory |
|---|---|---|---|
| 5,000 | 0.25 s | 216 KB | ~15 MB |
| 20,000 | 0.82 s | 619 KB | ~16 MB |

That is 32–44 bytes per page, depending on how long the paths are. Small
archives carry a fixed overhead — the 73-page demo reports about 120 bytes per
page — but at scale the per-page cost settles in the low tens of bytes. A
20,000-page archive produces well under a megabyte of JSON in total.

There is no incremental mode: every build is a full rescan. At these speeds a
full rebuild is cheaper than maintaining a cache, and it means the index can
never silently disagree with the disk.

## Limits

- **Read-only.** Source files are never moved, edited or deleted.
- **Not a search engine.** It indexes locations, not content. Pair it with
  full-text or semantic search if you need passage-level retrieval.
- **Filenames are the primary signal.** Meaningful names give a useful index;
  a folder of `untitled-3.md` will not.
- **Full rebuild every run.** Fine up to tens of thousands of files; not
  designed for a million-file cold storage drive.
- **One folder, one index.** Nested indexes are not merged automatically.

## FAQ

**Does it modify or move my files?**
No. It only creates `_index/` next to them. Delete that folder and your archive
is exactly as it was.

**Does it need an API key, a GPU, or a model?**
No. Standard library only. It runs offline.

**Can it index PDFs, images, archives?**
It records their names and paths; it does not read their contents. Anything it
skips is listed in `gaps.json` so the agent knows the difference between "not
there" and "not indexed".

**What does `heat` mean?**
A hint from modification times: `hot` < 30 days, `warm` < 180, `cold` beyond.
Useful for "what was I working on recently" questions.

**Should I commit `_index/`?**
Either way works. Commit it if you want agents to have the map without running
anything; ignore it if you prefer a clean tree. It is regenerable data.

**How is this different from just using `tree`?**
`tree` gives you every path, flat, with no notion of families, no keywords, no
size, no freshness, and no three-level zoom. On 800 files that is already too
much to read; on 20,000 it is useless.

**Why "Astrolabe"?**
An astrolabe does not move the stars. It tells you where they are.

## Related work

- **Wiki generators** rewrite your material into a new knowledge base.
- **Memory trees** restructure what an agent already remembers.
- **Markdown + vector indexes** retrieve passages by similarity.
- **Astrolabe** gives an agent a read-only map of an archive it has never seen,
  and changes nothing.

Adjacent, not competing. If you need knowledge growth, use those. If you need
archaeology, use this.

## Development

```bash
python3 -m unittest discover -s tests -v     # 25 tests, stdlib only
```

Layout: `astrolabe/core.py` (build + config), `astrolabe/audit.py`
(verification), `astrolabe/cli.py` (commands), `examples/make_demo.py`
(synthetic archive generator), `tests/`.

## License

MIT.

---

If this saves your agent a context window, a star helps the next person find it.
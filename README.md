# Astrolabe

A hierarchical, read-only index for AI agents.

Point it at a folder of notes, drafts or exports. It writes a small JSON
catalogue that an agent can navigate — **volume → chapter → page** — instead of
loading the whole folder into context.

Nothing in the folder is modified. No database, no embeddings, no server;
standard library only.

## Install

```bash
git clone <this-repo-url>
cd astrolabe-index

python3 -m astrolabe --version     # runs without installing
pip install -e .                   # optional: adds the `astrolabe` command
```

Requires Python 3.9 or newer.

## Use

```bash
# build or rebuild the index (writes <dir>/_index/, touches nothing else)
python3 -m astrolabe build ~/archive

# verify the index against the filesystem (read-only, exit 1 on drift)
python3 -m astrolabe check ~/archive

# size report
python3 -m astrolabe stats ~/archive
```

Try it on the bundled demo archive first:

```bash
python3 examples/make_demo.py /tmp/demo-archive
python3 -m astrolabe build /tmp/demo-archive --split-threshold 30
python3 -m astrolabe check /tmp/demo-archive
```

## Output

```
archive/
├── project-a_20250615/          ← your files, untouched
├── project-b_2024/
└── _index/                      ← generated, safe to delete
    ├── 00_catalog.json          ← read this first (a few KB)
    ├── 01_project-a.json        ← one file per volume
    ├── 02_project-b.json
    └── gaps.json                ← files that were skipped
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
`page_list` (small chapter) or `sample_pages` + `page_distribution` (large one).

## Reading the index (agent-side)

1. Read `_index/00_catalog.json`; pick a volume from `volume_list`.
2. Read that volume's `file`; each `chapter_list` item has an `entry` path.
3. Open pages under the entry path. When `page_distribution` is present, list the
   directory to see everything.
4. Check `_index/gaps.json` before reporting that a file is missing.

`SKILL.md` packages these steps as an Agent Skill for Claude Code, Codex, Cursor
and similar tools.

## Options

| flag | default | meaning |
|---|---|---|
| `-o, --out` | `_index` | index directory name |
| `--split-threshold` | `200` | a chapter with more pages than this is split one level deeper |
| `--list-threshold` | `20` | chapters up to this size list every page name; larger ones get a sample |

Grouping is controlled by `Config.group_patterns` (dated copies such as
`proj_20250615` and `proj_2024` collapse into one volume) and by `skip_ext` /
`skip_dirs` in `astrolabe/core.py`.

## Limits

- **Read-only.** Source files are never moved, edited or deleted.
- **Full rebuild on every run.** 5 000 pages ≈ 0.2 s; 20 000 ≈ 0.8 s; 15 MB peak.
- **Not a search engine.** It indexes locations, not content. Pair it with
  full-text or semantic search if you need passage-level retrieval.
- **Filenames are the primary signal.** Meaningful names give a useful index;
  a folder of `untitled-3.md` will not.

## Tests

```bash
python3 -m unittest discover -s tests -v
```

## License

MIT.
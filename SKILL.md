---
name: archive-index
description: Build a hierarchical read-only index over a folder of old notes, drafts or exports so an agent can locate files without loading them all into context. Use when a directory holds hundreds of files and the agent keeps grepping blindly or asking "where is X".
---

# Archive Index (Astrolabe)

Turns a folder into a three-level catalogue an agent can navigate:
**volume → chapter → page**. Nothing in the folder is modified; the index is
generated data that can be deleted and rebuilt at any time.

## When to use this

Use it when all of these hold:

- The folder holds many files (roughly 50+), accumulated over time.
- Files come in families: dated copies, versions, exports, per-project folders.
- You keep needing to locate a specific file, or answer "what is in here".
- Loading the whole tree into context is too expensive.

## Steps

1. **Build the index** (writes `<dir>/_index/`, touches nothing else):

   ```bash
   python3 -m astrolabe build <dir>
   ```

   For a flat folder with very large subfolders, lower the split threshold so
   chapters stay navigable:

   ```bash
   python3 -m astrolabe build <dir> --split-threshold 50
   ```

2. **Read `_index/00_catalog.json` first.** It is a few KB. It contains
   `volume_list` with per-volume `pages`, `chapters`, `keywords`, `heat`
   (`hot` < 30 days, `warm` < 180, `cold` older) and `entry` paths.

3. **Pick a volume, then read its file** (`_index/NN_<volume>.json`).
   `chapter_list` gives one `entry` path per chapter, plus `keywords` and either
   `page_list` (small chapter) or `sample_pages` + `page_distribution`
   (large chapter — list the directory to see everything).

4. **Open pages by entry path.** Entries are relative to the indexed root and
   always end with `/` for directories.

5. **Before saying "it isn't there", read `_index/gaps.json`.** It lists files
   that were not indexed (binaries, archives, images). An empty `items` list
   means "checked, nothing skipped".

6. **Verify a stale index:**

   ```bash
   python3 -m astrolabe check <dir>    # exit 0 = index matches filesystem
   ```

## Notes

- Use the index instead of walking the tree: that is the point of building it.
- Do not edit files inside `_index/`; they are regenerated on the next build.
- Chapter names are unique within a volume, not across volumes. Always pair a
  chapter with its volume.
- A chapter with `encoding_warning` has filenames that are stored in a legacy
  encoding on disk; the listed names are the repaired readable form.
- `heat` is derived from modification times and is a hint, not a rule.
#!/usr/bin/env python3
"""Read-only consistency check: does the index still match the filesystem?

Separate from `build`. Build answers "produce an index"; check answers
"is this index true right now". You can run check at any time; it never writes.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .core import Config, _collect_pages, _entry, _iter_safe


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def audit(cfg: Config) -> tuple[bool, list[str], list[str]]:
    """Return (ok, passes, failures)."""
    root = cfg.root.resolve()
    out_dir = root / cfg.out_dir
    master_path = out_dir / "00_catalog.json"
    passes: list[str] = []
    fails: list[str] = []

    def ok(msg: str) -> None:
        passes.append(msg)

    def bad(msg: str) -> None:
        fails.append(msg)

    if not master_path.exists():
        bad(f"catalogue missing: {master_path}")
        return False, passes, fails

    try:
        master = _load(master_path)
    except Exception as exc:
        bad(f"catalogue is not valid JSON: {exc}")
        return False, passes, fails

    # ---- page count vs filesystem -----------------------------------------
    # The index directory is not part of the source tree.
    def in_out_dir(p: Path) -> bool:
        try:
            return p.relative_to(root).parts[0] == cfg.out_dir
        except (ValueError, IndexError):
            return False

    real_pages = [p for p in _collect_pages(root, cfg) if not in_out_dir(p)]
    if master.get("total_pages") == len(real_pages):
        ok(f"page count matches filesystem ({len(real_pages)})")
    else:
        bad(f"page count mismatch: index {master.get('total_pages')} vs filesystem {len(real_pages)}")

    # ---- volume files ------------------------------------------------------
    volume_files = [f for f in _iter_safe(out_dir, cfg.skip_dirs)
                    if f.suffix == ".json" and f.name not in ("00_catalog.json", "gaps.json")]
    if len(volume_files) == master.get("volumes"):
        ok(f"volume count matches files ({len(volume_files)})")
    else:
        bad(f"volume count mismatch: catalogue {master.get('volumes')} vs files {len(volume_files)}")

    # ---- per-volume cross-file consistency --------------------------------
    sum_pages = sum_chapters = 0
    cross_bad = 0
    for entry in master.get("volume_list", []):
        vpath = root / entry["file"]
        if not vpath.exists():
            bad(f"volume file missing: {entry['file']}")
            continue
        try:
            volume = _load(vpath)
        except Exception as exc:
            bad(f"volume file invalid JSON ({entry['file']}): {exc}")
            continue

        problems: list[str] = []
        if volume.get("pages") != entry.get("pages"):
            problems.append(f"pages catalogue {entry.get('pages')} vs file {volume.get('pages')}")
        if volume.get("chapters") != entry.get("chapters"):
            problems.append(f"chapters catalogue {entry.get('chapters')} vs file {volume.get('chapters')}")
        chapter_pages = sum(c.get("pages", 0) for c in volume.get("chapter_list", []))
        if chapter_pages != volume.get("pages"):
            problems.append(f"chapter pages sum {chapter_pages} vs volume pages {volume.get('pages')}")
        sum_pages += volume.get("pages") or 0
        sum_chapters += volume.get("chapters") or 0
        if problems:
            cross_bad += 1
            bad(f"cross-file mismatch ({volume.get('volume')}): " + "; ".join(problems))

    if sum_pages != master.get("total_pages"):
        bad(f"volume pages sum {sum_pages} vs total_pages {master.get('total_pages')}")
    if cross_bad == 0 and sum_pages == master.get("total_pages"):
        ok(f"cross-file numbers agree ({master.get('volumes')} volumes / "
           f"{sum_chapters} chapters / {sum_pages} pages)")

    # ---- every path must exist -------------------------------------------
    bad_paths: list[str] = []
    n_entry = n_page = n_sub = 0
    for entry in master.get("volume_list", []):
        vpath = root / entry["file"]
        if not vpath.exists():
            continue
        volume = _load(vpath)
        for chapter in volume.get("chapter_list", []):
            chap_entry = root / chapter["entry"]
            n_entry += 1
            if not chap_entry.exists():
                bad_paths.append(chapter["entry"])
                continue
            if chap_entry.is_file():
                continue
            skip_names = set(chapter.get("encoding_warning") or [])
            for name in chapter.get("page_list") or []:
                n_page += 1
                if name in skip_names:
                    continue
                if not (chap_entry / name).exists():
                    bad_paths.append(chapter["entry"] + name)
            for sub in chapter.get("subdirs") or []:
                if sub.startswith("...and"):
                    continue
                n_sub += 1
                if not (chap_entry / sub).is_dir():
                    bad_paths.append(chapter["entry"] + sub)
    if bad_paths:
        bad(f"{len(bad_paths)} dead path(s), e.g. {bad_paths[:3]}")
    else:
        ok(f"all paths resolve (entries {n_entry} / pages {n_page} / subdirs {n_sub})")

    # ---- JSON health ------------------------------------------------------
    broken = []
    for f in _iter_safe(out_dir, cfg.skip_dirs):
        if f.suffix == ".json":
            try:
                _load(f)
            except Exception:
                broken.append(f.name)
    if broken:
        bad(f"invalid JSON: {broken}")
    else:
        ok(f"all JSON parses ({len([f for f in _iter_safe(out_dir, cfg.skip_dirs) if f.suffix == '.json'])} files)")

    # ---- gaps + temp files ------------------------------------------------
    gaps = out_dir / "gaps.json"
    if gaps.exists():
        ok("gaps.json present")
    else:
        bad("gaps.json missing (skipped files untracked)")

    tmp = [f.name for f in _iter_safe(out_dir, cfg.skip_dirs) if f.name.endswith(".tmp")]
    if tmp:
        bad(f"temp files left behind: {tmp}")
    else:
        ok("no temp files")

    return (not fails), passes, fails
#!/usr/bin/env python3
"""Astrolabe — a hierarchical, read-only index for AI agents.

Scans a directory of documents and produces a three-level catalogue:

    volume (a theme / project)  ->  chapter (a version / event)  ->  page (a file)

Behaviour
---------
- Read-only: the source tree is never modified.
- Generated output: the index directory can be deleted and rebuilt at any time.
- Standard library only: no database, no embeddings, no services.
- Symlinks are not followed; permission errors do not abort a build.
- Every run performs a full rebuild.

The index is written as plain JSON so an agent can read one small file to
learn what exists, then descend only into the branch it needs.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence

__all__ = [
    "Config",
    "build",
    "DEFAULT_SKIP_EXT",
    "DEFAULT_GROUP_PATTERNS",
    "SKIP_EXT",
]

VERSION = "0.1.0"
GENERATOR = f"astrolabe {VERSION}"

# Binary / archive files are not pages: they cannot be read by an agent anyway.
DEFAULT_SKIP_EXT: tuple[str, ...] = (
    ".pyc", ".pyo", ".zip", ".tar", ".gz", ".tgz", ".bz2", ".xz", ".7z", ".rar",
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".ico",
    ".mp4", ".mov", ".avi", ".mkv", ".mp3", ".wav", ".flac",
    ".pdf", ".xlsx", ".xls", ".doc", ".docx", ".ppt", ".pptx",
    ".db", ".sqlite", ".pkl", ".pt", ".pth", ".onnx", ".bin", ".exe", ".dll",
)

DEFAULT_SKIP_DIRS: tuple[str, ...] = (
    "__pycache__", "node_modules", ".git", ".svn", ".hg",
    ".obsidian", ".trash", ".cache", ".venv", "venv",
)

# Suffixes that should NOT split a volume: `backup_20260301` and `backup_20260405`
# are two chapters of the same volume. Order matters — first match wins.
DEFAULT_GROUP_PATTERNS: tuple[str, ...] = (
    r"[_-](?:19|20)\d{2}[-_]?\d{2}[-_]?\d{2}$",
    r"[_-](?:19|20)\d{2}[-_]?\d{2}$",
    r"[_-](?:19|20)\d{2}$",
    r"[_-]v?\d+(?:[._]\d+)+$",
    r"[_-](?:final|old|new|backup|bak|copy|deprecated|archive|draft|snapshot)$",
)

# Words that carry no retrieval signal in either language.
STOPWORDS = frozenset({
    "the", "and", "for", "with", "from", "this", "that", "copy", "old", "new",
    "backup", "bak", "draft", "final", "deprecated", "archive", "temp", "tmp",
    "备份", "版本", "临时", "新建", "副本", "测试", "旧版", "新版", "记录", "说明",
})


@dataclass
class Config:
    """Tunables. Everything that used to be hard-coded lives here."""

    root: Path
    out_dir: str = "_index"
    group_patterns: Sequence[str] = DEFAULT_GROUP_PATTERNS
    volume_split_threshold: int = 200   # chapter with more pages than this gets split one level deeper
    page_list_threshold: int = 20       # chapter with <= this many pages lists every page name
    max_keywords: int = 8
    max_chapter_keywords: int = 12
    skip_ext: Sequence[str] = DEFAULT_SKIP_EXT
    skip_dirs: Sequence[str] = DEFAULT_SKIP_DIRS
    max_split_depth: int = 2
    max_walk_dirs: int = 20_000         # guard against pathological trees
    heat_days: tuple[int, int] = (30, 180)   # hot < 30d, warm < 180d, else cold
    tz_offset: int = 8                  # local timezone for date rendering

    def skipped_ext(self) -> set[str]:
        return {e.lower() for e in self.skip_ext}


# --------------------------------------------------------------------------- #
# safe filesystem helpers
# --------------------------------------------------------------------------- #

def _iter_safe(path: Path, skip_dirs: Iterable[str]) -> list[Path]:
    """List a directory: never follow symlinks, never raise on permissions."""
    out: list[Path] = []
    try:
        for entry in path.iterdir():
            try:
                if entry.is_symlink():
                    continue
                if entry.is_dir() and entry.name in skip_dirs:
                    continue
                out.append(entry)
            except OSError:
                continue
    except (PermissionError, OSError):
        return []
    return sorted(out)


def _walk_safe(path: Path, cfg: Config) -> list[Path]:
    """Recursively list files without following symlinks or dying on errors."""
    out: list[Path] = []
    stack = [path]
    seen = 0
    skip_dirs = set(cfg.skip_dirs)
    while stack:
        current = stack.pop()
        seen += 1
        if seen > cfg.max_walk_dirs:
            break
        for entry in _iter_safe(current, skip_dirs):
            try:
                if entry.is_dir():
                    stack.append(entry)
                elif entry.is_file():
                    out.append(entry)
            except OSError:
                continue
    return sorted(out)


def _collect_pages(path: Path, cfg: Config) -> list[Path]:
    skip = cfg.skipped_ext()
    return [p for p in _walk_safe(path, cfg) if p.suffix.lower() not in skip]


def _dir_size(path: Path, cfg: Config) -> int:
    total = 0
    for p in _walk_safe(path, cfg):
        try:
            total += p.stat().st_size
        except OSError:
            continue
    return total


def _newest_mtime(path: Path, cfg: Config) -> float:
    newest = 0.0
    for p in _walk_safe(path, cfg):
        try:
            newest = max(newest, p.stat().st_mtime)
        except OSError:
            continue
    return newest


# --------------------------------------------------------------------------- #
# filename encoding
# --------------------------------------------------------------------------- #

_ENCODING_FIXES: set[str] = set()


def fix_name(value: str) -> str:
    """Repair filenames that are not valid UTF-8 (e.g. legacy GBK bytes).

    Undecodable bytes surface as lone surrogates, which cannot be serialised
    to JSON.
    """
    try:
        value.encode("utf-8")
        return value
    except UnicodeEncodeError:
        pass
    try:
        raw = value.encode("utf-8", "surrogateescape")
    except Exception:
        return value
    for enc in ("utf-8", "gbk", "gb18030", "big5", "shift_jis", "latin-1"):
        try:
            fixed = raw.decode(enc)
            _ENCODING_FIXES.add(fixed)
            return fixed
        except (UnicodeDecodeError, LookupError):
            continue
    fixed = raw.decode("utf-8", "replace")
    _ENCODING_FIXES.add(fixed)
    return fixed


def _deep_fix(obj: Any) -> Any:
    if isinstance(obj, str):
        return fix_name(obj)
    if isinstance(obj, list):
        return [_deep_fix(x) for x in obj]
    if isinstance(obj, dict):
        return {fix_name(k): _deep_fix(v) for k, v in obj.items()}
    return obj


def _atomic_write(path: Path, text: str) -> None:
    """Write via a temp file + rename: a reader never sees a half-written file."""
    tmp = path.parent / f".{path.name}.tmp"
    try:
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass


# --------------------------------------------------------------------------- #
# keywords, dates, sizes
# --------------------------------------------------------------------------- #

_CN = re.compile(r"[\u4e00-\u9fa5]{2,6}")
# Letters only, so digits and punctuation do not glue onto words.
_EN = re.compile(r"[A-Za-z][A-Za-z]{2,}")
_VER = re.compile(r"v\d+(?:\.\d+)*|第[一二三四五六七八九十百\d]+[幕卷章篇部章节]")


def extract_keywords(texts: Sequence[str], cfg: Config) -> list[str]:
    """Pick retrieval-useful terms from page/chapter names.

    Handles CJK runs, latin words and version tokens. Stopwords are dropped.
    """
    counts: dict[str, int] = {}

    def bump(token: str) -> None:
        token = token.strip()
        if len(token) < 2 or token.lower() in STOPWORDS or token in STOPWORDS:
            return
        counts[token] = counts.get(token, 0) + 1

    for text in texts:
        for m in _CN.findall(text):
            bump(m)
        for m in _EN.findall(text):
            bump(m)
        for m in _VER.findall(text):
            bump(m)

    ranked = sorted(counts.items(), key=lambda kv: (-kv[1], -len(kv[0])))
    return [k for k, _ in ranked[: cfg.max_keywords]]


def _fmt_date(ts: float, cfg: Config) -> str:
    if not ts:
        return ""
    tz = timezone(timedelta(hours=cfg.tz_offset))
    return datetime.fromtimestamp(ts, tz).strftime("%Y-%m-%d")


def _human_size(n: int) -> str:
    for unit in ("B", "K", "M", "G"):
        if n < 1024:
            return f"{n:.0f}{unit}" if unit == "B" else f"{n:.1f}{unit}"
        n /= 1024
    return f"{n:.1f}T"


def _heat(ts: float, cfg: Config) -> str:
    if not ts:
        return "unknown"
    hot, warm = cfg.heat_days
    days = (datetime.now().timestamp() - ts) / 86400
    if days < hot:
        return "hot"
    if days < warm:
        return "warm"
    return "cold"


# --------------------------------------------------------------------------- #
# grouping (volume = group of directories sharing a base name)
# --------------------------------------------------------------------------- #

def group_key(name: str, cfg: Config) -> str:
    """`notes_backup_20260301` -> `notes_backup` so dated copies stay in one volume."""
    for pattern in cfg.group_patterns:
        m = re.search(pattern, name, re.IGNORECASE)
        if m and m.start() > 0:
            return name[: m.start()]
    return name


# --------------------------------------------------------------------------- #
# chapter / volume construction
# --------------------------------------------------------------------------- #

def _rel(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root)).replace("\\", "/")
    except ValueError:
        return path.name


def _entry(path: Path, root: Path) -> str:
    """Entry path relative to the indexed root, always ending with `/` for dirs."""
    rel = _rel(path, root)
    if rel in (".", ""):
        return "./"
    return rel + "/"


def _annotate_encoding(chapter: dict, pages: Sequence[Path], base: Path) -> dict:
    """Record pages whose on-disk name differs from the name written to JSON."""
    fixed_pages: list[str] = []
    for p in pages:
        rel = _rel(p, base)
        if fix_name(rel) != rel:
            fixed_pages.append(fix_name(rel))
    if fixed_pages:
        chapter["encoding_warning"] = fixed_pages[:20] + (
            [f"...and {len(fixed_pages) - 20} more"] if len(fixed_pages) > 20 else []
        )
        chapter["encoding_note"] = (
            "These pages have legacy-encoded filenames on disk. The names above are "
            "the repaired readable form; open them by decoding the original bytes "
            "(e.g. gbk) rather than by the literal name."
        )
    return chapter


def build_chapter(chapter_dir: Path, root: Path, cfg: Config) -> dict:
    pages = _collect_pages(chapter_dir, cfg)
    mtime = _newest_mtime(chapter_dir, cfg)

    keywords = extract_keywords([p.stem for p in pages], cfg)
    # The chapter name also contributes keywords.
    for token in re.split(r"[_\-.\s()\[\]{}·,;]+", chapter_dir.name):
        token = token.strip()
        if len(token) >= 2 and not token.isdigit() and token not in keywords:
            keywords.append(token)

    chapter: dict = {
        "chapter": chapter_dir.name,
        "entry": _entry(chapter_dir, root),
        "pages": len(pages),
        "keywords": keywords[: cfg.max_chapter_keywords],
        "updated": _fmt_date(mtime, cfg),
    }
    _annotate_encoding(chapter, pages, chapter_dir)

    subdirs = [d.name for d in _iter_safe(chapter_dir, cfg.skip_dirs) if d.is_dir()]
    if subdirs:
        chapter["subdirs"] = subdirs[:10] + (
            [f"...and {len(subdirs) - 10} more"] if len(subdirs) > 10 else []
        )
        top_level = len([x for x in _iter_safe(chapter_dir, cfg.skip_dirs) if x.is_file()])
        if len(pages) > top_level:
            chapter["page_distribution"] = (
                f"{top_level} pages at top level, {len(pages) - top_level} more in "
                f"subdirectories (recurse)"
            )

    # Page paths are stored relative to the chapter entry so pages in
    # subdirectories stay reachable.
    if 0 < len(pages) <= cfg.page_list_threshold:
        chapter["page_list"] = [_rel(p, chapter_dir) for p in pages]
    elif len(pages) > cfg.page_list_threshold:
        chapter["sample_pages"] = (
            [_rel(p, chapter_dir) for p in pages[:3]]
            + ["..."]
            + [_rel(p, chapter_dir) for p in pages[-2:]]
        )
    return chapter


def _make_chapters(
    dir_path: Path,
    root: Path,
    cfg: Config,
    depth: int = 0,
    label_root_pages: bool = False,
    prefix: str = "",
) -> list[dict]:
    """First-level subdirectories become chapters; oversized chapters split once more.

    `prefix` is prepended to split chapter names so they stay unique
    (`release_2026/build_01`).
    """
    chapters: list[dict] = []
    subdirs = [d for d in _iter_safe(dir_path, cfg.skip_dirs)
               if d.is_dir() and not d.name.startswith(".")]

    for d in subdirs:
        page_count = len(_collect_pages(d, cfg))
        if page_count > cfg.volume_split_threshold and depth < cfg.max_split_depth:
            grandchildren = [x for x in _iter_safe(d, cfg.skip_dirs) if x.is_dir()]
            if grandchildren:
                chapters.extend(_make_chapters(
                    d, root, cfg, depth + 1,
                    prefix=f"{prefix}{d.name}/",
                ))
                continue
        chapter = build_chapter(d, root, cfg)
        if prefix:
            chapter["chapter"] = f"{prefix}{chapter['chapter']}"
        chapters.append(chapter)

    # Loose files sitting directly in this directory
    loose = [p for p in _iter_safe(dir_path, cfg.skip_dirs)
             if p.is_file() and p.suffix.lower() not in cfg.skipped_ext()]
    if loose:
        if depth > 0:
            name = (prefix.rstrip("/") + " (root files)") if prefix else f"{dir_path.name} (root files)"
        elif label_root_pages:
            # Several members share this volume: keep the member identity so the
            # chapter name is unique and still readable.
            name = f"{prefix}{dir_path.name}" if prefix else dir_path.name
        else:
            name = "(root files)"
        chapter = {
            "chapter": name,
            "entry": _entry(dir_path, root),
            "pages": len(loose),
            "keywords": extract_keywords([p.stem for p in loose], cfg),
            "page_list": [p.name for p in loose],
        }
        chapters.append(_annotate_encoding(chapter, loose, dir_path))
    return chapters


def build_volume(name: str, members: list[Path], root: Path, cfg: Config) -> dict:
    chapters: list[dict] = []
    entries: list[str] = []
    multi = len(members) > 1

    for member in members:
        if member.is_dir():
            entries.append(_entry(member, root))
            # When several dated copies share one volume, prefix chapter names with
            # the distinguishing suffix (`20250615/v1-wireframes`).
            member_prefix = ""
            if multi:
                suffix = member.name
                if name and member.name.startswith(name):
                    suffix = member.name[len(name):].strip("_- ")
                member_prefix = f"{suffix}/" if suffix else ""
            chapters.extend(_make_chapters(member, root, cfg, label_root_pages=multi,
                                           prefix=member_prefix))
        else:
            entries.append(_entry(member.parent, root))
            chapters.append({
                "chapter": member.stem,
                "entry": _entry(member.parent, root) + member.name,
                "pages": 1,
                "keywords": extract_keywords([member.stem], cfg),
                "page_list": [member.name],
            })

    total_pages = sum(c["pages"] for c in chapters)
    mtimes = [
        _newest_mtime(m, cfg) if m.is_dir() else (m.stat().st_mtime if m.exists() else 0)
        for m in members
    ]
    mtime = max(mtimes) if mtimes else 0.0
    size = sum(_dir_size(m, cfg) if m.is_dir() else m.stat().st_size for m in members)

    names: list[str] = []
    for c in chapters:
        names.extend(c.get("page_list", []) or c.get("sample_pages", []))
        names.append(c["chapter"])

    return {
        "volume": name,
        "entry": entries[0] if len(entries) == 1 else entries,
        "pages": total_pages,
        "chapters": len(chapters),
        "size": _human_size(size),
        "keywords": extract_keywords(names, cfg),
        "updated": _fmt_date(mtime, cfg),
        "heat": _heat(mtime, cfg),
        "chapter_list": chapters,
    }


# --------------------------------------------------------------------------- #
# top-level build
# --------------------------------------------------------------------------- #

def _scan_root(root: Path, cfg: Config) -> tuple[dict[str, list[Path]], list[dict]]:
    """Group top-level entries into volumes.

    Loose files sitting directly in the root are collected into a single
    `(root files)` volume.
    """
    groups: dict[str, list[Path]] = {}
    gaps: list[dict] = []
    loose: list[Path] = []
    skip_ext = cfg.skipped_ext()

    for entry in _iter_safe(root, cfg.skip_dirs):
        if entry.name == cfg.out_dir:
            continue
        if entry.is_file() and entry.suffix.lower() in skip_ext:
            gaps.append({
                "item": entry.name,
                "path": _entry(entry.parent, root) + entry.name,
                "reason": "extension is in the skip list; not indexed",
            })
            continue
        if entry.is_file():
            loose.append(entry)
            continue
        key = group_key(entry.name, cfg)
        groups.setdefault(key, []).append(entry)

    if loose:
        groups["(root files)"] = loose
    return groups, gaps


def build(cfg: Config, dry_run: bool = False, verbose: bool = False) -> dict:
    """Build the catalogue. Returns the master catalogue dict."""
    root = cfg.root.resolve()
    if not root.is_dir():
        raise NotADirectoryError(f"not a directory: {root}")

    groups, gaps = _scan_root(root, cfg)

    # Order volumes by size so the biggest theme comes first.
    ordered = sorted(
        groups.items(),
        key=lambda kv: -sum(len(_collect_pages(m, cfg)) if m.is_dir() else 1 for m in kv[1]),
    )

    volumes: list[dict] = []
    for name, members in ordered:
        if verbose:
            print(f"  volume {name}: {len(members)} member(s)")
        volumes.append(build_volume(name, members, root, cfg))

    out_dir = root / cfg.out_dir
    if dry_run:
        for v in volumes:
            print(f"  {v['volume']}  {v['pages']} pages / {v['chapters']} chapters / "
                  f"{v['size']} / {v['heat']}")
        return {"volumes": volumes, "gaps": gaps}

    out_dir.mkdir(exist_ok=True)
    now = datetime.now(timezone(timedelta(hours=cfg.tz_offset))).strftime("%Y-%m-%dT%H:%M:%S%z")

    master: dict = {
        "about": (
            "Hierarchical, read-only index. Search order: read this file to pick a volume, "
            "then read the volume file to pick a chapter, then open pages by entry path."
        ),
        "root": _rel(root, root) or ".",
        "generated_at": now,
        "generator": GENERATOR,
        "signed_by": "Nobody",
        "whisper": "Nobody is with you.",
        "volumes": len(volumes),
        "total_pages": sum(v["pages"] for v in volumes),
        "page_scope": (
            "Every text-like file under the root, excluding binary/archive extensions "
            "and the index directory itself."
        ),
        "how_to_search": [
            "Volume level: read volume_list below; match on name/keywords/heat.",
            "Chapter level: read the file referenced by a volume; its chapter_list has entry paths.",
            "Page level: append a page name to the chapter entry path, or list the directory.",
            "Encoding: a chapter with encoding_warning needs the original filename bytes decoded (e.g. gbk).",
            "Skipped files: see gaps.json next to this file.",
        ],
        "volume_list": [],
    }

    for i, volume in enumerate(volumes, 1):
        safe = re.sub(r"[^\w\u4e00-\u9fa5-]+", "_", volume["volume"]).strip("_") or f"volume{i}"
        filename = f"{i:02d}_{safe}.json"
        slim = dict(volume)
        # Only the fields listed here are written to disk.
        slim["chapter_list"] = [
            {k: c[k] for k in (
                "chapter", "entry", "pages", "keywords", "updated",
                "page_list", "sample_pages", "subdirs", "page_distribution",
                "encoding_warning", "encoding_note",
            ) if k in c}
            for c in volume["chapter_list"]
        ]
        _atomic_write(out_dir / filename,
                      json.dumps(_deep_fix(slim), ensure_ascii=False, indent=1))
        master["volume_list"].append({
            "volume": volume["volume"],
            "file": f"{cfg.out_dir}/{filename}",
            "pages": volume["pages"],
            "chapters": volume["chapters"],
            "size": volume["size"],
            "keywords": volume["keywords"],
            "updated": volume["updated"],
            "heat": volume["heat"],
            "entry": volume["entry"],
        })

    _atomic_write(out_dir / "00_catalog.json",
                  json.dumps(_deep_fix(master), ensure_ascii=False, indent=1))

    # Written every run; an empty list means nothing was skipped.
    _atomic_write(out_dir / "gaps.json",
                  json.dumps({"note": "entries that could not be indexed", "items": gaps},
                             ensure_ascii=False, indent=1))

    # Remove index files that no longer correspond to a volume (renamed/moved themes).
    expected = {"00_catalog.json", "gaps.json"} | {
        Path(v["file"]).name for v in master["volume_list"]
    }
    removed: list[str] = []
    for f in _iter_safe(out_dir, cfg.skip_dirs):
        if f.suffix == ".json" and f.name not in expected:
            try:
                f.unlink()
                removed.append(f.name)
            except OSError:
                pass

    return {"master": master, "removed": removed, "gaps": gaps}


SKIP_EXT = DEFAULT_SKIP_EXT   # backward-friendly alias


# ---
# Nobody 与你同在。
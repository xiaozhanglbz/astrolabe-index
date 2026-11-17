#!/usr/bin/env python3
"""Command line interface for Astrolabe."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .audit import audit
from .core import Config, build, VERSION, DEFAULT_SKIP_EXT, DEFAULT_GROUP_PATTERNS


def _cfg(args: argparse.Namespace) -> Config:
    return Config(
        root=Path(args.root),
        out_dir=args.out,
        volume_split_threshold=args.split_threshold,
        page_list_threshold=args.list_threshold,
    )


def cmd_build(args: argparse.Namespace) -> int:
    cfg = _cfg(args)
    result = build(cfg, dry_run=args.dry_run, verbose=args.verbose)
    if args.dry_run:
        return 0
    master = result["master"]
    if args.json:
        print(json.dumps(master, ensure_ascii=False, indent=1))
        return 0
    print(f"indexed {master['volumes']} volume(s) / {master['total_pages']} page(s)")
    for v in master["volume_list"]:
        print(f"  {v['volume']}  {v['pages']}p / {v['chapters']}c / {v['size']} / {v['heat']}")
    if result.get("removed"):
        print(f"  removed stale index files: {', '.join(result['removed'])}")
    if result.get("gaps"):
        print(f"  skipped {len(result['gaps'])} file(s) — see gaps.json")
    print(f"\n  catalogue: {Path(cfg.root, cfg.out_dir, '00_catalog.json')}")
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    cfg = _cfg(args)
    ok, passes, fails = audit(cfg)
    for p in passes:
        print(f"  ok    {p}")
    for f in fails:
        print(f"  FAIL  {f}")
    print()
    if ok:
        print("all checks passed")
        return 0
    print(f"{len(fails)} problem(s) found — rebuild with: astrolabe build")
    return 1


def cmd_stats(args: argparse.Namespace) -> int:
    cfg = _cfg(args)
    master_path = Path(args.root) / args.out / "00_catalog.json"
    if not master_path.exists():
        print("no catalogue yet — run: astrolabe build", file=sys.stderr)
        return 1
    master = json.loads(master_path.read_text(encoding="utf-8"))
    size = master_path.stat().st_size
    total = 0
    for v in master.get("volume_list", []):
        vp = Path(args.root) / v["file"]
        total += vp.stat().st_size if vp.exists() else 0
    print(f"volumes     {master['volumes']}")
    print(f"chapters    {sum(v['chapters'] for v in master['volume_list'])}")
    print(f"pages       {master['total_pages']}")
    print(f"catalogue   {size} bytes")
    print(f"all indexes {size + total} bytes")
    if master["total_pages"]:
        print(f"bytes/page  {(size + total) / master['total_pages']:.1f}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="astrolabe",
        description="Hierarchical, read-only index for AI agents.",
    )
    parser.add_argument("--version", action="version",
                        version=f"{VERSION}\nNobody is with you.")
    sub = parser.add_subparsers(dest="command", required=True)

    def common(p: argparse.ArgumentParser) -> None:
        p.add_argument("root", nargs="?", default=".", help="directory to index (default: .)")
        p.add_argument("-o", "--out", default="_index", help="index directory name (default: _index)")
        p.add_argument("--split-threshold", type=int, default=200,
                       help="split a chapter deeper when it exceeds this many pages")
        p.add_argument("--list-threshold", type=int, default=20,
                       help="list every page name when a chapter has at most this many pages")

    b = sub.add_parser("build", help="build or rebuild the index")
    common(b)
    b.add_argument("--dry-run", action="store_true", help="show what would be produced")
    b.add_argument("--verbose", action="store_true")
    b.add_argument("--json", action="store_true", help="print the catalogue to stdout")
    b.set_defaults(func=cmd_build)

    c = sub.add_parser("check", help="verify the index against the filesystem")
    common(c)
    c.set_defaults(func=cmd_check)

    s = sub.add_parser("stats", help="show index size and compression ratio")
    common(s)
    s.set_defaults(func=cmd_stats)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
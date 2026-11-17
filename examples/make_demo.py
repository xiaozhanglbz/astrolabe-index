#!/usr/bin/env python3
"""Create a synthetic archive so anyone can try Astrolabe without real data.

The layout deliberately contains every awkward case the indexer handles:
dated copies, nested chapter folders, loose files, an oversized chapter,
a legacy (GBK) filename, a symlink, a binary blob and a deep path.

    python3 examples/make_demo.py /tmp/demo-archive
"""
from __future__ import annotations

import os
import shutil
import sys
import time
from pathlib import Path

LOTS_OF_PAGES = 34          # more than the default --split-threshold of 30 used in the demo
OLD = 400 * 86400           # mtime ~13 months back -> "cold"


def write(path: Path, text: str = "placeholder\n") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def make(root: Path) -> None:
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)

    # --- one theme, two dated copies -> one volume, chapters from both -----
    for stamp in ("20250615", "20250820"):
        base = root / f"acme-redesign_{stamp}"
        write(base / "v1-wireframes" / "homepage.md", "# wireframe\n")
        write(base / "v1-wireframes" / "checkout.md", "# wireframe\n")
        write(base / "v2-mockups" / "dashboard.md", "# mockup\n")
        write(base / "v2-mockups" / "settings.md", "# mockup\n")
        write(base / "v3-final" / "index.md", "# final spec\n")
        write(base / "v3-final" / "assets" / "logo-notes.md", "# logo\n")
        write(base / "v3-final" / "assets" / "palette.md", "# palette\n")
        write(base / "notes.md", "# stray note at the volume root\n")

    # --- a second theme with an oversized chapter (gets split) -------------
    tickets = root / "support-tickets_2024"
    for i in range(LOTS_OF_PAGES):
        write(tickets / "batch-a" / f"ticket-{i:03d}.md", f"# ticket {i}\n")
    for i in range(15):
        write(tickets / "batch-b" / f"ticket-{i:03d}.md", f"# ticket {i}\n")

    # --- a third theme, two dated copies ----------------------------------
    for stamp in ("2025-01", "2025-02"):
        write(root / f"meeting-notes_{stamp}" / "weekly" / "week-01.md", "# notes\n")
        write(root / f"meeting-notes_{stamp}" / "weekly" / "week-02.md", "# notes\n")

    # --- loose files at the archive root ----------------------------------
    write(root / "inbox.md", "# unsorted\n")
    write(root / "todo.md", "# todo\n")
    (root / "backup-2024.zip").write_bytes(b"PK\x03\x04demo")
    (root / "screenshot.png").write_bytes(b"\x89PNG\r\n\x1a\n")

    # --- legacy encoded filename -----------------------------------------
    legacy = root / "legacy-export"
    legacy.mkdir(parents=True, exist_ok=True)
    raw = os.path.join(str(legacy).encode(), "报告-旧编码.md".encode("gbk"))
    with open(raw, "wb") as fh:
        fh.write(b"# legacy\n")

    # --- deep nesting -----------------------------------------------------
    deep = root / "deep-dive"
    cursor = deep
    for level in range(6):
        cursor = cursor / f"level-{level}"
    write(cursor / "bottom.md", "# very deep\n")

    # --- symlink trap: must never be followed -----------------------------
    # The trap lives outside the archive: it exists only as a symlink target,
    # to prove the scanner refuses to follow links.
    trap = root.parent / f"{root.name}-trap"
    if trap.exists():
        shutil.rmtree(trap)
    write(trap / "should-not-appear.md", "# trap\n")
    try:
        os.symlink(trap, root / "legacy-export" / "link-to-trap")
    except OSError:
        pass

    # --- age the archive so heat labels differ ----------------------------
    now = time.time()
    for path in root.rglob("*"):
        if path.is_file() and not path.is_symlink():
            if "support-tickets_2024" in str(path):
                os.utime(path, (now - OLD, now - OLD))

    print(f"demo archive created at {root}")
    print(f"  files: {sum(1 for p in root.rglob('*') if p.is_file())}")


if __name__ == "__main__":
    target = Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp/demo-archive")
    make(target)
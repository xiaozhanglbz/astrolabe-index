#!/usr/bin/env python3
"""Test suite for Astrolabe. Standard library only: `python3 -m unittest -v`."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from astrolabe.audit import audit                      # noqa: E402
from astrolabe.core import Config, build              # noqa: E402

LONG_NAME = "很长的名字" * 12                            # 180 bytes, under the 255 limit


def write(path: Path, text: str = "page\n") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


class Base(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="astrolabe-test-"))
        self.root = self.tmp / "archive"
        self.root.mkdir()
        self.cfg = Config(root=self.root)

    def tearDown(self) -> None:
        subprocess.run(["chmod", "-R", "u+rwX", str(self.tmp)], capture_output=True)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def build(self, **kwargs):
        cfg = Config(root=self.root, **kwargs) if kwargs else self.cfg
        return build(cfg)

    def catalog(self) -> dict:
        return json.loads((self.root / "_index" / "00_catalog.json").read_text(encoding="utf-8"))

    def volume(self, name: str) -> dict:
        for entry in self.catalog()["volume_list"]:
            if entry["volume"] == name:
                return json.loads((self.root / entry["file"]).read_text(encoding="utf-8"))
        raise AssertionError(f"volume not found: {name} (have {[v['volume'] for v in self.catalog()['volume_list']]})")


class TestGrouping(Base):
    def test_dated_copies_become_one_volume_with_two_chapters(self):
        write(self.root / "notes_20250101" / "draft" / "a.md")
        write(self.root / "notes_20250615" / "draft" / "b.md")
        self.build()
        volumes = [v["volume"] for v in self.catalog()["volume_list"]]
        self.assertEqual(volumes, ["notes"])
        vol = self.volume("notes")
        self.assertEqual(vol["pages"], 2)
        self.assertEqual(vol["chapters"], 2)
        names = [c["chapter"] for c in vol["chapter_list"]]
        self.assertIn("20250101/draft", names)
        self.assertIn("20250615/draft", names)

    def test_same_volume_chapter_names_are_unique(self):
        # Two dated copies of one theme, each with a same-named subdirectory.
        for stamp in ("20250101", "20250202"):
            write(self.root / f"pkg_{stamp}" / "sub" / "x.md")
            write(self.root / f"pkg_{stamp}" / "sub" / "y.md")
        self.build()
        vol = self.volume("pkg")
        names = [c["chapter"] for c in vol["chapter_list"]]
        self.assertEqual(len(names), 2)
        self.assertEqual(len(names), len(set(names)), f"duplicate chapter names: {names}")
        self.assertEqual(sorted(names), ["20250101/sub", "20250202/sub"])

    def test_bare_year_suffix_groups_into_one_volume(self):
        # A bare-year suffix groups like a full date.
        for year in (2024, 2025):
            write(self.root / f"contracts_{year}" / "signed" / "a.md")
        self.build()
        volumes = [v["volume"] for v in self.catalog()["volume_list"]]
        self.assertEqual(volumes, ["contracts"])
        self.assertEqual(self.volume("contracts")["chapters"], 2)

    def test_loose_root_files_share_one_volume(self):
        for name in ("a.md", "b.md", "c.md"):
            write(self.root / name)
        self.build()
        volumes = [v["volume"] for v in self.catalog()["volume_list"]]
        self.assertEqual(volumes, ["(root files)"])
        self.assertEqual(self.volume("(root files)")["chapters"], 3)


class TestSplitting(Base):
    def test_oversized_chapter_splits_with_readable_names(self):
        big = self.root / "project"
        for i in range(30):
            write(big / "batch-one" / f"p{i:02d}.md")
        for i in range(10):
            write(big / "batch-two" / f"p{i:02d}.md")
        self.build(volume_split_threshold=25)
        vol = self.volume("project")
        names = [c["chapter"] for c in vol["chapter_list"]]
        self.assertIn("batch-one", names)
        self.assertIn("batch-two", names)
        self.assertEqual(sum(c["pages"] for c in vol["chapter_list"]), 40)

    def test_threshold_boundary_is_not_split(self):
        for i in range(20):
            write(self.root / "proj" / "chapter" / "deep" / f"p{i:02d}.md")
        self.build(volume_split_threshold=20)
        vol = self.volume("proj")
        self.assertEqual([c["chapter"] for c in vol["chapter_list"]], ["chapter"])

    def test_page_list_switches_to_sample(self):
        for i in range(20):
            write(self.root / "small" / "chap" / f"p{i:02d}.md")
        self.build()
        chapter = self.volume("small")["chapter_list"][0]
        self.assertEqual(len(chapter["page_list"]), 20)
        self.assertNotIn("sample_pages", chapter)

        for i in range(20, 25):
            write(self.root / "small" / "chap" / f"p{i:02d}.md")
        self.build()
        chapter = self.volume("small")["chapter_list"][0]
        self.assertNotIn("page_list", chapter)
        self.assertIn("...", chapter["sample_pages"])


class TestSafety(Base):
    def test_symlink_is_never_followed(self):
        outside = self.tmp / "outside"
        write(outside / "secret.md")
        (self.root / "proj" / "inner").mkdir(parents=True)
        write(self.root / "proj" / "inner" / "real.md")
        os.symlink(outside, self.root / "proj" / "link")

        self.build()
        blob = (self.root / "_index" / "00_catalog.json").read_text(encoding="utf-8")
        self.assertNotIn("secret", blob)
        self.assertEqual(self.catalog()["total_pages"], 1)

    def test_permission_error_does_not_crash(self):
        locked = self.root / "proj" / "locked"
        write(locked / "inside.md")
        write(self.root / "proj" / "ok" / "fine.md")
        os.chmod(locked, 0o000)
        self.build()   # must not raise
        self.assertGreaterEqual(self.catalog()["total_pages"], 1)

    def test_long_filename(self):
        write(self.root / "proj" / "chap" / f"{LONG_NAME}.md")
        self.build()
        self.assertEqual(self.catalog()["total_pages"], 1)

    def test_deep_nesting(self):
        cursor = self.root / "proj"
        for level in range(15):
            cursor = cursor / f"l{level}"
        write(cursor / "bottom.md")
        self.build()
        self.assertEqual(self.catalog()["total_pages"], 1)

    def test_empty_directory(self):
        self.build()
        self.assertEqual(self.catalog()["volumes"], 0)
        self.assertEqual(self.catalog()["total_pages"], 0)
        ok, _, fails = audit(self.cfg)
        self.assertTrue(ok, fails)


class TestEncodingAndSkips(Base):
    def test_gbk_filename_is_repaired_and_flagged(self):
        chapter = self.root / "legacy" / "chap"
        chapter.mkdir(parents=True)
        raw = os.path.join(str(chapter).encode(), "报告.md".encode("gbk"))
        with open(raw, "wb") as fh:
            fh.write(b"x")

        self.build()
        chapter_data = self.volume("legacy")["chapter_list"][0]
        self.assertTrue(chapter_data.get("encoding_warning"))
        self.assertIn("gbk", chapter_data.get("encoding_note", "").lower())

    def test_skipped_extensions_land_in_gaps(self):
        write(self.root / "proj" / "chap" / "note.md")
        (self.root / "archive.zip").write_bytes(b"PK")
        (self.root / "shot.png").write_bytes(b"\x89PNG")

        self.build()
        gaps = json.loads((self.root / "_index" / "gaps.json").read_text(encoding="utf-8"))
        items = {g["item"] for g in gaps["items"]}
        self.assertEqual(items, {"archive.zip", "shot.png"})

    def test_gaps_file_exists_even_when_nothing_is_skipped(self):
        write(self.root / "proj" / "chap" / "note.md")
        self.build()
        gaps = json.loads((self.root / "_index" / "gaps.json").read_text(encoding="utf-8"))
        self.assertEqual(gaps["items"], [])


class TestIndexHygiene(Base):
    def test_no_temp_files_left(self):
        write(self.root / "proj" / "chap" / "a.md")
        self.build()
        tmp = list((self.root / "_index").glob("*.tmp"))
        self.assertEqual(tmp, [])

    def test_stale_index_is_removed(self):
        write(self.root / "alpha" / "chap" / "a.md")
        write(self.root / "beta" / "chap" / "b.md")
        self.build()
        self.assertEqual(len(list((self.root / "_index").glob("0[1-9]*.json"))), 2)

        shutil.move(str(self.root / "beta"), str(self.tmp / "beta"))
        result = self.build()
        remaining = [f.name for f in (self.root / "_index").glob("0[1-9]*.json")]
        self.assertEqual(len(remaining), 1)
        self.assertTrue(result["removed"])

    def test_idempotent(self):
        write(self.root / "proj" / "chap" / "a.md")
        write(self.root / "proj" / "chap" / "b.md")
        self.build()

        def snapshot() -> str:
            import hashlib
            h = hashlib.sha256()
            for f in sorted((self.root / "_index").glob("*.json")):
                text = f.read_text(encoding="utf-8")
                h.update(f.name.encode())
                h.update("\n".join(ln for ln in text.splitlines()
                                   if '"generated_at"' not in ln).encode())
            return h.hexdigest()

        first = snapshot()
        self.build()
        self.assertEqual(first, snapshot())

    def test_index_directory_is_not_indexed(self):
        write(self.root / "proj" / "chap" / "a.md")
        self.build()
        first = self.catalog()["total_pages"]
        self.build()
        self.assertEqual(self.catalog()["total_pages"], first)
        self.assertTrue(audit(self.cfg)[0])


class TestAudit(Base):
    def test_clean_index_passes(self):
        write(self.root / "proj" / "chap" / "a.md")
        self.build()
        ok, passes, fails = audit(self.cfg)
        self.assertTrue(ok, fails)
        self.assertTrue(passes)

    def test_audit_catches_added_pages(self):
        write(self.root / "proj" / "chap" / "a.md")
        self.build()
        write(self.root / "proj" / "chap" / "new.md")
        ok, _, fails = audit(self.cfg)
        self.assertFalse(ok)
        self.assertTrue(any("page count" in f for f in fails))

    def test_audit_catches_cross_file_mismatch(self):
        write(self.root / "proj" / "chap" / "a.md")
        self.build()
        catalog_path = self.root / "_index" / "00_catalog.json"
        catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
        catalog["volume_list"][0]["pages"] += 5
        catalog_path.write_text(json.dumps(catalog, ensure_ascii=False, indent=1), encoding="utf-8")

        ok, _, fails = audit(self.cfg)
        self.assertFalse(ok)
        self.assertTrue(any("cross-file" in f for f in fails), fails)

    def test_audit_catches_missing_volume_file(self):
        write(self.root / "proj" / "chap" / "a.md")
        self.build()
        next((self.root / "_index").glob("0[1-9]*.json")).unlink()
        ok, _, fails = audit(self.cfg)
        self.assertFalse(ok)


class TestRendering(Base):
    def test_master_catalogue_is_small_and_self_describing(self):
        for theme in range(5):
            for page in range(10):
                write(self.root / f"theme-{theme}" / "chap" / f"p{page}.md")
        self.build()
        catalog = self.catalog()
        self.assertEqual(catalog["volumes"], 5)
        self.assertLess((self.root / "_index" / "00_catalog.json").stat().st_size, 6000)
        self.assertIn("how_to_search", catalog)
        for key in ("volume", "file", "pages", "chapters", "keywords", "heat", "entry"):
            self.assertIn(key, catalog["volume_list"][0])

    def test_heat_labels(self):
        write(self.root / "fresh" / "chap" / "a.md")
        old = self.root / "stale" / "chap" / "b.md"
        write(old)
        past = time.time() - 400 * 86400
        os.utime(old, (past, past))

        self.build()
        self.assertEqual(self.volume("fresh")["heat"], "hot")
        self.assertEqual(self.volume("stale")["heat"], "cold")


if __name__ == "__main__":
    unittest.main(verbosity=2)
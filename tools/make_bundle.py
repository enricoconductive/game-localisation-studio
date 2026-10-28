#!/usr/bin/env python3
"""Build dist/studio_bundle.zip: everything the notebook needs in Colab.

Used when the GitHub repository cannot be cloned (private, not yet published, offline):
students upload this zip in the notebook's setup cell, which unpacks it safely.

    python3 tools/make_bundle.py            # -> dist/studio_bundle.zip
    python3 tools/make_bundle.py --out x.zip

Included: src, config, challenges, fixtures, game, notebooks (+ licences, requirements).
Excluded: tests, node_modules, .git, dist, caches, saved student state files.
"""
from __future__ import annotations

import argparse
import fnmatch
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOP = "game-localisation-studio"
INCLUDE_DIRS = ("src", "config", "challenges", "fixtures", "game", "notebooks")
INCLUDE_FILES = ("LICENSE", "LICENSE-CONTENT", "requirements.txt", "README.md")
EXCLUDE_DIRS = {"tests", "node_modules", ".git", "dist", "__pycache__", ".pytest_cache",
                ".ipynb_checkpoints", "exports", ".claude", "test-results", "playwright-report"}
EXCLUDE_PATTERNS = ("*.pyc", ".DS_Store", "studio_state*.json", ".env", "*.key", ".tmp_*")
FIXED_DATE = (2026, 1, 1, 0, 0, 0)   # reproducible zips


def bundle_files(root: Path = ROOT) -> list[Path]:
    files: list[Path] = []
    for d in INCLUDE_DIRS:
        base = root / d
        if not base.is_dir():
            continue
        for p in sorted(base.rglob("*")):
            rel = p.relative_to(root)
            if any(part in EXCLUDE_DIRS for part in rel.parts) or not p.is_file() or p.is_symlink():
                continue
            if any(fnmatch.fnmatch(p.name, pat) for pat in EXCLUDE_PATTERNS):
                continue
            files.append(p)
    for f in INCLUDE_FILES:
        if (root / f).is_file():
            files.append(root / f)
    return files


def build_bundle(out: Path | None = None, root: Path = ROOT) -> Path:
    out = Path(out) if out else root / "dist" / "studio_bundle.zip"
    out.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for p in bundle_files(root):
            rel = p.relative_to(root).as_posix()
            info = zipfile.ZipInfo(f"{TOP}/{rel}", date_time=FIXED_DATE)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            zf.writestr(info, p.read_bytes())
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, default=None, help="output zip (default dist/studio_bundle.zip)")
    args = ap.parse_args(argv)
    out = build_bundle(args.out)
    with zipfile.ZipFile(out) as zf:
        n = len(zf.infolist())
    print(f"Wrote {out} ({out.stat().st_size // 1024} KB, {n} files). "
          "Give this file to students if the GitHub clone does not work.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
